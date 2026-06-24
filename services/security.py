# -*- coding: utf-8 -*-
"""services/security.py - lightweight security helpers for FORMYLA.
Provides CSP/security headers, a simple session-based CSRF token and basic
input sanitisation. Implemented without Flask-WTF so it has no extra deps
beyond Flask + itsdangerous (both already in requirements).
"""
from __future__ import annotations
import html
import re
import secrets
from typing import Any
from flask import session, g

_CSRF_SESSION_KEY = "_csrf_token"
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def get_csrf_token() -> str:
    """Return a per-session CSRF token, generating one if needed."""
    token = session.get(_CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        session[_CSRF_SESSION_KEY] = token
    return token


def validate_csrf(token: str) -> bool:
    """Constant-time compare a submitted token against the session token."""
    expected = session.get(_CSRF_SESSION_KEY)
    if not expected or not token:
        return False
    return secrets.compare_digest(str(expected), str(token))


def sanitize_text(value: Any, max_len: int = 10000) -> str:
    """Coerce to str, strip control chars and HTML-escape. Safe for storage."""
    if value is None:
        return ""
    text = value if isinstance(value, str) else str(value)
    text = _CONTROL_CHARS_RE.sub("", text)
    text = text.strip()
    if max_len and len(text) > max_len:
        text = text[:max_len]
    return html.escape(text, quote=True)


def sanitize_json_payload(payload: Any, max_len: int = 10000) -> Any:
    """Recursively sanitise strings inside a JSON-like structure.
    Dict keys are kept as-is; string values, list items and nested dicts
    are sanitised. Non-string scalars (int/float/bool/None) pass through.
    """
    if isinstance(payload, str):
        return sanitize_text(payload, max_len=max_len)
    if isinstance(payload, dict):
        return {k: sanitize_json_payload(v, max_len=max_len) for k, v in payload.items()}
    if isinstance(payload, (list, tuple)):
        return [sanitize_json_payload(v, max_len=max_len) for v in payload]
    return payload


def _security_headers(response):
    """Attach a conservative set of security headers to every response."""
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault(
        "Content-Security-Policy",
        "frame-ancestors 'self'",
    )
    return response


def init_security(app) -> None:
    """Wire security helpers into a Flask app.
    - adds security headers on every response
    - exposes get_csrf_token / csrf_token to Jinja templates
    - ensures a CSRF token exists for each session
    This is intentionally non-blocking: it does NOT reject requests on its
    own so it cannot break existing forms. Enforcement can be layered on
    later via validate_csrf() in individual views.
    """
    app.after_request(_security_headers)

    @app.before_request
    def _ensure_csrf_token():
        try:
            g.csrf_token = get_csrf_token()
        except Exception:
            g.csrf_token = ""

    @app.context_processor
    def _inject_csrf():
        return {
            "get_csrf_token": get_csrf_token,
            "csrf_token": get_csrf_token,
        }

    app.logger.info("[security] init_security applied (headers + csrf helpers)")
