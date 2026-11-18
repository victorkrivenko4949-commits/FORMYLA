"""Прямой угол: один квадратик на вершину, а не по обе стороны линии."""
import pytest

from geoexact.core.schema import FigurePlan
from geoexact.core.solver import solve
from geoexact.core.render import render_svg


def height_plan(right):
    """Треугольник с высотой BH к основанию AC; H — foot."""
    return FigurePlan.from_dict({
        "points": list("ABCH"),
        "constructions": [
            {"op": "free_point", "out": "A"},
            {"op": "free_point", "out": "B"},
            {"op": "free_point", "out": "C"},
            {"op": "foot", "out": "H", "args": ["B", "A", "C"]}],
        "constraints": [
            {"type": "dist", "args": ["A", "H"], "value": 3},
            {"type": "dist", "args": ["H", "C"], "value": 3},
            {"type": "dist", "args": ["B", "H"], "value": 4}],
        "draw": {"segments": [["A", "B"], ["B", "C"], ["A", "C"], ["B", "H"]],
                 "right_angles": right},
        "scale_free": True})


def solved_svg(plan):
    sol = next(s for s in solve(plan, n_seeds=6) if s.ok)
    return render_svg(plan, sol)


def right_triangle_plan(right):
    """Прямоугольный треугольник (угол C) с высотой CH к гипотенузе AB."""
    return FigurePlan.from_dict({
        "points": list("ABCH"),
        "constructions": [
            {"op": "free_point", "out": "A"},
            {"op": "free_point", "out": "B"},
            {"op": "free_point", "out": "C"},
            {"op": "foot", "out": "H", "args": ["C", "A", "B"]}],
        "constraints": [
            {"type": "perpendicular", "args": ["A", "C", "B", "C"]},
            {"type": "dist", "args": ["A", "C"], "value": 3},
            {"type": "dist", "args": ["B", "C"], "value": 4}],
        "draw": {"segments": [["A", "B"], ["B", "C"], ["A", "C"], ["C", "H"]],
                 "right_angles": right},
        "scale_free": True})


def test_one_square_at_a_vertex_declared_twice():
    # модель отметила оба прямых угла при основании высоты — квадратик один
    svg = solved_svg(height_plan([["A", "H", "B"], ["B", "H", "C"]]))
    assert svg.count('class="rt"') == 1


def test_same_angle_twice_is_still_one_square():
    svg = solved_svg(height_plan([["A", "H", "B"], ["B", "H", "A"]]))
    assert svg.count('class="rt"') == 1


def test_two_vertices_keep_two_squares():
    # прямой угол при C и при H — разные вершины, квадратика два
    svg = solved_svg(right_triangle_plan([["A", "C", "B"], ["C", "H", "A"]]))
    assert svg.count('class="rt"') == 2


def test_two_marks_at_c_reduce_to_one():
    # ∠ACB и ∠BCA — один и тот же угол при C: квадратик один
    svg = solved_svg(right_triangle_plan([["A", "C", "B"], ["B", "C", "A"]]))
    assert svg.count('class="rt"') == 1


def test_rectangle_keeps_all_four_squares():
    plan = FigurePlan.from_dict({
        "points": list("ABCD"),
        "constructions": [{"op": "free_point", "out": c} for c in "ABC"] + [
            {"op": "translate", "out": "D", "args": ["C", "B", "A"]}],
        "constraints": [
            {"type": "perpendicular", "args": ["B", "A", "C", "B"]},
            {"type": "dist", "args": ["A", "B"], "value": 5},
            {"type": "dist", "args": ["B", "C"], "value": 3}],
        "draw": {"segments": [["A", "B"], ["B", "C"], ["C", "D"], ["D", "A"]],
                 "right_angles": [["A", "B", "C"], ["B", "C", "D"],
                                  ["C", "D", "A"], ["D", "A", "B"]]},
        "scale_free": True})
    assert solved_svg(plan).count('class="rt"') == 4
