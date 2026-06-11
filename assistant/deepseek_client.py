# -*- coding: utf-8 -*-
"""Thin, dependency-free DeepSeek wrapper used by the FORMYLA site assistant.

Why a separate wrapper?
-----------------------
The project already ships a heavier client in :mod:`ai.deepseek_client`
that is tuned for math generation (long timeouts, reasoner model, retries).
For a UX helper we want a tighter shape:

* sub-30s response time;
* a single try with a short timeout;
* graceful degradation when the key is missing or the call fails;
* support for several env-var names so we never accidentally break Render.

The wrapper purposely never raises — on any failure it returns ``None``
and the service layer falls back to a deterministic answer.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import requests

logger = logging.getLogger(__name__)


# Supported env-var aliases (TZ §6 — preserve compatibility with existing setups).
_API_KEY_ENV_NAMES = ("DEEPSEEK_API_KEY", "DEEPSEEK_KEY")
_BASE_URL_ENV = "DEEPSEEK_BASE_URL"
_MODEL_ENV = "DEEPSEEK_MODEL"

_DEFAULT_BASE_URL = "https://api.deepseek.com"
_DEFAULT_MODEL = "deepseek-chat"
_DEFAULT_TIMEOUT = 25      # seconds — UX helper, not a generator
_DEFAULT_TEMPERATURE = 0.2
_DEFAULT_MAX_TOKENS = 450  # answers are short by policy


def get_api_key() -> Optional[str]:
    """Return the first non-empty DeepSeek key found in the environment."""
    for name in _API_KEY_ENV_NAMES:
        val = (os.environ.get(name) or "").strip()
        if val:
            return val
    return None


def is_enabled() -> bool:
    """True if a DeepSeek key is configured."""
    return bool(get_api_key())


def chat(
    user_message: str,
    system_prompt: str,
    *,
    temperature: float = _DEFAULT_TEMPERATURE,
    max_tokens: int = _DEFAULT_MAX_TOKENS,
    timeout: int = _DEFAULT_TIMEOUT,
) -> Optional[str]:
    """Single-shot chat completion.

    Returns the assistant text on success, or ``None`` on any failure
    (missing key, network error, non-2xx response, empty content).
    """
    api_key = get_api_key()
    if not api_key:
        logger.info("assistant.deepseek_client: no API key configured")
        return None

    base_url = (os.environ.get(_BASE_URL_ENV) or _DEFAULT_BASE_URL).rstrip("/")
    model = (os.environ.get(_MODEL_ENV) or _DEFAULT_MODEL).strip() or _DEFAULT_MODEL
    url = f"{base_url}/v1/chat/completions"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
    except requests.RequestException as e:
        logger.warning("assistant.deepseek_client: network error: %s", e)
        return None

    if resp.status_code != 200:
        # Truncate to keep logs lean; never log the key.
        snippet = (resp.text or "")[:300]
        logger.warning(
            "assistant.deepseek_client: HTTP %s — %s", resp.status_code, snippet
        )
        return None

    try:
        data = resp.json()
        content = (
            data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
        )
    except Exception as e:  # pragma: no cover — defensive
        logger.warning("assistant.deepseek_client: bad response shape: %s", e)
        return None

    content = (content or "").strip()
    return content or None


__all__ = ["chat", "get_api_key", "is_enabled"]
