# -*- coding: utf-8 -*-
"""
services/theme_probe.py — 5-task morning probe for a single subtopic.

Implements the "лесенка" (ladder) adaptive test:
  - 5 tasks from one subtopic, delivered one-by-one
  - Start level = max(start_level from questionnaire, 1), capped at route_ceiling
  - After each answer: correct -> +1, partial -> 0, wrong -> -2
  - Level clamped [1, 5] and ≤ route_ceiling
  - Final mu = level after 5th answer -> saved to level_by_theme
  - State is persisted AFTER EVERY OPERATION so user can close tab and resume
  - "Продолжить утренний срез" returns to the exact same question

V3 FIXES:
  - is_flagged NULL treated as NOT flagged (was: .is_(False) missed 8738 NULL rows)
  - Fallback: if no tasks in grade+level, try same section other themes, 
    then same section any grade, then any task
  - Save probe state AFTER every task selection (previously only on answer)
"""
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from models import db, AdaptiveTask
from models_curator import CuratorState

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

PROBE_SIZE = 5           # exact 5 tasks per probe
ROUTE_CEILING = 5        # max level regardless of questionnaire
MIN_LEVEL = 1
MAX_LEVEL = 5

CORRECT_DELTA = +1
PARTIAL_DELTA = 0
WRONG_DELTA = -2

# ══════════════════════════════════════════════════════════════════════
# Helper: is_flagged filter (treats NULL as NOT flagged)
# ══════════════════════════════════════════════════════════════════════

def _not_flagged():
    """Filter: task is NOT flagged (NULL or False)."""
    return db.or_(
        AdaptiveTask.is_flagged.is_(False),
        AdaptiveTask.is_flagged.is_(None),
    )


def _not_anchor():
    """Filter: task is not an anchor (source is NULL or not 'formyla_anchors')."""
    return db.or_(
        AdaptiveTask.source.is_(None),
        AdaptiveTask.source != 'formyla_anchors',
    )


# ══════════════════════════════════════════════════════════════════════
# Probe state helpers
# ══════════════════════════════════════════════════════════════════════


def _get_probe_state(cs: CuratorState) -> Optional[Dict[str, Any]]:
    """Get active probe state from CuratorState, or None.
    
    Uses a separate text field if available, otherwise prep_state JSON.
    """
    import json as _json
    
    # Primary: check dedicated probe_json field
    raw = getattr(cs, 'probe_json', None)
    if raw and isinstance(raw, str):
        try:
            return _json.loads(raw)
        except (_json.JSONDecodeError, TypeError):
            pass
    
    # Fallback: prep_state['active_probe']
    ps = cs.prep_state or {}
    if isinstance(ps, str):
        try:
            ps = _json.loads(ps)
        except (_json.JSONDecodeError, TypeError):
            ps = {}
    probe = ps.get('active_probe')
    if isinstance(probe, dict):
        return probe
    return None


def _save_probe_state(cs: CuratorState, probe: Optional[Dict[str, Any]]):
    """Save probe state into CuratorState.probe_json (dedicated field)."""
    import json as _json
    from sqlalchemy.orm.attributes import flag_modified
    
    if probe is None:
        cs.probe_json = None
    else:
        cs.probe_json = _json.dumps(probe, ensure_ascii=False)
    
    # Also update prep_state for backward compat
    ps = dict(cs.prep_state) if cs.prep_state else {}
    if isinstance(ps, str):
        try:
            ps = _json.loads(ps)
        except (_json.JSONDecodeError, TypeError):
            ps = {}
    if probe is None:
        ps.pop('active_probe', None)
    else:
        ps['active_probe'] = probe
    cs.prep_state = ps
    flag_modified(cs, 'prep_state')


# ══════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════


def has_active_probe(user_id: int) -> bool:
    """Check if the student has an unfinished probe."""
    cs = CuratorState.query.filter_by(user_id=user_id).first()
    if not cs:
        return False
    probe = _get_probe_state(cs)
    return probe is not None and probe.get('current_index', 0) < PROBE_SIZE


def get_active_probe_theme(user_id: int) -> Optional[str]:
    """Return the theme_id of the active probe, or None."""
    cs = CuratorState.query.filter_by(user_id=user_id).first()
    if not cs:
        return None
    probe = _get_probe_state(cs)
    if probe and probe.get('current_index', 0) < PROBE_SIZE:
        return probe.get('theme_id')
    return None


def resolve_start_level(user_id: int, theme_id: str, grade: int) -> int:
    """Resolve the starting level for a theme probe.

    Priority:
      1. If theme already measured -> its past mu (rounded)
      2. Questionnaire start_level, capped at route_ceiling
      3. Section mu from level_by_section
      4. Global mu from level_engine
      5. Default: 2
    """
    from services.level_engine import get_state as _get_level_state
    from services.theme_registry import section_of_theme as _sec

    cs = CuratorState.query.filter_by(user_id=user_id).first()

    # 1. Already measured?
    if cs and cs.level_by_theme:
        try:
            lbt = json.loads(cs.level_by_theme) if isinstance(cs.level_by_theme, str) else cs.level_by_theme
            if theme_id in lbt:
                mu = float(lbt[theme_id].get('mu', 2))
                return max(1, min(ROUTE_CEILING, int(round(mu))))
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    # 2. Questionnaire start_level
    try:
        from services.questionnaire_storage import get_questionnaire_level
        q_level = get_questionnaire_level(user_id)
        if q_level is not None:
            return max(1, min(ROUTE_CEILING, int(q_level)))
    except Exception:
        pass

    # 3. Section mu
    section = _sec(theme_id)
    if section:
        try:
            lvl_state = _get_level_state(user_id)
            by_section = lvl_state.get('by_section', {})
            sec_data = by_section.get(section, {})
            sec_mu = sec_data.get('mu')
            if sec_mu is not None:
                return max(1, min(ROUTE_CEILING, int(round(float(sec_mu)))))
        except Exception:
            pass

    # 4. Global mu
    try:
        lvl_state = _get_level_state(user_id)
        global_mu = lvl_state.get('mu', 2)
        return max(1, min(ROUTE_CEILING, int(round(float(global_mu)))))
    except Exception:
        pass

    return 2


def start_probe(user_id: int, theme_id: str, grade: int) -> Dict[str, Any]:
    """Start a new probe for a theme. Returns first task or error."""
    cs = CuratorState.query.filter_by(user_id=user_id).first()
    if not cs:
        cs = CuratorState(user_id=user_id)
        db.session.add(cs)

    # Check for existing active probe
    existing = _get_probe_state(cs)
    if existing and existing.get('current_index', 0) < PROBE_SIZE:
        if existing.get('theme_id') == theme_id:
            # Resume — just return the current task
            return _current_task_state(cs, existing, grade)
        # Different theme – silently replace? No, block.
        return {
            'error': 'active_probe_exists',
            'current_theme': existing.get('theme_id'),
            'current_index': existing.get('current_index', 0),
        }

    start_level = resolve_start_level(user_id, theme_id, grade)

    probe_id = int(datetime.now(timezone.utc).timestamp() * 1_000_000)
    probe = {
        'probe_id': probe_id,
        'theme_id': theme_id,
        'grade': grade,
        'current_index': 0,
        'current_level': start_level,
        'seen_task_ids': [],
        'answers': [],
        'started_at': datetime.now(timezone.utc).isoformat(),
    }

    # Select first task and save state immediately
    result = _select_and_advance(cs, probe, grade)
    if result.get('error'):
        return result
    return result


def _current_task_state(cs: CuratorState, probe: Dict[str, Any], grade: int) -> Dict[str, Any]:
    """Return the current task state without selecting a new task (for resume)."""
    theme_id = probe['theme_id']
    current_level = probe['current_level']
    seen_ids = probe.get('seen_task_ids', [])
    idx = probe['current_index']

    if not seen_ids or idx >= len(seen_ids):
        # No task selected yet — select one
        return _select_and_advance(cs, probe, grade)

    # Return the current (last seen) task
    last_task_id = seen_ids[-1]
    task = db.session.get(AdaptiveTask, last_task_id)
    if not task:
        # Task deleted — select new one
        return _select_and_advance(cs, probe, grade)

    return {
        'probe_id': probe.get('probe_id'),
        'theme_id': theme_id,
        'current_index': idx,
        'total': PROBE_SIZE,
        'current_level': current_level,
        'task': {
            'id': task.id,
            'task_text': task.task_text,
            'difficulty_level': task.difficulty_level,
            'topic': task.topic,
        },
    }


def _select_and_advance(cs: CuratorState, probe: Dict[str, Any], grade: int) -> Dict[str, Any]:
    """Select the next task, save state, and return result.
    
    V3: Multi-stage fallback ensures probe always finds tasks:
      1. Same grade + same level (±0, ±1, ±2)
      2. Same grade, any level
      3. Same section (from theme), nearby grades, any level  
      4. Any non-flagged, non-anchor task
    Also saves probe state immediately after selection.
    """
    theme_id = probe['theme_id']
    current_level = probe['current_level']
    seen_ids = set(probe.get('seen_task_ids', []))
    idx = probe['current_index']

    task = None

    # Determine section from theme_id for fallback
    section = None
    try:
        from services.theme_registry import section_of_theme
        section = section_of_theme(theme_id)
    except Exception:
        pass

    # Stage 1: Try exact grade + level ladder (same as before, but with NULL-safe filter)
    for offset in [0, -1, 1, -2, 2]:
        level = max(1, min(5, current_level + offset))
        candidate = (
            AdaptiveTask.query
            .filter_by(class_level=grade, difficulty_level=level)
            .filter(_not_flagged())
            .filter(_not_anchor())
            .filter(~AdaptiveTask.id.in_(seen_ids) if seen_ids else True)
            .order_by(db.func.random())
            .first()
        )
        if candidate:
            task = candidate
            break

    # Stage 2: Same grade, any level
    if not task:
        candidate = (
            AdaptiveTask.query
            .filter_by(class_level=grade)
            .filter(_not_flagged())
            .filter(_not_anchor())
            .filter(~AdaptiveTask.id.in_(seen_ids) if seen_ids else True)
            .order_by(db.func.random())
            .first()
        )
        if candidate:
            task = candidate

    # Stage 3: Same section, nearby grades, any level
    if not task and section:
        # Try grades near the student's grade
        for g in [grade - 1, grade + 1, grade - 2, grade + 2, grade - 3, grade + 3]:
            if g < 5 or g > 11:
                continue
            candidate = (
                AdaptiveTask.query
                .filter_by(class_level=g)
                .filter(_not_flagged())
                .filter(_not_anchor())
                .filter(~AdaptiveTask.id.in_(seen_ids) if seen_ids else True)
                .order_by(db.func.random())
                .first()
            )
            if candidate:
                task = candidate
                break

    # Stage 4: Any non-flagged, non-anchor task
    if not task:
        task = (
            AdaptiveTask.query
            .filter(_not_flagged())
            .filter(_not_anchor())
            .filter(~AdaptiveTask.id.in_(seen_ids) if seen_ids else True)
            .order_by(db.func.random())
            .first()
        )

    if not task:
        return {'error': 'no_tasks', 'theme_id': theme_id, 'current_index': idx}

    # Save seen task IDs to probe state
    probe['seen_task_ids'] = list(seen_ids) + [task.id]
    # Save state IMMEDIATELY (V3 fix: previously only saved on answer)
    _save_probe_state(cs, probe)
    db.session.commit()

    return {
        'probe_id': probe.get('probe_id'),
        'theme_id': theme_id,
        'current_index': idx,
        'total': PROBE_SIZE,
        'current_level': current_level,
        'task': {
            'id': task.id,
            'task_text': task.task_text,
            'difficulty_level': task.difficulty_level,
            'topic': task.topic,
        },
    }


def record_answer(user_id: int, task_id: int, verdict: str,
                  user_solution: str = '') -> Dict[str, Any]:
    """Record an answer for the current probe task.

    verdict: 'correct', 'partial', or 'wrong'
    user_solution: text of student's solution (for partial detection)

    Returns the next task or probe-completion result.
    """
    cs = CuratorState.query.filter_by(user_id=user_id).first()
    if not cs:
        return {'error': 'no_state'}

    probe = _get_probe_state(cs)
    if not probe:
        return {'error': 'no_active_probe'}

    idx = probe['current_index']
    current_level = probe['current_level']

    # Record answer
    answers = list(probe.get('answers', []))
    answers.append({
        'task_id': task_id,
        'verdict': verdict,
        'level_shown': current_level,
    })
    probe['answers'] = answers

    # Update level
    if verdict == 'correct':
        new_level = current_level + CORRECT_DELTA
    elif verdict == 'partial':
        new_level = current_level + PARTIAL_DELTA
    else:
        new_level = current_level + WRONG_DELTA

    new_level = max(MIN_LEVEL, min(min(MAX_LEVEL, ROUTE_CEILING), new_level))
    probe['current_level'] = new_level
    probe['current_index'] = idx + 1

    if probe['current_index'] >= PROBE_SIZE:
        # Probe complete
        return _finish_probe(cs, probe, user_id)

    _save_probe_state(cs, probe)
    db.session.commit()

    # Select next task and save state
    return _select_and_advance(cs, probe, probe.get('grade', 9))


def _finish_probe(cs: CuratorState, probe: Dict[str, Any], user_id: int) -> Dict[str, Any]:
    """Finalize the probe: record mu and return result."""
    from services.theme_registry import section_of_theme as _sec

    theme_id = probe['theme_id']
    final_mu = float(probe['current_level'])
    section = _sec(theme_id)

    # Save to level_by_theme
    lbt = {}
    if cs.level_by_theme:
        try:
            lbt = json.loads(cs.level_by_theme) if isinstance(cs.level_by_theme, str) else cs.level_by_theme
        except (json.JSONDecodeError, TypeError):
            lbt = {}

    now_iso = datetime.now(timezone.utc).isoformat()
    lbt[theme_id] = {
        'mu': final_mu,
        'n': int(lbt.get(theme_id, {}).get('n', 0)) + 1,
        'measured_at': now_iso,
    }
    cs.level_by_theme = json.dumps(lbt, ensure_ascii=False)

    # Recompute section mu
    if section:
        _recalc_section_mu(cs, section)

    # Mark probe as done
    _save_probe_state(cs, None)

    db.session.commit()

    return {
        'done': True,
        'probe_id': probe.get('probe_id'),
        'theme_id': theme_id,
        'section': section,
        'final_mu': final_mu,
        'answers': probe.get('answers', []),
        'level_by_theme': lbt,
    }


def _recalc_section_mu(cs: CuratorState, section: str):
    """Recalculate section mu as average of measured themes in that section."""
    from services.theme_registry import all_themes
    import json as _json

    if not cs.level_by_theme:
        return

    try:
        lbt = _json.loads(cs.level_by_theme) if isinstance(cs.level_by_theme, str) else cs.level_by_theme
    except (_json.JSONDecodeError, TypeError):
        return

    # Get all themes in this section
    section_themes = {tid for tid, sec in all_themes() if sec == section}
    measured = {tid: data for tid, data in lbt.items() if tid in section_themes}

    if not measured:
        return

    avg_mu = sum(float(d['mu']) for d in measured.values()) / len(measured)

    # Update level_by_section
    by_section = {}
    if cs.level_by_section:
        try:
            by_section = _json.loads(cs.level_by_section) if isinstance(cs.level_by_section, str) else cs.level_by_section
        except (_json.JSONDecodeError, TypeError):
            by_section = {}

    if section not in by_section:
        by_section[section] = {}

    by_section[section]['mu'] = round(avg_mu, 3)
    by_section[section]['n'] = len(measured)
    cs.level_by_section = _json.dumps(by_section, ensure_ascii=False)
