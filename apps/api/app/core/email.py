"""Transactional email with graceful degradation.

Sends via SMTP (a Gmail App Password in prod) on a worker thread. If SMTP isn't configured
(``smtp_user`` blank), the message + link is logged instead — so a password-reset flow never
dead-ends, and delivery errors never surface to the requester (which would leak account existence).
"""

from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("email")


def _send_sync(to: str, subject: str, body: str) -> None:
    s = get_settings()
    if not s.smtp_user or not s.smtp_password:
        logger.info("email_not_configured to=%s subject=%s body=%s", to, subject, body)
        return
    msg = EmailMessage()
    msg["From"] = s.email_from or s.smtp_user
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as smtp:
        smtp.starttls()
        smtp.login(s.smtp_user, s.smtp_password)
        smtp.send_message(msg)


async def send_email(to: str, subject: str, body: str) -> None:
    try:
        await asyncio.to_thread(_send_sync, to, subject, body)
        logger.info("email_sent to=%s", to)
    except Exception as exc:
        logger.warning("email_failed: %s", exc)
