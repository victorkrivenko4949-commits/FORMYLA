# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from services.aux_compiler import compile_solver_aux

base_plan = {
    "constructions": [
        {"type": "free_point", "id": "A"},
        {"type": "free_point", "id": "B"},
        {"type": "free_point", "id": "C"},
        {"type": "segment", "id": "AB", "p1": "A", "p2": "B"},
        {"type": "segment", "id": "BC", "p1": "B", "p2": "C"},
        {"type": "segment", "id": "AC", "p1": "A", "p2": "C"},
    ]
}

solver_result = {
    "steps": [
        {"text": "Проведём биссектрису угла B до пересечения со стороной AC в точке D."},
        {"text": "Из точки D опустим перпендикуляр на сторону AB."},
        {"text": "Построим окружность с центром в D и радиусом до точки касания."},
    ],
    "aux_constructions": [
        {"op": "angle_bisector", "points": ["A", "B", "C"], "quote": "биссектрису угла B", "step_no": 1},
        {"op": "circle_center_radius", "points": ["D", "E"], "quote": "окружность с центром", "step_no": 3},
    ],
}

plan, issues = compile_solver_aux(solver_result, base_plan)
print("has_aux:", plan.get("has_aux"))
print("reason:", repr(plan.get("reason")))
print("issues:", issues)
print("constructions:")
for c in plan.get("constructions", []):
    print("  ", c.get("type"), c.get("id"), {k: v for k, v in c.items() if k in ("vertex", "side_a", "side_b", "center", "radius_point", "p1", "p2", "p3")})
