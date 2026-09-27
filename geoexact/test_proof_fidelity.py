"""No false OK on a proof with a point on a side and a parallelogram."""
import json

import numpy as np
import pytest

from geoexact.core import llm
from geoexact.core.constructions import execute
from geoexact.core.pipeline import generate
from geoexact.core.schema import FigurePlan, PlanError
from geoexact.core.semantics import (
    _PARALLELOGRAM_PROOF, proof_equality, proof_parallelogram_plan,
    semantic_failures,
)


TEXT = "Условие. " + _PARALLELOGRAM_PROOF


@pytest.mark.parametrize("aux", [False, True])
def test_exact_proof_is_fast_verified_and_labelled(aux, monkeypatch):
    monkeypatch.setattr(llm, "classify",
                        lambda *_: pytest.fail("exact theorem must not call an LLM"))
    result = generate(TEXT, with_aux=aux, sess=object(), use_cache=False)
    assert result.ok, (result.reason, result.detail)
    assert result.usage == []
    assert result.warnings == []
    assert result.plan["target"] == {"kind": "none", "args": []}
    assert {tuple(m["pts"]) for m in result.plan["draw"]["equal_marks"]} == {
        ("A", "B"), ("B", "C"), ("B", "D"), ("C", "F"),
    }
    assert 'data-point="F"' in result.svg
    assert result.svg.count('class="tick"') == 6  # 1+1+2+2 strokes
    assert 'data-kind="span"' in result.svg  # AB is split by D
    assert bool(result.plan["draw"]["aux_segments"]) == aux
    assert result.plan["constraints"] == [
        {"type": "dist", "args": ["A", "C"], "value": 1}
    ]


@pytest.mark.parametrize("height", [0.4, 0.65, 1.2])
@pytest.mark.parametrize("reverse", [False, True])
def test_exact_construction_satisfies_goal_for_multiple_triangles(height, reverse):
    plan = proof_parallelogram_plan(TEXT, False)
    next(c for c in plan.constructions if c.out == "B").value = height
    free = np.array([1., 0., 0., 0.] if reverse else [0., 0., 1., 0.])
    coords = execute(plan, free_values=free)
    assert semantic_failures(TEXT, plan, coords) == []
    norm = lambda a, b: np.linalg.norm(coords[a] - coords[b])
    assert abs(norm("B", "D") - norm("C", "F")) < 1e-10
    assert abs(norm("B", "E") - norm("B", "F")) < 1e-10


def wrong_plan():
    data = proof_parallelogram_plan(TEXT, False).to_dict()
    next(c for c in data["constructions"] if c["out"] == "F").update(
        op="line_intersect", args=["A", "C", "B", "D"], value=None)
    # Remove truth claims from the model's own plan; the semantic gate must
    # still reject the text/figure mismatch without relying on mark validation.
    data["draw"]["equal_marks"] = []
    return FigurePlan.from_dict(data)


def test_false_positive_at_endpoint_is_rejected():
    plan = wrong_plan()
    coords = execute(plan, free_values=np.array([0., 0., 1., 0.]))
    assert np.linalg.norm(coords["A"] - coords["F"]) < 1e-12
    failures = semantic_failures(TEXT, plan, coords)
    assert any("точка F не лежит внутри стороны AC" in f for f in failures)
    assert any("заданное равенство" in f for f in failures)


def test_remote_helper_cannot_relax_geometric_claims():
    plan = proof_parallelogram_plan(TEXT, False)
    coords = execute(plan, free_values=np.array([0., 0., 1., 0.]))
    coords["R"] = np.array([1e9, -1e9])
    coords["F"] = coords["F"] + np.array([0., .02])
    failures = semantic_failures(TEXT, plan, coords)
    assert any("точка F" in item for item in failures)
    assert any("заданное равенство" in item for item in failures)


def test_model_cannot_report_wrong_figure_as_verified(monkeypatch):
    text = TEXT + " Перечертите схему."
    assert proof_parallelogram_plan(text, False) is None
    monkeypatch.setattr(llm, "classify",
                        lambda *_: {"ok": True, "class": "M", "space": "plane"})
    monkeypatch.setattr(llm, "formalize",
                        lambda *_, **__: (wrong_plan(), []))
    result = generate(text, sess=object(), use_cache=False, max_retries=0)
    assert not result.ok
    assert result.reason == "SEMANTIC_MISMATCH"
    assert "точка F" in result.detail


@pytest.mark.parametrize("mutator,expected", [
    (lambda d: d.__setitem__("E", d["E"] + np.array([.1, .05])), "параллелограммом"),
    (lambda d: d.__setitem__("D", d["D"] + np.array([.1, .1])), "биссектрисой"),
    (lambda d: d.__setitem__("F", d["C"]), "точка F"),
    (lambda d: d.__setitem__("B", d["B"] + np.array([.25, 0.])), "AB=BC"),
])
def test_independent_claim_checks_reject_distortions(mutator, expected):
    plan = proof_parallelogram_plan(TEXT, False)
    coords = execute(plan, free_values=np.array([0., 0., 1., 0.]))
    mutator(coords)
    assert any(expected in item for item in semantic_failures(TEXT, plan, coords))


def test_missing_parallelogram_side_is_not_ok():
    plan = proof_parallelogram_plan(TEXT, False)
    data = plan.to_dict()
    data["draw"]["segments"].remove(["D", "E"])
    broken = FigurePlan.from_dict(data)
    coords = execute(plan, free_values=np.array([0., 0., 1., 0.]))
    assert any("не все стороны параллелограмма" in item
               for item in semantic_failures(TEXT, broken, coords))


@pytest.mark.parametrize("kind", ["UNKNOWN_TARGET", "dist_eq", "proof", "distance_equality"])
def test_proof_target_alias_normalized_only_for_named_proof(monkeypatch, kind):
    data = proof_parallelogram_plan(TEXT, False).to_dict()
    data["target"] = {"kind": kind, "args": ["B", "E", "B", "F"]}
    data["draw"]["aux_points"] = []
    monkeypatch.setattr(llm, "_chat",
                        lambda *_, **__: (json.dumps(data), llm.Usage()))
    plan, _ = llm.formalize(object(), TEXT, "M", False, llm.Budget())
    assert plan.target.kind == "none"
    assert plan.target.args == []
    with pytest.raises(PlanError, match="UNKNOWN_TARGET"):
        llm.formalize(object(), "Постройте треугольник ABC.",
                      "M", False, llm.Budget())


def test_template_not_used_when_statement_is_augmented():
    assert proof_equality(TEXT) == ("BE", "BF")
    assert proof_parallelogram_plan(TEXT + " Дополнительно угол A равен 60°.", False) is None
