"""Multi-vendor license verification drivers.

Supports four ways to validate a buyer's license key after purchase:

* **Lemon Squeezy** - POST https://api.lemonsqueezy.com/v1/licenses/validate
* **Payhip**        - POST https://payhip.com/api/v2/license/verify
* **Gumroad**       - POST https://api.gumroad.com/v2/licenses/verify
* **Offline RSA**   - a signed JWT verified with the embedded public key

Every driver returns a normalized :class:`ProviderResult`. Network drivers are
best-effort: if the network is down the caller falls back to the offline token
path and (when configured) a cached positive result, so a legitimate buyer is
never locked out by a flaky connection.

The provider is chosen automatically from the key's shape, or forced with
``LICENSE_PROVIDER`` in ``.env``. All drivers are dormant until
``LICENSING_ENABLED=true`` (enforced by :mod:`core.license_guard`).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable

__all__ = [
    "ProviderResult",
    "detect_provider",
    "verify_with_provider",
    "provider_endpoints",
    "PROVIDERS",
]

_TIMEOUT = 12
_UA = "SudarshanaChakra/1.0 (+licensing)"


@dataclass
class ProviderResult:
    ok: bool
    provider: str
    message: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    offline: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "provider": self.provider,
            "message": self.message,
            "offline": self.offline,
        }


# --------------------------------------------------------------------------- #
# Key-shape detection
# --------------------------------------------------------------------------- #

# Compact JWT produced by our offline signer: three base64url segments.
_JWT_RE = re.compile(r"^[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+$")
# Lemon Squeezy license keys look like UUID4: 8-4-4-4-12 hex.
_LS_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
# Payhip / Gumroad product keys are typically alphanumeric with dashes.
_PAYHIP_RE = re.compile(r"^[A-Z0-9]{4,}(?:-[A-Z0-9]{4,}){1,}$", re.IGNORECASE)
# Gumroad keys historically look like: A1B2C3D4-12345678 or long hex-ish tokens.
_GUMROAD_RE = re.compile(r"^[A-Z0-9]{8}-[A-Z0-9]{8,}$", re.IGNORECASE)


def detect_provider(license_key: str) -> str:
    """Guess which provider issued ``license_key``.

    ``LICENSE_PROVIDER`` (env) wins when set to a known provider. Otherwise the
    key's shape decides, defaulting to ``offline`` (the RSA token path) which is
    always tried last as a safe fallback.
    """
    forced = (os.environ.get("LICENSE_PROVIDER") or "").strip().lower()
    if forced in PROVIDERS:
        return forced
    if forced in ("rsa", "jwt", "offline_token"):
        return "offline"

    key = (license_key or "").strip()
    if not key:
        return "offline"
    if key.count(".") == 2 and _JWT_RE.match(key):
        return "offline"
    if _LS_RE.match(key):
        return "lemonsqueezy"
    if _GUMROAD_RE.match(key):
        return "gumroad"
    if _PAYHIP_RE.match(key):
        return "payhip"
    # Unknown shape: try the vendors that accept free-form keys, then offline.
    return "payhip"


# --------------------------------------------------------------------------- #
# HTTP helper (stdlib only)
# --------------------------------------------------------------------------- #

def _post_json(url: str, data: dict[str, str]) -> dict[str, Any] | None:
    try:
        import urllib.error
        import urllib.parse
        import urllib.request

        body = urllib.parse.urlencode(data).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": _UA,
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
            raw = response.read().decode("utf-8", errors="replace")
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Driver implementations
# --------------------------------------------------------------------------- #

def _verify_lemonsqueezy(license_key: str, product_hint: str) -> ProviderResult:
    url = "https://api.lemonsqueezy.com/v1/licenses/validate"
    data = {"license_key": license_key}
    if product_hint:
        data["product_id"] = product_hint
    parsed = _post_json(url, data)
    if parsed is None:
        return ProviderResult(False, "lemonsqueezy", "network unavailable", offline=True)
    if parsed.get("valid"):
        meta = parsed.get("meta") or {}
        return ProviderResult(True, "lemonsqueezy", "valid", meta if isinstance(meta, dict) else {})
    return ProviderResult(False, "lemonsqueezy", str(parsed.get("error") or "key not valid"))


def _verify_payhip(license_key: str, product_hint: str) -> ProviderResult:
    url = "https://payhip.com/api/v2/license/verify"
    api_key = os.environ.get("PAYHIP_API_KEY", "").strip()
    data = {"license_key": license_key}
    if api_key:
        data["product_link"] = product_hint or os.environ.get("PAYHIP_PRODUCT_LINK", "").strip()
    parsed = _post_json(url, data)
    if parsed is None:
        return ProviderResult(False, "payhip", "network unavailable", offline=True)
    # Payhip returns {"status": true/false, "data": {...}}
    if parsed.get("status") is True or parsed.get("success") is True or parsed.get("valid") is True:
        data_block = parsed.get("data") or parsed
        return ProviderResult(True, "payhip", "valid", data_block if isinstance(data_block, dict) else {})
    return ProviderResult(False, "payhip", str(parsed.get("message") or parsed.get("error") or "key not valid"))


def _verify_gumroad(license_key: str, product_hint: str) -> ProviderResult:
    url = "https://api.gumroad.com/v2/licenses/verify"
    data = {"license_key": license_key}
    product_id = product_hint or os.environ.get("GUMROAD_PRODUCT_ID", "").strip()
    if product_id:
        data["product_id"] = product_id
    parsed = _post_json(url, data)
    if parsed is None:
        return ProviderResult(False, "gumroad", "network unavailable", offline=True)
    if parsed.get("success"):
        purchase = parsed.get("purchase") or {}
        # Respect Gumroad's refund/chargeback flags.
        if isinstance(purchase, dict) and (purchase.get("refunded") or purchase.get("chargebacked") or purchase.get("disputed")):
            return ProviderResult(False, "gumroad", "purchase was refunded or disputed")
        return ProviderResult(True, "gumroad", "valid", purchase if isinstance(purchase, dict) else {})
    return ProviderResult(False, "gumroad", str(parsed.get("message") or "key not valid"))


def _verify_offline(license_key: str, _product_hint: str) -> ProviderResult:
    """Verify a signed RSA/JWT token using the embedded public key."""
    try:
        from core import license_guard as lg
    except Exception:
        return ProviderResult(False, "offline", "license guard unavailable")

    ok, result = lg.verify_license_token(license_key)
    if ok and isinstance(result, dict):
        return ProviderResult(True, "offline", "valid (signed token)", result, offline=True)
    return ProviderResult(False, "offline", str(result))


PROVIDERS: dict[str, Callable[[str, str], ProviderResult]] = {
    "lemonsqueezy": _verify_lemonsqueezy,
    "payhip": _verify_payhip,
    "gumroad": _verify_gumroad,
    "offline": _verify_offline,
}

_ALIASES = {
    "lemon": "lemonsqueezy",
    "lemon-squeezy": "lemonsqueezy",
    "ls": "lemonsqueezy",
    "payhip.com": "payhip",
    "gum": "gumroad",
    "rsa": "offline",
    "jwt": "offline",
    "offline_token": "offline",
}


def provider_endpoints() -> list[str]:
    return [name for name in PROVIDERS]


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #

def verify_with_provider(
    license_key: str,
    *,
    provider: str | None = None,
    product_hint: str | None = None,
) -> ProviderResult:
    """Verify ``license_key`` with the appropriate vendor driver.

    Order of attempts:
      1. Explicit ``provider`` (or ``LICENSE_PROVIDER``) if given.
      2. Auto-detected provider from the key shape.
      3. The offline RSA token path as a final fallback.

    A positive online result short-circuits the chain. Network failures fall
    through to the offline path so buyers with valid signed keys still activate.
    """
    key = (license_key or "").strip()
    if not key:
        return ProviderResult(False, "offline", "Please enter a license key.")

    hint = (product_hint or "").strip()
    attempted: list[str] = []

    forced = (provider or os.environ.get("LICENSE_PROVIDER") or "").strip().lower()
    order: list[str] = []
    if forced:
        canonical = _ALIASES.get(forced, forced)
        if canonical in PROVIDERS:
            order.append(canonical)
    auto = detect_provider(key)
    if auto not in order:
        order.append(auto)
    if "offline" not in order:
        order.append("offline")

    last: ProviderResult | None = None
    for name in order:
        if name in attempted:
            continue
        attempted.append(name)
        driver = PROVIDERS.get(name)
        if driver is None:
            continue
        result = driver(key, hint)
        if result.ok:
            result.payload.setdefault("provider_attempted", attempted)
            return result
        # Keep the most informative failure (prefer non-network).
        if last is None or (last.offline and not result.offline):
            last = result

    return last or ProviderResult(False, "offline", "could not verify the license key")
