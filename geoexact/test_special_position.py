# -*- coding: utf-8 -*-
"""Частное положение: незаявленные равенства сторон четырёхугольника.

Прод-сценарий (26.10.2026): «В выпуклом четырёхугольнике ABCD стороны AB и
BC равны, K — точка пересечения диагоналей... Докажите, что ∠AKX = ∠CKY» —
формализатор добавил лишнюю симметрию, и чертёж вышел дельтоидом (AD = CD,
AC ⟂ BD), навязывая равенства, которых нет в условии. Здесь: дельтоид
бракуется, общий четырёхугольник и заявленные равенства проходят.
"""
import math

from geoexact.core import llm as L, pipeline, semantics
from geoexact.core.schema import FigurePlan
from geoexact.core.solver import solve
from geoexact.core.special_position import special_position_failures

PROD_TEXT = ("В выпуклом четырёхугольнике ABCD стороны AB и BC равны, "
             "K — точка пересечения диагоналей. Описанная окружность "
             "треугольника ABD повторно пересекает сторону BC в точке Y, "
             "а описанная окружность треугольника BCD повторно пересекает "
             "сторону AB в точке X. Докажите, что ∠AKX = ∠CKY.")

# Прод-чертёж (дельтоид), координаты из SVG, /10: AB=BC=36.29, AD=CD=24.22.
KITE = {"A": (6.2316, 16.2124), "B": (42.5184, 16.2124),
        "C": (33.1267, 51.2628), "D": (11.7947, 39.7876)}
# Общий четырёхугольник с AB = BC (та же задача, решение без симметрии).
GENERAL = {"A": (0.0, 0.0), "B": (2.0, 5.0), "C": (4.0, 0.0), "D": (1.0, -2.0)}


def test_prod_kite_fails():
    fails = special_position_failures(PROD_TEXT, None, KITE)
    assert len(fails) == 1, fails
    assert "AD" in fails[0] and "CD" in fails[0], fails
    assert "частное положение" in fails[0], fails


def test_general_quad_passes():
    assert special_position_failures(PROD_TEXT, None, GENERAL) == []


def test_stated_equality_passes():
    """AB = BC заявлено — равные AB и BC на чертеже не нарушение."""
    fails = special_position_failures(PROD_TEXT, None, GENERAL)
    ab = math.dist(GENERAL["A"], GENERAL["B"])
    bc = math.dist(GENERAL["B"], GENERAL["C"])
    assert abs(ab - bc) < 1e-9          # действительно равны
    assert not any("AB" in f and "BC" in f for f in fails), fails


def test_dokazhi_stated_pair_allowed():
    """«докажите, что AB = CD» — равенство заявлено (в цели), не частное."""
    text = "В четырёхугольнике ABCD диагонали пересекаются в K. Докажите, что AB = CD."
    # AB = CD = 5, остальные стороны попарно различны
    coords = {"A": (0, 0), "B": (5, 0), "C": (2, 8), "D": (2, 3)}
    assert special_position_failures(text, None, coords) == []


def test_rhombus_and_median_skipped():
    """Ромб и медиана: равенство может следовать из условия неявно — пропуск."""
    text_rhombus = "В ромбе ABCD угол A равен 60°."
    coords = {"A": (0, 0), "B": (2, 0), "C": (3, 1.732), "D": (1, 1.732)}
    assert special_position_failures(text_rhombus, None, coords) == []
    text_median = "В четырёхугольнике ABCD проведена медиана BM треугольника ABC."
    assert special_position_failures(text_median, None, KITE) == []


def test_trapezoid_equal_legs_fail():
    text = "В трапеции ABCD с основаниями BC и AD известно, что BC = 6, AD = 16."
    coords = {"A": (-8, 0), "B": (-3, 12), "C": (3, 12), "D": (8, 0)}  # ноги по 13
    fails = special_position_failures(text, None, coords)
    assert any("AB" in f and "CD" in f for f in fails), fails


def test_plan_dist_eq_not_laundering():
    """Равенство из ограничений плана НЕ заявлено в тексте — частное положение
    (прод-дельтоид возник именно из добавленной формализатором симметрии)."""
    plan = FigurePlan.from_dict({
        "points": ["A", "B", "C", "D"],
        "constructions": [{"op": "free_point", "out": n} for n in "ABCD"],
        "constraints": [{"type": "dist_eq", "args": ["A", "D", "C", "D"]}],
        "draw": {"segments": [["A", "B"], ["B", "C"], ["C", "D"], ["D", "A"]]},
        "target": {"kind": "none", "args": []},
        "scale_free": True,
    })
    # AD = CD = 5, остальные стороны различны
    coords = {"A": (0, 0), "B": (1, 0), "C": (8, 4), "D": (3, 4)}
    fails = special_position_failures("В четырёхугольнике ABCD O — точка.", plan, coords)
    assert len(fails) == 1 and "CD" in fails[0] and "AD" in fails[0], fails


def test_equal_numbers_stated_pass():
    """«AB = 5 и BC = 5» — равные числа заявляют равенство."""
    text = "В четырёхугольнике ABCD известно, что AB = 5 и BC = 5, CD = 3."
    coords = {"A": (0, 0), "B": (5, 0), "C": (9, 3), "D": (2, 4)}  # AB=BC=5
    assert special_position_failures(text, None, coords) == []


def test_different_numbers_not_equal():
    """BC = 6, AD = 16 — числа разные, равенство не заявлено."""
    text = "В трапеции ABCD с основаниями BC и AD известно, что BC = 6, AD = 16."
    coords = {"A": (-8, 0), "B": (-3, 12), "C": (3, 12), "D": (8, 0)}
    fails = special_position_failures(text, None, coords)
    assert not any("BC" in f and "AD" in f for f in fails), fails


def test_parallelogram_opposite_sides_skipped():
    """Параллелограмм: противоположные стороны равны по определению — не частное
    положение (регрессия из proof_fidelity: биссектриса + CDEF-параллелограмм)."""
    text = ("Точка E выбрана так, что четырёхугольник CDEF — параллелограмм. "
            "Докажите, что BE = BF.")
    coords = {"C": (0, 0), "D": (2, 1), "E": (5, 1), "F": (3, 0)}
    # CD = EF = √5, DE = CF = 3 — равные противоположные стороны
    assert special_position_failures(text, None, coords) == []


def test_rectangle_skipped():
    text = "В четырёхугольнике ABCD, который является прямоугольником, проведена диагональ."
    coords = {"A": (0, 0), "B": (5, 0), "C": (5, 3), "D": (0, 3)}
    assert special_position_failures(text, None, coords) == []


def test_triangle_not_checked():
    """Треугольники не проверяются: равенство сторон часто следует из углов."""
    text = "В треугольнике ABC угол A равен углу C. Найдите AB."
    coords = {"A": (0, 0), "B": (4, 0), "C": (2, 3)}  # AB=BC≈3.61 «на глаз»
    assert special_position_failures(text, None, coords) == []


def test_wrapper_installed_and_rule44_present():
    assert getattr(semantics.semantic_failures, "_special_position", False)
    assert "44." in L.SYS_FORMALIZE and "SPECIAL_POSITION_RULE" in L.SYS_FORMALIZE
    # повторная установка — no-op, суффикс не дублируется
    from geoexact.core.special_position import CACHE_SUFFIX as _SP_SUFFIX
    assert pipeline.ENGINE_VERSION.count(_SP_SUFFIX) == 1


def test_canonical_plan_general_solution_passes():
    """Канонический план (правило 44: line_intersect + один angle_eq) решается,
    и ранжирование общего положения выбирает НЕ дельтоид."""
    plan = FigurePlan.from_dict({
        "points": ["A", "B", "C", "D", "K", "X", "Y", "O1", "O2"],
        "constructions": [
            {"op": "free_point", "out": "A"},
            {"op": "free_point", "out": "B"},
            {"op": "free_point", "out": "C"},
            {"op": "free_point", "out": "D"},
            {"op": "circumcenter", "out": "O1", "args": ["A", "B", "D"]},
            {"op": "circumcenter", "out": "O2", "args": ["B", "C", "D"]},
            {"op": "line_circle_other", "out": "Y", "args": ["B", "C", "O1", "B"]},
            {"op": "line_circle_other", "out": "X", "args": ["B", "A", "O2", "B"]},
            {"op": "line_intersect", "out": "K", "args": ["A", "C", "B", "D"]},
        ],
        "constraints": [
            {"type": "dist_eq", "args": ["A", "B", "B", "C"]},
            {"type": "angle_eq", "args": ["A", "K", "X", "C", "K", "Y"]},
        ],
        "draw": {"segments": [["A", "B"], ["B", "C"], ["C", "D"], ["D", "A"]]},
        "target": {"kind": "none", "args": []},
        "scale_free": True,
    })
    sols = solve(plan, n_seeds=48)
    ok = [s for s in sols if s.ok]
    assert len(ok) >= 8, "семейство решений выродилось"
    ranked = semantics  # noqa: F841 — просто импорт
    from geoexact.core import gates
    best, gr = gates.rank_solutions(plan, ok)[0]
    coords = {k: tuple(v) for k, v in best.coords.items()}
    # дельтоид бы не прошёл проверку частного положения
    assert special_position_failures(PROD_TEXT, plan, coords) == []
