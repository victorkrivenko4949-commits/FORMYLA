# -*- coding: utf-8 -*-
"""Generate CH15.1 figure 5: nine-point circle.

Base: acute triangle ABC (only the condition).
Aux (from solution): altitudes AD/BE/CF + orthocenter H; side midpoints M/N/L;
midpoints X/Y/Z of AH/BH/CH; circumcircle center O; K = midpoint of OH;
nine-point circle (center K through M).  No LLM/network.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from geometric_engine.engine import GeometricEngine
from geometric_engine import geom
from services.figure_plan_validator import validate_condition_solution, merge_base_aux

A = (140.0, 80.0)
B = (70.0, 480.0)
C = (590.0, 440.0)

# ── compute everything numerically ──
H = geom.orthocenter(A, B, C)
O = geom.circumcenter(A, B, C)
D = geom.foot_of_perpendicular(A, geom.line_through_points(B, C))
E = geom.foot_of_perpendicular(B, geom.line_through_points(C, A))
F = geom.foot_of_perpendicular(C, geom.line_through_points(A, B))
M = geom.midpoint(A, B)
N = geom.midpoint(B, C)
L = geom.midpoint(C, A)
X = geom.midpoint(A, H)
Y = geom.midpoint(B, H)
Z = geom.midpoint(C, H)
K = geom.midpoint(O, H)
R_circum = geom.dist(O, A)
R_nine = geom.dist(K, M)

base = {
    "version": 2,
    "canvas": {"width": 680, "height": 620, "margin": 55},
    "constructions": [
        {"type": "free_point", "id": "A", "x": A[0], "y": A[1]},
        {"type": "free_point", "id": "B", "x": B[0], "y": B[1]},
        {"type": "free_point", "id": "C", "x": C[0], "y": C[1]},
        {"type": "triangle_acute", "id": "tri_ABC", "p1": "A", "p2": "B", "p3": "C"},
        {"type": "segment", "id": "AB", "p1": "A", "p2": "B"},
        {"type": "segment", "id": "BC", "p1": "B", "p2": "C"},
        {"type": "segment", "id": "CA", "p1": "C", "p2": "A"},
    ],
}

def _free(pid, pt, side="auto", quote=None):
    return {
        "type": "free_point", "id": pid, "x": pt[0], "y": pt[1],
        "label": pid, "side": side,
        "style": "aux",
        "purpose": f"Точка {pid} (обозначена в решении)",
        "solution_evidence": {"step_no": 1, "quote": quote or f"Обозначим {pid}"},
    }

def _seg(pid, p1, p2, quote):
    return {
        "type": "segment", "id": pid, "p1": p1, "p2": p2,
        "dashed": True, "style": "aux",
        "purpose": pid, "solution_evidence": {"step_no": 1, "quote": quote},
    }

aux = {
    "has_aux": True,
    "reason": "Девять точек: основания высот, середины сторон и середины "
              "отрезков вершин с ортоцентром лежат на окружности девяти точек.",
    "constructions": [
        # feet of altitudes (explicitly "проведём высоты AD, BE и CF").
        _free("D", D, side="bottom", quote="Проведём высоты AD, BE и CF"),
        _free("E", E, quote="Проведём высоты AD, BE и CF"),
        _free("F", F, quote="Проведём высоты AD, BE и CF"),
        _seg("AD", "A", "D", "Проведём высоты AD, BE и CF"),
        _seg("BE", "B", "E", "Проведём высоты AD, BE и CF"),
        _seg("CF", "C", "F", "Проведём высоты AD, BE и CF"),
        {"type": "right_angle_mark", "id": "rD", "vertex": "D", "ray1": "A", "ray2": "B",
         "style": "aux", "purpose": "прямой угол при основании высоты",
         "solution_evidence": {"step_no": 1, "quote": "Проведём высоты AD, BE и CF"}},
        {"type": "right_angle_mark", "id": "rE", "vertex": "E", "ray1": "B", "ray2": "C",
         "style": "aux", "purpose": "прямой угол при основании высоты",
         "solution_evidence": {"step_no": 1, "quote": "Проведём высоты AD, BE и CF"}},
        {"type": "right_angle_mark", "id": "rF", "vertex": "F", "ray1": "C", "ray2": "A",
         "style": "aux", "purpose": "прямой угол при основании высоты",
         "solution_evidence": {"step_no": 1, "quote": "Проведём высоты AD, BE и CF"}},
        # orthocenter (explicitly "Обозначим через H точку их пересечения").
        {"type": "free_point", "id": "H", "x": H[0], "y": H[1], "label": "H",
         "side": "bottom", "style": "aux", "visual_role": "key_point",
         "purpose": "ортоцентр", "solution_evidence": {"step_no": 1, "quote": "Обозначим через H точку их пересечения"}},
        # side midpoints M/N/L (explicitly "Обозначим через M, N и L середины").
        _free("M", M), _free("N", N), _free("L", L),
        # midpoints X/Y/Z of AH/BH/CH.
        _free("X", X), _free("Y", Y), _free("Z", Z),
        # circumcircle center O (explicitly "обозначим её центр через O").
        _free("O", O),
        {"type": "circle_center_radius", "id": "circum_ABC", "center": "O", "radius": R_circum,
         "dashed": True, "style": "aux", "visual_role": "reference_circle",
         "purpose": "описанная окружность ABC",
         "solution_evidence": {"step_no": 4, "quote": "Построим описанную окружность треугольника ABC"}},
        # K = midpoint of OH.
        _free("K", K),
        # nine-point circle (center K through M).
        {"type": "circle_center_radius", "id": "nine_point", "center": "K", "radius": R_nine,
         "dashed": True, "style": "aux", "visual_role": "target_circle",
         "purpose": "окружность девяти точек (центр K, через M)",
         "solution_evidence": {"step_no": 6, "quote": "Построим окружность с центром K, проходящую через точку M"}},
    ],
}

inv = validate_condition_solution(base, aux)
print("VALIDATION valid=%s" % inv.get("valid"))
print("  errors:", inv.get("errors"))
print("  warnings:", inv.get("warnings"))

engine = GeometricEngine()
engine.settings.bg_color = "#070C18"
engine.settings.semantic_colors = True

base_svg, base_ctx, base_attempts, base_viol = engine.build_with_retry(base)
print("BASE attempts=%d violations=%s" % (base_attempts, base_viol))
open("ch151_f5_base.svg", "w", encoding="utf-8").write(base_svg)

merged = merge_base_aux(base, aux)
aux_svg, aux_ctx, aux_attempts, aux_viol = engine.build_with_retry(merged)
print("AUX attempts=%d violations=%s" % (aux_attempts, aux_viol))
open("ch151_f5_aux.svg", "w", encoding="utf-8").write(aux_svg)

print("aux points:", sorted(aux_ctx.points.keys()))
print("aux circles:", sorted(aux_ctx.circles.keys()))
print("R_circum=%.2f R_nine=%.2f" % (R_circum, R_nine))
