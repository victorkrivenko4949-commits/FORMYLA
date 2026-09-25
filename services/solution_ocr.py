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


# PHOTO_FIX_V1: HEIC/HEIF-фото (iPhone по умолчанию снимает в HEIC) —
# vision-модели (OpenRouter/Gemini/DeepSeek) такой формат не принимают:
# раньше _mime_from_b64 помечал их как «image/jpeg», все движки падали,
# и ученик на каждом фото получал 422 «Не удалось разобрать, что написано
# на фото». Конвертируем в JPEG на сервере (pillow_heif есть в requirements).
_HEIC_BRANDS = (b"heic", b"heix", b"heim", b"heis", b"hevc", b"hevm", b"mif1", b"msf1")


def _is_heic(b64: str) -> bool:
    """HEIC/HEIF по magic bytes (ftyp-бокс с брендами heic/mif1/...)."""
    try:
        head = base64.b64decode(b64[:32] + "==", validate=False)[:16]
        return head[4:8] == b"ftyp" and head[8:12].lower() in _HEIC_BRANDS
    except Exception:
        return False


def _heic_to_jpeg_b64(b64: str) -> Optional[str]:
    """HEIC/HEIF → JPEG (base64). None, если конвертация невозможна."""
    try:
        from io import BytesIO
        from PIL import Image
        try:
            from pillow_heif import register_heif_opener
            register_heif_opener()
        except Exception:
            logger.warning("[solution_ocr] pillow_heif недоступен — HEIC не конвертируется")
            return None
        img = Image.open(BytesIO(base64.b64decode(b64)))
        img = img.convert("RGB")
        buf = BytesIO()
        img.save(buf, "JPEG", quality=88)
        return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception as e:
        logger.warning("[solution_ocr] HEIC→JPEG conversion failed: %s", e)
        return None


def ensure_jpeg_images(images: List[str]) -> List[str]:
    """PHOTO_FIX_V1: нормализовать список base64-фото — HEIC/HEIF → JPEG.

    JPEG/PNG/WebP/GIF проходят без изменений. Используется и в OCR,
    и в чекере (solution_check_pipeline), чтобы vision-модели всегда
    получали читаемый формат.
    """
    out: List[str] = []
    for raw in (images or []):
        if not raw:
            continue
        b64 = _strip_dataurl(raw)
        if _is_heic(b64):
            conv = _heic_to_jpeg_b64(b64)
            if conv:
                b64 = conv
        out.append(b64)
    return out


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


def _ocr_openrouter_gemini(b64: str, task_text: str) -> Optional[str]:
    """Gemini flash через OpenRouter — распознавание рукописи (основной движок).

    2026-09-15: добавлено, т.к. GEMINI_API_KEY/OdiRouter на проде может
    отсутствовать, а OPENROUTER_API_KEY всегда есть. Распознаём фото ->
    ВЕСЬ текст уходит DeepSeek-проверяльщику как текст (см. pipeline).
    """
    try:
        import os as _os
        import requests as _requests
        _key = _os.environ.get("OPENROUTER_API_KEY", "").strip()
        if not _key:
            return None
        # Кандидаты по приоритету; можно переопределить одной моделью или
        # списком через запятую в OCR_OPENROUTER_MODEL.
        _env_models = [m.strip() for m in (_os.environ.get("OCR_OPENROUTER_MODEL", "") or "").split(",") if m.strip()]
        _candidates = _env_models or [
            "google/gemini-3-flash-preview",
            "google/gemini-3.7-flash",
            "google/gemini-2.5-flash",
            "google/gemini-2.5-flash-lite",
            "google/gemini-2.0-flash-001",
        ]
        _mime = _mime_from_b64(b64)
        _prompt = (
            "Ты — система распознавания рукописного математического текста. "
            "Пожалуйста, РАСПОЗНАЙ ВСЁ, что написано на фото, буква в букву: "
            "весь ход решения, формулы, слова, цифры. Ничего не выдумывай, "
            "не исправляй ошибки, НЕ решай задачу и НЕ комментируй. "
            "Формулы оформи в LaTeX. Если на фото нет решения или текст "
            "нечитабелен — ответь одним словом: UNREADABLE."
        )
        if task_text:
            _prompt += f"\n\nДля контекста, задача: {task_text[:600]}"
        for _model in _candidates:
            try:
                _resp = _requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": _os.environ.get("DOMAIN_URL", "https://formyla.net"),
                        "X-Title": "FORMYLA.net OCR",
                    },
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
                    timeout=(15, 50),
                )
                if _resp.status_code != 200:
                    logger.warning(
                        "[solution_ocr] openrouter %s HTTP %s: %s",
                        _model, _resp.status_code, _resp.text[:160],
                    )
                    continue
                _body = _resp.json()
                if not _body.get("choices"):
                    continue
                _txt = ((_body["choices"][0].get("message", {}) or {}).get("content") or "").strip()
                if not _txt or _txt.upper().startswith("UNREADABLE"):
                    logger.info(
                        "[solution_ocr] openrouter %s: модель не смогла прочитать фото", _model,
                    )
                    # UNREADABLE — честный ответ модели, не пробуем ресурсы впустую
                    return None
                return _txt
            except Exception as _one:
                logger.warning("[solution_ocr] openrouter %s failed: %s", _model, _one)
                continue
        return None
    except Exception as e:
        logger.warning("[solution_ocr] openrouter gemini failed: %s", e)
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
        # 2026-09-15: перебор flash-моделей OdiRouter (gemini-3.6-flash —
        # как просил пользователь; если у провайдера её нет — 3.7/3.8).
        _env_model = (_os.environ.get("GEMINI_VISION_MODEL") or "").strip()
        _models = [_env_model] if _env_model else [
            "gemini-3.6-flash",
            "gemini-3.7-flash",
            "gemini-3.8-flash",
        ]
        _mime = _mime_from_b64(b64)
        _prompt = (
            "Ты — система распознавания рукописного математического текста. "
            "Распознай ВСЁ написанное на фото (ход решения), не исправляя ошибок. "
            "Формулы оформи в LaTeX. НЕ решай и не комментируй."
        )
        if task_text:
            _prompt += f"\n\nДля контекста, задача: {task_text[:600]}"
        for _model in _models:
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
                logger.warning("[solution_ocr] gemini vision %s HTTP %s: %s", _model, _resp.status_code, _resp.text[:200])
                continue
            _body = _resp.json()
            if not _body.get("choices"):
                continue
            _text = (_body["choices"][0].get("message", {}) or {}).get("content") or None
            if _text:
                return _text
        return None
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
        # PHOTO_FIX_V1: HEIC → JPEG до вызова vision-моделей
        if _is_heic(b64):
            _conv = _heic_to_jpeg_b64(b64)
            if _conv:
                b64 = _conv
        mime = _mime_from_b64(b64)

        # Шаг 1: Gemini flash через OpenRouter — ОСНОВНОЙ распознаватель.
        text = None
        engine = "none"
        text = _ocr_openrouter_gemini(b64, task_text)
        if text:
            engine = "openrouter_gemini"

        # Шаг 1b: Gemini через OdiRouter (резерв, если задан GEMINI_API_KEY).
        if not text:
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
    elif "openrouter_gemini" in engines_used and engines_used[0] == "openrouter_gemini":
        confidence = 0.9
    elif "gemini_vision" in engines_used and engines_used[0] == "gemini_vision":
        confidence = 0.9
    elif "deepseek_vision" in engines_used and "tesseract" in engines_used:
        confidence = 0.7
    elif engines_used and engines_used[0] == "tesseract":
        confidence = 0.85
    else:
        confidence = 0.7

    # Приоритет имени движка для аудита: gemini(openrouter/odirouter) > tesseract > novita > deepseek.
    if "openrouter_gemini" in engines_used:
        engine_name = "openrouter_gemini"
    elif "gemini_vision" in engines_used:
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
