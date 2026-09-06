# -*- coding: utf-8 -*-
"""Сгенерировать полный sample для прогона ВСЕГО датасета (362 задачи).

Все задачи датасета имеют решение → режим condition_solution (group='A').
"""
import io, os, sys, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from load_dataset import load_dataset, DEFAULT_INPUT

rows = load_dataset(DEFAULT_INPUT)
for r in rows:
    r["group"] = "A"  # все с решением -> condition_solution
out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out", "sample_full.jsonl")
os.makedirs(os.path.dirname(out_path), exist_ok=True)
with open(out_path, "w", encoding="utf-8") as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
print(f"full sample: {len(rows)} задач -> {out_path}")
