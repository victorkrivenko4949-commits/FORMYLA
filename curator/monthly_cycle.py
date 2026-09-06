# -*- coding: utf-8 -*-
"""
curator/monthly_cycle.py — Monthly preparation cycle (new version).

Month = cycle. Days 1-7: morning probe (5 tasks per subtopic), evening daily tasks.
Days 8+: daily tasks only. Daily tasks are BLOCKED until morning probe is completed.

Key concepts:
  - 7 subtopics per cycle, one per active day
  - Probe uses services/theme_probe.py ladder mechanism
  - level_by_theme records mu per theme_id
  - monthly_cycle in prep_state tracks progress
"""
import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from models import db, User
from models_curator import CuratorState

logger = logging.getLogger(__name__)

# ─── Constants ──────────────────────────────────────────────────────────

ACTIVE_DAYS = 7           # days with morning probes (legacy)
MONTH_DAYS = 31           # виртуальный месяц: всегда 31 день
THEME_DAYS = 4            # одна тема идёт 4 дня (7 тем × 4 = 28 дней)
REVIEW_DAYS = 3           # дни 29..31 — повтор 3 худших тем месяца
CANONICAL_SECTIONS = ('algebra', 'geometry', 'combinatorics', 'logic', 'number_theory')

# ─── Prep state helpers ─────────────────────────────────────────────────


def _default_monthly_cycle() -> Dict[str, Any]:
    return {
        'started_at': None,
        'themes': [],           # 7 theme_ids
        'day_index': 1,         # 1..7
        'done_themes': [],      # completed theme_ids
        'finished_at': None,
        'covered_themes': [],   # темы, уже пройденные в предыдущих месяцах
    }


def _get_monthly_cycle(cs: CuratorState) -> Dict[str, Any]:
    ps = cs.prep_state or {}
    mc = ps.get('monthly_cycle')
    if not isinstance(mc, dict) or not mc.get('themes'):
        return _default_monthly_cycle()
    return mc


def _save_monthly_cycle(cs: CuratorState, mc: Dict[str, Any]):
    from sqlalchemy.orm.attributes import flag_modified
    ps = dict(cs.prep_state) if cs.prep_state else {}
    ps['monthly_cycle'] = mc
    cs.prep_state = ps
    # JSON-колонка: без flag_modified SQLAlchemy не увидит изменения
    # вложенного словаря и НЕ запишет их при commit (done_themes терялся,
    # из-за чего срез после 5-й задачи начинался заново).
    flag_modified(cs, 'prep_state')


# ─── Theme selection ────────────────────────────────────────────────────


def _section_aware_extras(all_grade_themes, selected, grade, section_order,
                          section_mus=None, max_per_section=2):
    """Pick additional themes with section diversity constraint.

    Each extra must be from a different section; no section may exceed
    max_per_section (2) total themes in the final set.

    Args:
        all_grade_themes: list of all theme_ids for this grade
        selected: already selected themes
        grade: integer grade
        section_order: list of (section_slug, priority) tuples, sorted by priority
        section_mus: optional dict {section: mu} for weakness-based priority
        max_per_section: max themes per section (default 2)
    Returns: updated selected list (modified in place)
    """
    from services.theme_registry import section_of_theme, themes_of_section

    def t_number(tid):
        try:
            parts = tid.split('_')
            for p in parts:
                if p.startswith('T') and p[1:].isdigit():
                    return int(p[1:])
            return 999
        except Exception:
            return 999

    # Count current themes per section
    section_counts = {}
    for tid in selected:
        sec = section_of_theme(tid) or ''
        section_counts[sec] = section_counts.get(sec, 0) + 1

    # Need exactly 7 total
    needed = 7 - len(selected)
    if needed <= 0:
        return selected

    # Sort sections by priority (lower mu first, then alternating)
    # For sections with no mu data, use a high default
    def section_priority(sec):
        if section_mus:
            return section_mus.get(sec, 3.0)
        return 0

    sorted_sections = sorted(
        CANONICAL_SECTIONS,
        key=lambda s: (section_priority(s), s)
    )

    # Pick one from each eligible section, round-robin until done.
    # `all_grade_themes` — допустимый пул тем (в последующих месяцах
    # из него уже исключены ранее пройденные темы).
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
            # Pick the smallest T that's not already selected
            sec_themes.sort(key=t_number)
            for t in sec_themes:
                if t not in selected:
                    selected.append(t)
                    section_counts[sec] = section_counts.get(sec, 0) + 1
                    extra_count += 1
                    picked_this_round = True
                    break
        if not picked_this_round:
            # No more sections can accept themes
            break

    return selected


def _select_first_cycle_themes(grade: int) -> List[str]:
    """Select up to 7 themes for the FIRST cycle: one from each available section + extras.

    Themes are strictly scoped to the student's grade. Sections missing for this
    grade are skipped (not backfilled from other grades). If the grade has fewer
    than 7 themes, the cycle is simply shorter.

    П2: extras must come from DIFFERENT sections; no section may exceed 2 themes.
    """
    from services.theme_registry import themes_of_section, themes_of_grade

    all_grade_themes = themes_of_grade(grade)
    if not all_grade_themes:
        return []

    grade_prefix = f"G{grade}"

    def t_number(tid):
        try:
            # G10_T039_S0 -> 39
            parts = tid.split('_')
            for p in parts:
                if p.startswith('T') and p[1:].isdigit():
                    return int(p[1:])
            return 999
        except Exception:
            return 999

    selected = []

    # Step 1: one base theme from each available section
    for section in CANONICAL_SECTIONS:
        sec_themes = themes_of_section(grade, section)
        if not sec_themes:
            continue
        sec_themes.sort(key=t_number)
        selected.append(sec_themes[0])

    # Step 2: extras with section diversity (no mu data -> alternating)
    _section_aware_extras(all_grade_themes, selected, grade,
                          CANONICAL_SECTIONS, section_mus=None)

    # Guard: every theme MUST belong to the student's grade
    for tid in selected:
        if not tid.startswith(grade_prefix):
            raise RuntimeError(
                f"GRADE GUARD: theme {tid} does not start with "
                f"{grade_prefix} (grade={grade}) — cross-grade leak detected"
            )

    # П2(в): validate — no more than 2 themes from any section
    from services.theme_registry import section_of_theme
    sec_counts = {}
    for tid in selected:
        sec = section_of_theme(tid) or '?'
        sec_counts[sec] = sec_counts.get(sec, 0) + 1
    for sec, cnt in sec_counts.items():
        if cnt > 2:
            raise RuntimeError(
                f"CYCLE GUARD: section '{sec}' has {cnt} themes "
                f"(max 2 allowed) — selection logic broken. "
                f"Selected: {selected}"
            )

    return selected[:7]


def _select_subsequent_cycle_themes(user_id: int, grade: int,
                                    exclude: Optional[set] = None) -> List[str]:
    """Select up to 7 themes for subsequent cycles, strictly within the student's grade.

    Rule: 4 from 2 weakest sections, 3 new unmeasured.
    Low-mu themes from the previous cycle carry over.
    ``exclude`` — темы, уже пройденные в предыдущих месяцах (их не выдаём повторно).
    If the grade has fewer than 7 themes, the cycle is shorter.
    """
    from services.theme_registry import themes_of_grade, themes_of_section, section_of_theme
    from services.level_engine import get_state as _get_level_state

    exclude = set(exclude or ())
    grade_themes = [t for t in themes_of_grade(grade) if t not in exclude]
    if not grade_themes:
        return []

    grade_prefix = f"G{grade}"

    # Get level_by_theme
    cs = CuratorState.query.filter_by(user_id=user_id).first()
    measured_themes = {}
    if cs and cs.level_by_theme:
        try:
            lbt = json.loads(cs.level_by_theme) if isinstance(cs.level_by_theme, str) else cs.level_by_theme
            measured_themes = {k: v.get('mu', 3) for k, v in lbt.items()}
        except (json.JSONDecodeError, TypeError):
            pass

    # Section mu from level_by_section
    lvl_state = _get_level_state(user_id)
    by_section = lvl_state.get('by_section', {})

    section_mus = {}
    for sec in CANONICAL_SECTIONS:
        sec_data = by_section.get(sec, {})
        section_mus[sec] = float(sec_data.get('mu', 3.0))

    # Sort sections by weakness
    weakest_sections = sorted(CANONICAL_SECTIONS, key=lambda s: section_mus.get(s, 3.0))

    selected = []
    # 4 themes from 2 weakest sections
    needed_from_weak = 4
    for sec in weakest_sections[:2]:
        sec_themes = [t for t in themes_of_section(grade, sec) if t not in exclude]
        # Sort by measured mu (lowest first), then unmeasured
        sec_themes.sort(key=lambda t: measured_themes.get(t, 5.0))
        for t in sec_themes:
            if t not in selected and len(selected) < needed_from_weak:
                selected.append(t)

        # If the 2 weakest sections didn't yield 4 themes,
        # try the next sections (still within the same grade)
        if len(selected) >= needed_from_weak:
            break
    else:
        # Still need more from weak sections — try remaining sections
        for sec in weakest_sections[2:]:
            if len(selected) >= needed_from_weak:
                break
            sec_themes = [t for t in themes_of_section(grade, sec) if t not in exclude]
            sec_themes.sort(key=lambda t: measured_themes.get(t, 5.0))
            for t in sec_themes:
                if t not in selected and len(selected) < needed_from_weak:
                    selected.append(t)

    # 3+ extras with section diversity using weakness priority
    _section_aware_extras(grade_themes, selected, grade,
                          CANONICAL_SECTIONS, section_mus=section_mus)

    # Guard: every theme MUST belong to the student's grade
    for tid in selected:
        if not tid.startswith(grade_prefix):
            raise RuntimeError(
                f"GRADE GUARD: theme {tid} does not start with "
                f"{grade_prefix} (grade={grade}) — cross-grade leak detected"
            )

    # П2(в): validate — no more than 2 themes from any section
    sec_counts = {}
    for tid in selected:
        sec = section_of_theme(tid) or '?'
        sec_counts[sec] = sec_counts.get(sec, 0) + 1
    for sec, cnt in sec_counts.items():
        if cnt > 2:
            raise RuntimeError(
                f"CYCLE GUARD: section '{sec}' has {cnt} themes "
                f"(max 2 allowed) — selection logic broken. "
                f"Selected: {selected}"
            )

    return selected[:7]


def build_or_get_cycle(user_id: int, grade: int, force_new: bool = False) -> Dict[str, Any]:
    """Build or retrieve the monthly cycle for a user.

    Месяцы:
      - 1-й и 2-й: до 7 тем (4 дня на тему + 3 дня повтора худших);
      - финальный: когда осталось < 7 тем — крутим ВСЕ оставшиеся темы
        весь месяц (31 день, round-robin от худшей к лучшей).

    При завершении месяца (день > 31) переходим к следующему.
    """
    cs = CuratorState.query.filter_by(user_id=user_id).first()
    if not cs:
        cs = CuratorState(user_id=user_id)
        db.session.add(cs)
        db.session.commit()

    mc = _get_monthly_cycle(cs)
    covered = set(mc.get('covered_themes') or [])

    # Если текущий цикл завершён и не принудительно пересоздаётся —
    # переходим к следующему месяцу.
    if mc.get('themes') and mc.get('finished_at') and not force_new:
        covered |= set(mc.get('themes') or [])
        next_themes = _next_month_themes(user_id, grade, covered)
        if next_themes:
            now_iso = datetime.now(timezone.utc).isoformat()
            mc = {
                'started_at': now_iso,
                'themes': next_themes,
                'day_index': 1,
                'done_themes': [],
                'finished_at': None,
                'covered_themes': sorted(covered),
            }
            _save_monthly_cycle(cs, mc)
            db.session.commit()
            return mc
        # Тем для следующего месяца нет — оставляем завершённый цикл.
        return mc

    if mc.get('themes') and not force_new:
        return mc

    # Определяем: первый цикл или последующий
    had_prev = bool(mc.get('finished_at')) or bool(mc.get('done_themes')) or bool(covered)
    if had_prev:
        themes = _next_month_themes(user_id, grade, covered)
    else:
        themes = _select_first_cycle_themes(grade)

    now_iso = datetime.now(timezone.utc).isoformat()
    mc = {
        'started_at': now_iso,
        'themes': themes,
        'day_index': 1,
        'done_themes': [],
        'finished_at': None,
        'covered_themes': sorted(covered),
    }
    _save_monthly_cycle(cs, mc)
    db.session.commit()

    # ── Hook: schedule conveyor generation for this new cycle ──
    try:
        _on_cycle_activated(user_id)
    except Exception:
        pass

    return mc


# ─── Public API ─────────────────────────────────────────────────────────


def _compute_day_index(started_at_iso: Optional[str], themes_count: int = 0) -> int:
    """Compute day_index from started_at date: (today - started_at).days + 1.

    **Not clamped** — returns the actual calendar day count.
    For theme lookup (get_cycle_info), clamper caps to themes_count.
    For daily norm (get_daily_task_count), the raw count is used.

    P11 FIX: Previously day_index was a stored static counter that never
    advanced. Now it's computed from the actual calendar date, so day 8
    correctly returns day_index 8 (and thus 15 tasks instead of 5).
    """
    if not started_at_iso:
        return 1
    try:
        started_date = date.fromisoformat(started_at_iso[:10])
        today = date.today()
        delta = (today - started_date).days
        if delta < 0:
            return 1
        return delta + 1
    except Exception:
        return 1


def _grade_for_user(user_id: int, cs: CuratorState) -> Optional[int]:
    """Класс ученика: CuratorState.grade -> User.preferred_grade -> None."""
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
    return None


def _order_themes_worst_first(user_id: int, themes: List[str]) -> List[str]:
    """Все темы месяца, отсортированные от худшей к лучшей.

    Измеренные (mu по level_by_theme) — по возрастанию mu, затем
    неизмеренные (в порядке появления).  Худшие идут первыми, поэтому при
    равномерном round-robin остаток дней достаётся именно им.
    """
    from services.level_engine import get_level_by_theme

    lbt = {}
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
    """Вернуть до ``k`` самых слабых тем месяца (наименьший mu по level_by_theme)."""
    return _order_themes_worst_first(user_id, themes)[:k]


def _next_month_themes(user_id: int, grade: int, covered: set) -> List[str]:
    """Темы для следующего месяца.

    Если оставшихся тем класса < 7 — возвращаем ВСЕ оставшиеся (финальный
    месяц: крутим сколько осталось).  Иначе — обычная выборка до 7 тем.
    """
    from services.theme_registry import themes_of_grade

    remaining = [t for t in themes_of_grade(grade) if t not in covered]
    if not remaining:
        return []
    if len(remaining) < 7:
        return remaining
    return _select_subsequent_cycle_themes(user_id, grade, exclude=covered)


def get_cycle_info(user_id: int) -> Dict[str, Any]:
    """Get current cycle status for the user.

    Виртуальный месяц = 31 день:
      - дни 1..28: 7 тем, каждая тема идёт 4 дня (тема = (день-1)//4);
      - дни 29..31: повтор 3 худших тем месяца (по mu);
      - день > 31: месяц завершён, при следующем обращении запускается
        СЛЕДУЮЩИЙ месяц из оставшихся тем класса.

    Returns:
        {
            'active', 'started_at', 'day_index', 'themes', 'done_themes',
            'finished', 'current_theme', 'blocked'
        }
    """
    cs = CuratorState.query.filter_by(user_id=user_id).first()
    if not cs:
        return {'active': False}

    mc = _get_monthly_cycle(cs)
    themes = mc.get('themes', [])
    if not themes:
        return {'active': False}

    done = mc.get('done_themes', [])
    day_idx = _compute_day_index(mc.get('started_at'))

    # Месяц завершён (день > 31) — переходим к следующему месяцу.
    if day_idx > MONTH_DAYS:
        grade = _grade_for_user(user_id, cs)
        if grade:
            covered = set(mc.get('covered_themes') or []) | set(themes)
            next_themes = _select_subsequent_cycle_themes(user_id, grade, exclude=covered)
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
                themes = next_themes
                done = []
                day_idx = 1
            else:
                # Все темы класса пройдены.
                mc['finished_at'] = mc.get('finished_at') or datetime.now(timezone.utc).isoformat()
                _save_monthly_cycle(cs, mc)
                db.session.commit()
                return {
                    'active': True,
                    'started_at': mc.get('started_at'),
                    'day_index': day_idx,
                    'themes': themes,
                    'done_themes': done,
                    'finished': True,
                    'current_theme': None,
                    'blocked': False,
                }
        else:
            return {
                'active': True,
                'started_at': mc.get('started_at'),
                'day_index': day_idx,
                'themes': themes,
                'done_themes': done,
                'finished': True,
                'current_theme': None,
                'blocked': False,
            }

    finished = False

    n = len(themes)
    # ── Финальный месяц: тем < 7 → круглое чередование весь месяц ──
    if n < 7:
        ordered = _order_themes_worst_first(user_id, themes)
        current_theme = ordered[(day_idx - 1) % n] if ordered else None
        blocked = False
    else:
        # Дни 1..28 — 7 тем по 4 дня.
        if day_idx <= 7 * THEME_DAYS:
            theme_pos = (day_idx - 1) // THEME_DAYS
            current_theme = themes[theme_pos] if theme_pos < len(themes) else None
            blocked = bool(current_theme and current_theme not in done)
        else:
            # Дни 29..31 — повтор 3 худших тем месяца.
            worst = _worst_themes(user_id, themes, k=REVIEW_DAYS)
            k_idx = day_idx - 7 * THEME_DAYS - 1  # 0..2
            current_theme = worst[k_idx] if 0 <= k_idx < len(worst) else None
            blocked = False  # повторы — только задачи дня, без нового среза

    return {
        'active': True,
        'started_at': mc.get('started_at'),
        'day_index': day_idx,
        'themes': themes,
        'done_themes': done,
        'finished': finished,
        'current_theme': current_theme,
        'blocked': blocked,
    }


def advance_day(user_id: int) -> Dict[str, Any]:
    """Отметить текущую тему месяца как пройденную (после утреннего среза).

    Раскладка 7 тем × 4 дня: помечается тема текущего календарного дня.
    В финальном месяце (< 7 тем) и в дни-повторы (29..31) ничего не помечаем —
    там идёт простое кручение задач.
    """
    cs = CuratorState.query.filter_by(user_id=user_id).first()
    if not cs:
        return {'error': 'no_state'}

    mc = _get_monthly_cycle(cs)
    day_idx = _compute_day_index(mc.get('started_at'))
    themes = mc.get('themes', [])
    done = list(mc.get('done_themes', []))

    if day_idx > MONTH_DAYS:
        return {'error': 'cycle_already_done'}

    # Только для месяца с 7 темами и только в дни 1..28.
    if len(themes) == 7 and day_idx <= 7 * THEME_DAYS:
        theme_pos = (day_idx - 1) // THEME_DAYS
        current_theme = themes[theme_pos] if theme_pos < len(themes) else None
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
    """Return today's subtopic info for morning/evening push notifications.

    Built on get_cycle_info — no extra DB writes.
    Returns dict with keys: subtopic, subtopic_title, is_test_day, tested, has_tasks, level.
    """
    info = get_cycle_info(user_id)
    if not info.get('active'):
        return {}

    current_theme = info.get('current_theme')
    if not current_theme:
        return {}

    from services.theme_registry import theme_title as _theme_title
    from services.theme_probe import has_active_probe

    subtopic_title = _theme_title(current_theme)

    # test day = blocked (probe not done) or probe still active
    is_test_day = info.get('blocked', False) or has_active_probe(user_id)
    tested = current_theme in info.get('done_themes', [])

    # has_tasks = daily task set exists for today for this user
    has_tasks = False
    try:
        from daily_tasks.models import DailyTaskSet
        from datetime import date
        has_tasks = DailyTaskSet.query.filter_by(
            user_id=user_id, target_date=date.today()
        ).first() is not None
    except Exception:
        pass

    from services.level_engine import get_state as _get_level_state
    lvl_state = _get_level_state(user_id)
    level = max(1, min(7, int(lvl_state.get('mu', 2))))

    return {
        'subtopic': current_theme,
        'subtopic_title': subtopic_title,
        'is_test_day': is_test_day,
        'tested': tested,
        'has_tasks': has_tasks,
        'level': level,
    }


def generate_tasks_only(user_id: int, subtopic: str = None) -> Dict[str, Any]:
    """Queue daily task generation for task-only days (8-30) without a probe.

    AI-генерация «Задач дня» отключена (см. daily_tasks/services.py).
    Задачи дня выдаются только из банка daily_task_bank, поэтому
    генерация LLM не запускается.

    Returns {success: bool, subtopic: str, generation_queued: bool, message: str}.
    """
    from services.level_engine import get_state as _get_level_state
    lvl_state = _get_level_state(user_id)
    level = max(1, min(7, int(lvl_state.get('mu', 2))))

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
    """Hook: add 7 entries to gen_conveyor after cycle creation.

    AI-генерация «Задач дня» отключена (см. daily_tasks/services.py).
    Конвейер gen_conveyor не заполняется.
    """
    return False
