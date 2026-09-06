# -*- coding: utf-8 -*-
"""scripts/batch/resume_geometry.py — восстановление прерванного прогона
датасета geometry 7-11 (362 задачи).

Контекст: «Provider Error 400» — это временная ошибка провайдера, которая
останавливает только ДИАЛОГ агента-оркестратора, а не сам конвейер. Конвейер
чекпоинтится на диск (out/results.jsonl, out/progress.jsonl, out/failed.jsonl,
out/svg_ready/*.svg, БД instance/formyla.db). Ничего не потеряно.

Этот скрипт делает ровно то, что нужно для продолжения:
  1) пересчитывает задачи, у которых ещё НЕТ готового SVG (свежий sample_missing);
  2) запускает идемпотентный run_batch.py ТОЛЬКО по недостающим задачам;
  3) итоги каждого прогона кладутся в отдельную папку (не затирают чужой results).

Запуск:
    python scripts/batch/resume_geometry.py            # только перегнать недостающие
    python scripts/batch/resume_geometry.py --limit N  # smoke-прогон первых N
"""
from __future__ import annotations

import argparse
import glob
import io
import json
import os
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(SCRIPT_DIR, "out")
SAMPLE_FULL = os.path.join(OUT_DIR, "sample_full.jsonl")
SAMPLE_MISSING = os.path.join(OUT_DIR, "sample_missing.jsonl")
SVG_DIR = os.path.join(OUT_DIR, "svg_ready")


def load_jsonl(path: str):
    if not os.path.exists(path):
        return []
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                out.append(obj)
    return out


def done_svg_task_ids() -> set:
    ids = set()
    for f in glob.glob(os.path.join(SVG_DIR, "*.svg")):
        base = os.path.basename(f).replace(".svg", "")
        # Имя файла: <task_id>_<класс>.svg  -> отрезаем только последний суффикс _N.
        ids.add(base.rsplit("_", 1)[0])
    return ids


def main() -> int:
    parser = argparse.ArgumentParser(description="Resume geometry 7-11 batch run")
    parser.add_argument("--limit", type=int, default=0, help="0 = все недостающие")
    parser.add_argument("--out-dir", default=os.path.join(OUT_DIR, "geom_resume"))
    parser.add_argument("--deadline-sec", type=float, default=240.0)
    args = parser.parse_args()

    full = load_jsonl(SAMPLE_FULL)
    if not full:
        print("[resume] sample_full.jsonl не найден. Сначала создайте выборку.",
              file=sys.stderr)
        return 1

    done = done_svg_task_ids()
    missing = [r for r in full if str(r.get("task_id")) not in done]
    print(f"[resume] dataset: {len(full)} задач; уже есть SVG: {len(done)}; "
          f"осталось: {len(missing)}")

    if not missing:
        print("[resume] Все задачи уже имеют готовый SVG — прогон не нужен.")
        return 0

    if args.limit > 0:
        missing = missing[: args.limit]
        print(f"[resume] ограничение --limit {args.limit} -> {len(missing)} задач")

    os.makedirs(os.path.dirname(SAMPLE_MISSING), exist_ok=True)
    with open(SAMPLE_MISSING, "w", encoding="utf-8") as f:
        for r in missing:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"[resume] sample_missing.jsonl -> {len(missing)} задач")

    cmd = [
        sys.executable,
        os.path.join(SCRIPT_DIR, "run_batch.py"),
        "--sample", SAMPLE_MISSING,
        "--out-dir", args.out_dir,
        "--deadline-sec", str(args.deadline_sec),
    ]
    print("[resume] запуск: " + " ".join(cmd))
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
