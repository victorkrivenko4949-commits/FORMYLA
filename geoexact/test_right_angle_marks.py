# -*- coding: utf-8 -*-
"""Прямые углы: один квадратик на перпендикуляр, серединный перпендикуляр отмечен.

Треугольник 13-14-15 с высотами, ортоцентром H, центром описанной окружности O и
серединой M стороны BC. Формализатор ставит прямые углы по обе стороны от каждой
высоты — два квадратика сливаются в «прямоугольник насквозь». OM ⊥ BC (серединный
перпендикуляр) раньше не отмечался вовсе."""
import numpy as np

from geoexact.core.annotations import dedupe_right_angles, mark_perpendiculars
from geoexact.core.schema import FigurePlan


def _figure():
    A, B, C = np.array([5.0, 12.0]), np.array([0.0, 0.0]), np.array([14.0, 0.0])

    def foot(P, X, Y):
        d = Y - X
        return X + float(np.dot(P - X, d) / np.dot(d, d)) * d

    O = np.array([7.0, 33.0 / 8.0])          # центр описанной окружности 13-14-15
    H = A + B + C - 2 * O
    coords = {"A": A, "B": B, "C": C, "A1": foot(A, B, C), "B1": foot(B, C, A),
              "C1": foot(C, A, B), "H": H, "O": O, "M": (B + C) / 2}
    plan = FigurePlan.from_dict({
        "points": list(coords),
        "constructions": [{"op": "free_point", "out": n} for n in coords],
        "constraints": [],
        "draw": {"segments": [["A", "B"], ["B", "C"], ["C", "A"], ["A", "A1"], ["B", "B1"],
                              ["C", "C1"], ["O", "M"]],
                 "right_angles": [["A", "C1", "C"], ["C", "C1", "B"], ["B", "A1", "A"],
                                  ["A", "A1", "C"], ["A", "B1", "B"]]},
        "target": {"kind": "none", "args": []},
        "scale_free": True})
    return plan, coords


def test_double_squares_collapse_to_one_per_foot():
    plan, coords = _figure()
    dedupe_right_angles(plan.draw, coords)
    feet = [m[1] for m in plan.draw.right_angles]
    assert sorted(feet) == ["A1", "B1", "C1"]


def test_perpendicular_bisector_gets_a_square():
    plan, coords = _figure()
    dedupe_right_angles(plan.draw, coords)
    added = mark_perpendiculars(plan.draw, coords)
    assert added >= 1
    assert any(m[1] == "M" and "O" in (m[0], m[2]) for m in plan.draw.right_angles)
    # повторный вызов ничего не добавляет
    assert mark_perpendiculars(plan.draw, coords) == 0
