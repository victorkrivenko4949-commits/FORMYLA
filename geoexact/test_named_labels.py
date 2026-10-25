# -*- coding: utf-8 -*-
"""Названная в условии точка не может быть скрытой: подпись обязательна.

Прод-сценарий (задача 2, живая генерация 24.10.2026): «Медианы AA₁, BB₁ и
CC₁ пересекаются в точке M» — формализатор положил A_1/B_1/C_1 в
draw.hide_labels, на чертеже три безымянных кружка. Здесь: точки из текста
возвращаются из hide_labels, технические остаются скрытыми, обёртка
_strip_invented_labels применяется, рендер даёт подписи названных точек.
"""
import xml.etree.ElementTree as ET

import numpy as np

from geoexact.core import pipeline, render
from geoexact.core.named_labels import unhide_named_points, _names_in_text
from geoexact.core.schema import FigurePlan
from geoexact.core.solver import Solution

NS = "{http://www.w3.org/2000/svg}"

PROBLEM = ("В треугольнике ABC известно, что AB = 10, BC = 14, AC = 16. "
           "Медианы AA₁, BB₁ и CC₁ пересекаются в точке M. Найдите BM и MA₁.")


def _medians_plan(hide):
    return FigurePlan.from_dict({
        "points": ["A", "B", "C", "A_1", "B_1", "C_1", "M"],
        "constructions": [
            *({"op": "free_point", "out": p} for p in "ABC"),
            {"op": "midpoint", "out": "A_1", "args": ["B", "C"]},
            {"op": "midpoint", "out": "B_1", "args": ["A", "C"]},
            {"op": "midpoint", "out": "C_1", "args": ["A", "B"]},
            {"op": "centroid", "out": "M", "args": ["A", "B", "C"]},
        ],
        "constraints": [
            {"type": "dist", "args": ["A", "B"], "value": 10},
            {"type": "dist", "args": ["B", "C"], "value": 14},
            {"type": "dist", "args": ["A", "C"], "value": 16},
        ],
        "draw": {"segments": [["A", "B"], ["B", "C"], ["C", "A"],
                              ["A", "A_1"], ["B", "B_1"], ["C", "C_1"]],
                 "hide_labels": list(hide)},
        "target": {"kind": "none", "args": []},
        "scale_free": False,
    })


def test_names_in_text_extracts_subscript_variants():
    names = _names_in_text(PROBLEM)
    for n in ("A", "B", "C", "M", "A_1", "A1", "B_1", "C_1"):
        assert n in names, n


def test_unhide_named_points_returns_text_points():
    plan = _medians_plan(["A_1", "B_1", "C_1", "I"])
    unhide_named_points(PROBLEM, plan)
    assert plan.draw.hide_labels == ["I"]


def test_unhide_keeps_hidden_when_not_named():
    plan = _medians_plan(["X", "Y", "I"])
    unhide_named_points(PROBLEM, plan)
    assert plan.draw.hide_labels == ["X", "Y", "I"]


def test_strip_invented_labels_wrapper_installed():
    assert getattr(pipeline._strip_invented_labels, "_named_labels", False)
    assert pipeline.ENGINE_VERSION.count("+namedLabels1") == 1


def test_wrapper_via_strip_keeps_named_and_drops_invented():
    plan = _medians_plan(["A_1", "B_1", "C_1", "Zz9"])
    pipeline._strip_invented_labels(PROBLEM, plan)
    # названные в условии вернулись в подписи, техническая Zz9 убрана оригиналом
    assert "A_1" not in plan.draw.hide_labels
    assert "C_1" not in plan.draw.hide_labels


def test_render_shows_named_points_labels():
    plan = _medians_plan(["A_1", "B_1", "C_1"])
    pipeline._strip_invented_labels(PROBLEM, plan)
    coords = {"A": np.array([0., 0.]), "B": np.array([10., 0.]),
              "C": np.array([2.4, 6.4])}
    coords["A_1"] = (coords["B"] + coords["C"]) / 2
    coords["B_1"] = (coords["A"] + coords["C"]) / 2
    coords["C_1"] = (coords["A"] + coords["B"]) / 2
    coords["M"] = (coords["A"] + coords["B"] + coords["C"]) / 3
    sol = Solution(coords=coords, residual=0.0, ok=True)
    svg = render.render_svg(plan, sol)
    labels = {t.text.strip() for t in ET.fromstring(svg).iter(NS + "text")
              if t.get("class") == "lab"}
    for n in ("A", "B", "C", "M"):
        assert n in labels, n
    # A_1 после label_subscripts: база «A» + tspan «1»
    pts = {t.get("data-point") for t in ET.fromstring(svg).iter(NS + "text")
           if t.get("class") == "lab"}
    for n in ("A_1", "B_1", "C_1"):
        assert n in pts, n
