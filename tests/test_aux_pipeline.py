# -*- coding: utf-8 -*-
"""Tests for CH-aux: solver-driven aux pipeline.

Ядро — answer_verifier.  Также aux_usefulness, строгие цитаты, шаблоны,
роутер (provider+model blocking) и обратная совместимость.
Без LLM и без БД (кроме роутера, который проверяется на чистых функциях).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.answer_verifier import verify_answer
from services.aux_compiler import compile_solver_aux, validate_quote
from services.aux_ops import AUX_ALLOWED_OPS
from services.aux_usefulness import evaluate_usefulness
from services import aux_templates
from services import llm_router as router
from geometric_engine.engine import GeometricEngine, BuildContext


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


def _build(plan):
    engine = GeometricEngine()
    svg, ctx = engine.build(plan)
    return ctx


# ──────────────────────────────────────────────────────────────────────────
# answer_verifier (ЯДРО)
# ──────────────────────────────────────────────────────────────────────────

def _triangle_50_70():
    # Треугольник с ∠B=50°, ∠C=70°, D на BC с ∠BAD=30° (реализован приближённо).
    return _plan([
        {"type": "free_point", "id": "A", "x": 300, "y": 60},
        {"type": "free_point", "id": "B", "x": 100, "y": 420},
        {"type": "free_point", "id": "C", "x": 500, "y": 420},
        {"type": "point_on_segment", "id": "D", "p1": "B", "p2": "C", "ratio": 0.4},
    ])


def test_answer_verify_angle_verified():
    # Реальный угол ADC ~ 80° (известная задача).  Двигаем D так, чтобы
    # измеренный угол был близок к declared.
    plan = _plan([
        {"type": "free_point", "id": "A", "x": 300, "y": 60},
        {"type": "free_point", "id": "D", "x": 500, "y": 420},
        {"type": "free_point", "id": "C", "x": 100, "y": 420},
    ])
    ctx = _build(plan)
    # Измерим реальный угол, чтобы заявить то же значение.
    import math
    from geometric_engine import geom
    actual = math.degrees(geom.angle_between_three(
        ctx.points["A"], ctx.points["D"], ctx.points["C"]
    ))
    solver = {
        "target": {"kind": "angle", "object": "ADC"},
        "answer": {"value": round(actual, 1), "is_numeric": True},
    }
    r = verify_answer(solver, ctx, plan, condition_text="Найдите ∠ADC.")
    assert r["verdict"] == "verified", r


def test_answer_verify_angle_mismatch():
    plan = _plan([
        {"type": "free_point", "id": "A", "x": 300, "y": 60},
        {"type": "free_point", "id": "D", "x": 500, "y": 420},
        {"type": "free_point", "id": "C", "x": 100, "y": 420},
    ])
    ctx = _build(plan)
    import math
    from geometric_engine import geom
    actual = math.degrees(geom.angle_between_three(
        ctx.points["A"], ctx.points["D"], ctx.points["C"]
    ))
    solver = {
        "target": {"kind": "angle", "object": "ADC"},
        "answer": {"value": actual + 40.0, "is_numeric": True},
    }
    r = verify_answer(solver, ctx, plan, condition_text="Найдите ∠ADC.")
    assert r["verdict"] == "mismatch", r


def test_answer_verify_unverifiable_non_numeric():
    solver = {
        "target": {"kind": "angle", "object": "B"},
        "answer": {"value": None, "is_numeric": False},
    }
    r = verify_answer(solver, None, {}, condition_text="Докажите, что ...")
    assert r["verdict"] == "unverifiable", r


def test_answer_verify_angle_by_single_letter():
    # «Найдите угол B» в треугольнике ABC → resolve_angle_triple.
    plan = _plan([
        {"type": "free_point", "id": "A", "x": 300, "y": 60},
        {"type": "free_point", "id": "B", "x": 100, "y": 420},
        {"type": "free_point", "id": "C", "x": 500, "y": 420},
    ])
    ctx = _build(plan)
    import math
    from geometric_engine import geom
    actual = math.degrees(geom.angle_between_three(
        ctx.points["A"], ctx.points["B"], ctx.points["C"]
    ))
    solver = {
        "target": {"kind": "angle", "object": "B"},
        "answer": {"value": round(actual, 1), "is_numeric": True},
    }
    r = verify_answer(solver, ctx, plan,
                      condition_text="В треугольнике ABC найдите угол B.")
    assert r["verdict"] == "verified", r


# ──────────────────────────────────────────────────────────────────────────
# aux_compiler: строгие цитаты
# ──────────────────────────────────────────────────────────────────────────

def test_validate_quote_ok():
    steps = [{"no": 1, "text": "Проведём радиус AO."}]
    ok, code = validate_quote("Проведём радиус AO", steps)
    assert ok and code == ""


def test_validate_quote_not_in_solution():
    steps = [{"no": 1, "text": "Проведём радиус AO."}]
    ok, code = validate_quote("Соединим X и Y", steps)
    assert not ok and code == "QUOTE_NOT_IN_SOLUTION"


def test_validate_quote_no_action_stem():
    steps = [{"no": 1, "text": "MC является радиусом."}]
    ok, code = validate_quote("MC является радиусом", steps)
    assert not ok and code == "QUOTE_NO_ACTION_STEM"


def test_compile_solver_aux_unknown_op():
    solver = {
        "steps": [{"no": 1, "text": "Проведём что-то."}],
        "aux_constructions": [{"op": "frobnicate", "quote": "Проведём что-то"}],
    }
    aux, issues = compile_solver_aux(solver, _plan([]))
    assert any("UNKNOWN_AUX_OP" in i for i in issues), issues


def test_compile_solver_aux_quote_rejected():
    solver = {
        "steps": [{"no": 1, "text": "Проведём радиус AO."}],
        "aux_constructions": [
            {"op": "segment", "points": ["A", "O"],
             "quote": "Соединим X и Y", "step_no": 1},
        ],
    }
    aux, issues = compile_solver_aux(solver, _plan([]))
    assert any("QUOTE_NOT_IN_SOLUTION" in i for i in issues), issues


# ──────────────────────────────────────────────────────────────────────────
# aux_usefulness
# ──────────────────────────────────────────────────────────────────────────

def _ctx_with(points, segments):
    ctx = BuildContext()
    for pid, p in points.items():
        ctx.points[pid] = p
    for sid, (a, b) in segments.items():
        ctx.segments[sid] = (a, b)
    return ctx


def test_usefulness_harmful_too_many_points():
    before = _ctx_with({"A": (0, 0)}, {})
    after = _ctx_with(
        {"A": (0, 0), "B": (10, 0), "C": (20, 0), "D": (30, 0), "E": (40, 0)},
        {},
    )
    r = evaluate_usefulness(before, after, [{"op": "segment"}])
    assert r["verdict"] == "harmful", r


def test_usefulness_useless_empty():
    before = _ctx_with({"A": (0, 0)}, {})
    r = evaluate_usefulness(before, before, [])
    assert r["verdict"] == "useless", r


# ──────────────────────────────────────────────────────────────────────────
# aux_templates
# ──────────────────────────────────────────────────────────────────────────

def test_template_circumcenter():
    plan = _plan([
        {"type": "free_point", "id": "O", "x": 200, "y": 180},
        {"type": "free_point", "id": "A", "x": 100, "y": 100},
        {"type": "free_point", "id": "B", "x": 300, "y": 100},
        {"type": "free_point", "id": "C", "x": 200, "y": 300},
        {"type": "circle_center_radius", "id": "omega", "center": "O", "radius": 150},
    ])
    ctx = _build(plan)
    m = aux_templates.match_template(plan, "O — центр описанной окружности", ctx)
    assert m is not None, m


def test_template_none_for_plain():
    plan = _plan([
        {"type": "free_point", "id": "A", "x": 100, "y": 100},
        {"type": "free_point", "id": "B", "x": 300, "y": 100},
    ])
    ctx = _build(plan)
    m = aux_templates.match_template(plan, "Просто две точки.", ctx)
    assert m is None


# ──────────────────────────────────────────────────────────────────────────
# router: provider+model blocking
# ──────────────────────────────────────────────────────────────────────────

def test_provider_model_blocking_isolated():
    router.clear_model_cache()
    router.mark_provider_model_unreachable("deepseek_direct", "deepseek-v4-pro", 600)
    # Блокировка pro не должна блокировать flash.
    assert not router.is_provider_model_unreachable("deepseek_direct", "deepseek-v4-flash")
    assert router.is_provider_model_unreachable("deepseek_direct", "deepseek-v4-pro")
    router.clear_model_cache()


def test_aux_ops_closed_dict():
    # Неизвестная op отсутствует.
    assert "frobnicate" not in AUX_ALLOWED_OPS
    assert "segment" in AUX_ALLOWED_OPS
