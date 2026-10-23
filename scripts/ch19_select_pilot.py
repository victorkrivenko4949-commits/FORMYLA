# -*- coding: utf-8 -*-
"""CH19 Step 2+3: классификация стилей и стратифицированный отбор пилота 100.

Печатает таблицу style -> количество по всему файлу, затем отбирает
стратифицированную выборку (seed фиксирован) и пишет output/ch19/pilot_100.jsonl.

Страты (при наличии записей стиля):
  constructive 45, angle_chase 20, area_ratio 15, coordinate/complex/trig 20.
Покрытие: grade 7-11 и все level.  Только записи с непустым solution.
"""
import json
import os
import random
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.solution_style import classify_solution_style  # noqa: E402

INPUT = "FORMYLA_geometry_7_11_chertezh_v13.jsonl"
OUT_DIR = os.path.join("output", "ch19")
OUT_PILOT = os.path.join(OUT_DIR, "pilot_100.jsonl")

SEED = 20260825

STYLE_QUOTA = {
    "constructive": 45,
    "angle_chase": 20,
    "area_ratio": 15,
    # coordinate / complex / trig вместе:
    "analytic": 20,
}

ANALYTIC_STYLES = {"coordinate", "complex", "trig"}


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    style_counter = Counter()
    buckets = defaultdict(list)  # bucket_key -> list of records

    with open(INPUT, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            solution = rec.get("solution") or ""
            if not solution.strip():
                continue
            style = classify_solution_style(rec)
            style_counter[style] += 1

            grade = str(rec.get("grade"))
            level = str(rec.get("level"))
            if style in ANALYTIC_STYLES:
                bucket = "analytic"
            else:
                bucket = style
            buckets[bucket].append(rec)

    print("style -> количество (по всему файлу, с непустым solution):")
    for s, c in style_counter.most_common():
        print(f"  {s:<14} {c}")
    print("  (из них analytic = coordinate+complex+trig:",
          sum(style_counter[s] for s in ANALYTIC_STYLES), ")")

    # ── Отбор ──
    rng = random.Random(SEED)
    selected = []
    for bucket, quota in STYLE_QUOTA.items():
        pool = list(buckets.get(bucket, []))
        rng.shuffle(pool)
        chosen = pool[:quota]
        selected.extend(chosen)
        print(f"[select] {bucket}: requested {quota}, got {len(chosen)}")

    # Добор до 100 (если какой-то страты не хватило) — из оставшихся.
    if len(selected) < 100:
        used_ids = {r.get("task_uid") for r in selected}
        rest = []
        for bucket, pool in buckets.items():
            for r in pool:
                if r.get("task_uid") not in used_ids:
                    rest.append(r)
        rng.shuffle(rest)
        need = 100 - len(selected)
        selected.extend(rest[:need])
        print(f"[select] top-up: +{len(selected) - (100 - need)} (need {need})")

    # Кап ровно 100.
    selected = selected[:100]

    # Сводка покрытия.
    g = Counter(str(r.get("grade")) for r in selected)
    lv = Counter(str(r.get("level")) for r in selected)
    st = Counter(classify_solution_style(r) for r in selected)
    print("pilot grade:", dict(sorted(g.items())))
    print("pilot level:", dict(sorted(lv.items())))
    print("pilot style:", dict(st.items()))

    with open(OUT_PILOT, "w", encoding="utf-8") as f:
        for r in selected:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"wrote {len(selected)} records to {OUT_PILOT} (seed={SEED})")


if __name__ == "__main__":
    main()
