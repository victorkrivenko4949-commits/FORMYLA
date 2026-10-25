# -*- coding: utf-8 -*-
"""«Трапеция ABCD»: проверка оснований и боковых + правило 42 формализатора.

Прод-сценарий (баг-хант 25.10.2026): «В равнобедренной трапеции ABCD с
основаниями BC и AD известно, что BC = 6, AD = 16, боковая сторона
AB = CD = 13. Диагонали AC и BD пересекаются в точке O. Найдите BO».
Формализатор собрал нерешаемую систему — фолбэк в схематичный чертёж с
пропорциями BC:AD = 1:2 вместо 3:8. Здесь: верная конфигурация проходит,
непараллельные основания и неравные боковые бракуются с указанием величины,
канонический план (правило 42: free_point + parallel + dist) решается
и проходит проверку.
"""
import math

from geoexact.core import llm as L, pipeline, semantics
from geoexact.core.schema import FigurePlan
from geoexact.core.solver import solve
from geoexact.core.trapezoid import trapezoid_failures

PROBLEM = ("В равнобедренной трапеции ABCD с основаниями BC и AD известно, "
           "что BC = 6, AD = 16, боковая сторона AB = CD = 13. Диагонали "
           "AC и BD пересекаются в точке O. Найдите BO.")

# Верная конфигурация: A=(-8,0), D=(8,0), B=(-3,12), C=(3,12);
# O = (0, 96/11), BO = (3/11)·√265.
GOOD = {"A": (-8, 0), "B": (-3, 12), "C": (3, 12), "D": (8, 0),
        "O": (0, 96 / 11)}


def test_good_config_passes():
    assert trapezoid_failures(PROBLEM, GOOD) == []


def test_nonparallel_bases_fail():
    """Схематичный фолбэк с прод-чертежа: BC:AD = 1:2, основания параллельны,
    но проверим именно непараллельность: сдвинем D."""
    wrong = dict(GOOD, D=(8, 2))
    fails = trapezoid_failures(PROBLEM, wrong)
    par = [f for f in fails if "не параллельны" in f]
    assert len(par) == 1, fails          # сдвиг D ломает и параллельность, и боковые
    assert "BC и AD" in par[0], fails


def test_unequal_legs_fail():
    wrong = dict(GOOD, B=(-3, 12), C=(3, 14))
    fails = trapezoid_failures(PROBLEM, wrong)
    assert any("не равны" in f for f in fails), fails


def test_default_bases_convention():
    """«трапеция ABCD» без явных оснований: проверяется AD ∥ BC."""
    text = "В трапеции ABCD диагонали пересекаются в точке O."
    assert trapezoid_failures(text, GOOD) == []
    wrong = dict(GOOD, D=(8, 2))
    fails = trapezoid_failures(text, wrong)
    assert len(fails) == 1 and "AD" in fails[0] and "BC" in fails[0], fails


def test_one_named_base_completes_pair():
    """«с основанием BC» — второе основание выводится из вершин (AD)."""
    text = "В трапеции ABCD с основанием BC = 6 найдите углы."
    assert trapezoid_failures(text, GOOD) == []
    fails = trapezoid_failures(text, dict(GOOD, D=(8, 2)))
    assert len(fails) == 1, fails


def test_hypothetical_and_no_trapezoid_skipped():
    text = "Возможно ли, что трапеция ABCD вырождается в отрезок?"
    assert trapezoid_failures(text, dict(GOOD, D=(8, 2))) == []
    assert trapezoid_failures("В треугольнике ABC основание BC равно 6.",
                              dict(GOOD, D=(8, 2))) == []


def test_missing_points_skipped():
    assert trapezoid_failures(PROBLEM, {"A": (0, 0)}) == []


def test_wrapper_installed_and_rule42_present():
    assert getattr(semantics.semantic_failures, "_trapezoid", False)
    assert "42." in L.SYS_FORMALIZE and "TRAPEZOID_RULE" in L.SYS_FORMALIZE
    # повторная установка — no-op, суффикс не дублируется
    assert pipeline.ENGINE_VERSION.count("+trapezoid1") == 1


def test_canonical_plan_solves_and_passes():
    """Правило 42: свободные точки + parallel + dist; BO:OD = BC:AD = 3:8."""
    plan = FigurePlan.from_dict({
        "points": ["A", "B", "C", "D", "O"],
        "constructions": [
            {"op": "free_point", "out": "A"},
            {"op": "free_point", "out": "B"},
            {"op": "free_point", "out": "C"},
            {"op": "free_point", "out": "D"},
            {"op": "line_intersect", "out": "O", "args": ["A", "C", "B", "D"]},
        ],
        "constraints": [
            {"type": "dist", "args": ["A", "D"], "value": 16},
            {"type": "dist", "args": ["B", "C"], "value": 6},
            {"type": "dist", "args": ["A", "B"], "value": 13},
            {"type": "dist", "args": ["C", "D"], "value": 13},
            {"type": "parallel", "args": ["A", "D", "B", "C"]},
        ],
        "draw": {"segments": [["A", "B"], ["B", "C"], ["C", "D"], ["D", "A"]]},
        "target": {"kind": "dist", "args": ["B", "O"]},
        "scale_free": False,
    })
    sols = solve(plan, n_seeds=8)
    assert sols, "канонический план не решил задачу"
    best = min(sols, key=lambda s: s.residual)
    assert best.residual < 1e-7, best.residual
    coords = {k: tuple(v) for k, v in best.coords.items()}
    assert trapezoid_failures(PROBLEM, coords) == []
    # жёсткое следствие: BO/OD = BC/AD = 6/16 = 0.375
    bo = math.dist(coords["B"], coords["O"])
    od = math.dist(coords["O"], coords["D"])
    assert abs(bo / od - 0.375) < 1e-6, (bo, od)
