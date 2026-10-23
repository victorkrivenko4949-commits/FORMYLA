"""Regression: two points on triangle sides fixed by angles at opposite vertices."""
import math

from geoexact.core.gates import rank_solutions
from geoexact.core.pipeline import generate
from geoexact.core.repair import angle_side_variants
from geoexact.core.render import render_svg
from geoexact.core.schema import FigurePlan, validate_plan
from geoexact.core.solver import solve


def make_plan():
    return FigurePlan.from_dict({
        "points": ["A", "B", "C", "R", "D", "S", "E"],
        "constructions": [
            *({"op": "free_point", "out": name} for name in "ABC"),
            {"op": "angle_ray", "out": "R", "args": ["B", "C"], "value": 60},
            {"op": "line_intersect", "out": "D", "args": ["A", "C", "B", "R"]},
            {"op": "angle_ray", "out": "S", "args": ["C", "B"], "value": -50},
            {"op": "line_intersect", "out": "E", "args": ["A", "B", "C", "S"]},
        ],
        "constraints": [
            {"type": "dist_eq", "args": ["A", "B", "A", "C"]},
            {"type": "angle", "args": ["B", "A", "C"], "value": 20},
            {"type": "on_segment", "args": ["D", "A", "C"]},
            {"type": "on_segment", "args": ["E", "A", "B"]},
            {"type": "angle", "args": ["D", "B", "C"], "value": 60},
            {"type": "angle", "args": ["E", "C", "B"], "value": 50},
        ],
        "draw": {
            "segments": [["A", "B"], ["B", "C"], ["C", "A"],
                         ["B", "D"], ["C", "E"], ["E", "D"]],
            "angle_marks": [
                {"pts": ["B", "A", "C"], "text": "20°"},
                {"pts": ["D", "B", "C"], "text": "60°"},
                {"pts": ["E", "C", "B"], "text": "50°"},
            ],
            "hide_labels": ["R", "S"],
        },
        "target": {"kind": "angle", "args": ["E", "D", "B"]},
        "scale_free": True,
    })


def test_angle_side_intersections_produce_checked_30_degree_drawing():
    plan = make_plan()
    validate_plan(plan)
    ranked = rank_solutions(plan, solve(plan, n_seeds=8), strict_readability=False)
    assert ranked
    sol, gate = ranked[0]
    assert sol.residual < 1e-7
    assert math.isclose(gate.measured, 30.0, abs_tol=1e-7)
    assert not any(" S " in warning for warning in gate.warnings)
    svg = render_svg(plan, sol, gate=gate)
    for name in ("R", "S"):
        assert f'data-point="{name}"' not in svg
    for name in ("A", "B", "C", "D", "E"):
        assert f'data-point="{name}"' in svg


def make_free_plan():
    plan = make_plan()
    plan.points.remove("R")
    plan.points.remove("S")
    plan.constructions = [c for c in plan.constructions
                          if c.out not in ("R", "S")]
    from geoexact.core.schema import Construction
    plan.constructions = [
        Construction(op="free_point", out=c.out)
        if c.out in ("D", "E") else c
        for c in plan.constructions
    ]
    plan.draw.hide_labels.clear()
    validate_plan(plan)
    return plan


def test_free_side_points_are_replaced_by_checked_intersections():
    plan = make_free_plan()

    variants = angle_side_variants(plan)
    assert len(variants) == 4
    matching = []
    for candidate in variants:
        solutions = solve(candidate, n_seeds=4)
        ranked = rank_solutions(candidate, solutions, strict_readability=False)
        if ranked:
            matching.append(ranked[0][1].measured)
    assert matching
    assert all(math.isclose(value, 30.0, abs_tol=1e-6) for value in matching)


def test_pipeline_recovers_from_free_side_points_without_llm_retry(monkeypatch):
    from geoexact.core import llm
    monkeypatch.setattr(llm, "classify",
                        lambda sess, text, budget: {"ok": True, "class": "L", "space": "plane"})
    monkeypatch.setattr(llm, "formalize",
                        lambda sess, text, cls, aux, budget, feedback, prev_code:
                        (make_free_plan(), []))
    result = generate(
        "В треугольнике ABC AB=AC, угол A=20°, D на AC, DBC=60°, "
        "E на AB, ECB=50°. Найдите EDB.",
        sess=object(), use_cache=False, n_seeds=4, max_retries=0,
    )
    assert result.ok, (result.reason, result.detail)
    assert math.isclose(result.measured, 30.0, abs_tol=1e-6)
    assert result.retries == 0
