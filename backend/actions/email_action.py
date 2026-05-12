"""Email-style Power Automate webhook delivery.

Despite the file name, ``send_email`` does not talk to an SMTP server —
it posts ``{to, subject, body}`` to the appropriate Power Automate flow,
which then sends the actual email. Historically every payload was sent
to ``POWER_ASSET_URL``, which silently dropped HR / IT messages on the
floor whenever the asset flow was the only one configured.

This module now routes per-channel:
    channel="hr"    -> POWER_HR_URL
    channel="it"    -> POWER_IT_URL
    channel="asset" -> POWER_ASSET_URL

If an unknown channel is passed we fall back to ``"hr"`` so callers
upgrading from the old single-arg signature keep working.
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

POWER_HR_URL = (os.getenv("POWER_HR_URL") or "").strip()
POWER_IT_URL = (os.getenv("POWER_IT_URL") or "").strip()
POWER_ASSET_URL = (os.getenv("POWER_ASSET_URL") or "").strip()

_CHANNEL_URLS = {
    "hr": POWER_HR_URL,
    "it": POWER_IT_URL,
    "asset": POWER_ASSET_URL,
}

_VALID_CHANNELS = set(_CHANNEL_URLS.keys())


def _resolve_channel(channel: str | None) -> tuple[str, str]:
    """Return (normalized_channel, target_url). Falls back to ``hr``."""
    ch = (channel or "hr").strip().lower()
    if ch not in _VALID_CHANNELS:
        print(f"[email_action] unknown channel '{channel}', falling back to 'hr'")
        ch = "hr"
    return ch, _CHANNEL_URLS.get(ch, "")


def send_email(to: str, subject: str, body: str, channel: str = "hr") -> bool:
    """Send an email-style notification through the channel's Power
    Automate webhook.

    Args:
        to: recipient email address.
        subject: email subject line.
        body: plain-text body.
        channel: one of ``"hr" | "it" | "asset"``. Defaults to ``"hr"``.
            Unknown values fall back to ``"hr"``.

    Returns:
        ``True`` if the webhook accepted the request (HTTP 200/202),
        ``False`` otherwise. Never raises.
    """
    ch, url = _resolve_channel(channel)

    if not url:
        env_var = f"POWER_{ch.upper()}_URL"
        print(f"[email_action] {env_var} not configured; skipping {ch} email to {to}")
        return False

    payload = {
        "to": to,
        "subject": subject,
        "body": body,
        "channel": ch,
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        print(
            f"[email_action] {ch} email -> {to} | "
            f"status={response.status_code}"
        )
        return response.status_code in (200, 202)

    except Exception as e:
        print(f"[email_action] {ch} email error: {e}")
        return False