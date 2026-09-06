# -*- coding: utf-8 -*-
"""
services/solution_ocr.py — OCR-препроцессинг фотографий решения (единый слой).

Для всех трёх режимов (regular / srez / daily_task):
  photo bytes -> Tesseract (local, free) -> fallback DeepSeek vision ->
  normalization (utils.math_text_fixer) -> structured text.

Возвращает словарь с метаданными для аудита и low-confidence handling:

    {
      "text": str,               # нормализованный LaTeX-текст решения
      "engine": "tesseract"|"deepseek_vision"|"none",
      "confidence": float,       # 0.0..1.0
      "low_confidence": bool,    # True — распознавание ненадёжно
      "parts": int,              # сколько фото обработано
      "normalized": bool,        # была ли применена нормализация
      "warning": Optional[str],  # человекочитаемое предупреждение
    }

Совместимость: текстовая проверка (без фото) не затрагивается — этот слой
вызывается только когда images_b64 непуст.
"""

from __future__ import annotations

import base64
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Пороги «низкого доверия» к распознаванию.
MIN_CHARS = 8            # меньше символов — почти наверняка пусто/мусор
LOW_CONF_CHARS = 20      # меньше — помечаем low_confidence
GARBAGE_RATIO = 0.6      # доля неалфавитных символов, при которой считаем мусором


def _mime_from_b64(b64: str) -> str:
    """Определить MIME по первым байтам base64-строки."""
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


def _strip_dataurl(b: str) -> str:
    """Убрать префикс data:..., если есть."""
    return b.split(",", 1)[-1] if b.startswith("data:") else b


def _ocr_tesseract(image_bytes: bytes, mime: str) -> Optional[str]:
    """Локальный бесплатный OCR через Tesseract. None при недоступности."""
    try:
        from services.tesseract_ocr import recognize_bytes, tesseract_available
        if not tesseract_available():
            return None
        text, err = recognize_bytes(image_bytes, mime)
        if text:
            return text
        logger.info("[solution_ocr] tesseract empty: %s", err)
    except Exception as e:
        logger.warning("[solution_ocr] tesseract failed: %s", e)
    return None


def _ocr_novita_vision(b64: str, task_text: str) -> Optional[str]:
    """Novita vision (qwen2.5-vl и др.) — распознавание рукописных решений."""
    try:
        from services.novita_vision import transcribe_handwritten_solution
        return transcribe_handwritten_solution(
            image_data=b64,
            task_text=task_text or "",
        )
    except Exception as e:
        logger.warning("[solution_ocr] novita vision failed: %s", e)
        return None


def _ocr_gemini_vision(b64: str, task_text: str) -> Optional[str]:
    """Gemini vision (через OdiRouter OpenAI-compatible endpoint) — распознавание рукописных решений.

    Использует GEMINI_API_KEY + GEMINI_API_BASE + GEMINI_VISION_MODEL (default: gemini-3.7-flash).
    None при сбое/отсутствии ключа.
    """
    try:
        import os as _os
        import requests as _requests
        _key = _os.environ.get("GEMINI_API_KEY", "").strip()
        if not _key:
            return None
        _base = (_os.environ.get("GEMINI_API_BASE") or "https://api.odirouter.ai/v1").strip().rstrip("/")
        _model = (_os.environ.get("GEMINI_VISION_MODEL") or "gemini-3.7-flash").strip()
        _mime = _mime_from_b64(b64)
        _prompt = (
            "Ты — система распознавания рукописного математического текста. "
            "Распознай ВСЁ написанное на фото (ход решения), не исправляя ошибок. "
            "Формулы оформи в LaTeX. НЕ решай и не комментируй."
        )
        if task_text:
            _prompt += f"\n\nДля контекста, задача: {task_text[:600]}"
        _resp = _requests.post(
            f"{_base}/chat/completions",
            headers={"Authorization": f"Bearer {_key}", "Content-Type": "application/json"},
            json={
                "model": _model,
                "messages": [
                    {"role": "user", "content": [
                        {"type": "text", "text": _prompt},
                        {"type": "image_url", "image_url": {"url": f"data:{_mime};base64,{b64}"}},
                    ]},
                ],
                "temperature": 0.1,
                "max_tokens": 4096,
            },
            timeout=(15, 60),
        )
        if _resp.status_code != 200:
            logger.warning("[solution_ocr] gemini vision HTTP %s: %s", _resp.status_code, _resp.text[:200])
            return None
        _body = _resp.json()
        if not _body.get("choices"):
            return None
        return (_body["choices"][0].get("message", {}) or {}).get("content") or None
    except Exception as e:
        logger.warning("[solution_ocr] gemini vision failed: %s", e)
        return None


def _ocr_deepseek_vision(b64: str, task_text: str) -> Optional[str]:
    """DeepSeek vision (deepseek-v4-flash-vision-exp) — распознавание рукописных решений.

    Прямой вызов к api.deepseek.com с image_url; корректно читает LaTeX-дроби
    и знаки неравенств (проверено). None при сбое.
    """
    try:
        import os as _os
        import requests as _requests
        _key = _os.environ.get("DEEPSEEK_API_KEY", "").strip()
        if not _key:
            return None
        _model = _os.getenv("DEEPSEEK_VISION_MODEL", "deepseek-v4-flash-vision-exp").strip()
        _mime = _mime_from_b64(b64)
        _prompt = "Распознай это рукописное решение задачи. Формулы оформи в LaTeX."
        if task_text:
            _prompt += f"\n\nДля контекста, задача: {task_text[:600]}"
        _resp = _requests.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {_key}", "Content-Type": "application/json"},
            json={
                "model": _model,
                "messages": [
                    {"role": "user", "content": [
                        {"type": "text", "text": _prompt},
                        {"type": "image_url", "image_url": {"url": f"data:{_mime};base64,{b64}"}},
                    ]},
                ],
                "temperature": 0.3,
                "max_tokens": 4096,
            },
            timeout=(15, 60),
        )
        if _resp.status_code != 200:
            logger.warning("[solution_ocr] deepseek vision HTTP %s: %s", _resp.status_code, _resp.text[:200])
            return None
        _body = _resp.json()
        if not _body.get("choices"):
            return None
        return (_body["choices"][0].get("message", {}) or {}).get("content") or None
    except Exception as e:
        logger.warning("[solution_ocr] deepseek vision failed: %s", e)
        return None


def _normalize(text: str) -> Tuple[str, bool]:
    """Нормализовать OCR-текст в корректный LaTeX. Возвращает (text, changed)."""
    try:
        from utils.math_text_fixer import fix_plain_math
        fixed = fix_plain_math(text)
        if fixed and fixed != text:
            return fixed, True
    except Exception as e:
        logger.warning("[solution_ocr] normalization failed: %s", e)
    return text, False


def _estimate_confidence(text: str) -> Tuple[float, bool, Optional[str]]:
    """Оценить надёжность распознавания."""
    t = (text or "").strip()
    if not t:
        return 0.0, True, "На фото не удалось разобрать решение."
    if len(t) < MIN_CHARS:
        return 0.1, True, "Распознано слишком мало текста — проверьте фото."

    # Доля «нечитаемых» символов
    readable = len(re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9\s=+\-*/^_\\]", t))
    ratio = readable / max(1, len(t))
    if ratio < GARBAGE_RATIO:
        return 0.2, True, "Распознанный текст похож на мусор — сделайте фото чётче."

    if len(t) < LOW_CONF_CHARS:
        return 0.5, True, "Текст короткий — проверка может быть неточной."

    return 0.85, False, None


def ocr_solution_images(
    images_b64: List[str],
    task_text: str = "",
) -> Dict[str, Any]:
    """Распознать список base64-фото решения и вернуть структурированный текст.

    Args:
        images_b64: список base64-строк (без/с data: префиксом).
        task_text: условие задачи (для контекста vision-модели).

    Returns:
        dict с полями text/engine/confidence/low_confidence/parts/normalized/warning.
    """
    images = [x for x in (images_b64 or []) if x]
    if not images:
        return {
            "text": "",
            "engine": "none",
            "confidence": 1.0,
            "low_confidence": False,
            "parts": 0,
            "normalized": False,
            "warning": None,
        }

    parts: List[str] = []
    engines_used: List[str] = []
    any_low = False
    warnings: List[str] = []
    any_normalized = False

    for idx, raw in enumerate(images, start=1):
        b64 = _strip_dataurl(raw)
        mime = _mime_from_b64(b64)

        # Шаг 1: Gemini vision — ОСНОВНОЙ распознаватель рукописных решений.
        text = None
        engine = "none"
        text = _ocr_gemini_vision(b64, task_text)
        if text:
            engine = "gemini_vision"

        # Шаг 2: DeepSeek vision (резерв).
        if not text:
            text = _ocr_deepseek_vision(b64, task_text)
            if text:
                engine = "deepseek_vision"

        # Шаг 3: локальный Tesseract (резерв).
        if not text:
            try:
                img_bytes = base64.b64decode(b64)
                text = _ocr_tesseract(img_bytes, mime)
                if text:
                    engine = "tesseract"
            except Exception as e:
                logger.warning("[solution_ocr] b64 decode failed #%d: %s", idx, e)

        # Шаг 4: Novita vision (резерв).
        if not text:
            text = _ocr_novita_vision(b64, task_text)
            if text:
                engine = "novita_vision"

        if text:
            normalized, changed = _normalize(text)
            if changed:
                any_normalized = True
                text = normalized
            conf, low, warn = _estimate_confidence(text)
            if low:
                any_low = True
                if warn:
                    warnings.append(warn)
            # Собираем итог
            parts.append(text)
            engines_used.append(engine)
        else:
            engines_used.append("none")
            warnings.append(f"Фото {idx}: не удалось распознать.")
            any_low = True

    joined = "\n\n".join(parts).strip()
    if not joined:
        return {
            "text": "",
            "engine": "none",
            "confidence": 0.0,
            "low_confidence": True,
            "parts": len(images),
            "normalized": any_normalized,
            "warning": "; ".join(warnings) if warnings else None,
        }

    # Итоговая уверенность — минимум по частям (грубая оценка)
    if "none" in engines_used:
        confidence = 0.3
    elif "gemini_vision" in engines_used and engines_used[0] == "gemini_vision":
        confidence = 0.9
    elif "deepseek_vision" in engines_used and "tesseract" in engines_used:
        confidence = 0.7
    elif engines_used and engines_used[0] == "tesseract":
        confidence = 0.85
    else:
        confidence = 0.7

    # Приоритет имени движка для аудита: gemini > tesseract > novita > deepseek.
    if "gemini_vision" in engines_used:
        engine_name = "gemini_vision"
    elif "tesseract" in engines_used:
        engine_name = "tesseract"
    elif "novita_vision" in engines_used:
        engine_name = "novita_vision"
    elif "deepseek_vision" in engines_used:
        engine_name = "deepseek_vision"
    else:
        engine_name = "none"

    return {
        "text": joined,
        "engine": engine_name,
        "confidence": round(confidence, 2),
        "low_confidence": any_low,
        "parts": len(images),
        "normalized": any_normalized,
        "warning": "; ".join(warnings) if warnings else None,
    }


__all__ = [
    "ocr_solution_images",
    "_estimate_confidence",
]
