# -*- coding: utf-8 -*-
"""Общий DeepSeek-vision декодер фото (тот же, что в GeoExact /recognize-photo).

Используется GeoExact и задачами дня: одна конфигурация — thinking отключён,
повтор без параметра при HTTP 400 «thinking», таймаут (15, 60).
"""
import os
from typing import Optional

# Модели, для которых провайдер не принял параметр thinking.
_THINKING_UNSUPPORTED: set = set()


def decode_photo(b64: str, mime: str, prompt: str, max_tokens: int = 2048,
                 timeout=(15, 60)) -> Optional[str]:
    """Вернуть текст с фото через DeepSeek vision или None при любом сбое."""
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not key or not b64:
        return None
    try:
        import requests as _rq
        model = os.getenv("DEEPSEEK_VISION_MODEL",
                          "deepseek-v4-flash-vision-exp").strip()
        payload = {"model": model, "max_tokens": max_tokens, "messages": [
            {"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url",
                 "image_url": {"url": f"data:{mime};base64,{b64}"}},
            ]},
        ]}
        headers = {"Authorization": "Bearer " + key,
                   "Content-Type": "application/json"}
        url = "https://api.deepseek.com/v1/chat/completions"
        if model not in _THINKING_UNSUPPORTED:
            payload["thinking"] = {"type": "disabled"}
        r = _rq.post(url, headers=headers, json=payload, timeout=timeout)
        if (r.status_code == 400 and model not in _THINKING_UNSUPPORTED
                and "thinking" in (r.text or "").lower()):
            _THINKING_UNSUPPORTED.add(model)
            payload.pop("thinking", None)
            r = _rq.post(url, headers=headers, json=payload, timeout=timeout)
        if r.status_code != 200:
            return None
        body = r.json()
        if not body.get("choices"):
            return None
        text = (body["choices"][0].get("message", {}) or {}).get("content") or ""
        return text.strip() or None
    except Exception:
        return None
