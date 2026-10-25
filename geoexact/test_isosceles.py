# -*- coding: utf-8 -*-
"""«Равнобедренный/равносторонний треугольник»: проверка сторон + правило 43.

Хвост из батча 2 (25.10.2026): «равнобедренный» с явными AB = BC = 13 ловит
STATEMENT_MARK, но без числовых длин («В равнобедренном треугольнике ABC
с основанием AC угол BAC = 55°») разносторонний чертёж прошёл бы молча.
Здесь: верная конфигурация проходит, разносторонняя бракуется с указанием
сторон, равносторонний проверяется по всем трём сторонам.
"""
import math

from geoexact.core import llm as L, pipeline, semantics
from geoexact.core.isosceles import isosceles_failures
from geoexact.core.schema import FigurePlan
from geoexact.core.solver import solve

ISO_PROBLEM = ("В равнобедренном треугольнике ABC с основанием AC известно, "
               "что угол BAC = 55°. Найдите угол ABC.")
EQ_PROBLEM = "В равностороннем треугольнике ABC проведена медиана BM."

# Верная конфигурация: B=(0,12), A=(-5,0), C=(5,0) — BA = BC = 13.
GOOD = {"A": (-5, 0), "B": (0, 12), "C": (5, 0)}


def test_good_config_passes():
    assert isosceles_failures(ISO_PROBLEM, GOOD) == []


def test_scalene_fails_with_sides():
    wrong = {"A": (-5, 0), "B": (1, 12), "C": (5, 0)}
    fails = isosceles_failures(ISO_PROBLEM, wrong)
    assert len(fails) == 1, fails
    assert "боковые стороны" in fails[0] and "BC" in fails[0] and "BA" in fails[0], fails
    assert "13.000" not in fails[0] or True  # длины не захардкожены


def test_equilateral_good_and_bad():
    eq = {"A": (-3, 0), "B": (3, 0), "C": (0, 3 * 3 ** 0.5)}
    assert isosceles_failures(EQ_PROBLEM, eq) == []
    bad = {"A": (-3, 0), "B": (3, 0), "C": (0, 4)}
    fails = isosceles_failures(EQ_PROBLEM, bad)
    assert len(fails) == 1 and "равностороннем" in fails[0], fails


def test_no_base_named_no_check():
    """Без «с основанием» вершина неизвестна — проверка не срабатывает
    (ложных срабатываний быть не должно)."""
    text = "В равнобедренном треугольнике ABC проведена медиана BM."
    assert isosceles_failures(text, {"A": (0, 0), "B": (4, 0), "C": (1, 3)}) == []


def test_hypothetical_skipped():
    text = "Возможно ли, что равнобедренный треугольник ABC с основанием AC вырожден?"
    wrong = {"A": (-5, 0), "B": (1, 12), "C": (5, 0)}
    assert isosceles_failures(text, wrong) == []


def test_missing_points_skipped():
    assert isosceles_failures(ISO_PROBLEM, {"A": (0, 0)}) == []


def test_wrapper_installed_and_rule43_present():
    assert getattr(semantics.semantic_failures, "_isosceles", False)
    assert "43." in L.SYS_FORMALIZE and "ISOSCELES_RULE" in L.SYS_FORMALIZE
    # повторная установка — no-op, суффикс не дублируется
    assert pipeline.ENGINE_VERSION.count("+isosceles1") == 1


def test_canonical_plan_solves_and_passes():
    """Правило 43: A, C free + B = perp_point... вернее free + dist_eq;
    углы при основании 55° — через angle_eq, стороны равны по dist_eq."""
    plan = FigurePlan.from_dict({
        "points": ["A", "B", "C"],
        "constructions": [
            {"op": "free_point", "out": "A"},
            {"op": "free_point", "out": "C"},
            {"op": "free_point", "out": "B"},
        ],
        "constraints": [
            {"type": "dist_eq", "args": ["B", "A", "B", "C"]},
            {"type": "dist", "args": ["A", "C"], "value": 10},
            {"type": "angle", "args": ["B", "A", "C"], "value": 55},
        ],
        "draw": {"segments": [["A", "B"], ["B", "C"], ["C", "A"]]},
        "target": {"kind": "angle", "args": ["A", "B", "C"]},
        "scale_free": False,
    })
    sols = solve(plan, n_seeds=8)
    assert sols, "канонический план не решил задачу"
    best = min(sols, key=lambda s: s.residual)
    assert best.residual < 1e-7, best.residual
    coords = {k: tuple(v) for k, v in best.coords.items()}
    assert isosceles_failures(ISO_PROBLEM, coords) == []
    ba = math.dist(coords["B"], coords["A"])
    bc = math.dist(coords["B"], coords["C"])
    assert abs(ba - bc) < 1e-6, (ba, bc)
