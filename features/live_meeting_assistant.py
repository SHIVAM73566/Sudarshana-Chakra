"""
Feature: live_meeting_assistant
Description: Joins a Zoom/Teams/Google Meet link in the browser, live-transcribes the meeting
audio, and produces a summary with action items during or after the call.
"""

FEATURE_METADATA = {
    "name": "live_meeting_assistant",
    "aliases": [
        "meeting assistant", "meeting mode", "join meeting", "live meeting",
        "meeting summary", "meeting action items", "meeting transcript",
    ],
    "description": (
        "Live video meeting assistant. Joins a Zoom, Microsoft Teams or Google Meet link in the "
        "browser, captures the meeting audio for a real-time transcript, and produces an executive "
        "summary plus assigned action items during or after the call. Use for joining a meeting, "
        "turning meeting mode on/off, reading the live transcript, or getting the meeting report."
    ),
    "triggers": [
        "join this meeting",
        "start meeting mode",
        "live transcribe the meeting",
        "summarize this meeting",
        "action items from the meeting",
        "meeting transcript",
        "end meeting mode",
        "what is being said in the meeting",
    ],
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "join | start | stop | status | transcript | report | action_items. Defaults to join when a url is given, otherwise status.",
            },
            "url": {
                "type": "STRING",
                "description": "Full meeting link (https://zoom.us/j/..., https://teams.microsoft.com/l/meetup-join/..., https://meet.google.com/xxx-yyyy-zzz).",
            },
            "platform": {
                "type": "STRING",
                "description": "Zoom | Google Meet | Microsoft Teams | WhatsApp | Discord. Auto-detected from the url when omitted.",
            },
            "title": {"type": "STRING", "description": "Meeting title or topic used in the report."},
            "context": {"type": "STRING", "description": "Extra context about the meeting (attendees, agenda, goals)."},
        },
        "required": [],
    },
    "version": "1.0.0",
    "active": True,
}

import time


def _assistant():
    from actions.meeting_assistant import MeetingAssistant
    return MeetingAssistant.ensure()


def _fmt_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h {m}m"
    return f"{m}m {s}s" if m else f"{s}s"


def _status_payload(inst) -> dict:
    running = inst.is_running()
    source = inst._audio_source or {}
    return {
        "running": running,
        "title": inst._title,
        "platform": inst._platform,
        "url": inst._join_url,
        "audio_source": source.get("label") or "none found",
        "audio_loopback": bool(source.get("loopback")),
        "transcript_lines": len(inst.transcript()),
        "latest_speech": inst.latest_speech(),
        "summary": inst._last_answer,
        "elapsed": _fmt_duration(time.time() - inst._started_at) if inst._started_at and running else "0s",
    }


def execute(**kwargs):
    """Live meeting assistant: join, transcribe, summarize and extract action items."""
    action = str(kwargs.get("action") or "").strip().lower()
    url = str(kwargs.get("url") or "").strip()
    platform = str(kwargs.get("platform") or "").strip()
    title = str(kwargs.get("title") or "").strip()
    context = str(kwargs.get("context") or "").strip()

    if not action:
        action = "join" if url else "status"

    inst = _assistant()

    # ---------------------------------------------------------------- join
    if action == "join":
        if not url:
            return {
                "success": False,
                "error": "No meeting link supplied. Provide the 'url' of the Zoom, Teams or Google Meet call.",
            }
        msg = inst.join(url, platform)
        if title:
            inst.update_context(title=title)
        if context:
            inst.update_context(context=context)
        status = _status_payload(inst)
        return {
            "success": True,
            "summary": msg,
            "output": msg,
            "status": status,
            "message": msg,
        }

    # ---------------------------------------------------------------- start
    if action == "start":
        inst.start(title=title or inst._title or "Meeting mode", context=context or inst._context)
        src = inst._audio_source or {}
        msg = (
            f"Meeting mode on for '{inst._title}'. "
            f"Audio source: {src.get('label') or 'no loopback device found'}. "
            "Live transcription and screen watching are active."
        )
        return {"success": True, "summary": msg, "output": msg, "status": _status_payload(inst)}

    # ---------------------------------------------------------------- stop
    if action == "stop":
        was_running = inst.is_running()
        report = inst.generate_report() if (was_running or inst.transcript()) else None
        inst.stop()
        if not report:
            msg = "Meeting mode stopped. Nothing was captured."
            return {"success": True, "summary": msg, "output": msg}
        msg = _report_text(report, include_transcript=False)
        return {"success": True, "summary": report.get("summary", ""), "output": msg, "report": report}

    # ------------------------------------------------------------- status
    if action == "status":
        status = _status_payload(inst)
        if not status["running"]:
            msg = f"Meeting mode is OFF. Title: {status['title']}."
        else:
            msg = (
                f"Meeting mode is LIVE on '{status['title']}' ({status['elapsed']}). "
                f"Audio: {status['audio_source']}. "
                f"Transcript lines: {status['transcript_lines']}."
            )
            if status["latest_speech"]:
                msg += f" Last heard: {status['latest_speech']}"
        return {"success": True, "summary": msg, "output": msg, "status": status}

    # ---------------------------------------------------------- transcript
    if action == "transcript":
        lines = inst.transcript()
        if not lines:
            return {
                "success": True,
                "summary": "No transcript captured yet.",
                "output": "No transcript captured yet. Make sure meeting mode is running and a loopback/stereo-mix audio device is available.",
            }
        text = inst.transcript_text(limit=200)
        return {
            "success": True,
            "summary": f"{len(lines)} transcript lines captured.",
            "output": text,
            "lines": len(lines),
        }

    # -------------------------------------------------------------- report
    if action in ("report", "action_items", "summary"):
        if not inst.transcript() and not inst.is_running():
            return {
                "success": False,
                "error": "No meeting has been captured yet. Start or join a meeting first.",
            }
        report = inst.generate_report()
        if action == "action_items":
            items = report.get("action_items") or []
            msg = "\n".join(f"- {i}" for i in items) if items else "No action items were identified."
            return {"success": True, "summary": f"{len(items)} action items.", "output": msg, "action_items": items, "report": report}
        return {
            "success": True,
            "summary": report.get("summary", ""),
            "output": _report_text(report, include_transcript=False),
            "report": report,
        }

    return {"success": False, "error": f"Unknown action '{action}'. Use join, start, stop, status, transcript, report or action_items."}


def _report_text(report: dict, include_transcript: bool = False) -> str:
    def bullets(items):
        return "\n".join(f"- {i}" for i in items) if items else "- None"

    parts = [
        f"MEETING: {report.get('title') or 'Untitled'}",
        f"Platform: {report.get('platform') or 'n/a'}  |  Duration: {report.get('duration')}",
        "",
        "SUMMARY:",
        str(report.get("summary") or ""),
        "",
        "ACTION ITEMS:",
        bullets(report.get("action_items")),
        "",
        "DECISIONS:",
        bullets(report.get("decisions")),
        "",
        "OPEN QUESTIONS:",
        bullets(report.get("questions")),
        "",
        "NEXT STEPS:",
        bullets(report.get("next_steps")),
    ]
    if report.get("path"):
        parts += ["", f"Saved report: {report['path']}"]
    if include_transcript:
        parts += ["", "TRANSCRIPT:", str(report.get("transcript") or "")]
    return "\n".join(parts)
