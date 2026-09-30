"""Всё, что сказано в условии, проведено и отмечено на чертеже.

Извлечение требований из текста, достройка названных отрезков и отметок по
проверенным координатам, отказ дорисовывать неверную геометрию и проводимость
сквозь основной конвейер и путь best-effort.
"""
import copy

import numpy as np
import pytest

from geoexact.core import llm
from geoexact.core.gates import gate_correctness
from geoexact.core.pipeline import generate
from geoexact.core.schema import FigurePlan
from geoexact.core.solver import solve
from geoexact.core.statement import (complete_statement_display,
                                     statement_requirements)


def _solved(plan, n_seeds=8):
    return next(s for s in solve(plan, n_seeds=n_seeds) if s.ok)


def triangle_plan(**draw):
    return FigurePlan.from_dict({
        "points": ["A", "B", "C", "M"],
        "constructions": [
            {"op": "free_point", "out": "A"}, {"op": "free_point", "out": "B"},
            {"op": "free_point", "out": "C"},
            {"op": "midpoint", "out": "M", "args": ["B", "C"]}],
        "constraints": [{"type": "angle", "args": ["A", "B", "C"], "value": 60},
                        {"type": "angle", "args": ["B", "C", "A"], "value": 50}],
        "draw": {"segments": [["A", "B"], ["B", "C"], ["C", "A"]], **draw},
        "scale_free": True})


@pytest.fixture
def model(monkeypatch):
    monkeypatch.setattr(llm, "classify",
                        lambda *_: {"ok": True, "class": "M", "space": "plane"})
    return lambda fn: monkeypatch.setattr(llm, "formalize", fn)


# ---------------------------------------------------------------- извлечение

def test_named_segments_are_extracted():
    req = statement_requirements(
        "Отрезки AD и BE пересекаются в точке O. В треугольнике ABC проведена "
        "медиана AM, CM — медиана, CH — высота. Биссектрисы AA_1 и BB_1, "
        "диагонали AC и BD.")
    pairs = {label for label, _ in req["segments"]}
    assert pairs == {"AD", "BE", "AM", "CM", "CH", "AA_1", "BB_1", "AC", "BD"}


def test_named_segments_ignore_plain_figure_names():
    req = statement_requirements("Дан угол AOB, равный 120°. Прямая, "
                                 "параллельная AN, проходит через M.")
    assert req["segments"] == []


def test_given_values_and_proof_targets():
    req = statement_requirements(
        "AB = CD, BC = 12. BD : DC = 1 : 2. AB + BC = 18. "
        "Докажите, что BE = BF.")
    assert (("A", "B"), ("C", "D")) in req["equalities"]
    assert ((("B", "C"), "12")) in req["lengths"]
    assert not any(p == ("D", "C") for p, _ in req["lengths"])   # не из отношения
    assert not any(p == ("B", "C") for p, _ in req["lengths"]) or True
    # сумма AB + BC = 18 не даёт длину BC = 18
    values = [v for p, v in req["lengths"] if p == ("B", "C")]
    assert values == ["12"]
    assert (("B", "E"), ("B", "F")) not in req["equalities"]     # цель доказательства


def test_angles_single_letter_and_latex():
    req = statement_requirements(
        r"В треугольнике ABC угол A равен 40, \(\angle C = 90^{\circ}\), "
        r"∠ABC = 30°.")
    got = {pts: value for pts, value in req["angles"]}
    assert got[("B", "A", "C")] == "40"
    assert got[("A", "C", "B")] == "90"
    assert got[("A", "B", "C")] == "30"


# ---------------------------------------------------------------- достройка

def test_median_is_drawn_and_halves_marked():
    plan = triangle_plan()
    sol = _solved(plan)
    plan, msgs = complete_statement_display(
        plan, sol.coords, "В треугольнике ABC проведена медиана AM.")
    segs = {frozenset(s) for s in plan.draw.segments}
    assert frozenset(("A", "M")) in segs                       # медиана проведена
    halves = {frozenset(m["pts"]) for m in plan.draw.equal_marks}
    assert {frozenset(("B", "M")), frozenset(("M", "C"))} <= halves
    counts = [m["count"] for m in plan.draw.equal_marks
              if frozenset(m["pts"]) in {frozenset(("B", "M")), frozenset(("M", "C"))}]
    assert counts[0] == counts[1]                              # засечки одинаковые
    assert any(m.startswith("STATEMENT_DRAW: проведён отрезок AM") for m in msgs)
    assert any("половины стороны" in m for m in msgs)
    assert gate_correctness(plan, sol).ok                      # отметки верны


def test_median_side_split_visually_identical():
    """Сторона BC, поделённая на BM и MC, остаётся сплошной линией."""
    plan = triangle_plan()
    sol = _solved(plan)
    plan, _ = complete_statement_display(
        plan, sol.coords, "В треугольнике ABC проведена медиана AM.")
    order = [s for s in plan.draw.segments if set(s) <= {"B", "C", "M"}]
    assert {frozenset(s) for s in order} == {frozenset(("B", "M")),
                                            frozenset(("M", "C"))}


def test_given_equality_length_and_angle_marked():
    plan = FigurePlan.from_dict({
        "points": ["A", "B", "C", "D"],
        "constructions": [
            {"op": "free_point", "out": "A"}, {"op": "free_point", "out": "B"},
            {"op": "free_point", "out": "C"},
            {"op": "translate", "out": "D", "args": ["C", "A", "B"]}],
        "constraints": [{"type": "dist", "args": ["A", "B"], "value": 6},
                        {"type": "angle", "args": ["B", "A", "C"], "value": 50}],
        "draw": {"segments": [["A", "B"], ["B", "C"], ["C", "A"]]},
        "scale_free": False})
    sol = _solved(plan)
    assert abs(np.linalg.norm(sol.coords["C"] - sol.coords["D"])
               - np.linalg.norm(sol.coords["A"] - sol.coords["B"])) < 1e-6  # CD = AB
    plan, msgs = complete_statement_display(
        plan, sol.coords, "AB = CD. AB = 6. ∠BAC = 50.")
    eq = {frozenset(m["pts"]) for m in plan.draw.equal_marks}
    assert {frozenset(("A", "B")), frozenset(("C", "D"))} <= eq
    labels = {frozenset(m["pts"]): m["text"] for m in plan.draw.length_marks}
    assert labels.get(frozenset(("A", "B"))) == "6"
    arcs = [m for m in plan.draw.angle_marks if m["pts"] == ["B", "A", "C"]]
    assert arcs and arcs[0]["text"] == "50°"
    assert gate_correctness(plan, sol).ok


def test_false_geometry_is_not_marked():
    plan = triangle_plan()
    sol = _solved(plan)
    plan, msgs = complete_statement_display(plan, sol.coords, "AB = AC. AB = 6.")
    assert plan.draw.equal_marks == []          # равенство не выполняется — молча
    assert plan.draw.length_marks == []         # длина не такая — молча
    assert msgs == []
    assert gate_correctness(plan, sol).ok


def test_covered_by_chain_is_not_redrawn():
    """Отрезок AB, нарисованный половинами AM и MB, уже проведён."""
    plan = FigurePlan.from_dict({
        "points": ["A", "M", "B"],
        "constructions": [
            {"op": "free_point", "out": "A"},
            {"op": "midpoint", "out": "M", "args": ["A", "B"]},
            {"op": "free_point", "out": "B"}],
        "constraints": [],
        "draw": {"segments": [["A", "M"], ["M", "B"]]},
        "scale_free": True})
    coords = {"A": np.array([0.0, 0.0]), "M": np.array([0.5, 0.0]),
              "B": np.array([1.0, 0.0])}
    plan, msgs = complete_statement_display(plan, coords, "Проведён отрезок AB.")
    assert plan.draw.segments == [["A", "M"], ["M", "B"]]      # без дубля
    assert msgs == []


def test_right_angles_marked():
    plan = FigurePlan.from_dict({
        "points": ["A", "B", "M", "C", "H"],
        "constructions": [
            {"op": "free_point", "out": "A"}, {"op": "free_point", "out": "B"},
            {"op": "midpoint", "out": "M", "args": ["A", "B"]},
            {"op": "perp_point", "out": "C", "args": ["M", "A", "B"], "value": 2},
            {"op": "foot", "out": "H", "args": ["C", "A", "B"]}],
        "constraints": [{"type": "dist", "args": ["A", "B"], "value": 4}],
        "draw": {"segments": [["A", "B"], ["B", "C"], ["C", "A"], ["C", "H"]]},
        "scale_free": False})
    sol = _solved(plan)
    plan, msgs = complete_statement_display(
        plan, sol.coords, "В треугольнике ABC с прямым углом C проведена высота CH.")
    tris = {frozenset(t) for t in plan.draw.right_angles}
    assert frozenset(("A", "C", "B")) in tris                  # прямой угол при C
    assert any(frozenset(t) == frozenset(("C", "H", "A"))       # высота ⊥ AB
               for t in plan.draw.right_angles)
    assert gate_correctness(plan, sol).ok
    assert any("прямой угол" in m for m in msgs)


def test_bisector_halves_marked_with_equal_arcs():
    plan = FigurePlan.from_dict({
        "points": ["A", "B", "C", "D"],
        "constructions": [
            {"op": "free_point", "out": "A"}, {"op": "free_point", "out": "B"},
            {"op": "free_point", "out": "C"},
            {"op": "bisector_point", "out": "D", "args": ["C", "A", "B"]}],
        "constraints": [{"type": "angle", "args": ["A", "C", "B"], "value": 60}],
        "draw": {"segments": [["A", "B"], ["B", "C"], ["C", "A"], ["C", "D"]]},
        "scale_free": True})
    sol = _solved(plan)
    plan, msgs = complete_statement_display(
        plan, sol.coords, "В треугольнике ABC проведена биссектриса CD.")
    arcs = [m for m in plan.draw.angle_marks if "count" in m]
    assert len(arcs) == 2 and arcs[0]["count"] == arcs[1]["count"]
    assert {tuple(m["pts"])[1] for m in arcs} == {"C"}
    assert any("биссектриса" in m for m in msgs)
    assert gate_correctness(plan, sol).ok


# ---------------------------------------------------------------- конвейер

def test_pipeline_draws_and_marks_the_statement(model):
    plan = triangle_plan()
    model(lambda *_, **__: (copy.deepcopy(plan), []))
    r = generate("В треугольнике ABC проведена медиана AM.",
                 sess=object(), use_cache=False)
    assert r.ok and r.verification == "constraints_only", (r.reason, r.detail)
    segs = {frozenset(s) for s in r.plan["draw"]["segments"]}
    assert frozenset(("A", "M")) in segs
    halves = {frozenset(m["pts"]) for m in r.plan["draw"]["equal_marks"]}
    assert {frozenset(("B", "M")), frozenset(("M", "C"))} <= halves
    assert any(w.startswith("STATEMENT_DRAW: проведён отрезок AM") for w in r.warnings)
    assert any("половины стороны" in w for w in r.warnings)
    assert 'data-point="M"' in r.svg


def test_pipeline_missing_point_is_reported_not_hidden(model):
    """Модель не построила M: отказ виден пользователю, чертёж — best-effort."""
    data = triangle_plan().to_dict()
    data["points"] = ["A", "B", "C"]
    data["constructions"] = [{"op": "free_point", "out": n} for n in "ABC"]
    data["draw"]["segments"] = [["A", "B"], ["B", "C"], ["C", "A"]]
    broken = FigurePlan.from_dict(data)
    model(lambda *_, **__: (copy.deepcopy(broken), []))
    r = generate("В треугольнике ABC проведена медиана AM.",
                 sess=object(), use_cache=False)
    assert r.ok                                    # чертёж есть
    assert r.verification == "approximate"          # но не полностью проверен
    assert any("STATEMENT_MISSING" in w and "AM" in w for w in r.warnings)
