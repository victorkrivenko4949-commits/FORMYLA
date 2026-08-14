# -*- coding: utf-8 -*-
"""
services/bank_daily.py — выдача задач дня из предзаполненного банка.

Банк daily_task_bank наполняет человек (132 подтемы x 5 уровней x 35 задач).
Этот модуль НЕ генерирует задачи и не обращается к внешним моделям: только
SQLAlchemy-чтение daily_task_bank и запись в bank_issues.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func

from models import db, DailyTaskBank, BankIssue
from services.curator_plan_service import get_active_subtopics

logger = logging.getLogger(__name__)

# Раскладка месяца: неделя 1 — одна подтема и 5 задач,
# недели 2, 3, 4 — по две подтемы и 10 задач.
WEEK_TOPIC_COUNTS: Tuple[int, int, int, int] = (1, 2, 2, 2)
TASKS_PER_SUBTOPIC = 5

CANONICAL_SECTIONS = ("algebra", "number_theory", "geometry", "combinatorics", "logic")

_SECTION_ALIASES: Dict[str, str] = {
    "алгебра": "algebra",
    "алгебра и анализ": "algebra",
    "арифметика": "algebra",
    "текстовые задачи": "algebra",
    "геометрия": "geometry",
    "комбинаторика": "combinatorics",
    "логика": "logic",
    "логика и методы": "logic",
    "логика и игры": "logic",
    "теория чисел": "number_theory",
}


def _section_for_subtopic(subtopic: str) -> str:
    """Определить раздел подтемы по slug.

    Порядок: подтема сама по себе канонический раздел; подтема входит в
    data/theme_to_section.json как theme_id; иначе угадывание по префиксу
    латинских ключей подтем из таксономии. Fallback — 'algebra' (значение
    по умолчанию для неклассифицируемого slug, как в старых движках).
    """
    s = (subtopic or "").strip().lower()
    if not s:
        return "algebra"

    if s in CANONICAL_SECTIONS:
        return s
    if s in _SECTION_ALIASES:
        return _SECTION_ALIASES[s]

    try:
        from services.theme_registry import section_of_theme
        sec = section_of_theme(s)
        if sec in CANONICAL_SECTIONS:
            return sec
    except Exception:
        pass

    # Эвристика по префиксу латинских ключей подтем (topic_taxonomy.py).
    prefixes = (
        ("geometry", ("geometry", "grid_", "cutting_", "tiling_", "angle",
                      "triangle", "circle", "area_", "perimeter", "vector",
                      "stereometry", "polygon", "quadrilateral")),
        ("number_theory", ("number_theory", "divisibility", "remainder",
                           "gcd", "lcm", "prime", "coprime", "modular",
                           "diophantine", "last_digit", "parity", "digit",
                           "cryptarithmetic")),
        ("combinatorics", ("combinatorics", "counting_", "pigeonhole",
                           "graph_", "weighing", "pouring", "tiling",
                           "invariant", "invariants")),
        ("logic", ("logic", "knights", "liars", "deduction", "paradox",
                   "strategy", "games")),
        ("algebra", ("algebra", "equation", "inequalit", "function",
                     "polynomial", "quadratic", "linear", "expression",
                     "motion", "work_", "reverse", "fraction", "percent",
                     "proportion", "sequence", "series", "system")),
    )
    for section, keys in prefixes:
        if any(s.startswith(k) for k in keys):
            return section
    return "algebra"


def user_level(user_id: int, subtopic: str) -> int:
    """Уровень ученика по разделу подтемы: round(mu) зажатый в 1..5.

    Только читает механику mu. Профиля нет — уровень 3 (DEFAULT_MU).
    """
    section = _section_for_subtopic(subtopic)
    try:
        from services.level_engine import get_state
        state = get_state(user_id)
    except Exception as _exc:
        logger.warning("user_level: level_engine.get_state failed: %s", _exc)
        return 3

    by_section = state.get("by_section", {}) or {}
    sec_data = by_section.get(section) if isinstance(by_section, dict) else None
    mu = None
    if isinstance(sec_data, dict):
        try:
            mu = float(sec_data.get("mu"))
        except (TypeError, ValueError):
            mu = None
    if mu is None:
        try:
            mu = float(state.get("mu", 3.0))
        except (TypeError, ValueError):
            mu = 3.0

    return max(1, min(5, int(round(mu))))


def _issued_task_ids(user_id: int) -> set:
    """Все task_id из daily_task_bank, уже выданные этому ученику."""
    rows = (
        db.session.query(BankIssue.task_id)
        .filter(BankIssue.user_id == user_id)
        .all()
    )
    return {int(r[0]) for r in rows if r[0] is not None}


def _bank_has_rows() -> bool:
    return db.session.query(func.count(DailyTaskBank.id)).scalar() > 0


def pick_tasks(user_id: int, subtopic: str, level: int, count: int):
    """Вернуть задачи из daily_task_bank по паре подтема-уровень.

    Порядок детерминированно перемешан по ученику: сортировка по
    md5(str(user_id) + ':' + str(task_id)), взять первые count.
    Уже выданные (bank_issues) исключаются.
    Возвращает (список DailyTaskBank, bank_exhausted: bool).
    """
    level = max(1, min(5, int(level)))
    issued = _issued_task_ids(user_id)

    candidates = (
        DailyTaskBank.query
        .filter_by(subtopic=subtopic, level=level)
        .all()
    )

    fresh = [t for t in candidates if t.id not in issued]

    if candidates and not fresh:
        # Задачи есть, но ученик видел все -> нужен более глубокий запас.
        return [], True

    def _sort_key(task: DailyTaskBank) -> str:
        return hashlib.md5(f"{user_id}:{task.id}".encode("utf-8")).hexdigest()

    fresh.sort(key=_sort_key)
    return fresh[:count], False


def _week_number(target_date: date, anchor: Optional[date]) -> int:
    """Номер недели внутри месяца (1..4) по 28-дневному циклу от anchor."""
    if anchor is None:
        anchor = target_date
    days = max(0, (target_date - anchor).days)
    return (days // 7) % 4 + 1


def _subtopics_for_week(assignments: List[Any], week_number: int) -> List[str]:
    """Взять подтемы недели по раскладке (1/2/2/2) из семи подтем месяца."""
    subs = [str(a.subtopic) for a in assignments]
    if not subs:
        return []

    starts = []
    cursor = 0
    for c in WEEK_TOPIC_COUNTS:
        starts.append(cursor)
        cursor += c

    start = starts[week_number - 1]
    count = WEEK_TOPIC_COUNTS[week_number - 1]
    # Если план неполный — берём столько, сколько реально есть подряд.
    return subs[start:start + count]


def _existing_issues_for_date(user_id: int, target_date: date) -> Dict[int, List[int]]:
    """{subtopic_index: [task_id]} для уже выданных задач на дату.

    Ключ — порядковый номер подтемы в выдаче дня (не ID подтемы).
    """
    issues = (
        BankIssue.query
        .filter_by(user_id=user_id, issued_date=target_date)
        .all()
    )
    # Восстанавливаем порядок по subtopic: группируем task_id по subtopic,
    # но для идемпотентности важен детерминированный порядок подтем недели.
    return issues


def build_daily_set(user_id: int, target_date: date) -> Dict[str, Any]:
    """Собрать набор задач дня для ученика и даты.

    Возвращает dict с ключами:
        items: list[DailyTaskBank],
        plan_missing: bool,
        bank_exhausted: bool,
        bank_empty: bool,
        week_number: int,
        subtopics: list[str],
    Идемпотентно: повторный вызов на ту же дату возвращает тот же набор
    и не создаёт новых строк в bank_issues.
    """
    bank_empty = not _bank_has_rows()

    assignments, status = get_active_subtopics(user_id)
    if status.get("plan_missing") or not assignments:
        logger.warning("build_daily_set: user=%d date=%s план на месяц не задан",
                       user_id, target_date)
        return {
            "items": [],
            "plan_missing": True,
            "bank_exhausted": False,
            "bank_empty": bank_empty,
            "week_number": None,
            "subtopics": [],
        }

    # Номер недели от anchor-даты плана (get_active_subtopics отдаёт месяц,
    # но anchor живёт в curator_state.prep_plan / monthly_plan).
    try:
        from daily_tasks.monthly_plan import get_or_build_plan
        from models_curator import CuratorState
        cs = CuratorState.query.filter_by(user_id=user_id).first()
        if cs is not None:
            plan = get_or_build_plan(cs, getattr(cs, "grade", None) or 1, target_date)
            anchor_raw = plan.get("anchor_date") if isinstance(plan, dict) else None
            anchor = date.fromisoformat(str(anchor_raw)) if anchor_raw else None
        else:
            anchor = None
    except Exception:
        anchor = None

    week_number = _week_number(target_date, anchor)
    week_subtopics = _subtopics_for_week(assignments, week_number)

    if not week_subtopics:
        logger.warning("build_daily_set: user=%d date=%s неделя %d не дала подтем",
                       user_id, target_date, week_number)
        return {
            "items": [],
            "plan_missing": True,
            "bank_exhausted": False,
            "bank_empty": bank_empty,
            "week_number": week_number,
            "subtopics": [],
        }

    # Идемпотентность: проверяем уже выданные записи на эту дату.
    prior = (
        BankIssue.query
        .filter_by(user_id=user_id, issued_date=target_date)
        .order_by(BankIssue.id.asc())
        .all()
    )
    if prior:
        task_ids = [int(p.task_id) for p in prior]
        tasks = (
            DailyTaskBank.query
            .filter(DailyTaskBank.id.in_(task_ids))
            .all()
        )
        by_id = {t.id: t for t in tasks}
        ordered = [by_id[tid] for tid in task_ids if tid in by_id]
        logger.info("build_daily_set: user=%d date=%s повторный вызов, отдаём %d задач",
                    user_id, target_date, len(ordered))
        return {
            "items": ordered,
            "plan_missing": False,
            "bank_exhausted": False,
            "bank_empty": bank_empty,
            "week_number": week_number,
            "subtopics": week_subtopics,
        }

    bank_exhausted = False
    items: List[DailyTaskBank] = []
    for subtopic in week_subtopics:
        level = user_level(user_id, subtopic)
        tasks, exhausted = pick_tasks(user_id, subtopic, level, TASKS_PER_SUBTOPIC)
        items.extend(tasks)
        if exhausted:
            bank_exhausted = True

    # Записываем выданное в bank_issues.
    for task in items:
        db.session.add(BankIssue(
            user_id=user_id,
            task_id=task.id,
            subtopic=task.subtopic,
            level=task.level,
            issued_date=target_date,
        ))
    db.session.commit()

    return {
        "items": items,
        "plan_missing": False,
        "bank_exhausted": bank_exhausted,
        "bank_empty": bank_empty,
        "week_number": week_number,
        "subtopics": week_subtopics,
    }


def bank_stats(subtopic: Optional[str] = None, level: Optional[int] = None) -> Dict[str, Any]:
    """Статистика банка для проверки заливки человеком.

    Без аргументов — по всему банку. С аргументами — по одной паре
    плюс сколько задач пары ещё никем не выдано.
    """
    q = db.session.query(DailyTaskBank)
    if subtopic is not None:
        q = q.filter(DailyTaskBank.subtopic == subtopic)
    if level is not None:
        q = q.filter(DailyTaskBank.level == level)

    total = q.count()
    pairs = (
        db.session.query(DailyTaskBank.subtopic, DailyTaskBank.level)
        .distinct()
        .count()
    ) if subtopic is None and level is None else None

    solution_count = q.filter(DailyTaskBank.solution.isnot(None), DailyTaskBank.solution != "").count()
    svg_count = q.filter(DailyTaskBank.svg_path.isnot(None), DailyTaskBank.svg_path != "").count()
    figure_count = q.filter(DailyTaskBank.needs_figure.is_(True)).count()

    stats: Dict[str, Any] = {
        "total": total,
        "solution_nonempty": solution_count,
        "svg_nonempty": svg_count,
        "needs_figure": figure_count,
    }
    if pairs is not None:
        stats["pairs_filled"] = pairs

    if subtopic is not None and level is not None:
        issued = (
            db.session.query(func.count(BankIssue.id))
            .join(DailyTaskBank, BankIssue.task_id == DailyTaskBank.id)
            .filter(DailyTaskBank.subtopic == subtopic, DailyTaskBank.level == level)
            .scalar()
        )
        stats["issued_anywhere"] = int(issued or 0)
        stats["not_issued_anywhere"] = total - int(issued or 0)

    return stats
