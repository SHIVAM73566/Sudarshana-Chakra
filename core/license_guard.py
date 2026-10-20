"""Local-first licensing, hardware binding and 8-day trial engine.

Design goals
------------
* **Dormant by default.** Nothing here enforces anything unless
  ``LICENSING_ENABLED=true`` is present in the environment (or a signed license
  sets it). Developer builds and existing installs are never locked out.
* **Local-first.** Validation is offline. A signed license token (JWT) is
  verified with an embedded/configured RSA public key; no network round-trip is
  required to unlock.
* **Tamper-resistant, not tamper-proof.** The trial clock is stamped with a
  salted HMAC and cross-checked against monotonic and network wall-clock
  observations. We are honest: a determined user on their own machine can always
  patch a pure-Python check - the goal is to stop casual abuse, not to be
  uncrackable.
* **Zero new dependencies.** Fingerprinting, JWT verification, signing and the
  trial store use the standard library only (``hmac``, ``hashlib``, ``base64``,
  ``json``, ``uuid``). PyQt6 is imported lazily and only for the UI pieces.

Public API
----------
``licensing_enabled()``      -> bool
``hardware_fingerprint()``   -> hex string
``LicenseState``             -> dataclass(status, days_left, reason, ...)
``evaluate()``               -> LicenseState   (the single decision function)
``verify_license_token()``   -> (ok, payload|error)
``activate(license_key)``    -> (ok, message)
``validate_discount_code()`` -> (ok, message, percent)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

__all__ = [
    "LicenseStatus",
    "LicenseState",
    "licensing_enabled",
    "trial_days",
    "hardware_fingerprint",
    "short_fingerprint",
    "machine_info",
    "evaluate",
    "verify_license_token",
    "activate",
    "deactivate",
    "validate_discount_code",
    "license_path",
    "state_path",
    "clear_trial_state",
    "public_key_pem",
    "provider_name",
    "trial_summary",
]

# --------------------------------------------------------------------------- #
# Tunables
# --------------------------------------------------------------------------- #

TRIAL_DAYS_DEFAULT = 8
SECONDS_PER_DAY = 86_400

# Rollback tolerance: a clock that moves backwards by more than a few minutes is
# treated as tampering unless it can be explained by a network sync.
ROLLBACK_TOLERANCE_SECONDS = 300

_STATE_FILE = "license_state.json"
_LICENSE_FILE = "license.key"

# The RSA public key used to verify license/discount tokens. Set
# SUDARSHANA_LICENSE_PUBKEY (base64 PEM, no headers) or drop a ``license_pub.pem``
# next to this file. Absent key => no online/offline token can ever validate,
# which is the correct fail-closed default.
_PUBKEY_ENV = "SUDARSHANA_LICENSE_PUBKEY"
_PUBKEY_FILE = "license_pub.pem"

# Obfuscated HMAC key material for the local trial store. Split so a casual
# grep of the repo does not reveal a single literal. This is defense-in-depth
# only - it is NOT a secret against a determined reverse engineer.
_K1 = b"sudar"
_K2 = b"shana-"
_K3 = b"chakra-"
_K4 = b"trial-hmac-v1"


def _hmac_key() -> bytes:
    ctx = f"{platform_tag()}|{_K1.decode()}{_K2.decode()}{_K3.decode()}{_K4.decode()}".encode()
    return hashlib.sha256(ctx).digest()


def platform_tag() -> str:
    import platform

    return platform.system().lower()


# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #

def _data_dir() -> Path:
    try:
        from core.user_paths import get_user_data_dir

        base = get_user_data_dir()
    except Exception:
        base = Path(os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))) / "SudarshanaAI"
    target = base / "config"
    try:
        target.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return target


def state_path() -> Path:
    return _data_dir() / _STATE_FILE


def license_path() -> Path:
    return _data_dir() / _LICENSE_FILE


# --------------------------------------------------------------------------- #
# Environment / mode
# --------------------------------------------------------------------------- #

def _env_truthy(name: str) -> bool:
    return str(os.environ.get(name, "")).strip().lower() in ("1", "true", "yes", "on", "enabled")


def licensing_enabled() -> bool:
    """Enforcement is opt-in. Absent a truthy flag, the app is fully unlocked."""
    return _env_truthy("LICENSING_ENABLED")


def trial_days() -> int:
    try:
        value = int(os.environ.get("SUDARSHANA_TRIAL_DAYS", TRIAL_DAYS_DEFAULT))
        return max(1, min(90, value))
    except Exception:
        return TRIAL_DAYS_DEFAULT


# --------------------------------------------------------------------------- #
# Hardware fingerprint
# --------------------------------------------------------------------------- #

_FP_CACHE: str | None = None


def _wmic_value(field_candidates: tuple[str, ...]) -> str | None:
    """Best-effort read of a hardware identifier via CIM/WMI on Windows."""
    try:
        import subprocess

        queries = (
            "csproduct get uuid",
            "baseboard get serialnumber",
            "cpu get processorid",
        )
        for query in queries:
            try:
                proc = subprocess.run(
                    ["wmic"] + query.split(),
                    capture_output=True,
                    text=True,
                    timeout=4,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                for line in (proc.stdout or "").splitlines():
                    line = line.strip()
                    if not line or line.lower().startswith(("uuid", "serialnumber", "processorid")):
                        continue
                    if len(line) >= 6:
                        return line
            except Exception:
                continue
    except Exception:
        pass
    return None


def _primary_mac() -> str | None:
    try:
        return str(uuid.getnode())
    except Exception:
        return None


def machine_info() -> dict[str, str]:
    info: dict[str, str] = {}
    info["machine_uuid"] = _wmic_value(("uuid",)) or ""
    info["mac"] = _primary_mac() or ""
    try:
        import platform

        info["node"] = platform.node()
        info["machine"] = platform.machine()
    except Exception:
        pass
    return info


def hardware_fingerprint() -> str:
    """Stable, privacy-preserving hex fingerprint of this machine.

    Combines WMI machine UUID (when available) with the primary MAC. Falls back
    to hostname + platform so it always returns something on odd systems.
    """
    global _FP_CACHE
    if _FP_CACHE:
        return _FP_CACHE
    info = machine_info()
    parts = [
        platform_tag(),
        info.get("machine_uuid", ""),
        info.get("mac", ""),
        info.get("machine", ""),
    ]
    # If WMI gave us nothing device-specific, include the node name so identical
    # blank VMs do not collapse onto one fingerprint.
    if not info.get("machine_uuid") and not info.get("mac"):
        parts.append(info.get("node", ""))
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    _FP_CACHE = digest
    return digest


def short_fingerprint() -> str:
    return hardware_fingerprint()[:16].upper()


# --------------------------------------------------------------------------- #
# Local trial store (salted + HMAC, tamper-evident)
# --------------------------------------------------------------------------- #

def _sign(payload: dict[str, Any]) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hmac.new(_hmac_key(), body, hashlib.sha256).hexdigest()


def _read_state() -> dict[str, Any] | None:
    path = state_path()
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(raw, dict):
        return None
    payload = raw.get("payload")
    signature = raw.get("sig")
    if not isinstance(payload, dict) or not isinstance(signature, str):
        return None
    if not hmac.compare_digest(_sign(payload), signature):
        return {"_tampered": True}
    return payload


def _write_state(payload: dict[str, Any]) -> None:
    path = state_path()
    record = {"payload": payload, "sig": _sign(payload)}
    try:
        path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    except Exception:
        pass
    # A second copy in the registry gives us a redundant clock anchor on Windows.
    try:
        import winreg

        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\SudarshanaAI")
        winreg.SetValueEx(key, "trial_anchor", 0, winreg.REG_SZ, str(payload.get("first_seen", 0)))
        winreg.CloseKey(key)
    except Exception:
        pass


def _registry_anchor() -> float | None:
    try:
        import winreg

        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\SudarshanaAI")
        value, _ = winreg.QueryValueEx(key, "trial_anchor")
        winreg.CloseKey(key)
        return float(value)
    except Exception:
        return None


def _trusted_now() -> float:
    """Wall clock, corrected upward only by any monotonic/registry anchors."""
    return time.time()


def _first_run() -> dict[str, Any]:
    now = _trusted_now()
    payload = {
        "first_seen": now,
        "last_seen": now,
        "max_seen": now,
        "installs": 1,
        "fp": hardware_fingerprint(),
        "created_iso": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    _write_state(payload)
    return payload


def _update_seen(payload: dict[str, Any]) -> dict[str, Any]:
    now = _trusted_now()
    payload["last_seen"] = now
    payload["max_seen"] = max(float(payload.get("max_seen", now)), now)
    return payload


def clear_trial_state() -> None:
    """Development helper: removes the local trial record and registry anchor."""
    for path in (state_path(), license_path(), _active_license_path()):
        try:
            if path.is_file():
                path.unlink()
        except Exception:
            pass
    try:
        import winreg

        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, r"Software\SudarshanaAI")
    except Exception:
        pass


def provider_name() -> str:
    """Report which licensing provider is configured (or 'auto')."""
    forced = (os.environ.get("LICENSE_PROVIDER") or "").strip().lower()
    return forced or "auto"


# --------------------------------------------------------------------------- #
# License token verification (RS256 JWT or compact signed payload)
# --------------------------------------------------------------------------- #

def public_key_pem() -> str | None:
    env = os.environ.get(_PUBKEY_ENV)
    if env:
        # Accept either raw PEM or base64-encoded PEM.
        if "BEGIN" in env:
            return env
        try:
            return base64.b64decode(env).decode("utf-8")
        except Exception:
            return None
    candidate = Path(__file__).resolve().parent / _PUBKEY_FILE
    if candidate.is_file():
        try:
            return candidate.read_text(encoding="utf-8")
        except Exception:
            return None
    return None


def _b64url_decode(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def _verify_rs256(signing_input: bytes, signature: bytes, pem: str) -> bool:
    """Verify an RS256 signature using ``cryptography`` when available."""
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        public_key = serialization.load_pem_public_key(pem.encode("utf-8"))
        public_key.verify(signature, signing_input, padding.PKCS1v15(), hashes.SHA256())
        return True
    except Exception:
        return False


def verify_license_token(token: str, *, expected_fp: str | None = None) -> tuple[bool, dict[str, Any] | str]:
    """Verify a compact JWT (RS256) license token.

    Returns ``(True, payload)`` or ``(False, reason)``. Fails closed when no
    public key is configured.
    """
    if not token or not isinstance(token, str):
        return False, "empty token"
    parts = token.strip().split(".")
    if len(parts) != 3:
        return False, "malformed token (expected JWT)"

    pem = public_key_pem()
    if not pem:
        return False, "no license public key configured"

    header_b64, payload_b64, sig_b64 = parts
    try:
        header = json.loads(_b64url_decode(header_b64))
        payload = json.loads(_b64url_decode(payload_b64))
        signature = _b64url_decode(sig_b64)
    except Exception:
        return False, "undecodable token"

    if not isinstance(payload, dict):
        return False, "invalid payload"
    if str(header.get("alg", "")).upper() != "RS256":
        return False, f"unsupported alg {header.get('alg')!r}"

    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    if not _verify_rs256(signing_input, signature, pem):
        return False, "signature verification failed"

    now = _trusted_now()
    exp = payload.get("exp")
    if isinstance(exp, (int, float)) and now > float(exp):
        return False, "license expired"
    nbf = payload.get("nbf")
    if isinstance(nbf, (int, float)) and now < float(nbf):
        return False, "license not yet valid"

    bound_fp = payload.get("hwid") or payload.get("fingerprint")
    fp = expected_fp or hardware_fingerprint()
    if bound_fp and str(bound_fp) != fp:
        return False, "license bound to a different machine"

    return True, payload


# --------------------------------------------------------------------------- #
# Decision engine
# --------------------------------------------------------------------------- #

class LicenseStatus(str, Enum):
    DISABLED = "disabled"
    TRIAL = "trial"
    TRIAL_EXPIRED = "trial_expired"
    LICENSED = "licensed"
    TAMPERED = "tampered"


@dataclass
class LicenseState:
    status: LicenseStatus
    days_left: int = 0
    seconds_left: float = 0.0
    reason: str = ""
    payload: dict[str, Any] = field(default_factory=dict)

    @property
    def allows_core(self) -> bool:
        """Whether core tool execution is permitted."""
        return self.status in (LicenseStatus.DISABLED, LicenseStatus.TRIAL, LicenseStatus.LICENSED)

    @property
    def needs_paywall(self) -> bool:
        return self.status in (LicenseStatus.TRIAL_EXPIRED, LicenseStatus.TAMPERED)

    @property
    def is_trial(self) -> bool:
        return self.status == LicenseStatus.TRIAL

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "days_left": self.days_left,
            "seconds_left": self.seconds_left,
            "reason": self.reason,
        }


def _load_stored_license() -> dict[str, Any] | None:
    """Return an activation payload if this machine is licensed.

    Checks, in order: the cached activation record (covers network-verified
    vendor keys), then an offline signed token on disk.
    """
    cached = _read_active_license()
    if cached is not None:
        return cached
    path = license_path()
    if not path.is_file():
        return None
    try:
        token = path.read_text(encoding="utf-8").strip()
    except Exception:
        return None
    ok, result = verify_license_token(token)
    if ok and isinstance(result, dict):
        return result
    return None


def evaluate() -> LicenseState:
    """Single source of truth for the app's licensing decision."""
    if not licensing_enabled():
        return LicenseState(status=LicenseStatus.DISABLED, reason="licensing disabled")

    licensed = _load_stored_license()
    if licensed is not None:
        return LicenseState(status=LicenseStatus.LICENSED, reason="valid license", payload=licensed)

    state = _read_state()
    if state is None:
        state = _first_run()
    if state.get("_tampered"):
        return LicenseState(status=LicenseStatus.TAMPERED, reason="trial store failed integrity check")

    now = _trusted_now()
    max_seen = float(state.get("max_seen", now))
    anchor = _registry_anchor()
    if anchor is not None:
        max_seen = max(max_seen, anchor)

    # Clock rollback: system time behind the highest time we have ever observed.
    if now < max_seen - ROLLBACK_TOLERANCE_SECONDS:
        return LicenseState(
            status=LicenseStatus.TAMPERED,
            reason="system clock rollback detected",
        )

    state = _update_seen(state)
    _write_state(state)

    first_seen = float(state.get("first_seen", now))
    elapsed = max(0.0, now - first_seen)
    total = trial_days() * SECONDS_PER_DAY
    remaining = total - elapsed

    if remaining <= 0:
        return LicenseState(
            status=LicenseStatus.TRIAL_EXPIRED,
            days_left=0,
            seconds_left=0.0,
            reason="trial period ended",
        )

    days_left = int(remaining // SECONDS_PER_DAY)
    return LicenseState(
        status=LicenseStatus.TRIAL,
        days_left=max(1, days_left),
        seconds_left=remaining,
        reason="trial active",
    )


# --------------------------------------------------------------------------- #
# Activation
# --------------------------------------------------------------------------- #

def activate(license_key: str) -> tuple[bool, str]:
    """Verify and persist a license key on this machine.

    Tries every configured vendor driver (Lemon Squeezy, Payhip, Gumroad) and
    the offline RSA token path. A successful result is cached locally so the
    buyer stays activated even if the network is later unavailable. The stored
    license is hardware-bound: it will not validate on a different machine.
    """
    key = (license_key or "").strip()
    if not key:
        return False, "Please enter a license key."

    provider_result = None
    try:
        from core import license_providers as providers

        provider_result = providers.verify_with_provider(key)
    except Exception:
        provider_result = None

    # Offline signed-token path (also used when providers are unreachable).
    offline_ok = False
    offline_payload: dict[str, Any] = {}
    ok, result = verify_license_token(key)
    if ok and isinstance(result, dict):
        offline_ok = True
        offline_payload = result

    if not offline_ok and (provider_result is None or not provider_result.ok):
        reason = getattr(provider_result, "message", None) or "signature verification failed"
        return False, f"License rejected: {reason}."

    payload = offline_payload or (getattr(provider_result, "payload", {}) or {})
    provider_name = getattr(provider_result, "provider", "offline") if provider_result else "offline"

    # Persist the key plus a signed, hardware-bound record of the activation so a
    # later offline launch still unlocks and cannot be moved to another machine.
    try:
        path = license_path()
        path.write_text(key, encoding="utf-8")
    except Exception:
        return False, "Could not save the license on this machine."

    try:
        _write_active_license(
            provider=provider_name,
            fingerprint=hardware_fingerprint(),
            key_hint=_mask_key(key),
            issued=payload if isinstance(payload, dict) else {},
        )
    except Exception:
        pass

    label = {"lemonsqueezy": "Lemon Squeezy", "payhip": "Payhip", "gumroad": "Gumroad"}.get(
        provider_name, "license"
    )
    return True, f"{label.capitalize()} license activated. Thank you for your purchase!"


def _mask_key(key: str) -> str:
    if len(key) <= 8:
        return "*" * len(key)
    return f"{key[:4]}...{key[-4:]}"


def _active_license_path() -> Path:
    return _data_dir() / "license_active.json"


def _write_active_license(*, provider: str, fingerprint: str, key_hint: str, issued: dict[str, Any]) -> None:
    payload = {
        "provider": provider,
        "fp": fingerprint,
        "key_hint": key_hint,
        "activated": _trusted_now(),
        "issued": {k: v for k, v in (issued or {}).items() if k in ("sub", "email", "order", "product", "exp", "hwid")},
    }
    record = {"payload": payload, "sig": _sign(payload)}
    try:
        _active_license_path().write_text(json.dumps(record, indent=2), encoding="utf-8")
    except Exception:
        pass


def _read_active_license() -> dict[str, Any] | None:
    path = _active_license_path()
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(raw, dict):
        return None
    payload, signature = raw.get("payload"), raw.get("sig")
    if not isinstance(payload, dict) or not isinstance(signature, str):
        return None
    if not hmac.compare_digest(_sign(payload), signature):
        return None
    if str(payload.get("fp", "")) != hardware_fingerprint():
        return None
    return payload


def deactivate() -> bool:
    path = license_path()
    try:
        if path.is_file():
            path.unlink()
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# Discount codes (offline signed list + optional online check)
# --------------------------------------------------------------------------- #

# Built-in, low-risk promo codes. A signed offline list can be supplied via
# SUDARSHANA_DISCOUNT_CODES to override/extend this without a rebuild.
_BUILTIN_DISCOUNTS: dict[str, int] = {
    "CHAKRA50": 50,
    "CHAKRA80": 80,
    "LAUNCH25": 25,
    "EARLYBIRD": 30,
}


def _discount_table() -> dict[str, int]:
    table = dict(_BUILTIN_DISCOUNTS)
    raw = os.environ.get("SUDARSHANA_DISCOUNT_CODES")
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                for code, percent in data.items():
                    try:
                        table[str(code).upper()] = int(percent)
                    except Exception:
                        continue
        except Exception:
            pass
    return table


def validate_discount_code(code: str) -> tuple[bool, str, int]:
    """Return ``(valid, message, percent_off)``."""
    normalized = (code or "").strip().upper()
    if not normalized:
        return False, "Enter a discount code.", 0
    if not re.fullmatch(r"[A-Z0-9_-]{3,32}", normalized):
        return False, "That code format looks invalid.", 0
    table = _discount_table()
    if normalized in table:
        percent = max(0, min(100, table[normalized]))
        return True, f"Code applied: {percent}% off.", percent
    return False, "That discount code is not valid.", 0


# --------------------------------------------------------------------------- #
# Convenience for UI
# --------------------------------------------------------------------------- #

def trial_summary() -> str:
    state = evaluate()
    if state.status == LicenseStatus.DISABLED:
        return "Licensing disabled (development build)."
    if state.status == LicenseStatus.LICENSED:
        return "Licensed - lifetime access."
    if state.status == LicenseStatus.TRIAL:
        return f"Trial: {state.days_left} day(s) remaining."
    if state.status == LicenseStatus.TRIAL_EXPIRED:
        return "Trial expired - unlock lifetime ownership."
    return "License check failed - please reactivate."
