# -*- coding: utf-8 -*-
"""Скрытая служебная точка, совпавшая с вершиной, не даёт предупреждений гейтов.

Задача с чертежа: ∠C = 60°, медиана AM = 6, BC = 12. Формализатор добавил
служебную D = divide_segment(B, C, 1.0) (калибровка длины) и отрезок BD;
D скрыта и совпадает с C. Раньше: «C и D совпали», «D лежит на BC», «M лежит на BD»,
«C–D на 0.00% габарита»."""
import math

import numpy as np

from geoexact.core.constructions import execute
from geoexact.core.gates import coincident_aliases, gate_correctness, gate_readability
from geoexact.core.schema import FigurePlan
from geoexact.core.solver import Solution


def _plan(hide_d: bool) -> FigurePlan:
    return FigurePlan.from_dict({
        "points": list("ABCMD"),
        "constructions": [{"op": "free_point", "out": n} for n in "ABC"] + [
            {"op": "midpoint", "out": "M", "args": ["B", "C"]},
            {"op": "divide_segment", "out": "D", "args": ["B", "C"], "value": 1.0}],
        "constraints": [],
        "draw": {"segments": [["A", "B"], ["B", "C"], ["C", "A"], ["A", "M"], ["B", "D"]],
                 "equal_marks": [{"pts": ["B", "M"], "count": 1}, {"pts": ["M", "C"], "count": 1}],
                 "hide_labels": ["D"] if hide_d else []},
        "target": {"kind": "none", "args": []},
        "scale_free": True})


_FREE = np.array([0.0, 0.0, 6 * math.sqrt(3), 0.0, 0.0, 6.0])


def test_hidden_duplicate_is_an_alias_and_silent():
    plan = _plan(hide_d=True)
    coords = execute(plan, free_values=_FREE)
    assert coincident_aliases(plan, coords) == {"D": "C"}
    sol = Solution(coords=coords, residual=0.0, ok=True)
    gc, gr = gate_correctness(plan, sol), gate_readability(plan, sol, strict=False)
    assert gc.ok and gr.ok
    noisy = [w for w in gc.warnings + gr.warnings if "D" in w.split(":", 1)[1]]
    assert noisy == [], noisy


def test_labelled_duplicate_still_warns():
    plan = _plan(hide_d=False)
    coords = execute(plan, free_values=_FREE)
    assert coincident_aliases(plan, coords) == {}
    gc = gate_correctness(plan, Solution(coords=coords, residual=0.0, ok=True))
    assert any(w.startswith("CONSTRUCTED_COINCIDENCE") for w in gc.warnings)
