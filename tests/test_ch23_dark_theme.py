# -*- coding: utf-8 -*-
"""CH23 PART A: тёмная тема — фоновый rect, контрастные линии, без чёрного halo."""
import os
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from geometric_engine.engine import GeometricEngine, EngineSettings  # noqa: E402

NS = "{http://www.w3.org/2000/svg}"


def _build():
    engine = GeometricEngine()
    spec = {
        "canvas": {"width": 600, "height": 500, "margin": 40},
        "constructions": [
            {"type": "free_point", "id": "A", "x": 100, "y": 400},
            {"type": "free_point", "id": "B", "x": 500, "y": 400},
            {"type": "free_point", "id": "C", "x": 300, "y": 80},
            {"type": "triangle_arbitrary", "id": "tri_ABC", "p1": "A", "p2": "B", "p3": "C"},
            {"type": "segment", "id": "AB", "p1": "A", "p2": "B"},
        ],
    }
    svg, ctx = engine.build(spec)
    return svg


def test_background_rect_present():
    svg = _build()
    root = ET.fromstring(svg)
    rects = [e for e in root.iter(NS + "rect")]
    assert len(rects) >= 1
    bg = rects[0].get("fill")
    assert bg and bg.lower() not in ("none", "transparent")


def test_base_line_stroke_light():
    svg = _build()
    root = ET.fromstring(svg)
    # polygon — контур треугольника (base)
    pol = next(e for e in root.iter(NS + "polygon"))
    stroke = pol.get("stroke")
    assert stroke.upper() in ("#D9E5F5", "#C8D6E5", "#D9E5F5")


def test_text_no_black_halo():
    svg = _build()
    root = ET.fromstring(svg)
    texts = [e for e in root.iter(NS + "text")]
    assert texts
    for t in texts:
        stroke = (t.get("stroke") or "").upper()
        # обводка должна быть цветом фона, а не чёрным
        assert stroke != "#000000"
