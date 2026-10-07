# -*- coding: utf-8 -*-
"""services/base_normalizer.py — детерминированная нормализация base-плана.

Исправляет типичную ошибку Gemini-планировщика: точки касания вписанной
окружности задаются как point_on_segment с произвольным ratio, из-за чего
отрезки «AC1 = AB1», «BA1 = BC1», «CA1 = CB1» НЕ сходятся численно, хотя на
чертеже ставятся equal_segments_mark.

Нормализатор находит паттерн «три точки на сторонах треугольника + попарные
равенства касательных из вершин» и заменяет point_on_segment на нативный
incircle_touch, чтобы равенства реально выполнялись.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def _triangle_vertices(cs: List[dict]) -> List[str]:
    return [c.get("id") for c in cs
            if isinstance(c, dict) and c.get("type") == "free_point" and c.get("id")]


def _point_on_side(cs: List[dict], side_pair, names) -> Optional[str]:
    """Найти точку на стороне side_pair (два id вершин), чей id ∈ names."""
    s = set(side_pair)
    for c in cs:
        if c.get("type") == "point_on_segment":
            if {c.get("p1"), c.get("p2")} == s and c.get("id") in names:
                return c.get("id")
    return None


def normalize_base_plan(base_plan: Dict[str, Any]) -> Dict[str, Any]:
    """Нормализовать base-план: заменить «точку касания как point_on_segment»
    на нативный incircle_touch, когда в плане есть equal_segments_mark с
    паттерном касательных (AC1=AB1, BA1=BC1, CA1=CB1).

    Возвращает новый план (исходный не мутируется).
    """
    import copy
    base = copy.deepcopy(base_plan)
    if not isinstance(base, dict):
        return base_plan

    cs = base.get("constructions", [])
    if not isinstance(cs, list):
        return base_plan

    tri = _triangle_vertices(cs)
    if len(tri) < 3:
        return base_plan
    A, B, C = tri[0], tri[1], tri[2]

    # Собрать все пары равных отрезков из equal_segments_mark.
    eq_pairs = []
    for c in cs:
        if c.get("type") != "equal_segments_mark":
            continue
        segs = c.get("segments") or []
        pairs = []
        if segs and isinstance(segs[0], (list, tuple)):
            pairs = [list(p) for p in segs if isinstance(p, (list, tuple)) and len(p) >= 2]
        else:
            pairs = [[segs[i], segs[i + 1]] for i in range(0, len(segs) - 1, 2)]
        for (x, y) in pairs:
            if isinstance(x, str) and isinstance(y, str):
                eq_pairs.append((x, y))

    # Ищем паттерн касательных из вершин: для вершины V два отрезка (V, T1) и
    # (V, T2), где T1/T2 — точки на сторонах, прилегающих к V.
    # Стороны: AB (C напротив), BC (A напротив), CA (B напротив).
    touch_names = {"A1", "A_1", "B1", "B_1", "C1", "C_1", "A2", "A_2", "B2", "B_2", "C2", "C_2"}

    def _find_touch_points(vertex, adj1, adj2):
        # Точки на сторонах, прилегающих к vertex: (vertex, adj1) и (vertex, adj2)
        t1 = _point_on_side(cs, (vertex, adj1), touch_names)
        t2 = _point_on_side(cs, (vertex, adj2), touch_names)
        return t1, t2

    # Определяем, какие точки касания уже заданы как point_on_segment.
    replacements = {}  # touch_id -> (opposite_vertex, s1, s2)

    # Сторона BC напротив A: точка на BC, названная A1/A_1.
    # Сторона CA напротив B: B1/B_1.  Сторона AB напротив C: C1/C_1.
    side_defs = [
        ("BC", A, B, C, ("A1", "A_1")),   # точка на BC напротив A
        ("CA", B, C, A, ("B1", "B_1")),   # на CA напротив B
        ("AB", C, A, B, ("C1", "C_1")),   # на AB напротив C
    ]
    for side_label, opp, s1, s2, names in side_defs:
        t = _point_on_side(cs, (s1, s2), names)
        if t:
            replacements[t] = (opp, s1, s2)

    if not replacements:
        return base_plan

    # Заменяем point_on_segment на incircle_touch (нативная, точная точка касания).
    new_cs = []
    for c in cs:
        if c.get("type") == "point_on_segment" and c.get("id") in replacements:
            tid = c.get("id")
            opp, s1, s2 = replacements[tid]
            new_cs.append({
                "type": "incircle_touch",
                "id": tid,
                "p1": opp, "p2": s1, "p3": s2,
                "label": c.get("label", ""),
                "side": "auto",
            })
        else:
            new_cs.append(c)

    base["constructions"] = new_cs
    return base
