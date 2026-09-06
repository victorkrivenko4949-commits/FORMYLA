# -*- coding: utf-8 -*-
"""Проверить суммарное число задач во всех аудит-файлах."""
import json
import os

paths = [
    "FORMYLA_1_4_AUDIT_BOTH_CORRECT.jsonl",
    "FORMYLA_1_4_AUDIT_BOTH_INCORRECT.jsonl",
    "FORMYLA_1_4_AUDIT_DISPUTED.jsonl",
    "FORMYLA_1_4_AUDIT_ERROR.jsonl",
    "audit_l1_l3_results.json",
    "audit_l1_l3_failed.json",
    "audit_675_full_results.json",
    "audit_balanced_checkpoint.json",
    "L4L5_AUDIT_RESULTS.jsonl",
    "L4L5_FINAL_AUDIT.jsonl",
    "state_audit.jsonl",
    "EXPERT_AUDIT.jsonl",
]

out = []
grand = 0
for p in paths:
    if not os.path.exists(p):
        out.append(f"[skip] {p}")
        continue
    n = 0
    if p.endswith(".jsonl"):
        with open(p, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    n += 1
    else:
        try:
            d = json.load(open(p, encoding="utf-8"))
            n = len(d)
        except Exception as e:
            n = -1
            out.append(f"[err] {p}: {e}")
    grand += max(n, 0)
    out.append(f"{n:>8}  {p}")

out.append(f"{grand:>8}  TOTAL")
with open("_audit_total.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(out))
print("done")
