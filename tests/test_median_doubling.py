# -*- coding: utf-8 -*-
"""Регрессия: удвоение медианы — шаблон отражает ВЕРШИНУ через середину,
и evaluate_usefulness признаёт получившийся параллелограмм полезным."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from geometric_engine.engine import GeometricEngine
from services import aux_templates
from services.aux_usefulness import evaluate_usefulness


def _plan(constructions):
    return {
        "version": 2,
        "canvas": {"width": 600, "height": 500, "margin": 40},
        "constructions": constructions,
    }


def _median_plan():
    # Треугольник ABC, M — середина BC, AM — медиана.
    return _plan([
        {"type": "free_point", "id": "A", "x": 300, "y": 80},
        {"type": "free_point", "id": "B", "x": 100, "y": 420},
        {"type": "free_point", "id": "C", "x": 500, "y": 420},
        {"type": "segment", "id": "AB", "p1": "A", "p2": "B"},
        {"type": "segment", "id": "AC", "p1": "A", "p2": "C"},
        {"type": "segment", "id": "BC", "p1": "B", "p2": "C"},
        {"type": "midpoint", "id": "M", "p1": "B", "p2": "C"},
        {"type": "segment", "id": "AM", "p1": "A", "p2": "M"},
    ])


def test_median_doubling_reflects_apex_not_base_end():
    plan = _median_plan()
    engine = GeometricEngine()
    _, ctx = engine.build(plan)

    cons = aux_templates._t_median_doubling(plan, "В треугольнике ABC медиана AM...", ctx)
    assert cons is not None, "шаблон должен сматчиться"

    reflect = next(c for c in cons if c["type"] == "reflect_point")
    # Отражаемая точка — вершина A (не B/C), центр — M.
    assert reflect["point"] == "A", reflect
    assert reflect["center"] == "M", reflect
    # Новая точка названа человекочитаемо (A1), не aux_...
    assert reflect["id"] == "A1", reflect
    assert reflect.get("label") == "A′", reflect

    # Должны быть три aux-отрезка: продление медианы A-A1 + стороны A1B, A1C.
    segs = [c for c in cons if c["type"] == "segment"]
    assert len(segs) == 3, cons
    # Есть продление медианы A → A1.
    assert any(s["p1"] == "A" and s["p2"] == "A1" for s in segs), cons


def test_median_doubling_is_useful():
    plan = _median_plan()
    engine = GeometricEngine()
    base_svg, base_ctx = engine.build(plan)

    cons = aux_templates._t_median_doubling(plan, "В треугольнике ABC медиана AM...", base_ctx)
    aux_plan = {"has_aux": True, "constructions": cons}
    merged = dict(plan)
    merged["constructions"] = plan["constructions"] + cons
    _, aux_ctx = engine.build(merged)

    r = evaluate_usefulness(base_ctx, aux_ctx, cons)
    # Отразив A через M получили A'; A'B = AC (параллелограмм) — новое равенство.
    assert r["useful"], r
    assert any("equal_segments" in g for g in r["gains"]), r
