# -*- coding: utf-8 -*-
"""
daily_tasks/monthly_plan.py - Monthly subtopic plan (Step 1, new system).

Идея новой системы:
* Обучение разбито на МЕСЯЦА, в каждом месяце ровно 7 ПОДТЕМ.
* Задачи дня генерируются по ОДНОЙ ПОДТЕМЕ (а не по теме): все 10 задач
  дня принадлежат одной подтеме текущего месяца, выбранной детерминированным
  календарём.

План хранится в CuratorState.prep_plan (JSON):
    {
      "version": 1,
      "anchor_date": "2026-06-29",
      "subtopics_per_month": 7,
      "months": [
        {"index": 1, "subtopics": ["pigeonhole_basic", ... 7 шт]},
        ...
      ]
    }
"""

import logging
from datetime import date
from typing import Any, Dict, List, Optional

from services.topic_taxonomy import SUBTOPICS, SUBTOPIC_NAMES_RU
from services.adaptive_topics_registry import ADAPTIVE_TOPICS_BY_GRADE

logger = logging.getLogger(__name__)

SUBTOPICS_PER_MONTH = 7
PLAN_VERSION = 1


def _ordered_subtopics_for_grade(grade: int) -> List[str]:
    """Вернуть упорядоченный плоский список slug-ов подтем для класса.

    Для 5-6 кл. берём SUBTOPICS (тема -> список подтем).
    Для 7-11 кл. берём subtopics из ADAPTIVE_TOPICS_BY_GRADE.
    Порядок тем сохраняется, подтемы идут подряд внутри темы.
    Дубликаты убираются с сохранением первого вхождения.
    """
    ordered: List[str] = []
    seen = set()

    def _add(slug: str) -> None:
        if slug and slug not in seen:
            ordered.append(slug)
            seen.add(slug)

    if grade is not None and int(grade) >= 7:
        for entry in ADAPTIVE_TOPICS_BY_GRADE.get(int(grade), []):
            for sub in (entry.get("subtopics") or []):
                _add(str(sub))
    else:
        for theme, subs in SUBTOPICS.items():
            if isinstance(subs, dict):
                for k in (subs.get("topics", {}) or {}):
                    _add(str(k))
            elif isinstance(subs, list):
                for s in subs:
                    _add(str(s))
    return ordered


def build_monthly_plan(grade: int, anchor: Optional[date] = None, subtopics: Optional[List[str]] = None) -> Dict[str, Any]:
    """Построить помесячный план: подтемы класса нарезаются на месяцы по 7.

    Если передан ``subtopics`` — используется именно этот список подтем (ровно один месяц).
    Иначе подтемы берутся из _ordered_subtopics_for_grade(grade) и нарезаются на месяцы.
    Последний месяц может быть неполным (< 7 подтем), это допустимо.
    Возвращает dict, готовый для сохранения в CuratorState.prep_plan.
    """
    if anchor is None:
        anchor = date.today()
    if subtopics is not None:
        # Интеллектуальный подбор: куратор выбрал 7 слабых подтем → один месяц
        months: List[Dict[str, Any]] = [{
            "index": 1,
            "subtopics": subtopics,
        }]
    else:
        flat = _ordered_subtopics_for_grade(grade)
        months = []
        for i in range(0, len(flat), SUBTOPICS_PER_MONTH):
            chunk = flat[i:i + SUBTOPICS_PER_MONTH]
            months.append({
                "index": (i // SUBTOPICS_PER_MONTH) + 1,
                "subtopics": chunk,
            })
    return {
        "version": PLAN_VERSION,
        "anchor_date": anchor.isoformat(),
        "subtopics_per_month": SUBTOPICS_PER_MONTH,
        "grade": int(grade) if grade is not None else None,
        "months": months,
    }


def _flatten_plan_subtopics(plan: Dict[str, Any]) -> List[str]:
    """Собрать все подтемы плана в один плоский список (по порядку месяцев)."""
    flat: List[str] = []
    for month in (plan.get("months") or []):
        for sub in (month.get("subtopics") or []):
            flat.append(str(sub))
    return flat


def current_month_index(plan: Dict[str, Any], today: Optional[date] = None) -> int:
    """Номер текущего месяца обучения (1-based) по календарю от anchor_date.

    Месяц = 28 дней (4 недели). Циклически по числу месяцев плана.
    """
    months = plan.get("months") or []
    if not months:
        return 1
    if today is None:
        today = date.today()
    try:
        anchor = date.fromisoformat(str(plan.get("anchor_date")))
    except (TypeError, ValueError):
        anchor = today
    days = max(0, (today - anchor).days)
    return (days // 28) % len(months) + 1


def pick_day_subtopic(plan: Dict[str, Any], today: Optional[date] = None) -> Optional[str]:
    """Выбрать ПОДТЕМУ дня детерминированным календарём.

    В пределах текущего месяца берём подтему по индексу (дни % 7),
    чтобы за неделю пройти все 7 подтем месяца. Одна дата -> одна подтема.
    """
    months = plan.get("months") or []
    if not months:
        return None
    if today is None:
        today = date.today()
    try:
        anchor = date.fromisoformat(str(plan.get("anchor_date")))
    except (TypeError, ValueError):
        anchor = today
    days = max(0, (today - anchor).days)
    month = months[(days // 28) % len(months)]
    subs = month.get("subtopics") or []
    if not subs:
        return None
    return str(subs[days % len(subs)])


def subtopic_title(slug: str) -> str:
    """Русское название подтемы для UI/промпта (фолбэк на slug).

    Если slug имеет формат GX_TXX (theme_id из JSONL), делегирует
    в services.theme_registry.theme_title(), которая возвращает
    человеческое название из JSONL (например "Многочлены и алгебраические тождества").
    """
    if not slug:
        return slug
    # Detect GX_TXX pattern (e.g. G9_T05, G10_T01)
    if len(slug) >= 6 and slug[0] == 'G' and '_T' in slug:
        try:
            from services.theme_registry import theme_title as _theme_title
            title = _theme_title(slug)
            if title and title != slug:
                return title
        except Exception:
            pass
    return SUBTOPIC_NAMES_RU.get(slug, slug)


def parent_topic_for_subtopic(slug: str, grade: int) -> Optional[str]:
    """Найти родительскую тему (db_topic) для подтемы.

    Нужно, чтобы slot_planner взял level_window родительской темы из профиля.
    """
    if grade is not None and int(grade) >= 7:
        for entry in ADAPTIVE_TOPICS_BY_GRADE.get(int(grade), []):
            if slug in (entry.get("subtopics") or []):
                return entry.get("db_topic") or entry.get("key")
        return None
    for theme, subs in SUBTOPICS.items():
        if isinstance(subs, dict):
            if slug in (subs.get("topics", {}) or {}):
                return theme
        elif isinstance(subs, list):
            if slug in subs:
                return theme
    return None


def get_or_build_plan(curator_state: Any, grade: int, today: Optional[date] = None) -> Dict[str, Any]:
    """Вернуть валидный prep_plan из CuratorState, построив его при отсутствии.

    НЕ коммитит в БД сам — вызывающий код решает, сохранять ли обновлённый план.
    Возвращает (plan_dict). Если план был построен заново — записывает его
    в curator_state.prep_plan (в памяти).
    """
    plan = getattr(curator_state, "prep_plan", None) if curator_state else None
    valid = (
        isinstance(plan, dict)
        and plan.get("months")
        and plan.get("version") == PLAN_VERSION
    )
    if not valid:
        plan = build_monthly_plan(grade, anchor=today or date.today())
        if curator_state is not None:
            curator_state.prep_plan = plan
    return plan
