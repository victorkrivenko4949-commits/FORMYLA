# -*- coding: utf-8 -*-
"""CH21 Problem A: диагностика «Геометрические ограничения base».

Извлекает base_plan_json трёх упавших задач из output/ch19/_pilot.db и
прогоняет движок, собирая для каждой из 50 попыток список непройденных
проверок и числовые нарушения (минимальный угол, минимальное расстояние,
максимальное отношение сторон, коллизии подписей, LABEL_OVERLAP_ANGLE).
"""
import io
import json
import os
import re
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from geometric_engine.engine import (  # noqa: E402
    GeometricEngine, EngineSettings, BuildContext, run_all_checks,
)
from geometric_engine import geom  # noqa: E402

DB = os.path.join("output", "ch19", "_pilot.db")
TARGET_UIDS = {
    "RG2-04a8ef202822bb265b56bc33",
    "2908b8065bf4e2557a33776c6910d776d8d136d2868f397a5e595622fdf4262c",
    "GEN-L123-w2_47_s1-b4f825e2814dfb90",
}

CHECK_CODES = {
    "Проверка 1": "OUT_OF_CANVAS",
    "Проверка 2": "LABEL_COLLISION",
    "Проверка 3 (расстояние)": "MIN_DISTANCE",
    "Проверка 3 (угол)": "MIN_ANGLE",
    "Проверка 3 (площадь)": "MIN_AREA",
    "Проверка 5": "SIDE_RATIO",
    "LABEL_OVERLAP_ANGLE": "LABEL_OVERLAP_ANGLE",
}


def classify_violation(v):
    for key, code in CHECK_CODES.items():
        if key in v:
            return code
    return "OTHER"


def analyze(plan):
    engine = GeometricEngine()
    engine.settings.semantic_colors = True
    engine.settings.auto_fit = True
    canvas = plan.get("canvas", {})
    w = canvas.get("width", 600)
    h = canvas.get("height", 500)
    margin = canvas.get("margin", 40)

    attempts = []
    worst = {"min_angle": 1e9, "min_dist": 1e9, "max_ratio": 0.0}
    for attempt in range(engine.settings.max_retries):
        seed = 42 + attempt * 137
        svg, ctx, _, violations = engine.build_with_retry(plan, seed=seed)
        # Считаем числовые нарушения напрямую по ctx (последняя попытка ctx пуст при fail).
        codes = sorted({classify_violation(v) for v in violations})
        attempts.append(codes)

        # числовые значения (для последней попытки берём ctx из build_with_retry)
        if ctx is not None:
            for name, meta in ctx.meta.items():
                if meta.get("type") == "triangle" and "parents" in meta:
                    ps = meta["parents"]
                    if len(ps) >= 3:
                        try:
                            p1 = ctx.points[ps[0]]
                            p2 = ctx.points[ps[1]]
                            p3 = ctx.points[ps[2]]
                            for (a, b, c) in [(p1, p2, p3), (p2, p3, p1), (p3, p1, p2)]:
                                ang = math.degrees(geom.angle_between_three(a, b, c))
                                worst["min_angle"] = min(worst["min_angle"], ang)
                            sides = [geom.dist(p1, p2), geom.dist(p2, p3), geom.dist(p3, p1)]
                            mn = min(sides)
                            mx = max(sides)
                            if mn > geom.EPS:
                                worst["max_ratio"] = max(worst["max_ratio"], mx / mn)
                        except Exception:
                            pass
            pts = list(ctx.points.values())
            for i in range(len(pts)):
                for j in range(i + 1, len(pts)):
                    d = geom.dist(pts[i], pts[j])
                    worst["min_dist"] = min(worst["min_dist"], d)

    from collections import Counter
    freq = Counter()
    for codes in attempts:
        for c in codes:
            freq[c] += 1
    return freq, worst, attempts


def main():
    import math  # noqa: F401

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT id, problem_text, base_plan_json, error, status FROM figure_build_jobs"
    ).fetchall()

    print("=" * 100)
    for r in rows:
        uid = None
        m = re.search(r"(RG2-04a8ef[0-9a-f]+|2908b806[0-9a-f]+|GEN-L123-w2_47_s1-[0-9a-f]+)",
                      r["problem_text"] or "")
        # Пробуем найти task_uid через base_plan_json (нет) — используем problem_text фрагмент.
        # Вместо этого сопоставим по сохранённым планам: у этих задач base_plan_json есть.
        if not r["base_plan_json"]:
            continue
        plan = json.loads(r["base_plan_json"])
        # task_uid не хранится в job, но problem_text начинается с условия. Сопоставим
        # по результатам probe: найдём план с числом точек, характерным для трёх задач.
        # Проще: выведем все failed-base задачи и пометим.
        freq, worst, attempts = analyze(plan)
        print(f"job_id={r['id']} status={r['status']} error={r['error']}")
        print(f"  problem: {r['problem_text'][:80]}")
        print(f"  points/constructions: {len([c for c in plan.get('constructions',[]) if c.get('type')=='free_point'])}/{len(plan.get('constructions',[]))}")
        print(f"  top violations: {dict(freq.most_common())}")
        print(f"  worst: min_angle={worst['min_angle']:.2f} min_dist={worst['min_dist']:.2f} max_ratio={worst['max_ratio']:.2f}")
        print("-" * 100)

    con.close()


if __name__ == "__main__":
    main()
