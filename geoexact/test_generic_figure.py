"""A proof about an arbitrary triangle must not be drawn for one rigid triangle."""
import numpy as np
import pytest

from geoexact.core import llm
from geoexact.core.constructions import execute, _circumcenter
from geoexact.core.pipeline import generate
from geoexact.core.schema import FigurePlan
from geoexact.core.semantics import _generic_failures
from geoexact.core.solver import solve

PXQ = ("Дан остроугольный треугольник ABC. Точка P выбрана так, что AP = AB и PB ∥ AC. "
       "Точка Q выбрана так, что AQ = AC и CQ ∥ AB. Отрезки CP и BQ пересекаются в точке X. "
       "Докажите, что центр описанной окружности треугольника ABC лежит на окружности (PXQ).")
SEGS = [["A", "B"], ["B", "C"], ["C", "A"], ["C", "P"], ["B", "Q"]]


def plan(kind):
    cons = [{"op": "free_point", "out": n} for n in "ABC"]
    cs, pts = [], list("ABCPQXO")
    if kind == "rigid":
        cons += [{"op": "translate", "out": "P", "args": ["A", "C", "B"]},
                 {"op": "translate", "out": "Q", "args": ["A", "B", "C"]}]
        cs = [{"type": "dist_eq", "args": ["A", "P", "A", "B"]},
              {"type": "dist_eq", "args": ["A", "Q", "A", "C"]}]
    else:
        pts += ["H", "K"]
        cons += [{"op": "translate", "out": "H", "args": ["B", "A", "C"]},
                 {"op": "line_circle_other", "out": "P", "args": ["B", "H", "A", "B"]},
                 {"op": "translate", "out": "K", "args": ["C", "A", "B"]},
                 {"op": "line_circle_other", "out": "Q", "args": ["C", "K", "A", "C"]}]
    cons += [{"op": "line_intersect", "out": "X", "args": ["C", "P", "B", "Q"]},
             {"op": "circumcenter", "out": "O", "args": ["A", "B", "C"]}]
    return FigurePlan.from_dict({"points": pts, "constructions": cons, "constraints": cs,
                                 "draw": {"segments": SEGS, "hide_labels": ["H", "K"] if kind != "rigid" else []},
                                 "scale_free": True})


def test_line_circle_other_gives_the_second_root_for_any_triangle():
    rng = np.random.default_rng(3)
    for _ in range(40):
        fv = rng.uniform(-3, 3, 6)
        c = execute(plan("generic"), free_values=fv)
        A, B, C, P, Q, X, O = (c[k] for k in "ABCPQXO")
        cr = lambda u, v: u[0] * v[1] - u[1] * v[0]
        assert np.linalg.norm(P - A) == pytest.approx(np.linalg.norm(B - A))
        assert abs(cr(P - B, C - A)) < 1e-9 * np.linalg.norm(C - A) * np.linalg.norm(P - B) + 1e-9
        assert np.linalg.norm(Q - A) == pytest.approx(np.linalg.norm(C - A))
        # the statement itself: O lies on circle (PXQ)
        Z = _circumcenter(P, X, Q)
        assert np.linalg.norm(O - Z) == pytest.approx(np.linalg.norm(P - Z), rel=1e-7)


def test_rigid_plan_is_flagged_and_generic_is_not():
    for kind, flagged in (("rigid", True), ("generic", False)):
        pl = plan(kind)
        sols = [s for s in solve(pl, n_seeds=8) if s.ok]
        assert sols
        assert bool(_generic_failures(PXQ, pl, sols[0].coords)) is flagged


def test_numbers_or_special_words_disable_the_check():
    pl = plan("rigid")
    sol = next(s for s in solve(pl, n_seeds=8) if s.ok)
    assert _generic_failures(PXQ + " Пусть AB = 5.", pl, sol.coords) == []
    assert _generic_failures(PXQ.replace("остроугольный", "равнобедренный"), pl, sol.coords) == []
    assert _generic_failures(PXQ.replace("Докажите", "Найдите"), pl, sol.coords) == []


@pytest.fixture
def model(monkeypatch):
    monkeypatch.setattr(llm, "classify", lambda *_: {"ok": True, "class": "M", "space": "plane"})
    monkeypatch.setattr(llm, "aux_plan", lambda *_, **__: {"steps": []})


def test_retry_replaces_rigid_plan_with_generic_one(monkeypatch, model):
    answers = [plan("rigid"), plan("generic")]
    feedbacks = []

    def formalize(sess, text, cls, aux, budget, feedback="", prev=""):
        feedbacks.append(feedback)
        return answers[min(len(feedbacks) - 1, 1)], []
    monkeypatch.setattr(llm, "formalize", formalize)
    r = generate(PXQ, False, sess=object(), use_cache=False)
    assert r.ok and r.verification == "constraints_only"
    assert "line_circle_other" in feedbacks[1]
    assert "H" in r.plan["points"] and "line_circle_other" in str(r.plan["constructions"])


def test_only_rigid_answers_still_draw_something(monkeypatch, model):
    monkeypatch.setattr(llm, "formalize", lambda *_, **__: (plan("rigid"), []))
    r = generate(PXQ, False, sess=object(), use_cache=False)
    assert r.ok and "<svg" in r.svg


def test_sample_numbers_do_not_count_as_specialisation():
    pl = plan("generic")
    pl.constraints.extend(FigurePlan.from_dict({"points": ["A", "B", "C"], "constructions": [],
        "constraints": [{"type": "dist", "args": ["A", "B"], "value": 5},
                        {"type": "dist", "args": ["A", "C"], "value": 6},
                        {"type": "dist", "args": ["B", "C"], "value": 7}]}).constraints)
    sol = next(s for s in solve(pl, n_seeds=8) if s.ok)
    assert _generic_failures(PXQ, pl, sol.coords) == []


def test_made_up_numeric_labels_are_removed_for_number_free_problem():
    from geoexact.core.pipeline import _strip_invented_labels
    pl = plan("generic")
    pl.draw.length_marks = [{"pts": ["A", "B"], "text": "5", "layer": "main"},
                            {"pts": ["A", "C"], "text": "a", "layer": "main"}]
    _strip_invented_labels(PXQ, pl)
    assert [m["text"] for m in pl.draw.length_marks] == ["a"]
    pl.draw.length_marks = [{"pts": ["A", "B"], "text": "5", "layer": "main"}]
    _strip_invented_labels(PXQ + " AB = 5.", pl)
    assert len(pl.draw.length_marks) == 1


def test_undeclared_helper_point_is_declared_not_rejected():
    from geoexact.core.llm import _declare_helper_points
    d = plan("generic").to_dict()
    d["points"] = [p for p in d["points"] if p not in ("H", "K")]
    d["draw"]["hide_labels"] = []
    _declare_helper_points(d)
    assert {"H", "K"} <= set(d["points"]) and {"H", "K"} <= set(d["draw"]["hide_labels"])
    FigurePlan.from_dict(d)


def test_circle_named_in_the_statement_is_drawn():
    from geoexact.core import auxplan
    pl = plan("generic")
    sol = next(s for s in solve(pl, n_seeds=8) if s.ok)
    new, coords = auxplan.add_named_circles(pl, sol.coords, PXQ)
    centre, ref = new.draw.circles[-1]
    P, X, Q = (np.asarray(coords[n]) for n in "PXQ")
    r = np.linalg.norm(np.asarray(coords[centre]) - P)
    assert np.linalg.norm(np.asarray(coords[centre]) - X) == pytest.approx(r)
    assert np.linalg.norm(np.asarray(coords[centre]) - Q) == pytest.approx(r)
    assert centre in new.draw.hide_labels
    # a second call does not duplicate it, and unknown/collinear names are ignored
    again, _ = auxplan.add_named_circles(new, coords, PXQ)
    assert len(again.draw.circles) == len(new.draw.circles)
    same, _ = auxplan.add_named_circles(pl, sol.coords, "окружность (PXZ)")
    assert same is pl


def test_sketch_for_the_pxq_problem_is_the_real_figure():
    from geoexact.core.pipeline import _sketch_result
    for aux in (False, True):
        r = _sketch_result(PXQ, aux, None)
        assert r is not None and r.verification == "sketch"
        d = r.plan["draw"]
        assert {frozenset(s) for s in d["segments"]} >= {frozenset("CP"), frozenset("BQ")}
        ops = {c["out"]: c for c in r.plan["constructions"]}
        assert ops["P"]["op"] == "line_circle_other" and ops["Q"]["op"] == "line_circle_other"
        assert ops["X"]["op"] == "line_intersect"
        pl = FigurePlan.from_dict(r.plan)
        c = execute(pl, free_values=np.array([0, 0, 5, 0, 1.5, 4.]))
        P, X, Q = (np.asarray(c[k]) for k in "PXQ")
        Z = _circumcenter(P, X, Q)
        assert np.linalg.norm(np.asarray(c["O"]) - Z) == pytest.approx(np.linalg.norm(P - Z), rel=1e-7)
        assert ["Z", "P"] in d["circles"]           # the circle (PXQ) from the statement


def test_floating_constructed_point_is_joined_to_its_source():
    from geoexact.core.pipeline import _connect_orphans
    pl = FigurePlan.from_dict({
        "points": list("ABCDOW"),
        "constructions": [{"op": "free_point", "out": n} for n in "ABC"] + [
            {"op": "circumcenter", "out": "O", "args": ["A", "B", "C"]},
            {"op": "midpoint", "out": "D", "args": ["B", "C"]},
            {"op": "line_circle", "out": "W", "args": ["A", "D", "O", "A"], "value": 1}],
        "draw": {"segments": [["A", "B"], ["B", "C"], ["C", "A"], ["A", "D"]], "circles": [["O", "A"]]},
        "scale_free": True})
    _connect_orphans(pl)
    assert ["A", "W"] in pl.draw.segments


def test_aux_data_without_new_points_is_accepted():
    from geoexact.core import auxplan
    coords = {"A": np.array([0., 0.]), "B": np.array([4., 0.]), "C": np.array([1., 3.])}
    pl = FigurePlan.from_dict({"points": list("ABC"),
                               "constructions": [{"op": "free_point", "out": n} for n in "ABC"],
                               "draw": {"segments": [["A", "B"]]}, "scale_free": True})
    out = auxplan.apply_aux(pl, coords, {"idea": "x", "steps": [], "aux_segments": [["B", "C"]]})
    assert out is not None and ["B", "C"] in out[0].draw.aux_segments


def test_no_dimension_brackets_on_split_segments():
    from geoexact.core.render import render_svg
    from geoexact.core.solver import Solution
    pl = FigurePlan.from_dict({
        "points": list("ABCD"),
        "constructions": [{"op": "free_point", "out": n} for n in "ABC"] + [
            {"op": "midpoint", "out": "D", "args": ["A", "B"]}],
        "draw": {"segments": [["A", "B"], ["B", "C"], ["C", "A"]],
                 "equal_marks": [{"pts": ["A", "B"], "count": 1}, {"pts": ["B", "C"], "count": 1},
                                 {"pts": ["B", "C"], "count": 2}, {"pts": ["A", "C"], "count": 2}]},
        "scale_free": True})
    coords = execute(pl, free_values=np.array([0, 0, 4, 0, 1., 3.]))
    svg = render_svg(pl, Solution(coords=coords, residual=0.0, ok=True), gate=None, show_aux=False)
    assert "data-kind=\"span\"" not in svg
    assert svg.count('class="tick') == 4       # only the 2-tick group (BC = AC); no lone tick
