"""Common text drawings should not silently omit requested geometry."""
import math

import numpy as np
import pytest

from geoexact.core.constructions import execute
from geoexact.core.pipeline import generate
from geoexact.core.schema import FigurePlan
from geoexact.core.semantics import (
    common_plan, requests_circumcircle, requests_incircle, semantic_failures,
)


INCIRCLE_TEXTS = [
    "В треугольнике ABC точка I — центр вписанной окружности. "
    "Постройте вписанную окружность.",
    "Постройте вписанную окружность треугольника ABC.",
    "В треугольнике ABC проведите окружность с центром I, "
    "касающуюся всех трёх сторон, где I — инцентр.",
]
RHOMBUS = "Постройте ромб ABCD, в котором угол A равен 60°."
CIRCUMCIRCLE = "Постройте описанную окружность треугольника ABC."


@pytest.mark.parametrize("text", INCIRCLE_TEXTS)
@pytest.mark.parametrize("aux", [False, True])
def test_incircle_is_visible_and_has_tangent_radius(text, aux, monkeypatch):
    from geoexact.core import llm
    monkeypatch.setattr(llm, "classify",
                        lambda *_: pytest.fail("common drawing should not call LLM"))
    result = generate(text, with_aux=aux, sess=object(), use_cache=False)
    assert result.ok, (result.reason, result.detail)
    assert result.usage == []
    assert result.warnings == []
    assert result.plan["draw"]["circles"] == [["I", "T"]]
    assert 'class="circ"' in result.svg
    assert 'data-point="I"' in result.svg


@pytest.mark.parametrize("C", [(0.2, 0.7), (0.5, 1.2), (1.4, -0.6)])
def test_incircle_radius_equals_distance_to_each_side(C):
    plan = common_plan(INCIRCLE_TEXTS[0], False)
    coords = execute(plan, free_values=np.array([0., 0., 1., 0., *C]))
    assert semantic_failures(INCIRCLE_TEXTS[0], plan, coords) == []
    I, T = coords["I"], coords["T"]
    radius = np.linalg.norm(I - T)
    for a, b in (("A", "B"), ("B", "C"), ("C", "A")):
        u = coords[b] - coords[a]
        distance = abs(np.linalg.det(np.array([u, I - coords[a]]))) / np.linalg.norm(u)
        assert math.isclose(radius, distance, abs_tol=1e-9)


def _wrong_plan(circle):
    data = common_plan(INCIRCLE_TEXTS[0], False).to_dict()
    data["draw"]["circles"] = circle
    return FigurePlan.from_dict(data)


@pytest.mark.parametrize("circle,expected", [
    ([], "отсутствует"),
    ([["I", "A"]], "неверным центром или радиусом"),
    ([["A", "B"]], "неверным центром или радиусом"),
])
def test_requested_incircle_rejects_missing_or_false_circle(circle, expected):
    plan = _wrong_plan(circle)
    coords = execute(plan, free_values=np.array([0., 0., 1., 0., 0.3, 0.8]))
    assert any(expected in error
               for error in semantic_failures(INCIRCLE_TEXTS[0], plan, coords))


def test_model_retry_replaces_false_incircle(monkeypatch):
    from geoexact.core import llm
    text = INCIRCLE_TEXTS[0] + " Покажите её на рисунке."
    assert common_plan(text, False) is None
    assert requests_incircle(text)
    attempts = []
    monkeypatch.setattr(llm, "classify",
                        lambda *_: {"ok": True, "class": "M", "space": "plane"})

    def formalize(*args):
        attempts.append(args[-2])
        return (_wrong_plan([]) if len(attempts) == 1
                else common_plan(INCIRCLE_TEXTS[0], False)), []

    monkeypatch.setattr(llm, "formalize", formalize)
    result = generate(text, sess=object(), use_cache=False, max_retries=1)
    assert result.ok, (result.reason, result.detail)
    assert result.retries == 1
    assert "draw.circles" in attempts[1]
    assert result.plan["draw"]["circles"] == [["I", "T"]]


@pytest.mark.parametrize("aux", [False, True])
def test_rhombus_is_analytic_and_has_four_equal_sides(aux, monkeypatch):
    from geoexact.core import llm
    monkeypatch.setattr(llm, "classify",
                        lambda *_: pytest.fail("rhombus should not call LLM"))
    result = generate(RHOMBUS, with_aux=aux, sess=object(), use_cache=False)
    assert result.ok, (result.reason, result.detail)
    assert result.usage == []
    assert result.warnings == []
    plan = common_plan(RHOMBUS, aux)
    coords = execute(plan, free_values=np.array([0., 0., 1., 0.]))
    lengths = [np.linalg.norm(coords[b] - coords[a])
               for a, b in (("A", "B"), ("B", "C"), ("C", "D"), ("D", "A"))]
    assert max(lengths) - min(lengths) < 1e-10
    assert math.isclose(
        math.degrees(math.acos(np.dot(coords["B"] - coords["A"],
                                      coords["D"] - coords["A"]))),
        60.0, abs_tol=1e-9,
    )
    assert result.plan["draw"]["angle_marks"][0]["text"] == "60°"


def test_augmented_requests_do_not_silently_lose_conditions():
    assert common_plan(RHOMBUS + " Сторона AB равна 2.", False) is None
    assert common_plan(INCIRCLE_TEXTS[0] + " Угол A равен 40°.", False) is None
    assert not requests_incircle(
        "В треугольнике ABC точка I — центр вписанной окружности. "
        "Постройте биссектрису угла A."
    )


@pytest.mark.parametrize("aux", [False, True])
def test_circumcircle_is_visible_and_correct(aux, monkeypatch):
    from geoexact.core import llm
    monkeypatch.setattr(llm, "classify",
                        lambda *_: pytest.fail("common drawing should not call LLM"))
    result = generate(CIRCUMCIRCLE, with_aux=aux, sess=object(), use_cache=False)
    assert result.ok, (result.reason, result.detail)
    assert result.warnings == []
    assert result.usage == []
    assert result.plan["draw"]["circles"] == [["O", "A"]]
    assert 'class="circ"' in result.svg
    plan = common_plan(CIRCUMCIRCLE, aux)
    for C in ((0.2, 0.7), (1.1, -0.6)):
        points = execute(plan, free_values=np.array([0., 0., 1., 0., *C]))
        assert semantic_failures(CIRCUMCIRCLE, plan, points) == []
        radius = np.linalg.norm(points["O"] - points["A"])
        for name in "BC":
            assert math.isclose(np.linalg.norm(points["O"] - points[name]),
                                radius, abs_tol=1e-9)


def test_missing_or_false_circumcircle_cannot_get_verified():
    assert requests_circumcircle(CIRCUMCIRCLE)
    plan = common_plan(CIRCUMCIRCLE, False)
    coords = execute(plan, free_values=np.array([0., 0., 1., 0., 0.2, 0.7]))
    for circles in ([], [["A", "B"]]):
        data = plan.to_dict()
        data["draw"]["circles"] = circles
        wrong = FigurePlan.from_dict(data)
        failures = semantic_failures(CIRCUMCIRCLE, wrong, coords)
        assert any("описанная окружность" in x for x in failures)
    assert common_plan(CIRCUMCIRCLE + " AB = AC.", False) is None


def test_false_rhombus_or_missing_edge_cannot_get_verified():
    plan = common_plan(RHOMBUS, False)
    base = plan.to_dict()
    data = plan.to_dict()
    next(c for c in data["constructions"] if c["out"] == "C").update(
        op="free_point", args=[], value=None)
    wrong = FigurePlan.from_dict(data)
    coords = execute(wrong, free_values=np.array([0., 0., 1., 0., 0.8, 0.6]))
    assert any("стороны ABCD не равны" in x
               for x in semantic_failures(RHOMBUS, wrong, coords))

    data = plan.to_dict()
    data["draw"]["segments"].remove(["C", "D"])
    incomplete = FigurePlan.from_dict(data)
    coords = execute(plan, free_values=np.array([0., 0., 1., 0.]))
    assert any("не все четыре стороны" in x
               for x in semantic_failures(RHOMBUS, incomplete, coords))

    next(c for c in base["constructions"] if c["out"] == "D")["value"] = 70
    wrong_angle = FigurePlan.from_dict(base)
    coords = execute(wrong_angle, free_values=np.array([0., 0., 1., 0.]))
    assert any("угол A ромба" in x
               for x in semantic_failures(RHOMBUS, wrong_angle, coords))
