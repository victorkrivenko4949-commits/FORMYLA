"""Auxiliary constructions on top of an already verified figure.

The main figure is built and checked first. The auxiliary layer is a small,
separate step, so a weak model answer can no longer leave the "with auxiliary
constructions" mode empty:

1. a deterministic rule for the classical trapezoid-diagonals construction;
2. otherwise the model is asked only for the auxiliary steps, in a tiny
   whitelisted language (new points from exact operations on existing ones);
3. every step is executed by the engine, checked (finite, not degenerate,
   near the figure) and only then drawn. Equal-length ticks are added only
   for equalities that follow from the operation itself and hold numerically.

Nothing here changes the main figure or any verified point.
"""
from __future__ import annotations

import copy
import math
import re

import numpy as np

from .constructions import OPS
from .schema import Construction

# op -> (number of point arguments, needs numeric value)
ALLOWED = {
    "midpoint": (2, False), "divide_segment": (2, True), "reflect_point": (2, False),
    "translate": (3, False), "parallel_point": (3, True), "line_intersect": (4, False),
    "foot": (3, False), "homothety": (2, True), "rotate": (2, True),
    "circumcenter": (3, False), "incenter": (3, False), "centroid": (3, False),
    "orthocenter": (3, False),
}
MAX_NEW_POINTS = 6
_NAME = re.compile(r"^[A-Z](?:_?\d{1,2})?$")

OP_DOC = """Разрешённые операции (out — НОВОЕ имя точки, args — уже существующие точки):
midpoint(A,B) — середина AB;
divide_segment(A,B,value=t) — точка A+t·(B−A) (t>1 даёт продолжение за B);
reflect_point(A,O) — точка, симметричная A относительно точки O;
translate(A,B,C) — A+(C−B), то есть A, сдвинутая на вектор BC;
parallel_point(A,B,C,value=k) — A+k·(C−B);
line_intersect(A,B,C,D) — пересечение прямых AB и CD;
foot(P,A,B) — основание перпендикуляра из P на прямую AB;
homothety(A,O,value=k) — O+k·(A−O);
rotate(A,O,value=градусы) — поворот A вокруг O против часовой стрелки;
circumcenter(A,B,C), incenter(A,B,C), centroid(A,B,C), orthocenter(A,B,C)."""

SYS_AUXPLAN = """Ты помогаешь оформить чертёж школьной или олимпиадной геометрической задачи.
Основной чертёж по условию УЖЕ построен и проверен. Твоя задача — ТОЛЬКО указать
дополнительное построение, которое сделал бы хороший учитель при решении: то, что
сводит задачу к известной конфигурации (параллельный перенос диагонали или стороны,
удвоение медианы, параллельная прямая через точку, продолжение стороны, симметрия,
высота, средняя линия, описанная окружность и т. п.).

""" + OP_DOC + """

Верни ТОЛЬКО JSON:
{"idea": "одна строка по-русски: зачем это построение",
 "steps": [{"op": "translate", "out": "E", "args": ["D","B","C"]}],
 "aux_segments": [["C","E"]],
 "aux_extensions": [["A","D"]],
 "aux_lines": [],
 "aux_circles": [["O","A"]]}

Правила:
1. Не больше 6 новых точек; имена — заглавные латинские буквы, которых ещё нет на чертеже.
2. Используй только точки, которые есть в описании чертежа, и точки, созданные выше.
3. aux_segments — ВСЕ отрезки нового построения, в том числе продолжения сторон и
   медиан: продолжение AM за M до новой точки D задаётся отрезком [M,D]. aux_extensions
   не используй. aux_circles [центр, точка на окружности].
4. Не дублируй уже нарисованное. Если для решения дополнительное построение НЕ нужно,
   верни {"idea": "", "steps": []}.
5. Не пиши решение и ответ, не выдумывай данных, только построение."""


def describe_figure(plan, coords) -> str:
    lines = ["Точки чертежа (имя: способ построения):"]
    by_out = {c.out: c for c in plan.constructions if c.out}
    for name in plan.points:
        if name in plan.draw.hide_labels or name not in coords:
            continue
        c = by_out.get(name)
        how = "свободная" if c is None or c.op == "free_point" else f"{c.op}({', '.join(c.args)})"
        lines.append(f"{name}: {how}")
    if plan.draw.segments:
        lines.append("Нарисованы отрезки: " + ", ".join("".join(s) for s in plan.draw.segments))
    if plan.draw.circles:
        lines.append("Окружности [центр, точка]: " + ", ".join("".join(c) for c in plan.draw.circles))
    return "\n".join(lines)


def has_aux(plan) -> bool:
    d = plan.draw
    return bool(d.aux_segments or d.aux_lines or d.aux_rays or d.aux_extensions or d.aux_circles)


# ---------------------------------------------------------------- deterministic

def trapezoid_diagonals(plan, coords, text: str) -> dict | None:
    """Classical step: translate a diagonal by a base, giving a triangle with
    sides = both diagonals and the sum of the bases (also the midline*2)."""
    t = text.lower()
    if "трапец" not in t or "диагонал" not in t:
        return None
    m = re.search(r"трапеци\w*\s+([A-Z])([A-Z])([A-Z])([A-Z])(?![A-Za-z])", text, re.I)
    if not m:
        return None
    a, b, c, d = (g.upper() for g in m.groups())
    if not all(n in coords for n in (a, b, c, d)) or len({a, b, c, d}) != 4:
        return None
    bases = re.search(r"основани\w*\s+([A-Z])([A-Z])\s+и\s+([A-Z])([A-Z])", text, re.I)
    order = None
    if bases:
        s1, s2 = frozenset(x.upper() for x in bases.group(1, 2)), frozenset(x.upper() for x in bases.group(3, 4))
        if {s1, s2} == {frozenset((a, d)), frozenset((b, c))}:
            order = (a, b, c, d)
        elif {s1, s2} == {frozenset((a, b)), frozenset((c, d))}:
            order = (b, c, d, a)
    if order is None:
        # bases from the geometry: a pair of opposite sides that is parallel
        P = {n: np.asarray(coords[n], float) for n in (a, b, c, d)}
        cross = lambda u, v: abs(u[0] * v[1] - u[1] * v[0])
        scale = max(np.linalg.norm(P[x] - P[y]) for x in P for y in P) ** 2
        if cross(P[d] - P[a], P[c] - P[b]) < 1e-7 * scale:
            order = (a, b, c, d)
        elif cross(P[b] - P[a], P[d] - P[c]) < 1e-7 * scale:
            order = (b, c, d, a)
    if order is None:
        return None
    v0, v1, v2, v3 = order
    e = next((n for n in "EFGHKLMNPQ" if n not in coords and n not in plan.points), None)
    if e is None:
        return None
    return {"idea": f"Сдвиг диагонали {v1}{v3} на {v1}{v2}: треугольник {v0}{v2}{e} со сторонами, "
                    f"равными диагоналям и сумме оснований.",
            "steps": [{"op": "translate", "out": e, "args": [v3, v1, v2]}],
            "aux_segments": [[v2, e], [v3, e]], "aux_extensions": [], "aux_lines": [],
            "aux_circles": [], "_expect_collinear": [v0, v3, e]}


# ---------------------------------------------------------------- validation / apply

def _pair_list(value, known, limit=8):
    out = []
    for item in value if isinstance(value, list) else []:
        if (isinstance(item, list) and len(item) == 2 and all(isinstance(n, str) for n in item)
                and all(n in known for n in item) and item[0] != item[1]):
            out.append(list(item))
    return out[:limit]


def apply_aux(plan, coords: dict, data) -> tuple | None:
    """Validate and execute an auxiliary plan. Returns (plan, coords) or None."""
    if not isinstance(data, dict) or not isinstance(data.get("steps"), list) or not data["steps"]:
        return None
    if len(data["steps"]) > MAX_NEW_POINTS:
        return None
    known = {k: np.asarray(v, float) for k, v in coords.items()}
    pts = np.array(list(known.values()))
    span = float(np.max(np.ptp(pts, axis=0))) if len(pts) else 0.0
    if span <= 1e-9:
        return None
    centre = pts.mean(axis=0)
    new: list[Construction] = []
    for step in data["steps"]:
        if not isinstance(step, dict):
            return None
        op, out, args = step.get("op"), step.get("out"), step.get("args")
        value = step.get("value")
        if op not in ALLOWED or not isinstance(out, str) or not _NAME.match(out) \
                or out in known or out in plan.points or not isinstance(args, list):
            return None
        need, needs_value = ALLOWED[op]
        if len(args) != need or not all(isinstance(a, str) and a in known for a in args):
            return None
        if needs_value:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                return None
            if op == "divide_segment" and not -3 <= value <= 4:
                return None
            if op in ("parallel_point", "homothety") and not -4 <= value <= 4:
                return None
        else:
            value = None
        try:
            p = np.asarray(OPS[op](*[known[a] for a in args], value=value), dtype=float).reshape(2)
        except Exception:  # noqa: BLE001 - degenerate step
            return None
        if not np.all(np.isfinite(p)) or float(np.linalg.norm(p - centre)) > 3.0 * span:
            return None
        if any(float(np.linalg.norm(p - q)) < 1e-6 * span for q in known.values()):
            return None                      # coincides with an existing point
        known[out] = p
        new.append(Construction(op=op, out=out, args=list(args),
                                value=float(value) if value is not None else None))

    names = set(known)
    segments = _pair_list(data.get("aux_segments"), names)
    extensions = _pair_list(data.get("aux_extensions"), names)
    # A continuation "PQ beyond Q up to a new point R" is just the segment QR.
    for p, q in extensions:
        for c in new:
            r = known[c.out]
            d = known[q] - known[p]
            v = r - known[q]
            if float(d @ v) > 0 and abs(d[0] * v[1] - d[1] * v[0]) <= 1e-7 * float(d @ d) ** 0.5 * span:
                segments.append([q, c.out])
    extensions = []
    # The continuation created by a reflection or an extension must be visible.
    for c in new:
        if c.op == "reflect_point":
            segments.append([c.args[1], c.out])
        elif c.op == "divide_segment" and (c.value or 0) > 1:
            segments.append([c.args[1], c.out])
    lines = _pair_list(data.get("aux_lines"), names, 4)
    circles = _pair_list(data.get("aux_circles"), names, 2)
    if not (segments or extensions or lines or circles):
        return None
    expect = data.get("_expect_collinear")
    if expect:
        a, b, c = (known[n] for n in expect)
        d = b - a
        if abs(d[0] * (c - a)[1] - d[1] * (c - a)[0]) > 2e-2 * float(d @ d) ** 0.5 * span:
            return None

    plan = copy.deepcopy(plan)
    draw = plan.draw
    for c in new:
        plan.points.append(c.out)
        plan.constructions.append(c)
    used = {n for grp in (segments, extensions, lines, circles) for pr in grp for n in pr}
    for c in new:
        if c.out in used:
            draw.aux_points.append(c.out)
        else:
            draw.hide_labels.append(c.out)
    have = {frozenset(s) for s in draw.segments + draw.aux_segments}
    for s in segments:
        if frozenset(s) not in have:
            draw.aux_segments.append(s)
            have.add(frozenset(s))
    draw.aux_extensions += [e for e in extensions if e not in draw.aux_extensions]
    draw.aux_lines += lines
    draw.aux_circles += circles
    if data.get("idea") and isinstance(data["idea"], str) and not plan.notes:
        plan.notes = data["idea"][:300]
    _verified_ticks(plan, known, new)
    return plan, known


def _verified_ticks(plan, coords, new) -> None:
    """Equal-length ticks for equalities implied by the operation, if they hold."""
    d = plan.draw
    used = {m.get("count", 1) for m in d.equal_marks}
    pairs: list[list[tuple[str, str]]] = []
    for c in new:
        a = c.args
        if c.op in ("translate", "parallel_point") and (c.op == "translate" or c.value == 1.0):
            pairs.append([(a[0], a[1]), (c.out, a[2])])      # the translated segment first
            pairs.append([(a[1], a[2]), (a[0], c.out)])
        elif c.op == "midpoint":
            pairs.append([(a[0], c.out), (c.out, a[1])])
        elif c.op == "reflect_point":
            pairs.append([(a[1], a[0]), (a[1], c.out)])
    length = lambda p: float(np.linalg.norm(coords[p[0]] - coords[p[1]]))
    for group in pairs:
        if any(p[0] not in coords or p[1] not in coords for p in group):
            continue
        if max(length(p) for p in group) - min(length(p) for p in group) > 1e-6 * max(length(p) for p in group):
            continue
        # both segments must be visible to carry a mark
        visible = {frozenset(s) for f in ("segments", "aux_segments") for s in getattr(d, f)}
        if not all(frozenset(p) in visible for p in group):
            continue
        labelled = [m for m in d.length_marks if m.get("text")
                    and any(frozenset(m["pts"]) == frozenset(p) for p in group)]
        if labelled:
            # a segment already carries its length: its copy gets the same label
            text = labelled[0]["text"]
            for p in group:
                if not any(frozenset(m["pts"]) == frozenset(p) for m in d.length_marks + d.equal_marks):
                    d.length_marks.append({"pts": list(p), "text": text, "layer": "aux"})
            continue
        if any(frozenset(m["pts"]) == frozenset(p) for m in d.equal_marks + d.length_marks
               for p in group):
            continue
        count = next((n for n in (1, 2, 3) if n not in used), None)
        if count is None:
            return
        used.add(count)
        for p in group:
            d.equal_marks.append({"pts": list(p), "count": count, "layer": "aux"})
