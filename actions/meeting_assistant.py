from __future__ import annotations
from core.user_paths import get_user_data_dir

import base64
import hashlib
import io
import json
import os
import re
import threading
import time
import wave
from pathlib import Path
from typing import Callable

import mss
import mss.tools
import sounddevice as sd
from google import genai
from google.genai import types

try:
    import PIL.Image
    _PIL_OK = True
except Exception:  # pragma: no cover
    PIL = None
    _PIL_OK = False


def _base_dir() -> Path:
    return Path(__file__).resolve().parent.parent


BASE_DIR = _base_dir()
API_CONFIG_PATH = get_user_data_dir() / "config" / "api_keys.json"
LIVE_MODEL = "models/gemini-2.5-flash-native-audio-preview-12-2025"
IMG_MAX_W = 1280
IMG_MAX_H = 720
JPEG_Q = 72
AUD_SAMPLE_RATE = 16000
AUD_CHUNK_SECONDS = 5.0


def _get_api_key() -> str:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        keys = json.load(f)
    key = keys.get("gemini_api_key", "")
    if not key:
        raise RuntimeError("gemini_api_key not found")
    return key


def _capture_screen() -> bytes:
    with mss.mss() as sct:
        shot = sct.grab(sct.monitors[1])
        png_bytes = mss.tools.to_png(shot.rgb, shot.size)
    if not _PIL_OK:
        return png_bytes
    img = PIL.Image.open(io.BytesIO(png_bytes)).convert("RGB")
    img.thumbnail([IMG_MAX_W, IMG_MAX_H], PIL.Image.BILINEAR)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_Q, optimize=False)
    return buf.getvalue()


def _extract_text(response) -> str:
    parts: list[str] = []
    try:
        for candidate in getattr(response, "candidates", []) or []:
            content = getattr(candidate, "content", None)
            if not content:
                continue
            for part in getattr(content, "parts", []) or []:
                txt = getattr(part, "text", None)
                if txt:
                    parts.append(txt)
    except Exception:
        pass
    if parts:
        return "".join(parts).strip()
    return (getattr(response, "text", "") or "").strip()


def _wav_bytes(pcm_bytes: bytes, channels: int, sample_rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(max(1, int(channels)))
        wf.setsampwidth(2)
        wf.setframerate(max(8000, int(sample_rate)))
        wf.writeframes(pcm_bytes)
    return buf.getvalue()


def _audio_input_source() -> dict:
    try:
        devices = sd.query_devices()
    except Exception:
        devices = []

    for idx, dev in enumerate(devices):
        name = (dev.get("name") or "").lower()
        if "stereo mix" in name or "what u hear" in name or "what you hear" in name:
            return {
                "device": idx,
                "channels": max(1, min(2, int(dev.get("max_input_channels") or 2))),
                "samplerate": int(dev.get("default_samplerate") or AUD_SAMPLE_RATE),
                "loopback": False,
                "label": dev.get("name") or f"Device {idx}",
            }

    try:
        hostapis = sd.query_hostapis()
        for api_idx, api in enumerate(hostapis):
            if "wasapi" not in (api.get("name") or "").lower():
                continue
            out_dev = api.get("default_output_device")
            if out_dev is None or out_dev < 0:
                continue
            dev = devices[out_dev]
            return {
                "device": out_dev,
                "channels": max(1, min(2, int(dev.get("max_output_channels") or 2))),
                "samplerate": int(dev.get("default_samplerate") or AUD_SAMPLE_RATE),
                "loopback": True,
                "label": dev.get("name") or f"WASAPI device {out_dev}",
            }
    except Exception:
        pass

    try:
        default_output = sd.default.device[1]
        if isinstance(default_output, int) and default_output >= 0:
            dev = devices[default_output]
            return {
                "device": default_output,
                "channels": max(1, min(2, int(dev.get("max_output_channels") or 2))),
                "samplerate": int(dev.get("default_samplerate") or AUD_SAMPLE_RATE),
                "loopback": True,
                "label": dev.get("name") or f"Default output {default_output}",
            }
    except Exception:
        pass

    return {}


_PLATFORM_HOSTS = (
    ("zoom", "Zoom"),
    ("teams.microsoft", "Microsoft Teams"),
    ("meet.google", "Google Meet"),
    ("web.whatsapp", "WhatsApp"),
    ("whatsapp", "WhatsApp"),
    ("discord", "Discord"),
    ("skype", "Skype"),
    ("webex", "Webex"),
    ("gotomeeting", "GoToMeeting"),
    ("whereby", "Whereby"),
)


def _guess_platform(url: str) -> str:
    low = (url or "").lower()
    for needle, label in _PLATFORM_HOSTS:
        if needle in low:
            return label
    return ""


def _clean_response(text: str) -> tuple[str, str]:
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    if not lines:
        return "", ""
    summary = ""
    answer = ""
    for ln in lines:
        low = ln.lower()
        if low.startswith(("summary:", "meeting:", "topic:")) and not summary:
            summary = ln.split(":", 1)[-1].strip()
        elif low.startswith(("answer:", "response:", "reply:")) and not answer:
            answer = ln.split(":", 1)[-1].strip()
    if not summary:
        summary = lines[0]
    if not answer and len(lines) > 1:
        answer = lines[1]
    return summary, answer


class MeetingAssistant:
    _active_instance: "MeetingAssistant | None" = None

    @classmethod
    def get_active(cls) -> "MeetingAssistant | None":
        return cls._active_instance

    @classmethod
    def ensure(cls) -> "MeetingAssistant":
        inst = cls._active_instance
        if inst is None:
            inst = cls()
        return inst

    def __init__(
        self,
        on_update: Callable[[dict], None] | None = None,
        on_state: Callable[[str], None] | None = None,
        interval: float = 6.0,
    ):
        self._on_update = on_update
        self._on_state = on_state
        self._interval = max(4.0, float(interval))
        self._running = False
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._last_hash = ""
        self._last_audio_hash = ""
        self._last_answer = ""
        self._last_speech = ""
        self._context = ""
        self._title = "Meeting mode"
        self._audio_thread: threading.Thread | None = None
        self._audio_stop = threading.Event()
        self._audio_lock = threading.Lock()
        self._audio_buf = bytearray()
        self._audio_source = {}
        self._speech_gen = 0
        self._transcript: list[dict] = []
        self._started_at = 0.0
        self._platform = ""
        self._join_url = ""
        self._report: dict | None = None
        self._report_lock = threading.Lock()
        MeetingAssistant._active_instance = self

    def join(self, url: str, platform: str = "") -> str:
        """Open a meeting link in the persistent browser session and wait for it to load."""
        if not url:
            return "No meeting link provided."
        if not re.match(r"^https?://", url.strip(), re.I):
            url = "https://" + url.strip()
        self._join_url = url.strip()
        self._platform = (platform or _guess_platform(url)).strip()
        try:
            from actions.browser_control import browser_control
            result = browser_control({"action": "go_to", "url": self._join_url})
        except Exception as exc:
            return f"Could not open the meeting link: {exc}"
        self.start(title=self._title if self._title != "Meeting mode" else f"{self._platform} meeting".strip(),
                   context=f"Joined via browser: {self._join_url}")
        return f"Opened {self._platform or 'the'} meeting in the browser: {self._join_url}. {result}"

    def start(self, *, title: str = "Meeting mode", context: str = "") -> None:
        if self._running:
            self.update_context(title or None, context if context is not None else None)
            return
        self._title = title or "Meeting mode"
        self._context = context or ""
        self._transcript = []
        self._report = None
        self._started_at = time.time()
        self._running = True
        self._stop_event.clear()
        self._audio_stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self._audio_source = _audio_input_source()
        if self._audio_source:
            self._audio_thread = threading.Thread(target=self._audio_loop, daemon=True)
            self._audio_thread.start()
        if self._on_state:
            self._on_state("MEETING")

    def stop(self) -> None:
        self._running = False
        self._stop_event.set()
        self._audio_stop.set()
        if self._on_state:
            self._on_state("LISTENING")

    def update_context(self, title: str | None = None, context: str | None = None) -> None:
        if title:
            self._title = title
        if context is not None:
            self._context = context

    def latest_speech(self) -> str:
        return self._last_speech

    def is_running(self) -> bool:
        return bool(self._running)

    def transcript_text(self, limit: int = 400) -> str:
        lines = [
            f"[{time.strftime('%H:%M:%S', time.localtime(t))}] {text}"
            for t, text in self._transcript[-limit:]
        ]
        return "\n".join(lines)

    def transcript(self) -> list[dict]:
        return list(self._transcript)

    def _record_speech(self, speech: str) -> None:
        if not speech:
            return
        if self._transcript and self._transcript[-1][1] == speech:
            return
        self._transcript.append({"t": time.time(), "text": speech})
        if len(self._transcript) > 4000:
            del self._transcript[:1000]

    def _transcribe_audio(self, client, wav_bytes: bytes) -> str:
        prompt = (
            "Transcribe the spoken words from this meeting audio. "
            "Return only the words other people are speaking. "
            "If there is no clear speech, return an empty string."
        )
        contents = [
            types.Part.from_bytes(data=wav_bytes, mime_type="audio/wav"),
            prompt,
        ]
        response = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=contents,
            config={"temperature": 0.0},
        )
        return _extract_text(response).strip()

    def _audio_loop(self) -> None:
        source = self._audio_source or {}
        if not source:
            return

        device = source.get("device")
        channels = int(source.get("channels") or 2)
        samplerate = int(source.get("samplerate") or AUD_SAMPLE_RATE)
        loopback = bool(source.get("loopback"))
        label = source.get("label") or "audio source"
        print(f"[MeetingAssistant] audio source: {label}")

        try:
            client = genai.Client(
                api_key=_get_api_key(),
                http_options={"api_version": "v1beta"},
            )
        except Exception as exc:
            print(f"[MeetingAssistant] audio model init failed: {exc}")
            return

        extra = None
        if loopback:
            try:
                extra = sd.WasapiSettings(loopback=True)
            except Exception:
                extra = None

        frame_bytes = int(samplerate * channels * 2)
        target_bytes = max(frame_bytes * 3, int(samplerate * channels * 2 * AUD_CHUNK_SECONDS))
        last_flush = time.time()

        def callback(indata, frames, time_info, status):
            if self._audio_stop.is_set():
                return
            try:
                with self._audio_lock:
                    self._audio_buf.extend(indata.tobytes())
            except Exception:
                pass

        try:
            with sd.InputStream(
                device=device,
                samplerate=samplerate,
                channels=channels,
                dtype="int16",
                blocksize=max(1024, int(samplerate * 0.25)),
                callback=callback,
                extra_settings=extra,
            ):
                while not self._audio_stop.is_set():
                    time.sleep(0.35)
                    should_flush = False
                    with self._audio_lock:
                        if len(self._audio_buf) >= target_bytes:
                            should_flush = True
                        elif self._audio_buf and (time.time() - last_flush) >= AUD_CHUNK_SECONDS:
                            should_flush = True
                        if not should_flush:
                            continue
                        pcm = bytes(self._audio_buf)
                        self._audio_buf.clear()
                    last_flush = time.time()
                    if not pcm:
                        continue
                    try:
                        wav_bytes = _wav_bytes(pcm, channels, samplerate)
                        digest = hashlib.sha1(wav_bytes).hexdigest()
                        if digest == self._last_audio_hash:
                            continue
                        speech = self._transcribe_audio(client, wav_bytes)
                        speech = re.sub(r"\s+", " ", (speech or "").strip())
                        if speech:
                            self._last_audio_hash = digest
                            self._last_speech = speech
                            self._speech_gen += 1
                            self._record_speech(speech)
                            payload = {
                                "active": True,
                                "title": self._title,
                                "summary": "Listening to the meeting audio.",
                                "answer": "",
                                "speech": speech,
                                "status": "speech",
                            }
                            if self._on_update:
                                self._on_update(payload)
                    except Exception as exc:
                        print(f"[MeetingAssistant] audio transcribe failed: {exc}")
        except Exception as exc:
            print(f"[MeetingAssistant] audio loop failed: {exc}")

    def _loop(self) -> None:
        try:
            client = genai.Client(
                api_key=_get_api_key(),
                http_options={"api_version": "v1beta"},
            )
        except Exception as exc:
            if self._on_update:
                self._on_update({
                    "active": False,
                    "title": self._title,
                    "summary": "Meeting mode could not start.",
                    "answer": str(exc),
                    "status": "error",
                })
            self.stop()
            return

        while not self._stop_event.is_set():
            try:
                image_bytes = _capture_screen()
                digest = hashlib.sha1(image_bytes).hexdigest()
                if digest == self._last_hash:
                    time.sleep(self._interval)
                    continue
                self._last_hash = digest
                spoken = self._last_speech

                prompt = f"""
You are Sudarshana Chakra AI running in meeting mode on a Windows desktop.
The screen belongs to a live Zoom, Microsoft Teams, WhatsApp call, or similar meeting.

Tasks:
1. Identify the meeting topic from what is visible.
2. If a question is visible on screen, answer it directly and briefly.
3. If no question is visible, give a very short helpful summary of what is happening.
4. Keep it to at most 3 short lines.
5. Use plain language and be confident.

Meeting title/context: {self._title}
Extra context: {self._context}
Latest spoken audio from the meeting: {spoken or 'No speech captured yet.'}

Return the result in this structure:
Summary: ...
Answer: ...
"""
                contents = [
                    types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                    prompt,
                ]
                response = client.models.generate_content(
                    model="gemini-3.8-flash",
                    contents=contents,
                    config={"temperature": 0.2},
                )
                text = _extract_text(response)
                summary, answer = _clean_response(text)
                self._last_answer = answer or summary
                payload = {
                    "active": True,
                    "title": self._title,
                    "summary": summary or "Watching the meeting screen.",
                    "answer": answer or summary or "No question detected yet.",
                    "speech": self._last_speech,
                    "status": "live",
                }
                if self._on_update:
                    self._on_update(payload)
            except Exception as exc:
                if self._on_update:
                    self._on_update({
                        "active": True,
                        "title": self._title,
                        "summary": "Meeting watch is active.",
                        "answer": f"Analysis paused: {exc}",
                        "status": "error",
                    })
            time.sleep(self._interval)

    def generate_report(self, save: bool = True) -> dict:
        """Summarize the meeting transcript into action items, decisions and next steps."""
        with self._report_lock:
            if self._report is not None:
                return self._report

            transcript = self.transcript_text(limit=400)
            started = self._started_at or time.time()
            duration = max(0, int(time.time() - started))
            minutes, seconds = divmod(duration, 60)
            duration_str = f"{minutes}m {seconds}s" if minutes else f"{seconds}s"

            report = {
                "title": self._title,
                "platform": self._platform or "Unknown",
                "url": self._join_url,
                "started_at": started,
                "duration": duration_str,
                "lines_captured": len(self._transcript),
                "summary": "No speech was captured during this meeting.",
                "action_items": [],
                "decisions": [],
                "questions": [],
                "risks": [],
                "next_steps": [],
                "path": "",
            }

            if not transcript:
                self._report = report
                return report

            try:
                client = genai.Client(
                    api_key=_get_api_key(),
                    http_options={"api_version": "v1beta"},
                )
            except Exception as exc:
                report["summary"] = f"Could not build the meeting report: {exc}"
                self._report = report
                return report

            prompt = f"""You are the meeting assistant for Sudarshana Chakra.
Below is the live transcript of a meeting. Produce a precise executive briefing.

Meeting title: {self._title}
Platform: {report['platform']}
Duration: {duration_str}
Extra context: {self._context}

TRANSCRIPT:
{transcript}

Return ONLY valid JSON, no markdown, no commentary:
{{
  "summary": "3-4 sentence executive summary of what was discussed and the outcome",
  "action_items": [{{"task": "specific action", "owner": "who", "due": "when or empty"}}],
  "decisions": ["decision that was made"],
  "questions": ["open question still unresolved"],
  "risks": ["risk or blocker mentioned"],
  "next_steps": ["ordered next step"]
}}
Rules: action_items must be concrete and assigned. Keep each list short (max 8). Empty list is fine when nothing applies."""

            try:
                response = client.models.generate_content(
                    model="gemini-3.8-flash",
                    contents=prompt,
                    config={"temperature": 0.2, "response_mime_type": "application/json"},
                )
                raw = _extract_text(response)
                data = _parse_json_object(raw)
                if not data:
                    raise ValueError("model returned no parseable JSON")
                report["summary"] = str(data.get("summary") or report["summary"]).strip()
                for key in ("action_items", "decisions", "questions", "risks", "next_steps"):
                    value = data.get(key)
                    if isinstance(value, list):
                        report[key] = [
                            (v if isinstance(v, str) else json.dumps(v, ensure_ascii=False))
                            for v in value
                            if str(v).strip()
                        ][:8]
            except Exception as exc:
                report["summary"] = f"Report generation failed: {exc}"

            if save:
                try:
                    report["path"] = _save_report_markdown(report, transcript)
                except Exception as exc:
                    print(f"[MeetingAssistant] report save failed: {exc}")

            self._report = report
            return report


def _parse_json_object(raw: str) -> dict | None:
    text = (raw or "").strip()
    if not text:
        return None
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I).strip()
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass
    try:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            obj = json.loads(text[start:end + 1])
            return obj if isinstance(obj, dict) else None
    except Exception:
        pass
    return None


def _save_report_markdown(report: dict, transcript: str) -> str:
    out_dir = get_user_data_dir() / "deliverables" / "meeting_reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S", time.localtime(report.get("started_at") or time.time()))
    safe_title = re.sub(r"[^a-zA-Z0-9]+", "_", report.get("title") or "meeting").strip("_")[:40] or "meeting"
    path = out_dir / f"{safe_title}_{stamp}.md"

    def _bullet(items) -> list[str]:
        if not items:
            return ["- None"]
        return [f"- {i}" for i in items]

    lines = [
        f"# {report.get('title') or 'Meeting Report'}",
        "",
        f"- **Platform:** {report.get('platform')}",
        f"- **Link:** {report.get('url') or 'n/a'}",
        f"- **Duration:** {report.get('duration')}",
        f"- **Captured lines:** {report.get('lines_captured')}",
        "",
        "## Summary",
        "",
        str(report.get("summary") or ""),
        "",
        "## Action Items",
        "",
        *_bullet(report.get("action_items")),
        "",
        "## Decisions",
        "",
        *_bullet(report.get("decisions")),
        "",
        "## Open Questions",
        "",
        *_bullet(report.get("questions")),
        "",
        "## Risks",
        "",
        *_bullet(report.get("risks")),
        "",
        "## Next Steps",
        "",
        *_bullet(report.get("next_steps")),
        "",
        "## Transcript",
        "",
        "```",
        transcript,
        "```",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)
