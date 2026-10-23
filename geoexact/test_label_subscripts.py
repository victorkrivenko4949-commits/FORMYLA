"""Подписи точек с индексами: B_1 -> B с нижним индексом 1 (только оформление)."""
import re
import xml.etree.ElementTree as ET

import numpy as np

from geoexact.core import label_subscripts as ls, render
from geoexact.core.schema import FigurePlan
from geoexact.core.solver import Solution

NS = "{http://www.w3.org/2000/svg}"


def test_split_label():
    assert ls.split_label("B_1") == ("B", "1", True)
    assert ls.split_label("K_12") == ("K", "12", True)
    assert ls.split_label("C1") == ("C", "1", True)
    assert ls.split_label("I_A") == ("I", "A", False)
    for plain in ("A", "AB", "A'", "ℓ", "M_", "_1", "A_123"):
        assert ls.split_label(plain) is None


def test_subscript_labels_rewrites_only_point_labels():
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><g id="labels">'
           '<circle class="pt" data-point="B_1" cx="1" cy="1" r="3"/>'
           '<text class="lab" data-point="B_1" x="1" y="2">B_1</text>'
           '<text class="lab" data-point="I_A" x="1" y="2">I_A</text>'
           '<text class="lab" data-point="A" x="1" y="2">A</text>'
           '<text class="mark" x="1" y="2">B_1</text></g></svg>')
    out = ls.subscript_labels(svg)
    root = ET.fromstring(out)
    labs = {t.get("data-point"): t for t in root.iter(NS + "text") if t.get("class") == "lab"}
    assert labs["B_1"].text == "B" and labs["B_1"][0].text == "1"
    assert labs["B_1"][0].get("font-style") == "normal"
    assert labs["I_A"].text == "I" and labs["I_A"][0].text == "A" and labs["I_A"][0].get("font-style") is None
    assert labs["A"].text == "A" and len(labs["A"]) == 0
    marks = [t for t in root.iter(NS + "text") if t.get("class") == "mark"]
    assert marks[0].text == "B_1"                       # подписи-метки не трогаем
    assert 'data-point="B_1"' in out                    # атрибуты для UI/тестов сохранены
    assert ls.subscript_labels(out) == out              # идемпотентно


def test_broken_or_plain_svg_is_returned_unchanged():
    assert ls.subscript_labels("<svg><text class=\"lab\">B_1</text>") == "<svg><text class=\"lab\">B_1</text>"
    plain = '<svg xmlns="http://www.w3.org/2000/svg"><text class="lab">A</text></svg>'
    assert ls.subscript_labels(plain) == plain


def test_render_wrapper_installed_and_applied():
    assert getattr(render.render_svg, "_label_subscripts", False)
    plan = FigurePlan.from_dict({
        "points": ["A", "B", "C", "M_1"],
        "constructions": [*({"op": "free_point", "out": p} for p in "ABC"),
                          {"op": "midpoint", "out": "M_1", "args": ["B", "C"]}],
        "constraints": [],
        "draw": {"segments": [["A", "B"], ["B", "C"], ["C", "A"], ["A", "M_1"]]},
        "target": {"kind": "none", "args": []}, "scale_free": True,
    })
    coords = {"A": np.array([0., 0.]), "B": np.array([4., 0.]), "C": np.array([1., 3.])}
    coords["M_1"] = (coords["B"] + coords["C"]) / 2
    svg = render.render_svg(plan, Solution(coords=coords, residual=0.0, ok=True), gate=None, show_aux=False)
    assert 'data-point="M_1"' in svg
    assert re.search(r'<text class="lab" data-point="M_1"[^>]*>M<tspan[^>]*>1</tspan></text>', svg)
    assert ">M_1<" not in svg
