import math
import types

import numpy as np
import pytest

from geoexact.core import general_position as G


class _Sol:
    def __init__(self, coords, ok=True):
        self.coords = {k: np.asarray(v, float) for k, v in coords.items()}
        self.ok = ok
        self.residual = 0.0


class _GR:
    def __init__(self, score):
        self.ok, self.score, self.failures = True, score, []


PLAN = types.SimpleNamespace(points=["A", "B", "C"])

EQUILATERAL = {"A": (0, 0), "B": (10, 0), "C": (5, 5 * math.sqrt(3))}
RIGHT = {"A": (0, 0), "B": (8, 0), "C": (0, 6)}
ISOSCELES = {"A": (0, 0), "B": (10, 0), "C": (5, 7)}
GENERIC = {"A": (0, 0), "B": (10, 0), "C": (3.1, 6.3)}
OBTUSE = {"A": (0, 0), "B": (-4, 6 * math.sqrt(3)), "C": (10, 0)}   # задача про медиану AM = 6


def test_generic_triangle_beats_special_ones():
    g = G.score(PLAN, GENERIC)
    assert g > G.score(PLAN, EQUILATERAL)
    assert g > G.score(PLAN, RIGHT)
    assert g > G.score(PLAN, ISOSCELES)
    assert g >= 0.9


def test_obtuse_median_configuration_is_fine():
    assert G.score(PLAN, OBTUSE) > 0.9


def test_close_points_and_near_line_are_penalised():
    plan = types.SimpleNamespace(points=["A", "B", "C", "D"])
    base = dict(GENERIC, D=(6.0, 2.5))
    close = dict(GENERIC, D=(3.2, 6.35))          # D слиплась с C
    near_line = dict(GENERIC, D=(5.0, 0.15))      # D почти на AB, но не на ней
    assert G.score(plan, base) > G.score(plan, close)
    assert G.score(plan, base) > G.score(plan, near_line)


def test_exact_incidence_is_not_penalised():
    plan = types.SimpleNamespace(points=["A", "B", "C", "M"])
    with_mid = dict(GENERIC, M=(6.55, 3.15))       # середина BC — лежит на BC точно
    assert G.score(plan, with_mid) == pytest.approx(G.score(PLAN, GENERIC), abs=0.05)


def test_sliver_aspect_is_penalised():
    sliver = {"A": (0, 0), "B": (10, 0), "C": (5.3, 0.9)}
    assert G.score(PLAN, sliver) < G.score(PLAN, GENERIC)


def _fake_modules(solutions, scores):
    solver = types.ModuleType("solver")
    seen = {}

    def solve(plan, n_seeds=24, seed=0):
        """orig"""
        seen["n_seeds"] = n_seeds
        return list(solutions)
    solver.solve = solve
    gates = types.ModuleType("gates")

    def rank_solutions(plan, sols, *, strict_readability=True):
        return [(s, _GR(scores[i])) for i, s in enumerate(sols)]
    gates.rank_solutions = rank_solutions
    return solver, gates, seen


def test_install_puts_generic_solution_first_and_asks_for_more_seeds():
    sols = [_Sol(EQUILATERAL), _Sol(RIGHT), _Sol(GENERIC), _Sol(ISOSCELES, ok=False)]
    solver, gates, seen = _fake_modules(sols, [0.9, 0.9, 0.9])
    assert G.install(solver, gates) is True and G.install(solver, gates) is False
    assert solver.solve.__doc__ == "orig"
    out = solver.solve(PLAN, n_seeds=8)
    assert seen["n_seeds"] == G.GP_SEEDS
    assert out[0].coords["C"][0] == pytest.approx(3.1)      # разносторонний первым
    assert out[-1].ok is False                                # не-ok остаётся хвостом
    assert len(out) == 4


def test_rank_mixes_readability_with_general_position():
    sols = [_Sol(EQUILATERAL), _Sol(GENERIC)]
    solver, gates, _ = _fake_modules(sols, [0.95, 0.80])     # наглядность чуть за равносторонний
    G.install(solver, gates)
    ranked = gates.rank_solutions(PLAN, sols, strict_readability=False)
    assert ranked[0][0].coords["C"][0] == pytest.approx(3.1)
    assert [type(gr).__name__ for _, gr in ranked] == ["_GR", "_GR"]


def test_required_right_angle_same_in_both_only_spacing_decides():
    # оба кандидата прямоугольные при A (условие требует), D лежит на AB точно;
    # разница только в том, что в tight точка D слиплась с A
    plan = types.SimpleNamespace(points=["A", "B", "C", "D"])
    tight = {"A": (0, 0), "B": (8, 0), "C": (0, 6), "D": (0.2, 0)}
    spread = {"A": (0, 0), "B": (8, 0), "C": (0, 6), "D": (3.7, 0)}
    assert G.score(plan, spread) > G.score(plan, tight)
    assert G.score(plan, tight) < 0.5 < G.score(plan, spread)


def test_disabled_by_env(monkeypatch):
    monkeypatch.setattr(G, "ENABLED", False)
    solver, gates, _ = _fake_modules([], [])
    assert G.install(solver, gates) is False
    assert not getattr(solver.solve, "_general_position", False)


def test_core_package_installs_general_position():
    from geoexact.core import solver, gates
    assert getattr(solver.solve, "_general_position", False) is True
    assert getattr(gates.rank_solutions, "_general_position", False) is True
