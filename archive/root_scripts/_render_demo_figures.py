# -*- coding: utf-8 -*-
"""Render the demo task (isosceles triangle ABC, angle A=40°, altitude AH)
into two SVG files: base (condition only) and aux (with dashed altitude)."""
import json
from geometric_engine.engine import GeometricEngine

BASE_PLAN = {
    "version": 2,
    "canvas": {"width": 600, "height": 500, "margin": 40},
    "constructions": [
        {"type": "free_point", "id": "A", "x": 300, "y": 80},
        {"type": "free_point", "id": "B", "x": 120, "y": 400},
        {"type": "free_point", "id": "C", "x": 480, "y": 400},
        {"type": "triangle_isosceles", "id": "tri_ABC", "p1": "A", "p2": "B", "p3": "C"},
        {"type": "segment", "id": "AB", "p1": "A", "p2": "B"},
        {"type": "segment", "id": "AC", "p1": "A", "p2": "C"},
        {"type": "segment", "id": "BC", "p1": "B", "p2": "C"},
        {"type": "point_label", "id": "lbl_A", "p1": "A", "label": "A", "side": "top"},
        {"type": "point_label", "id": "lbl_B", "p1": "B", "label": "B", "side": "bottom_left"},
        {"type": "point_label", "id": "lbl_C", "p1": "C", "label": "C", "side": "bottom_right"},
    ],
    "assumptions": [],
}

AUX_CONSTRUCTIONS = [
    {
        "type": "altitude",
        "id": "aux_altitude_AH",
        "p1": "A",
        "p2": "B",
        "p3": "C",
        "dashed": True,
        "style": "aux",
        "purpose": "Высота AH (в равнобедренном треугольнике — биссектриса)",
        "solution_evidence": {
            "step_no": 1,
            "quote": "Проведём высоту AH из вершины A на сторону BC",
        },
    },
]


def main():
    engine = GeometricEngine()
    # Тёмный фон, чтобы светлые линии были видны при просмотре.
    engine.settings.bg_color = "#0f172a"

    base_svg, _, _, base_viol = engine.build_with_retry(BASE_PLAN)
    print("base violations:", base_viol)
    with open("demo_base.svg", "w", encoding="utf-8") as f:
        f.write(base_svg)

    merged = dict(BASE_PLAN)
    merged["constructions"] = list(BASE_PLAN["constructions"]) + AUX_CONSTRUCTIONS
    aux_svg, _, _, aux_viol = engine.build_with_retry(merged)
    print("aux violations:", aux_viol)
    with open("demo_aux.svg", "w", encoding="utf-8") as f:
        f.write(aux_svg)

    print("Wrote demo_base.svg and demo_aux.svg")


if __name__ == "__main__":
    main()
