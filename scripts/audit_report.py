# -*- coding: utf-8 -*-
"""Сводный отчёт по готовым результатам аудита задач (standalone DeepSeek)."""
import json
import os
from collections import Counter

FILES = ["audit_output.jsonl", "AUDIT1.jsonl", "AUDIT2.jsonl"]

for path in FILES:
    if not os.path.exists(path):
        print(f"[skip] {path} not found")
        continue
    total = 0
    parsed = 0
    cond = Counter()
    ans = Counter()
    sol = Counter()
    defects_total = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            total += 1
            try:
                d = json.loads(line)
            except Exception:
                continue
            parsed += 1
            cond[str(d.get("condition_correct"))] += 1
            ans[str(d.get("answer_correct"))] += 1
            sol[str(d.get("solution_correct"))] += 1
            defects_total += len(d.get("defects") or [])
    print("=" * 60)
    print(path)
    print("  строк всего:", total, "| JSON распарсено:", parsed)
    print("  condition_correct:", dict(cond))
    print("  answer_correct:   ", dict(ans))
    print("  solution_correct: ", dict(sol))
    print("  дефектов упомянуто:", defects_total)
    # Последняя строка для определения завершённости
    last = None
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                last = line
    if last:
        try:
            d = json.loads(last)
            print("  последний task_uid:", d.get("task_uid"))
        except Exception:
            print("  последняя строка не JSON")
