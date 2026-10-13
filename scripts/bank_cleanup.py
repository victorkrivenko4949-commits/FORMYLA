# -*- coding: utf-8 -*-
"""Чистка FORMYLA_BANK.jsonl от мусора.

Удаляются:
  R1  «школьные» задачи на уровнях 3–4 (строгие шаблоны серий: площадь прямоугольника/круга/
      квадрата, π=22/7, катеты→гипотенуза и площадь, диагонали ромба, основания трапеции,
      площадь квадрата→периметр, объём/поверхность куба, «прямоугольник N×M разрезали на
      равные части», «на клетчатой бумаге изображён … найдите площадь»);
  R2  дубли одного текста в разных ячейках — остаётся одно вхождение
      (минимальный уровень, затем минимальный класс, затем первая строка файла);
  R3  битые ответы (пустые или ссылки «та же что …», «см. решение»).

Без --apply банк не трогается: пишется план reports/bank_cleanup_plan.md и
reports/bank_cleanup_delete_lines.json. С --apply строки удаляются из FORMYLA_BANK.jsonl.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FULL = 35

TRIVIAL = [re.compile(p, re.IGNORECASE) for p in [
    r"Найдите площадь (прямоугольника|квадрата|круга)",
    r"число\s*\\?pi\s*считайте|π\s*считайте|считайте равным\s*22/7",
    r"Катеты прямоугольного треугольника равны\s*\$?\d+\$?\s*и\s*\$?\d+\$?\.\s*Найдите гипотенузу",
    r"^Диагонали ромба равны\s*\$?\d+\$?\s*и\s*\$?\d+\$?\.\s*Найдите площадь ромба\.?$",
    r"^Основания трапеции равны\s*\$?\d+\$?\s*и\s*\$?\d+\$?,\s*а высота\s*[—-]\s*\$?\d+\$?\.\s*Найдите площадь трапеции\.?$",
    r"^Площадь квадрата равна\s*\$?\d+\$?\.\s*Найдите его периметр\.?$",
    r"^Найдите площадь и периметр прямоугольника со сторонами",
    r"Найдите периметр (прямоугольника|квадрата)",
    r"^Ребро куба равно\s*\$?\d+\$?\.\s*Найдите (его )?(объём|площадь поверхности|диагональ)",
    r"^Найдите объём (куба|прямоугольного параллелепипеда|цилиндра|конуса|шара) ",
    r"^Найдите площадь поверхности (куба|прямоугольного параллелепипеда)",
    r"^Измерения прямоугольного параллелепипеда равны",
    r"^Радиус шара равен\s*\$?\d+\$?\.\s*Найдите",
    r"^Прямоугольник\s*\d+\s*[×x]\s*\d+\s*разрезали на\s*\d+\s*равных по площади частей",
    r"^На клетчатой бумаге изображён (прямоугольник|квадрат|прямоугольный треугольник)[^.]*\.\s*Найдите (его )?площадь",
    r"^Сколько будет",
    r"^Вычислите:?\s*\$?[\d\s\+\-\*/\\cdot\.,()]+\$?\.?$",
]]
BAD_ANSWER = re.compile(r"(та же что|см\. решение|см\. выше|аналогично задаче|как в задаче)", re.IGNORECASE)


def text_of(d):
    return (d.get("task_text") or d.get("statement") or "").strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bank", default=str(ROOT / "FORMYLA_BANK.jsonl"))
    ap.add_argument("--plan", default=str(ROOT / "reports" / "bank_cleanup_plan.md"))
    ap.add_argument("--lines", default=str(ROOT / "reports" / "bank_cleanup_delete_lines.json"))
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    raw_lines = Path(args.bank).read_text(encoding="utf-8").splitlines()
    rows = []
    for i, line in enumerate(raw_lines, 1):
        s = line.strip()
        if not s:
            continue
        try:
            d = json.loads(s)
            rows.append({"line": i, "g": int(d["grade"]), "lv": int(d["level"]),
                         "t": (d.get("topic") or "").strip(), "text": text_of(d),
                         "ans": str(d.get("correct_answer") or "").strip()})
        except Exception:
            continue

    delete = {}  # line -> reason

    # R1
    for r in rows:
        if r["lv"] >= 3 and any(p.search(r["text"]) for p in TRIVIAL):
            delete[r["line"]] = "R1 школьная формулировка на L%d" % r["lv"]

    # R3
    for r in rows:
        if r["line"] in delete:
            continue
        if not r["ans"] or BAD_ANSWER.search(r["ans"]):
            delete[r["line"]] = "R3 битый ответ: «%s»" % r["ans"][:60]

    # R2 — среди оставшихся
    by_text = collections.defaultdict(list)
    for r in rows:
        if r["line"] not in delete and r["text"]:
            by_text[r["text"]].append(r)
    for text, items in by_text.items():
        cells = {(x["g"], x["t"], x["lv"]) for x in items}
        if len(cells) <= 1:
            continue
        keep = min(items, key=lambda x: (x["lv"], x["g"], x["line"]))
        for x in items:
            if x is not keep:
                delete[x["line"]] = "R2 дубль (оставлен: %d кл, L%d, стр. %d)" % (keep["g"], keep["lv"], keep["line"])

    # holes
    before = collections.Counter((r["g"], r["t"], r["lv"]) for r in rows)
    after = collections.Counter((r["g"], r["t"], r["lv"]) for r in rows if r["line"] not in delete)
    all_cells = sorted({(r["g"], r["t"]) for r in rows})

    reasons = collections.Counter(v.split()[0] for v in delete.values())
    out = ["# План чистки FORMYLA_BANK.jsonl\n",
           f"Всего задач: {len(rows)}. К удалению: {len(delete)} "
           f"(R1 школьные: {reasons.get('R1', 0)}, R2 дубли: {reasons.get('R2', 0)}, R3 битые ответы: {reasons.get('R3', 0)}). "
           f"Останется: {len(rows) - len(delete)}.\n",
           f"Режим: {'ПРИМЕНЕНО — банк перезаписан' if args.apply else 'сухой прогон, банк не изменён'}.\n"]

    out.append("\n## Дырки после чистки (ячейки, где останется меньше 35)\n")
    out.append("| Класс | Тема | L1 | L2 | L3 | L4 | Не хватает до 35 |")
    out.append("|---|---|---|---|---|---|---|")
    total_missing = 0
    critical = []
    for g, t in all_cells:
        cells_vals = []
        missing = 0
        hole = False
        for lv in (1, 2, 3, 4):
            a = after.get((g, t, lv), 0)
            b = before.get((g, t, lv), 0)
            missing += max(0, FULL - a)
            mark = f"**{a}**" if a < FULL else str(a)
            if a < 5:
                critical.append((g, t, lv, a))
            if a < b:
                mark += f" (−{b - a})"
            if a < FULL:
                hole = True
            cells_vals.append(mark)
        if hole:
            total_missing += missing
            out.append(f"| {g} | {t} | " + " | ".join(cells_vals) + f" | {missing} |")
    out.append(f"\nВсего задач нужно догенерировать до полных 35: **{total_missing}**.")
    out.append(f"\nКритические ячейки (< 5 задач, дневная норма не набирается): {len(critical)}\n")
    for g, t, lv, a in critical:
        out.append(f"- {g} кл., «{t}», уровень {lv}: {a}")

    out.append("\n## Что удаляется (по ячейкам)\n")
    per_cell = collections.Counter()
    for r in rows:
        if r["line"] in delete:
            per_cell[(r["g"], r["t"], r["lv"], delete[r["line"]].split()[0])] += 1
    for (g, t, lv, rs), n in sorted(per_cell.items()):
        out.append(f"- {g} кл., «{t}», L{lv}, {rs}: {n}")

    out.append("\n## Список удаляемых строк\n")
    for r in rows:
        if r["line"] in delete:
            out.append(f"- стр. {r['line']} | {r['g']} кл. | «{r['t']}» | L{r['lv']} | {delete[r['line']]}  \n  {r['text'][:140]}")

    Path(args.plan).parent.mkdir(parents=True, exist_ok=True)
    Path(args.plan).write_text("\n".join(out) + "\n", encoding="utf-8")
    Path(args.lines).write_text(json.dumps(sorted(delete), ensure_ascii=False), encoding="utf-8")
    print("\n".join(out[:4]))

    if args.apply:
        kept = [line for i, line in enumerate(raw_lines, 1) if i not in delete]
        Path(args.bank).write_text("\n".join(kept) + "\n", encoding="utf-8")
        print(f"applied: removed {len(delete)} lines, kept {len(kept)}")


if __name__ == "__main__":
    main()
