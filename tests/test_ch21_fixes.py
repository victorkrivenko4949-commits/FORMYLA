 # -*- coding: utf-8 -*-
"""CH21 fixes regression tests."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from geometric_engine.engine import GeometricEngine, EngineSettings  # noqa: E402
from services.figure_plan_validator import (  # noqa: E402
    validate_condition_solution,
    extract_condition_points,
    check_condition_points,
)
import routes.figures_generator as fg  # noqa: E402


def _orthocenter_plan():
    """Остроугольный треугольник с высотами и ортоцентром H."""
    return {
        "canvas": {"width": 600, "height": 500, "margin": 40},
        "constructions": [
            {"type": "free_point", "id": "A", "x": 100, "y": 400},
            {"type": "free_point", "id": "B", "x": 500, "y": 400},
            {"type": "free_point", "id": "C", "x": 300, "y": 80},
            {"type": "triangle_arbitrary", "id": "tri_ABC", "p1": "A", "p2": "B", "p3": "C"},
            {"type": "altitude", "id": "alt_A", "vertex": "A", "side_a": "B", "side_b": "C", "foot_id": "A1"},
            {"type": "altitude", "id": "alt_B", "vertex": "B", "side_a": "A", "side_b": "C", "foot_id": "B1"},
            {"type": "altitude", "id": "alt_C", "vertex": "C", "side_a": "A", "side_b": "B", "foot_id": "C1"},
            {"type": "orthocenter", "id": "H", "p1": "A", "p2": "B", "p3": "C"},
        ],
    }


def _degenerate_segment_plan():
    return {
        "canvas": {"width": 600, "height": 500, "margin": 40},
        "constructions": [
            {"type": "free_point", "id": "A", "x": 100, "y": 400},
            {"type": "free_point", "id": "B", "x": 500, "y": 400},
            {"type": "segment", "id": "CH", "p1": "A", "p2": "A"},  # вырожденный
        ],
    }


class TestSoftChecks:
    def test_label_collision_returns_svg_not_failed(self):
        engine = GeometricEngine()
        engine.settings.semantic_colors = True
        svg, ctx, attempts, violations = engine.build_with_retry(_orthocenter_plan())
        # Даже при SOFT-нарушениях возвращается SVG (не failed).
        assert svg
        assert "<svg" in svg

    def test_degenerate_still_failed(self):
        engine = GeometricEngine()
        svg, ctx, attempts, violations = engine.build_with_retry(_degenerate_segment_plan())
        # Вырожденный segment — HARD, поэтому svg пуст.
        assert not svg


class TestConditionPoints:
    def test_midpoint_condition_requires_point(self):
        base = {
            "canvas": {"width": 600, "height": 500, "margin": 40},
            "constructions": [
                {"type": "free_point", "id": "A", "x": 100, "y": 400},
                {"type": "free_point", "id": "B", "x": 500, "y": 400},
            ],
        }
        w = check_condition_points("M — середина AB", base)
        assert any("MISSING_CONDITION_POINT" in x and "M" in x for x in w)

    def test_triangle_abc_no_extra_points(self):
        base = {
            "canvas": {"width": 600, "height": 500, "margin": 40},
            "constructions": [
                {"type": "free_point", "id": "A", "x": 100, "y": 400},
                {"type": "free_point", "id": "B", "x": 500, "y": 400},
                {"type": "free_point", "id": "C", "x": 300, "y": 80},
            ],
        }
        assert check_condition_points("Дан треугольник ABC", base) == []

    def test_angle_aob_no_extra_points(self):
        base = {
            "canvas": {"width": 600, "height": 500, "margin": 40},
            "constructions": [
                {"type": "free_point", "id": "A", "x": 100, "y": 400},
                {"type": "free_point", "id": "O", "x": 300, "y": 250},
                {"type": "free_point", "id": "B", "x": 500, "y": 400},
            ],
        }
        assert check_condition_points("Угол AOB равен 60°", base) == []


class TestDegenerateSegment:
    def test_degenerate_segment_rejected(self):
        base = _degenerate_segment_plan()
        aux = {"has_aux": False, "reason": "", "constructions": []}
        r = validate_condition_solution(base, aux)
        assert r["valid"] is False
        assert any("DEGENERATE_SEGMENT" in e for e in r.get("errors", []))

    def test_altitude_foot_id_passes(self):
        base = _orthocenter_plan()
        aux = {"has_aux": False, "reason": "", "constructions": []}
        r = validate_condition_solution(base, aux)
        # altitude с foot_id — валидно (нет DEGENERATE_SEGMENT).
        assert not any("DEGENERATE_SEGMENT" in e for e in r.get("errors", []))


class TestBaseRepairFeedback:
    def test_degenerate_segment_feedback_is_concrete(self):
        fb = fg._concrete_base_feedback([
            "DEGENERATE_SEGMENT: объект 'seg_CH' (segment) соединяет точку 'C' саму с собой"
        ])
        assert "altitude" in fb
        assert "seg_CH" in fb or "foot_id" in fb

    def test_engine_feedback_is_concrete(self):
        fb = fg._concrete_engine_feedback(["Проверка 3 (угол): треугольник ABC имеет угол 2.1° < 8.0°"])
        assert "2.1" in fb
        assert "угол" in fb
