# -*- coding: utf-8 -*-
"""Новая точка доп. построения, совпавшая с существующей, — псевдоним, а не отказ.

Задача с чертежа: ∠C = 60°, медиана AM = 6, BC = 12 (∠A = 90°). Эксперт предлагает
«отметим D на BC так, что AD = AC»; при этих данных D совпадает с M (ΔACD правильный).
Раньше apply_aux отвечал «точка D совпадает с уже существующей», и слой доп.
построения пропадал целиком."""
import math

import numpy as np

from geoexact.core.auxplan import apply_aux
from geoexact.core.constructions import execute
from geoexact.core.schema import FigurePlan


def _figure():
    plan = FigurePlan.from_dict({
        "points": list("ABCM"),
        "constructions": [{"op": "free_point", "out": n} for n in "ABC"]
        + [{"op": "midpoint", "out": "M", "args": ["B", "C"]}],
        "constraints": [],
        "draw": {"segments": [["A", "B"], ["B", "C"], ["C", "A"], ["A", "M"]]},
        "target": {"kind": "none", "args": []},
        "scale_free": True})
    coords = execute(plan, free_values=np.array([0.0, 0.0, 6 * math.sqrt(3), 0.0, 0.0, 6.0]))
    return plan, coords


def test_coincident_point_becomes_alias_and_layer_survives():
    plan, coords = _figure()
    why = []
    out = apply_aux(plan, coords, {
        "idea": "Отметим D на BC так, что AD = AC.",
        "steps": [{"op": "line_circle", "out": "D", "args": ["B", "C", "A", "C"], "value": 0}],
        "aux_segments": [["A", "D"], ["D", "C"]]}, why)
    assert out is not None, why
    new_plan, new_coords = out
    assert "D" not in new_plan.points and "D" not in new_coords
    assert ["M", "C"] in new_plan.draw.aux_segments        # D C -> M C
    assert "D совпадает с M" in new_plan.notes


def test_alias_is_used_by_later_steps():
    plan, coords = _figure()
    why = []
    out = apply_aux(plan, coords, {
        "idea": "",
        "steps": [{"op": "line_circle", "out": "D", "args": ["B", "C", "A", "C"], "value": 1},
                  {"op": "midpoint", "out": "F", "args": ["D", "C"]}],
        "aux_segments": [["A", "F"]]}, why)
    assert out is not None, why
    f = next(c for c in out[0].constructions if c.out == "F")
    assert f.args == ["M", "C"]


def test_nothing_new_is_refused_with_the_coincidence_named():
    plan, coords = _figure()
    why = []
    out = apply_aux(plan, coords, {
        "idea": "x",
        "steps": [{"op": "line_circle", "out": "D", "args": ["B", "C", "A", "C"], "value": 0}],
        "aux_segments": [["A", "D"]]}, why)
    assert out is None
    assert why and "D = M" in why[0]
