#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Найти все использования normalize_condition / normalized_or_original."""
import glob
import os

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(OUT, exist_ok=True)

pats = ["normalize_condition", "normalized_or_original"]
hits = []

paths = (
    glob.glob(os.path.join(BASE, "routes", "**", "*.py"), recursive=True)
    + glob.glob(os.path.join(BASE, "services", "**", "*.py"), recursive=True)
    + [os.path.join(BASE, "models.py")]
)

for f in paths:
    try:
        s = open(f, encoding="utf-8").read()
    except Exception:
        continue
    for p in pats:
        for i, l in enumerate(s.splitlines(), 1):
            if p in l:
                rel = os.path.relpath(f, BASE)
                hits.append(f"{rel}:{i}: {l.strip()}")

with open(os.path.join(OUT, "grep_normalize.txt"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(hits))

print(len(hits))
