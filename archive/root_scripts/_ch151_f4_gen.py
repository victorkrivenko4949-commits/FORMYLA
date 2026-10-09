# -*- coding: utf-8 -*-
"""Generate CH15.1 figure 4: triangle with incircle (touch points D, E, F),
aux cevians AD, BE, CF and their concurrency point P (Ceva).  No LLM/network."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from geometric_engine.engine import GeometricEngine
from services.figure_plan_validator import validate_condition_solution, merge_base_aux

from geometric_engine import geom

A = (170.0, 120.0)
B = (140.0, 440.0)
C = (520.0, 170.0)

# Touch points (incircle_touch: p1 opposite the side where touch happens).
# D on BC, E on CA, F on AB.
D = geom.incircle_touch_point(A, B, C)   # touch on BC
E = geom.incircle_touch_point(B, C, A)   # touch on CA
F = geom.incircle_touch_point(C, A, B)   # touch on AB

# Concurrency point (Gergonne point): intersection of cevians AD and BE.
line_AD = geom.line_through_points(A, D)
line_BE = geom.line_through_points(B, E)
P = geom.intersect_lines(line_AD, line_BE)

# Choose a label side for P whose 14px-offset bbox avoids all three cevians.
_SIDES = ["top", "bottom", "left", "right",
          "top_left", "top_right", "bottom_left", "bottom_right"]
_OFFSETS = {
    "top": (0, -14), "bottom": (0, 14), "left": (-14, 0), "right": (14, 0),
    "top_left": (-14, -14), "top_right": (14, -14),
    "bottom_left": (-14, 14), "bottom_right": (14, 14),
}
_cevians = [(A, D), (B, E), (C, F)]


def _bbox_clear(center, segs, half_w=18.0, half_h=7.0, pad=2.0):
    x1, y1 = center[0] - half_w, center[1] - half_h
    x2, y2 = center[0] + half_w, center[1] + half_h
    for (p1, p2) in segs:
        # endpoint or midpoint inside expanded bbox (mirror engine check)
        for pt in (p1, p2, geom.midpoint(p1, p2)):
            if (x1 - pad) <= pt[0] <= (x2 + pad) and (y1 - pad) <= pt[1] <= (y2 + pad):
                return False
    return True


P_SIDE = "top_right"
for s in _SIDES:
    dx, dy = _OFFSETS[s]
    if _bbox_clear((P[0] + dx, P[1] + dy), _cevians):
        P_SIDE = s
        break
print("P =", P, "label side =", P_SIDE)

base = {
    "version": 2,
    "canvas": {"width": 640, "height": 560, "margin": 50},
    "constructions": [
        {"type": "free_point", "id": "A", "x": A[0], "y": A[1]},
        {"type": "free_point", "id": "B", "x": B[0], "y": B[1]},
        {"type": "free_point", "id": "C", "x": C[0], "y": C[1]},
        {"type": "triangle_arbitrary", "id": "tri_ABC", "p1": "A", "p2": "B", "p3": "C"},
        {"type": "segment", "id": "AB", "p1": "A", "p2": "B"},
        {"type": "segment", "id": "BC", "p1": "B", "p2": "C"},
        {"type": "segment", "id": "CA", "p1": "C", "p2": "A"},
        # Incircle (touch points stated in the condition -> free points).
        {"type": "incircle", "id": "incircle_ABC", "p1": "A", "p2": "B", "p3": "C"},
        {"type": "free_point", "id": "D", "x": D[0], "y": D[1]},
        {"type": "free_point", "id": "E", "x": E[0], "y": E[1]},
        {"type": "free_point", "id": "F", "x": F[0], "y": F[1]},
    ],
}

aux = {
    "has_aux": True,
    "reason": "Проведём прямые AD, BE и CF; их точка пересечения P (обратная теорема Чевы).",
    "constructions": [
        {
            "type": "segment", "id": "AD", "p1": "A", "p2": "D",
            "dashed": True, "style": "aux",
            "purpose": "Чевиана из вершины A в точку касания D",
            "solution_evidence": {"step_no": 1, "quote": "Проведём прямые AD, BE и CF"},
        },
        {
            "type": "segment", "id": "BE", "p1": "B", "p2": "E",
            "dashed": True, "style": "aux",
            "purpose": "Чевиана из вершины B в точку касания E",
            "solution_evidence": {"step_no": 1, "quote": "Проведём прямые AD, BE и CF"},
        },
        {
            "type": "segment", "id": "CF", "p1": "C", "p2": "F",
            "dashed": True, "style": "aux",
            "purpose": "Чевиана из вершины C в точку касания F",
            "solution_evidence": {"step_no": 1, "quote": "Проведём прямые AD, BE и CF"},
        },
        {
            "type": "intersect_lines", "id": "P", "line1": "AD", "line2": "BE",
            "label": "P", "side": P_SIDE, "style": "aux",
            "purpose": "Точка пересечения прямых AD и BE (обозначена в решении)",
            "solution_evidence": {"step_no": 1, "quote": "Обозначим через P точку пересечения прямых AD и BE"},
        },
    ],
}

inv = validate_condition_solution(base, aux)
print("VALIDATION valid=%s" % inv.get("valid"))
print("  errors:", inv.get("errors"))
print("  warnings:", inv.get("warnings"))

engine = GeometricEngine()
engine.settings.bg_color = "#070C18"

base_svg, base_ctx, base_attempts, base_viol = engine.build_with_retry(base)
print("BASE attempts=%d violations=%s" % (base_attempts, base_viol))
open("ch151_f4_base.svg", "w", encoding="utf-8").write(base_svg)

merged = merge_base_aux(base, aux)
aux_svg, aux_ctx, aux_attempts, aux_viol = engine.build_with_retry(merged)
print("AUX attempts=%d violations=%s" % (aux_attempts, aux_viol))
open("ch151_f4_aux.svg", "w", encoding="utf-8").write(aux_svg)

print("base points:", sorted(base_ctx.points.keys()))
print("aux points :", sorted(aux_ctx.points.keys()))
print("aux circles:", sorted(aux_ctx.circles.keys()))
print("P in aux points:", "P" in aux_ctx.points)
print("D/E/F in base points:", "D" in base_ctx.points, "E" in base_ctx.points, "F" in base_ctx.points)
