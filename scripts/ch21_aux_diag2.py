# -*- coding: utf-8 -*-
"""CH21 PART 1: диагностика has_aux=0 по 8 задачам probe."""
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from services.solution_style import classify_solution_style  # noqa: E402

UIDS = [
    "GEN-L123-par27_s2-428077da17e93ad0",
    "RG2-04a8ef202822bb265b56bc33",
    "0d6906742da7dcdbf7993bd4b9b4ba15e42fa241098a8237a6d07be48344e02f",
    "2908b8065bf4e2557a33776c6910d776d8d136d2868f397a5e595622fdf4262c",
    "GEN-fill_0558",
    "REG-4b14f342d2a6f7a6331ee49b",
    "GEN-L123-par27_s6-2b10669528a0cfe7",
    "GEN-L123-w2_47_s1-b4f825e2814dfb90",
]

VERBS = ("провед", "соедин", "продл", "постро", "опуст", "впишем", "опишем",
         "обозначим точк", "отметим точк")


def main():
    recs = {}
    with open("output/ch19/pilot_100.jsonl", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            recs[d["task_uid"]] = d

    print("| task_uid | style | sol_len | verbs | statement_preview |")
    for uid in UIDS:
        r = recs.get(uid)
        if not r:
            print(f"| {uid} | NOT_FOUND | | | |")
            continue
        style = classify_solution_style(r)
        sol = r.get("solution") or ""
        sol_l = sol.lower()
        verbs = [v for v in VERBS if v in sol_l]
        print(f"| {uid[:20]} | {style} | {len(sol)} | {','.join(verbs) or '-'} | "
              f"{(r.get('statement') or '')[:40]} |")


if __name__ == "__main__":
    main()
