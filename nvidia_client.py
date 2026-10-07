"""NVIDIA NIM API client for Sudarshana Chakra.

Speaks the OpenAI-compatible chat completions protocol used by the NVIDIA
build/API endpoint (https://integrate.api.nvidia.com/v1). The API key is
resolved from the NVIDIA_API_KEY environment variable (typically sourced
from the project .env file) and falls back to config/api_keys.json so the
key is never hardcoded in source.
"""

import base64
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

import requests

from core.env import load_dotenv
from core.security import sanitize_prompt, looks_like_injection, redact_secrets

# Load .env (GEMINI_API_KEY / NVIDIA_API_KEY) before reading any key.
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nvidia_client")

API_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
DEFAULT_MODEL = "meta/llama-3.2-90b-vision-instruct"
DEFAULT_MAX_TOKENS = 4096
DEFAULT_TEMPERATURE = 0.7
REQUEST_TIMEOUT = 90
MAX_RETRIES = 2
RETRY_DELAY = 2

TEXT_MODELS: list[str] = [
    "meta/llama-3.2-90b-vision-instruct",
    "meta/llama-3.2-11b-vision-instruct",
    "nvidia/nemotron-3-super-120b-a12b",
    "openai/gpt-oss-20b",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
]

VISION_MODELS: list[str] = [
    "meta/llama-3.2-90b-vision-instruct",
    "meta/llama-3.2-11b-vision-instruct",
]


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


BASE_DIR = _get_base_dir()
API_KEY_PATH = BASE_DIR / "config" / "api_keys.json"


def _load_api_key() -> str:
    key = os.environ.get("NVIDIA_API_KEY", "").strip()
    if key:
        return key
    try:
        with open(API_KEY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return str(data.get("nvidia_api_key", "")).strip()
    except FileNotFoundError:
        return ""
    except Exception as e:
        logger.warning(f"[NVIDIA] Failed to load API key: {e}")
        return ""


class NvidiaClient:
    def __init__(self) -> None:
        self.api_key = _load_api_key()
        self._headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "SudarshanaChakra/1.0",
        }

    def _call(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
        response_format: Optional[dict] = None,
    ) -> Optional[str]:
        if not self.api_key:
            raise PermissionError(
                "NVIDIA API key is missing. Set NVIDIA_API_KEY in .env or in Settings → AI Providers."
            )
        payload: dict = {
            "model": model or DEFAULT_MODEL,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if response_format:
            payload["response_format"] = response_format

        last_exc: Optional[Exception] = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                resp = requests.post(API_URL, headers=self._headers, json=payload, timeout=REQUEST_TIMEOUT)
                if resp.status_code == 401 or resp.status_code == 403:
                    raise PermissionError(f"NVIDIA API authentication failed ({resp.status_code}): {resp.text[:300]}")
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("choices", [{}])[0].get("message", {}).get("content") or ""
                if resp.status_code == 429:
                    time.sleep(RETRY_DELAY * (attempt + 1))
                    continue
                last_exc = RuntimeError(f"[NVIDIA] API error {resp.status_code}: {resp.text[:300]}")
            except requests.Timeout:
                last_exc = RuntimeError("[NVIDIA] Request timed out.")
            except requests.RequestException as e:
                last_exc = RuntimeError(f"[NVIDIA] Request failed: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
        raise last_exc or RuntimeError("[NVIDIA] Unknown request failure.")

    def chat(
        self,
        prompt: str,
        system: str = "You are a helpful assistant.",
        history: Optional[list[dict]] = None,
        model: Optional[str] = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
    ) -> str:
        if looks_like_injection(prompt):
            logger.warning("[NVIDIA] Possible prompt-injection attempt neutralized.")
        prompt = sanitize_prompt(prompt)
        messages: list[dict] = [{"role": "system", "content": system}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": prompt})
        result = self._call(messages, model=model, max_tokens=max_tokens, temperature=temperature)
        if not result:
            raise RuntimeError("NVIDIA API returned an empty response.")
        return result

    def chat_json(
        self,
        prompt: str,
        system: str = "Return ONLY valid JSON.",
        model: Optional[str] = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> dict:
        if looks_like_injection(prompt):
            logger.warning("[NVIDIA] Possible prompt-injection attempt neutralized (json).")
        prompt = sanitize_prompt(prompt)
        messages = [
            {"role": "system", "content": system + " Output valid JSON only, without any markdown formatting."},
            {"role": "user", "content": prompt},
        ]
        raw = self._call(messages, model=model, max_tokens=max_tokens, temperature=0.2, response_format={"type": "json_object"})
        if not raw:
            raise RuntimeError("NVIDIA API returned an empty response.")
        clean = raw.strip()
        if clean.startswith("```"):
            parts = clean.split("```")
            clean = parts[1] if len(parts) > 1 else clean
            if clean.startswith("json"):
                clean = clean[4:]
        clean = clean.strip().rstrip("`").strip()
        try:
            return json.loads(clean)
        except json.JSONDecodeError as e:
            raise ValueError(f"NVIDIA model returned unparseable JSON: {e}\nRaw output: {raw[:200]}")

    def vision(
        self,
        prompt: str,
        image_b64: str,
        mime: str = "image/png",
        system: str = "Analyze the image.",
        model: Optional[str] = None,
        max_tokens: int = 1024,
    ) -> str:
        messages = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_b64}"}},
                    {"type": "text", "text": prompt},
                ],
            },
        ]
        result = self._call(messages, model=model or VISION_MODELS[0], max_tokens=max_tokens, temperature=0.2)
        if not result:
            raise RuntimeError("NVIDIA vision request failed.")
        return result

    def vision_from_file(
        self,
        prompt: str,
        image_path: str,
        system: str = "Analyze the image.",
        model: Optional[str] = None,
        max_tokens: int = 1024,
    ) -> str:
        path = Path(image_path)
        mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif"}
        mime = mime_map.get(path.suffix.lower(), "image/png")
        with open(path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode("utf-8")
        return self.vision(prompt, image_b64, mime, system, model, max_tokens)

    def multi_turn(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
    ) -> str:
        result = self._call(messages, model=model, max_tokens=max_tokens, temperature=temperature)
        if not result:
            raise RuntimeError("NVIDIA multi-turn request failed.")
        return result


client = NvidiaClient()
NvidiaLLMClient = NvidiaClient


if __name__ == "__main__":
    print("NVIDIA client self-test")
    print(f"NVIDIA model pool: {TEXT_MODELS}")
    print(f"API key configured: {bool(client.api_key)}")