# -*- coding: utf-8 -*-
"""CH30 ЭТАП 1b Задача 3: проверка автовывода семантики на эталоне
(ортоцентр + окружность 9 точек) через обычный pipeline без ручных visual_role."""
import io
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from geometric_engine.engine import GeometricEngine  # noqa: E402
from geometric_engine import geom  # noqa: E402


def main():
    # Координаты как в _ch151_f5_gen.py.
    A = (140.0, 80.0)
    B = (70.0, 480.0)
    C = (590.0, 440.0)
    H = geom.orthocenter(A, B, C)
    O = geom.circumcenter(A, B, C)
    D = geom.foot_of_perpendicular(A, geom.line_through_points(B, C))
    E = geom.foot_of_perpendicular(B, geom.line_through_points(C, A))
    F = geom.foot_of_perpendicular(C, geom.line_through_points(A, B))
    M = geom.midpoint(A, B)
    N = geom.midpoint(B, C)
    L = geom.midpoint(C, A)
    K = geom.midpoint(O, H)
    R_circum = geom.dist(O, A)
    R_nine = geom.dist(K, M)

    # Base: без ручных visual_role — только free_point + triangle + segment.
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

    # Aux: без ручных visual_role / right_angle_mark — только построения.
    aux = {
        "has_aux": True,
        "reason": "Девять точек окружности Эйлера.",
        "constructions": [
            # Высоты через free_point + segment (как LLM), БЕЗ явных меток.
            {"type": "free_point", "id": "D", "x": D[0], "y": D[1], "style": "aux"},
            {"type": "free_point", "id": "E", "x": E[0], "y": E[1], "style": "aux"},
            {"type": "free_point", "id": "F", "x": F[0], "y": F[1], "style": "aux"},
            {"type": "segment", "id": "AD", "p1": "A", "p2": "D", "dashed": True, "style": "aux"},
            {"type": "segment", "id": "BE", "p1": "B", "p2": "E", "dashed": True, "style": "aux"},
            {"type": "segment", "id": "CF", "p1": "C", "p2": "F", "dashed": True, "style": "aux"},
            {"type": "free_point", "id": "H", "x": H[0], "y": H[1], "style": "aux"},
            {"type": "free_point", "id": "M", "x": M[0], "y": M[1], "style": "aux"},
            {"type": "free_point", "id": "N", "x": N[0], "y": N[1], "style": "aux"},
            {"type": "free_point", "id": "L", "x": L[0], "y": L[1], "style": "aux"},
            {"type": "free_point", "id": "O", "x": O[0], "y": O[1], "style": "aux"},
            {"type": "circle_center_radius", "id": "circum_ABC", "center": "O",
             "radius": R_circum, "dashed": True, "style": "aux"},
            {"type": "free_point", "id": "K", "x": K[0], "y": K[1], "style": "aux"},
            {"type": "circle_center_radius", "id": "nine_point", "center": "K",
             "radius": R_nine, "dashed": True, "style": "aux"},
        ],
    }

    from services.figure_plan_validator import merge_base_aux
    merged = merge_base_aux(base, aux)

    engine = GeometricEngine()
    engine.settings.semantic_colors = True
    engine.settings.bg_color = "#0F1729"
    svg, ctx = engine.build(merged)

    # Подсчёт авто-меток и ролей.
    right_marks = [o for o in ctx.objects if o.get("type") == "right_angle_mark"]
    circles = [(o.get("id"), ctx.meta.get(o.get("id"), {}).get("visual_role"))
               for o in ctx.objects
               if o.get("type") in ("circle_center_radius", "circumcircle", "incircle")]
    key_points = [n for n, m in ctx.meta.items()
                  if m.get("visual_role") == "key_point" and n in ctx.points]

    print("=== АВТОВЫВОД НА ЭТАЛОНЕ ===")
    print(f"right_angle_mark (авто): {len(right_marks)}")
    for r in right_marks:
        print("  ", r.get("vertex"), r.get("ray1"), r.get("ray2"))
    print(f"окружности и роли: {circles}")
    print(f"key_point: {key_points}")

    # Эталон вручную: 3 метки (rD/rE/rF), circum=reference_circle,
    # nine_point=target_circle, H=key_point.
    print()
    print("=== ЭТАЛОН (вручную из _ch151_f5_gen.py) ===")
    print("right_angle_mark: 3 (rD/rE/rF)")
    print("circum_ABC = reference_circle, nine_point = target_circle")
    print("key_point: H")


if __name__ == "__main__":
    main()
