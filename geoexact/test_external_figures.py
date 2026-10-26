# -*- coding: utf-8 -*-
"""Внешние квадраты: правило 46, семантическая проверка стороны, канонический план.

Прод-ошибка (26.10.2026): «На сторонах AB и AC треугольника ABC во внешнюю
сторону построены квадраты ABDE и ACFG. Докажите, что BG = CE и BG
перпендикулярно CE.» — формализатор строил оба квадрата поворотами одного
знака; внешность обоих математически невозможна; система не решалась и
конвейер ушёл в приближённый фолбэк, хотя точное решение существует.
"""
import numpy as np
import pytest

import geoexact.core                       # обёртки устанавливаются при импорте
from geoexact.core import llm, semantics, pipeline
from geoexact.core.schema import FigurePlan
from geoexact.core.solver import solve
from geoexact.core.external_figures import (external_figure_failures,
                                             external_squares_plan)

PROD_TEXT = (
    "На сторонах AB и AC треугольника ABC во внешнюю сторону построены "
    "квадраты ABDE и ACFG. Докажите, что BG = CE и BG перпендикулярно CE.")


def test_rule_46_installed():
    assert "46." in llm.SYS_FORMALIZE
    assert "EXTERNAL_FIGURE_RULE" in llm.SYS_FORMALIZE


def test_engine_suffix():
    assert "+extFig2" in pipeline.ENGINE_VERSION


def _sq(A, B, out=1.0):
    """Координаты квадрата на AB: (adjA, adjB) — вершины при A и при B.
    out=+1: слева от AB, out=-1: справа."""
    A, B = np.asarray(A, float), np.asarray(B, float)
    d = (B - A) * out
    n = np.array([-d[1], d[0]])
    return A + n, B + n


def test_semantic_check_fires_on_internal_square():
    """Квадрат внутри + «внешним образом» — отказ."""
    A, B, C = (0.0, 0.0), (4.0, 0.0), (1.0, 3.0)
    # квадрат НАД AB (внутрь, C тоже сверху)
    E, D = _sq(A, B, out=+1)
    coords = {"A": A, "B": B, "C": C, "D": D, "E": E}
    fails = external_figure_failures(PROD_TEXT, coords)
    assert len(fails) >= 1
    assert "EXTERNAL_FIGURE" in fails[0]
    assert "ABDE" in fails[0]


def test_semantic_check_silent_on_external_square():
    A, B, C = (0.0, 0.0), (4.0, 0.0), (1.0, 3.0)
    E, D = _sq(A, B, out=-1)              # вниз — внешняя сторона
    F, G = _sq(A, C, out=+1)             # наружу от B
    coords = {"A": A, "B": B, "C": C, "D": D, "E": E, "F": F, "G": G}
    assert external_figure_failures(PROD_TEXT, coords) == []


def test_semantic_check_silent_without_external_word():
    """Без «внешним образом» ориентация не заявлена — проверка молчит."""
    A, B, C = (0.0, 0.0), (4.0, 0.0), (1.0, 3.0)
    E, D = _sq(A, B, out=+1)
    coords = {"A": A, "B": B, "C": C, "D": D, "E": E}
    text = "На сторонах AB и AC треугольника ABC построены квадраты ABDE и ACFG."
    assert external_figure_failures(text, coords) == []


def test_semantic_check_equilateral():
    A, B, C = (0.0, 0.0), (4.0, 0.0), (1.0, 3.0)
    E, D = _sq(A, B, out=+1)
    coords = {"A": A, "B": B, "C": C, "E": E}
    text = ("На стороне AB треугольника ABC во внешнюю сторону построен "
            "равносторонний треугольник ABE.")
    fails = external_figure_failures(text, coords)
    assert len(fails) == 1
    assert "ABE" in fails[0]


def _plan(trap: bool = False):
    """Канонический план двух внешних квадратов (циклические A,B,D,E и A,C,F,G).

    Правильные знаки: E=rotate(B,A,-90), D=rotate(A,B,+90),
    F=rotate(A,C,-90), G=rotate(C,A,+90) — вершина при ПЕРВОЙ букве
    стороны AB и вершина при ПЕРВОЙ букве стороны AC строятся
    противоположными поворотами. trap=True — обе одним знаком (ловушка
    прода: внешность обоих квадратов невозможна)."""
    f_sign = +90 if trap else -90
    g_sign = -90 if trap else +90
    return FigurePlan.from_dict({
        "points": ["A", "B", "C", "D", "E", "F", "G"],
        "constructions": [
            {"op": "free_point", "out": "A"}, {"op": "free_point", "out": "B"},
            {"op": "free_point", "out": "C"},
            {"op": "rotate", "args": ["B", "A"], "out": "E", "value": -90},
            {"op": "rotate", "args": ["A", "B"], "out": "D", "value": 90},
            {"op": "rotate", "args": ["A", "C"], "out": "F", "value": f_sign},
            {"op": "rotate", "args": ["C", "A"], "out": "G", "value": g_sign},
        ],
        "constraints": [
            {"type": "opposite_side", "args": ["D", "C", "A", "B"]},
            {"type": "opposite_side", "args": ["E", "C", "A", "B"]},
            {"type": "opposite_side", "args": ["F", "B", "A", "C"]},
            {"type": "opposite_side", "args": ["G", "B", "A", "C"]},
            {"type": "dist_eq", "args": ["B", "G", "C", "E"]},
            {"type": "perpendicular", "args": ["B", "G", "C", "E"]},
        ],
        "draw": {"segments": [["A", "B"], ["B", "C"], ["C", "A"],
                              ["B", "D"], ["D", "E"], ["E", "A"],
                              ["C", "F"], ["F", "G"], ["G", "A"],
                              ["B", "G"], ["C", "E"]]},
        "target": {"kind": "none", "args": []},
        "scale_free": True,
    })


def test_canonical_plan_solves_exactly():
    """Правильные (противоположные) знаки: точное решение, внешние квадраты,
    утверждения BG = CE и BG ⟂ CE выполнены."""
    sols = solve(_plan())
    good = [s for s in sols if s.ok]
    assert len(good) >= 10, [str(getattr(s, "reason", "")) for s in sols[:3]]
    c = good[0].coords
    P = {k: np.asarray(v, dtype=float) for k, v in c.items()}
    cr = lambda o, a, b: float(np.cross(P[a] - P[o], P[b] - P[o]))
    # оба квадрата с внешней стороны
    assert (cr("A", "B", "D") > 0) != (cr("A", "B", "C") > 0)
    assert (cr("A", "B", "E") > 0) != (cr("A", "B", "C") > 0)
    assert (cr("A", "C", "F") > 0) != (cr("A", "C", "B") > 0)
    assert (cr("A", "C", "G") > 0) != (cr("A", "C", "B") > 0)
    # утверждения
    bg = float(np.hypot(*(P["G"] - P["B"])))
    ce = float(np.hypot(*(P["E"] - P["C"])))
    assert abs(bg - ce) < 1e-9 * max(1.0, bg)
    assert abs(float(np.dot(P["G"] - P["B"], P["E"] - P["C"]))) < 1e-9
    # и семантическая проверка согласна
    assert external_figure_failures(PROD_TEXT, c) == []


def test_same_sign_trap_is_unsolvable():
    """Документация ловушки: одинаковые знаки + требования внешности —
    система не имеет решений (то, что словил прод)."""
    sols = solve(_plan(trap=True))
    good = [s for s in sols if s.ok]
    assert good == [], "одинаковые знаки не должны давать внешние квадраты"


def test_semantic_wrapper_carries_check():
    assert getattr(semantics.semantic_failures, "_external_figures", False)


def test_special_plan_wrapped_into_chain():
    """Обёртка в цепочке спец-планов: прод-фраза даёт канонический план."""
    assert getattr(semantics.trisected_parallel_plan, "_external_figures", False)
    plan = semantics.trisected_parallel_plan(PROD_TEXT, True)
    assert plan is not None
    assert {"dist_eq", "perpendicular"} <= {c.type for c in plan.constraints}


def test_special_plan_solves_prod_problem():
    """Прод-фраза целиком: план решается точно, квадраты внешние, теорема
    выполнена (BG = CE и BG ⟂ CE)."""
    plan = external_squares_plan(PROD_TEXT, True)
    assert plan is not None
    sols = solve(plan)
    good = [s for s in sols if s.ok]
    assert len(good) >= 5, [str(getattr(s, "reason", "")) for s in sols[:3]]
    P = {k: np.asarray(v, dtype=float) for k, v in good[0].coords.items()}
    cr = lambda o, a, b: float(np.cross(P[a] - P[o], P[b] - P[o]))
    assert (cr("A", "B", "D") > 0) != (cr("A", "B", "C") > 0)
    assert (cr("A", "B", "E") > 0) != (cr("A", "B", "C") > 0)
    assert (cr("A", "C", "F") > 0) != (cr("A", "C", "B") > 0)
    assert (cr("A", "C", "G") > 0) != (cr("A", "C", "B") > 0)
    bg = float(np.hypot(*(P["G"] - P["B"])))
    ce = float(np.hypot(*(P["E"] - P["C"])))
    assert abs(bg - ce) < 1e-9 * max(1.0, bg)
    assert abs(float(np.dot(P["G"] - P["B"], P["E"] - P["C"]))) < 1e-9


def test_special_plan_requires_external_word():
    text = ("На сторонах AB и AC треугольника ABC построены квадраты "
            "ABDE и ACFG. Докажите, что BG = CE.")
    assert external_squares_plan(text, True) is None


def test_special_plan_rejects_non_triangle_side():
    text = ("Во внешнюю сторону треугольника ABC на сторонах AB и AC "
            "построены квадраты ABDE и ACFG, а на отрезке DE — квадрат DEFG.")
    assert external_squares_plan(text, True) is None


def test_special_plan_single_square_rejected():
    """Одиночный квадрат — не разобранная конфигурация: отказ, путь LLM."""
    text = ("На стороне AB треугольника ABC во внешнюю сторону построен "
            "квадрат ABDE.")
    assert external_squares_plan(text, True) is None


def test_special_plan_rejects_extra_data():
    """Заданные длины/медианы/чужие точки — не берёмся: план их не учтёт."""
    with_len = ("На сторонах AB и AC треугольника ABC во внешнюю сторону "
                "построены квадраты ABDE и ACFG, AB = 3. Докажите, что BG = CE.")
    with_mid = ("На сторонах AB и AC треугольника ABC во внешнюю сторону "
                "построены квадраты ABDE и ACFG, M — середина BG. "
                "Докажите, что BG = CE.")
    assert external_squares_plan(with_len, True) is None
    assert external_squares_plan(with_mid, True) is None


def test_special_plan_rejects_false_claim():
    """Ложное для конфигурации «докажите» не должно подменять условие
    частным положением (AG = AE верно только при AB = AC) — отказ."""
    text = ("На сторонах AB и AC треугольника ABC во внешнюю сторону "
            "построены квадраты ABDE и ACFG. Докажите, что AG = AE.")
    assert external_squares_plan(text, True) is None


def test_theorem_holds_without_claim_constraints():
    """Теорема — следствие построения: без ограничений-утверждений BG = CE
    и BG ⟂ CE выполняются на свободном семействе (частное положение
    не подмешивается)."""
    text = ("На сторонах AB и AC треугольника ABC во внешнюю сторону "
            "построены квадраты ABDE и ACFG.")
    plan = external_squares_plan(text, True)
    assert plan is not None
    assert not any(c.type in ("dist_eq", "perpendicular") for c in plan.constraints)
    sols = solve(plan)
    good = [s for s in sols if s.ok]
    assert len(good) >= 5
    for s in good[:3]:
        P = {k: np.asarray(v, dtype=float) for k, v in s.coords.items()}
        bg = float(np.hypot(*(P["G"] - P["B"])))
        ce = float(np.hypot(*(P["E"] - P["C"])))
        assert abs(bg - ce) < 1e-9 * max(1.0, bg)
        assert abs(float(np.dot(P["G"] - P["B"], P["E"] - P["C"]))) < 1e-9


def test_special_plan_does_not_hijack_simson():
    """Фраза Симсона проходит прежнюю цепочку, а не новый план."""
    simson_text = (
        "Точка P лежит на описанной окружности треугольника ABC. X, Y и Z — "
        "основания перпендикуляров, опущенных из точки P на прямые AB, BC "
        "и CA соответственно. Докажите, что точки X, Y и Z лежат на одной прямой.")
    plan = semantics.trisected_parallel_plan(simson_text, True)
    assert plan is not None
    assert "P" in plan.points and "O" in plan.points
