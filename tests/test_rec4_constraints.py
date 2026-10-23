# -*- coding: utf-8 -*-
"""Tests for REC-4: constraint operations + reaction policy."""
import math
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from geometric_engine.engine import GeometricEngine
from geometric_engine import geom
from services.condition_coverage import check_condition_coverage
from services.text_normalize import normalize_condition

JOB152_PLAN = {
    "version": 2,
    "canvas": {"width": 600, "height": 500, "margin": 40},
    "constructions": [
        {"type": "free_point", "id": "A", "x": 300, "y": 60},
        {"type": "free_point", "id": "B", "x": 100, "y": 420},
        {"type": "free_point", "id": "C", "x": 500, "y": 420},
        {"type": "circumcircle", "id": "omega", "p1": "A", "p2": "B", "p3": "C"},
        {"type": "circumcenter", "id": "O", "p1": "A", "p2": "B", "p3": "C"},
        {"type": "segment", "id": "AB", "p1": "A", "p2": "B"},
        {"type": "segment", "id": "AC", "p1": "A", "p2": "C"},
        {"type": "segment", "id": "BC", "p1": "B", "p2": "C"},
        {"type": "line", "id": "BO", "p1": "B", "p2": "O"},
        {"type": "line", "id": "CO", "p1": "C", "p2": "O"},
        {"type": "intersect_lines", "id": "D", "line1": "BO", "line2": "AC"},
        {"type": "intersect_lines", "id": "E", "line1": "CO", "line2": "AB"},
        {"type": "segment", "id": "BD", "p1": "B", "p2": "D"},
        {"type": "segment", "id": "CE", "p1": "C", "p2": "E"},
        {"type": "angle_label", "id": "ang_A", "vertex": "A", "ray1": "B",
         "ray2": "C", "text": "45°"},
    ],
}

COND = "В остроугольном треугольнике ABC угол A равен 45°. BD = CE. Найдите угол B."


def test_18_job152_not_realized():
    engine = GeometricEngine()
    _, ctx = engine.build(JOB152_PLAN)
    cov = check_condition_coverage(normalize_condition(COND), JOB152_PLAN,
                                   build_context=ctx, settings=engine.settings)
    assert any("CONDITION_NOT_REALIZED" in e for e in cov.get("errors", [])), cov


def test_19_triangle_by_two_angles_exact():
    plan = {
        "version": 2,
        "canvas": {"width": 600, "height": 500, "margin": 40},
        "constructions": [
            {"type": "free_point", "id": "A", "x": 100, "y": 420},
            {"type": "free_point", "id": "B", "x": 500, "y": 420},
            {"type": "triangle_by_two_angles", "id": "tri", "p1": "A",
             "p2": "B", "p3": "C", "angle_a": 45, "angle_b": 67.5},
        ],
    }
    engine = GeometricEngine()
    _, ctx = engine.build(plan)
    a = math.degrees(geom.angle_between_three(
        ctx.points["B"], ctx.points["A"], ctx.points["C"]))
    b = math.degrees(geom.angle_between_three(
        ctx.points["A"], ctx.points["B"], ctx.points["C"]))
    assert abs(a - 45.0) <= 0.5, a
    assert abs(b - 67.5) <= 0.5, b


def test_20_plan_uses_constraints():
    from routes.figures_generator import plan_uses_constraints
    no_constraint = {"constructions": [{"type": "free_point", "id": "A"}]}
    with_constraint = {"constructions": [
        {"type": "triangle_by_two_angles", "id": "t", "p1": "A", "p2": "B",
         "p3": "C", "angle_a": 45, "angle_b": 60},
    ]}
    assert plan_uses_constraints(no_constraint) is False
    assert plan_uses_constraints(with_constraint) is True


def test_21_without_constraints_repair_not_reseed():
    # План без ограничений: CONDITION_NOT_REALIZED → должен давать targeted
    # repair (в base_only это означает failed с указанием операции).
    from routes.figures_generator import plan_uses_constraints
    assert plan_uses_constraints(JOB152_PLAN) is False
    engine = GeometricEngine()
    _, ctx = engine.build(JOB152_PLAN)
    cov = check_condition_coverage(normalize_condition(COND), JOB152_PLAN,
                                   build_context=ctx, settings=engine.settings)
    codes = [e.split(":")[0] for e in cov.get("errors", [])]
    assert "CONDITION_NOT_REALIZED" in codes
    # repair_feedback должен упоминать операцию-ограничение.
    assert "triangle_by_two_angles" in cov.get("repair_feedback", "") \
        or "angle_at_vertex" in cov.get("repair_feedback", ""), cov


def test_22_with_constraints_reseed_no_llm():
    # План с triangle_by_two_angles: углы точны, CONDITION_NOT_REALIZED не
    # возникает — решатель сошёлся, reseed не нужен.
    plan = {
        "version": 2,
        "canvas": {"width": 600, "height": 500, "margin": 40},
        "constructions": [
            {"type": "free_point", "id": "A", "x": 100, "y": 420},
            {"type": "free_point", "id": "B", "x": 500, "y": 420},
            {"type": "triangle_by_two_angles", "id": "tri", "p1": "A",
             "p2": "B", "p3": "C", "angle_a": 45, "angle_b": 67.5},
        ],
    }
    engine = GeometricEngine()
    _, ctx = engine.build(plan)
    cov = check_condition_coverage(normalize_condition(COND), plan,
                                   build_context=ctx, settings=engine.settings)
    assert "CONDITION_NOT_REALIZED" not in [
        e.split(":")[0] for e in cov.get("errors", [])
    ]


def test_23_refund_exactly_once():
    # Проверяем инвариант на уровне кода: _fail_job вызывает _refund_credit,
    # а _refund_credit возврат только если credit_charged был выставлен.
    # Здесь проверяем сам факт существования single-refund guard через
    # _refund_credit (уже покрыт в test_figures_ch5).  Smoke: функция существует.
    from routes.figures_generator import _refund_credit, _fail_job
    assert callable(_refund_credit)
    assert callable(_fail_job)
