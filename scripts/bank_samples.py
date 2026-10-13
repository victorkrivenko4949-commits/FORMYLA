# -*- coding: utf-8 -*-
"""Выгрузка примеров задач из FORMYLA_BANK.jsonl по уровням — для проверки калибровки сложности.

Запуск: python scripts/bank_samples.py --grade 9 --topic "Отрезки, отношения и площади" --n 5
"""
from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bank", default=str(ROOT / "FORMYLA_BANK.jsonl"))
    ap.add_argument("--grade", type=int, action="append", required=True)
    ap.add_argument("--topic", action="append", required=True)
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--out", default=str(ROOT / "reports" / "bank_samples.md"))
    args = ap.parse_args()

    want = {(g, t) for g in args.grade for t in args.topic}
    rows = collections.defaultdict(list)
    with open(args.bank, encoding="utf-8") as f:
        for line in f:
            try:
                d = json.loads(line)
                key = (int(d["grade"]), (d.get("topic") or "").strip())
            except Exception:
                continue
            if key in want:
                rows[(key[0], key[1], int(d["level"]))].append(d)

    out = ["# Примеры задач из FORMYLA_BANK.jsonl по уровням\n"]
    for g, t in sorted(want):
        out.append(f"\n## Класс {g} — «{t}»\n")
        for lv in (1, 2, 3, 4):
            items = rows.get((g, t, lv), [])
            out.append(f"\n### Уровень {lv} (всего {len(items)})\n")
            for d in items[: args.n]:
                text = (d.get("task_text") or d.get("statement") or "").strip().replace("\n", " ")
                ans = str(d.get("correct_answer") or "").strip().replace("\n", " ")
                out.append(f"- [pos {d.get('position')}] {text}  \n  **Ответ:** {ans}")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
