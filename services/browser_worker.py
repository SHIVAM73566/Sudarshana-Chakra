"""
Persistent-Profile Browser Worker (Chrome DevTools Protocol)
============================================================

Playwright worker that keeps the user authenticated across sessions instead of
throwing away the profile on every launch. Two attachment strategies, tried in
order:

1.  ``connect_over_cdp`` - attach to a Chrome/Edge instance the user (or a
    previous run) started with ``--remote-debugging-port``. Logins, cookies,
    extensions and open tabs are all reused.
2.  ``launch_persistent_context`` - launch Chrome against a dedicated profile
    directory under the Sudarshana user-data folder, so cookies and tokens
    survive app restarts.

The browser is driven from a dedicated background thread that owns its own
asyncio loop, so callers (the Qt main thread, the agent executor) use the plain
synchronous ``BrowserWorker`` API and never touch the event loop.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.user_paths import get_user_data_dir

DEFAULT_CDP_PORT = 9222
DEFAULT_PROFILE_DIRNAME = "chrome_profile"
LAUNCH_TIMEOUT = 45.0
ACTION_TIMEOUT = 30.0

_CHROME_CANDIDATES = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
)


def chrome_executable() -> Optional[str]:
    """Resolves the host Chrome/Edge binary, or None when unavailable."""
    local = os.environ.get("LOCALAPPDATA")
    candidates: List[str] = []
    if local:
        candidates.extend(
            [
                os.path.join(local, "Google", "Chrome", "Application", "chrome.exe"),
                os.path.join(local, "Microsoft", "Edge", "Application", "msedge.exe"),
            ]
        )
    candidates.extend(_CHROME_CANDIDATES)
    candidates.extend(
        path for path in (
            shutil.which("chrome"),
            shutil.which("google-chrome"),
            shutil.which("msedge"),
        ) if path
    )
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return None


def profile_dir() -> Path:
    """Dedicated, app-owned Chrome profile directory."""
    path = get_user_data_dir() / "config" / DEFAULT_PROFILE_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def cdp_endpoint(port: int = DEFAULT_CDP_PORT) -> str:
    return f"http://127.0.0.1:{port}"


def is_cdp_available(port: int = DEFAULT_CDP_PORT, host: str = "127.0.0.1") -> bool:
    """True when something is already listening on the CDP port."""
    with socket.socket() as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def launch_chrome_with_cdp(port: int = DEFAULT_CDP_PORT, url: str = "about:blank") -> bool:
    """Starts a detached Chrome exposing a CDP endpoint on ``port``.

    Returns True when the debug endpoint answers within a few seconds.
    """
    exe = chrome_executable()
    if not exe:
        return False
    args = [
        exe,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile_dir()}",
        "--no-first-run",
        "--no-default-browser-check",
        url,
    ]
    creation = 0x00000008 | 0x00000200 if sys.platform == "win32" else 0
    try:
        subprocess.Popen(
            args,
            creationflags=creation,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return False

    import time

    for _ in range(40):
        if is_cdp_available(port):
            return True
        time.sleep(0.5)
    return False


class _BrowserLoop:
    """Owns the Playwright objects on a private asyncio loop / thread."""

    def __init__(self, headless: bool = False, cdp_port: int = DEFAULT_CDP_PORT):
        self._headless = headless
        self._cdp_port = cdp_port
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._ready = threading.Event()
        self._lock = threading.Lock()
        self._playwright = None
        self._context = None
        self._browser = None
        self._page = None
        self._mode = ""

    # -- lifecycle -----------------------------------------------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._ready.clear()
        self._thread = threading.Thread(target=self._run_loop, name="browser-worker", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=LAUNCH_TIMEOUT)

    def _run_loop(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._startup())
        except Exception:
            self._ready.set()
        loop.run_forever()

    async def _startup(self) -> None:
        try:
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
            await self._ensure_connected()
        finally:
            self._ready.set()

    async def _ensure_connected(self) -> None:
        if self._context is not None:
            return

        endpoint = cdp_endpoint(self._cdp_port)
        if is_cdp_available(self._cdp_port):
            try:
                self._browser = await self._playwright.chromium.connect_over_cdp(endpoint)
                contexts = self._browser.contexts
                self._context = contexts[0] if contexts else await self._browser.new_context()
                self._mode = f"cdp:{endpoint}"
                return
            except Exception:
                self._browser = None

        exe = chrome_executable()
        kwargs: Dict[str, Any] = {
            "user_data_dir": str(profile_dir()),
            "headless": self._headless,
            "args": ["--start-maximized", "--no-first-run", "--no-default-browser-check"],
            "viewport": None,
        }
        if exe:
            kwargs["executable_path"] = exe
        self._context = await self._playwright.chromium.launch_persistent_context(**kwargs)
        self._mode = f"persistent:{profile_dir()}"

    async def _get_page(self):
        if self._context is None:
            await self._ensure_connected()
        pages = getattr(self._context, "pages", None) or []
        live = [p for p in pages if not p.is_closed()]
        if live:
            self._page = live[-1]
        else:
            self._page = await self._context.new_page()
        return self._page

    # -- execution -----------------------------------------------------
    def run(self, coro_factory, timeout: float = ACTION_TIMEOUT) -> Any:
        """Runs ``coro_factory()`` on the worker loop and blocks for the result."""
        self.start()
        if self._loop is None:
            raise RuntimeError("browser worker failed to start")
        future = asyncio.run_coroutine_threadsafe(coro_factory(), self._loop)
        return future.result(timeout=timeout)

    def shutdown(self) -> None:
        loop = self._loop
        if loop is None:
            return

        async def _close() -> None:
            try:
                if self._context is not None:
                    await self._context.close()
            except Exception:
                pass
            try:
                if self._browser is not None:
                    await self._browser.close()
            except Exception:
                pass
            try:
                if self._playwright is not None:
                    await self._playwright.stop()
            except Exception:
                pass

        try:
            asyncio.run_coroutine_threadsafe(_close(), loop).result(timeout=15)
        except Exception:
            pass
        loop.call_soon_threadsafe(loop.stop)
        self._loop = None
        self._context = None
        self._browser = None
        self._page = None
        self._thread = None


class BrowserWorker:
    """Synchronous, thread-safe facade over the persistent browser session."""

    def __init__(self, headless: bool = False, cdp_port: int = DEFAULT_CDP_PORT):
        self._loop = _BrowserLoop(headless=headless, cdp_port=cdp_port)
        self._lock = threading.Lock()

    @property
    def mode(self) -> str:
        return self._loop._mode

    def _require_playwright(self) -> None:
        import importlib.util

        if importlib.util.find_spec("playwright") is None:
            raise RuntimeError(
                "Playwright is not installed. Run: pip install playwright && playwright install chromium"
            )

    # -- primitives ----------------------------------------------------
    def open(self, url: str, wait_until: str = "domcontentloaded") -> Dict[str, Any]:
        self._require_playwright()

        async def action():
            page = await self._loop._get_page()
            response = await page.goto(url, wait_until=wait_until, timeout=int(ACTION_TIMEOUT * 1000))
            return {
                "url": page.url,
                "title": await page.title(),
                "status": getattr(response, "status", None),
                "mode": self._loop._mode,
            }

        with self._lock:
            return self._loop.run(action)

    def html(self, url: Optional[str] = None) -> str:
        self._require_playwright()

        async def action():
            page = await self._loop._get_page()
            if url:
                await page.goto(url, wait_until="domcontentloaded", timeout=int(ACTION_TIMEOUT * 1000))
            return await page.content()

        with self._lock:
            return self._loop.run(action)

    def text(self, url: Optional[str] = None) -> str:
        self._require_playwright()

        async def action():
            page = await self._loop._get_page()
            if url:
                await page.goto(url, wait_until="domcontentloaded", timeout=int(ACTION_TIMEOUT * 1000))
            return (await page.inner_text("body"))[:20000]

        with self._lock:
            return self._loop.run(action)

    def evaluate(self, expression: str, url: Optional[str] = None) -> Any:
        self._require_playwright()

        async def action():
            page = await self._loop._get_page()
            if url:
                await page.goto(url, wait_until="domcontentloaded", timeout=int(ACTION_TIMEOUT * 1000))
            return await page.evaluate(expression)

        with self._lock:
            return self._loop.run(action)

    def click(self, selector: str, timeout_ms: int = 15000) -> bool:
        self._require_playwright()

        async def action():
            page = await self._loop._get_page()
            await page.click(selector, timeout=timeout_ms)
            return True

        with self._lock:
            try:
                return self._loop.run(action)
            except Exception:
                return False

    def fill(self, selector: str, value: str, timeout_ms: int = 15000) -> bool:
        self._require_playwright()

        async def action():
            page = await self._loop._get_page()
            await page.fill(selector, value, timeout=timeout_ms)
            return True

        with self._lock:
            try:
                return self._loop.run(action)
            except Exception:
                return False

    def screenshot(self, path: Optional[str] = None) -> str:
        self._require_playwright()
        target = Path(path) if path else get_user_data_dir() / "deliverables" / "browser_shot.png"
        target.parent.mkdir(parents=True, exist_ok=True)

        async def action():
            page = await self._loop._get_page()
            await page.screenshot(path=str(target), full_page=True)
            return str(target)

        with self._lock:
            return self._loop.run(action)

    def extract_links(self, url: str, pattern: str = "") -> List[Dict[str, str]]:
        """Returns visible anchors, optionally filtered by a substring of the href."""
        self._require_playwright()

        async def action():
            page = await self._loop._get_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=int(ACTION_TIMEOUT * 1000))
            raw = await page.evaluate(
                "() => Array.from(document.querySelectorAll('a[href]')).map(a => "
                "({href: a.href, text: (a.innerText || '').trim().slice(0, 160)}))"
            )
            return raw or []

        with self._lock:
            links = self._loop.run(action)
        if pattern:
            needle = pattern.lower()
            links = [link for link in links if needle in (link.get("href") or "").lower()]
        seen = set()
        unique: List[Dict[str, str]] = []
        for link in links:
            href = link.get("href")
            if href and href not in seen:
                seen.add(href)
                unique.append(link)
        return unique

    def close(self) -> None:
        with self._lock:
            self._loop.shutdown()


_SHARED: Optional[BrowserWorker] = None
_SHARED_LOCK = threading.Lock()


def get_browser(headless: bool = False) -> BrowserWorker:
    """Process-wide persistent browser session."""
    global _SHARED
    with _SHARED_LOCK:
        if _SHARED is None:
            _SHARED = BrowserWorker(headless=headless)
        return _SHARED


def close_browser() -> None:
    global _SHARED
    with _SHARED_LOCK:
        if _SHARED is not None:
            _SHARED.close()
            _SHARED = None


def browser_worker(parameters: Optional[Dict[str, Any]] = None, **_: Any) -> Dict[str, Any]:
    """Callable facade used by the agent executor.

    Actions: ``open | text | html | links | screenshot | eval | status | close``.
    """
    params = parameters or {}
    action = str(params.get("action") or "status").strip().lower()

    if action == "status":
        return {
            "success": True,
            "message": (
                f"Browser worker idle. Chrome: {chrome_executable() or 'not found'}. "
                f"CDP port {DEFAULT_CDP_PORT} "
                f"{'reachable' if is_cdp_available() else 'not running'}."
            ),
            "cdp_available": is_cdp_available(),
            "chrome": chrome_executable(),
            "profile": str(profile_dir()),
        }

    if action == "close":
        close_browser()
        return {"success": True, "message": "Persistent browser session closed."}

    if action == "launch":
        port = int(params.get("port") or DEFAULT_CDP_PORT)
        ok = launch_chrome_with_cdp(port=port, url=str(params.get("url") or "about:blank"))
        return {
            "success": ok,
            "message": (
                f"Chrome launched with CDP on port {port}." if ok
                else f"Could not start Chrome with CDP on port {port}; falling back to a persistent context."
            ),
            "cdp_available": ok,
        }

    url = str(params.get("url") or "").strip()
    if not url and action in {"open", "text", "html", "links", "screenshot"}:
        return {"success": False, "error": "A url is required for this action."}

    worker = get_browser()
    try:
        if action == "open":
            return {"success": True, "message": "Page opened.", "data": worker.open(url)}
        if action == "text":
            return {"success": True, "message": "Page text captured.", "text": worker.text(url)}
        if action == "html":
            return {"success": True, "message": "Page HTML captured.", "html": worker.html(url)}
        if action == "links":
            links = worker.extract_links(url, pattern=str(params.get("pattern") or ""))
            return {"success": True, "message": f"{len(links)} links found.", "links": links}
        if action == "screenshot":
            path = worker.screenshot(params.get("path"))
            return {"success": True, "message": f"Screenshot saved to {path}", "path": path}
        if action == "eval":
            expression = str(params.get("expression") or "").strip()
            if not expression:
                return {"success": False, "error": "An expression is required for eval."}
            return {"success": True, "data": worker.evaluate(expression, url or None)}
        if action in {"click", "fill"}:
            selector = str(params.get("selector") or "").strip()
            if not selector:
                return {"success": False, "error": "A selector is required."}
            if action == "click":
                return {"success": worker.click(selector), "message": f"Clicked {selector}."}
            ok = worker.fill(selector, str(params.get("text") or ""))
            return {"success": ok, "message": f"Filled {selector}."}
    except Exception as exc:
        return {"success": False, "error": f"{type(exc).__name__}: {exc}"}

    return {"success": False, "error": f"Unknown browser action '{action}'."}


def main() -> int:
    """Smoke test: report the resolved Chrome, profile and CDP availability."""
    report = browser_worker({"action": "status"})
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
