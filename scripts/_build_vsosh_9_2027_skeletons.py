# -*- coding: utf-8 -*-
"""One-shot generator for empty skeletons of:

    data/olympiads/vsosh_9_2027_probniks.json   (14 probniks)
    data/olympiads/vsosh_9_2027_theory.json     (24 theory blocks)
    data/olympiads/vsosh_9_2027_tasks.json      (204 tasks)

All text fields that the Pydantic schema allows to be empty/None are
left as null or "".  Fields that the schema requires (`condition_md`,
`idea_md`, `solution_md`, `method_primary`, ...) are filled with a
short placeholder so that `pydantic.TypeAdapter(list[...]).validate_python`
passes and `scripts/import_olympiad.py --dry-run` succeeds.

Run from project root:

    python scripts/_build_vsosh_9_2027_skeletons.py

The script is idempotent — re-running overwrites the three JSON files.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Make project root importable so we can validate against Pydantic schemas.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pydantic import TypeAdapter  # noqa: E402

from schemas.olympiad import (  # noqa: E402
    ProbnikSchema,
    TaskSchema,
    TheoryBlockSchema,
)

OUT_DIR = ROOT / 'data' / 'olympiads'

# ───────────────────── method list (24) ─────────────────────
# Order is the order the user dictated in the task description.
METHODS = [
    ('A1',   'A'),
    ('A2',   'A'),
    ('B1',   'B'),
    ('C1',   'C'),
    ('C5',   'C'),
    ('C5a',  'C'),
    ('D1',   'D'),
    ('D2',   'D'),
    ('D3',   'D'),
    ('D12',  'D'),
    ('E4',   'E'),
    ('E10',  'E'),
    ('E10b', 'E'),
    ('E14',  'E'),
    ('E14a', 'E'),
    ('E14b', 'E'),
    ('F1',   'F'),
    ('F2',   'F'),
    ('F3',   'F'),
    ('F4',   'F'),
    ('F4a',  'F'),
    ('F8',   'F'),
    ('F9a',  'F'),
    ('F13',  'F'),
]

assert len(METHODS) == 24, len(METHODS)

# Stage-task mapping: stage code -> source topic-task number ("1.1", ...)
STAGE_MAP = {
    'stage-1': [('Э1.1', '1.1'), ('Э1.2', '1.3'),  ('Э1.3', '1.8'),
                ('Э1.4', '2.3'), ('Э1.5', '1.17')],
    'stage-2': [('Э2.1', '1.6'), ('Э2.2', '2.2'),  ('Э2.3', '3.6'),
                ('Э2.4', '2.7'), ('Э2.5', '5.7')],
    'stage-3': [('Э3.1', '1.16'),('Э3.2', '4.7'),  ('Э3.3', '2.9'),
                ('Э3.4', '5.4'), ('Э3.5', '9.17')],
    'stage-4': [('Э4.1', '3.4'), ('Э4.2', '8.3'),  ('Э4.3', '2.6'),
                ('Э4.4', '5.8'), ('Э4.5', '7.14')],
    'stage-5': [('Э5.1', '3.10'),('Э5.2', '8.17'), ('Э5.3', '7.16'),
                ('Э5.4', '9.20')],
}
assert sum(len(v) for v in STAGE_MAP.values()) == 24

PROBNIK_PREFIX = 'vsosh-9-2027'

# Placeholder text that satisfies `min_length=1` constraints in the
# schema.  Importing this string from the JSON makes it obvious the
# entry is awaiting real content.
PH = 'TODO: ждёт текста'


# ───────────────────── builders ─────────────────────

def build_theory():
    blocks = []
    for code, section in METHODS:
        blocks.append({
            'method_code':           code,
            'method_name':           f'{code} (название ждёт текста)',
            'section':               section,
            'definition_md':         None,
            'main_theorems_md':      None,
            'typical_techniques_md': None,
            'triggers_md':           None,
            'worked_example_md':     None,
            'pitfalls_md':           None,
            'related_methods':       [],
        })
    return blocks


def build_probniks():
    probs = []

    # 9 topic probniks
    for n in range(1, 10):
        probs.append({
            'code':             f'{PROBNIK_PREFIX}-topic-{n}',
            'type':             'topic',
            'number':           n,
            'title':            f'Тема {n} (название ждёт текста)',
            'description':      None,
            'competition':      'ВсОШ',
            'grade':            9,
            'season_year':      2027,
            'duration_minutes': None,
            'max_score':        None,
            'threshold_prize':  None,
            'threshold_winner': None,
            'sort_order':       n,
            'is_published':     True,
            'theory':           [],   # filled in after methods are assigned
        })

    # 5 stage probniks
    stage_defaults = {
        'stage-1': (180, 35),
        'stage-2': (210, 35),
        'stage-3': (210, 35),
        'stage-4': (240, 35),
        'stage-5': (240, 28),
    }
    for i, key in enumerate(('stage-1', 'stage-2', 'stage-3',
                             'stage-4', 'stage-5'), start=1):
        dur, mxs = stage_defaults[key]
        probs.append({
            'code':             f'{PROBNIK_PREFIX}-{key}',
            'type':             'stage',
            'number':           i,
            'title':            f'Этапный пробник {i} (название ждёт текста)',
            'description':      None,
            'competition':      'ВсОШ',
            'grade':            9,
            'season_year':      2027,
            'duration_minutes': dur,
            'max_score':        mxs,
            'threshold_prize':  None,
            'threshold_winner': None,
            'sort_order':       100 + i,
            'is_published':     True,
            'theory':           [],
        })

    return probs


def build_tasks():
    tasks = []

    # 9 topics × 20 tasks = 180 thematic tasks.
    for topic in range(1, 10):
        for k in range(1, 21):
            tasks.append({
                'probnik_code':     f'{PROBNIK_PREFIX}-topic-{topic}',
                'number':           f'{topic}.{k}',
                'sort_order':       k,
                'difficulty':       None,
                'method_primary':   'X',   # placeholder, schema requires non-empty
                'method_secondary': None,
                'condition_md':     PH,
                'idea_md':          PH,
                'solution_md':      PH,
                'answer':           None,
                'source_prototype': None,
                'estimated_minutes': None,
                'max_score':        7,
            })

    # 5 stage probniks × N tasks (5+5+5+5+4 = 24).
    for stage_key, items in STAGE_MAP.items():
        for idx, (stage_num, source_num) in enumerate(items, start=1):
            tasks.append({
                'probnik_code':     f'{PROBNIK_PREFIX}-{stage_key}',
                'number':           stage_num,
                'sort_order':       idx,
                'difficulty':       None,
                'method_primary':   'X',
                'method_secondary': None,
                'condition_md':     f'{PH} (копия задачи {source_num})',
                'idea_md':          f'{PH} (копия задачи {source_num})',
                'solution_md':      f'{PH} (копия задачи {source_num})',
                'answer':           None,
                'source_prototype': f'копия задачи {source_num}',
                'estimated_minutes': None,
                'max_score':        7,
            })

    return tasks


# ───────────────────── validate + write ─────────────────────

def validate(theory, probniks, tasks):
    TypeAdapter(list[TheoryBlockSchema]).validate_python(theory)
    TypeAdapter(list[ProbnikSchema]).validate_python(probniks)
    TypeAdapter(list[TaskSchema]).validate_python(tasks)

    probnik_codes = {p['code'] for p in probniks}
    orphan = [t['number'] for t in tasks
              if t['probnik_code'] not in probnik_codes]
    if orphan:
        raise SystemExit(f'orphan tasks (no probnik): {orphan!r}')


def dump(name, data):
    path = OUT_DIR / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write('\n')
    print(f'  wrote {path.relative_to(ROOT)}  ({len(data)} items)')


def main():
    theory   = build_theory()
    probniks = build_probniks()
    tasks    = build_tasks()

    validate(theory, probniks, tasks)

    dump('vsosh_9_2027_theory.json',   theory)
    dump('vsosh_9_2027_probniks.json', probniks)
    dump('vsosh_9_2027_tasks.json',    tasks)

    print()
    print(f'theory blocks:  {len(theory)}')
    print(f'probniks:       {len(probniks)} '
          f'(topic: {sum(1 for p in probniks if p["type"]=="topic")}, '
          f'stage: {sum(1 for p in probniks if p["type"]=="stage")})')
    print(f'tasks:          {len(tasks)} '
          f'(thematic: {sum(1 for t in tasks if "topic" in t["probnik_code"])}, '
          f'stage: {sum(1 for t in tasks if "stage" in t["probnik_code"])})')


if __name__ == '__main__':
    main()
