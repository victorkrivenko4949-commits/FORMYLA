# -*- coding: utf-8 -*-
"""CH16 semantic visual_role tests.

Deterministic. No LLM/network/vision/SVG->PNG.
"""
import sys
import os
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from geometric_engine.engine import GeometricEngine, EngineSettings
from geometric_engine.semantic_theme import (
    BASE_STROKE, AUX_STROKE, REFERENCE_CIRCLE, TARGET_CIRCLE,
    KEY_POINT, RIGHT_ANGLE, GIVEN_MARK, SECONDARY,
    resolve_visual_role, resolve_point_role,
)


NS = "{http://www.w3.org/2000/svg}"


def _build(constructions, semantic=True):
    engine = GeometricEngine()
    engine.settings.semantic_colors = semantic
    engine.settings.bg_color = "#070C18"
    spec = {
        "canvas": {"width": 640, "height": 560, "margin": 50},
        "constructions": constructions,
    }
    svg, ctx = engine.build(spec)
    return svg, ctx


def _strokes(svg_str):
    root = ET.fromstring(svg_str)
    out = []
    for el in root.iter(NS + "line"):
        out.append((el.get("class"), el.get("stroke")))
    for el in root.iter(NS + "circle"):
        if float(el.get("r")) > 5:
            out.append(("circle", el.get("stroke")))
    for el in root.iter(NS + "polyline"):
        out.append(("polyline", el.get("stroke")))
    return out


def _point_fills(svg_str):
    root = ET.fromstring(svg_str)
    out = []
    for el in root.iter(NS + "circle"):
        if float(el.get("r")) <= 5:
            out.append(el.get("fill"))
    return out


# ── 1. Unknown visual_role rejected ──
def test_unknown_visual_role_rejected():
    from services.figure_plan_validator import validate_condition_solution
    aux = {
        "has_aux": True, "reason": "x",
        "constructions": [{
            "type": "segment", "id": "s", "p1": "A", "p2": "B",
            "dashed": True, "style": "aux", "purpose": "x",
            "visual_role": "neon_pink",
            "solution_evidence": {"step_no": 1, "quote": "Проведём s"},
        }],
    }
    base = {
        "constructions": [
            {"type": "free_point", "id": "A", "x": 100, "y": 100},
            {"type": "free_point", "id": "B", "x": 300, "y": 100},
        ],
    }
    r = validate_condition_solution(base, aux)
    assert r["valid"] is False
    assert any("INVALID_VISUAL_ROLE" in e for e in r["errors"])


# ── 2. Direct color field rejected ──
def test_direct_color_field_rejected():
    from services.figure_plan_validator import validate_condition_solution
    aux = {
        "has_aux": True, "reason": "x",
        "constructions": [{
            "type": "segment", "id": "s", "p1": "A", "p2": "B",
            "dashed": True, "style": "aux", "purpose": "x",
            "stroke": "#ff0000",
            "solution_evidence": {"step_no": 1, "quote": "Проведём s"},
        }],
    }
    base = {
        "constructions": [
            {"type": "free_point", "id": "A", "x": 100, "y": 100},
            {"type": "free_point", "id": "B", "x": 300, "y": 100},
        ],
    }
    r = validate_condition_solution(base, aux)
    assert r["valid"] is False
    assert any("DIRECT_COLOR_FORBIDDEN" in e for e in r["errors"])


# ── 3. Base segment in merged aux SVG retains BASE_STROKE ──
def test_base_segment_retains_base_stroke():
    svg, _ = _build([
        {"type": "free_point", "id": "A", "x": 100, "y": 100},
        {"type": "free_point", "id": "B", "x": 300, "y": 100},
        {"type": "segment", "id": "AB", "p1": "A", "p2": "B"},
        # aux object present but base segment should stay base.
        {"type": "segment", "id": "aux_s", "p1": "A", "p2": "B",
         "dashed": True, "style": "aux"},
    ])
    assert (None, BASE_STROKE) in _strokes(svg)


# ── 4. Aux altitude gets AUX_STROKE ──
def test_aux_altitude_gets_aux_stroke():
    svg, _ = _build([
        {"type": "free_point", "id": "A", "x": 300, "y": 80},
        {"type": "free_point", "id": "B", "x": 120, "y": 400},
        {"type": "free_point", "id": "C", "x": 480, "y": 400},
        {"type": "altitude", "id": "alt", "vertex": "A", "side_a": "B",
         "side_b": "C", "foot_id": "H", "dashed": True, "style": "aux"},
    ])
    assert (None, AUX_STROKE) in _strokes(svg)


# ── 5. Auxiliary ordinary circle gets REFERENCE_CIRCLE ──
def test_aux_ordinary_circle_gets_reference_circle():
    svg, _ = _build([
        {"type": "free_point", "id": "A", "x": 150, "y": 150},
        {"type": "free_point", "id": "B", "x": 300, "y": 150},
        {"type": "midpoint", "id": "M", "p1": "A", "p2": "B"},
        {"type": "circle_center_radius", "id": "c", "center": "M", "radius": 120,
         "dashed": True, "style": "aux"},
    ])
    assert ("circle", REFERENCE_CIRCLE) in _strokes(svg)


# ── 6. target_circle gets TARGET_CIRCLE ──
def test_target_circle_color():
    svg, _ = _build([
        {"type": "free_point", "id": "A", "x": 150, "y": 150},
        {"type": "free_point", "id": "B", "x": 300, "y": 150},
        {"type": "midpoint", "id": "M", "p1": "A", "p2": "B"},
        {"type": "circle_center_radius", "id": "c", "center": "M", "radius": 120,
         "dashed": True, "style": "aux", "visual_role": "target_circle"},
    ])
    assert ("circle", TARGET_CIRCLE) in _strokes(svg)


# ── 7. key_point gets KEY_POINT fill ──
def test_key_point_color():
    svg, _ = _build([
        {"type": "free_point", "id": "A", "x": 100, "y": 100},
        {"type": "free_point", "id": "B", "x": 300, "y": 100},
        {"type": "segment", "id": "AB", "p1": "A", "p2": "B"},
        {"type": "free_point", "id": "P", "x": 200, "y": 100,
         "style": "aux", "visual_role": "key_point"},
    ])
    assert KEY_POINT in _point_fills(svg)


# ── 8. right_angle_mark gets RIGHT_ANGLE ──
def test_right_angle_mark_color():
    svg, _ = _build([
        {"type": "free_point", "id": "A", "x": 100, "y": 100},
        {"type": "free_point", "id": "B", "x": 300, "y": 100},
        {"type": "free_point", "id": "C", "x": 100, "y": 300},
        {"type": "right_angle_mark", "id": "r", "vertex": "A", "ray1": "B", "ray2": "C"},
    ])
    assert ("polyline", RIGHT_ANGLE) in _strokes(svg)


# ── 9. Feature flag off preserves existing stroke behavior ──
def test_feature_flag_off_preserves_legacy():
    svg, _ = _build([
        {"type": "free_point", "id": "A", "x": 150, "y": 150},
        {"type": "free_point", "id": "B", "x": 300, "y": 150},
        {"type": "midpoint", "id": "M", "p1": "A", "p2": "B"},
        {"type": "circle_center_radius", "id": "c", "center": "M", "radius": 120,
         "dashed": True, "style": "aux", "visual_role": "target_circle"},
    ], semantic=False)
    strokes = _strokes(svg)
    # Legacy dashed circles use dash_color, never TARGET_CIRCLE.
    assert not any(s == TARGET_CIRCLE for _, s in strokes)


# ── 10. Nine-point circle fixture colors ──
def _nine_point_constructions():
    from geometric_engine import geom
    A = (140.0, 80.0)
    B = (70.0, 480.0)
    C = (590.0, 440.0)
    H = geom.orthocenter(A, B, C)
    O = geom.circumcenter(A, B, C)
    D = geom.foot_of_perpendicular(A, geom.line_through_points(B, C))
    E = geom.foot_of_perpendicular(B, geom.line_through_points(C, A))
    F = geom.foot_of_perpendicular(C, geom.line_through_points(A, B))
    M = geom.midpoint(A, B)
    K = geom.midpoint(O, H)
    R_circum = geom.dist(O, A)
    R_nine = geom.dist(K, M)
    cs = [
        {"type": "free_point", "id": "A", "x": A[0], "y": A[1]},
        {"type": "free_point", "id": "B", "x": B[0], "y": B[1]},
        {"type": "free_point", "id": "C", "x": C[0], "y": C[1]},
        {"type": "triangle_acute", "id": "tri", "p1": "A", "p2": "B", "p3": "C"},
        {"type": "segment", "id": "AB", "p1": "A", "p2": "B"},
        {"type": "segment", "id": "BC", "p1": "B", "p2": "C"},
        {"type": "segment", "id": "CA", "p1": "C", "p2": "A"},
        # altitudes aux
        {"type": "free_point", "id": "D", "x": D[0], "y": D[1], "style": "aux",
         "purpose": "D", "solution_evidence": {"step_no": 1, "quote": "Проведём высоты"}},
        {"type": "free_point", "id": "E", "x": E[0], "y": E[1], "style": "aux",
         "purpose": "E", "solution_evidence": {"step_no": 1, "quote": "Проведём высоты"}},
        {"type": "free_point", "id": "F", "x": F[0], "y": F[1], "style": "aux",
         "purpose": "F", "solution_evidence": {"step_no": 1, "quote": "Проведём высоты"}},
        {"type": "altitude", "id": "AD", "vertex": "A", "side_a": "B", "side_b": "C",
         "foot_id": "D2", "dashed": True, "style": "aux"},
        {"type": "right_angle_mark", "id": "rD", "vertex": "D", "ray1": "A", "ray2": "B"},
        # key point H
        {"type": "free_point", "id": "H", "x": H[0], "y": H[1],
         "style": "aux", "visual_role": "key_point",
         "purpose": "H", "solution_evidence": {"step_no": 1, "quote": "Обозначим H"}},
        # circumcircle reference
        {"type": "free_point", "id": "O", "x": O[0], "y": O[1], "style": "aux",
         "purpose": "O", "solution_evidence": {"step_no": 4, "quote": "обозначим центр O"}},
        {"type": "circle_center_radius", "id": "circum", "center": "O", "radius": R_circum,
         "dashed": True, "style": "aux", "visual_role": "reference_circle"},
        # nine-point target
        {"type": "free_point", "id": "K", "x": K[0], "y": K[1], "style": "aux",
         "purpose": "K", "solution_evidence": {"step_no": 5, "quote": "Обозначим K"}},
        {"type": "circle_center_radius", "id": "nine", "center": "K", "radius": R_nine,
         "dashed": True, "style": "aux", "visual_role": "target_circle"},
    ]
    return cs


def test_nine_point_circle_colors():
    svg, ctx = _build(_nine_point_constructions())
    circle_strokes = [s for (c, s) in _strokes(svg) if c == "circle"]
    # circumcircle -> reference, nine-point -> target
    assert REFERENCE_CIRCLE in circle_strokes
    assert TARGET_CIRCLE in circle_strokes
    # altitudes -> aux (line stroke)
    line_strokes = [s for (c, s) in _strokes(svg) if c is None]
    assert AUX_STROKE in line_strokes
    # H -> key_point fill
    assert KEY_POINT in _point_fills(svg)
    # right_angle_mark -> RIGHT_ANGLE
    polyline_strokes = [s for (c, s) in _strokes(svg) if c == "polyline"]
    assert RIGHT_ANGLE in polyline_strokes


def test_resolver_defaults():
    # base segment -> base
    assert resolve_visual_role({"type": "segment"}) == "base"
    # aux altitude -> aux
    assert resolve_visual_role({"type": "altitude", "style": "aux"}) == "aux"
    # aux circle -> reference_circle
    assert resolve_visual_role({"type": "circumcircle", "style": "aux"}) == "reference_circle"
    # right_angle_mark -> right_angle_mark
    assert resolve_visual_role({"type": "right_angle_mark"}) == "right_angle_mark"
    # given marks -> given_mark
    assert resolve_visual_role({"type": "equal_segments_mark"}) == "given_mark"
    # aux point -> secondary
    assert resolve_point_role({"style": "aux"}) == "secondary"
    # explicit role wins
    assert resolve_visual_role({"type": "circumcircle", "style": "aux",
                                "visual_role": "target_circle"}) == "target_circle"
