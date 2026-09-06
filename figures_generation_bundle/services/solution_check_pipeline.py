# -*- coding: utf-8 -*-
"""
services/solution_check_pipeline.py — единый pipeline проверки решения.

Режимы (entity_type):
    - "regular"     — ИИ-тьютор (чат)
    - "srez"        — утренний срез (prep/probe)
    - "daily_task"  — задачи дня

Логика:
    1. Если есть фото -> OCR (services.solution_ocr) -> нормализация.
    2. Текст или распознанное фото -> единый checker (services.ai_tutor_review.review_attempt).
    3. Возвращает unified verdict format.

Unified verdict:
    {
      "status": "processing"|"success"|"failed",
      "entity_type": str,
      "is_correct": bool,
      "score": float,
      "answer_correct": bool|None,
      "method_correct": bool|None,
      "category": str,
      "confidence": float,
      "feedback": str,
      "solution": str,          # эталон/полное решение для показа
      "correct_answer": str,
      "ocr": {...} | None,      # метаданные OCR (если было фото)
      "ai_failure": bool,       # True — ИИ не смог вынести вердикт (нейтрально)
    }

Совместимость: текстовая проверка (без фото) полностью эквивалентна старому
review_attempt() — pipeline не меняет финальный вердикт, только добавляет
OCR-слой перед ним.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _pick_deepseek():
    """Вернуть (DeepSeekClient, available) по аналогии с app.py."""
    try:
        from ai.deepseek_client import DeepSeekClient
        return DeepSeekClient, True
    except Exception:
        return None, False


def check_solution(
    *,
    entity_type: str,
    task_text: str,
    correct_answer: str,
    solution_ref: str = "",
    user_answer: str = "",
    user_solution: str = "",
    images_b64: Optional[List[str]] = None,
    difficulty_level: int = 4,
    max_tokens: int = 4096,
) -> Dict[str, Any]:
    """Единая точка проверки решения для всех трёх режимов.

    Args:
        entity_type: 'regular' | 'srez' | 'daily_task'.
        task_text: условие задачи.
        correct_answer: эталонный ответ.
        solution_ref: эталонное решение.
        user_answer: краткий ответ ученика.
        user_solution: текст решения (или распознанный OCR).
        images_b64: список base64-фото решения.
        difficulty_level: уровень задачи.
        max_tokens: лимит генерации.

    Returns unified verdict dict (см. docstring модуля).
    """
    entity_type = (entity_type or "regular").strip().lower()
    if entity_type not in ("regular", "srez", "daily_task"):
        logger.warning("[pipeline] unknown entity_type=%r -> regular", entity_type)
        entity_type = "regular"

    user_answer = (user_answer or "").strip()
    user_solution = (user_solution or "").strip()
    images = [x for x in (images_b64 or []) if x]

    ocr_meta: Optional[Dict[str, Any]] = None

    # ── Шаг 1: OCR фото ────────────────────────────────────────────────
    if images:
        try:
            from services.solution_ocr import ocr_solution_images
            ocr_meta = ocr_solution_images(images, task_text or "")
            ocr_text = (ocr_meta.get("text") or "").strip()
            if ocr_text:
                header = (
                    "[Распознанное фото-решение]"
                    if ocr_meta.get("parts", 0) > 1
                    else "[Распознанное фото-решение]"
                )
                if user_solution:
                    user_solution = f"{user_solution}\n\n{header}\n{ocr_text}"
                else:
                    user_solution = f"{header}\n{ocr_text}"
            if ocr_meta.get("warning"):
                logger.info(
                    "[pipeline] %s OCR warning: %s",
                    entity_type, ocr_meta.get("warning"),
                )
        except Exception as e:
            logger.exception("[pipeline] OCR failed for %s: %s", entity_type, e)
            ocr_meta = {
                "text": "",
                "engine": "none",
                "confidence": 0.0,
                "low_confidence": True,
                "parts": len(images),
                "normalized": False,
                "warning": str(e),
            }

    # ── Шаг 2: единый checker ──────────────────────────────────────────
    deepseek_cls, deepseek_avail = _pick_deepseek()

    try:
        from services.ai_tutor_review import review_attempt
        result = review_attempt(
            task_text=task_text or "",
            correct_answer=correct_answer or "",
            solution_ref=solution_ref or "",
            user_answer=user_answer,
            user_solution=user_solution,
            images_b64=images,
            deepseek_client_cls=deepseek_cls,
            deepseek_available=deepseek_avail,
            max_tokens=max_tokens,
            difficulty_level=difficulty_level,
            sanitize_latex=False,  # оставляем LaTeX для фронта (KaTeX)
        )
    except Exception as e:
        logger.exception("[pipeline] review_attempt raised for %s: %s", entity_type, e)
        result = {
            "score": 0.0,
            "feedback": "AI-проверка временно недоступна — оценка нейтральная.",
            "is_correct": False,
            "answer_correct": None,
            "method_correct": None,
            "category": "suspicious",
            "confidence": 0.0,
            "error_location": None,
            "needs_escalation": False,
            "user_solution_enriched": user_solution,
        }

    # ── Шаг 3: unified verdict ─────────────────────────────────────────
    ai_failure = (
        result.get("category") == "suspicious"
        and float(result.get("confidence") or 0.0) <= 0.0
    )
    status = "failed" if ai_failure else "success"

    verdict: Dict[str, Any] = {
        "status": status,
        "entity_type": entity_type,
        "is_correct": bool(result.get("is_correct")),
        "score": float(result.get("score") or 0.0),
        "answer_correct": result.get("answer_correct"),
        "method_correct": result.get("method_correct"),
        "category": result.get("category") or "suspicious",
        "confidence": float(result.get("confidence") or 0.0),
        "feedback": result.get("feedback") or "",
        "solution": solution_ref or "",
        "correct_answer": correct_answer or "",
        "error_location": result.get("error_location"),
        "needs_escalation": bool(result.get("needs_escalation")),
        "ocr": ocr_meta,
        "ai_failure": ai_failure,
    }

    logger.info(
        "[pipeline] %s verdict: status=%s is_correct=%s category=%s "
        "confidence=%.2f ocr_engine=%s low_confidence=%s",
        entity_type,
        verdict["status"],
        verdict["is_correct"],
        verdict["category"],
        verdict["confidence"],
        (ocr_meta or {}).get("engine"),
        (ocr_meta or {}).get("low_confidence"),
    )

    return verdict


__all__ = ["check_solution"]
