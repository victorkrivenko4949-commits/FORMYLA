# -*- coding: utf-8 -*-
"""«Биссектриса угла XYZ ... в точке T»: проверка по координатам + канонический план.

Прод-сценарий (задача 1, живая генерация 24.10.2026): «В параллелограмме ABCD
биссектриса угла BAD пересекает сторону BC в точке E и диагональ BD в точке F.
Известно, что AB = 6, AD = 10, угол BAD равен 60°. Найдите EF». Формализатор
потерял биссектрису: луч AE под ~19° к AB вместо 30°, BE = 3 вместо 6,
EF = 1.83 вместо ~3.90, гейты молчали. Здесь: верная конфигурация проходит
проверку, прод-координаты бракуются с указанием точки и угла, канонический
план (правило 40: bisector_point + line_intersect) решается и проходит.
"""
import numpy as np

from geoexact.core import llm as L, pipeline, semantics
from geoexact.core.bisector_angle import bisector_failures
from geoexact.core.schema import FigurePlan
from geoexact.core.solver import solve

PROBLEM = ("В параллелограмме ABCD биссектриса угла BAD пересекает сторону BC "
           "в точке E и диагональ BD в точке F. Известно, что AB = 6, AD = 10, "
           "угол BAD равен 60°. Найдите EF.")

# Верная конфигурация: A=(0,0), B=(6,0), D=(5, 5√3), C=B+D-A=(11, 5√3).
# Биссектриса (30°) встречает BC в E=(9, 3√3) (BE=AB=6) и BD в F=(45/8, 15√3/8).
R3 = 3 ** 0.5
GOOD = {"A": (0, 0), "B": (6, 0), "D": (5, 5 * R3), "C": (11, 5 * R3),
        "E": (9, 3 * R3), "F": (45 / 8, 15 * R3 / 8)}

# Прод-координаты (SVG, нормировано к AB=6): E на BC в 3 единицах от B —
# луч AE под ~19.1° к AB, делит угол 60° как 19.1°/40.9°. E и F на своих
# прямых (координаты точные, без округления — иначе проверка прямой ложно срабатывает).
BAD = {"A": (0, 0), "B": (6, 0), "D": (5, 5 * R3), "C": (11, 5 * R3),
       "E": (7.5, 1.5 * R3), "F": (75 / 13, 15 * R3 / 13)}


def test_good_config_passes():
    assert bisector_failures(PROBLEM, GOOD) == []


def test_point_on_bisector_but_wrong_line_fails():
    """Прод-ошибка №2 (деплой d696e7c9): биссектриса верная (30°/30°), но E
    построена на диагонали BD вместо стороны BC и совпала с F (E = F)."""
    wrong_line = dict(GOOD, E=GOOD["F"])          # E стерта с F на диагонали BD
    fails = bisector_failures(PROBLEM, wrong_line)
    assert len(fails) == 1, fails
    assert "точка E не лежит на прямой BC" in fails[0], fails


def test_prod_bad_config_names_point_and_angle():
    fails = bisector_failures(PROBLEM, BAD)
    assert len(fails) == 2, fails
    e_fail = [f for f in fails if "точка E не лежит на биссектрисе угла BAD" in f]
    f_fail = [f for f in fails if "точка F не лежит на биссектрисе угла BAD" in f]
    assert e_fail and f_fail, fails
    assert "19." in e_fail[0] and "40." in e_fail[0], fails


def test_external_bisector_is_skipped():
    text = ("В параллелограмме ABCD внешняя биссектриса угла BAD пересекает "
            "сторону BC в точке E.")
    assert bisector_failures(text, BAD) == []


def test_no_intersection_point_no_check():
    text = "В параллелограмме ABCD проведена биссектриса угла BAD."
    assert bisector_failures(text, BAD) == []


def test_hypothetical_sentence_is_skipped():
    text = ("Возможно ли, что биссектриса угла BAD пересекает сторону BC "
            "в точке E? Ответ обоснуйте.")
    assert bisector_failures(text, BAD) == []


def test_unicode_subscripts_in_text():
    text = ("В треугольнике ABC биссектриса угла BAC пересекает сторону BC "
            "в точке A₁. Известно, что AB = AC.")
    # A₁ нет в coords -> проверки нет (отсутствие точки ловит семантика имён);
    # с координатой — проверяется: верная середина BC проходит.
    mid = {"A": (0, 4), "B": (-3, 0), "C": (3, 0), "A_1": (0, 0)}
    assert bisector_failures(text, mid) == []
    wrong = {"A": (0, 4), "B": (-3, 0), "C": (3, 0), "A_1": (2, 0)}
    assert bisector_failures(text, wrong) != []


def test_wrapper_installed_and_rule40_present():
    assert getattr(semantics.semantic_failures, "_bisector_angle", False)
    assert "40." in L.SYS_FORMALIZE and "BISECTOR_ANGLE_RULE" in L.SYS_FORMALIZE
    # повторная установка — no-op, суффикс не дублируется
    assert pipeline.ENGINE_VERSION.count("+bisectorAngle2") == 1


def test_canonical_plan_solves_and_passes():
    """Правило 40: F = bisector_point(A,B,D), E = line_intersect(B,C,A,F)."""
    plan = FigurePlan.from_dict({
        "points": ["A", "B", "D", "C", "F", "E"],
        "constructions": [
            {"op": "free_point", "out": "A"},
            {"op": "free_point", "out": "B"},
            {"op": "free_point", "out": "D"},
            {"op": "translate", "out": "C", "args": ["B", "D", "A"]},   # B+D-A
            {"op": "bisector_point", "out": "F", "args": ["A", "B", "D"]},
            {"op": "line_intersect", "out": "E", "args": ["B", "C", "A", "F"]},
        ],
        "constraints": [
            {"type": "dist", "args": ["A", "B"], "value": 6},
            {"type": "dist", "args": ["A", "D"], "value": 10},
            {"type": "angle", "args": ["B", "A", "D"], "value": 60},
        ],
        "draw": {"segments": [["A", "B"], ["B", "C"], ["C", "D"], ["D", "A"],
                              ["B", "D"], ["A", "E"]]},
        "target": {"kind": "none", "args": []},
        "scale_free": False,
    })
    sols = solve(plan, n_seeds=8)
    assert sols, "канонический план не решил задачу"
    best = sols[0]
    assert best.residual < 1e-7, best.residual
    coords = {k: tuple(v) for k, v in best.coords.items()}
    assert bisector_failures(PROBLEM, coords) == []
    # жёсткие следствия правильной конфигурации: BE = AB = 6,
    # E между B и C, F между B и D.
    be = np.linalg.norm(np.array(coords["E"]) - np.array(coords["B"]))
    assert abs(be - 6) < 1e-6, be
