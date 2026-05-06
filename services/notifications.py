# -*- coding: utf-8 -*-
"""
Notification service for FORMYLA.
Sends messages via Telegram bot and email (Yandex SMTP).
"""
import os
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)

TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "")
SMTP_SERVER = "smtp.yandex.ru"
SMTP_PORT = 587
SMTP_USER = os.environ.get("MAIL_USERNAME", "kr1venkovictor@yandex.ru")
SMTP_PASS = os.environ.get("MAIL_PASSWORD", "")


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
    """Send an email via Yandex SMTP (port 587 TLS).

    Returns True on success, False on failure.
    """
    if not SMTP_PASS or not to_email:
        logger.debug("Email send skipped: no password or recipient")
        return False

    msg = MIMEMultipart("alternative")
    msg["From"] = SMTP_USER
    msg["To"] = to_email
    msg["Subject"] = subject

    msg.attach(MIMEText(body, "plain", "utf-8"))
    if html:
        msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=10) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, [to_email], msg.as_string())
        return True
    except Exception as exc:
        logger.error("Email send error: %s", exc)
        return False
