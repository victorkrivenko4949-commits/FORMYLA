# -*- coding: utf-8 -*-
"""CH27: тесты reflect_point / rotate_point / mark_intersection (step-id)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from geometric_engine.engine import GeometricEngine  # noqa: E402
from geometric_engine import geom  # noqa: E402
from services.aux_compiler import compile_steps_to_aux  # noqa: E402


def _build(description, seed=42):
    eng = GeometricEngine()
    svg, ctx = eng.build(description, seed=seed)
    return svg, ctx, eng


BASE = {
    "canvas": {"width": 600, "height": 500, "margin": 40},
    "constructions": [
        {"type": "free_point", "id": "A", "x": 100, "y": 100},
        {"type": "free_point", "id": "B", "x": 400, "y": 100},
        {"type": "free_point", "id": "C", "x": 300, "y": 300},
        {"type": "free_point", "id": "M", "x": 250, "y": 100},
    ],
}


# ── FIX1: reflect_point ──

def test_reflect_point_midpoint_equal():
    plan = dict(BASE)
    plan["constructions"] = BASE["constructions"] + [
        {"type": "reflect_point", "id": "D", "point": "B", "center": "M"},
    ]
    _, ctx, _ = _build(plan)
    B = ctx.points["B"]
    M = ctx.points["M"]
    D = ctx.points["D"]
    # D = 2M - B.
    assert abs(D[0] - (2 * M[0] - B[0])) < 1e-9
    assert abs(D[1] - (2 * M[1] - B[1])) < 1e-9
    # M — середина BD.
    mid = geom.midpoint(B, D)
    assert geom.dist(mid, M) < 1e-9
    # длины равны.
    assert abs(geom.dist(B, M) - geom.dist(M, D)) < 1e-9


# ── FIX2: rotate_point ──

def test_rotate_point_preserves_distance():
    plan = dict(BASE)
    plan["constructions"] = BASE["constructions"] + [
        {"type": "rotate_point", "id": "P2", "point": "A", "center": "B", "degrees": 60},
    ]
    _, ctx, _ = _build(plan)
    A = ctx.points["A"]
    B = ctx.points["B"]
    P2 = ctx.points["P2"]
    assert abs(geom.dist(B, A) - geom.dist(B, P2)) < 1e-9


def test_rotate_point_90_degrees_direction():
    # Поворот на 90°: в SVG (Y вниз) положительный угол = по часовой стрелке.
    plan = {
        "canvas": {"width": 600, "height": 500, "margin": 40},
        "constructions": [
            {"type": "free_point", "id": "B", "x": 300, "y": 250},
            {"type": "free_point", "id": "A", "x": 400, "y": 250},  # вправо от B
        ],
    }
    plan["constructions"].append(
        {"type": "rotate_point", "id": "P2", "point": "A", "center": "B", "degrees": 90}
    )
    _, ctx, _ = _build(plan)
    B = ctx.points["B"]
    A = ctx.points["A"]
    P2 = ctx.points["P2"]
    # A вправо (dx>0, dy=0).  После +90° (по часовой) — P2 должен быть ВНИЗ (dy>0).
    assert A[0] - B[0] > 0
    assert abs(P2[0] - B[0]) < 1e-6
    assert P2[1] - B[1] > 0  # вниз


def test_rotate_point_maps_a_to_c():
    # maps: ["A", "C"] — угол ∠ABC, знак такой, чтобы A перешла в C.
    plan = {
        "canvas": {"width": 600, "height": 500, "margin": 40},
        "constructions": [
            {"type": "free_point", "id": "B", "x": 300, "y": 250},
            {"type": "free_point", "id": "A", "x": 400, "y": 250},
            {"type": "free_point", "id": "C", "x": 300, "y": 150},  # вверх от B
        ],
    }
    plan["constructions"].append(
        {"type": "rotate_point", "id": "P2", "point": "A", "center": "B", "maps": ["A", "C"]}
    )
    _, ctx, _ = _build(plan)
    B = ctx.points["B"]
    A = ctx.points["A"]
    C = ctx.points["C"]
    P2 = ctx.points["P2"]
    # Поворот должен перевести A в направление C (на луче B->C).
    assert geom.dist(P2, C) < 1e-6


# ── FIX3: mark_intersection с step-id ──

def test_mark_intersection_step_id():
    steps = [
        {"step_no": 1, "id": "par_N", "action": "draw_parallel",
         "args": {"p1": "N", "p2": "A"}, "creates_point": None,
         "quote": "Проведём через N прямую, параллельную ..."},
        {"step_no": 2, "action": "mark_intersection",
         "args": {"obj1": "par_N", "obj2": ["A", "C"]},
         "creates_point": "K", "quote": "пересекает AC в точке K"},
    ]
    # N должен существовать в base.
    base = dict(BASE)
    base["constructions"] = BASE["constructions"] + [
        {"type": "free_point", "id": "N", "x": 150, "y": 200},
    ]
    aux, issues = compile_steps_to_aux(steps, base)
    cs = aux["constructions"]
    inter = [c for c in cs if c.get("type") == "intersect_lines"]
    assert len(inter) == 1, issues
    k = inter[0]
    assert k["id"] == "K"
    # obj2 ["A","C"] резолвится в линию (aux_line или существующий отрезок).
    assert k["line2"]
    assert not any(i.startswith("UNKNOWN_STEP_ID") for i in issues)


def test_mark_intersection_old_form():
    steps = [
        {"step_no": 1, "action": "mark_intersection",
         "args": {"line1": ["A", "B"], "line2": ["A", "C"]},
         "creates_point": "X", "quote": "пересечение AB и AC"},
    ]
    aux, issues = compile_steps_to_aux(steps, BASE)
    inter = [c for c in aux["constructions"] if c.get("type") == "intersect_lines"]
    assert len(inter) == 1
    assert not any(i.startswith("UNKNOWN_STEP_ID") for i in issues)


def test_mark_intersection_unknown_step_id():
    steps = [
        {"step_no": 1, "action": "mark_intersection",
         "args": {"obj1": "no_such", "obj2": ["A", "C"]},
         "creates_point": "K", "quote": "пересечение"},
    ]
    aux, issues = compile_steps_to_aux(steps, BASE)
    assert any(i.startswith("UNKNOWN_STEP_ID:no_such") for i in issues)
