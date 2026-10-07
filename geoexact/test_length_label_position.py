# -*- coding: utf-8 -*-
"""Подпись длины не прилипает к именованной точке на отрезке (например, к середине M)."""
import math
import re

import numpy as np

from geoexact.core.render import render_svg
from geoexact.core.schema import FigurePlan
from geoexact.core.solver import Solution


def _positions(svg, cls):
    return {t: (float(x), float(y)) for x, y, t in
            re.findall(r'<text class="' + cls + r'"[^>]*x="([^"]+)" y="([^"]+)"[^>]*>([^<]+)</text>', svg)}


def test_length_label_moves_away_from_midpoint_dot():
    plan = FigurePlan.from_dict({
        "points": list("ABCM"),
        "constructions": [{"op": "free_point", "out": n} for n in "ABC"]
        + [{"op": "midpoint", "out": "M", "args": ["B", "C"]}],
        "draw": {"segments": [["A", "B"], ["B", "C"], ["C", "A"], ["A", "M"]],
                 "length_marks": [{"pts": ["B", "C"], "text": "12"}, {"pts": ["A", "M"], "text": "6"}],
                 "angle_marks": [{"pts": ["A", "C", "B"], "text": "60°"}]},
        "target": {"kind": "none", "args": []},
        "scale_free": True})
    coords = {"A": np.array([0.0, 0.0]), "C": np.array([0.0, 6.0]),
              "B": np.array([6 * math.sqrt(3), 0.0])}
    coords["M"] = (coords["B"] + coords["C"]) / 2
    svg = render_svg(plan, Solution(coords=coords, residual=0.0, ok=True), gate=None, show_aux=False)
    marks = _positions(svg, "mark")
    dots = {n: (float(x), float(y)) for n, x, y in
            re.findall(r'<circle class="pt" data-point="([A-Z])"[^>]*cx="([^"]+)" cy="([^"]+)"', svg)}
    assert math.dist(marks["12"], dots["M"]) > 60      # раньше ≈ 14 px: читалось как «M = 12»
    assert math.dist(marks["6"], dots["M"]) > 25 and math.dist(marks["6"], dots["A"]) > 25
