# -*- coding: utf-8 -*-
"""scripts/ch19_manual_review.py — ручная выборка 30 задач (CH19 Step 6).

Копирует SVG в output/ch19/manual_review/:
  * 8 constructive с максимальным числом aux-объектов;
  * 6 случайных constructive;
  * 5 angle_chase;
  * 5 area_ratio;
  * 3 coordinate/complex/trig;
  * 3 с QA-предупреждениями.

В отчёте перечисляет task_uid, grade, style, число aux-объектов, описание.
"""
import argparse
import csv
import json
import os
import random
import re
import shutil
import sys
from collections import defaultdict

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts.ch19_lib import aux_constructions, classify_solution_style  # noqa: E402

SEED = 20260825


def _safe(uid):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(uid))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join("output", "ch19"))
    ap.add_argument("--input", default=os.path.join("output", "ch19", "pilot_100.jsonl"))
    args = ap.parse_args()

    mr = os.path.join(args.out, "manual_review")
    os.makedirs(mr, exist_ok=True)

    results = {}
    with open(os.path.join(args.out, "results.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["status"] == "done":
                results[r["task_uid"]] = r

    recs = {}
    with open(args.input, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            recs[str(rec["task_uid"])] = rec

    # QA-предупреждения: task_uid с любым кодом.
    qa_uids = set()
    qa_path = os.path.join(args.out, "qa_report.md")
    if os.path.exists(qa_path):
        txt = open(qa_path, encoding="utf-8").read()
        # из секции "Сводка по задачам" извлекаем uid, где codes != OK
        for ln in txt.splitlines():
            if ln.startswith("| ") and "| OK" not in ln and "task_uid" not in ln \
                    and "---" not in ln and "код" not in ln:
                parts = [p.strip() for p in ln.strip("|").split("|")]
                if parts:
                    qa_uids.add(parts[0])

    # Подсчёт aux-объектов для done-задач.
    aux_ops = {}
    for uid, r in results.items():
        rec = recs.get(uid)
        if not rec:
            continue
        aux_plan_path = os.path.join(args.out, "plans", f"{_safe(uid)}_aux.json")
        aux_cs = []
        if os.path.exists(aux_plan_path):
            aux_cs = aux_constructions(open(aux_plan_path, encoding="utf-8").read())
        aux_ops[uid] = len(aux_cs)

    constructive = sorted(
        [uid for uid in results if classify_solution_style(recs.get(uid, {})) == "constructive"],
        key=lambda u: aux_ops.get(u, 0), reverse=True,
    )
    angle = [uid for uid in results if classify_solution_style(recs.get(uid, {})) == "angle_chase"]
    area = [uid for uid in results if classify_solution_style(recs.get(uid, {})) == "area_ratio"]
    analytic = [uid for uid in results
                if classify_solution_style(recs.get(uid, {})) in ("coordinate", "complex", "trig")]

    rng = random.Random(SEED)
    rng.shuffle(constructive)

    picks = []
    picks += constructive[:8]                      # 8 с макс aux
    # 6 случайных constructive (исключая уже взятые)
    rest_constructive = [u for u in constructive[8:] if u not in picks]
    rng.shuffle(rest_constructive)
    picks += rest_constructive[:6]

    rng.shuffle(angle)
    picks += angle[:5]
    rng.shuffle(area)
    picks += area[:5]
    rng.shuffle(analytic)
    picks += analytic[:3]

    # 3 с QA-предупреждениями (если есть)
    qa_available = [u for u in qa_uids if u in results and u not in picks]
    rng.shuffle(qa_available)
    picks += qa_available[:3]

    # Добор до 30.
    if len(picks) < 30:
        remaining = [u for u in results if u not in picks]
        rng.shuffle(remaining)
        picks += remaining[:30 - len(picks)]
    picks = picks[:30]

    lines = ["# CH19 — Ручная выборка 30 задач\n"]
    lines.append("| task_uid | grade | style | aux_objects | описание |")
    lines.append("|---|---|---|---|---|")
    for uid in picks:
        rec = recs.get(uid, {})
        style = classify_solution_style(rec)
        grade = rec.get("grade", "")
        stmt = (rec.get("statement") or "").replace("\n", " ")[:90]
        aops = aux_ops.get(uid, 0)
        lines.append(f"| {uid} | {grade} | {style} | {aops} | {stmt} |")

        # Копируем SVG.
        for suffix in ("_base.svg", "_aux.svg"):
            src = os.path.join(args.out, "svg", f"{_safe(uid)}{suffix}")
            if os.path.exists(src):
                shutil.copy(src, os.path.join(mr, f"{_safe(uid)}{suffix}"))

    with open(os.path.join(mr, "README.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"manual review: {len(picks)} задач, SVG скопированы в {mr}")


if __name__ == "__main__":
    main()
