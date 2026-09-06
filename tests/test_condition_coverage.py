# -*- coding: utf-8 -*-
"""Tests for CH22: condition_coverage.py and figure_plan_validator bugfixes.

Позитивные (полнота), регрессионные (на багфиксы BUG-1..7) и негативные
(должны падать) кейсы.  Без LLM и без БД.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.condition_coverage import check_condition_coverage
from services import figure_plan_validator as fpv


# ──────────────────────────────────────────────────────────────────────────
# Фабрика минимальных планов.
# ──────────────────────────────────────────────────────────────────────────

def _plan(constructions, **extra):
    plan = {
        "version": 2,
        "canvas": {"width": 600, "height": 500, "margin": 40},
        "constructions": constructions,
        "given_marks": [],
        "assumptions": [],
        "aux": {"has_aux": False, "reason": "", "constructions": []},
    }
    plan.update(extra)
    return plan


COND = ("В треугольнике ABC ∠B=50°, ∠C=70°. На стороне BC выбрана точка D "
        "так, что ∠BAD=30°. Найдите ∠ADC.")


def test_positive_full_coverage():
    """Эталон: все точки/углы/инцидентность/target отражены -> complete=True."""
    cs = [
        {"type": "free_point", "id": "A", "x": 300, "y": 60},
        {"type": "free_point", "id": "B", "x": 100, "y": 420},
        {"type": "free_point", "id": "C", "x": 500, "y": 420},
        {"type": "segment", "id": "AB", "p1": "A", "p2": "B"},
        {"type": "segment", "id": "AC", "p1": "A", "p2": "C"},
        {"type": "segment", "id": "BC", "p1": "B", "p2": "C"},
        {"type": "point_on_segment", "id": "D", "p1": "B", "p2": "C", "ratio": 0.4},
        {"type": "segment", "id": "AD", "p1": "A", "p2": "D"},
        {"type": "angle_label", "id": "ang_B", "vertex": "B", "ray1": "A", "ray2": "C", "text": "50°"},
        {"type": "angle_label", "id": "ang_C", "vertex": "C", "ray1": "A", "ray2": "B", "text": "70°"},
        {"type": "angle_label", "id": "ang_BAD", "vertex": "A", "ray1": "B", "ray2": "D", "text": "30°"},
        {"type": "angle_label", "id": "ang_ADC", "vertex": "D", "ray1": "A", "ray2": "C", "visual_role": "key_point"},
    ]
    r = check_condition_coverage(COND, _plan(cs))
    # Точки D не в given_marks — но уже объявлена.  Ошибок не должно быть
    # кроме возможного target-not-highlighted (уже key_point).
    assert not r["errors"], r.get("errors")


def test_regression_bug1_no_missing_given_warnings():
    """BUG-1: условие без равенств/прямых углов/середин -> ноль MISSING_GIVEN_*."""
    inv = fpv.validate_condition_solution(
        _plan([{"type": "free_point", "id": "A", "x": 0, "y": 0}]),
        {"has_aux": False},
        condition_text="В треугольнике ABC точка D лежит на стороне BC. "
                      "Найдите длину отрезка AD.",
    )
    warns = inv.get("warnings", [])
    assert not any(w.startswith("MISSING_GIVEN_") for w in warns), warns


def test_regression_bug2_only_named_point_flagged():
    """BUG-2: «на стороне BC выбрана точка D» -> MISSING_INCIDENCE только для D."""
    cs = [
        {"type": "free_point", "id": "A", "x": 100, "y": 100},
        {"type": "free_point", "id": "B", "x": 200, "y": 300},
        {"type": "free_point", "id": "C", "x": 400, "y": 300},
        {"type": "free_point", "id": "D", "x": 300, "y": 300},
    ]
    errs = fpv.check_missing_incidence(
        "На стороне BC выбрана точка D.", _plan(cs)
    )
    # Проверяем, что D есть в ошибках, а A/B/C — нет.
    assert any("'D'" in e for e in errs), errs
    assert not any("'A'" in e for e in errs), errs
    assert not any("'B'" in e for e in errs), errs
    assert not any("'C'" in e for e in errs), errs


def test_regression_bug7_extract_new_forms():
    """BUG-7: формы «середина M», «O — центр», «пересекаются в P», «обозначим K»."""
    points = fpv.extract_condition_points(
        "Середина M отрезка AB. O — центр окружности. "
        "Прямые пересекаются в точке P. Обозначим K точку касания."
    )
    for p in ("M", "O", "P", "K"):
        assert p in points, (p, points)


def test_negative_condition_not_realized():
    """H: фактический угол ≠ условию -> CONDITION_NOT_REALIZED."""
    from geometric_engine.engine import GeometricEngine
    import math

    # Строим треугольник, где угол B далёк от 50°.
    cs = [
        {"type": "free_point", "id": "A", "x": 300, "y": 60},
        {"type": "free_point", "id": "B", "x": 100, "y": 420},
        {"type": "free_point", "id": "C", "x": 500, "y": 420},
    ]
    plan = _plan(cs)
    engine = GeometricEngine()
    _, ctx = engine.build(plan)
    r = check_condition_coverage(
        "В треугольнике ABC ∠ABC=50°.", plan, build_context=ctx,
        settings=engine.settings,
    )
    assert any(e.startswith("CONDITION_NOT_REALIZED") for e in r.get("errors", []))


def test_negative_missing_numeric_label():
    """B: план без angle_label для 50° -> MISSING_NUMERIC_LABEL."""
    cs = [
        {"type": "free_point", "id": "A", "x": 300, "y": 60},
        {"type": "free_point", "id": "B", "x": 100, "y": 420},
        {"type": "free_point", "id": "C", "x": 500, "y": 420},
    ]
    r = check_condition_coverage(
        "В треугольнике ABC ∠B=50°.", _plan(cs)
    )
    assert any(e.startswith("MISSING_NUMERIC_LABEL") for e in r.get("errors", []))


def test_negative_aux_in_base_only():
    """AUX_IN_BASE_ONLY_MODE: aux-объект в base-only -> error."""
    cs = [
        {"type": "free_point", "id": "A", "x": 0, "y": 0},
        {"type": "free_point", "id": "B", "x": 100, "y": 0},
        {"type": "segment", "id": "AB", "p1": "A", "p2": "B", "style": "aux", "dashed": True},
    ]
    r = check_condition_coverage("Точки A и B.", _plan(cs))
    assert any(e.startswith("AUX_IN_BASE_ONLY_MODE") for e in r.get("errors", []))


def test_negative_target_points_missing():
    """G: «Найдите ∠ADC» без точки D -> TARGET_POINTS_MISSING."""
    cs = [
        {"type": "free_point", "id": "A", "x": 300, "y": 60},
        {"type": "free_point", "id": "C", "x": 500, "y": 420},
    ]
    r = check_condition_coverage(
        "В треугольнике ABC найдите ∠ADC.", _plan(cs)
    )
    assert any(e.startswith("TARGET_POINTS_MISSING") for e in r.get("errors", []))


def test_backward_compat_merge_base_aux():
    """merge_base_aux не меняет поведение на старых фикстурах."""
    base = _plan([{"type": "free_point", "id": "A", "x": 0, "y": 0}])
    aux = {"has_aux": True, "constructions": [
        {"type": "segment", "id": "AB", "p1": "A", "p2": "B",
         "style": "aux", "dashed": True},
        {"type": "free_point", "id": "B", "x": 10, "y": 10, "style": "aux"},
    ]}
    merged = fpv.merge_base_aux(base, aux)
    assert merged["constructions"][0]["id"] == "A"
    assert len(merged["constructions"]) == 3


def test_bug4_vertices_referenced():
    """BUG-4: aux ссылается на вершину inscribed_polygon через vertices."""
    base = _plan([
        {"type": "circle_center_radius", "id": "omega", "center": "O", "radius": 180},
        {"type": "inscribed_polygon", "id": "quad", "circle": "omega",
         "vertices": ["A", "B", "C", "D"], "order": "ccw"},
    ])
    aux = {"has_aux": True, "constructions": [
        {"type": "segment", "id": "AC", "p1": "A", "p2": "C",
         "style": "aux", "dashed": True, "purpose": "диагональ",
         "solution_evidence": {"step_no": 1, "quote": "Проведём AC"}},
    ]}
    inv = fpv.validate_condition_solution(base, aux)
    # Ссылки A и C существуют через vertices — INVALID_REFERENCE быть не должно.
    assert not any("INVALID_REFERENCE" in e for e in inv.get("errors", [])), inv
