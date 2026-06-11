# -*- coding: utf-8 -*-
"""Показывает точный before/after для конкретных задач (для ревью безопасности)."""
import json, sys, difflib
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from services.latex_root_normalizer import normalize_roots

targets = {
    "data/olympiads/vsosh_10_11_full.json": ["G6.20", "A1.13", "A1.18", "F6.19", "C8.15"],
    "data/adaptive/adaptive_full_9120.json": [305, 324, 584, 7166],
}

def char_diff(a, b):
    sm = difflib.SequenceMatcher(None, a, b)
    out = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        out.append(f"      [{tag}] OLD={a[i1:i2]!r}  ->  NEW={b[j1:j2]!r}")
    return out

for rel, ids in targets.items():
    data = json.loads((ROOT/rel).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = [data]
    by = {}
    for it in data:
        if not isinstance(it, dict): continue
        k = it.get("number") or it.get("id")
        by[k] = it
    print(f"\n########## {rel} ##########")
    for tid in ids:
        it = by.get(tid)
        if not it:
            print(f"  (не найдено: {tid})"); continue
        print(f"\n----- {tid} -----")
        for fld in ("text","solution","idea","answer"):
            v = it.get(fld)
            if not isinstance(v, str) or not v: continue
            nv = normalize_roots(v)
            if nv != v:
                print(f"  поле .{fld}:")
                for line in char_diff(v, nv):
                    print(line)
