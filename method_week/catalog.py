# -*- coding: utf-8 -*-
"""Выбор метода куратором + план методов на месяц.

Куратор здесь НЕ выдаёт задачи — он только решает, какой метод изучать,
исходя из результатов ученика (слабые разделы level_engine), его класса и
уровня. План на месяц (4–5 методов, по одному на неделю) хранится в
CuratorState.prep_state['method_plan']; в следующем месяце берутся уже
другие методы (пройденные попадают в covered).
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_CATALOG_PATH = os.path.join(
    os.path.dirname(__file__), '..', 'data', 'olympiads', 'methods_catalog_105.json',
)
_CATALOG_FALLBACK = os.path.join(
    os.path.dirname(__file__), '..', 'data', 'olympiads', 'methods_catalog_89.json',
)

# Раздел level_engine -> буквы разделов в каталоге методов
# (в каталоге: A — арифметика/текстовые, B — логика, C — алгебра,
#  D — теория чисел, E — комбинаторика, G — геометрия; на всякий случай
#  поддерживаем и буквы L/N из старого маппинга messenger.py).
SECTION_LETTERS: Dict[str, List[str]] = {
    'algebra': ['C', 'A'],
    'geometry': ['G'],
    'combinatorics': ['E'],
    'logic': ['B', 'L'],
    'number_theory': ['D', 'N'],
}
CANONICAL_SECTIONS = ('algebra', 'geometry', 'combinatorics', 'logic', 'number_theory')

SECTION_NAMES_RU = {
    'algebra': 'Алгебра',
    'geometry': 'Геометрия',
    'combinatorics': 'Комбинаторика',
    'logic': 'Логика',
    'number_theory': 'Теория чисел',
}

_catalog_cache: Optional[List[Dict[str, Any]]] = None


def load_catalog() -> List[Dict[str, Any]]:
    global _catalog_cache
    if _catalog_cache is not None:
        return _catalog_cache
    for path in (_CATALOG_PATH, _CATALOG_FALLBACK):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list) and data:
                _catalog_cache = data
                return data
        except Exception as exc:
            logger.warning("method_week: cannot load %s: %s", path, exc)
    _catalog_cache = []
    return _catalog_cache


def method_by_code(code: str) -> Optional[Dict[str, Any]]:
    for m in load_catalog():
        if m.get('method_code') == code:
            return m
    return None


def section_of_method(m: Dict[str, Any]) -> Optional[str]:
    letter = (m.get('section') or '').strip().upper()
    for sec, letters in SECTION_LETTERS.items():
        if letter in letters:
            return sec
    return None


# ─── Данные ученика ────────────────────────────────────────────────────

def user_grade(user_id: int) -> Optional[int]:
    try:
        from models_curator import CuratorState
        cs = CuratorState.query.filter_by(user_id=user_id).first()
        if cs and cs.grade:
            return int(cs.grade)
    except Exception:
        pass
    try:
        from models import User, db
        u = db.session.get(User, user_id)
        g = getattr(u, 'preferred_grade', None) or getattr(u, 'class_level', None)
        if g:
            return int(g)
    except Exception:
        pass
    return None


def user_level(user_id: int) -> int:
    """Уровень ученика 1..7 из level_engine (по умолчанию 2)."""
    try:
        from services.level_engine import get_state
        return max(1, min(7, int(round(float(get_state(user_id).get('mu', 2))))))
    except Exception:
        return 2


def level_to_difficulty(level: int) -> int:
    """Уровень 1..7 -> difficulty_level каталога 1..5."""
    return max(1, min(5, int(round(1 + (level - 1) * 4 / 6))))


def weakest_sections(user_id: int) -> List[str]:
    """Разделы от самого слабого к сильному (по mu level_engine)."""
    mus: Dict[str, float] = {}
    try:
        from services.level_engine import get_state
        by_section = get_state(user_id).get('by_section', {}) or {}
        for sec in CANONICAL_SECTIONS:
            d = by_section.get(sec, {}) if isinstance(by_section, dict) else {}
            try:
                n = int(d.get('n', 0) or 0)
                mu = float(d.get('mu', 3.0))
            except (TypeError, ValueError, AttributeError):
                n, mu = 0, 3.0
            # неизмеренные разделы — в середину, чтобы не считать их слабыми
            mus[sec] = mu if n > 0 else 2.5
    except Exception:
        mus = {sec: 2.5 for sec in CANONICAL_SECTIONS}
    return sorted(CANONICAL_SECTIONS, key=lambda s: (mus.get(s, 2.5), s))


# ─── План методов на месяц ─────────────────────────────────────────────

def _prep_state(cs) -> Dict[str, Any]:
    raw = getattr(cs, 'prep_state', None)
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            d = json.loads(raw)
            return d if isinstance(d, dict) else {}
        except Exception:
            return {}
    return {}


def weeks_in_month(d: date) -> int:
    first = d.replace(day=1)
    nxt = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
    days = (nxt - first).days
    return 5 if days > 28 else 4


def week_index_in_month(d: date) -> int:
    return min((d.day - 1) // 7, weeks_in_month(d) - 1)


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _pick_methods(user_id: int, grade: int, level: int, covered: set, count: int) -> List[Dict[str, Any]]:
    """Выбор методов: слабые разделы первыми, сложность около уровня ученика,
    не более 2 методов из одного раздела, пройденные исключаются."""
    catalog = [m for m in load_catalog()
               if grade in (m.get('grades') or []) and m.get('method_code') not in covered]
    if not catalog:
        catalog = [m for m in load_catalog() if m.get('method_code') not in covered]
    target_diff = level_to_difficulty(level)
    order = weakest_sections(user_id)
    rank = {sec: i for i, sec in enumerate(order)}

    def key(m):
        sec = section_of_method(m)
        sec_rank = rank.get(sec, len(order))
        diff_gap = abs(int(m.get('difficulty_level') or 3) - target_diff)
        freq = -int(m.get('frequency_vsosh_9') or 0)
        return (diff_gap > 1, sec_rank, diff_gap, freq, int(m.get('sort_order') or 999))

    chosen: List[Dict[str, Any]] = []
    per_section: Dict[str, int] = {}
    # 1-й проход: по одному методу из каждого раздела, начиная со слабых
    for sec in order:
        cands = sorted([m for m in catalog if section_of_method(m) == sec], key=key)
        if cands and len(chosen) < count:
            chosen.append(cands[0])
            per_section[sec] = 1
    # 2-й проход: добираем из самых слабых разделов (макс. 2 на раздел)
    for m in sorted(catalog, key=key):
        if len(chosen) >= count:
            break
        if m in chosen:
            continue
        sec = section_of_method(m) or '?'
        if per_section.get(sec, 0) >= 2:
            continue
        chosen.append(m)
        per_section[sec] = per_section.get(sec, 0) + 1
    return chosen[:count]


def get_or_build_month_plan(user_id: int, today: Optional[date] = None, force: bool = False) -> Dict[str, Any]:
    """План методов на текущий месяц. Создаёт новый при смене месяца."""
    from models import db
    from models_curator import CuratorState
    from sqlalchemy.orm.attributes import flag_modified

    today = today or date.today()
    month_key = today.strftime('%Y-%m')
    cs = CuratorState.query.filter_by(user_id=user_id).first()
    if cs is None:
        cs = CuratorState(user_id=user_id)
        db.session.add(cs)
        db.session.flush()
    ps = _prep_state(cs)
    plan = ps.get('method_plan') if isinstance(ps.get('method_plan'), dict) else {}
    covered = set(plan.get('covered') or [])

    if plan.get('month') == month_key and plan.get('methods') and not force:
        return plan

    # прошлый месяц закрыт -> его методы считаются пройденными
    if plan.get('methods'):
        covered |= set(plan.get('methods') or [])

    grade = user_grade(user_id) or 8
    level = user_level(user_id)
    n = weeks_in_month(today)
    methods = _pick_methods(user_id, grade, level, covered, n)
    if not methods and covered:
        # все методы класса пройдены — начинаем круг заново
        covered = set()
        methods = _pick_methods(user_id, grade, level, covered, n)

    weak2 = weakest_sections(user_id)[:2]
    new_plan = {
        'month': month_key,
        'grade': grade,
        'level': level,
        'methods': [m.get('method_code') for m in methods],
        'names': {m.get('method_code'): m.get('method_name') for m in methods},
        'sections': {m.get('method_code'): section_of_method(m) for m in methods},
        'reason': {
            m.get('method_code'): (
                "слабый раздел «%s»" % SECTION_NAMES_RU.get(section_of_method(m) or '', section_of_method(m) or '')
                if section_of_method(m) in weak2 else 'баланс разделов'
            ) for m in methods
        },
        'covered': sorted(covered),
    }
    ps['method_plan'] = new_plan
    cs.prep_state = ps
    flag_modified(cs, 'prep_state')
    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logger.error("method_week: plan commit failed user=%s: %s", user_id, exc)
    return new_plan


def week_set_method(user_id: int, today: Optional[date] = None) -> Optional[str]:
    """Код метода уже сохранённого недельного сета (если он есть).

    Сет — источник 3 дипсиковых задач: когда он создан, кнопка и блок
    задач на странице метода должны вести на его метод (на неделе,
    пересекающей границу месяца, план мог смениться после создания
    сета — задачи при этом остаются прежние).
    """
    try:
        from datetime import timedelta
        from method_week.models import MethodWeekSet
        today = today or date.today()
        ws = today - timedelta(days=today.weekday())
        s = MethodWeekSet.query.filter_by(user_id=user_id, week_start=ws).first()
        return (s.method_code if s and s.method_code else None)
    except Exception as e:  # noqa: BLE001
        logger.warning('[method_week] week_set_method failed: %r', e)
        return None


def method_for_week(user_id: int, today: Optional[date] = None) -> Optional[Dict[str, Any]]:
    """Метод текущей недели по плану куратора (+ описание из каталога)."""
    today = today or date.today()
    plan = get_or_build_month_plan(user_id, today)
    codes = plan.get('methods') or []
    if not codes:
        return None
    idx = min(week_index_in_month(today), len(codes) - 1)
    code = codes[idx]
    m = method_by_code(code) or {'method_code': code, 'method_name': plan.get('names', {}).get(code, code)}
    out = dict(m)
    out['section_slug'] = section_of_method(m)
    out['section_ru'] = SECTION_NAMES_RU.get(out['section_slug'] or '', '')
    out['week_index'] = idx
    out['reason'] = (plan.get('reason') or {}).get(code, '')
    return out


def mark_covered(user_id: int, code: str) -> None:
    try:
        from models import db
        from models_curator import CuratorState
        from sqlalchemy.orm.attributes import flag_modified
        cs = CuratorState.query.filter_by(user_id=user_id).first()
        if not cs:
            return
        ps = _prep_state(cs)
        plan = ps.get('method_plan') or {}
        covered = set(plan.get('covered') or [])
        covered.add(code)
        plan['covered'] = sorted(covered)
        ps['method_plan'] = plan
        cs.prep_state = ps
        flag_modified(cs, 'prep_state')
        db.session.commit()
    except Exception as exc:
        logger.warning("method_week: mark_covered failed: %s", exc)
