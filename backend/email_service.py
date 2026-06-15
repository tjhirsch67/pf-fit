"""Email delivery via the Mailtrap Send HTTP API.

HTTP (not SMTP) because Railway blocks outbound SMTP ports — the same lesson learned on the
IMS project. Email is optional in PF Coach (welcome notes, streak nudges); if no Mailtrap
token is configured, ``send_email`` is a no-op that returns ``False`` so callers never crash.
"""

import logging
from typing import Optional

import httpx

from config import settings

logger = logging.getLogger("pf_coach.email")

MAILTRAP_SEND_URL = "https://send.api.mailtrap.io/api/send"


def is_configured() -> bool:
    return bool(settings.mailtrap_api_token)


def send_email(to_email: str, subject: str, html: str, text: Optional[str] = None) -> bool:
    """Send one HTML email. Returns True on success, False if unconfigured or on error."""
    if not is_configured():
        logger.info("Mailtrap not configured; skipping email to %s (%s)", to_email, subject)
        return False

    payload = {
        "from": {"email": settings.from_email, "name": settings.from_name},
        "to": [{"email": to_email}],
        "subject": subject,
        "html": html,
    }
    if text:
        payload["text"] = text

    headers = {
        "Authorization": f"Bearer {settings.mailtrap_api_token}",
        "Content-Type": "application/json",
    }

    try:
        resp = httpx.post(MAILTRAP_SEND_URL, json=payload, headers=headers, timeout=15.0)
        resp.raise_for_status()
        return True
    except httpx.HTTPError as e:
        logger.warning("Mailtrap send failed for %s: %s", to_email, e)
        return False
