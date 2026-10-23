# -*- coding: utf-8 -*-
import io, sys, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

files = [
    "FORMYLA_1_4_AUDIT_BOTH_CORRECT.jsonl",
    "FORMYLA_1_4_AUDIT_BOTH_INCORRECT.jsonl",
    "FORMYLA_1_4_AUDIT_DISPUTED.jsonl",
    "FORMYLA_1_4_AUDIT_ERROR.jsonl",
]
total = 0
for f in files:
    n = sum(1 for _ in open(f, encoding="utf-8")) if os.path.exists(f) else 0
    total += n
    print(f, "=>", n)
print("SUM:", total)
