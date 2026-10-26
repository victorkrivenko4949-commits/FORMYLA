# -*- coding: utf-8 -*-
"""Плечи и дуги углов из утверждения — на чертеже.

Прод-кейс (AKX=CKY, 26.10.2026): чертёж точный, но отрезки KX и KY не
проведены — углы из «докажите» не видны. Формализатор рисует плечи не
всегда; обёртка добирает недостающие сегменты и дуги-метки сама.
"""
from unittest.mock import patch

import geoexact.core                       # обёртки устанавливаются при импорте
from geoexact.core import llm as L, pipeline
from geoexact.core.claim_arms import add_claim_arms, add_claim_angle_marks
from geoexact.core.schema import FigurePlan

AKX_TEXT = ("В выпуклом четырёхугольнике ABCD стороны AB и BC равны, K — точка "
            "пересечения диагоналей. Описанная окружность треугольника ABD "
            "повторно пересекает сторону BC в точке Y, а описанная окружность "
            "треугольника BCD повторно пересекает сторону AB в точке X. "
            "Докажите, что ∠ AKX = ∠ CKY.")

# draw как в прод-плане: A-K и C-K есть, KX и KY — нет
AKX_DRAW = {"segments": [["A", "B"], ["B", "C"], ["C", "D"], ["D", "A"],
                         ["A", "C"], ["B", "D"], ["A", "K"], ["C", "K"],
                         ["B", "X"], ["B", "Y"]]}


def _plan(text_draw=None):
    import copy
    return FigurePlan.from_dict({
        "points": ["A", "B", "C", "D", "K", "X", "Y"],
        "constructions": [{"op": "free_point", "out": p}
                          for p in ("A", "B", "C", "D", "K", "X", "Y")],
        "constraints": [],
        "draw": copy.deepcopy(text_draw or AKX_DRAW),
        "target": {"kind": "none", "args": []},
        "scale_free": True,
        "notes": "n",
    })


def test_adds_missing_arms():
    plan = _plan()
    added = add_claim_arms(AKX_TEXT, plan)
    assert sorted(added) == ["KX", "KY"]
    segs = {tuple(s) for s in plan.draw.segments}
    assert ("K", "X") in segs and ("K", "Y") in segs
    assert ("A", "K") in segs and ("C", "K") in segs


def test_idempotent_no_duplicates():
    plan = _plan()
    add_claim_arms(AKX_TEXT, plan)
    n = len(plan.draw.segments)
    assert add_claim_arms(AKX_TEXT, plan) == []
    assert len(plan.draw.segments) == n


def test_skips_unknown_points():
    text = "Докажите, что ∠ AKZ = ∠ CKZ."
    plan = _plan()
    assert add_claim_arms(text, plan) == []


def test_latex_angle_form():
    text = ("Дан остроугольный треугольник ABC. Докажите, что "
            "\\( \\angle BAC = \\angle CAD \\).")
    plan = FigurePlan.from_dict({
        "points": ["A", "B", "C", "D"],
        "constructions": [{"op": "free_point", "out": p} for p in "ABCD"],
        "constraints": [],
        "draw": {"segments": [["A", "B"], ["A", "C"]]},
        "target": {"kind": "none", "args": []},
        "scale_free": True, "notes": "n",
    })
    added = add_claim_arms(text, plan)
    assert sorted(added) == ["AD"]          # AB и AC уже нарисованы
    segs = {tuple(s) for s in plan.draw.segments}
    assert ("A", "D") in segs


def test_russian_word_form():
    text = "Докажите, что угол AKX равен углу CKY."
    plan = _plan()
    added = add_claim_arms(text, plan)
    assert sorted(added) == ["KX", "KY"]


def test_angle_marks_added():
    plan = _plan()
    added = add_claim_angle_marks(AKX_TEXT, plan)
    assert added == ["K", "K"]
    pts_list = [tuple(m["pts"]) for m in plan.draw.angle_marks]
    assert ("A", "K", "X") in pts_list and ("C", "K", "Y") in pts_list
    # повторно — без дубликатов
    assert add_claim_angle_marks(AKX_TEXT, plan) == []


def test_angle_mark_respects_existing():
    plan = _plan()
    plan.draw.angle_marks.append({"pts": ["X", "K", "A"]})   # те же лучи
    assert add_claim_angle_marks(AKX_TEXT, plan) == ["K"]    # только CKY


def test_wrapper_installed():
    assert getattr(pipeline._strip_invented_labels, "_claim_arms", False)
    assert "+claimArms1" in pipeline.ENGINE_VERSION


def test_pipeline_route_adds_arms():
    """Прод-маршрут: медиана BM, углы ∠AMB + ∠BMC = 180° — плечи AM и MC
    должны появиться на итоговом SVG (формализатор их не нарисовал)."""
    text = ("В треугольнике ABC проведена медиана BM. Докажите, что "
            "\\( \\angle AMB + \\angle BMC = 180^\\circ \\).")
    formalized = {
        "space": "plane",
        "points": ["A", "B", "C", "M"],
        "constructions": [
            {"op": "free_point", "out": "A"},
            {"op": "free_point", "out": "B"},
            {"op": "free_point", "out": "C"},
            {"op": "midpoint", "args": ["A", "C"], "out": "M"},
        ],
        "constraints": [],
        "draw": {"segments": [["A", "B"], ["B", "C"], ["C", "A"], ["B", "M"]]},
        "target": {"kind": "none", "args": []},
        "scale_free": True,
        "notes": "n",
    }
    with patch.object(L, "classify", lambda *a, **k: {"ok": True, "class": "O", "space": "plane"}), \
         patch.object(L, "formalize", lambda *a, **k: (FigurePlan.from_dict(formalized), [])):
        result = pipeline.generate(text, use_cache=False)
    assert result.ok and result.stage == "9-render", (result.stage, result.detail)

    import xml.etree.ElementTree as ET
    import numpy as np
    root = ET.fromstring(result.svg)
    NS = "{http://www.w3.org/2000/svg}"
    pts = {c.get("data-point"): (float(c.get("cx")), float(c.get("cy")))
           for c in root.iter(NS + "circle") if c.get("data-point")}
    assert {"A", "B", "C", "M"} <= set(pts)

    def _on(p, q, r):
        a, b = np.array(pts[q]) - np.array(pts[p]), np.array(pts[r]) - np.array(pts[p])
        return abs(np.cross(a, b)) < 1e-6 * max(np.linalg.norm(a), 1.0)

    # AM и MC проведены: A, M, C на одной прямой и отрезки есть в линиях
    assert _on("A", "M", "C"), "медиана не прямая"
    # проверяем через рендер: точки A-M-C коллинеарны и плечи AM/MC присутствуют
    # как отдельные <line> элементы (плечи добавлены обёрткой)
    lines_svg = root.iter(NS + "line")
    n_am_mc = 0
    P = {k: np.array(v) for k, v in pts.items()}
    for ln in lines_svg:
        x1, y1 = float(ln.get("x1")), float(ln.get("y1"))
        x2, y2 = float(ln.get("x2")), float(ln.get("y2"))
        for (u, v) in ((P["A"], P["M"]), (P["M"], P["C"])):
            d1 = np.hypot(x1 - u[0], y1 - u[1]) + np.hypot(x2 - v[0], y2 - v[1])
            d2 = np.hypot(x1 - v[0], y1 - v[1]) + np.hypot(x2 - u[0], y2 - u[1])
            if min(d1, d2) < 2.0:
                n_am_mc += 1
                break
    assert n_am_mc >= 2, "плечи AM/MC не отрисованы"
