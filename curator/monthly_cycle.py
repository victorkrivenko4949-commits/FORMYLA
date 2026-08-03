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

ACTIVE_DAYS = 7           # days with morning probes
CANONICAL_SECTIONS = ('algebra', 'geometry', 'combinatorics', 'logic', 'number_theory')

# ─── Prep state helpers ─────────────────────────────────────────────────


def _default_monthly_cycle() -> Dict[str, Any]:
    return {
        'started_at': None,
        'themes': [],           # 7 theme_ids
        'day_index': 1,         # 1..7
        'done_themes': [],      # completed theme_ids
        'finished_at': None,
    }


def _get_monthly_cycle(cs: CuratorState) -> Dict[str, Any]:
    ps = cs.prep_state or {}
    mc = ps.get('monthly_cycle')
    if not isinstance(mc, dict) or not mc.get('themes'):
        return _default_monthly_cycle()
    return mc


def _save_monthly_cycle(cs: CuratorState, mc: Dict[str, Any]):
    ps = dict(cs.prep_state) if cs.prep_state else {}
    ps['monthly_cycle'] = mc
    cs.prep_state = ps


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

    # Pick one from each eligible section, round-robin until done
    extra_count = 0
    while extra_count < needed:
        picked_this_round = False
        for sec in sorted_sections:
            if extra_count >= needed:
                break
            if section_counts.get(sec, 0) >= max_per_section:
                continue
            sec_themes = themes_of_section(grade, sec)
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


def _select_subsequent_cycle_themes(user_id: int, grade: int) -> List[str]:
    """Select up to 7 themes for subsequent cycles, strictly within the student's grade.

    Rule: 4 from 2 weakest sections, 3 new unmeasured.
    Low-mu themes from the previous cycle carry over.
    If the grade has fewer than 7 themes, the cycle is shorter.
    """
    from services.theme_registry import themes_of_grade, themes_of_section, section_of_theme
    from services.level_engine import get_state as _get_level_state

    grade_themes = themes_of_grade(grade)
    if not grade_themes:
        return _select_first_cycle_themes(grade)

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
        sec_themes = themes_of_section(grade, sec)
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
            sec_themes = themes_of_section(grade, sec)
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

    If no cycle exists or force_new=True, selects 7 themes and starts a new cycle.
    """
    cs = CuratorState.query.filter_by(user_id=user_id).first()
    if not cs:
        cs = CuratorState(user_id=user_id)
        db.session.add(cs)
        db.session.commit()

    mc = _get_monthly_cycle(cs)

    if mc.get('themes') and not force_new:
        # Validate cached cycle: max 2 themes per section.
        # P11 FIX: only rebuild if a KNOWN section exceeds 2.
        # Unknown sections ('?') mean theme IDs are synthetic/test data —
        # don't destroy the cached started_at date.
        from services.theme_registry import section_of_theme
        sec_counts = {}
        unknown_count = 0
        for tid in mc['themes']:
            sec = section_of_theme(tid) or '?'
            if sec == '?':
                unknown_count += 1
            else:
                sec_counts[sec] = sec_counts.get(sec, 0) + 1
        # Only rebuild if a known section exceeds 2 (ignore '?' for all-unknown cycles)
        if any(cnt > 2 for cnt in sec_counts.values()):
            logger.info(
                'build_or_get_cycle: cached cycle violates max-2 rule — rebuilding. '
                'Counts: %s  Themes: %s', sec_counts, mc['themes']
            )
        elif unknown_count == len(mc['themes']) and mc.get('started_at'):
            # All themes unknown (test/fake data) — preserve started_at, return as-is
            return mc
        else:
            return mc

    # Determine if first cycle
    if mc.get('finished_at') or not mc.get('started_at'):
        # Check if any cycle was ever completed
        had_prev = bool(mc.get('finished_at')) or bool(mc.get('done_themes'))
        if had_prev:
            themes = _select_subsequent_cycle_themes(user_id, grade)
        else:
            themes = _select_first_cycle_themes(grade)
    else:
        themes = _select_first_cycle_themes(grade)

    now_iso = datetime.now(timezone.utc).isoformat()
    mc = {
        'started_at': now_iso,
        'themes': themes,
        'day_index': 1,
        'done_themes': [],
        'finished_at': None,
    }
    _save_monthly_cycle(cs, mc)
    db.session.commit()

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


def get_cycle_info(user_id: int) -> Dict[str, Any]:
    """Get current cycle status for the user.

    day_index is computed from started_at date (calendar arithmetic),
    NOT from a stored static counter. This means day_index auto-advances
    as calendar days pass.

    Returns:
        {
            'active': bool,
            'started_at': iso_str | None,
            'day_index': 1..7 (computed from started_at),
            'themes': [theme_id, ...],
            'done_themes': [theme_id, ...],
            'finished': bool,
            'current_theme': str | None,   # theme for current day
            'blocked': bool,               # True if probe not done for current day
        }
    """
    cs = CuratorState.query.filter_by(user_id=user_id).first()
    if not cs:
        return {'active': False}

    mc = _get_monthly_cycle(cs)
    if not mc.get('themes'):
        return {'active': False}

    # P11 FIX: compute day_index from started_at date, not stored counter
    day_idx = _compute_day_index(mc.get('started_at'))
    themes = mc.get('themes', [])
    done = mc.get('done_themes', [])
    finished = len(done) >= ACTIVE_DAYS

    # theme_index clamps to themes_count for safe array access
    theme_idx = min(day_idx, len(themes)) if themes else 1
    current_theme = themes[theme_idx - 1] if theme_idx <= len(themes) else None

    # Check if probe is pending
    from services.theme_probe import has_active_probe, get_active_probe_theme
    probe_pending = has_active_probe(user_id)
    probe_theme = get_active_probe_theme(user_id)
    blocked = False

    if not finished and current_theme and current_theme not in done and not probe_pending:
        blocked = True  # No probe started yet for today

    if probe_pending and probe_theme and probe_theme != current_theme:
        blocked = True  # Probe for different theme is pending

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
    """Mark current day's probe as done. Day index stays — the done_themes
    list tells get_cycle_info that the current theme is measured, unblocking
    daily tasks for today. Day index only advances when get_cycle_info is
    called on a different calendar day (outside this function).

    Called after a probe is completed.
    """
    cs = CuratorState.query.filter_by(user_id=user_id).first()
    if not cs:
        return {'error': 'no_state'}

    mc = _get_monthly_cycle(cs)
    day_idx = mc.get('day_index', 1)
    themes = mc.get('themes', [])
    done = list(mc.get('done_themes', []))

    if day_idx > len(themes):
        return {'error': 'cycle_already_done'}

    current_theme = themes[day_idx - 1]
    if current_theme not in done:
        done.append(current_theme)

    mc['done_themes'] = done

    # DO NOT advance day_index — stay on current day.
    # When the student visits /daily_tasks, get_cycle_info will see
    # current_theme in done_themes -> blocked=False -> tasks are shown.
    # Day index only advances when get_cycle_info is called on a
    # calendar day where the student already finished the previous probe.

    if len(done) >= ACTIVE_DAYS:
        mc['finished_at'] = datetime.now(timezone.utc).isoformat()

    _save_monthly_cycle(cs, mc)
    db.session.commit()

    return {
        'day_index': mc['day_index'],
        'done_count': len(mc['done_themes']),
        'finished': len(mc['done_themes']) >= ACTIVE_DAYS,
        'current_theme': themes[mc['day_index'] - 1] if mc['day_index'] <= len(themes) else None,
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

    Returns {success: bool, subtopic: str, generation_queued: bool, message: str}.
    """
    from services.level_engine import get_state as _get_level_state
    lvl_state = _get_level_state(user_id)
    level = max(1, min(7, int(lvl_state.get('mu', 2))))

    if subtopic is None:
        info = get_today_info(user_id)
        subtopic = info.get('subtopic', '')

    queued = False
    try:
        from daily_tasks.services import enqueue_daily_generation
        enqueue_daily_generation(user_id)
        queued = True
    except Exception:
        pass

    return {
        'success': queued,
        'subtopic': subtopic,
        'level': level,
        'generation_queued': queued,
        'message': 'Tasks generation queued' if queued else 'Daily set already exists or generation not available',
    }
