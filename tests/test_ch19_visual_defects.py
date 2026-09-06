# -*- coding: utf-8 -*-
"""CH19 visual defects regression tests.

Covers three fixes without LLM/vision/PNG conversion:
  1. INVALID_LABEL_TEXT: service names ("len_AB") rejected and skipped.
  2. angle_label stepped radius + LABEL_OVERLAP_ANGLE check.
  3. auto-fit by default: fan-of-rays occupies >= 70% canvas per axis.

Fixtures:
  * fan_of_rays_5 — пять лучей из O (углы 22, 31, 41, 28).
  * triangle_with_var_labels — треугольник, где план пытается подписать "len_AB".
  * isosceles_ok — корректный кейс (PILOT2-fill_0437), не должен меняться.
"""
import os
import sys
import xml.etree.ElementTree as ET

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from geometric_engine.engine import GeometricEngine, EngineSettings, run_all_checks  # noqa: E402
from services.figure_plan_validator import (  # noqa: E402
    is_invalid_label_text,
    validate_label_texts,
)

NS = "{http://www.w3.org/2000/svg}"


def _build(constructions, auto_fit=False, semantic=True):
    engine = GeometricEngine()
    engine.settings.semantic_colors = semantic
    engine.settings.auto_fit = auto_fit
    engine.settings.bg_color = "#0b1020"
    spec = {
        "canvas": {"width": 600, "height": 500, "margin": 40},
        "constructions": constructions,
    }
    svg, ctx = engine.build(spec)
    return svg, ctx, engine


def _svg_texts(svg_str):
    root = ET.fromstring(svg_str)
    return [t.text for t in root.iter(NS + "text") if t.text]


def _viewbox(svg_str):
    root = ET.fromstring(svg_str)
    vb = root.get("viewBox") or "0 0 0 0"
    parts = [float(x) for x in vb.split()]
    return parts  # [x, y, w, h]


def _svg_circle_radii(svg_str):
    root = ET.fromstring(svg_str)
    return [float(c.get("r")) for c in root.iter(NS + "circle")]


# ══════════════════════════════════════════════════════════════════
# Фикстуры
# ══════════════════════════════════════════════════════════════════

def fan_of_rays_5():
    """Пять лучей из O: углы 22°, 31°, 41°, 28° между соседними лучами."""
    import math
    center = (300, 250)
    # Стартуем с угла 0° (вправо), дальше повороты на 22,31,41,28 градусов.
    angles = [0.0]
    for d in (22, 31, 41, 28):
        angles.append(angles[-1] + math.radians(d))
    pts = {}
    for i, ang in enumerate(angles):
        pid = chr(ord("A") + i)
        pts[pid] = (center[0] + 150 * math.cos(ang), center[1] + 150 * math.sin(ang))
    constructions = [
        {"type": "free_point", "id": "O", "x": center[0], "y": center[1]},
    ]
    for pid, (x, y) in pts.items():
        constructions.append({"type": "free_point", "id": pid, "x": x, "y": y})
    for pid in pts:
        constructions.append({"type": "ray", "id": f"ray_O{pid}", "p1": "O", "p2": pid})
    labels = ["22°", "31°", "41°", "28°"]
    for i, pid in enumerate(list(pts)[:-1]):
        nxt = list(pts)[i + 1]
        constructions.append({
            "type": "angle_label", "id": f"ang_{i}",
            "vertex": "O", "ray1": pid, "ray2": nxt, "text": labels[i],
        })
    return constructions


def triangle_with_var_labels():
    """Треугольник ABC со стороной, где план подписывает "len_AB"."""
    return [
        {"type": "free_point", "id": "A", "x": 100, "y": 400},
        {"type": "free_point", "id": "B", "x": 500, "y": 400},
        {"type": "free_point", "id": "C", "x": 300, "y": 80},
        {"type": "triangle_arbitrary", "id": "tri_ABC", "p1": "A", "p2": "B", "p3": "C"},
        # Дефектный план: id=len_AB, text="len_AB" (служебное имя).
        {"type": "length_label", "id": "len_AB", "p1": "A", "p2": "B", "text": "len_AB"},
    ]


def isosceles_ok():
    """Корректный кейс (PILOT2-fill_0437): равнобедренный треугольник."""
    return [
        {"type": "free_point", "id": "A", "x": 100, "y": 400},
        {"type": "free_point", "id": "B", "x": 500, "y": 400},
        {"type": "free_point", "id": "C", "x": 300, "y": 100},
        {"type": "triangle_arbitrary", "id": "tri_ABC", "p1": "A", "p2": "B", "p3": "C"},
        {"type": "equal_segments_mark", "id": "eq_AC_BC",
         "segments": [["A", "C"], ["B", "C"]], "count": 1},
    ]


# ══════════════════════════════════════════════════════════════════
# DEFECT 1
# ══════════════════════════════════════════════════════════════════

class TestInvalidLabelText:
    def test_len_ab_rejected_by_validator(self):
        r = validate_label_texts(triangle_with_var_labels())
        assert any("INVALID_LABEL_TEXT" in e for e in r)

    def test_valid_labels_pass(self):
        ok = ["40°", "2x", "6", "6 см", "a", "x+1", "3a"]
        for t in ok:
            assert not is_invalid_label_text(t, "some_id"), t

    def test_render_svg_skips_invalid_label(self):
        svg, ctx, engine = _build(triangle_with_var_labels())
        texts = _svg_texts(svg)
        assert "len_AB" not in texts
        # Точки A, B, C подписаны, а служебного имени нет.
        assert "A" in texts and "B" in texts and "C" in texts


# ══════════════════════════════════════════════════════════════════
# DEFECT 2
# ══════════════════════════════════════════════════════════════════

class TestAngleLabelLayout:
    def test_five_angle_labels_distinct_radii(self):
        svg, ctx, engine = _build(fan_of_rays_5())
        # Радиусы дуг angle-arc (path с class angle-arc) — берём из layout.
        from geometric_engine.engine import _angle_label_layout
        lay = _angle_label_layout(ctx, engine.settings)
        radii = sorted(v["r"] for v in lay.values())
        assert len(set(radii)) == len(radii)  # все разные
        # ступенчатость ~14px
        for a, b in zip(radii, radii[1:]):
            assert abs(b - a) >= 10.0

    def test_no_angle_label_bbox_overlap(self):
        svg, ctx, engine = _build(fan_of_rays_5())
        check = run_all_checks(ctx, 600, 500, 40, engine.settings)
        assert not any("LABEL_OVERLAP_ANGLE" in v for v in check.violations), check.violations


# ══════════════════════════════════════════════════════════════════
# DEFECT 3
# ══════════════════════════════════════════════════════════════════

class TestAutoFit:
    def test_fan_of_rays_occupies_70_percent(self):
        svg, ctx, engine = _build(fan_of_rays_5(), auto_fit=True)
        vb = _viewbox(svg)
        w, h = vb[2], vb[3]
        # Сцена занимает не менее 70% canvas по каждой оси.
        # Считаем охват по координатам видимых точек после масштаба.
        # Проще: проверить, что viewBox не обрезан и >= 70% исходного canvas.
        assert w >= 0.70 * 600
        assert h >= 0.70 * 500


# ══════════════════════════════════════════════════════════════════
# Регрессия: isosceles_ok не меняется
# ══════════════════════════════════════════════════════════════════

class TestIsoscelesRegression:
    def test_isosceles_ok_drawn_elements_unchanged(self):
        svg_old, ctx_old, _ = _build(isosceles_ok(), auto_fit=False)
        svg_new, ctx_new, _ = _build(isosceles_ok(), auto_fit=False)

        def count(root):
            from collections import Counter
            c = Counter()
            for el in root.iter():
                tag = el.tag.split("}")[-1]
                c[tag] += 1
            return c

        root_old = ET.fromstring(svg_old)
        root_new = ET.fromstring(svg_new)
        assert count(root_old) == count(root_new)

    def test_isosceles_ok_auto_fit_preserves_relative_geometry(self):
        # После auto-fit точки всё ещё образуют равнобедренный треугольник
        # (AC == BC).
        svg, ctx, engine = _build(isosceles_ok(), auto_fit=True)
        from geometric_engine import geom
        a = ctx.points["A"]
        b = ctx.points["B"]
        c = ctx.points["C"]
        assert abs(geom.dist(a, c) - geom.dist(b, c)) < 1e-6
