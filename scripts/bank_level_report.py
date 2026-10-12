# -*- coding: utf-8 -*-
"""Отчёт по заполненности FORMYLA_BANK.jsonl: сколько задач на (класс, тема, уровень).

Запуск: python scripts/bank_level_report.py [--min 5] [--out reports/bank_level_report.md]
Ячейки, где задач меньше --min (дневной нормы), помечаются ❗ — там formyla_bank.get_tasks
вынужден добирать задачи соседних уровней.
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
    ap.add_argument("--min", type=int, default=5)
    ap.add_argument("--out", default=str(ROOT / "reports" / "bank_level_report.md"))
    args = ap.parse_args()

    counts = collections.Counter()
    texts = collections.defaultdict(set)
    levels_seen = set()
    total = bad = 0
    with open(args.bank, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                g = int(d["grade"]); lv = int(d["level"])
                topic = (d.get("topic") or "").strip()
            except Exception:
                bad += 1
                continue
            if not topic:
                bad += 1
                continue
            total += 1
            levels_seen.add(lv)
            counts[(g, topic, lv)] += 1
            t = (d.get("task_text") or d.get("statement") or "").strip()
            if t:
                texts[(g, topic, lv)].add(t)

    levels = sorted(levels_seen)
    keys = sorted({(g, t) for (g, t, _) in counts})

    out = []
    out.append(f"# FORMYLA_BANK.jsonl — заполненность по уровням\n")
    out.append(f"Всего строк: {total}, битых/без темы: {bad}. Уровни в банке: {levels}. "
               f"Порог нормы: {args.min} задач (❗ = меньше порога, будет добор из соседних уровней). "
               f"В скобках — уникальных текстов, если отличается от числа строк.\n")

    shortage = []
    for g in sorted({g for g, _ in keys}):
        out.append(f"\n## Класс {g}\n")
        out.append("| Тема | " + " | ".join(f"L{lv}" for lv in levels) + " |")
        out.append("|---|" + "---|" * len(levels))
        for gg, topic in keys:
            if gg != g:
                continue
            cells = []
            for lv in levels:
                n = counts.get((g, topic, lv), 0)
                u = len(texts.get((g, topic, lv), ()))
                cell = str(n) if u in (0, n) else f"{n} ({u})"
                if n < args.min:
                    cell = f"❗{cell}"
                    shortage.append((g, topic, lv, n))
                cells.append(cell)
            out.append(f"| {topic} | " + " | ".join(cells) + " |")

    out.append("\n## Ячейки ниже порога\n")
    if not shortage:
        out.append("Нет — во всех ячейках задач достаточно.")
    for g, topic, lv, n in shortage:
        out.append(f"- класс {g}, «{topic}», уровень {lv}: {n}")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
