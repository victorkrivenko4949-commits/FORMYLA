# -*- coding: utf-8 -*-
"""Пост-валидация результата глубокого разбора (раздел 6 ТЗ).

Модуль `insightValidator`, покрытый тестами. Отбрасывает результат, если:
  - has_insight = false;
  - title или what_went_wrong содержит слово из стоп-списка;
  - type вне допустимого перечня;
  - practice содержит не ровно 3 задачи;
  - значения visibility не образуют полный набор obvious/medium/hidden;
  - у задачи пустое why_this_task;
  - title короче 15 символов — признак общей формулировки.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from models_insights import INSIGHT_TYPES, SKIP_REASONS, VISIBILITIES

# Стоп-слова общих формулировок (раздел 6 ТЗ, с учётом словоформ).
STOPWORDS = (
    "невнимательн",
    "больше практики",
    "слабая база",
    "не умеет",
    "аккуратн",
    "ошибки в вычислениях",
    "не хватает логики",
    "нужно повторить тему",
)

MIN_TITLE_LEN = 15


class ValidationResult:
    """Результат валидации одного deep-ответа модели."""

    def __init__(self, ok: bool, reason: Optional[str] = None):
        self.ok = ok
        self.reason = reason

    def __bool__(self):
        return self.ok

    def __repr__(self):
        return f"<ValidationResult ok={self.ok} reason={self.reason}>"


def _has_stopword(text: str) -> Optional[str]:
    low = (text or "").lower()
    for w in STOPWORDS:
        if w in low:
            return w
    return None


def _parse_insights(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    insights = payload.get("insights") or []
    if isinstance(insights, dict):
        insights = [insights]
    return [i for i in insights if isinstance(i, dict)]


def validate_insight(insight: Dict[str, Any]) -> ValidationResult:
    """Проверить одну неточность из списка insights[]."""
    title = (insight.get("title") or "").strip()
    what_went_wrong = (insight.get("what_went_wrong") or "").strip()
    itype = (insight.get("type") or "").strip()
    practice = insight.get("practice") or []

    # 1. title короче 15 символов — признак общей формулировки.
    if len(title) < MIN_TITLE_LEN:
        return ValidationResult(False, "title_too_short")

    # 2. Стоп-слова в title / what_went_wrong.
    for field_name, text in (("title", title), ("what_went_wrong", what_went_wrong)):
        w = _has_stopword(text)
        if w:
            return ValidationResult(False, f"stopword:{w}:{field_name}")

    # 3. type вне допустимого перечня.
    if itype not in INSIGHT_TYPES:
        return ValidationResult(False, "invalid_type")

    # 4. practice ровно 3 задачи.
    if not isinstance(practice, list) or len(practice) != 3:
        return ValidationResult(False, "practice_not_3")

    # 5. visibility образуют полный набор obvious/medium/hidden.
    vis = [p.get("visibility") for p in practice if isinstance(p, dict)]
    if sorted(vis) != sorted(VISIBILITIES):
        return ValidationResult(False, "visibility_incomplete")

    # 6. у задачи пустое why_this_task.
    for idx, p in enumerate(practice):
        if not isinstance(p, dict):
            return ValidationResult(False, "practice_item_not_dict")
        if not (p.get("why_this_task") or "").strip():
            return ValidationResult(False, f"empty_why_this_task:{idx}")

    return ValidationResult(True)


def validate_deep_result(payload: Dict[str, Any]) -> ValidationResult:
    """Проверить весь deep-ответ модели.

    Возвращает ValidationResult(ok=True), только если has_insight=true и хотя
    бы одна неточность прошла валидацию. Если has_insight=false — ok=False с
    reason="has_insight_false".
    """
    if not isinstance(payload, dict):
        return ValidationResult(False, "not_dict")

    has_insight = payload.get("has_insight", False)
    insights = _parse_insights(payload)

    if not has_insight:
        # skip_reason должен быть в допустимом перечне (иначе это мусор).
        skip_reason = payload.get("skip_reason")
        if skip_reason is not None and skip_reason not in SKIP_REASONS:
            return ValidationResult(False, "invalid_skip_reason")
        return ValidationResult(False, "has_insight_false")

    if not insights:
        return ValidationResult(False, "no_insights")

    for i, insight in enumerate(insights):
        r = validate_insight(insight)
        if not r.ok:
            return ValidationResult(False, f"insight[{i}]:{r.reason}")

    return ValidationResult(True)


def filter_valid_insights(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Вернуть только валидные неточности (для частично-валидного ответа)."""
    if not isinstance(payload, dict) or not payload.get("has_insight"):
        return []
    out = []
    for insight in _parse_insights(payload):
        if validate_insight(insight).ok:
            out.append(insight)
    return out
