"""Transactional email via Resend (register verify + password reset)."""

from __future__ import annotations

import logging

import httpx

from config import settings

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"


def is_email_delivery_enabled() -> bool:
    return bool(settings.resend_api_key.strip())


def _from_address() -> str:
    return settings.email_from.strip() or "PersonalOps <onboarding@resend.dev>"


async def send_auth_code_email(
    *,
    to_email: str,
    code: str,
    purpose: str,
) -> None:
    if purpose == "register_verify":
        subject = "Your PersonalOps verification code"
        heading = "Verify your email"
        body = (
            "Enter this code in PersonalOps to finish creating your account. "
            "It expires in 15 minutes."
        )
    else:
        subject = "Your PersonalOps password reset code"
        heading = "Reset your password"
        body = (
            "Enter this code in PersonalOps to set a new password. "
            "It expires in 15 minutes."
        )

    html = f"""<!DOCTYPE html>
<html><body style="font-family:system-ui,sans-serif;line-height:1.5;color:#18181b;">
  <h2 style="margin-bottom:8px;">{heading}</h2>
  <p style="margin-top:0;">{body}</p>
  <p style="font-size:28px;font-weight:700;letter-spacing:0.2em;margin:24px 0;">{code}</p>
  <p style="color:#71717a;font-size:14px;">If you did not request this, you can ignore this email.</p>
</body></html>"""

    api_key = settings.resend_api_key.strip()
    if not api_key:
        logger.warning(
            "RESEND_API_KEY not set; skipping email to %s (purpose=%s)",
            to_email,
            purpose,
        )
        return

    payload = {
        "from": _from_address(),
        "to": [to_email],
        "subject": subject,
        "html": html,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(RESEND_API_URL, json=payload, headers=headers)
        if response.status_code >= 400:
            logger.error(
                "Resend API error %s: %s",
                response.status_code,
                response.text[:500],
            )
            raise RuntimeError("Failed to send email")
