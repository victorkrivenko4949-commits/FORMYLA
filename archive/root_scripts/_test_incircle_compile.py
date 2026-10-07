# -*- coding: utf-8 -*-
import io, sys, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from services.aux_compiler import compile_solver_aux
from services.figure_plan_validator import merge_base_aux
from geometric_engine.engine import GeometricEngine

# Реальный base_plan задачи 5429.
base_plan = {
    "constructions": [
        {"type": "free_point", "id": "A", "x": 120.0, "y": 140.0},
        {"type": "free_point", "id": "B", "x": 620.0, "y": 160.0},
        {"type": "free_point", "id": "C", "x": 340.0, "y": 520.0},
        {"type": "segment", "id": "AB", "p1": "A", "p2": "B"},
        {"type": "segment", "id": "BC", "p1": "B", "p2": "C"},
        {"type": "segment", "id": "AC", "p1": "A", "p2": "C"},
    ],
    "canvas": {"width": 800, "height": 600, "margin": 30},
}

# Реальный GPT-вывод для задачи 5429 (усечённо, достаточно для распознавания).
solver_result = {
    "steps": [
        {"no": 1, "text": "Проведём биссектрисы углов A и B треугольника ABC и обозначим их пересечение через O."},
        {"no": 2, "text": "Опустим из точки O перпендикуляры на стороны BC, CA и AB и обозначим основания через A_1', B_1' и C_1'."},
        {"no": 3, "text": "Построим окружность с центром O и радиусом OA_1'."},
    ],
    "aux_constructions": [
        {"op": "angle_bisector", "points": ["A", "B", "C"], "quote": "Проведём биссектрисы углов A и B", "step_no": 1},
        {"op": "angle_bisector", "points": ["B", "A", "C"], "quote": "Проведём биссектрисы углов A и B", "step_no": 1},
        {"op": "line_intersection", "points": ["A", "O", "B", "O"], "quote": "Проведём биссектрисы углов A и B", "step_no": 1},
        {"op": "perpendicular_through", "points": ["O", "B", "C"], "quote": "Опустим из точки O перпендикуляры", "step_no": 2},
        {"op": "perpendicular_through", "points": ["O", "C", "A"], "quote": "Опустим из точки O перпендикуляры", "step_no": 2},
        {"op": "perpendicular_through", "points": ["O", "A", "B"], "quote": "Опустим из точки O перпендикуляры", "step_no": 2},
        {"op": "circle_center_radius", "points": ["O", "A_1'"], "quote": "Построим окружность с центром O", "step_no": 3},
    ],
}

compiled, issues = compile_solver_aux(solver_result, base_plan)
print("=== COMPILED AUX PLAN ===")
print("has_aux:", compiled.get("has_aux"))
print("reason:", compiled.get("reason"))
print("issues:", issues)
for c in compiled.get("constructions", []):
    print("  ", c.get("type"), c.get("id"), {k: v for k, v in c.items() if k in ("p1","p2","p3","vertex","side_a","side_b","foot_id","center","radius_point")})

print()
print("=== ENGINE BUILD ===")
merged = merge_base_aux(base_plan, compiled)
eng = GeometricEngine()
try:
    svg, ctx = eng.build(merged)
    print("BUILD OK, svg length:", len(svg))
    print("points:", sorted(ctx.points.keys()))
    print("circles:", list(ctx.circles.keys()))
    print("has O:", 'aux_O' in ctx.points)
    # Проверим, что окружность реально вписана (радиус > 0).
    for cid, circ in ctx.circles.items():
        print(f"  circle {cid}: center={circ[0]}, r={circ[1]:.2f}")
except Exception as e:
    import traceback
    print("BUILD FAILED:", e)
    traceback.print_exc()
