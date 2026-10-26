# -*- coding: utf-8 -*-
"""Спец-план «точка с отношением на медиане + параллельная прямая».

Прод-кейс (26.10.2026, задача пользователя): медиана BM, BK:KM = 3:1,
прямая через K параллельна AC, P и Q на AB и BC — формализатор давал
FORWARD_REF на Q, задача падала в схематичный эскиз.
"""
import numpy as np
import pytest

import geoexact.core                       # обёртки устанавливаются при импорте
from geoexact.core import pipeline, semantics
from geoexact.core.median_parallel import median_parallel_plan
from geoexact.core.schema import validate_plan
from geoexact.core.solver import solve

PROD_TEXT = (
    "В треугольнике ABC на медиане BM отмечена точка K так, что BK:KM = 3:1. "
    "Через точку K проведена прямая, параллельная AC, пересекающая стороны "
    "AB и BC в точках P и Q соответственно. Найдите отношение площади "
    "четырёхугольника APQC к площади треугольника ABC.")


def test_engine_suffix():
    assert "+medPar1" in pipeline.ENGINE_VERSION


def test_wrapper_installed():
    assert getattr(semantics.trisected_parallel_plan, "_median_parallel", False)


def test_prod_text_builds_plan():
    plan = median_parallel_plan(PROD_TEXT, False)
    assert plan is not None
    assert validate_plan(plan) in ([], None)


def test_prod_plan_solves_exactly():
    plan = median_parallel_plan(PROD_TEXT, False)
    sols = solve(plan)
    good = [s for s in sols if s.ok]
    assert len(good) >= 5, [str(getattr(s, "reason", "")) for s in sols[:3]]
    P = {k: np.asarray(v, dtype=float) for k, v in good[0].coords.items()}
    bk = float(np.hypot(*(P["K"] - P["B"])))
    km = float(np.hypot(*(P["M"] - P["K"])))
    assert abs(bk - 3 * km) < 1e-9 * max(1.0, bk)
    assert abs(float(np.hypot(*(P["M"] - P["A"])))
               - float(np.hypot(*(P["C"] - P["M"])))) < 1e-9
    # PQ ∥ AC
    v1 = P["Q"] - P["P"]; v2 = P["C"] - P["A"]
    assert abs(v1[0] * v2[1] - v1[1] * v2[0]) < 1e-9
    # P на AB, Q на BC
    for a, b, pt in (("A", "B", "P"), ("B", "C", "Q")):
        v1, v2 = P[pt] - P[a], P[b] - P[pt]
        assert abs(v1[0] * v2[1] - v1[1] * v2[0]) < 1e-9
    # площадь APQC / ABC = 1 − (3/4)² = 7/16
    def area(*ids):
        return abs(np.cross(P[ids[1]] - P[ids[0]], P[ids[2]] - P[ids[0]])) / 2
    ratio = (area("A", "B", "C") - area("B", "P", "Q")) / area("A", "B", "C")
    assert abs(ratio - 7 / 16) < 1e-9


def test_other_ratio_and_labels():
    text = ("В треугольнике KLM на медиане LN отмечена точка T так, что "
            "LT:TN = 1:2. Через точку T проведена прямая, параллельная KM, "
            "пересекающая стороны LK и LM в точках R и S соответственно. "
            "Найдите отношение площади четырёхугольника KRSM к площади "
            "треугольника KLM.")
    plan = median_parallel_plan(text, False)
    assert plan is not None
    sols = [s for s in solve(plan) if s.ok]
    assert len(sols) >= 5
    P = {k: np.asarray(v, dtype=float) for k, v in sols[0].coords.items()}
    lt = float(np.hypot(*(P["T"] - P["L"])))
    tn = float(np.hypot(*(P["N"] - P["T"])))
    assert abs(lt - 0.5 * tn) < 1e-9 * max(1.0, lt)
    # N — середина KM
    assert abs(float(np.hypot(*(P["N"] - P["K"])))
               - float(np.hypot(*(P["M"] - P["N"])))) < 1e-9
    # RS ∥ KM
    v1 = P["S"] - P["R"]; v2 = P["M"] - P["K"]
    assert abs(v1[0] * v2[1] - v1[1] * v2[0]) < 1e-9


def test_rejects_extra_data():
    text = ("В треугольнике ABC на медиане BM отмечена точка K так, что "
            "BK:KM = 3:1. Известно, что BC = 10. Через точку K проведена "
            "прямая, параллельная AC, пересекающая стороны AB и BC в точках "
            "P и Q соответственно.")
    assert median_parallel_plan(text, False) is None


def test_rejects_non_median():
    text = ("В треугольнике ABC на стороне BM отмечена точка K так, что "
            "BK:KM = 3:1. Через точку K проведена прямая, параллельная AC, "
            "пересекающая стороны AB и BC в точках P и Q соответственно.")
    assert median_parallel_plan(text, False) is None
