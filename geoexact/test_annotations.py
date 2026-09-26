"""Verified annotations, including the exterior angle-bisectors of an excenter."""
from types import SimpleNamespace

import numpy as np
import pytest

from geoexact.core.annotations import enrich_annotations
from geoexact.core.completion import complete_intersection_support
from geoexact.core.constructions import execute
from geoexact.core.gates import gate_correctness
from geoexact.core.pipeline import generate
from geoexact.core.render import render_svg
from geoexact.core.schema import FigurePlan, PlanError, validate_plan
from geoexact.core.semantics import _EXCENTER_THEOREM, theorem_plan


def triangle_plan(*, isosceles=True):
    return FigurePlan.from_dict({
        "points": ["A", "B", "C"],
        "constructions": [{"op": "free_point", "out": name} for name in "ABC"],
        "constraints": ([
            {"type": "dist_eq", "args": ["A", "B", "A", "C"]},
            {"type": "angle_eq", "args": ["A", "B", "C", "B", "C", "A"]},
        ] if isosceles else []),
        "draw": {"segments": [["A", "B"], ["B", "C"], ["C", "A"]]},
        "target": {"kind": "none", "args": []},
        "scale_free": True,
    })


def solved(plan, *flat):
    return SimpleNamespace(coords=execute(plan, free_values=np.asarray(flat, dtype=float)))


def test_equal_constraints_add_visible_marks_only_when_verified():
    plan = triangle_plan()
    sol = solved(plan, 0, 1, -1, 0, 1, 0)
    enriched = enrich_annotations(plan, sol, with_aux=False)
    assert len(enriched.draw.equal_marks) == 2
    assert len(enriched.draw.angle_marks) == 2
    assert not plan.draw.equal_marks  # never mutate caller's plan
    assert validate_plan(enriched) is not None
    assert gate_correctness(enriched, sol).ok
    svg = render_svg(enriched, sol, show_aux=False)
    assert svg.count('class="tick"') == 2
    assert svg.count('class="arc"') >= 2
    wrong = solved(plan, 0, 1, -1, 0, 1.4, 0)
    assert not enrich_annotations(plan, wrong, with_aux=False).draw.equal_marks
    assert not enrich_annotations(plan, wrong, with_aux=False).draw.angle_marks
    assert not enrich_annotations(triangle_plan(isosceles=False), sol,
                                  with_aux=False).draw.equal_marks


@pytest.mark.parametrize("aux", [False, True])
def test_excenter_shows_short_extensions_and_true_exterior_halves(aux):
    problem = "Условие. " + _EXCENTER_THEOREM
    result = generate(problem, with_aux=aux, sess=object(), use_cache=False)
    assert result.ok, (result.reason, result.detail)
    draw = result.plan["draw"]
    assert {tuple(m["pts"]) for m in draw["equal_marks"]} == {
        ("W", p) for p in ("B", "C", "I", "I_A")
    }
    assert result.svg.count('class="tick"') == 4
    assert {tuple(s) for s in draw["aux_extensions"]} == (
        {("A", "B"), ("A", "C")} if aux else set()
    )
    assert result.svg.count('data-kind="extension"') == (2 if aux else 0)
    for vertex in ("B", "C"):
        marks = [m for m in draw["angle_marks"] if m["pts"][1] == vertex]
        assert len(marks) == (2 if aux else 0)
        if aux:
            assert marks[0]["count"] == marks[1]["count"]
            assert any(m.get("reverse_first") for m in marks)
            assert all(m["layer"] == "aux" for m in marks)
            assert ["I_A", vertex] in draw["aux_segments"] or [vertex, "I_A"] in draw["aux_segments"]
    sol = solved(theorem_plan(problem, aux), 0, 0, 1, 0, 0.4, 0.9)
    amended, _ = complete_intersection_support(
        enrich_annotations(theorem_plan(problem, aux), sol, with_aux=aux), sol)
    assert gate_correctness(amended, sol).ok
    assert 'data-kind="extension"' not in render_svg(amended, sol, show_aux=False)


def test_incenter_bisectors_are_auxiliary_and_hide_with_aux_layer():
    from geoexact.core.semantics import common_plan
    text = "Постройте вписанную окружность треугольника ABC."
    plan = common_plan(text, True)
    sol = solved(plan, 0, 0, 1, 0, 0.45, 0.9)
    decorated = enrich_annotations(plan, sol, with_aux=True)
    assert len(decorated.draw.angle_marks) == 6
    assert all(m["layer"] == "aux" for m in decorated.draw.angle_marks)
    assert gate_correctness(decorated, sol).ok
    full = render_svg(decorated, sol, show_aux=True)
    base = render_svg(decorated, sol, show_aux=False)
    assert full.count('class="arc"') >= 6
    assert base.count('class="arc"') == 0


def test_reversed_exterior_mark_is_checked_against_exterior_value():
    plan = triangle_plan(isosceles=False)
    plan.draw.angle_marks = [
        {"pts": ["A", "B", "C"], "text": "135°", "reverse_first": True}
    ]
    sol = solved(plan, 0, 1, -1, 0, 1, 0)
    assert gate_correctness(plan, sol).ok  # interior angle ABC is 45°
    plan.draw.angle_marks[0]["text"] = "45°"
    assert not gate_correctness(plan, sol).ok
    plan.draw.angle_marks[0]["reverse_first"] = "yes"
    with pytest.raises(PlanError, match="reverse_first"):
        validate_plan(plan)


def test_model_plan_gets_annotations_in_pipeline(monkeypatch):
    from geoexact.core import llm
    monkeypatch.setattr(llm, "classify",
                        lambda *_: {"ok": True, "class": "M", "space": "plane"})
    monkeypatch.setattr(llm, "formalize",
                        lambda *_, **__: (triangle_plan(), []))
    result = generate("Постройте равнобедренный треугольник ABC: AB=AC.",
                      sess=object(), use_cache=False, max_retries=0)
    assert result.ok, (result.reason, result.detail)
    assert len(result.plan["draw"]["equal_marks"]) == 2


@pytest.mark.parametrize("figure,groups", [
    ("ромб", [4]), ("квадрат", [4]),
    ("прямоугольник", [2, 2]), ("параллелограмм", [2, 2]),
])
def test_named_quadrilateral_equalities_are_verified(figure, groups):
    plan = triangle_plan(isosceles=False)
    plan.points.append("D")
    plan.constructions.append(type(plan.constructions[0])(op="free_point", out="D"))
    plan.draw.segments = [["A", "B"], ["B", "C"], ["C", "D"], ["D", "A"]]
    sol = solved(plan, 0, 0, 1, 0, 1.5, 0.8660254, 0.5, 0.8660254)
    marked = enrich_annotations(plan, sol, with_aux=False,
                                problem_text=f"Постройте {figure} ABCD.")
    if figure in ("ромб", "квадрат"):
        # 60° rhombus is not a square, but the side equality itself is true;
        # figure semantics are checked separately by the pipeline.
        pass
    assert sorted([sum(m["count"] == c for m in marked.draw.equal_marks)
                   for c in {m["count"] for m in marked.draw.equal_marks}]) == sorted(groups)
    assert gate_correctness(marked, sol).ok


def test_analytic_rhombus_and_circumcircle_get_ticks():
    rhombus = generate("Постройте ромб ABCD, в котором угол A равен 60°.",
                       with_aux=False, sess=object(), use_cache=False)
    assert rhombus.ok
    assert len(rhombus.plan["draw"]["equal_marks"]) == 4
    assert rhombus.svg.count('class="tick"') == 4
    circle = generate("Постройте описанную окружность треугольника ABC.",
                      with_aux=True, sess=object(), use_cache=False)
    assert circle.ok
    radii = circle.plan["draw"]["equal_marks"]
    assert {tuple(m["pts"]) for m in radii} == {("O", p) for p in "ABC"}
    assert all(m["layer"] == "aux" for m in radii)
    assert 'class="tick" data-layer="aux"' not in circle.svg_base


@pytest.mark.parametrize("opposite", [0, 1, 2])
@pytest.mark.parametrize("c", [(0.3, 0.9), (1.25, -0.65), (-0.2, 0.8)])
def test_exterior_bisectors_support_each_excenter_and_orientation(opposite, c):
    plan = FigurePlan.from_dict({
        "points": ["A", "B", "C", "X"],
        "constructions": [
            *({"op": "free_point", "out": name} for name in "ABC"),
            {"op": "excenter", "out": "X", "args": ["A", "B", "C"],
             "value": opposite},
        ],
        "draw": {"segments": [["A", "B"], ["B", "C"], ["C", "A"]]},
        "scale_free": True,
    })
    sol = solved(plan, 0, 0, 1, 0, *c)
    enriched = enrich_annotations(plan, sol, with_aux=True)
    assert len(enriched.draw.aux_extensions) == 2
    assert len(enriched.draw.angle_marks) == 4
    assert sum(bool(m.get("reverse_first")) for m in enriched.draw.angle_marks) == 2
    assert gate_correctness(enriched, sol).ok
    finished, _ = complete_intersection_support(enriched, sol)
    svg = render_svg(finished, sol, show_aux=True)
    assert svg.count('data-kind="extension"') == 2
