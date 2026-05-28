# -*- coding: utf-8 -*-
"""Email sending helper built on top of Resend HTTP API.

Why HTTP API instead of SMTP:
- No SMTP credentials/App-Password games (we're explicitly migrating off Gmail).
- One outbound HTTPS call -> works through every Render/PaaS firewall.
- Identical behaviour on Windows (Python 3.13/3.14 stdlib SMTP_SSL bug on Windows
  is what bit us when we tried smtplib.SMTP_SSL(465) earlier).

The module exposes a single function ``send_email`` that all application code
should use. It is intentionally tolerant: if ``RESEND_API_KEY`` is missing it
raises ``RuntimeError`` immediately so the caller can log/fallback — never
silently drops mail.

Env vars consumed:
    RESEND_API_KEY        — required, format ``re_xxxxxxxxxxxxx``
    MAIL_DEFAULT_SENDER   — From address, e.g. ``noreply@formyla.com``.
                            Fallback: ``onboarding@resend.dev`` (Resend's
                            shared sandbox sender, works without DNS setup).
    RESEND_TIMEOUT        — optional, HTTP timeout in seconds (default 10).
"""
from __future__ import annotations

import logging
import os
from typing import Iterable, Optional, Union

import requests

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"
DEFAULT_FROM_FALLBACK = "onboarding@resend.dev"


def _get_api_key() -> str:
    key = os.environ.get("RESEND_API_KEY") or ""
    if not key:
        # Allow MAIL_PASSWORD to double as the API key for backwards
        # compatibility with the Flask-Mail Variant A configuration
        # (MAIL_PASSWORD=<re_xxx> in Render Environment).
        mp = os.environ.get("MAIL_PASSWORD") or ""
        if mp.startswith("re_"):
            key = mp
    if not key:
        raise RuntimeError(
            "RESEND_API_KEY is not set in environment. "
            "Add it in Render → Environment (format: re_xxxxxxxxxxxxx)."
        )
    return key


def _get_default_sender() -> str:
    sender = (
        os.environ.get("MAIL_DEFAULT_SENDER")
        or os.environ.get("RESEND_FROM")
        or DEFAULT_FROM_FALLBACK
    )
    # Resend rejects ``resend`` (the SMTP username) as a From address.
    if sender == "resend":
        sender = DEFAULT_FROM_FALLBACK
    # Add a friendly display name unless the sender already has one.
    # Format must be: "Name <email@domain>" (RFC 5322). Resend accepts both
    # bare emails and Name+address, but a display name gives slightly better
    # deliverability with Gmail (less likely to land in Promotions/Spam).
    if "<" not in sender and "@" in sender:
        sender = "FORMYLA <" + sender + ">"
    return sender


def _log_verification_code_for_dev(to_email: str, subject: str, html: str) -> None:
    """Log the 6-digit verification code to stdout for development visibility.

    Triggered only for auth/verification emails (heuristic on subject).
    Resend's sandbox sender ``onboarding@resend.dev`` is often filtered by
    Gmail; printing the code to Render logs lets us complete login flows
    even when delivery is delayed/blocked.

    NEVER logs the code in production with a verified custom sender —
    enable by checking the sender domain.
    """
    s = (subject or "").lower()
    if not ("код" in s or "verification" in s or "verify" in s):
        return
    import re
    m = re.search(r"\b\d{6}\b", html or "")
    if not m:
        return
    print(
        "[EMAIL DEV] verification code for " + to_email + ": " + m.group(),
        flush=True,
    )


def send_email(
    to: Union[str, Iterable[str]],
    subject: str,
    html: str,
    *,
    text: Optional[str] = None,
    sender: Optional[str] = None,
    reply_to: Optional[str] = None,
    timeout: Optional[float] = None,
) -> dict:
    """Send an email via Resend HTTP API.

    Args:
        to:        recipient address or iterable of addresses.
        subject:   email subject line.
        html:      HTML body. If you only have plain text, pass ``text`` and
                   leave ``html`` empty — Resend accepts text-only.
        text:      optional plain-text alternative.
        sender:    override From address (default: ``MAIL_DEFAULT_SENDER`` env).
        reply_to:  optional Reply-To header.
        timeout:   HTTP timeout in seconds (default: ``RESEND_TIMEOUT`` or 10).

    Returns:
        dict with Resend response (contains ``id`` of the queued email).

    Raises:
        RuntimeError: if ``RESEND_API_KEY`` is not configured.
        requests.HTTPError: on non-2xx response from Resend.
    """
    api_key = _get_api_key()
    from_addr = sender or _get_default_sender()

    if isinstance(to, str):
        recipients = [to]
    else:
        recipients = [r for r in to if r]
    if not recipients:
        raise ValueError("send_email: no recipients provided")

    payload: dict = {
        "from": from_addr,
        "to": recipients,
        "subject": subject,
    }
    if html:
        payload["html"] = html
    if text:
        payload["text"] = text
    if not html and not text:
        # Resend requires at least one of html/text.
        payload["text"] = ""
    if reply_to:
        payload["reply_to"] = reply_to

    if timeout is None:
        try:
            timeout = float(os.environ.get("RESEND_TIMEOUT", "10"))
        except (TypeError, ValueError):
            timeout = 10.0

    headers = {
        "Authorization": "Bearer " + api_key,
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(
            RESEND_API_URL, json=payload, headers=headers, timeout=timeout
        )
    except requests.RequestException as exc:
        logger.error("Resend network error: %s", exc)
        raise

    if resp.status_code >= 400:
        # Log full body — invaluable for diagnosing 403 (domain not verified),
        # 401 (bad API key), 422 (invalid From), rate limits, etc.
        logger.error(
            "Resend API error %s for %s: %s",
            resp.status_code,
            recipients,
            resp.text[:500],
        )
        resp.raise_for_status()

    try:
        body = resp.json()
    except ValueError:
        body = {"raw": resp.text}

    # Belt-and-braces: only the presence of ``id`` proves Resend queued the
    # message. Without it we treat the call as failed even on HTTP 2xx so
    # callers don't see the "everything is fine" branch wrongly.
    if not isinstance(body, dict) or not body.get("id"):
        logger.error(
            "Resend returned 2xx without id for %s; body=%r", recipients, body
        )
        raise RuntimeError(
            "Resend response missing id (delivery not confirmed): " + str(body)[:200]
        )

    # Dev visibility: print 6-digit code from auth emails so we can complete
    # the login flow from Render logs even if Gmail filters the message.
    try:
        _log_verification_code_for_dev(recipients[0], subject, html or "")
    except Exception:
        pass  # never let logging break delivery

    return body


def is_configured() -> bool:
    """True iff Resend can be used (API key is present)."""
    try:
        _get_api_key()
        return True
    except RuntimeError:
        return False
