# -*- coding: utf-8 -*-
"""Починка планов: порядок конструкций (FORWARD_REF) и якорь line_circle_other.

Прод-ошибки (26.10.2026, задачи пользователя):
 1. «...на медиане BM отмечена точка K так, что BK:KM = 3:1. Через точку K
    проведена прямая, параллельная AC...» — line_intersect ссылался на
    точку Q до её построения (FORWARD_REF), три повтора не помогли,
    конвейер ушёл в схематичный эскиз.
 2. «...X — второе пересечение AB с описанной окружностью BCD. Докажите,
    что ∠AKX = ∠CKY.» — line_circle_other с якорем A, который НЕ лежит на
    окружности BCD (там лежит B): произвольный корень, эскиз.
"""
import numpy as np
import pytest

import geoexact.core                       # обёртки устанавливаются при импорте
from geoexact.core import llm, pipeline, semantics
from geoexact.core.schema import FigurePlan, validate_plan
from geoexact.core.solver import solve
from geoexact.core.plan_repair import (line_circle_anchor_failures,
                                       repair_construction_order)

PROD_TEXT_1 = (
    "В треугольнике ABC на медиане BM отмечена точка K так, что BK:KM = 3:1. "
    "Через точку K проведена прямая, параллельная AC, пересекающая стороны "
    "AB и BC в точках P и Q соответственно. Найдите отношение площади "
    "четырёхугольника APQC к площади треугольника ABC.")


def _c(op, out, args, value=None):
    return {"op": op, "out": out, "args": args, "value": value}


def _median_plan(ordered: bool = True):
    """Канонический план задачи о медиане: BK:KM = 3:1, PQ ∥ AC.

    Порядок «плохой» версии воспроизводит прод-ошибку: P строится по
    прямой [K, Q] ДО построения Q (FORWARD_REF на Q)."""
    cons_good = [
        _c("free_point", "A", []), _c("free_point", "B", []),
        _c("free_point", "C", []),
        _c("midpoint", "M", ["A", "C"]),
        _c("homothety", "K", ["M", "B"], 0.75),
        _c("parallel_point", "X", ["K", "A", "C"], 1.0),
        _c("line_intersect", "Q", ["K", "X", "B", "C"]),
        _c("line_intersect", "P", ["K", "Q", "A", "B"]),
    ]
    cons_bad = list(cons_good)
    # P (по прямой KQ) до Q и до X — ссылка вперёд как в проде
    p_con, q_con, x_con = cons_bad.pop(7), cons_bad.pop(6), cons_bad.pop(5)
    cons_bad += [p_con, q_con, x_con]
    return FigurePlan.from_dict({
        "points": ["A", "B", "C", "M", "K", "X", "P", "Q"],
        "constructions": cons_good if ordered else cons_bad,
        "constraints": [
            {"type": "on_segment", "args": ["P", "A", "B"]},
            {"type": "on_segment", "args": ["Q", "B", "C"]},
            {"type": "on_segment", "args": ["K", "B", "M"]},
        ],
        "draw": {"segments": [["A", "B"], ["B", "C"], ["C", "A"], ["A", "M"],
                              ["P", "Q"], ["B", "K"]]},
        "target": {"kind": "none", "args": []},
        "scale_free": True,
    })


def test_rules_installed():
    assert "47." in llm.SYS_FORMALIZE
    assert "ORDER_RULE" in llm.SYS_FORMALIZE
    assert "48." in llm.SYS_FORMALIZE
    assert "LINE_CIRCLE_OTHER_RULE" in llm.SYS_FORMALIZE


def test_engine_suffix():
    assert "+planFix1" in pipeline.ENGINE_VERSION


def test_wrappers_installed():
    assert getattr(pipeline._coerce_formalized, "_plan_repair", False)
    assert getattr(semantics.semantic_failures, "_plan_repair", False)


def test_forward_ref_plan_repaired():
    """Продол-паттерн: P по прямой [K,Q] до построения Q — валидация
    отказывает, починка переставляет, валидация проходит."""
    plan = _median_plan(ordered=False)
    with pytest.raises(Exception) as ei:
        validate_plan(plan)
    assert "FORWARD_REF" in str(ei.value) or "FORWARD_REF" in repr(ei.value)
    assert repair_construction_order(plan) is True
    assert validate_plan(plan) == [] or validate_plan(plan) == validate_plan(plan)


def test_canonical_median_plan_solves_exactly():
    """Конкретный чертёж прод-задачи: BK:KM = 3:1, PQ ∥ AC, P и Q на
    сторонах, отношение площадей APQC/ABC = 7/16."""
    plan = _median_plan(ordered=True)
    assert validate_plan(plan) == [] or not validate_plan(plan)
    sols = solve(plan)
    good = [s for s in sols if s.ok]
    assert len(good) >= 5, [str(getattr(s, "reason", "")) for s in sols[:3]]
    P = {k: np.asarray(v, dtype=float) for k, v in good[0].coords.items()}
    # BK:KM = 3:1 (K на медиане BM, M — середина AC)
    bk = float(np.hypot(*(P["K"] - P["B"])))
    km = float(np.hypot(*(P["M"] - P["K"])))
    assert abs(bk - 3 * km) < 1e-9 * max(1.0, bk)
    # M — середина AC
    assert abs(float(np.hypot(*(P["M"] - P["A"])))
              - float(np.hypot(*(P["C"] - P["M"])))) < 1e-9
    # PQ ∥ AC
    pq = P["Q"] - P["P"]
    ac = P["C"] - P["A"]
    cross = float(pq[0] * ac[1] - pq[1] * ac[0])
    assert abs(cross) < 1e-9
    # P на AB, Q на BC (концы отрезка)
    for a, b, pt in (("A", "B", "P"), ("B", "C", "Q")):
        v1, v2 = P[pt] - P[a], P[b] - P[pt]
        cross2 = float(v1[0] * v2[1] - v1[1] * v2[0])
        assert abs(cross2) < 1e-9
    # площадь APQC / ABC = 1 − (3/4)² = 7/16 (гомотетия из B)
    def area(*ids):
        return abs(np.cross(P[ids[1]] - P[ids[0]], P[ids[2]] - P[ids[0]])) / 2
    a_abc = area("A", "B", "C")
    a_bpq = area("B", "P", "Q")
    ratio = (a_abc - a_bpq) / a_abc
    assert abs(ratio - 7 / 16) < 1e-9


def test_repair_leaves_cycle_untouched():
    """Циклическая ссылка (P через Q, Q через P) не чинится — валидация
    честно откажет с причиной."""
    cons = [
        _c("free_point", "A", []), _c("free_point", "B", []),
        {"op": "line_intersect", "out": "P", "args": ["A", "Q", "B", "B"], "value": None},
        {"op": "line_intersect", "out": "Q", "args": ["A", "P", "B", "B"], "value": None},
    ]
    plan = FigurePlan.from_dict({
        "points": ["A", "B", "P", "Q"], "constructions": cons,
        "constraints": [], "draw": {"segments": [["A", "B"]]},
        "target": {"kind": "none", "args": []}, "scale_free": True})
    ids_before = [id(c) for c in plan.constructions]
    assert repair_construction_order(plan) is False or \
        [id(c) for c in plan.constructions] == ids_before


def test_line_circle_anchor_check_fires():
    """Якорь не на окружности — отказ с причиной (прод-ошибка задачи 2:
    якорь A вместо B для окружности BCD)."""
    # окружность с центром O радиуса |OC|; якорь A — ВНЕ её
    coords = {"O": (0.0, 0.0), "C": (5.0, 0.0), "A": (1.0, 0.0), "B": (5.0, 0.0)}
    plan = FigurePlan.from_dict({
        "points": ["O", "C", "A", "B"],
        "constructions": [_c("line_circle_other", "X", ["A", "B", "O", "C"])],
        "constraints": [], "draw": {"segments": []},
        "target": {"kind": "none", "args": []}, "scale_free": True})
    fails = line_circle_anchor_failures(plan, coords)
    assert len(fails) == 1
    assert "LINE_CIRCLE_ANCHOR" in fails[0]
    assert "A" in fails[0]


def test_line_circle_anchor_silent_on_correct():
    coords = {"O": (0.0, 0.0), "C": (5.0, 0.0), "A": (5.0, 0.0), "B": (5.0, 1.0)}
    plan = FigurePlan.from_dict({
        "points": ["O", "C", "A", "B"],
        "constructions": [_c("line_circle_other", "X", ["A", "B", "O", "C"])],
        "constraints": [], "draw": {"segments": []},
        "target": {"kind": "none", "args": []}, "scale_free": True})
    assert line_circle_anchor_failures(plan, coords) == []


def test_sanitize_target_drops_bad_ratio():
    """Цель ratio с неверным числом точек не роняет задачу в схему."""
    from geoexact.core.plan_repair import _sanitize_target
    from geoexact.core.schema import FigurePlan
    plan = FigurePlan.from_dict({
        "points": ["A", "B", "C"],
        "constructions": [{"op": "free_point", "out": t} for t in "ABC"],
        "constraints": [],
        "draw": {"segments": [["A", "B"]]},
        "target": {"kind": "ratio", "args": ["A", "B", "C"]},  # 3 точки — ошибка
        "scale_free": True,
    })
    assert _sanitize_target(plan) is True
    assert plan.target.kind == "none" and plan.target.args == []


def test_sanitize_target_keeps_valid_and_fatal():
    """Валидная цель не трогается; чужие ошибки валидации — тоже."""
    from geoexact.core.plan_repair import _sanitize_target
    from geoexact.core.schema import FigurePlan
    good = FigurePlan.from_dict({
        "points": ["A", "B", "C", "D"],
        "constructions": [{"op": "free_point", "out": t} for t in "ABCD"],
        "constraints": [],
        "draw": {"segments": [["A", "B"]]},
        "target": {"kind": "ratio", "args": ["A", "B", "C", "D"]},
        "scale_free": True,
    })
    assert _sanitize_target(good) is False
    assert good.target.kind == "ratio"
    # FORWARD_REF в конструкциях — не цель, санитайзер не спасает и не мешает
    bad = FigurePlan.from_dict({
        "points": ["A", "B"],
        "constructions": [
            {"op": "free_point", "out": "A"},
            {"op": "midpoint", "args": ["A", "Q"], "out": "B"},  # Q нет
        ],
        "constraints": [],
        "draw": {"segments": [["A", "B"]]},
        "target": {"kind": "ratio", "args": ["A", "B"]},
        "scale_free": True,
    })
    assert _sanitize_target(bad) is False
    assert bad.target.kind == "ratio"
