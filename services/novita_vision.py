# -*- coding: utf-8 -*-
"""
services/novita_vision.py — распознавание рукописных решений через Novita AI.

Novita предоставляет OpenAI-совместимый endpoint:
    POST https://api.novita.ai/v3/openai/chat/completions
    Authorization: Bearer <NOVITA_API_KEY>

Vision-модели Novita (OpenAI-совместимые, с поддержкой image_url):
    - qwen/qwen3-vl-30b-a3b-instruct   (основная, проверено: 200 OK)
    - qwen/qwen3-vl-235b-a22b-instruct (fallback, требует JPEG + ресайз)

Возвращает распознанный текст (с LaTeX-оформлением) или None при сбое.
"""

from __future__ import annotations

import base64
import io
import logging
import os
from typing import List, Optional

import requests

logger = logging.getLogger(__name__)

NOVITA_BASE_URL = "https://api.novita.ai/v3/openai/chat/completions"

# Приоритетный список vision-моделей Novita. Порядок важен.
# Проверенная рабочая модель — qwen3-vl-30b-a3b-instruct.
DEFAULT_VISION_MODELS = [
    "qwen/qwen3-vl-30b-a3b-instruct",
    "qwen/qwen3-vl-235b-a22b-instruct",
]

# Параметры подготовки изображения. Все фото ужимаем до JPEG (максимум
# 1536px по длинной стороне, quality=85) — это резко ускоряет запрос и
# убирает таймауты «write operation timed out» на больших фото с телефона.
IMAGE_MAX_SIDE = 1536
IMAGE_JPEG_QUALITY = 85
VISION_MAX_TOKENS = 2048
VISION_TEMPERATURE = 0.1

_SYSTEM_PROMPT = (
    "Ты — система распознавания рукописного математического текста "
    "для российского школьника. На фото рукописное решение задачи "
    "из тетради. Твоя задача:\n"
    "1. ВНИМАТЕЛЬНО распознать ВЕСЬ написанный текст и формулы.\n"
    "2. Выписать ход решения в точности, как ученик его записал, "
    "не исправляя ошибок ученика.\n"
    "3. Математические формулы оформить в LaTeX: \\(...\\) "
    "для строчных, \\[...\\] для блочных.\n"
    "4. Сохранить переносы строк и нумерацию шагов.\n"
    "5. НЕ комментировать, НЕ оценивать, НЕ решать заново. "
    "Только аккуратная транскрипция того, что написано.\n\n"
    "ВАЖНО ПРО ДРОБИ И НЕРАВЕНСТВА:\n"
    "- Дробь с числителем и знаменателем ВСЕГДА записывай как "
    "\\frac{числитель}{знаменатель}. НИКОГДА не разрывай дробь и не "
    "теряй ни числитель, ни знаменатель.\n"
    "- Например «AM < (AB + AC) / 2» пиши как "
    "\\(AM < \\frac{AB + AC}{2}\\).\n"
    "- Если в условии стоит знак ≤ или ≥, сохраняй именно его, а не < или >.\n"
    "- Проверяй, что после дроби не потеряны знаменатель и правая часть.\n\n"
    "Если на фото вообще нет читаемого решения, верни одну строку: "
    "(на фото не удалось разобрать решение)."
)


def _api_key() -> str:
    """Вернуть NOVITA_API_KEY из окружения (через .env, если загружен)."""
    return (os.environ.get("NOVITA_API_KEY") or "").strip()


def _vision_models() -> List[str]:
    """Список vision-моделей (можно переопределить через env)."""
    override = (os.environ.get("NOVITA_VISION_MODELS") or "").strip()
    if override:
        models = [m.strip() for m in override.split(",") if m.strip()]
        if models:
            return models
    return list(DEFAULT_VISION_MODELS)


def _mime_from_b64(b64: str) -> str:
    """Определить MIME по магическим байтам base64-строки."""
    try:
        head = base64.b64decode(b64[:32] + "==", validate=False)[:12]
        if head.startswith(b"\x89PNG"):
            return "image/png"
        if head.startswith(b"GIF8"):
            return "image/gif"
        if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
            return "image/webp"
        if head.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
    except Exception:
        pass
    return "image/jpeg"


def _prepare_image_jpeg(
    image_data: str,
    max_side: int = IMAGE_MAX_SIDE,
    quality: int = IMAGE_JPEG_QUALITY,
) -> str:
    """Декодировать base64-картинку, ресайзнуть и перекодировать в JPEG.

    Возвращает base64-строку JPEG (без data: префикса), либо None при сбое.
    """
    try:
        from PIL import Image

        raw = base64.b64decode(image_data)
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        img.thumbnail((max_side, max_side))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception as e:
        logger.warning("[novita_vision] prepare_image failed: %s", e)
        return None


def _error_message(resp: requests.Response) -> str:
    """Извлечь поле error.message / reason из тела ответа Novita."""
    try:
        data = resp.json()
    except Exception:
        return resp.text[:500]
    if isinstance(data, dict):
        msg = data.get("message") or data.get("reason") or data.get("error")
        if isinstance(msg, dict):
            return str(msg)
        return str(msg) if msg else resp.text[:500]
    return str(data)[:500]


def transcribe_handwritten_solution(image_data: str, task_text: str = "") -> Optional[str]:
    """Распознать рукописное решение через Novita vision.

    Args:
        image_data: base64-строка изображения (без data: префикса).
        task_text: условие задачи (контекст для модели).

    Returns:
        Распознанный текст или None, если ни одна модель не сработала.
    """
    if not image_data:
        return None

    api_key = _api_key()
    if not api_key:
        logger.warning("[novita_vision] NOVITA_API_KEY не задан.")
        return None

    mime = _mime_from_b64(image_data)
    user_text = "Распознай это рукописное решение."
    if task_text:
        user_text += f"\n\nДля контекста, задача: {task_text[:600]}"

    # Для ВСЕХ моделей готовим уменьшенный JPEG (максимум 1536px по длинной
    # стороне, quality=85). Большие фото (фото с телефона) вызывают таймаут
    # «write operation timed out» у Novita и медленную генерацию — ресайз
    # резко ускоряет запрос и повышает надёжность распознавания.
    jpeg_b64 = _prepare_image_jpeg(image_data)
    if jpeg_b64:
        use_b64 = jpeg_b64
        use_mime = "image/jpeg"
    else:
        use_b64 = image_data
        use_mime = mime

    for model in _vision_models():
        if not use_b64:
            logger.warning("[novita_vision] пустое изображение для %s.", model)
            continue

        # 30B/235B принимают image_url в OpenAI-совместимом формате.
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{use_mime};base64,{use_b64}",
                            },
                        },
                    ],
                },
            ],
            "temperature": VISION_TEMPERATURE,
            "max_tokens": VISION_MAX_TOKENS,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        try:
            # Короткие таймауты: Novita периодически зависает на стадии
            # отправки и на чтении ответа. 5 c на соединение, 20 c на чтение —
            # пайплайн быстро падает к следующей модели или Tesseract.
            resp = requests.post(
                NOVITA_BASE_URL,
                headers=headers,
                json=payload,
                timeout=(5, 20),
            )
            if resp.status_code != 200:
                err = _error_message(resp)
                logger.warning(
                    "[novita_vision] %s HTTP %s: %s",
                    model, resp.status_code, err,
                )
                continue
            data = resp.json()
            if "choices" in data and data["choices"]:
                text = (data["choices"][0].get("message", {}) or {}).get("content") or ""
                if text:
                    logger.info(
                        "[novita_vision] %s ok, transcribed_len=%d",
                        model, len(text),
                    )
                    return text.strip()
        except Exception as e:
            logger.warning("[novita_vision] %s raised: %s", model, e)
            continue

    logger.error("[novita_vision] все vision-модели Novita не сработали.")
    return None


__all__ = [
    "transcribe_handwritten_solution",
    "_api_key",
]
