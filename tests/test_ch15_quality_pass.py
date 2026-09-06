# -*- coding: utf-8 -*-
"""CH15.1 quality-pass tests.

Deterministic (no LLM/network). Covers:

  * given_marks schema + validation warnings/errors;
  * altitude foot_id contract (registration, availability, conflicts);
  * aux minimality (unnecessary construction detection);
  * layout pass (labels inside canvas, non-overlapping, not on circle/segment);
  * two full fixtures (isosceles altitude, right triangle diameter circle).
"""

import json
import math
import os
import re
import sys
import xml.etree.ElementTree as ET

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from geometric_engine.engine import (
    GeometricEngine,
    EngineSettings,
    _collect_label_boxes,
    _compute_label_candidates,
    _score_label_candidate,
)
from geometric_engine import geom


# ──────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────

def _isosceles_base():
    """Base: ABC, AB=AC (equal mark), angle 40° at A. No H, no AH."""
    return {
        "version": 2,
        "canvas": {"width": 600, "height": 500, "margin": 40},
        "constructions": [
            {"type": "free_point", "id": "A", "x": 300, "y": 100},
            {"type": "free_point", "id": "B", "x": 150, "y": 400},
            {"type": "free_point", "id": "C", "x": 450, "y": 400},
            {"type": "segment", "id": "AB", "p1": "A", "p2": "B"},
            {"type": "segment", "id": "BC", "p1": "B", "p2": "C"},
            {"type": "segment", "id": "CA", "p1": "C", "p2": "A"},
            {"type": "triangle_isosceles", "id": "tri_ABC", "p1": "A", "p2": "B", "p3": "C"},
            {"type": "equal_segments_mark", "id": "eq_AB_AC",
             "segments": [["A", "B"], ["A", "C"]], "count": 1},
            {"type": "angle_label", "id": "ang_A",
             "vertex": "A", "ray1": "B", "ray2": "C", "text": "40°"},
        ],
        "given_marks": [
            {"type": "equal_segments_mark", "segments": [["A", "B"], ["A", "C"]], "count": 1},
            {"type": "angle_label", "vertex": "A", "ray1": "B", "ray2": "C", "text": "40°"},
        ],
    }


def _isosceles_aux():
    """Aux: altitude AH (foot_id=H) + right angle mark at H."""
    return {
        "has_aux": True,
        "reason": "Проведём высоту AH.",
        "constructions": [
            {
                "type": "altitude",
                "id": "aux_altitude_AH",
                "vertex": "A",
                "side_a": "B",
                "side_b": "C",
                "foot_id": "H",
                "dashed": True,
                "style": "aux",
                "purpose": "Опустить высоту из A на BC",
                "solution_evidence": {
                    "step_no": 1,
                    "quote": "Проведём высоту AH из вершины A на сторону BC",
                },
            },
            {
                "type": "right_angle_mark",
                "id": "aux_right_H",
                "vertex": "H",
                "ray1": "A",
                "ray2": "B",
                "style": "aux",
                "purpose": "Отметить прямой угол при основании высоты",
                "solution_evidence": {
                    "step_no": 1,
                    "quote": "Проведём высоту AH из вершины A на сторону BC",
                },
            },
        ],
    }


def _right_triangle_base():
    """Base: ABC right at C, M midpoint of AB. No circle."""
    return {
        "version": 2,
        "canvas": {"width": 600, "height": 500, "margin": 40},
        "constructions": [
            {"type": "free_point", "id": "A", "x": 150, "y": 100},
            {"type": "free_point", "id": "B", "x": 480, "y": 400},
            {"type": "free_point", "id": "C", "x": 150, "y": 400},
            {"type": "segment", "id": "AB", "p1": "A", "p2": "B"},
            {"type": "segment", "id": "BC", "p1": "B", "p2": "C"},
            {"type": "segment", "id": "CA", "p1": "C", "p2": "A"},
            {"type": "triangle_right", "id": "tri_ABC", "p1": "A", "p2": "C", "p3": "B"},
            {"type": "right_angle_mark", "id": "right_C",
             "vertex": "C", "ray1": "A", "ray2": "B"},
            {"type": "midpoint", "id": "M", "p1": "A", "p2": "B"},
            {"type": "midpoint_mark", "id": "mid_AB", "point": "M", "p1": "A", "p2": "B"},
        ],
        "given_marks": [
            {"type": "right_angle_mark", "vertex": "C", "ray1": "A", "ray2": "B"},
            {"type": "midpoint_mark", "point": "M", "p1": "A", "p2": "B"},
        ],
    }


def _right_triangle_aux():
    """Aux: только окружность с диаметром AB (центр M). Без MC/радиусов."""
    return {
        "has_aux": True,
        "reason": "Окружность с диаметром AB.",
        "constructions": [
            {
                "type": "circumcircle",
                "id": "aux_circle_AB",
                "p1": "A",
                "p2": "B",
                "p3": "C",
                "dashed": True,
                "style": "aux",
                "purpose": "Окружность с диаметром AB (проходит через C)",
                "solution_evidence": {
                    "step_no": 1,
                    "quote": "Проведём окружность с диаметром AB",
                },
            },
        ],
    }


def _build_ctx(constructions, canvas=None):
    engine = GeometricEngine()
    spec = {
        "canvas": canvas or {"width": 600, "height": 500, "margin": 40},
        "constructions": constructions,
    }
    svg, ctx = engine.build(spec)
    return svg, ctx, engine


def _text_positions(svg_str):
    """Вернуть {text: (x, y)} для всех <text> элементов SVG."""
    root = ET.fromstring(svg_str)
    out = {}
    for el in root.iter("{http://www.w3.org/2000/svg}text"):
        text = (el.text or "").strip()
        if text:
            out[text] = (float(el.get("x")), float(el.get("y")))
    return out


def _dashed_line_count(svg_str):
    root = ET.fromstring(svg_str)
    count = 0
    for el in root.iter("{http://www.w3.org/2000/svg}line"):
        if el.get("stroke-dasharray"):
            count += 1
    return count


def _circle_elements(svg_str):
    root = ET.fromstring(svg_str)
    circles = []
    for el in root.iter("{http://www.w3.org/2000/svg}circle"):
        circles.append({
            "cx": float(el.get("cx")),
            "cy": float(el.get("cy")),
            "r": float(el.get("r")),
            "dashed": el.get("stroke-dasharray") is not None,
        })
    return circles


# ──────────────────────────────────────────────────────────────────────────
# 1. given_marks schema
# ──────────────────────────────────────────────────────────────────────────

class TestGivenMarksSchema:

    def test_parse_base_plan_with_given_marks(self):
        from services.figure_plan_schemas import parse_base_plan
        p = parse_base_plan(json.dumps(_isosceles_base()))
        assert p is not None
        assert isinstance(p.get("given_marks"), list)
        assert p["given_marks"][0]["type"] == "equal_segments_mark"
        assert p["given_marks"][1]["text"] == "40°"

    def test_given_mark_unknown_type_is_tolerated(self):
        from services.figure_plan_schemas import parse_base_plan
        base = _isosceles_base()
        base["given_marks"].append({"type": "weird_mark"})
        p = parse_base_plan(json.dumps(base))
        # pydantic extra=allow: unknown mark type сохраняется как dict.
        assert p is not None
        assert any(m["type"] == "weird_mark" for m in p["given_marks"])


# ──────────────────────────────────────────────────────────────────────────
# 2. given_marks validation
# ──────────────────────────────────────────────────────────────────────────

class TestGivenMarksValidation:

    def test_invalid_mark_reference_is_error(self):
        from services.figure_plan_validator import validate_condition_solution
        base = _isosceles_base()
        base["given_marks"].append(
            {"type": "angle_label", "vertex": "Z", "ray1": "B", "ray2": "C"}
        )
        r = validate_condition_solution(base, {"has_aux": False, "constructions": []})
        assert r["valid"] is False
        assert any("GIVEN_MARK_INVALID_REF" in e for e in r["errors"])

    def test_missing_given_mark_warnings(self):
        # BUG-1: MISSING_GIVEN_* warnings выдаются ТОЛЬКО при триггере в условии.
        from services.figure_plan_validator import validate_condition_solution
        base = {
            "version": 2,
            "canvas": {"width": 600, "height": 500, "margin": 40},
            "constructions": [
                {"type": "free_point", "id": "A", "x": 100, "y": 400},
                {"type": "free_point", "id": "B", "x": 500, "y": 400},
                {"type": "free_point", "id": "C", "x": 300, "y": 80},
                {"type": "triangle_arbitrary", "id": "tri", "p1": "A", "p2": "B", "p3": "C"},
            ],
        }
        condition = (
            "В равнобедренном треугольнике ABC угол B равен 40°, прямой угол "
            "при вершине C, точка M — середина AB."
        )
        r = validate_condition_solution(
            base, {"has_aux": False, "constructions": []}, condition_text=condition
        )
        assert r["valid"] is True  # warnings не ломают valid
        warnings = r.get("warnings", [])
        assert any("MISSING_GIVEN_EQUALITY_MARK" in w for w in warnings)
        assert any("MISSING_GIVEN_ANGLE_LABEL" in w for w in warnings)
        assert any("MISSING_GIVEN_RIGHT_ANGLE_MARK" in w for w in warnings)
        assert any("MISSING_GIVEN_MIDPOINT_MARK" in w for w in warnings)

    def test_no_missing_given_warnings_without_triggers(self):
        # BUG-1: без condition_text (или без триггеров) — ноль MISSING_GIVEN_*.
        from services.figure_plan_validator import validate_condition_solution
        base = {
            "version": 2,
            "canvas": {"width": 600, "height": 500, "margin": 40},
            "constructions": [
                {"type": "free_point", "id": "A", "x": 100, "y": 400},
                {"type": "free_point", "id": "B", "x": 500, "y": 400},
                {"type": "free_point", "id": "C", "x": 300, "y": 80},
                {"type": "triangle_arbitrary", "id": "tri", "p1": "A", "p2": "B", "p3": "C"},
            ],
        }
        r = validate_condition_solution(base, {"has_aux": False, "constructions": []})
        assert r["valid"] is True
        assert not any(
            w.startswith("MISSING_GIVEN_") for w in r.get("warnings", [])
        )

    def test_present_marks_do_not_warn(self):
        from services.figure_plan_validator import validate_condition_solution
        r = validate_condition_solution(_isosceles_base(), {"has_aux": False, "constructions": []})
        warnings = r.get("warnings", [])
        assert not any("MISSING_GIVEN_EQUALITY_MARK" in w for w in warnings)
        assert not any("MISSING_GIVEN_ANGLE_LABEL" in w for w in warnings)


# ──────────────────────────────────────────────────────────────────────────
# 3. altitude foot_id contract
# ──────────────────────────────────────────────────────────────────────────

class TestAltitudeFootId:

    def test_altitude_registers_foot(self):
        from geometric_engine.engine import execute_construction, BuildContext
        ctx = BuildContext()
        for c in [
            {"type": "free_point", "id": "A", "x": 300, "y": 100},
            {"type": "free_point", "id": "B", "x": 150, "y": 400},
            {"type": "free_point", "id": "C", "x": 450, "y": 400},
        ]:
            execute_construction(ctx, c)
        execute_construction(ctx, {
            "type": "altitude", "id": "aux_altitude_AH",
            "vertex": "A", "side_a": "B", "side_b": "C", "foot_id": "H",
        })
        assert "H" in ctx.points
        # Основание высоты на отрезке BC.
        assert geom.segment_contains_point(
            (ctx.points["B"], ctx.points["C"]), ctx.points["H"]
        )
        assert ctx.meta["H"]["hidden"] is False
        assert ctx.meta["H"]["label"] == "H"

    def test_foot_available_for_next_construction(self):
        svg, ctx, _ = _build_ctx(_isosceles_base()["constructions"] + _isosceles_aux()["constructions"])
        assert "H" in ctx.points
        assert "aux_right_H" in ctx.meta  # right_angle_mark сослался на H

    def test_foot_id_conflict_with_base_id(self):
        from services.figure_plan_validator import validate_condition_solution
        base = _isosceles_base()
        # Добавим точку H в base, чтобы foot_id=H конфликтовал.
        base["constructions"].append({"type": "free_point", "id": "H", "x": 300, "y": 400})
        aux = _isosceles_aux()
        r = validate_condition_solution(base, aux)
        assert r["valid"] is False
        assert any("FOOT_ID_CONFLICT" in e for e in r["errors"])

    def test_foot_id_repeated(self):
        from services.figure_plan_validator import validate_condition_solution
        aux = _isosceles_aux()
        # Второй altitude с тем же foot_id=H.
        aux["constructions"].append({
            "type": "altitude", "id": "aux_altitude_2",
            "vertex": "B", "side_a": "A", "side_b": "C", "foot_id": "H",
            "dashed": True, "style": "aux", "purpose": "x",
            "solution_evidence": {"step_no": 1, "quote": "опустим высоту"},
        })
        r = validate_condition_solution(_isosceles_base(), aux)
        assert r["valid"] is False
        assert any("FOOT_ID_CONFLICT" in e for e in r["errors"])

    def test_right_angle_mark_references_created_foot(self):
        from services.figure_plan_validator import validate_condition_solution
        r = validate_condition_solution(_isosceles_base(), _isosceles_aux())
        assert r["valid"] is True, r.get("errors")


# ──────────────────────────────────────────────────────────────────────────
# 4. aux minimality
# ──────────────────────────────────────────────────────────────────────────

class TestAuxMinimality:

    def test_aux_object_without_evidence_is_problem(self):
        from services.figure_plan_validator import validate_condition_solution
        aux = _right_triangle_aux()
        aux["constructions"].append({
            "type": "segment", "id": "aux_MC", "p1": "M", "p2": "C",
            "dashed": True, "style": "aux", "purpose": "радиус MC",
            # нет solution_evidence
        })
        r = validate_condition_solution(_right_triangle_base(), aux)
        assert r["valid"] is False
        assert any("solution_evidence" in e for e in r["errors"])

    def test_short_evidence_quote_warns(self):
        from services.figure_plan_validator import validate_condition_solution
        aux = _right_triangle_aux()
        aux["constructions"][0]["solution_evidence"]["quote"] = "MC"
        r = validate_condition_solution(_right_triangle_base(), aux)
        warnings = r.get("warnings", [])
        assert any("UNNECESSARY_AUX_CONSTRUCTION" in w for w in warnings)


# ──────────────────────────────────────────────────────────────────────────
# 4b. dashed requirement (geometry vs visual marks)
# ──────────────────────────────────────────────────────────────────────────

class TestAuxDashedRule:

    def test_aux_right_angle_mark_without_dashed_is_valid(self):
        from services.figure_plan_validator import validate_condition_solution
        aux = {
            "has_aux": True,
            "reason": "Прямой угол при основании высоты.",
            "constructions": [
                {
                    "type": "right_angle_mark",
                    "id": "aux_right_H",
                    "vertex": "C",
                    "ray1": "A",
                    "ray2": "B",
                    "style": "aux",
                    "dashed": False,
                    "purpose": "Отметить прямой угол",
                    "solution_evidence": {"step_no": 1, "quote": "угол C прямой"},
                }
            ],
        }
        r = validate_condition_solution(_right_triangle_base(), aux)
        assert r["valid"] is True, r.get("errors")

    def test_aux_altitude_without_dashed_is_invalid(self):
        from services.figure_plan_validator import validate_condition_solution
        aux = {
            "has_aux": True,
            "reason": "Опустим высоту AH.",
            "constructions": [
                {
                    "type": "altitude",
                    "id": "aux_altitude_AH",
                    "vertex": "A",
                    "side_a": "B",
                    "side_b": "C",
                    "foot_id": "H",
                    "style": "aux",
                    "dashed": False,
                    "purpose": "Опустить высоту из A на BC",
                    "solution_evidence": {"step_no": 1, "quote": "Проведём высоту AH"},
                }
            ],
        }
        r = validate_condition_solution(_isosceles_base(), aux)
        assert r["valid"] is False
        assert any("dashed=true" in e for e in r["errors"])


# ──────────────────────────────────────────────────────────────────────────
# 4c. aux segment/line/ray require explicit construction action
# ──────────────────────────────────────────────────────────────────────────

class TestAuxSegmentConstructionAction:

    def test_circle_diameter_valid_without_segment_mc(self):
        from services.figure_plan_validator import validate_condition_solution
        aux = {
            "has_aux": True,
            "reason": "Окружность с диаметром AB.",
            "constructions": [
                {
                    "type": "circle_center_radius",
                    "id": "aux_circle_AB",
                    "center": "M",
                    "radius": 160,
                    "dashed": True,
                    "style": "aux",
                    "purpose": "Окружность с диаметром AB",
                    "solution_evidence": {
                        "step_no": 1,
                        "quote": "Проведём окружность с диаметром AB",
                    },
                }
            ],
        }
        r = validate_condition_solution(_right_triangle_base(), aux)
        assert r["valid"] is True, r.get("errors")
        # Окружность не является segment/line/ray — предупреждения быть не должно.
        assert not any(
            "AUX_SEGMENT_WITHOUT_CONSTRUCTION_ACTION" in w
            for w in r.get("warnings", [])
        )

    def test_segment_mc_with_proof_quote_warns(self):
        from services.figure_plan_validator import validate_condition_solution
        aux = {
            "has_aux": True,
            "reason": "MA, MB, MC — радиусы одной окружности.",
            "constructions": [
                {
                    "type": "circle_center_radius",
                    "id": "aux_circle_AB",
                    "center": "M",
                    "radius": 160,
                    "dashed": True,
                    "style": "aux",
                    "purpose": "Окружность с диаметром AB",
                    "solution_evidence": {
                        "step_no": 1,
                        "quote": "Проведём окружность с диаметром AB",
                    },
                },
                {
                    "type": "segment",
                    "id": "aux_MC",
                    "p1": "M",
                    "p2": "C",
                    "dashed": True,
                    "style": "aux",
                    "purpose": "радиус MC",
                    "solution_evidence": {
                        "step_no": 4,
                        "quote": "MC является радиусом",
                    },
                },
            ],
        }
        r = validate_condition_solution(_right_triangle_base(), aux)
        warnings = r.get("warnings", [])
        assert any(
            "AUX_SEGMENT_WITHOUT_CONSTRUCTION_ACTION" in w for w in warnings
        ), r


class TestAltitudeFootRendered:

    def test_altitude_foot_rendered_with_label_and_right_angle(self):
        merged = _isosceles_base()["constructions"] + _isosceles_aux()["constructions"]
        svg, ctx, _ = _build_ctx(merged)

        # 1. foot_id создаёт H в ctx.points.
        assert "H" in ctx.points
        # 2. H не hidden — попадает в rendered points.
        assert ctx.meta["H"]["hidden"] is False
        # 3. label H есть в SVG.
        assert "H" in _text_positions(svg)
        # 4. right_angle_mark у H рендерится (polyline).
        root = ET.fromstring(svg)
        polylines = list(root.iter("{http://www.w3.org/2000/svg}polyline"))
        assert len(polylines) >= 1

    def test_altitude_without_foot_id_warns(self):
        from services.figure_plan_validator import validate_condition_solution
        aux = {
            "has_aux": True,
            "reason": "Опустим высоту AH.",
            "constructions": [
                {
                    "type": "altitude",
                    "id": "aux_altitude_AH",
                    "vertex": "A",
                    "side_a": "B",
                    "side_b": "C",
                    "dashed": True,
                    "style": "aux",
                    "purpose": "Опустить высоту из A на BC",
                    "solution_evidence": {"step_no": 1, "quote": "Проведём высоту AH"},
                }
            ],
        }
        r = validate_condition_solution(_isosceles_base(), aux)
        assert any(
            "MISSING_FOOT_ID" in w for w in r.get("warnings", [])
        ), r


# ──────────────────────────────────────────────────────────────────────────
# 5. layout pass
# ──────────────────────────────────────────────────────────────────────────

class TestLayout:

    def test_labels_inside_canvas(self):
        svg, ctx, _ = _build_ctx(_isosceles_base()["constructions"])
        positions = _text_positions(svg)
        assert positions
        for text, (x, y) in positions.items():
            assert 0 <= x <= 600, f"label {text} x={x} outside canvas"
            assert 0 <= y <= 500, f"label {text} y={y} outside canvas"

    def test_labels_do_not_overlap(self):
        svg, ctx, engine = _build_ctx(_isosceles_base()["constructions"])
        boxes = _collect_label_boxes(ctx, engine.settings)
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                a = boxes[i][2]
                b = boxes[j][2]
                overlap = not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])
                assert not overlap, f"labels {boxes[i][1]} and {boxes[j][1]} overlap"

    def test_out_of_canvas_candidate_penalized(self):
        from geometric_engine.engine import _compute_label_candidates, _score_label_candidate
        settings = EngineSettings()
        cands = _compute_label_candidates((10, 10), settings.label_padding, 8)
        scores = []
        for c in cands:
            s = _score_label_candidate(
                c, [], [], settings,
                circles=[], canvas_w=600, canvas_h=500,
            )
            scores.append((s, c))
        # Кандидаты, выходящие за холст, штрафуются сильнее остальных.
        inside = [s for s, c in scores if s < 1e6]
        assert inside, "expected at least one in-canvas candidate"

    def test_point_collision_penalized(self):
        from geometric_engine.engine import _compute_label_candidates, _score_label_candidate
        settings = EngineSettings()
        # Свободная точка-кандидат в центре; чужая точка лежит прямо на
        # кандидате N.  Кандидат N должен получить штраф за пересечение точки.
        cands = _compute_label_candidates((300, 250), settings.label_padding, 8)
        foreign = [(300, 250 - settings.label_padding)]  # совпадает с N
        scores = {tuple(c): _score_label_candidate(
            c, [], [], settings, circles=[], points=foreign,
            canvas_w=600, canvas_h=500,
        ) for c in cands}
        n_key = (300, 250 - settings.label_padding)
        other_keys = [k for k in scores if k != n_key]
        assert scores[n_key] > max(scores[k] for k in other_keys), (
            "candidate overlapping a foreign point must be penalised"
        )

    def test_label_m_not_on_ab_or_circle(self):
        merged = dict(_right_triangle_base())
        merged["constructions"] = (
            _right_triangle_base()["constructions"] + _right_triangle_aux()["constructions"]
        )
        svg, ctx, engine = _build_ctx(merged["constructions"])

        # Окружность (aux circumcircle, centre M, radius MA).
        circle = None
        for cid, cdata in ctx.circles.items():
            circle = cdata
            break
        assert circle is not None

        positions = _text_positions(svg)
        assert "M" in positions
        mx, my = positions["M"]

        # label M не лежит на AB.
        ab = (ctx.points["A"], ctx.points["B"])
        d_ab = geom.point_to_segment_distance((mx, my), ab)
        assert d_ab > 5.0, f"label M too close to AB: {d_ab}"

        # label M не лежит на окружности.
        center, r = circle
        d_circle = abs(geom.dist((mx, my), center) - r)
        assert d_circle > 5.0, f"label M too close to circle: {d_circle}"


# ──────────────────────────────────────────────────────────────────────────
# 6. Full fixtures
# ──────────────────────────────────────────────────────────────────────────

class TestIsoscelesFixture:

    def test_base_has_no_h_no_ah(self):
        base = _isosceles_base()
        ids = [c["id"] for c in base["constructions"]]
        types = {c["id"]: c["type"] for c in base["constructions"]}
        assert "H" not in ids
        assert not any(t == "altitude" for t in types.values())
        assert any(t == "equal_segments_mark" for t in types.values())
        assert any(t == "angle_label" for t in types.values())

    def test_aux_altitude_creates_h_and_is_dashed(self):
        merged = _isosceles_base()["constructions"] + _isosceles_aux()["constructions"]
        svg, ctx, _ = _build_ctx(merged)
        assert "H" in ctx.points
        assert "H" in _text_positions(svg)  # label H видим
        # altitude AH нарисована пунктиром.
        assert _dashed_line_count(svg) >= 1
        # Есть только одна вспомогательная линия (сама высота).
        assert _dashed_line_count(svg) == 1

    def test_aux_has_right_angle_mark_at_h(self):
        merged = _isosceles_base()["constructions"] + _isosceles_aux()["constructions"]
        svg, ctx, _ = _build_ctx(merged)
        # right_angle_mark рендерится как polyline.
        root = ET.fromstring(svg)
        polylines = list(root.iter("{http://www.w3.org/2000/svg}polyline"))
        assert len(polylines) >= 1

    def test_base_has_equal_mark_and_angle_label(self):
        svg, ctx, _ = _build_ctx(_isosceles_base()["constructions"])
        # equal ticks рендерятся как line с class="equal-tick".
        root = ET.fromstring(svg)
        ticks = [el for el in root.iter("{http://www.w3.org/2000/svg}line")
                 if el.get("class") == "equal-tick"]
        assert ticks
        # angle label "40°" видим.
        assert "40°" in _text_positions(svg)


class TestRightTriangleFixture:

    def test_base_has_right_angle_and_midpoint_no_circle(self):
        base = _right_triangle_base()
        types = {c["id"]: c["type"] for c in base["constructions"]}
        assert any(t == "right_angle_mark" for t in types.values())
        assert "M" in types and types["M"] == "midpoint"
        assert not any(t.startswith("circle") or t == "circumcircle" for t in types.values())

    def test_aux_circle_dashed_and_no_mc(self):
        merged = _right_triangle_base()["constructions"] + _right_triangle_aux()["constructions"]
        svg, ctx, _ = _build_ctx(merged)
        circles = _circle_elements(svg)
        # Геометрические окружности (r > 5), исключая маркеры точек (r ≈ 3.5).
        geo_circles = [c for c in circles if c["r"] > 5]
        assert len(geo_circles) == 1  # только одна вспомогательная окружность
        assert geo_circles[0]["dashed"] is True
        # нет MC: в aux нет сегмента с M..C.
        aux_ids = [c["id"] for c in _right_triangle_aux()["constructions"]]
        assert not any("MC" in cid for cid in aux_ids)

    def test_aux_has_no_extra_radii(self):
        aux = _right_triangle_aux()
        for c in aux["constructions"]:
            assert c["type"] != "segment"
