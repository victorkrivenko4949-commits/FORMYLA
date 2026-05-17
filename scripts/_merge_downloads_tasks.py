# -*- coding: utf-8 -*-
"""Merge the user-supplied tasks file from Downloads into
   data/olympiads/vsosh_9_2027_tasks.json.

Accepts either the original filename or a "(1)" copy that Chrome
creates when the file is re-downloaded.  The newest mtime wins.

The Downloads file has the full method_primary assignment (A1, A2a, …)
but uses `null` for the three required *_md text fields and may include
an extra `status` key not allowed by the Pydantic schema.

This script normalises the file so it validates against TaskSchema:
  * drops the `status` key,
  * replaces null in condition_md/idea_md/solution_md with the
    placeholder 'TODO: ждёт текста',
  * keeps everything else as-is.

Then it appends skeleton rows for any probniks NOT covered by the
Downloads file (e.g. stage probniks if only thematic batches were sent),
re-using whatever already exists in data/olympiads/vsosh_9_2027_tasks.json
(so re-running the skeleton builder first is recommended).
"""

from __future__ import annotations

import glob
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pydantic import TypeAdapter  # noqa: E402

from schemas.olympiad import TaskSchema  # noqa: E402

DOWNLOADS = Path(os.path.expanduser('~')) / 'Downloads'
DST = ROOT / 'data' / 'olympiads' / 'vsosh_9_2027_tasks.json'

PH = 'TODO: ждёт текста'


def find_src() -> Path:
    """Return the newest matching tasks_batches file in Downloads."""
    matches = sorted(
        glob.glob(str(DOWNLOADS / 'vsosh_9_2027_tasks_batches_*.json')),
        key=os.path.getmtime,
        reverse=True,
    )
    if not matches:
        raise SystemExit(
            f'No vsosh_9_2027_tasks_batches_*.json file found in {DOWNLOADS}'
        )
    return Path(matches[0])


def main():
    src = find_src()
    print(f'src: {src}')
    print(f'dst: {DST.relative_to(ROOT)}')

    with src.open('r', encoding='utf-8') as fh:
        raw = json.load(fh)
    print(f'loaded {len(raw)} items from Downloads')

    cleaned = []
    for t in raw:
        t = dict(t)             # copy
        t.pop('status', None)   # drop non-schema key
        if t.get('condition_md') in (None, ''):
            t['condition_md'] = PH
        if t.get('idea_md') in (None, ''):
            t['idea_md'] = PH
        if t.get('solution_md') in (None, ''):
            t['solution_md'] = PH
        cleaned.append(t)

    # The Downloads file may only cover thematic topics.  Read the
    # existing dst file (it has the placeholder skeletons for any
    # probniks not covered) and append those rows whose probnik_code
    # is NOT already covered.
    if DST.exists():
        with DST.open('r', encoding='utf-8') as fh:
            existing = json.load(fh)
        present_codes = {t['probnik_code'] for t in cleaned}
        appended = 0
        for t in existing:
            if t['probnik_code'] not in present_codes:
                # Re-clean any leftover status / null fields from the
                # previous skeleton run.
                t = dict(t)
                t.pop('status', None)
                if t.get('condition_md') in (None, ''):
                    t['condition_md'] = PH
                if t.get('idea_md') in (None, ''):
                    t['idea_md'] = PH
                if t.get('solution_md') in (None, ''):
                    t['solution_md'] = PH
                cleaned.append(t)
                appended += 1
        print(f'appended {appended} skeleton tasks for un-covered probniks')

    # Validate.
    TypeAdapter(list[TaskSchema]).validate_python(cleaned)

    DST.parent.mkdir(parents=True, exist_ok=True)
    with DST.open('w', encoding='utf-8') as fh:
        json.dump(cleaned, fh, ensure_ascii=False, indent=2)
        fh.write('\n')

    # Stats.
    by_probnik = {}
    for t in cleaned:
        by_probnik.setdefault(t['probnik_code'], 0)
        by_probnik[t['probnik_code']] += 1
    print('\ntasks per probnik:')
    for code in sorted(by_probnik):
        print(f'  {code}: {by_probnik[code]}')
    print(f'\nTOTAL: {len(cleaned)} tasks')


if __name__ == '__main__':
    main()
