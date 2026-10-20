"""Tests for the dormant licensing, trial and integrity engine.

All tests run against a temporary user-data directory and toggle the
``LICENSING_ENABLED`` flag explicitly, so they are hermetic and never touch the
developer's real trial state.
"""

import json
import os
import time
from unittest.mock import patch

import pytest

from core import anti_tamper, license_guard as lg
from core import license_providers as lp


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    """Point the license store at a temp dir and reset the fingerprint cache."""
    monkeypatch.setattr(lg, "_data_dir", lambda: tmp_path)
    monkeypatch.setattr(lg, "_FP_CACHE", None, raising=False)
    for key in ("LICENSING_ENABLED", "SUDARSHANA_TRIAL_DAYS", "SUDARSHANA_LICENSE_PUBKEY"):
        monkeypatch.delenv(key, raising=False)
    yield tmp_path


def test_disabled_by_default(isolated_state):
    state = lg.evaluate()
    assert state.status == lg.LicenseStatus.DISABLED
    assert state.allows_core
    assert not state.needs_paywall


def test_trial_starts_and_counts_down(isolated_state, monkeypatch):
    monkeypatch.setenv("LICENSING_ENABLED", "true")
    state = lg.evaluate()
    assert state.status == lg.LicenseStatus.TRIAL
    assert state.days_left == lg.trial_days() - 1
    assert state.allows_core
    assert lg.state_path().is_file()


def test_trial_expires_after_window(isolated_state, monkeypatch):
    monkeypatch.setenv("LICENSING_ENABLED", "true")
    monkeypatch.setenv("SUDARSHANA_TRIAL_DAYS", "8")
    lg.evaluate()  # first run creates the record

    record = json.loads(lg.state_path().read_text(encoding="utf-8"))
    aged = time.time() - (9 * lg.SECONDS_PER_DAY)
    record["payload"]["first_seen"] = aged
    record["payload"]["max_seen"] = time.time()
    record["sig"] = lg._sign(record["payload"])
    lg.state_path().write_text(json.dumps(record), encoding="utf-8")

    state = lg.evaluate()
    assert state.status == lg.LicenseStatus.TRIAL_EXPIRED
    assert not state.allows_core
    assert state.needs_paywall


def test_clock_rollback_is_detected(isolated_state, monkeypatch):
    monkeypatch.setenv("LICENSING_ENABLED", "true")
    lg.evaluate()

    record = json.loads(lg.state_path().read_text(encoding="utf-8"))
    record["payload"]["max_seen"] = time.time() + (3 * lg.SECONDS_PER_DAY)
    record["sig"] = lg._sign(record["payload"])
    lg.state_path().write_text(json.dumps(record), encoding="utf-8")
    monkeypatch.setattr(lg, "_registry_anchor", lambda: None)

    state = lg.evaluate()
    assert state.status == lg.LicenseStatus.TAMPERED
    assert not state.allows_core


def test_tampered_trial_store_is_detected(isolated_state, monkeypatch):
    monkeypatch.setenv("LICENSING_ENABLED", "true")
    lg.evaluate()
    record = json.loads(lg.state_path().read_text(encoding="utf-8"))
    record["payload"]["first_seen"] = 0  # invalidate signature
    lg.state_path().write_text(json.dumps(record), encoding="utf-8")

    state = lg.evaluate()
    assert state.status == lg.LicenseStatus.TAMPERED


def test_fingerprint_is_stable_and_hex(isolated_state):
    first = lg.hardware_fingerprint()
    second = lg.hardware_fingerprint()
    assert first == second
    assert len(first) == 64
    int(first, 16)  # valid hex


def test_token_without_pubkey_fails_closed(isolated_state):
    ok, reason = lg.verify_license_token("a.b.c")
    assert ok is False


def test_malformed_token_rejected(isolated_state):
    ok, reason = lg.verify_license_token("not-a-jwt")
    assert ok is False
    assert "malformed" in reason


def test_discount_codes(isolated_state):
    ok, msg, percent = lg.validate_discount_code("CHAKRA50")
    assert ok and percent == 50
    ok2, _, _ = lg.validate_discount_code("NOPE99")
    assert ok2 is False
    ok3, _, p3 = lg.validate_discount_code("chakra50")  # case-insensitive
    assert ok3 and p3 == 50
    ok4, _, p4 = lg.validate_discount_code("CHAKRA80")
    assert ok4 and p4 == 80


# --------------------------------------------------------------------------- #
# Multi-provider engine
# --------------------------------------------------------------------------- #

def test_provider_detection_by_shape(isolated_state):
    ls_key = "12345678-1234-1234-1234-123456789abc"
    assert lp.detect_provider(ls_key) == "lemonsqueezy"
    jwt_key = "aa.bb.cc"
    assert lp.detect_provider(jwt_key) == "offline"
    assert lp.detect_provider("ABCD-EFGH-IJKL") == "payhip"


def test_provider_env_override(isolated_state, monkeypatch):
    monkeypatch.setenv("LICENSE_PROVIDER", "gumroad")
    assert lp.detect_provider("anything") == "gumroad"
    monkeypatch.setenv("LICENSE_PROVIDER", "rsa")
    assert lp.detect_provider("anything") == "offline"


def test_provider_network_failure_falls_back_to_offline(isolated_state, monkeypatch):
    # No network in tests: driver returns offline=True, then offline path fails
    # closed because no public key is configured.
    result = lp.verify_with_provider("12345678-1234-1234-1234-123456789abc")
    assert result.ok is False
    assert "offline" in result.provider or result.offline


def test_activate_empty_key(isolated_state):
    ok, message = lg.activate("   ")
    assert ok is False


def test_activate_persists_offline_token(isolated_state):
    # Sign a real token with a throwaway RSA key so the offline path succeeds.
    pytest.importorskip("cryptography")
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, rsa
    import base64

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")

    def _b64url(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    header = _b64url(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    payload = _b64url(
        json.dumps({"sub": "buyer@example.com", "hwid": lg.hardware_fingerprint()}).encode()
    )
    signing_input = f"{header}.{payload}".encode("ascii")
    signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    token = f"{header}.{payload}.{_b64url(signature)}"

    os.environ["SUDARSHANA_LICENSE_PUBKEY"] = base64.b64encode(public_pem.encode()).decode()
    os.environ["LICENSING_ENABLED"] = "true"
    try:
        ok, message = lg.activate(token)
        assert ok is True, message
        state = lg.evaluate()
        assert state.status == lg.LicenseStatus.LICENSED
        # Cached activation survives even without the token file.
        lg.license_path().unlink()
        assert lg.evaluate().status == lg.LicenseStatus.LICENSED
    finally:
        os.environ.pop("SUDARSHANA_LICENSE_PUBKEY", None)
        os.environ.pop("LICENSING_ENABLED", None)


def test_anti_tamper_missing_manifest_is_not_enforced(isolated_state, tmp_path):
    with patch.object(anti_tamper, "manifest_path", return_value=tmp_path / "none.json"):
        assert anti_tamper.find_violations() == []
        assert anti_tamper.enforce(release=True) == []


def test_anti_tamper_detects_modification(isolated_state, tmp_path):
    target = tmp_path / "good.py"
    target.write_text("x = 1\n", encoding="utf-8")

    def _sha(path):
        import hashlib

        return hashlib.sha256(path.read_bytes()).hexdigest()

    manifest = {"good.py": _sha(target)}
    with patch.object(anti_tamper, "_ROOT", tmp_path), patch.object(
        anti_tamper, "load_manifest", return_value=manifest
    ):
        assert anti_tamper.find_violations() == []
        target.write_text("x = 2\n", encoding="utf-8")
        violations = anti_tamper.find_violations()
        assert violations and "modified" in violations[0]
        with pytest.raises(anti_tamper.IntegrityError):
            anti_tamper.enforce(release=True)
        # Dev mode only warns.
        assert anti_tamper.enforce(release=False)
