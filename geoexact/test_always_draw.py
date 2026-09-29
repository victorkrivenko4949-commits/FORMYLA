"""Every recognisable figure produces a drawing; strictness moves to labels.

Verified drawings stay verified. When strict checks fail, the user gets the
most trustworthy drawing available, explicitly marked as approximate,
simplified or a keyword sketch, instead of an error code.
"""
import numpy as np
import pytest

from geoexact.core import llm
from geoexact.core.pipeline import generate
from geoexact.core.schema import FigurePlan, PlanError
from geoexact.core.semantics import semantic_failures
from geoexact.core.sketch import sketch_plan
from geoexact.core.solver import solve

RATIO = ("Условие В треугольнике ABC на стороне BC взята точка D, причём "
         "BD : DC = 1 : 2. На стороне AC взята точка E, причём AE : EC = 1 : 3. "
         "Отрезки AD и BE пересекаются в точке O. Найдите:")


def ratio_plan(constraints=None):
    return FigurePlan.from_dict({
        "points": ["A", "B", "C", "D", "E", "O"],
        "constructions": [
            {"op": "free_point", "out": "A"},
            {"op": "free_point", "out": "B"},
            {"op": "free_point", "out": "C"},
            {"op": "divide_segment", "out": "D", "args": ["B", "C"], "value": 1 / 3},
            {"op": "divide_segment", "out": "E", "args": ["A", "C"], "value": 1 / 4},
            {"op": "line_intersect", "out": "O", "args": ["A", "D", "B", "E"]},
        ],
        "constraints": constraints or [
            {"type": "dist", "args": ["B", "C"], "value": 6},
            {"type": "angle", "args": ["A", "B", "C"], "value": 60},
            {"type": "angle", "args": ["B", "C", "A"], "value": 55},
        ],
        "draw": {"segments": [["A", "B"], ["B", "C"], ["C", "A"],
                              ["A", "D"], ["B", "E"]]},
        "scale_free": True,
    })


@pytest.fixture
def model(monkeypatch):
    monkeypatch.setattr(llm, "classify",
                        lambda *_: {"ok": True, "class": "M", "space": "plane"})
    return lambda fn: monkeypatch.setattr(llm, "formalize", fn)


def test_ratio_is_not_misread_as_length():
    """'BD : DC = 1 : 2' used to be parsed as the length DC = 1."""
    plan = ratio_plan()
    sol = next(s for s in solve(plan, n_seeds=4) if s.ok)
    assert semantic_failures(RATIO, plan, sol.coords) == []
    for text in ("BD:DC = AE:EC", "AB + BC = 12", "AB = 2x", "AB = 1/2 BC"):
        assert semantic_failures(text, plan, sol.coords) == []


def test_user_ratio_problem_is_verified(model):
    model(lambda *_, **__: (ratio_plan(), []))
    r = generate(RATIO, sess=object(), use_cache=False)
    assert r.ok and r.stage == "9-render"
    assert r.verification == "constraints_only"
    assert not any(w.startswith("ORPHAN_POINT: O") for w in r.warnings)


def test_impossible_model_plan_is_drawn_as_approximate(model):
    impossible = [{"type": "dist", "args": ["B", "C"], "value": 6},
                  {"type": "dist", "args": ["A", "B"], "value": 1},
                  {"type": "dist", "args": ["A", "C"], "value": 10}]
    model(lambda *_, **__: (ratio_plan(impossible), []))
    r = generate(RATIO, sess=object(), use_cache=False)
    assert r.ok and r.verification == "approximate"
    assert r.stage == "9-render-fallback" and r.measured is None
    assert r.warnings[0].startswith("APPROXIMATE:")
    assert "<svg" in r.svg


def test_last_resort_simplified_attempt(model):
    seen = []

    def formalize(sess, problem, cls, aux, budget, feedback="", prev_code=""):
        seen.append(prev_code)
        if prev_code != "SIMPLIFY":
            raise PlanError("BAD_JSON", "повреждённый JSON")
        return ratio_plan(), []

    model(formalize)
    r = generate(RATIO, sess=object(), use_cache=False, max_retries=1)
    assert seen[-1] == "SIMPLIFY" and len(seen) == 3
    assert r.ok and r.verification == "simplified" and r.measured is None
    assert r.warnings[0].startswith("SIMPLIFIED:")


@pytest.mark.parametrize("code", ["UNSUPPORTED_CONSTRUCTION", "NETWORK_UNCERTAIN"])
def test_model_or_network_failure_still_draws_sketch(model, code):
    def formalize(*_, **__):
        raise PlanError(code, "нет")

    model(formalize)
    r = generate(RATIO, sess=object(), use_cache=False)
    assert r.ok and r.verification == "sketch"
    coords = __import__("geoexact.core.constructions", fromlist=["execute"]).execute(
        FigurePlan.from_dict(r.plan), free_values=sketch_plan(RATIO)[1])
    B, C, D = (np.asarray(coords[k]) for k in "BCD")
    assert np.allclose(D, B + (C - B) / 3)          # BD : DC = 1 : 2
    A, E = np.asarray(coords["A"]), np.asarray(coords["E"])
    assert np.allclose(E, A + (np.asarray(coords["C"]) - A) / 4)  # AE : EC = 1 : 3


def test_classify_failure_draws_sketch(monkeypatch):
    def broken(*_):
        raise PlanError("NETWORK_UNCERTAIN", "нет ответа")

    monkeypatch.setattr(llm, "classify", broken)
    r = generate(RATIO, sess=object(), use_cache=False)
    assert r.ok and r.verification == "sketch"


@pytest.mark.parametrize("text,points,circles", [
    ("В прямоугольном треугольнике ABC с прямым углом C проведена высота CH.",
     {"A", "B", "C", "H"}, 0),
    ("В равнобедренном треугольнике ABC (AB = BC) проведены медиана BM и биссектриса AL.",
     {"M", "L"}, 0),
    ("Диагонали параллелограмма ABCD пересекаются в точке O. M — середина AB.",
     {"O", "M"}, 0),
    ("Около треугольника ABC описана окружность.", {"O"}, 1),
    ("На стороне BC треугольника ABC отмечены точки M и N так, что BM = MN = NC.",
     {"M", "N"}, 0),
    ("Квадрат ABCD, точка K на стороне BC.", {"K"}, 0),
    ("Правильный шестиугольник ABCDEF.", set("ABCDEF"), 0),
    ("Две окружности с центрами O и Q пересекаются.", {"O", "Q"}, 2),
    ("Дан угол AOB, равный 60°.", {"A", "O", "B"}, 0),
    ("В △ABC проведена медиана AM.", {"M"}, 0),
])
def test_sketch_recognises_common_wording(text, points, circles):
    built = sketch_plan(text)
    assert built is not None
    plan, _ = built
    assert points <= set(plan.points)
    assert len(plan.draw.circles) == circles


def test_non_geometry_has_no_sketch():
    assert sketch_plan("Найдите x, если 2x + 3 = 7.") is None
