# -*- coding: utf-8 -*-
"""
Brevo (formerly Sendinblue) transactional email service.

Sends welcome / password-reset / payment-receipt emails through the Brevo
REST API. Falls back to a no-op (with a logged warning) when BREVO_API_KEY
is not configured, so local development keeps working without a real key.

Environment variables:
    BREVO_API_KEY        — API key from https://app.brevo.com -> SMTP & API
    BREVO_SENDER_EMAIL   — verified sender address (default: no-reply@formyla.com)
    BREVO_SENDER_NAME    — display name (default: FORMYLA)
"""
from __future__ import annotations

import logging
import os
from typing import Optional

log = logging.getLogger(__name__)


def _get_api_client():
    """Lazy import + lazy init of the Brevo SDK client.

    Returns (TransactionalEmailsApi, SendSmtpEmail_cls) on success, or
    (None, None) when either the SDK is missing or BREVO_API_KEY is unset.
    """
    api_key = os.environ.get("BREVO_API_KEY", "").strip()
    if not api_key:
        return None, None
    try:
        import sib_api_v3_sdk
        from sib_api_v3_sdk.rest import ApiException  # noqa: F401 (used by caller)
    except ImportError:
        log.warning("sib-api-v3-sdk is not installed; emails disabled")
        return None, None

    cfg = sib_api_v3_sdk.Configuration()
    cfg.api_key["api-key"] = api_key
    api_client = sib_api_v3_sdk.ApiClient(cfg)
    return (
        sib_api_v3_sdk.TransactionalEmailsApi(api_client),
        sib_api_v3_sdk.SendSmtpEmail,
    )


def _sender_block() -> dict:
    return {
        "email": os.environ.get("BREVO_SENDER_EMAIL", "no-reply@formyla.com"),
        "name": os.environ.get("BREVO_SENDER_NAME", "FORMYLA"),
    }


def send_email(
    to_email: str,
    subject: str,
    html_content: str,
    text_content: Optional[str] = None,
    to_name: Optional[str] = None,
) -> bool:
    """Send a transactional email through Brevo.

    Returns True on success, False on any failure (and logs the reason).
    Never raises — callers can safely fire-and-forget.
    """
    if not to_email:
        log.warning("send_email: empty recipient, skipped")
        return False

    api, SendSmtpEmail = _get_api_client()
    if api is None:
        log.info("send_email: BREVO_API_KEY not set, skipping email to %s", to_email)
        return False

    payload = SendSmtpEmail(
        sender=_sender_block(),
        to=[{"email": to_email, "name": to_name or to_email}],
        subject=subject,
        html_content=html_content,
        text_content=text_content or _strip_html(html_content),
    )

    try:
        api.send_transac_email(payload)
        log.info("Brevo: email sent to %s | subject=%r", to_email, subject)
        return True
    except Exception as exc:  # noqa: BLE001 — Brevo SDK raises ApiException + httpx errors
        log.error("Brevo: failed to send email to %s: %s", to_email, exc)
        # Best-effort: report to Sentry if available
        try:
            import sentry_sdk
            sentry_sdk.capture_exception(exc)
        except Exception:
            pass
        return False


def _strip_html(html: str) -> str:
    """Very small HTML -> text fallback for the text_content field."""
    import re
    text = re.sub(r"<br\s*/?>", "\n", html or "", flags=re.IGNORECASE)
    text = re.sub(r"</p\s*>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


# ─────────────────────────── Pre-built templates ───────────────────────────

def send_welcome_email(user) -> bool:
    """Welcome a new user right after registration.

    `user` is a SQLAlchemy User row with .email and (optionally) .nickname.
    """
    email = getattr(user, "email", None)
    if not email:
        return False
    name = getattr(user, "nickname", None) or getattr(user, "display_name", None) or email.split("@")[0]
    subject = "Добро пожаловать в FORMYLA!"
    html = f"""
    <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;max-width:560px;margin:0 auto;padding:24px;color:#1f2937;">
      <h1 style="color:#7c3aed;margin:0 0 12px;">Привет, {name}!</h1>
      <p>Спасибо, что зарегистрировался в <strong>FORMYLA</strong> — платформе подготовки к математическим олимпиадам.</p>
      <p>Что ты можешь сделать прямо сейчас:</p>
      <ul>
        <li>Решить <a href="https://formyla.com/daily" style="color:#0ea5e9;">сегодняшнюю задачу дня</a> и заработать XP.</li>
        <li>Открыть <a href="https://formyla.com/olympiads/methods" style="color:#0ea5e9;">295 методов ВсОШ-9</a> с разбором.</li>
        <li>Пройти <a href="https://formyla.com/adaptive_test/select_class" style="color:#0ea5e9;">адаптивный тест</a> чтобы получить персональный план.</li>
      </ul>
      <p style="margin-top:24px;">Если что-то непонятно — напиши прямо в форму поддержки на <a href="https://formyla.com/about">странице «О нас»</a>.</p>
      <p style="color:#6b7280;font-size:13px;margin-top:32px;">Это автоматическое письмо, отвечать на него не нужно.</p>
    </div>
    """
    return send_email(email, subject, html, to_name=name)


def send_password_reset(user, reset_link: str) -> bool:
    """Send a password-reset link (auth is passwordless today, so this is
    reserved for future use — e.g. account recovery via Telegram-linked email)."""
    email = getattr(user, "email", None)
    if not email or not reset_link:
        return False
    name = getattr(user, "nickname", None) or email.split("@")[0]
    subject = "FORMYLA: восстановление доступа"
    html = f"""
    <div style="font-family:sans-serif;max-width:560px;margin:0 auto;padding:24px;color:#1f2937;">
      <h2 style="color:#7c3aed;">Восстановление доступа</h2>
      <p>Привет, {name}. По твоему запросу мы выслали ссылку для входа без пароля:</p>
      <p style="text-align:center;margin:24px 0;">
        <a href="{reset_link}" style="display:inline-block;background:#7c3aed;color:#fff;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:600;">Войти в FORMYLA</a>
      </p>
      <p style="color:#6b7280;font-size:13px;">Если ссылку запрашивал не ты — просто проигнорируй это письмо. Ссылка действует 30 минут.</p>
    </div>
    """
    return send_email(email, subject, html, to_name=name)


def send_payment_receipt(user, plan: str, amount_rub: int, period: str = "месяц") -> bool:
    """Confirmation receipt after a successful subscription payment."""
    email = getattr(user, "email", None)
    if not email:
        return False
    name = getattr(user, "nickname", None) or email.split("@")[0]
    subject = f"FORMYLA Pro {period}: оплата получена"
    html = f"""
    <div style="font-family:sans-serif;max-width:560px;margin:0 auto;padding:24px;color:#1f2937;">
      <h2 style="color:#7c3aed;">Спасибо за оплату!</h2>
      <p>Привет, {name}. Мы получили {amount_rub} руб. за тариф <strong>{plan}</strong> ({period}).</p>
      <p>Доступ ко всем функциям Pro уже активирован. Перейти к занятиям: <a href="https://formyla.com/profile" style="color:#0ea5e9;">личный кабинет</a>.</p>
      <p style="color:#6b7280;font-size:13px;margin-top:24px;">Чек об оплате будет также доступен в разделе «История платежей».</p>
    </div>
    """
    return send_email(email, subject, html, to_name=name)
