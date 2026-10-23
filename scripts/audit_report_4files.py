# -*- coding: utf-8 -*-
"""Сводка по 4 файлам двойного аудита (FORMYLA_1_4_AUDIT_*)."""
import json
import os
from collections import Counter

FILES = [
    "FORMYLA_1_4_AUDIT_BOTH_CORRECT.jsonl",
    "FORMYLA_1_4_AUDIT_BOTH_INCORRECT.jsonl",
    "FORMYLA_1_4_AUDIT_DISPUTED.jsonl",
    "FORMYLA_1_4_AUDIT_ERROR.jsonl",
]

total = 0
print("=" * 70)
for path in FILES:
    if not os.path.exists(path):
        print(f"[skip] {path}")
        continue
    n = 0
    grades = Counter()
    levels = Counter()
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            n += 1
            try:
                d = json.loads(line)
            except Exception:
                continue
            t = d.get("task") or {}
            grades[str(t.get("grade"))] += 1
            levels[str(t.get("level"))] += 1
    total += n
    print(f"{path}: {n}")
    print(f"   grade: {dict(sorted(grades.items(), key=lambda x: (int(x[0]) if x[0].isdigit() else 999, x[0])))}")
    print(f"   level: {dict(sorted(levels.items()))}")
print("=" * 70)
print(f"ИТОГО по 4 файлам: {total} задач")
