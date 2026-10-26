# -*- coding: utf-8 -*-
"""Канонический план «D диаметрально противоположна A, BX=XD, CY=YD».

Прод-кластер: 6 отправок пользователя ушли в approximate/sketch; починка
equidistant_repair ловила только известные кодировки LLM — 26.10.2026
план прошёл валидацию, но солвер дал DEGENERATE_FIGURE (ACD схлопнулся).
Теперь конфигурация строится канонически, без формализатора.
"""
import numpy as np
import pytest

import geoexact.core                       # обёртки устанавливаются при импорте
from geoexact.core import pipeline, semantics
from geoexact.core.diametral_plan import diametral_plan
from geoexact.core.schema import validate_plan
from geoexact.core.solver import solve

PROD_TEXT = (
    "Задача 2. Дан остроугольный треугольник \\(ABC\\). На его описанной "
    "окружности отмечена точка \\(D\\), диаметрально противоположная вершине "
    "\\(A\\). Точки \\(X\\) и \\(Y\\) на стороне \\(BC\\) таковы, что "
    "\\(BX = XD\\) и \\(CY = YD\\) (точка \\(X\\) лежит на отрезке "
    "\\(BY\\)). Докажите, что \\(DA\\) — биссектриса угла \\(XDY\\).")


def test_engine_suffix():
    assert "+diaPlan1" in pipeline.ENGINE_VERSION


def test_wrapper_installed():
    assert getattr(semantics.trisected_parallel_plan, "_diametral_plan", False)


def test_prod_text_builds_plan():
    plan = diametral_plan(PROD_TEXT, False)
    assert plan is not None
    # UNDERDETERMINED — косметика фиксированной формы (0 уравнений);
    # pipeline для special-планов сам его отфильтровывает (pipeline.py:630)
    warn = [w for w in validate_plan(plan) if not w.startswith("UNDERDETERMINED:")]
    assert warn in ([], None)


def test_prod_plan_solves_exactly():
    plan = diametral_plan(PROD_TEXT, False)
    sols = solve(plan)
    good = [s for s in sols if s.ok]
    assert len(good) >= 5, [str(getattr(s, "reason", "")) for s in sols[:3]]
    P = {k: np.asarray(v, dtype=float) for k, v in good[0].coords.items()}
    d = lambda u, v: float(np.linalg.norm(P[u] - P[v]))
    # равенства расстояний — точно по построению
    assert abs(d("B", "X") - d("X", "D")) < 1e-9
    assert abs(d("C", "Y") - d("Y", "D")) < 1e-9
    # D — антипод A относительно O
    O = P["O_"]
    assert np.linalg.norm(P["D"] - (2 * O - P["A"])) < 1e-9
    # X и Y на BC, порядок B-X-Y-C
    def t(pt, a, b):
        return float(np.dot(P[pt] - P[a], P[b] - P[a]) / np.dot(P[b] - P[a], P[b] - P[a]))
    for pt in ("X", "Y"):
        assert abs(np.cross(P["C"] - P["B"], P[pt] - P["B"])) < 1e-9
        assert -1e-9 < t(pt, "B", "C") < 1 + 1e-9
    assert t("X", "B", "C") < t("Y", "B", "C")
    # биссектриса: угол XDA = угол ADY
    def ang(u, v):
        u = u / np.linalg.norm(u); v = v / np.linalg.norm(v)
        return np.degrees(np.arccos(np.clip(u @ v, -1, 1)))
    a1 = ang(P["X"] - P["D"], P["A"] - P["D"])
    a2 = ang(P["A"] - P["D"], P["Y"] - P["D"])
    assert abs(a1 - a2) < 1e-7


def test_rejects_modified_text():
    text = ("Дан остроугольный треугольник ABC. На его описанной окружности "
            "отмечена точка D, диаметрально противоположная вершине A. Точки "
            "X и Y на стороне BC таковы, что BX = XD и CY = YD (точка X лежит "
            "на отрезке BY). Докажите, что DA — биссектриса угла XDY. "
            "Дополнительно XD = DB.")
    assert diametral_plan(text, False) is None


def test_pipeline_route_exact_without_llm():
    """Прод-маршрут целиком: спец-план строит точный чертёж без формализатора
    (перехват только classify — formalize не вызывается, план канонический)."""
    from unittest.mock import patch
    from geoexact.core import llm as L
    with patch.object(L, "classify", lambda *a, **k: {"ok": True, "class": "O", "space": "plane"}):
        result = pipeline.generate(PROD_TEXT, use_cache=False)
    assert result.ok and result.stage == "9-render", (result.stage, result.detail)
    assert result.verification == "constraints_only", result.warnings
    import xml.etree.ElementTree as ET
    root = ET.fromstring(result.svg)
    NS = "{http://www.w3.org/2000/svg}"
    pts = {c.get("data-point"): (float(c.get("cx")), float(c.get("cy")))
           for c in root.iter(NS + "circle") if c.get("data-point")}
    assert {"A", "B", "C", "D", "X", "Y"} <= set(pts)
    A, B, C, D = (np.array(pts[k]) for k in "ABCD")
    X, Y = np.array(pts["X"]), np.array(pts["Y"])
    # равенства и порядок на BC
    bc = C - B
    t = lambda P_: float((P_ - B) @ bc / (bc @ bc))
    assert 0 < t(X) < t(Y) < 1, (t(X), t(Y))
    for p1, p2, q1, q2 in (("B", "X", "X", "D"), ("C", "Y", "Y", "D")):
        d1 = np.linalg.norm(np.array(pts[p1]) - np.array(pts[p2]))
        d2 = np.linalg.norm(np.array(pts[q1]) - np.array(pts[q2]))
        assert abs(d1 - d2) < 1e-6 * max(d1, d2), (p1, d1, d2)
    # остроугольность
    for v, p, q in (("A", "B", "C"), ("B", "A", "C"), ("C", "A", "B")):
        u, w = np.array(pts[p]) - np.array(pts[v]), np.array(pts[q]) - np.array(pts[v])
        ang = np.degrees(np.arccos(np.clip(u @ w / np.linalg.norm(u) / np.linalg.norm(w), -1, 1)))
        assert ang < 89.0, f"угол {v} = {ang:.1f}"
