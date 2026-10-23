"""Given ratios are marked, and crossing cevians get the parallel-line construction."""
import numpy as np
import pytest

from geoexact.core import llm
from geoexact.core.pipeline import generate
from geoexact.core.ratios import _given_ratios
from geoexact.test_hard_corpus import ratio_plan

TASK = ("В треугольнике ABC на стороне BC взята точка D, причём BD : DC = 1 : 2. "
        "На стороне AC взята точка E, причём AE : EC = 1 : 3. Отрезки AD и BE пересекаются "
        "в точке O.\n\nНайдите:\n\n1. Отношения AO : OD и BO : OE.\n\n"
        "2. Площадь четырёхугольника ODCE, если площадь треугольника ABC равна S.")


@pytest.fixture
def bare_model(monkeypatch):
    """The model returns a bare figure: no marks, no auxiliary construction."""
    monkeypatch.setattr(llm, "classify", lambda *_: {"ok": True, "class": "M", "space": "plane"})
    monkeypatch.setattr(llm, "formalize", lambda *_, **__: (ratio_plan(), []))


def test_parsing_skips_goals_and_proofs():
    assert _given_ratios("BD : DC = 1 : 2. AE/EC = 1/3.")[0][1] == [1.0, 2.0]
    assert len(_given_ratios("BD : DC = 1 : 2. AE : EC = 1 : 3.")) == 2
    assert _given_ratios("Докажите, что AM : MA1 = 2 : 1.") == []
    assert _given_ratios("Найдите AO : OD, если AO : OD = 1 : 1.") == []
    assert _given_ratios("$AB : BC : CA = 3 : 4 : 5$")[0][1] == [3.0, 4.0, 5.0]


def test_ratio_marks_in_plain_mode(bare_model):
    r = generate(TASK, False, sess=object(), use_cache=False)
    marks = {tuple(m["pts"]): m["text"] for m in r.plan["draw"]["length_marks"]}
    assert marks == {("B", "D"): "x", ("D", "C"): "2x", ("A", "E"): "y", ("E", "C"): "3y"}
    assert r.plan["draw"]["aux_segments"] == []
    assert ">2x<" in r.svg and ">3y<" in r.svg


def test_parallel_aux_in_aux_mode(bare_model):
    r = generate(TASK, True, sess=object(), use_cache=False)
    assert r.ok and r.verification == "constraints_only"
    d = r.plan["draw"]
    assert d["aux_segments"] == [["D", "F"]]
    cons = {c["out"]: c for c in r.plan["constructions"]}
    assert cons["F"]["op"] == "line_intersect" and cons["F"]["args"][2:] == ["A", "C"]
    # F is really on AC and DF ∥ BE, checked from the plan itself
    from geoexact.core.constructions import execute
    from geoexact.core.schema import FigurePlan
    from geoexact.core.solver import solve
    plan = FigurePlan.from_dict(r.plan)
    sol = next(s for s in solve(plan, n_seeds=4) if s.ok)
    P = {k: np.asarray(v, float) for k, v in sol.coords.items()}
    cross = lambda u, v: u[0] * v[1] - u[1] * v[0]
    assert abs(cross(P["F"] - P["A"], P["C"] - P["A"])) < 1e-8
    assert abs(cross(P["F"] - P["D"], P["E"] - P["B"])) < 1e-8
    # AE = EF (same line) and AO = OD are verified equalities, marked in the aux layer
    tick = {frozenset(m["pts"]) for m in d["equal_marks"]}
    assert {frozenset("AO"), frozenset("OD")} <= tick
    texts = {frozenset(m["pts"]): m["text"] for m in d["length_marks"]}
    assert texts[frozenset("EF")] == "y"
    assert np.linalg.norm(P["A"] - P["E"]) == pytest.approx(np.linalg.norm(P["E"] - P["F"]))
    assert np.linalg.norm(P["A"] - P["O"]) == pytest.approx(np.linalg.norm(P["O"] - P["D"]))


def test_no_aux_when_model_already_built_one(monkeypatch):
    plan = ratio_plan()
    plan.draw.aux_segments.append(["D", "E"])
    monkeypatch.setattr(llm, "classify", lambda *_: {"ok": True, "class": "M", "space": "plane"})
    monkeypatch.setattr(llm, "formalize", lambda *_, **__: (plan, []))
    r = generate(TASK, True, sess=object(), use_cache=False)
    assert r.plan["draw"]["aux_segments"] == [["D", "E"]]
    assert "F" not in r.plan["points"]


def test_wrong_ratio_is_not_marked(monkeypatch):
    monkeypatch.setattr(llm, "classify", lambda *_: {"ok": True, "class": "M", "space": "plane"})
    monkeypatch.setattr(llm, "formalize", lambda *_, **__: (ratio_plan(d=0.5), []))
    text = TASK.replace("BD : DC = 1 : 2", "BD : DC = 1 : 1")      # figure and text agree: 1 : 1
    r = generate(text, False, sess=object(), use_cache=False)
    marks = {tuple(m["pts"]): m["text"] for m in r.plan["draw"]["length_marks"]}
    assert marks[("B", "D")] == "x" and marks[("D", "C")] == "x"
