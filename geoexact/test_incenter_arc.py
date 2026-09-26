"""The second A-bisector/circumcircle intersection is not on BC."""
import numpy as np
import pytest

from geoexact.core.constructions import execute
from geoexact.core.pipeline import generate
from geoexact.core.schema import FigurePlan
from geoexact.core.semantics import semantic_failures, theorem_plan


PROBLEM = (
    "Условие. Пусть I — центр вписанной окружности треугольника ABC. "
    "Биссектриса угла A второй раз пересекает описанную окружность "
    "треугольника в точке W. Докажите, что WB = WC = WI."
)


@pytest.mark.parametrize("with_aux", [False, True])
def test_full_theorem_skips_llm_and_draws_faithfully(with_aux, monkeypatch):
    from geoexact.core import llm
    monkeypatch.setattr(
        llm, "classify",
        lambda *_: pytest.fail("Exact theorem should not call an LLM"),
    )
    result = generate(PROBLEM, with_aux=with_aux, sess=object(), use_cache=False)
    assert result.ok, (result.reason, result.detail)
    assert result.usage == []
    assert result.warnings == []
    assert result.plan["constraints"] == []  # no invented side lengths
    assert next(c for c in result.plan["constructions"]
                if c["out"] == "W")["op"] == "bisector_circumcircle"
    assert 'data-point="W"' in result.svg


@pytest.mark.parametrize("C", [
    (0.15, 0.65), (0.5, 1.2), (1.45, 0.35), (-0.25, 0.7), (0.85, -0.6),
])
def test_circle_bisector_theorem_on_different_triangles(C):
    plan = theorem_plan(PROBLEM, False)
    points = execute(plan, free_values=np.array([0., 0., 1., 0., *C]))
    assert not semantic_failures(PROBLEM, plan, points)
    W = points["W"]
    distances = [np.linalg.norm(W - points[name]) for name in ("B", "C", "I")]
    assert max(distances) - min(distances) < 1e-8
    assert np.linalg.norm(W - points["A"]) > 0.1


def wrong_plan():
    return FigurePlan.from_dict({
        "points": ["A", "B", "C", "I", "W"],
        "constructions": [
            *({"op": "free_point", "out": name} for name in "ABC"),
            {"op": "incenter", "out": "I", "args": ["A", "B", "C"]},
            {"op": "bisector_point", "out": "W", "args": ["A", "B", "C"]},
        ],
        "constraints": [
            {"type": "dist", "args": ["A", "B"], "value": 6},
            {"type": "dist", "args": ["B", "C"], "value": 7},
            {"type": "dist", "args": ["C", "A"], "value": 8},
        ],
        "draw": {"segments": [["A", "B"], ["B", "C"], ["C", "A"],
                              ["A", "W"], ["W", "I"]]},
        "target": {"kind": "none", "args": []},
        "scale_free": False,
    })


def test_wrong_w_on_bc_is_not_reported_as_verified(monkeypatch):
    from geoexact.core import llm
    # The conclusion is intentionally phrased differently to exercise the
    # semantic gate even without the deterministic full-theorem template.
    text = PROBLEM.replace("WB = WC = WI", "W лежит на дуге BC")
    assert theorem_plan(text, False) is None
    monkeypatch.setattr(llm, "classify",
                        lambda *_: {"ok": True, "class": "M", "space": "plane"})
    monkeypatch.setattr(llm, "formalize",
                        lambda *_, **__: (wrong_plan(), []))
    result = generate(text, sess=object(), use_cache=False, max_retries=0)
    assert not result.ok
    assert result.reason == "SEMANTIC_MISMATCH"
    assert "описанной окружности" in result.detail


def test_invented_lengths_rejected_even_with_correct_w():
    plan = theorem_plan(PROBLEM, False)
    data = plan.to_dict()
    data["constraints"] = [
        {"type": "dist", "args": ["A", "B"], "value": 6},
        {"type": "dist", "args": ["B", "C"], "value": 7},
    ]
    invented = FigurePlan.from_dict(data)
    points = execute(invented, free_values=np.array([0., 0., 1., 0., 0.4, 0.9]))
    assert any("придумал числовые длины" in e
               for e in semantic_failures(PROBLEM, invented, points))


def test_extra_condition_does_not_use_exact_template():
    assert theorem_plan(PROBLEM + " Дополнительно AB = AC.", False) is None


def test_photo_latex_names_use_same_exact_template():
    photo_text = (
        "Условие. Пусть \\(I\\) — центр вписанной окружности треугольника "
        "\\(ABC\\). Биссектриса угла \\(A\\) второй раз пересекает описанную "
        "окружность треугольника в точке \\(W\\). "
        "Докажите, что \\(WB = WC = WI\\)."
    )
    assert theorem_plan(photo_text, False) is not None
    assert theorem_plan(photo_text + " При этом AB=AC.", False) is None
