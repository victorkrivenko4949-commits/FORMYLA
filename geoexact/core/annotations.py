"""Enrich a solved 2D figure with verified equality marks and exterior bisectors.

Do not infer equality from a visually symmetric random drawing. Only named
constraints and exact constructions are eligible, and every mark is checked
against the actual solved coordinates before being attached.
"""
from __future__ import annotations

import copy
import math
import re

import numpy as np

from .gates import _angle_deg


def _pts(mark):
    return list(mark["pts"]) if isinstance(mark, dict) else list(mark)


def _ray_key(coords, vertex, toward):
    d = coords[toward] - coords[vertex]
    n = float(np.linalg.norm(d))
    if n <= 1e-12:
        return None
    d = d / n
    return (vertex, round(float(d[0]), 6), round(float(d[1]), 6))


def dedupe_right_angles(draw, coords) -> None:
    """Два прямых угла при одной точке по обе стороны от одной прямой (∠AFC и ∠CFB
    у основания высоты F) рисуются двумя квадратиками и сливаются в прямоугольник
    «насквозь». Факт один — перпендикуляр — и квадратик нужен один."""
    kept: list = []
    seen_rays: list[tuple] = []
    for mark in draw.right_angles:
        pts = _pts(mark)
        if len(pts) != 3 or any(p not in coords for p in pts):
            kept.append(mark)
            continue
        a, v, b = pts
        ka, kb = _ray_key(coords, v, a), _ray_key(coords, v, b)
        if ka is None or kb is None:
            kept.append(mark)
            continue
        duplicate = False
        for (v2, ra, rb) in seen_rays:
            if v2 != v:
                continue
            rays = {ra, rb}
            # общий луч и противоположный второй — тот же перпендикуляр
            def opposite(k1, k2):
                return abs(k1[1] + k2[1]) < 1e-5 and abs(k1[2] + k2[2]) < 1e-5
            if (ka in rays and any(opposite(kb, r) for r in rays)) or \
                    (kb in rays and any(opposite(ka, r) for r in rays)):
                duplicate = True
                break
            if ka in rays and kb in rays:
                duplicate = True
                break
        if duplicate:
            continue
        seen_rays.append((v, ka, kb))
        kept.append(mark)
    draw.right_angles[:] = kept


def mark_perpendiculars(draw, coords, *, limit: int = 4) -> int:
    """Проверенные прямые углы между нарисованными отрезками.

    Серединный перпендикуляр OM к стороне BC, высота, касательная к радиусу —
    если два нарисованных отрезка действительно перпендикулярны (не «почти», а
    точно, с невязкой 1e-9) и имеют общую точку (общий конец или конец одного
    лежит на другом), ставится один квадратик. Углы, уже отмеченные при этой
    вершине вдоль этих лучей, не дублируются.
    """
    segs = [list(s) for s in list(draw.segments) + list(draw.aux_segments)
            if len(s) == 2 and s[0] != s[1] and all(p in coords for p in s)]
    marked: set = set()
    for group in (draw.right_angles, draw.angle_marks):
        for mark in group:
            pts = _pts(mark)
            if len(pts) == 3 and all(p in coords for p in pts):
                for end in (pts[0], pts[2]):
                    key = _ray_key(coords, pts[1], end)
                    if key is not None:
                        marked.add(key)

    def unit(p, q):
        d = coords[q] - coords[p]
        n = float(np.linalg.norm(d))
        return None if n <= 1e-12 else d / n

    added = 0
    for p, q in segs:
        for vertex, other in ((q, p), (p, q)):
            u = unit(vertex, other)
            if u is None:
                continue
            for a, b in segs:
                if {a, b} == {p, q}:
                    continue
                w = unit(a, b)
                if w is None or abs(float(np.dot(u, w))) > 1e-9:
                    continue
                if vertex in (a, b):
                    far = b if vertex == a else a
                else:
                    # конец одного отрезка лежит строго внутри другого
                    ab = coords[b] - coords[a]
                    length = float(np.linalg.norm(ab))
                    rel = coords[vertex] - coords[a]
                    t = float(np.dot(rel, ab)) / (length * length)
                    off = abs(float(ab[0] * rel[1] - ab[1] * rel[0])) / length
                    if not (0.02 < t < 0.98) or off > 1e-9 * length:
                        continue
                    far = b if t < 0.5 else a
                k_other = _ray_key(coords, vertex, other)
                k_far = _ray_key(coords, vertex, far)
                k_near = _ray_key(coords, vertex, a if far == b else b) if vertex not in (a, b) else None
                if k_other in marked or k_far in marked or (k_near is not None and k_near in marked):
                    continue
                if abs(_angle_deg(coords[other], coords[vertex], coords[far]) - 90.0) > 1e-6:
                    continue
                draw.right_angles.append([other, vertex, far])
                marked.update(k for k in (k_other, k_far, k_near) if k is not None)
                added += 1
                if added >= limit:
                    return added
    return added


def enrich_annotations(plan, solution, *, with_aux: bool, problem_text: str = ""):
    plan = copy.deepcopy(plan)
    draw = plan.draw
    coords = {name: np.asarray(value, dtype=float) for name, value in solution.coords.items()}
    used_lengths = {m.get("count", 1) for m in draw.equal_marks}
    used_angles = {m["count"] for m in draw.angle_marks if "count" in m}

    def next_count(used):
        count = next((n for n in (1, 2, 3) if n not in used), None)
        if count is not None:
            used.add(count)
        return count

    def length(pair):
        return float(np.linalg.norm(coords[pair[0]] - coords[pair[1]]))

    def group_lengths(pairs, *, layer="main"):
        unique = list(dict.fromkeys(frozenset(pair) for pair in pairs))
        if len(unique) < 2 or any(len(pair) != 2 for pair in unique):
            return
        lengths = [length(tuple(pair)) for pair in unique]
        if min(lengths) <= 1e-10 or max(lengths) - min(lengths) > 1e-5 * max(lengths):
            return
        # Existing marks take precedence. Do not put two different symbols on
        # a single segment, e.g. the midpoint WI=WI_A already marked by WB=WC.
        if any(set(m["pts"]) == pair for pair in unique for m in draw.equal_marks):
            return
        count = next_count(used_lengths)
        if count is None:
            return
        for pair in pairs:
            if frozenset(pair) in unique:
                mark = {"pts": list(pair), "count": count}
                if layer == "aux":
                    mark["layer"] = "aux"
                draw.equal_marks.append(mark)
                unique.remove(frozenset(pair))

    def group_angles(marks, *, layer="main"):
        values = []
        for m in marks:
            a, b, c = m["pts"]
            value = _angle_deg(coords[a], coords[b], coords[c])
            if m.get("reverse_first"):
                value = 180 - value
            values.append(value)
        if (not all(math.isfinite(v) and 0.1 < v < 179.9 for v in values)
                or max(values) - min(values) > 0.01):
            return False
        if any(any(old["pts"] == m["pts"] and
                   old.get("reverse_first", False) == m.get("reverse_first", False)
                   and "count" in old for old in draw.angle_marks) for m in marks):
            return False
        count = next_count(used_angles)
        if count is None:
            return False
        for m in marks:
            draw.angle_marks.append({**m, "count": count, "layer": layer})
        return True

    # Named equalities from constraints, including chains AB=AC=BC.
    length_groups: list[set[frozenset[str]]] = []
    for constraint in plan.constraints:
        if constraint.type == "dist_eq" and all(n in coords for n in constraint.args):
            left, right = map(frozenset, (constraint.args[:2], constraint.args[2:]))
            merged = {left, right}
            retained = []
            for group in length_groups:
                if merged & group:
                    merged |= group
                else:
                    retained.append(group)
            length_groups = retained + [merged]
    for group in length_groups:
        pairs = [sorted(p) for p in sorted(group, key=lambda p: sorted(p))]
        group_lengths(pairs)

    # Named polygons have defining equalities even when an analytic template
    # expresses them by construction rather than dist_eq constraints.
    figure = re.search(r"\b(ромб|квадрат|прямоугольник|параллелограмм)\s+([A-Z]{4})\b",
                       problem_text, re.I)
    if figure:
        vertices = figure[2].upper()
        if len(set(vertices)) == 4 and all(n in coords for n in vertices):
            sides = [[vertices[i], vertices[(i + 1) % 4]] for i in range(4)]
            if figure[1].casefold() in ("ромб", "квадрат"):
                group_lengths(sides)
            else:
                group_lengths([sides[0], sides[2]])
                group_lengths([sides[1], sides[3]])

    if with_aux:
        for center, radius_point in draw.circles:
            if center not in coords or radius_point not in coords:
                continue
            radius = length([center, radius_point])
            radii = []
            for a, b in draw.aux_segments:
                if a == center or b == center:
                    target = b if a == center else a
                    if target in coords and abs(length([center, target]) - radius) <= 1e-5 * radius:
                        radii.append([center, target])
            if len(radii) >= 2:
                group_lengths(radii, layer="aux")

    for constraint in plan.constraints:
        if constraint.type == "angle_eq" and all(n in coords for n in constraint.args):
            group_angles([{"pts": constraint.args[:3]},
                          {"pts": constraint.args[3:]}])

    # Exterior bisectors are more informative than redundant interior ones
    # when both an incenter and an excenter are present in a dense diagram.
    constructions = sorted(plan.constructions, key=lambda c: c.op != "excenter")
    for construction in constructions:
        if construction.out not in coords or any(n not in coords for n in construction.args):
            continue
        if construction.op == "midpoint":
            a, b = construction.args
            halves = [[a, construction.out], [construction.out, b]]
            main_edges = {frozenset(pair) for pair in draw.segments}
            if construction.out not in draw.hide_labels and (
                    with_aux or all(frozenset(pair) in main_edges for pair in halves)):
                group_lengths(halves, layer="aux" if with_aux and not all(
                    frozenset(pair) in main_edges for pair in halves) else "main")
        if not with_aux:
            continue
        if construction.op == "incenter":
            a, b, c = construction.args
            center = construction.out
            for vertex, left, right in ((a, b, c), (b, a, c), (c, a, b)):
                if any(m["pts"][1] == vertex and "count" in m for m in draw.angle_marks):
                    continue
                marks = [{"pts": [left, vertex, center]},
                         {"pts": [center, vertex, right]}]
                if group_angles(marks, layer="aux"):
                    support = [vertex, center]
                    if support not in draw.aux_segments and support[::-1] not in draw.aux_segments:
                        draw.aux_segments.append(support)
        if construction.op == "excenter":
            tri = construction.args
            opposite = tri[int(construction.value)]
            center = construction.out
            for vertex in tri:
                if vertex == opposite:
                    continue
                other = next(n for n in tri if n not in (opposite, vertex))
                marks = [
                    {"pts": [opposite, vertex, center], "reverse_first": True},
                    {"pts": [center, vertex, other]},
                ]
                if group_angles(marks, layer="aux"):
                    support = [vertex, center]
                    if support not in draw.aux_segments and support[::-1] not in draw.aux_segments:
                        draw.aux_segments.append(support)
                    extension = [opposite, vertex]
                    if extension not in draw.aux_extensions:
                        draw.aux_extensions.append(extension)

    # Перпендикуляры между нарисованными отрезками (серединный перпендикуляр OM,
    # высота, радиус к касательной) — один квадратик на факт, без дублей по обе
    # стороны от прямой.
    try:
        dedupe_right_angles(draw, coords)
        mark_perpendiculars(draw, coords)
        dedupe_right_angles(draw, coords)
    except Exception:  # noqa: BLE001 - отметки не должны ронять построение
        pass
    return plan
