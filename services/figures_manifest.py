"""
Figures manifest loader and lookup helpers.

Loads static/figures/MANIFEST.json once at import time.

All 205 entries now have problem_num and placement populated — every figure
is bound to a specific (olympiad, year, class, day, problem_num) tuple.
No more kit-level / per-task split.

Public API:
  get_figures_for_problem(olympiad, year, grade, day, problem_num)
      -> {'condition': [filename, ...], 'solution': [filename, ...]}

  competition_to_slug(competition_name: str) -> str | None
      Maps Probnik.competition (e.g. 'ВсОШ') to manifest slug (e.g. 'vsosh').

  slug_to_competition(olympiad_slug: str) -> str | None
      Reverse map: manifest slug -> human-readable competition name.

  get_figures_for_probnik_task(probnik, task)
      -> {'condition': [filename, ...], 'solution': [filename, ...]}
      Convenience helper that extracts fields from a Probnik + OlympiadTask
      and attempts a lookup.
"""

import json
import os
import re
from collections import defaultdict

_MANIFEST_PATH = os.path.join(
    os.path.dirname(__file__), '..', 'static', 'figures', 'MANIFEST.json'
)

_MANIFEST: list = []
try:
    with open(_MANIFEST_PATH, encoding='utf-8') as _f:
        _MANIFEST = json.load(_f)
    print(f"[figures_manifest] loaded {len(_MANIFEST)} entries")
except FileNotFoundError:
    print("[figures_manifest] MANIFEST.json not found - figures disabled")
except Exception as _e:
    print(f"[figures_manifest] error loading manifest: {_e}")

# ── competition <-> slug mapping ──────────────────────────────────────────────
# Built from the olympiad_title fields in MANIFEST.json.
COMPETITION_TO_SLUG: dict[str, str] = {
    'Всероссийская олимпиада школьников (ВсОШ)': 'vsosh',
    'Московская математическая олимпиада':        'mos',
    'Турнир городов':                              'turgor',
    'Ломоносов':                                   'lomonosov',
    'Олимпиада СПбГУ':                             'spbgu',
    'Олимпиада Эйлера':                            'euler',
}
# Shorter / alternative names that may appear in Probnik.competition.
COMPETITION_TO_SLUG.update({
    'ВсОШ':       'vsosh',
    'ММО':        'mos',
    'СПбГУ':      'spbgu',
    'Турнир':     'turgor',
})

# Reverse mapping (slug -> canonical human-readable name).
SLUG_TO_COMPETITION: dict[str, str] = {
    v: k for k, v in COMPETITION_TO_SLUG.items()
    if k in (
        'Всероссийская олимпиада школьников (ВсОШ)',
        'Московская математическая олимпиада',
        'Турнир городов',
        'Ломоносов',
        'Олимпиада СПбГУ',
        'Олимпиада Эйлера',
    )
}


def competition_to_slug(name: str) -> str | None:
    """Map a human-readable competition name (as stored in Probnik.competition)
    to the short slug used in MANIFEST.json (e.g. 'vsosh', 'mos')."""
    return COMPETITION_TO_SLUG.get(name.strip())


def slug_to_competition(slug: str) -> str | None:
    """Reverse lookup: manifest slug -> canonical competition name."""
    return SLUG_TO_COMPETITION.get(slug)


# ── unified index ─────────────────────────────────────────────────────────────
# Key: (olympiad_slug, year, class, day, problem_num)
# Value: {'condition': [filenames], 'solution': [filenames]}
# day and problem_num may be None for entries that lack them.

_UNIFIED_INDEX: dict = defaultdict(lambda: {'condition': [], 'solution': []})

for _entry in _MANIFEST:
    _file = _entry.get('file', '')
    _olympiad = _entry.get('olympiad') or ''
    _year = _entry.get('year')
    _cls = _entry.get('class')
    _day = _entry.get('day')
    _pnum = _entry.get('problem_num')
    _placement = _entry.get('placement') or 'condition'

    _key = (_olympiad, _year, _cls, _day, _pnum)
    if _file and _file not in _UNIFIED_INDEX[_key][_placement]:
        _UNIFIED_INDEX[_key][_placement].append(_file)


# ── public API ────────────────────────────────────────────────────────────────


def get_figures_for_problem(
    olympiad: str,
    year: int | None,
    grade: int | None,
    day: int | None = None,
    problem_num: int | None = None,
) -> dict:
    """
    Return per-task figures from the unified index.

    Args:
        olympiad:   Slug like 'mos', 'vsosh', 'turgor', etc.
        year:       Competition year.
        grade:      Class/grade (8-11).
        day:        Day of the olympiad (1 or 2, may be None).
        problem_num: Problem number (may be None for some entries).

    Returns:
        {'condition': [filenames], 'solution': [filenames]}
    """
    key = (olympiad, year, grade, day, problem_num)
    entry = _UNIFIED_INDEX.get(key)
    if entry is not None:
        return {
            'condition': list(entry['condition']),
            'solution':  list(entry['solution']),
        }

    # Fallback: try with day=None if we had a specific day.
    if day is not None:
        fallback_key = (olympiad, year, grade, None, problem_num)
        fallback = _UNIFIED_INDEX.get(fallback_key)
        if fallback is not None:
            return {
                'condition': list(fallback['condition']),
                'solution':  list(fallback['solution']),
            }

    return {'condition': [], 'solution': []}


def _extract_problem_num(task_number: str) -> int | None:
    """Extract the integer problem number from an OlympiadTask.number.

    Examples:
      '1.1'   -> 1
      '2.3'   -> 2
      'Э3.5'  -> 3  (extra problem)
      '5'     -> 5
      '1'     -> 1
    """
    # Match digits at the start or after a non-digit prefix like 'Э'.
    m = re.search(r'(\d+)', str(task_number))
    if m:
        return int(m.group(1))
    return None


def get_figures_for_probnik_task(probnik, task) -> dict:
    """Convenience: extract fields from a Probnik + OlympiadTask and look up
    matching figures.

    Uses:
      - probnik.competition   (human-readable, e.g. 'ВсОШ')
      - probnik.season_year   (int)
      - probnik.grade         (int)
      - task.number           (str, e.g. '1.1')
      - task.year             (int | None, overrides probnik.season_year if set)
      - task.source_prototype (str | None, may contain structured info)

    Returns {'condition': [...], 'solution': [...]} (possibly empty).
    """
    # 1) Determine year: prefer task.year (more specific) over probnik.season_year.
    year = task.year if task.year is not None else getattr(probnik, 'season_year', None)
    grade = getattr(probnik, 'grade', None)
    competition = getattr(probnik, 'competition', '') or ''
    slug = competition_to_slug(competition)

    if not slug or not year or not grade:
        return {'condition': [], 'solution': []}

    # 2) Extract problem number from task.number.
    pnum = _extract_problem_num(task.number)

    # 3) Lookup — try both day=None and day=1 as plausible defaults.
    #    Most MANIFEST entries have day=1; some have day=2; some have day=None.
    for day_candidate in (None, 1):
        result = get_figures_for_problem(slug, year, grade, day_candidate, pnum)
        if result['condition'] or result['solution']:
            return result

    return {'condition': [], 'solution': []}
