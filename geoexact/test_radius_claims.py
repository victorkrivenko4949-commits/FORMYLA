"""Радиус описанной/вписанной окружности названного треугольника — проверяемое условие."""
import numpy as np
import pytest

from geoexact.core import llm, radius_claims as rc, semantics
from geoexact.core.schema import FigurePlan
from geoexact.core.semantics import semantic_failures

TEXT = ("Точка D лежит на основании AB равнобедренного тупоугольного треугольника ABC так, что "
        "отрезок AD равен радиусу описанной окружности треугольника BCD. Найдите угол ACD.")
H = float(np.tan(np.radians(30)))
# верная конфигурация: угол C = 120°, ∠ACD = 30°  =>  AD = R(BCD) = 2/3
GOOD = {"A": (-1., 0.), "B": (1., 0.), "C": (0., H), "D": (-1 / 3, 0.)}
# чертёж модели: D — середина AB, нарисована окружность (ABC); AD = 1, R(BCD) ≈ 0.577
BAD = {"A": (-1., 0.), "B": (1., 0.), "C": (0., H), "D": (0., 0.)}


def _np(d):
    return {k: np.array(v, dtype=float) for k, v in d.items()}


def test_claims_are_parsed():
    want = [{"seg": ("A", "D"), "value": None, "factor": 1, "kind": "circum", "tri": ("B", "C", "D")}]
    assert rc.radius_claims(TEXT) == want
    assert rc.radius_claims("AD равен радиусу окружности, описанной около треугольника $BCD$.") == want
    assert rc.radius_claims("CD равен диаметру описанной окружности треугольника ABD")[0]["factor"] == 2
    claims = rc.radius_claims("Радиус вписанной окружности треугольника ABC равен 2. "
                              "Радиус описанной окружности треугольника ABC равен AH.")
    assert [(c["kind"], c["value"], c["seg"]) for c in claims] == [("in", 2.0, None), ("circum", None, ("A", "H"))]
    assert rc.radius_claims("В треугольнике ABC проведена медиана AM.") == []
    # цель доказательства — не данность
    assert rc.radius_claims("Докажите, что AD равен радиусу описанной окружности треугольника BCD.") == []


def test_triangle_radius_on_3_4_5():
    P, Q, R = np.array([0., 0.]), np.array([6., 0.]), np.array([0., 8.])
    assert rc.triangle_radius("circum", P, Q, R) == pytest.approx(5.0)
    assert rc.triangle_radius("in", P, Q, R) == pytest.approx(2.0)
    assert rc.triangle_radius("circum", P, Q, 2 * Q) is None


def test_failures_good_bad_missing():
    assert rc.radius_failures(TEXT, None, _np(GOOD)) == []
    bad = rc.radius_failures(TEXT, None, _np(BAD))
    assert len(bad) == 1 and bad[0].startswith(rc.PREFIX)
    assert "circumcenter(B,C,D)" in bad[0] and "dist_eq [A,D,O,B]" in bad[0]
    missing = rc.radius_failures(TEXT, None, {k: v for k, v in _np(GOOD).items() if k != "D"})
    assert missing and "нет точек D" in missing[0]
    inr = rc.radius_failures("Радиус вписанной окружности треугольника ABC равен 2.", None,
                             _np({"A": (0, 0), "B": (6, 0), "C": (0, 8)}))
    assert inr == []


def test_semantic_failures_is_wrapped_and_rules_added():
    assert getattr(semantics.semantic_failures, "_radius_claims", False)
    assert rc.MARK in llm.SYS_FORMALIZE and llm.SYS_FORMALIZE.count("33. Радиус описанной") == 1


def bad_plan():
    return FigurePlan.from_dict({
        "points": ["A", "B", "C", "D", "O"],
        "constructions": [*({"op": "free_point", "out": p} for p in "ABC"),
                          {"op": "midpoint", "out": "D", "args": ["A", "B"]},
                          {"op": "circumcenter", "out": "O", "args": ["A", "B", "C"]}],
        "constraints": [{"type": "dist_eq", "args": ["C", "A", "C", "B"]},
                        {"type": "angle", "args": ["A", "C", "B"], "value": 118}],
        "draw": {"segments": [["A", "B"], ["B", "C"], ["C", "A"], ["C", "D"]],
                 "circles": [["O", "A"]], "hide_labels": ["O"]},
        "target": {"kind": "angle", "args": ["A", "C", "D"]}, "scale_free": True})


def good_plan():
    return FigurePlan.from_dict({
        "points": ["A", "B", "C", "D", "O"],
        "constructions": [*({"op": "free_point", "out": p} for p in "ABCD"),
                          {"op": "circumcenter", "out": "O", "args": ["B", "C", "D"]}],
        "constraints": [{"type": "dist_eq", "args": ["C", "A", "C", "B"]},
                        {"type": "angle", "args": ["A", "C", "B"], "value": 120},
                        {"type": "on_segment", "args": ["D", "A", "B"]},
                        {"type": "dist_eq", "args": ["A", "D", "O", "B"]}],
        "draw": {"segments": [["A", "B"], ["B", "C"], ["C", "A"], ["C", "D"]],
                 "circles": [["O", "B"]], "hide_labels": ["O"]},
        "target": {"kind": "angle", "args": ["A", "C", "D"]}, "scale_free": True})


def test_bad_plan_is_rejected_by_semantic_gate():
    from geoexact.core.constructions import execute
    plan = bad_plan()
    P = execute(plan, free_values=np.array([-1., 0., 1., 0., 0., H]))
    assert any(f.startswith(rc.PREFIX) for f in semantic_failures(TEXT, plan, P))


def test_correct_constraints_give_30_degrees():
    from geoexact.core.gates import _angle_deg
    from geoexact.core.solver import solve
    plan = good_plan()
    sols = [s for s in solve(plan, n_seeds=24) if s.ok]
    assert sols, "решатель не нашёл конфигурацию с AD = R(BCD)"
    for s in sols:
        assert semantic_failures(TEXT, plan, s.coords) == []
        acd = _angle_deg(s.coords["A"], s.coords["C"], s.coords["D"])
        assert min(abs(acd - 30), abs(acd - 150)) < 1e-3


def test_pipeline_never_reports_model_figure_as_verified(monkeypatch):
    from geoexact.core.pipeline import generate
    monkeypatch.setattr(llm, "classify", lambda *_: {"ok": True, "class": "M", "space": "plane"})
    monkeypatch.setattr(llm, "formalize", lambda *_, **__: (bad_plan(), []))
    r = generate(TEXT, sess=object(), use_cache=False, max_retries=0)
    assert r.ok
    assert r.verification == "approximate"
    assert any(rc.PREFIX in w for w in r.warnings)
