# -*- coding: utf-8 -*-
"""
services/olympiad_adaptive.py — Data loader and test engine for
FORMYLA_L1_L5_TOP5.jsonl olympiad adaptive test.

Loads the JSONL once at module import, provides query functions
for sections/themes/tasks, and session-based test state management.
"""
import json
import os
import random
from typing import Any, Dict, List, Optional, Set

_JSONL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'FORMYLA_L1_L5_TOP5.jsonl',
)

# ── Load tasks once ─────────────────────────────────────────────────
_all_tasks: List[Dict[str, Any]] = []

def _load():
    global _all_tasks
    if _all_tasks:
        return
    try:
        with open(_JSONL_PATH, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    _all_tasks.append(json.loads(line))
    except FileNotFoundError:
        print(f"[olympiad_adaptive] File not found: {_JSONL_PATH}")
    except Exception as e:
        print(f"[olympiad_adaptive] Load error: {e}")

_load()
print(f"[olympiad_adaptive] Loaded {len(_all_tasks)} tasks")

# ── Query API ───────────────────────────────────────────────────────

def get_sections(grade: int) -> List[str]:
    """Return unique section names for a grade, sorted."""
    sections: Set[str] = set()
    for t in _all_tasks:
        if t.get('grade') == grade:
            s = (t.get('section') or '').strip()
            if s:
                sections.add(s)
    return sorted(sections)

def get_themes(grade: int, section: str) -> List[Dict[str, Any]]:
    """Return {theme, count} for a given grade+section."""
    themes: Dict[str, int] = {}
    for t in _all_tasks:
        if t.get('grade') == grade and (t.get('section') or '').strip() == section:
            th = (t.get('theme') or '').strip()
            if th:
                themes[th] = themes.get(th, 0) + 1
    return [
        {'name': name, 'count': count}
        for name, count in sorted(themes.items(), key=lambda x: -x[1])
    ]

def get_task(
    grade: int,
    theme: str,
    level: int,
    shown_uids: Set[str],
) -> Optional[Dict[str, Any]]:
    """Get a random task matching criteria, excluding shown_uids."""
    pool = [
        t for t in _all_tasks
        if t.get('grade') == grade
        and (t.get('theme') or '').strip() == theme
        and t.get('level') == level
        and t.get('task_uid') not in shown_uids
    ]
    if not pool:
        # Try adjacent level
        alt_level = level + 1 if level < 5 else level - 1
        pool = [
            t for t in _all_tasks
            if t.get('grade') == grade
            and (t.get('theme') or '').strip() == theme
            and t.get('level') == alt_level
            and t.get('task_uid') not in shown_uids
        ]
    if not pool:
        return None
    return random.choice(pool)

# ── Test state management (Flask session) ───────────────────────────

def init_test_state(session, grade: int, theme: str):
    """Initialize or reset test state in Flask session."""
    session['olyad_grade'] = grade
    session['olyad_theme'] = theme
    session['olyad_current_level'] = 2  # Start at L2
    session['olyad_task_count'] = 0
    session['olyad_shown_uids'] = []  # list of task_uid strings
    session['olyad_results'] = []  # [{level, ball, task_uid, user_answer, correct_answer, solution, statement}]
    session.modified = True

def get_test_state(session) -> Optional[Dict[str, Any]]:
    """Get current test state dict, or None if not started."""
    if 'olyad_grade' not in session:
        return None
    return {
        'grade': session.get('olyad_grade'),
        'theme': session.get('olyad_theme'),
        'current_level': session.get('olyad_current_level', 2),
        'task_count': session.get('olyad_task_count', 0),
        'shown_uids': set(session.get('olyad_shown_uids', [])),
        'results': session.get('olyad_results', []),
    }

def next_task(session) -> Optional[Dict[str, Any]]:
    """Pick next task, update session, return task dict or None."""
    state = get_test_state(session)
    if state is None:
        return None
    if state['task_count'] >= 5:
        return None  # Test complete

    task = get_task(
        grade=state['grade'],
        theme=state['theme'],
        level=state['current_level'],
        shown_uids=state['shown_uids'],
    )
    if not task:
        return None

    # Record shown
    shown = session.get('olyad_shown_uids', [])
    shown.append(task['task_uid'])
    session['olyad_shown_uids'] = shown
    session.modified = True

    return task

def process_answer(
    session,
    user_answer: str,
    user_solution: str = '',
) -> Dict[str, Any]:
    """Evaluate answer, update level, return feedback dict.
    
    Returns: {
        is_correct, ball, new_level, correct_answer, solution, task_uid
    }
    """
    state = get_test_state(session)
    if state is None:
        return {'error': 'no active test'}

    # Get current task info (last shown uid)
    shown = session.get('olyad_shown_uids', [])
    if not shown:
        return {'error': 'no task in progress'}
    
    current_uid = shown[-1]
    # Find task in DB
    task_data = None
    for t in _all_tasks:
        if t.get('task_uid') == current_uid:
            task_data = t
            break
    if not task_data:
        return {'error': 'task not found'}

    correct_answer = (task_data.get('answer') or '').strip()
    ref_solution = (task_data.get('solution') or '').strip()
    statement = (task_data.get('statement') or '').strip()
    current_level = state['current_level']

    # Normalize and compare
    is_correct = _normalize_answer(user_answer) == _normalize_answer(correct_answer)

    ball = 0
    if is_correct and (not user_solution or user_solution.strip() == ''):
        ball = 1
    elif is_correct and user_solution.strip():
        # Solution provided — check partial quality
        solution_ok = _check_solution_quality(user_solution, ref_solution)
        if solution_ok == 'correct':
            ball = 1
        elif solution_ok == 'partial':
            ball = 0
        else:
            ball = 1  # answer correct, weak solution still counts
    else:
        ball = -1

    new_level = max(1, min(5, current_level + ball))

    # Update session
    session['olyad_current_level'] = new_level
    session['olyad_task_count'] = (session.get('olyad_task_count', 0) + 1)

    results = session.get('olyad_results', [])
    results.append({
        'level': current_level,
        'ball': ball,
        'task_uid': current_uid,
        'user_answer': user_answer,
        'correct_answer': correct_answer,
        'solution': ref_solution,
        'statement': statement,
        'is_correct': is_correct,
    })
    session['olyad_results'] = results
    session.modified = True

    return {
        'is_correct': is_correct,
        'ball': ball,
        'new_level': new_level,
        'correct_answer': correct_answer,
        'solution': ref_solution,
        'task_uid': current_uid,
        'task_count': session['olyad_task_count'],
    }

def get_final_result(session) -> Optional[Dict[str, Any]]:
    """Compute final result after 5 tasks."""
    results = session.get('olyad_results', [])
    if len(results) < 5:
        return None

    total = sum(r['ball'] for r in results)
    final_level = max(1, min(5, 2 + total))

    level_names = {
        1: 'Школьная математика',
        2: 'Школьный этап ВОШ',
        3: 'Муниципальный этап ВОШ',
        4: 'Региональный этап ВОШ',
        5: 'Заключительный этап / Всеросс',
    }

    correct_count = sum(1 for r in results if r['is_correct'])
    partial_count = sum(1 for r in results if not r['is_correct'] and r['ball'] == 0)
    wrong_count = sum(1 for r in results if r['ball'] == -1)

    return {
        'results': results,
        'total_score': total,
        'final_level': final_level,
        'level_name': level_names.get(final_level, f'Уровень {final_level}'),
        'correct_count': correct_count,
        'partial_count': partial_count,
        'wrong_count': wrong_count,
        'grade': session.get('olyad_grade'),
        'theme': session.get('olyad_theme'),
    }

# ── Helpers ─────────────────────────────────────────────────────────

def _normalize_answer(s: str) -> str:
    """Normalize answer for comparison."""
    return s.strip().lower().replace(' ', '').rstrip('.0').rstrip(',')

def _check_solution_quality(user_sol: str, ref_sol: str) -> str:
    """Quick heuristic check: does user solution contain key elements?
    
    Very simple: count how many 'key phrases' from ref solution appear.
    """
    if not ref_sol:
        return 'correct'  # No reference — count as correct
    user = user_sol.strip().lower()
    ref = ref_sol.strip().lower()
    
    # Extract key phrases (sentences/equations)
    ref_sentences = [s.strip() for s in ref.replace('.', '\n').replace(';', '\n').split('\n') if len(s.strip()) > 10]
    if not ref_sentences:
        return 'correct'
    
    matches = 0
    for phrase in ref_sentences[:5]:  # Check first 5 key phrases
        # Check if significant words appear
        words = [w for w in phrase.split() if len(w) > 3]
        if not words:
            continue
        match_words = sum(1 for w in words if w in user)
        if match_words >= len(words) * 0.5:
            matches += 1
    
    if matches >= len(ref_sentences[:5]) * 0.6:
        return 'correct'
    elif matches >= 1:
        return 'partial'
    return 'weak'
