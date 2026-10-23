# -*- coding: utf-8 -*-
"""Render task 2: right triangle ABC (angle C = 90°), M — midpoint of AB.
Solution adds circumcircle with diameter AB (center M) and radii MA, MB, MC."""
from geometric_engine.engine import GeometricEngine

BASE_PLAN = {
    "version": 2,
    "canvas": {"width": 600, "height": 500, "margin": 40},
    "constructions": [
        {"type": "free_point", "id": "A", "x": 150, "y": 100},
        {"type": "free_point", "id": "B", "x": 480, "y": 400},
        {"type": "free_point", "id": "C", "x": 150, "y": 400},
        {"type": "triangle_right", "id": "tri_ABC", "p1": "A", "p2": "C", "p3": "B"},
        {"type": "segment", "id": "AB", "p1": "A", "p2": "B"},
        {"type": "segment", "id": "BC", "p1": "B", "p2": "C"},
        {"type": "segment", "id": "CA", "p1": "C", "p2": "A"},
        {"type": "midpoint", "id": "M", "p1": "A", "p2": "B"},
        {"type": "right_angle_mark", "id": "right_C", "p1": "A", "p2": "C", "p3": "B"},
        {"type": "point_label", "id": "lbl_A", "p1": "A", "label": "A", "side": "top_left"},
        {"type": "point_label", "id": "lbl_B", "p1": "B", "label": "B", "side": "bottom_right"},
        {"type": "point_label", "id": "lbl_C", "p1": "C", "label": "C", "side": "bottom_left"},
        {"type": "point_label", "id": "lbl_M", "p1": "M", "label": "M", "side": "bottom"},
    ],
}

AUX_CONSTRUCTIONS = [
    {
        "type": "circumcircle",
        "id": "aux_circumcircle",
        "p1": "A",
        "p2": "B",
        "p3": "C",
        "dashed": True,
        "style": "aux",
        "purpose": "Окружность с диаметром AB (проходит через C, т.к. угол C прямой)",
        "solution_evidence": {
            "step_no": 1,
            "quote": "Проведём окружность с диаметром AB",
        },
    },
    {
        "type": "segment",
        "id": "aux_MA",
        "p1": "M",
        "p2": "A",
        "dashed": True,
        "style": "aux",
        "purpose": "Радиус MA окружности",
        "solution_evidence": {
            "step_no": 4,
            "quote": "MA, MB и MC являются радиусами одной окружности",
        },
    },
    {
        "type": "segment",
        "id": "aux_MB",
        "p1": "M",
        "p2": "B",
        "dashed": True,
        "style": "aux",
        "purpose": "Радиус MB окружности",
        "solution_evidence": {
            "step_no": 4,
            "quote": "MA, MB и MC являются радиусами одной окружности",
        },
    },
    {
        "type": "segment",
        "id": "aux_MC",
        "p1": "M",
        "p2": "C",
        "dashed": True,
        "style": "aux",
        "purpose": "Радиус MC окружности",
        "solution_evidence": {
            "step_no": 4,
            "quote": "MA, MB и MC являются радиусами одной окружности",
        },
    },
]


def main():
    engine = GeometricEngine()
    engine.settings.bg_color = "#0f172a"

    base_svg, _, _, base_viol = engine.build_with_retry(BASE_PLAN)
    print("base violations:", base_viol)
    with open("demo2_base.svg", "w", encoding="utf-8") as f:
        f.write(base_svg)

    merged = dict(BASE_PLAN)
    merged["constructions"] = list(BASE_PLAN["constructions"]) + AUX_CONSTRUCTIONS
    aux_svg, _, _, aux_viol = engine.build_with_retry(merged)
    print("aux violations:", aux_viol)
    with open("demo2_aux.svg", "w", encoding="utf-8") as f:
        f.write(aux_svg)

    print("Wrote demo2_base.svg and demo2_aux.svg")


if __name__ == "__main__":
    main()
