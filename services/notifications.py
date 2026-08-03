# -*- coding: utf-8 -*-
"""
Notification service for FORMYLA.
Sends messages via Telegram bot and email (Resend).

Email delivery went through several providers (Gmail -> Yandex -> Resend).
The current implementation prefers Resend HTTP API (see utils/mail.py)
because Gmail App Passwords got revoked (SMTPAuthenticationError 535)
and SMTP_SSL on port 465 hits a Python 3.13+ Windows bug.
SMTP via Resend (smtp.resend.com:465 SSL) is kept as a transparent fallback.
"""
import os
import logging

logger = logging.getLogger(__name__)

TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "")


def send_telegram(chat_id, text):
    """Send a message via Telegram Bot API.

    Returns True on success, False on failure.
    """
    if not TG_BOT_TOKEN or not chat_id:
        logger.debug("TG send skipped: no token or chat_id")
        return False

    import requests
    url = "https://api.telegram.org/bot" + TG_BOT_TOKEN + "/sendMessage"
    payload = dict(
        chat_id=chat_id,
        text=text,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    try:
        r = requests.post(url, json=payload, timeout=5)
        if not r.ok:
            logger.warning("TG send failed: %s %s", r.status_code, r.text[:200])
        return r.ok
    except Exception as exc:
        logger.error("TG send error: %s", exc)
        return False


def send_email(to_email, subject, body, html=None):
    """Send an email via Resend.

    Order of preference:
      1. Resend HTTP API (utils.mail.send_email) — works on any platform,
         no SMTP plumbing required.
      2. SMTP fallback via smtp.resend.com:465 (implicit TLS) using the
         standard MAIL_* env vars.

    Returns True on success, False on failure (never raises).
    """
    if not to_email:
        logger.debug("Email send skipped: empty recipient")
        return False

    # ── 1) HTTP API ──────────────────────────────────────────────────
    try:
        from utils.mail import send_email as resend_send, is_configured
        if is_configured():
            resend_send(
                to_email,
                subject,
                html or body or "",
                text=body if html else None,
            )
            return True
    except Exception as exc:
        logger.error("Resend HTTP send failed, falling back to SMTP: %s", exc)

    # ── 2) SMTP fallback ─────────────────────────────────────────────
    import smtplib
    import ssl
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    smtp_host = os.environ.get("MAIL_SERVER", "smtp.resend.com")
    smtp_port = int(os.environ.get("MAIL_PORT", "465"))
    smtp_user = os.environ.get("MAIL_USERNAME", "resend")
    smtp_pass = os.environ.get("MAIL_PASSWORD", "") or os.environ.get("RESEND_API_KEY", "")
    sender = (
        os.environ.get("MAIL_DEFAULT_SENDER")
        or "onboarding@resend.dev"
    )
    use_ssl = os.environ.get("MAIL_USE_SSL", "True").lower() in ("true", "1", "t", "yes")

    if not smtp_pass:
        logger.debug("Email send skipped: no SMTP password / RESEND_API_KEY")
        return False

    msg = MIMEMultipart("alternative")
    msg["From"] = sender
    msg["To"] = to_email
    msg["Subject"] = subject

    msg.attach(MIMEText(body, "plain", "utf-8"))
    if html:
        msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        if use_ssl and smtp_port == 465:
            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=10, context=ctx) as server:
                server.login(smtp_user, smtp_pass)
                server.sendmail(sender, [to_email], msg.as_string())
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(smtp_user, smtp_pass)
                server.sendmail(sender, [to_email], msg.as_string())
        return True
    except Exception as exc:
        logger.error("Email SMTP send error: %s", exc)
        return False
