# -*- coding: utf-8 -*-
"""Loads OLYMPIADS_DB from data/olympiads/olympiad_tasks_CLEAN.jsonl."""
import json
import os

_JSONL_PATH = os.path.join(os.path.dirname(__file__), 'data', 'olympiads', 'olympiad_tasks_CLEAN.jsonl')

OLYMPIADS_DB = []
OLYMPIADS_INFO = []

_PERFECT_JSON_PATH = os.path.join(os.path.dirname(__file__), 'olympiad_tasks_PERFECT.json')

try:
    try:
        with open(_JSONL_PATH, 'r', encoding='utf-8') as _f:
            for _line in _f:
                _line = _line.strip()
                if _line:
                    OLYMPIADS_DB.append(json.loads(_line))
        print(f"[olympiads.py] Loaded {len(OLYMPIADS_DB)} entries from JSONL")
    except FileNotFoundError:
        # JSONL заигнорен и на проде отсутствует; банк хранится в корне репо как JSON
        with open(_PERFECT_JSON_PATH, 'r', encoding='utf-8') as _f:
            OLYMPIADS_DB.extend(json.load(_f))
        print(f"[olympiads.py] JSONL not found, loaded {len(OLYMPIADS_DB)} entries from PERFECT JSON")
except FileNotFoundError:
    print(f"[olympiads.py] File not found: {_JSONL_PATH} / {_PERFECT_JSON_PATH}")
except Exception as _e:
    print(f"[olympiads.py] Error loading: {_e}")
