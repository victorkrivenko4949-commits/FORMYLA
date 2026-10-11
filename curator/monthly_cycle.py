# -*- coding: utf-8 -*-
"""
curator/monthly_cycle.py — Monthly preparation cycle (new version).

Month = cycle. 7 themes per cycle, one theme per day in round-robin.

Key concepts:
  - 7 themes per cycle
  - level_by_theme records mu per theme_id
  - monthly_cycle in prep_state tracks progress

Rollover safety (2026-10-11): selection of next-month themes must NEVER
raise. Previously _select_subsequent_cycle_themes could pick 3-4 themes
from one section, the CYCLE GUARD raised RuntimeError inside
get_cycle_info, callers swallowed it and /daily_tasks showed
«Задач пока нет». Now: max 2 themes per section when picking from weak
sections, and _safe_next_themes falls back to a simple section-diverse
selection on any error. If no themes remain, the current themes keep
rotating instead of returning current_theme=None.
"""
import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from models import db, User
from models_curator import CuratorState

logger = logging.getLogger(__name__)

# ─── Constants ──────────────────────────────────────────────────────────

ACTIVE_DAYS = 7
MONTH_DAYS = 31
THEME_DAYS = 1
REVIEW_DAYS = 3
MAX_PER_SECTION = 2
CANONICAL_SECTIONS = ('algebra', 'geometry', 'combinatorics', 'logic', 'number_theory')

# ─── Prep state helpers ─────────────────────────────────────────────────


def _default_monthly_cycle() -> Dict[str, Any]:
    return {
        'started_at': None,
        'themes': [],
        'day_index': 1,
        'done_themes': [],
        'finished_at': None,
        'covered_themes': [],
    }


def _prep_state_dict(cs: CuratorState) -> Dict[str, Any]:
    raw = getattr(cs, 'prep_state', None)
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
    return {}


def _get_monthly_cycle(cs: CuratorState) -> Dict[str, Any]:
    ps = _prep_state_dict(cs)
    mc = ps.get('monthly_cycle')
    if not isinstance(mc, dict) or not mc.get('themes'):
        return _default_monthly_cycle()
    return mc


def _save_monthly_cycle(cs: CuratorState, mc: Dict[str, Any]):
    from sqlalchemy.orm.attributes import flag_modified
    ps = _prep_state_dict(cs)
    ps['monthly_cycle'] = mc
    cs.prep_state = ps
    flag_modified(cs, 'prep_state')


# ─── Theme selection ────────────────────────────────────────────────────


def _t_number(tid: str) -> int:
    try:
        for p in tid.split('_'):
            if p.startswith('T') and p[1:].isdigit():
                return int(p[1:])
    except Exception:
        pass
    return 999


def _section_aware_extras(all_grade_themes, selected, grade, section_order,
                          section_mus=None, max_per_section=MAX_PER_SECTION):
    from services.theme_registry import section_of_theme, themes_of_section

    section_counts: Dict[str, int] = {}
    for tid in selected:
        sec = section_of_theme(tid) or ''
        section_counts[sec] = section_counts.get(sec, 0) + 1

    needed = 7 - len(selected)
    if needed <= 0:
        return selected

    def section_priority(sec):
        if section_mus:
            return section_mus.get(sec, 3.0)
        return 0

    sorted_sections = sorted(CANONICAL_SECTIONS, key=lambda s: (section_priority(s), s))

    allowed = set(all_grade_themes)
    extra_count = 0
    while extra_count < needed:
        picked_this_round = False
        for sec in sorted_sections:
            if extra_count >= needed:
                break
            if section_counts.get(sec, 0) >= max_per_section:
                continue
            sec_themes = [t for t in themes_of_section(grade, sec) if t in allowed]
            if not sec_themes:
                continue
            sec_themes.sort(key=_t_number)
            for t in sec_themes:
                if t not in selected:
                    selected.append(t)
                    section_counts[sec] = section_counts.get(sec, 0) + 1
                    extra_count += 1
                    picked_this_round = True
                    break
        if not picked_this_round:
            break

    return selected


def _validate_selection(selected: List[str], grade: int) -> None:
    from services.theme_registry import section_of_theme
    grade_prefix = f"G{grade}_"
    for tid in selected:
        if not tid.startswith(grade_prefix):
            raise RuntimeError(
                f"GRADE GUARD: theme {tid} does not start with {grade_prefix} (grade={grade})"
            )
    sec_counts: Dict[str, int] = {}
    for tid in selected:
        sec = section_of_theme(tid) or '?'
        sec_counts[sec] = sec_counts.get(sec, 0) + 1
    for sec, cnt in sec_counts.items():
        if cnt > MAX_PER_SECTION:
            raise RuntimeError(
                f"CYCLE GUARD: section '{sec}' has {cnt} themes (max {MAX_PER_SECTION}). Selected: {selected}"
            )


def _select_first_cycle_themes(grade: int) -> List[str]:
    from services.theme_registry import themes_of_section, themes_of_grade

    all_grade_themes = themes_of_grade(grade)
    if not all_grade_themes:
        return []

    selected: List[str] = []
    for section in CANONICAL_SECTIONS:
        sec_themes = themes_of_section(grade, section)
        if not sec_themes:
            continue
        sec_themes.sort(key=_t_number)
        selected.append(sec_themes[0])

    _section_aware_extras(all_grade_themes, selected, grade, CANONICAL_SECTIONS, section_mus=None)
    _validate_selection(selected, grade)
    return selected[:7]


def _select_subsequent_cycle_themes(user_id: int, grade: int,
                                    exclude: Optional[set] = None) -> List[str]:
    """Up to 7 themes for subsequent cycles, strictly within the grade.

    Rule: up to 4 from the weakest sections (max 2 per section), rest with
    section diversity. Themes in ``exclude`` are never reused.
    """
    from services.theme_registry import themes_of_grade, themes_of_section, section_of_theme
    from services.level_engine import get_state as _get_level_state

    exclude = set(exclude or ())
    grade_themes = [t for t in themes_of_grade(grade) if t not in exclude]
    if not grade_themes:
        return []

    cs = CuratorState.query.filter_by(user_id=user_id).first()
    measured_themes: Dict[str, float] = {}
    if cs and cs.level_by_theme:
        try:
            lbt = json.loads(cs.level_by_theme) if isinstance(cs.level_by_theme, str) else cs.level_by_theme
            measured_themes = {k: float(v.get('mu', 3)) for k, v in lbt.items() if isinstance(v, dict)}
        except (json.JSONDecodeError, TypeError, ValueError, AttributeError):
            pass

    section_mus: Dict[str, float] = {}
    try:
        by_section = _get_level_state(user_id).get('by_section', {}) or {}
    except Exception:
        by_section = {}
    for sec in CANONICAL_SECTIONS:
        sec_data = by_section.get(sec, {}) if isinstance(by_section, dict) else {}
        try:
            section_mus[sec] = float(sec_data.get('mu', 3.0))
        except (TypeError, ValueError, AttributeError):
            section_mus[sec] = 3.0

    weakest_sections = sorted(CANONICAL_SECTIONS, key=lambda s: section_mus.get(s, 3.0))

    selected: List[str] = []
    section_counts: Dict[str, int] = {}
    needed_from_weak = 4
    for sec in weakest_sections:
        if len(selected) >= needed_from_weak:
            break
        sec_themes = [t for t in themes_of_section(grade, sec) if t not in exclude]
        sec_themes.sort(key=lambda t: measured_themes.get(t, 5.0))
        for t in sec_themes:
            if len(selected) >= needed_from_weak:
                break
            if section_counts.get(sec, 0) >= MAX_PER_SECTION:
                break
            if t not in selected:
                selected.append(t)
                section_counts[sec] = section_counts.get(sec, 0) + 1

    _section_aware_extras(grade_themes, selected, grade, CANONICAL_SECTIONS, section_mus=section_mus)
    _validate_selection(selected, grade)
    return selected[:7]


def _simple_diverse_themes(grade: int, covered: set) -> List[str]:
    """Fallback selection without level data: one per section, then the rest."""
    from services.theme_registry import themes_of_grade, section_of_theme

    remaining = [t for t in themes_of_grade(grade) if t not in covered]
    remaining.sort(key=_t_number)
    if len(remaining) <= 7:
        return remaining
    selected: List[str] = []
    counts: Dict[str, int] = {}
    for _round in range(MAX_PER_SECTION):
        for sec in CANONICAL_SECTIONS:
            if len(selected) >= 7:
                break
            for t in remaining:
                if t in selected or (section_of_theme(t) or '?') != sec:
                    continue
                if counts.get(sec, 0) > _round:
                    break
                selected.append(t)
                counts[sec] = counts.get(sec, 0) + 1
                break
    for t in remaining:
        if len(selected) >= 7:
            break
        if t not in selected:
            selected.append(t)
    return selected[:7]


def _safe_next_themes(user_id: int, grade: int, covered: set) -> List[str]:
    """Themes for the next month. Never raises.

    < 7 remaining -> all remaining (final month). Otherwise weakness-based
    selection; on any error -> simple section-diverse fallback.
    """
    try:
        from services.theme_registry import themes_of_grade
        remaining = [t for t in themes_of_grade(grade) if t not in covered]
    except Exception as exc:
        logger.error("monthly_cycle: themes_of_grade failed grade=%s: %s", grade, exc)
        return []
    if not remaining:
        return []
    if len(remaining) < 7:
        return sorted(remaining, key=_t_number)
    try:
        themes = _select_subsequent_cycle_themes(user_id, grade, exclude=covered)
        if themes:
            return themes
    except Exception as exc:
        logger.warning("monthly_cycle: weakness selection failed user=%s grade=%s: %s — fallback",
                       user_id, grade, exc)
    try:
        return _simple_diverse_themes(grade, covered)
    except Exception as exc:
        logger.error("monthly_cycle: fallback selection failed user=%s: %s", user_id, exc)
        return sorted(remaining, key=_t_number)[:7]


def _next_month_themes(user_id: int, grade: int, covered: set) -> List[str]:
    return _safe_next_themes(user_id, grade, covered)


def build_or_get_cycle(user_id: int, grade: int, force_new: bool = False) -> Dict[str, Any]:
    cs = CuratorState.query.filter_by(user_id=user_id).first()
    if not cs:
        cs = CuratorState(user_id=user_id)
        db.session.add(cs)
        db.session.commit()

    mc = _get_monthly_cycle(cs)
    covered = set(mc.get('covered_themes') or [])

    if mc.get('themes') and mc.get('finished_at') and not force_new:
        covered |= set(mc.get('themes') or [])
        next_themes = _safe_next_themes(user_id, grade, covered)
        if next_themes:
            mc = {
                'started_at': datetime.now(timezone.utc).isoformat(),
                'themes': next_themes,
                'day_index': 1,
                'done_themes': [],
                'finished_at': None,
                'covered_themes': sorted(covered),
            }
            _save_monthly_cycle(cs, mc)
            db.session.commit()
            return mc
        return mc

    if mc.get('themes') and not force_new:
        return mc

    had_prev = bool(mc.get('finished_at')) or bool(mc.get('done_themes')) or bool(covered)
    themes: List[str] = []
    if had_prev:
        themes = _safe_next_themes(user_id, grade, covered)
    if not themes:
        try:
            themes = _select_first_cycle_themes(grade)
        except Exception as exc:
            logger.warning("monthly_cycle: first-cycle selection failed grade=%s: %s — fallback", grade, exc)
            themes = _simple_diverse_themes(grade, set())

    mc = {
        'started_at': datetime.now(timezone.utc).isoformat(),
        'themes': themes,
        'day_index': 1,
        'done_themes': [],
        'finished_at': None,
        'covered_themes': sorted(covered),
    }
    _save_monthly_cycle(cs, mc)
    db.session.commit()

    try:
        _on_cycle_activated(user_id)
    except Exception:
        pass

    return mc


# ─── Public API ─────────────────────────────────────────────────────────


def _compute_day_index(started_at_iso: Optional[str], themes_count: int = 0) -> int:
    if not started_at_iso:
        return 1
    try:
        started_date = date.fromisoformat(started_at_iso[:10])
        delta = (date.today() - started_date).days
        if delta < 0:
            return 1
        return delta + 1
    except Exception:
        return 1


def _grade_for_user(user_id: int, cs: CuratorState) -> Optional[int]:
    g = getattr(cs, 'grade', None)
    if g:
        try:
            return int(g)
        except (TypeError, ValueError):
            pass
    try:
        user = User.query.get(user_id)
        if user:
            g = getattr(user, 'preferred_grade', None) or getattr(user, 'class_level', None)
            if g:
                return int(g)
    except Exception:
        pass
    try:
        ps = _prep_state_dict(cs)
        intake = ps.get('intake') or ps.get('onboarding') or {}
        g = intake.get('class_level') or intake.get('grade') if isinstance(intake, dict) else None
        if g:
            return int(g)
    except Exception:
        pass
    return None


def _order_themes_worst_first(user_id: int, themes: List[str]) -> List[str]:
    from services.level_engine import get_level_by_theme

    try:
        lbt = get_level_by_theme(user_id) or {}
    except Exception:
        lbt = {}

    def sort_key(t: str):
        entry = lbt.get(t)
        mu = entry.get('mu') if isinstance(entry, dict) else None
        try:
            mu = float(mu) if mu is not None else None
        except (TypeError, ValueError):
            mu = None
        if mu is None:
            return (1, 0.0)
        return (0, mu)

    return sorted(themes, key=sort_key)


def _worst_themes(user_id: int, themes: List[str], k: int = REVIEW_DAYS) -> List[str]:
    return _order_themes_worst_first(user_id, themes)[:k]


def _cycle_payload(mc: Dict[str, Any], themes: List[str], done: List[str],
                   day_idx: int, finished: bool, current_theme: Optional[str]) -> Dict[str, Any]:
    return {
        'active': True,
        'started_at': mc.get('started_at'),
        'day_index': day_idx,
        'themes': themes,
        'done_themes': done,
        'finished': finished,
        'current_theme': current_theme,
        'blocked': False,
    }


def get_cycle_info(user_id: int) -> Dict[str, Any]:
    """Current cycle status. Never raises; always yields a current_theme
    while the user has at least one theme in the cycle."""
    cs = CuratorState.query.filter_by(user_id=user_id).first()
    if not cs:
        return {'active': False}

    mc = _get_monthly_cycle(cs)
    themes = list(mc.get('themes', []) or [])
    if not themes:
        return {'active': False}

    done = list(mc.get('done_themes', []) or [])
    day_idx = _compute_day_index(mc.get('started_at'))

    if day_idx > MONTH_DAYS:
        grade = _grade_for_user(user_id, cs)
        covered = set(mc.get('covered_themes') or []) | set(themes)
        next_themes = _safe_next_themes(user_id, grade, covered) if grade else []
        if next_themes:
            try:
                mc = {
                    'started_at': datetime.now(timezone.utc).isoformat(),
                    'themes': next_themes,
                    'day_index': 1,
                    'done_themes': [],
                    'finished_at': None,
                    'covered_themes': sorted(covered),
                }
                _save_monthly_cycle(cs, mc)
                db.session.commit()
                themes, done, day_idx = next_themes, [], 1
            except Exception as exc:
                db.session.rollback()
                logger.error("monthly_cycle: rollover save failed user=%s: %s — keep rotating", user_id, exc)
        else:
            # Все темы класса пройдены (или класс неизвестен): продолжаем
            # крутить темы текущего месяца, чтобы задачи дня не пропадали.
            try:
                if not mc.get('finished_at'):
                    mc['finished_at'] = datetime.now(timezone.utc).isoformat()
                    _save_monthly_cycle(cs, mc)
                    db.session.commit()
            except Exception:
                db.session.rollback()
            current_theme = themes[(day_idx - 1) % len(themes)]
            return _cycle_payload(mc, themes, done, day_idx, True, current_theme)

    current_theme = themes[(day_idx - 1) % len(themes)]
    return _cycle_payload(mc, themes, done, day_idx, False, current_theme)


def advance_day(user_id: int) -> Dict[str, Any]:
    cs = CuratorState.query.filter_by(user_id=user_id).first()
    if not cs:
        return {'error': 'no_state'}

    mc = _get_monthly_cycle(cs)
    day_idx = _compute_day_index(mc.get('started_at'))
    themes = mc.get('themes', [])
    done = list(mc.get('done_themes', []))

    if day_idx > MONTH_DAYS:
        return {'error': 'cycle_already_done'}

    if len(themes) > 0 and day_idx <= ACTIVE_DAYS:
        current_theme = themes[(day_idx - 1) % len(themes)]
        if current_theme and current_theme not in done:
            done.append(current_theme)

    mc['done_themes'] = done
    _save_monthly_cycle(cs, mc)
    db.session.commit()

    return {
        'day_index': day_idx,
        'done_count': len(done),
        'finished': False,
        'current_theme': None,
    }


def get_today_info(user_id: int) -> Dict[str, Any]:
    info = get_cycle_info(user_id)
    if not info.get('active'):
        return {}

    current_theme = info.get('current_theme')
    if not current_theme:
        return {}

    from services.theme_registry import theme_title as _theme_title

    subtopic_title = _theme_title(current_theme)
    is_test_day = info.get('blocked', False)
    tested = current_theme in info.get('done_themes', [])

    has_tasks = False
    try:
        from daily_tasks.models import DailyTaskSet
        has_tasks = DailyTaskSet.query.filter_by(
            user_id=user_id, target_date=date.today()
        ).first() is not None
    except Exception:
        pass

    level = 2
    try:
        from services.level_engine import get_state as _get_level_state
        level = max(1, min(7, int(_get_level_state(user_id).get('mu', 2))))
    except Exception:
        pass

    return {
        'subtopic': current_theme,
        'subtopic_title': subtopic_title,
        'is_test_day': is_test_day,
        'tested': tested,
        'has_tasks': has_tasks,
        'level': level,
    }


def generate_tasks_only(user_id: int, subtopic: str = None) -> Dict[str, Any]:
    level = 2
    try:
        from services.level_engine import get_state as _get_level_state
        level = max(1, min(7, int(_get_level_state(user_id).get('mu', 2))))
    except Exception:
        pass

    if subtopic is None:
        info = get_today_info(user_id)
        subtopic = info.get('subtopic', '')

    return {
        'success': False,
        'subtopic': subtopic,
        'level': level,
        'generation_queued': False,
        'message': 'AI-генерация задач дня отключена (выдача из банка)',
    }


def _on_cycle_activated(user_id: int) -> bool:
    return False
