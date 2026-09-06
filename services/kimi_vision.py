# -*- coding: utf-8 -*-
"""
services/kimi_vision.py — KIMI Vision OCR for photo-to-text recognition.

Uses api.moonshot.ai (.ai domain — the .cn domain is geo-blocked in Russia)
and a vision-capable model (same model family as solution review in
services/kimi_review.py).  The old version pointed at api.moonshot.cn with
the text-only model "moonshot-v1-8k", which cannot accept image input and
returned HTTP 401 (Invalid Authentication) — both fixed here.
"""
import base64
import logging
import time

import requests

from services.kimi_review import _get_kimi_key, _get_kimi_model

logger = logging.getLogger(__name__)

KIMI_API_URL = "https://api.moonshot.ai/v1/chat/completions"

_VISION_SYSTEM_PROMPT = (
    "Ты — OCR-ассистент для распознавания математических задач с фотографий. "
    "Перепиши ВСЁ, что видно на фото: текст, условие, обозначения, формулы. "
    "Формулы записывай в LaTeX (между $...$). "
    "НЕ решай задачу и не комментируй — только аккуратно перепиши условие. "
    "Отвечай на русском языке."
)


def process_photo_with_kimi(image_bytes: bytes, mime_type: str = "image/jpeg"):
    """Recognize math text from a photo via the KIMI vision API.

    Returns (text, error) — exactly one of them is non-empty/None.
    """
    try:
        kimi_key = _get_kimi_key()
    except Exception as e:
        return None, str(e)

    model = _get_kimi_model()

    try:
        b64 = base64.b64encode(image_bytes).decode()
    except Exception as e:
        return None, str(e)

    messages = [
        {"role": "system", "content": _VISION_SYSTEM_PROMPT},
        {"role": "user", "content": [
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime_type};base64,{b64}",
                    "detail": "high",
                },
            },
        ]},
    ]

    headers = {
        "Authorization": f"Bearer {kimi_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": 2000,
    }

    max_retries = 3
    base_delay = 2.0

    for attempt in range(max_retries):
        try:
            logger.info("[Kimi-Vision] attempt %d/%d model=%s",
                        attempt + 1, max_retries, model)
            r = requests.post(
                KIMI_API_URL,
                headers=headers,
                json=payload,
                timeout=90,
            )

            if r.status_code == 200:
                data = r.json()
                if "choices" in data and data["choices"]:
                    msg = data["choices"][0].get("message", {}) or {}
                    content = msg.get("content") or ""
                    # Reasoning models often leave `content` empty and put
                    # the actual answer into `reasoning_content`.
                    if not content:
                        content = msg.get("reasoning_content") or ""
                    if content:
                        return content, None
                    return None, "KIMI: пустой ответ (content и reasoning_content пусты)"
                return None, "KIMI: нет choices в ответе"

            if r.status_code in (401, 403):
                return None, f"KIMI HTTP {r.status_code}: {r.text[:200]}"

            if r.status_code == 429:
                wait = 30
                logger.warning("[Kimi-Vision] 429, waiting %ds", wait)
                time.sleep(wait)
                continue

            if r.status_code in (500, 502, 503, 504):
                wait = base_delay * (2 ** attempt)
                logger.warning("[Kimi-Vision] %d, waiting %.1fs", r.status_code, wait)
                time.sleep(wait)
                continue

            return None, f"KIMI HTTP {r.status_code}: {r.text[:300]}"

        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                wait = base_delay * (2 ** attempt)
                logger.warning("[Kimi-Vision] timeout, waiting %.1fs", wait)
                time.sleep(wait)
                continue
            return None, "KIMI: превышено время ожидания"
        except requests.exceptions.ConnectionError as e:
            if attempt < max_retries - 1:
                wait = base_delay * (2 ** attempt)
                logger.warning("[Kimi-Vision] connection error, waiting %.1fs", wait)
                time.sleep(wait)
                continue
            return None, str(e)
        except Exception as e:
            return None, str(e)

    return None, f"KIMI: не удалось после {max_retries} попыток"
