import importlib

import pytest


@pytest.fixture()
def vs(tmp_path, monkeypatch):
    from core import voice_security

    importlib.reload(voice_security)
    voice_security._AUTHORIZED_UNTIL = 0.0
    monkeypatch.setattr(voice_security, "get_user_data_dir", lambda: tmp_path)
    return voice_security


def test_disabled_by_default(vs):
    assert vs.is_enabled() is False
    assert vs.is_locked() is False
    handled, allowed, msg = vs.gate_text("open youtube", source="mic")
    assert (handled, allowed, msg) == (False, True, None)


def test_register_phrase_enables_lock(vs):
    handled, allowed, msg = vs.gate_text("register voice password open sesame", source="mic")
    assert handled is True and allowed is False
    assert "enrolled" in msg.lower()
    assert vs.is_locked() is True


def test_voice_denied_without_password(vs):
    vs.register_phrase("open sesame")
    vs.set_enabled(True)
    handled, allowed, msg = vs.gate_text("launch the browser", source="mic")
    assert handled is True and allowed is False
    assert msg == vs.AUTH_DENIED_MESSAGE


def test_voice_allowed_after_password(vs):
    vs.register_phrase("open sesame")
    vs.set_enabled(True)
    vs.gate_text("voice password is open sesame", source="mic")
    handled, allowed, msg = vs.gate_text("launch the browser", source="mic")
    assert (handled, allowed, msg) == (False, True, None)


def test_text_fallback_not_gated(vs):
    vs.register_phrase("open sesame")
    vs.set_enabled(True)
    handled, allowed, msg = vs.gate_text("launch the browser", source="local")
    assert (handled, allowed, msg) == (False, True, None)


def test_forget_disables_lock(vs):
    vs.register_phrase("open sesame")
    vs.gate_text("forget voice password", source="local")
    assert vs.is_enabled() is False
    assert vs.has_passphrase() is False