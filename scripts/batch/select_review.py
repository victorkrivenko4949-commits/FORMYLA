# -*- coding: utf-8 -*-
"""scripts/batch/select_review.py — блок 6: визуальная выборка 20 SVG.

Отбирает:
  * 10 SVG с trust_level=verified и aux (лучший случай);
  * 5 SVG с aux_dropped (почему отбросили?);
  * 5 из ячейки «solver match / measured mismatch» (D1).

Копирует SVG в out/review/<task_id>_<grade>_<trust_level>.svg
и пишет out/review/review_index.md.

Использует модуль сверки ответов из analyze.py (без его main).
"""
from __future__ import annotations

import os
import re
import sys
import json

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_OUT_DIR = os.path.join(_SCRIPT_DIR, "out")
_REVIEW_DIR = os.path.join(_OUT_DIR, "review")
RESULTS_PATH = os.path.join(_OUT_DIR, "results.jsonl")
SAMPLE_PATH = os.path.join(_OUT_DIR, "sample_100.jsonl")

# Импорт функций сверки из analyze.py (без запуска main).
sys.path.insert(0, _SCRIPT_DIR)
from analyze import (  # noqa: E402
    load_jsonl,
    compare_answers,
)


def _sanitize(tid: str) -> str:
    return re.sub(r"[^A-Za-z0-9_\-]+", "_", str(tid))


def _svg_filename(r: dict) -> str:
    tid = _sanitize(r.get("task_id"))
    grade = r.get("grade")
    trust = r.get("trust_level") or "none"
    return f"{tid}_{grade}_{trust}.svg"


def main() -> int:
    results = load_jsonl(RESULTS_PATH)
    sample = load_jsonl(SAMPLE_PATH)
    if not results:
        print("[review] results.jsonl пуст.", file=sys.stderr)
        return 1

    # Справочник условий по task_id.
    cond_map = {r.get("task_id"): r.get("condition") for r in sample}

    # ── Категории ──
    best = [r for r in results
            if r.get("trust_level") == "verified"
            and (r.get("has_aux") or r.get("aux_source") in ("template", "solver"))
            and r.get("svg_path")][:10]

    dropped = [r for r in results
               if r.get("aux_status") == "AUX_DROPPED"
               and r.get("svg_path")][:5]

    d1 = []
    for r in results:
        ds = r.get("dataset_answer")
        sol = r.get("solver_answer")
        meas = r.get("measured_answer")
        if ds not in (None, "") and sol not in (None, "") and meas not in (None, ""):
            if compare_answers(ds, sol) == "match" and compare_answers(ds, meas) == "mismatch":
                if r.get("svg_path"):
                    d1.append(r)
    d1 = d1[:5]

    selected = best + dropped + d1
    os.makedirs(_REVIEW_DIR, exist_ok=True)

    index_lines = [
        "# Review index — визуальная выборка 20 SVG\n",
        f"- Лучший случай (verified + aux): {len(best)}",
        f"- aux_dropped: {len(dropped)}",
        f"- D1 (solver match / measured mismatch): {len(d1)}\n",
    ]

    copied = 0
    for r in selected:
        fname = _svg_filename(r)
        svg = r.get("svg_path")
        if svg:
            # svg_path хранит либо путь к файлу, либо inline-SVG (XML-строку).
            if isinstance(svg, str) and svg.lstrip().startswith("<?xml"):
                content = svg
            else:
                try:
                    with open(svg, "r", encoding="utf-8") as src:
                        content = src.read()
                except (FileNotFoundError, OSError):
                    content = None
            if content:
                with open(os.path.join(_REVIEW_DIR, fname), "w", encoding="utf-8") as dst:
                    dst.write(content)
                copied += 1
        index_lines.append(f"## {fname}\n")
        index_lines.append(f"- task_id: `{r.get('task_id')}`")
        index_lines.append(f"- класс: {r.get('grade')}, группа: {r.get('group')}")
        index_lines.append(f"- trust_level: {r.get('trust_level')}")
        index_lines.append(f"- aux_source: {r.get('aux_source')}, aux_status: {r.get('aux_status')}")
        index_lines.append(f"- aux_dropped_reason: {r.get('aux_dropped_reason')}")
        index_lines.append(f"- dataset_answer: `{r.get('dataset_answer')}`")
        index_lines.append(f"- solver_answer: `{r.get('solver_answer')}`")
        index_lines.append(f"- measured_answer: `{r.get('measured_answer')}`")
        index_lines.append(f"- answer_verdict: `{r.get('answer_verdict')}`")
        index_lines.append(f"- aux_template_id: `{r.get('aux_template_id')}`")
        # aux-построения (из стадий aux_compile/aux_usefulness не сохраняются текстом;
        # берём aux_reason если есть).
        index_lines.append("")
        index_lines.append(f"Условие: {cond_map.get(r.get('task_id'), '(нет)')[:400]}")
        index_lines.append("")

    with open(os.path.join(_REVIEW_DIR, "review_index.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(index_lines))

    print(f"[review] отобрано: {len(selected)} (скопировано SVG: {copied})")
    print(f"[review] индекс: {os.path.join(_REVIEW_DIR, 'review_index.md')}")
    print(f"[review] best={len(best)} dropped={len(dropped)} d1={len(d1)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
