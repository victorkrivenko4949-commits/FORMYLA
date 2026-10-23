# -*- coding: utf-8 -*-
"""Merge DOUBLE_FAIL + DISPUTED + ERROR into one JSONL with category tag."""
import json

SOURCES = [
    ("BALANCED_DOUBLE_FAIL.jsonl", "double_fail"),
    ("BALANCED_DISPUTED.jsonl", "disputed"),
    ("BALANCED_ERROR.jsonl", "error"),
]
OUT = "BALANCED_ALL_PROBLEMS.jsonl"

total = 0
with open(OUT, "w", encoding="utf-8") as out:
    for path, category in SOURCES:
        n = 0
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                row["category"] = category
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
                n += 1
        print(f"{path}: {n}")
        total += n

print(f"TOTAL: {total} -> {OUT}")
