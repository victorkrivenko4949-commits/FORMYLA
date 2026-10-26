# -*- coding: utf-8 -*-
"""Прямая Симсона: спец-план без LLM, защита от вырожденной хорды, правило 45.

Прод-ошибка (26.10.2026): «Точка P лежит на описанной окружности треугольника
ABC... Докажите, что X, Y и Z лежат на одной прямой» — формализатор строил
P как line_circle(A, B, O, A) (хорда!), P совпадал с вершиной, система
дегенерировала, конвейер уходил в схематичный фолбэк. Здесь проверяем, что
конфигурация теперь решается точно без LLM, и что вырожденная хорда
отбраковывается семантикой.
"""
import math

import numpy as np
import pytest

import geoexact.core                       # обёртки устанавливаются при импорте
from geoexact.core import llm, semantics, pipeline
from geoexact.core.schema import FigurePlan
from geoexact.core.solver import solve
from geoexact.core.simson_line import (
    chord_coincidence_failures, simson_plan)

PROD_TEXT = (
    "Точка P лежит на описанной окружности треугольника ABC. X, Y и Z — "
    "основания перпендикуляров, опущенных из точки P на прямые AB, BC и CA "
    "соответственно. Докажите, что точки X, Y и Z лежат на одной прямой.")


def test_rule_45_installed():
    assert "45." in llm.SYS_FORMALIZE
    assert "POINT_ON_CIRCLE_RULE" in llm.SYS_FORMALIZE


def test_engine_suffix():
    assert "+simson1" in pipeline.ENGINE_VERSION


def test_recognizes_prod_problem():
    plan = simson_plan(PROD_TEXT, False)
    assert plan is not None
    cons = {(c.type, tuple(c.args)) for c in plan.constraints}
    assert ("on_circle", ("P", "O", "O", "A")) in cons
    assert ("collinear", ("X", "Y", "Z")) in cons
    ops = {(c.op, tuple(c.args)) for c in plan.constructions}
    assert ("circumcenter", ("A", "B", "C")) in ops
    assert ("foot", ("P", "A", "B")) in ops
    assert ("foot", ("P", "B", "C")) in ops
    assert ("foot", ("P", "C", "A")) in ops
    assert "line_circle" not in {op for op, _ in ops}


def test_special_plan_solves_exactly(monkeypatch):
    """Признанная конфигурация не должна звать LLM и обязана решаться точно."""
    monkeypatch.setattr(
        llm, "classify",
        lambda *_: pytest.fail("спец-план Симсона не должен звать LLM"))
    plan = simson_plan(PROD_TEXT, False)
    sols = solve(plan)
    good = [s for s in sols if s.ok]
    assert len(good) >= 10, [str(getattr(s, "reason", "")) for s in sols[:3]]
    s = good[0]
    P = {k: np.asarray(v, dtype=float) for k, v in s.coords.items()}
    # P действительно на описанной окружности
    o, r = P["O"], float(np.hypot(*(P["A"] - P["O"])))
    assert abs(float(np.hypot(*(P["P"] - o))) - r) < 1e-9 * max(1.0, r)
    # X, Y, Z — основания перпендикуляров (PX ⟂ AB и т.д.)
    for foot, u, v in (("X", "A", "B"), ("Y", "B", "C"), ("Z", "C", "A")):
        d = P[u] - P[v]
        assert abs(float(np.dot(P["P"] - P[foot], d))) < 1e-9, foot
    # заключение теоремы: X, Y, Z коллинеарны
    cross = np.cross(P["Y"] - P["X"], P["Z"] - P["X"])
    assert abs(float(cross)) < 1e-9
    # P не совпадает ни с одной вершиной (нет вырожденной хорды)
    for v in ("A", "B", "C"):
        assert float(np.hypot(*(P["P"] - P[v]))) > 1e-6


def test_end_to_end_generate(monkeypatch):
    monkeypatch.setattr(
        llm, "classify",
        lambda *_: pytest.fail("спец-план Симсона не должен звать LLM"))
    result = pipeline.generate(PROD_TEXT, sess=object(), use_cache=False)
    assert result.ok, (result.reason, result.detail)
    assert "SKETCH" not in "".join(result.warnings)
    assert "FALLBACK" not in "".join(result.warnings)


def test_feet_on_sides_not_recognized():
    """«на СТОРОНЫ» (не прямые) — другая задача, спец-план не включается."""
    text = (PROD_TEXT.replace("на прямые AB, BC и CA", "на стороны AB, BC и CA"))
    assert simson_plan(text, False) is None


def test_no_circumcircle_not_recognized():
    text = PROD_TEXT.replace(
        "Точка P лежит на описанной окружности треугольника ABC. ", "")
    assert simson_plan(text, False) is None


def test_no_collinearity_claim_not_recognized():
    text = PROD_TEXT.replace(
        "Докажите, что точки X, Y и Z лежат на одной прямой.",
        "Докажите, что PX = PY.")
    assert simson_plan(text, False) is None


def test_foreign_lines_not_recognized():
    """Прямые не стороны треугольника — не Симсон."""
    text = PROD_TEXT.replace("на прямые AB, BC и CA", "на прямые AB, BC и BD")
    assert simson_plan(text, False) is None


def _kite_like_coords():
    """Вырожденный прод-план: P = line_circle(A,B,O,A) совпал с вершиной A."""
    return {
        "A": np.array([0.0, 0.0]), "B": np.array([4.0, 0.0]),
        "C": np.array([1.0, 3.0]), "O": np.array([2.0, 0.5]),
        "P": np.array([0.0, 0.0]),       # P совпал с A
        "X": np.array([0.0, 0.0]), "Y": np.array([2.0, 1.0]),
        "Z": np.array([0.2, 0.1]),
    }


def test_chord_coincidence_fires():
    plan = FigurePlan.from_dict({
        "points": ["A", "B", "C", "O", "P", "X", "Y", "Z"],
        "constructions": [
            {"op": "free_point", "out": "A"}, {"op": "free_point", "out": "B"},
            {"op": "free_point", "out": "C"},
            {"op": "circumcenter", "args": ["A", "B", "C"], "out": "O"},
            {"op": "line_circle", "args": ["A", "B", "O", "A"], "out": "P"},
        ],
        "constraints": [],
        "draw": {"segments": [["A", "B"], ["B", "C"], ["C", "A"]]},
        "target": {"kind": "none", "args": []},
        "scale_free": True,
    })
    coords = _kite_like_coords()
    fails = chord_coincidence_failures(plan, coords)
    assert len(fails) == 1
    assert "POINT_ON_CIRCLE" in fails[0] and "P" in fails[0]


def test_chord_coincidence_silent_when_distinct():
    """Та же хорда, но P не совпал с концами — семантика не ругается
    (совпадение поймают гейты вырожденности, здесь проверка узкая)."""
    plan = FigurePlan.from_dict({
        "points": ["A", "B", "C", "O", "P"],
        "constructions": [
            {"op": "free_point", "out": "A"}, {"op": "free_point", "out": "B"},
            {"op": "free_point", "out": "C"},
            {"op": "circumcenter", "args": ["A", "B", "C"], "out": "O"},
            {"op": "line_circle", "args": ["A", "B", "O", "A"], "out": "P"},
        ],
        "constraints": [],
        "draw": {"segments": [["A", "B"], ["B", "C"], ["C", "A"]]},
        "target": {"kind": "none", "args": []},
        "scale_free": True,
    })
    coords = _kite_like_coords()
    coords["P"] = np.array([2.0, 2.0])   # на окружности, но не вершина
    # скорректируем O: центр описанной окружности реального треугольника
    coords["O"] = circumcenter(coords["A"], coords["B"], coords["C"])
    r = float(np.hypot(*(coords["O"] - coords["A"])))
    # поставим P ровно на окружность, подальше от A и B
    coords["P"] = coords["O"] + np.array([r, 0.0])
    assert chord_coincidence_failures(plan, coords) == []


def circumcenter(a, b, c):
    a, b, c = map(np.asarray, (a, b, c))
    d = 2.0 * (a[0] * (b[1] - c[1]) + b[0] * (c[1] - a[1]) + c[0] * (a[1] - b[1]))
    ux = ((a @ a) * (b[1] - c[1]) + (b @ b) * (c[1] - a[1]) + (c @ c) * (a[1] - b[1])) / d
    uy = ((a @ a) * (c[0] - b[0]) + (b @ b) * (a[0] - c[0]) + (c @ c) * (b[0] - a[0])) / d
    return np.array([ux, uy])


def test_chord_check_requires_chord():
    """Прямая не хорда (один конец вне окружности) — проверка молчит:
    это законное пересечение прямой с окружностью."""
    plan = FigurePlan.from_dict({
        "points": ["A", "B", "C", "O", "P"],
        "constructions": [
            {"op": "free_point", "out": "A"}, {"op": "free_point", "out": "B"},
            {"op": "free_point", "out": "C"},
            {"op": "circumcenter", "args": ["A", "B", "C"], "out": "O"},
            {"op": "line_circle", "args": ["A", "D", "O", "A"], "out": "P"},
        ],
        "constraints": [],
        "draw": {"segments": [["A", "B"], ["B", "C"], ["C", "A"]]},
        "target": {"kind": "none", "args": []},
        "scale_free": True,
    })
    coords = _kite_like_coords()
    coords["D"] = np.array([10.0, 10.0])   # вне окружности
    assert chord_coincidence_failures(plan, coords) == []


def test_semantic_wrapper_carries_chord_check():
    """Обёртка semantic_failures включает проверку хорды (флаг установлен)."""
    assert getattr(semantics.semantic_failures, "_simson", False)
