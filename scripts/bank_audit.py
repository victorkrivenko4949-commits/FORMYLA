# -*- coding: utf-8 -*-
"""Аудит FORMYLA_BANK.jsonl: поиск конкретных ошибок в данных банка.

Проверки:
  A. position=None по ячейкам (класс, тема, уровень) — задачи позднего дозаполнения.
  B. «Школьные» формулировки на уровнях 3–4 (регулярки + очень короткие тексты).
  C. Один и тот же текст задачи в нескольких уровнях/классах/темах.
  D. Битые ответы: пустые, ссылки на другие задачи («та же что …»), «см. решение».
  E. Инверсия сложности: медианная длина текста на уровне 3 заметно меньше, чем на уровне 1.
Запуск: python scripts/bank_audit.py --out reports/bank_audit.md
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TRIVIAL_PATTERNS = [
    r"Найдите площадь (прямоугольника|квадрата|круга)",
    r"число\s*\\?pi\s*считайте|π\s*считайте|считайте равным",
    r"Катеты прямоугольного треугольника равны\s*\$?\d+\$?\s*и\s*\$?\d+\$?\.\s*Найдите гипотенузу",
    r"Найдите периметр (прямоугольника|квадрата)",
    r"^Вычислите:?\s*\$?[\d\s\+\-\*/\\cdot\.,]+\$?\.?$",
    r"^Решите уравнение\s*\$?\s*\d*\s*x\s*[\+\-]\s*\d+\s*=\s*\d+\s*\$?\.?$",
    r"Сколько будет",
    r"Найдите сумму чисел\s*\d+\s*и\s*\d+",
    r"Найдите площадь треугольника с основанием\s*\$?\d+\$?\s*и высотой",
]
TRIVIAL_RE = [re.compile(p, re.IGNORECASE) for p in TRIVIAL_PATTERNS]
BAD_ANSWER_RE = re.compile(r"(та же что|см\. решение|см\. выше|аналогично задаче|как в задаче)", re.IGNORECASE)
SHORT_LEN = 75


def text_of(d):
    return (d.get("task_text") or d.get("statement") or "").strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bank", default=str(ROOT / "FORMYLA_BANK.jsonl"))
    ap.add_argument("--out", default=str(ROOT / "reports" / "bank_audit.md"))
    args = ap.parse_args()

    rows = []
    with open(args.bank, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                d["_line"] = i
                d["_g"] = int(d["grade"]); d["_lv"] = int(d["level"])
                d["_t"] = (d.get("topic") or "").strip()
                d["_text"] = text_of(d)
                rows.append(d)
            except Exception:
                continue

    cells = collections.defaultdict(list)
    for d in rows:
        cells[(d["_g"], d["_t"], d["_lv"])].append(d)

    out = ["# Аудит FORMYLA_BANK.jsonl\n", f"Строк разобрано: {len(rows)}, ячеек: {len(cells)}.\n"]

    # A. position None
    out.append("\n## A. Задачи без position (позднее дозаполнение) — доля по ячейкам\n")
    out.append("| Класс | Тема | L1 | L2 | L3 | L4 |")
    out.append("|---|---|---|---|---|---|")
    none_total = 0
    for (g, t) in sorted({(k[0], k[1]) for k in cells}):
        cs = []
        for lv in (1, 2, 3, 4):
            items = cells.get((g, t, lv), [])
            n_none = sum(1 for d in items if d.get("position") is None)
            none_total += n_none
            cs.append(f"{n_none}/{len(items)}" if items else "—")
        out.append(f"| {g} | {t} | " + " | ".join(cs) + " |")
    out.append(f"\nВсего задач без position: {none_total} из {len(rows)}.")

    # B. trivial on L3-L4
    out.append("\n## B. «Школьные» формулировки на уровнях 3–4\n")
    trivial = []
    for d in rows:
        if d["_lv"] < 3:
            continue
        txt = d["_text"]
        hit = next((p.pattern for p in TRIVIAL_RE if p.search(txt)), None)
        if hit or len(txt) < SHORT_LEN:
            trivial.append((d, hit or f"короткий текст (<{SHORT_LEN} симв.)"))
    by_cell = collections.Counter((d["_g"], d["_t"], d["_lv"]) for d, _ in trivial)
    out.append(f"Найдено подозрительных: {len(trivial)}. По ячейкам:\n")
    out.append("| Класс | Тема | Уровень | Подозрительных / всего |")
    out.append("|---|---|---|---|")
    for (g, t, lv), n in sorted(by_cell.items(), key=lambda x: -x[1]):
        out.append(f"| {g} | {t} | {lv} | {n} / {len(cells[(g, t, lv)])} |")
    out.append("\nПримеры (до 60):\n")
    for d, why in trivial[:60]:
        out.append(f"- стр. {d['_line']} | {d['_g']} кл. | «{d['_t']}» | L{d['_lv']} | pos={d.get('position')} | {why}  \n  {d['_text'][:200]}")

    # C. duplicates across cells
    out.append("\n## C. Один текст в нескольких ячейках\n")
    by_text = collections.defaultdict(list)
    for d in rows:
        if d["_text"]:
            by_text[d["_text"]].append(d)
    dups = {k: v for k, v in by_text.items() if len({(x["_g"], x["_t"], x["_lv"]) for x in v}) > 1}
    cross_level = sum(1 for v in dups.values() if len({x["_lv"] for x in v if True}) > 1)
    out.append(f"Текстов, встречающихся более чем в одной ячейке: {len(dups)} (из них с разными уровнями: {cross_level}).\n")
    for k, v in list(sorted(dups.items(), key=lambda kv: -len(kv[1])))[:40]:
        where = ", ".join(sorted({f"{x['_g']}кл/L{x['_lv']}/«{x['_t'][:25]}»" for x in v}))
        out.append(f"- {k[:120]}  \n  → {where}")

    # D. bad answers
    out.append("\n## D. Битые ответы\n")
    bad = [d for d in rows if not str(d.get("correct_answer") or "").strip() or BAD_ANSWER_RE.search(str(d.get("correct_answer") or ""))]
    out.append(f"Найдено: {len(bad)}\n")
    for d in bad[:40]:
        out.append(f"- стр. {d['_line']} | {d['_g']} кл. | «{d['_t']}» | L{d['_lv']} | ответ: «{str(d.get('correct_answer') or '')[:80]}»  \n  {d['_text'][:160]}")

    # E. inversion by median length
    out.append("\n## E. Инверсия сложности (медианная длина текста L3 < 0.6 × L1)\n")
    out.append("| Класс | Тема | медиана L1 | L2 | L3 | L4 |")
    out.append("|---|---|---|---|---|---|")
    inv = 0
    for (g, t) in sorted({(k[0], k[1]) for k in cells}):
        med = {}
        for lv in (1, 2, 3, 4):
            items = cells.get((g, t, lv), [])
            med[lv] = int(statistics.median(len(d["_text"]) for d in items)) if items else 0
        if med[1] and med[3] and med[3] < 0.6 * med[1]:
            inv += 1
            out.append(f"| {g} | {t} | {med[1]} | {med[2]} | **{med[3]}** | {med[4]} |")
    if not inv:
        out.append("| — | нет | | | | |")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out[:5]))


if __name__ == "__main__":
    main()
