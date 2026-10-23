# -*- coding: utf-8 -*-
"""Generate CH15.1 figure 3: acute triangle with given altitudes AD, BE,
aux circle with diameter AB (Thales).  Deterministic, no LLM/network."""
import json
import math
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from geometric_engine.engine import GeometricEngine
from services.figure_plan_validator import validate_condition_solution, merge_base_aux

# Acute triangle: A top-left, B bottom, C top-right.
A = (150.0, 120.0)
B = (300.0, 430.0)
C = (520.0, 140.0)

base = {
    "version": 2,
    "canvas": {"width": 640, "height": 560, "margin": 50},
    "constructions": [
        {"type": "free_point", "id": "A", "x": A[0], "y": A[1]},
        {"type": "free_point", "id": "B", "x": B[0], "y": B[1]},
        {"type": "free_point", "id": "C", "x": C[0], "y": C[1]},
        {"type": "triangle_acute", "id": "tri_ABC", "p1": "A", "p2": "B", "p3": "C"},
        {"type": "segment", "id": "AB", "p1": "A", "p2": "B"},
        {"type": "segment", "id": "BC", "p1": "B", "p2": "C"},
        {"type": "segment", "id": "CA", "p1": "C", "p2": "A"},
        # Given altitudes (feet explicitly stated in the condition).
        {"type": "foot_perpendicular", "id": "D", "p1": "A", "line1": "BC"},
        {"type": "foot_perpendicular", "id": "E", "p1": "B", "line1": "CA"},
        {"type": "segment", "id": "AD", "p1": "A", "p2": "D"},
        {"type": "segment", "id": "BE", "p1": "B", "p2": "E"},
        # Right angles implied by the given heights.
        {"type": "right_angle_mark", "id": "right_D", "vertex": "D", "ray1": "A", "ray2": "B"},
        {"type": "right_angle_mark", "id": "right_E", "vertex": "E", "ray1": "B", "ray2": "A"},
    ],
    "given_marks": [
        {"type": "right_angle_mark", "vertex": "D", "ray1": "A", "ray2": "B"},
        {"type": "right_angle_mark", "vertex": "E", "ray1": "B", "ray2": "A"},
    ],
}

# Radius of circle with diameter AB = |AB| / 2.
ab = math.hypot(B[0] - A[0], B[1] - A[1])
radius = ab / 2.0

aux = {
    "has_aux": True,
    "reason": "Рассмотрим окружность с диаметром AB (по теореме Фалеса).",
    "constructions": [
        {
            "type": "midpoint", "id": "M", "p1": "A", "p2": "B",
            "style": "aux",
            "purpose": "Центр окружности с диаметром AB (середина диаметра)",
            "solution_evidence": {"step_no": 1, "quote": "Рассмотрим окружность с диаметром AB"},
        },
        {
            "type": "circle_center_radius", "id": "aux_circle_AB",
            "center": "M", "radius": radius,
            "dashed": True, "style": "aux",
            "purpose": "Окружность с диаметром AB, на которой лежат D и E",
            "solution_evidence": {"step_no": 1, "quote": "Рассмотрим окружность с диаметром AB"},
        },
    ],
}

inv = validate_condition_solution(base, aux)
print("VALIDATION valid=%s" % inv.get("valid"))
print("  errors:", inv.get("errors"))
print("  warnings:", inv.get("warnings"))

engine = GeometricEngine()
# Dark background for presentation (matches FORMYLA theme #070C18).
engine.settings.bg_color = "#070C18"

base_svg, base_ctx, base_attempts, base_viol = engine.build_with_retry(base)
print("BASE attempts=%d violations=%s" % (base_attempts, base_viol))
open("ch151_f3_base.svg", "w", encoding="utf-8").write(base_svg)

merged = merge_base_aux(base, aux)
aux_svg, aux_ctx, aux_attempts, aux_viol = engine.build_with_retry(merged)
print("AUX attempts=%d violations=%s" % (aux_attempts, aux_viol))
open("ch151_f3_aux.svg", "w", encoding="utf-8").write(aux_svg)

# Report key invariants.
print("base points:", sorted(base_ctx.points.keys()))
print("aux points :", sorted(aux_ctx.points.keys()))
print("aux circles:", sorted(aux_ctx.circles.keys()))
print("M in aux points:", "M" in aux_ctx.points)
print("D/E in base points:", "D" in base_ctx.points, "E" in base_ctx.points)
