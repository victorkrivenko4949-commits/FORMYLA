# -*- coding: utf-8 -*-
"""
services/tesseract_ocr.py — локальное распознавание текста с фото (без AI).

Обёртка над Tesseract OCR (rus+eng), извлечённая из прототипа _photo_ocr.py.
Работает полностью локально: без API, без интернета, бесплатно.

Использование из web-эндпоинтов:
    from services.tesseract_ocr import recognize_bytes
    text, err = recognize_bytes(image_bytes, mime_type)
    # text — распознанный текст, err — описание ошибки (или None)

Если Tesseract не установлен или языки не найдены — возвращает (None, err),
чтобы вызывающий код мог прозрачно переключиться на vision-модель (fallback).
"""

from __future__ import annotations

import base64
import logging
import os
import shutil
import subprocess
import tempfile
import time

logger = logging.getLogger(__name__)

# ── Конфигурация ──────────────────────────────────────────────────────

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESSCACHE = os.path.join(os.path.expanduser("~"), "tessdata_both")

# ── Поиск Tesseract ───────────────────────────────────────────────────

_CANDIDATE_PATHS = [
    os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"),
                 "Tesseract-OCR", "tesseract.exe"),
    os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                 "Tesseract-OCR", "tesseract.exe"),
]

_tesseract_path: str | None = None
_tesseract_checked: bool = False


def _find_tesseract() -> str | None:
    """Найти бинарник Tesseract. Возвращает путь или None."""
    for p in _CANDIDATE_PATHS:
        if p and os.path.exists(p):
            return p
    env_cmd = os.environ.get("TESSERACT_CMD", "").strip()
    if env_cmd and os.path.exists(env_cmd):
        return env_cmd
    found = shutil.which("tesseract")
    if found:
        return found
    return None


def tesseract_available() -> bool:
    """True, если Tesseract найден в системе."""
    global _tesseract_path, _tesseract_checked
    if not _tesseract_checked:
        _tesseract_path = _find_tesseract()
        _tesseract_checked = True
    return _tesseract_path is not None


# ── Языковые пакеты ───────────────────────────────────────────────────

_lang_cache: tuple[str, bool] | None = None  # (lang, use_rus)


def _prepare_tessdata() -> None:
    """Скопировать eng/rus traineddata в TESSCACHE (путь без кириллицы)."""
    global _lang_cache
    if _lang_cache is not None:
        return

    os.makedirs(TESSCACHE, exist_ok=True)

    tesseract = _find_tesseract()
    system_tessdata = (
        os.path.join(os.path.dirname(tesseract), "tessdata")
        if tesseract else None
    )

    # eng
    eng_dst = os.path.join(TESSCACHE, "eng.traineddata")
    if not os.path.exists(eng_dst):
        if system_tessdata:
            eng_src = os.path.join(system_tessdata, "eng.traineddata")
            if os.path.exists(eng_src):
                shutil.copy2(eng_src, eng_dst)

    # rus (из проекта или системы)
    rus_dst = os.path.join(TESSCACHE, "rus.traineddata")
    if not os.path.exists(rus_dst):
        for src in [
            os.path.join(PROJECT_DIR, "rus.traineddata"),
            os.path.join(PROJECT_DIR, "tessdata", "rus.traineddata"),
        ] + ([os.path.join(system_tessdata, "rus.traineddata")]
             if system_tessdata else []):
            if src and os.path.exists(src):
                shutil.copy2(src, rus_dst)
                break

    use_rus = os.path.exists(rus_dst)
    lang = "rus+eng" if use_rus else "eng"
    _lang_cache = (lang, use_rus)
    logger.info("[tesseract] ready (lang=%s)", lang)


# ── OCR по байтам ─────────────────────────────────────────────────────

def _run_ocr_on_file(image_path: str, lang: str) -> str:
    """Запустить Tesseract на файле, вернуть stdout."""
    tesseract = _find_tesseract()
    if not tesseract:
        return ""
    cmd = [tesseract, image_path, "stdout", "-l", lang, "--psm", "3",
           "--tessdata-dir", TESSCACHE]
    try:
        result = subprocess.run(
            cmd, capture_output=True, encoding="utf-8",
            errors="replace", timeout=30,
        )
        return (result.stdout or "").strip()
    except Exception as e:
        logger.warning("[tesseract] OCR subprocess error: %s", e)
        return ""


def recognize_bytes(image_bytes: bytes, mime_type: str = "image/png",
                    refine: bool = False):
    """Распознать текст с фото (raw image bytes).

    Returns (text, error) — ровно одно непустое/None.
    refine=True дополнительно прогоняет через DeepSeek-коррекцию OCR-ошибок
    (требует DEEPSEEK_API_KEY); при его отсутствии просто вернёт сырой текст.
    """
    if not tesseract_available():
        return None, "Tesseract не установлен"

    try:
        _prepare_tessdata()
    except Exception as e:
        return None, f"Ошибка подготовки языков: {e}"

    lang, use_rus = _lang_cache or ("eng", False)

    # Расширение по MIME — Tesseract сам определяет формат, но явное
    # расширение помогает избежать ошибок при автоопределении.
    ext = ".png"
    m = (mime_type or "").lower()
    if "jpeg" in m or "jpg" in m:
        ext = ".jpg"
    elif "webp" in m:
        ext = ".webp"
    elif "bmp" in m:
        ext = ".bmp"
    elif "tiff" in m:
        ext = ".tiff"

    tmp_path = None
    try:
        # Временный файл в TESSCACHE (ASCII-путь, без кириллицы).
        fd, tmp_path = tempfile.mkstemp(suffix=ext, dir=TESSCACHE)
        with os.fdopen(fd, "wb") as f:
            f.write(image_bytes)

        t0 = time.time()
        text = _run_ocr_on_file(tmp_path, lang)

        # Fallback: если rus+eng дал пустоту — пробуем только eng.
        if not text and use_rus:
            text = _run_ocr_on_file(tmp_path, "eng")

        elapsed = time.time() - t0
    except Exception as e:
        logger.warning("[tesseract] recognize_bytes error: %s", e)
        return None, str(e)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    if not text:
        return None, "OCR вернул пустой текст (возможно, на фото нет текста)"

    if refine:
        refined = _refine_with_deepseek(text)
        if refined:
            text = refined

    logger.info("[tesseract] OCR ok: %d chars in %.1fs", len(text), elapsed)
    return text, None


# ── DeepSeek-коррекция OCR-ошибок (опционально) ──────────────────────

def _refine_with_deepseek(raw_text: str) -> str | None:
    """Исправить типичные OCR-ошибки через DeepSeek. Вернуть None при сбое."""
    import requests

    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not key:
        return None

    prompt = (
        "You received OCR output from a photo of a Russian math problem. "
        "OCR may have errors (letters/digits mixed, '3' vs 'Z', '4' vs 'ch'). "
        "Reconstruct the EXACT task statement in Russian:\n"
        "1. Fix OCR errors, restore proper Russian text.\n"
        "2. Math formulas as plain text: x^2, a/b, sqrt(...), <=, >=.\n"
        "3. Return ONLY the clean task statement, nothing else.\n\n"
        f"OCR text:\n{raw_text}"
    )
    try:
        r = requests.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}",
                     "Content-Type": "application/json"},
            json={"model": "deepseek-chat",
                  "messages": [{"role": "user", "content": prompt}],
                  "temperature": 0.1, "max_tokens": 800},
            timeout=20,
        )
        if r.status_code == 200:
            data = r.json()
            if "choices" in data and data["choices"]:
                content = data["choices"][0]["message"].get("content", "")
                if content and content.strip():
                    return content.strip()
    except Exception as e:
        logger.warning("[tesseract] DeepSeek refine error: %s", e)
    return None


# ── Экспорт ───────────────────────────────────────────────────────────

__all__ = [
    "tesseract_available",
    "recognize_bytes",
    "TESSCACHE",
]
