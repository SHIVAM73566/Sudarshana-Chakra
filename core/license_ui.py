"""PyQt6 paywall, trial-expired dialog and trial status banner.

Self-contained so it can be imported by ``main.py`` without touching ``ui.py``.
The palette mirrors ``ui.py``'s ``C`` class so it looks native to the app.
Imports PyQt6 lazily-guarded; on failure the helpers degrade to no-ops.
"""

from __future__ import annotations

from typing import Any

try:
    from PyQt6.QtCore import QTimer, pyqtSignal
    from PyQt6.QtGui import QFont
    from PyQt6.QtWidgets import (
        QDialog,
        QFrame,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )

    _QT_OK = True
except Exception:  # pragma: no cover - only when PyQt6 absent
    _QT_OK = False

from core import license_guard as lg

__all__ = [
    "PaywallDialog",
    "TrialBanner",
    "show_paywall",
    "purchase_url",
    "provider_checkout_links",
]

# Palette (kept in sync with ui.C)
_BG = "rgba(8,10,14,240)"
_PANEL = "rgba(13,15,20,250)"
_BORDER = "rgba(0, 229, 255, 0.35)"
_ACC = "#00e5ff"
_WHITE = "#ffffff"
_TEXT = "#f4f6f8"
_DIM = "#8e949d"


# Known vendor checkout bases. Override any of them via .env so you can point at
# your real product without touching code.
_VENDOR_URL_ENV = {
    "lemonsqueezy": "LEMONSQUEEZY_CHECKOUT_URL",
    "payhip": "PAYHIP_CHECKOUT_URL",
    "gumroad": "GUMROAD_CHECKOUT_URL",
}


def _vendor_urls() -> dict[str, str]:
    import os

    fallback = (
        os.environ.get("SUDARSHANA_PURCHASE_URL")
        or "https://sudarshanachakra.ai/buy"
    )
    urls: dict[str, str] = {}
    for provider, env_name in _VENDOR_URL_ENV.items():
        urls[provider] = (os.environ.get(env_name) or "").strip() or fallback
    return urls


def provider_checkout_links() -> dict[str, str]:
    """Return {provider -> checkout url} for the vendors you have configured."""
    return _vendor_urls()


def purchase_url(discount_code: str = "", percent: int = 0, provider: str | None = None) -> str:
    """Return the checkout URL, appending a vendor-agnostic discount hint."""
    import os

    urls = _vendor_urls()
    base = urls.get((provider or "").strip().lower()) or (
        os.environ.get("SUDARSHANA_PURCHASE_URL")
        or "https://sudarshanachakra.ai/buy"
    )
    sep = "&" if "?" in base else "?"
    query = f"hwid={lg.short_fingerprint()}"
    if discount_code and percent:
        query = f"discount={discount_code}&off={percent}&{query}"
    return f"{base}{sep}{query}"


if _QT_OK:

    class PaywallDialog(QDialog):
        """Native unlock dialog. Emits :attr:`activated` when a key validates."""

        activated = pyqtSignal()

        def __init__(self, type: str = "trial_expired", parent: QWidget | None = None):
            super().__init__(parent)
            self.setWindowTitle("Unlock Sudarshana Chakra")
            self.setMinimumWidth(460)
            self._discount_code = ""
            self._discount_percent = 0
            self._type = type

            self.setStyleSheet(
                f"""
                QDialog {{ background: {_BG}; color: {_WHITE}; border: 1px solid {_BORDER}; }}
                QLabel {{ color: {_TEXT}; }}
                QLineEdit {{
                    background: rgba(16,16,16,240); color: {_WHITE};
                    border: 1px solid {_BORDER}; border-radius: 10px; padding: 9px 11px;
                }}
                QLineEdit:focus {{ border: 1px solid {_ACC}; }}
                QPushButton {{
                    background: rgba(18,18,18,240); color: {_WHITE};
                    border: 1px solid {_BORDER}; border-radius: 10px; padding: 9px 12px;
                }}
                QPushButton:hover {{ background: rgba(28,28,28,245); border: 1px solid {_ACC}; }}
                """
            )

            root = QVBoxLayout(self)
            root.setSpacing(12)
            root.setContentsMargins(20, 20, 20, 20)

            emoji = "⏳" if self._type == "trial_expired" else "🔒"
            title = QLabel(f"{emoji}  {'Trial Expired — Unlock Lifetime Access' if self._type == 'trial_expired' else 'Activation Required'}")
            title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
            title.setStyleSheet(f"color: {_ACC};")
            root.addWidget(title)

            self._countdown = QLabel("")
            self._countdown.setStyleSheet(f"color: {_ACC}; font-family: Consolas; font-size: 12px;")
            root.addWidget(self._countdown)
            self._ticker = QTimer(self)
            self._ticker.setInterval(1000)
            self._ticker.timeout.connect(self._refresh_countdown)
            self._ticker.start()
            self._refresh_countdown()

            blurb = (
                f"Your {lg.trial_days()}-day free trial has ended. Unlock lifetime ownership to keep "
                "using every tool, offline, on this machine - no subscription.\n\n"
                "Limited-time launch offer: use code CHAKRA50 for 50% OFF, or CHAKRA80 for the "
                "best launch-tier discount."
                if self._type == "trial_expired"
                else "This build requires a valid license. Enter your key below to unlock."
            )
            desc = QLabel(blurb)
            desc.setWordWrap(True)
            desc.setStyleSheet(f"color: {_DIM};")
            root.addWidget(desc)

            self._hwid = QLabel(f"Device ID: {lg.short_fingerprint()}  •  provider: {lg.provider_name()}")
            self._hwid.setStyleSheet(f"color: {_DIM}; font-family: Consolas; font-size: 11px;")
            root.addWidget(self._hwid)

            key_lbl = QLabel("License key (from your purchase email)")
            key_lbl.setStyleSheet(f"color: {_TEXT};")
            root.addWidget(key_lbl)
            self._key_edit = QLineEdit()
            self._key_edit.setPlaceholderText("Paste your Lemon Squeezy / Payhip / Gumroad key")
            root.addWidget(self._key_edit)

            row = QHBoxLayout()
            row.setSpacing(8)
            self._discount_edit = QLineEdit()
            self._discount_edit.setPlaceholderText("Discount code (try CHAKRA50 / CHAKRA80)")
            # Pre-fill the launch code on the trial-expired modal and auto-apply it,
            # so the buyer immediately sees the discount reflected in the buttons.
            if self._type == "trial_expired":
                self._discount_edit.setText("CHAKRA50")
            row.addWidget(self._discount_edit, stretch=1)
            self._apply_btn = QPushButton("Apply")
            self._apply_btn.clicked.connect(self._apply_discount)
            row.addWidget(self._apply_btn)
            root.addLayout(row)

            self._status = QLabel("")
            self._status.setWordWrap(True)
            self._status.setStyleSheet(f"color: {_DIM};")
            root.addWidget(self._status)

            buy_lbl = QLabel("Buy lifetime access")
            buy_lbl.setStyleSheet(f"color: {_TEXT};")
            root.addWidget(buy_lbl)

            buy_row = QHBoxLayout()
            buy_row.setSpacing(8)
            self._buy_btns: dict[str, QPushButton] = {}
            for provider, label in (
                ("lemonsqueezy", "Lemon Squeezy"),
                ("payhip", "Payhip"),
                ("gumroad", "Gumroad"),
            ):
                button = QPushButton(label)
                button.clicked.connect(lambda _=False, p=provider: self._on_buy(p))
                buy_row.addWidget(button, stretch=1)
                self._buy_btns[provider] = button
            root.addLayout(buy_row)

            actions = QHBoxLayout()
            actions.setSpacing(8)
            self._activate_btn = QPushButton("Activate License Key")
            self._activate_btn.setStyleSheet(
                f"QPushButton {{ background: rgba(0,229,255,0.22); color: {_WHITE}; "
                f"border: 1px solid {_ACC}; border-radius: 10px; padding: 9px 12px; font-weight: 600; }}"
                f"QPushButton:hover {{ background: rgba(0,229,255,0.40); }}"
            )
            self._activate_btn.clicked.connect(self._on_activate)
            actions.addWidget(self._activate_btn, stretch=1)
            root.addLayout(actions)

            close_row = QHBoxLayout()
            close_row.addStretch(1)
            self._later_btn = QPushButton("Continue with limited mode")
            self._later_btn.clicked.connect(self.reject)
            close_row.addWidget(self._later_btn)
            root.addLayout(close_row)

            # Auto-apply the pre-filled launch discount so pricing is visible at once.
            if self._type == "trial_expired" and self._discount_edit.text().strip():
                self._apply_discount()

        # -- countdown ---------------------------------------------------
        def _refresh_countdown(self) -> None:
            state = lg.evaluate()
            if state.status == lg.LicenseStatus.TRIAL:
                total = max(0, int(state.seconds_left))
                days, rem = divmod(total, 86400)
                hours, rem = divmod(rem, 3600)
                minutes, seconds = divmod(rem, 60)
                self._countdown.setText(
                    f"Trial remaining: {days}d {hours:02d}h {minutes:02d}m {seconds:02d}s"
                )
            elif state.status == lg.LicenseStatus.LICENSED:
                self._countdown.setText("Licensed - lifetime access")
                self._ticker.stop()
            else:
                self._countdown.setText("Trial period ended")

        # -- actions -----------------------------------------------------
        def _apply_discount(self) -> None:
            ok, message, percent = lg.validate_discount_code(self._discount_edit.text())
            self._status.setText(message)
            if ok:
                self._discount_code = self._discount_edit.text().strip().upper()
                self._discount_percent = percent
                for button in self._buy_btns.values():
                    button.setText(f"{button.text().split(' (')[0]} ({percent}% off)")

        def _on_activate(self) -> None:
            self._status.setText("Verifying license key...")
            ok, message = lg.activate(self._key_edit.text())
            self._status.setText(message)
            if ok:
                self._ticker.stop()
                self.activated.emit()
                self.accept()

        def _on_buy(self, provider: str) -> None:
            url = purchase_url(self._discount_code, self._discount_percent, provider)
            try:
                import webbrowser

                webbrowser.open(url)
                self._status.setText(f"Opening {provider} checkout... if nothing happens, visit {url}")
            except Exception:
                self._status.setText(f"Visit {url} to purchase.")

    class TrialBanner(QFrame):
        """Top-of-window banner with a live countdown ticker and urgency styling."""

        unlock_clicked = pyqtSignal()

        def __init__(self, parent: QWidget | None = None):
            super().__init__(parent)
            self.setObjectName("trialBanner")
            self.setFixedHeight(34)
            layout = QHBoxLayout(self)
            layout.setContentsMargins(14, 2, 14, 2)
            layout.setSpacing(10)

            self._label = QLabel("")
            self._label.setStyleSheet(f"color: {_WHITE}; background: transparent;")
            layout.addWidget(self._label, stretch=1)

            self._btn = QPushButton("Unlock")
            self._btn.setStyleSheet(
                f"QPushButton {{ background: rgba(0,229,255,0.20); color: {_ACC}; "
                f"border: 1px solid {_BORDER}; border-radius: 7px; padding: 4px 12px; }}"
                f"QPushButton:hover {{ background: rgba(0,229,255,0.38); color: {_WHITE}; }}"
            )
            self._btn.clicked.connect(self.unlock_clicked.emit)
            layout.addWidget(self._btn)

            self.refresh()
            # Live ticker: update the countdown text every second while in trial.
            self._ticker = QTimer(self)
            self._ticker.setInterval(1000)
            self._ticker.timeout.connect(self._tick)
            self._ticker.start()

        def _tick(self) -> None:
            """Refresh the countdown text; escalate styling in the final day."""
            try:
                state = lg.evaluate()
            except Exception:
                return
            if state.status != lg.LicenseStatus.TRIAL:
                return
            self._render_trial(state)

        def _render_trial(self, state) -> None:
            total = max(0, int(state.seconds_left))
            days, rem = divmod(total, 86400)
            hours, rem = divmod(rem, 3600)
            minutes, seconds = divmod(rem, 60)
            urgent = days < 1
            if urgent:
                self._label.setText(
                    f"TRIAL ENDING: {hours:02d}h {minutes:02d}m {seconds:02d}s left \u2014 "
                    "unlock lifetime access (code CHAKRA50)"
                )
                self.setStyleSheet(
                    "QFrame#trialBanner { background: rgba(255,140,0,0.20); "
                    "border-bottom: 1px solid rgba(255,140,0,0.60); }"
                )
                self._btn.setText("Unlock Now \u2014 50% OFF")
            else:
                self._label.setText(
                    f"Trial \u2014 {days}d {hours:02d}h {minutes:02d}m {seconds:02d}s remaining"
                )
                self.setStyleSheet(
                    "QFrame#trialBanner { background: rgba(0,229,255,0.10); "
                    "border-bottom: 1px solid rgba(0,229,255,0.35); }"
                )
                self._btn.setText("Unlock")

        def refresh(self) -> bool:
            """Update text from the current license state. Returns True if visible."""
            state = lg.evaluate()
            if state.status == lg.LicenseStatus.DISABLED:
                self.setVisible(False)
                return False
            self.setVisible(True)
            if state.status == lg.LicenseStatus.LICENSED:
                self._label.setText("Licensed — lifetime access. Thank you!")
                self._btn.setVisible(False)
                self.setStyleSheet(
                    "QFrame#trialBanner { background: rgba(55,255,95,0.12); "
                    "border-bottom: 1px solid rgba(55,255,95,0.35); }"
                )
            elif state.status == lg.LicenseStatus.TRIAL:
                self._render_trial(state)
                self._btn.setVisible(True)
            else:
                self._label.setText("Trial ended — unlock lifetime access (code CHAKRA50)")
                self._btn.setText("Unlock \u2014 50% OFF")
                self._btn.setVisible(True)
                self.setStyleSheet(
                    "QFrame#trialBanner { background: rgba(255,59,48,0.14); "
                    "border-bottom: 1px solid rgba(255,59,48,0.40); }"
                )
            return True

else:  # pragma: no cover

    class PaywallDialog:  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any):
            raise RuntimeError("PyQt6 is not available")

    class TrialBanner:  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any):
            raise RuntimeError("PyQt6 is not available")


def show_paywall(kind: str = "trial_expired", parent: QWidget | None = None) -> bool:
    """Convenience: show the dialog and return True if the user activated."""
    if not _QT_OK:
        return False
    dialog = PaywallDialog(kind, parent)
    result = dialog.exec()
    return result == QDialog.DialogCode.Accepted
