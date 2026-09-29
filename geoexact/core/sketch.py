"""Deterministic last-resort sketch built from the wording alone (no LLM).

Used only when every model attempt failed to produce anything drawable
(refusal, broken JSON, network/budget failure). The sketch recognises the
main figure (triangle, quadrilaterals, regular polygons), points on sides
(ratios, midpoints, even spacing), medians/altitudes/bisectors, named
segments/diagonals, intersections and inscribed/circumscribed circles.

Proportions are conventional; the result is always labelled as a sketch and
never as a verified drawing.
"""
from __future__ import annotations

import math
import re

import numpy as np

from .schema import FigurePlan, PlanError, validate_plan

_P = r"[A-Z](?:_?\d)?"          # point name: A, A1, A_1
_SEG = rf"({_P})({_P})"


def _clean(text: str) -> str:
    t = re.sub(r"\\(?:mathrm|text|operatorname)\s*\{([^{}]*)\}", r"\1", text)
    t = t.replace(r"\angle", "∠").replace("$", "").replace(r"\(", "").replace(r"\)", "")
    t = t.replace("ё", "е").replace("Ё", "Е").replace("–", "—").replace("−", "-")
    # Russian words are matched in lower case; Latin point names keep case.
    t = re.sub(r"[А-Я]", lambda m: m[0].lower(), t)
    return re.sub(r"\s+", " ", t)


def _names(s: str) -> list[str]:
    return re.findall(_P, s)


def _num(s: str) -> float:
    return float(s.replace(",", "."))


_SHAPES = [
    ("square", r"квадрат\w*"),
    ("rectangle", r"прямоугольник\w*"),
    ("rhombus", r"ромб\w*"),
    ("parallelogram", r"параллелограмм\w*"),
    ("trapezoid", r"трапеци\w*"),
    ("quad", r"четырехугольник\w*"),
    ("polygon", r"(?:пяти|шести|восьми|много)угольник\w*"),
    ("triangle", r"(?:треугольник\w*|△|Δ|∆)"),
]


def _base_polygon(t: str):
    for kind, word in _SHAPES:
        m = re.search(rf"{word}\s*((?:{_P}){{3,8}})\b", t)
        if m:
            names = _names(m[1])
            if kind == "triangle" and len(names) != 3:
                continue
            if kind in ("square", "rectangle", "rhombus", "parallelogram",
                        "trapezoid", "quad") and len(names) != 4:
                continue
            return kind, names, m.start()
    # "треугольник со сторонами 3, 4, 5": a figure without point names
    for kind, word in _SHAPES:
        m = re.search(word, t)
        if m:
            n = {"triangle": 3, "polygon": 5}.get(kind, 4)
            m2 = re.match(r"(пяти|шести|восьми)", m[0])
            if m2:
                n = {"пяти": 5, "шести": 6, "восьми": 8}[m2[1]]
            return kind, list("ABCDEFGH"[:n]), m.start()
    return None


def _triangle(t: str, names: list[str]) -> list[tuple[float, float]]:
    a, b, c = names
    low = t.casefold()
    if "равносторонн" in low or "правильн" in low:
        return [(0, 0), (2, 2 * math.sqrt(3)), (4, 0)]
    if "прямоугольн" in low:
        right = None
        m = re.search(rf"прям\w*\s+угл\w*\s+({_P})\b", t)
        m = m or re.search(rf"∠\s*({_P})\s*=\s*90", t)
        m = m or re.search(rf"угол\s+({_P})\s+(?:равен\s+)?(?:=\s*)?90", t)
        if m and m[1] in names:
            right = m[1]
        right = right or c
        others = [n for n in names if n != right]
        pts = {right: (0.0, 0.0), others[0]: (0.0, 3.0), others[1]: (4.0, 0.0)}
        return [pts[n] for n in names]
    if "равнобедренн" in low:
        apex = None
        for m in re.finditer(rf"({_P})({_P})\s*=\s*({_P})({_P})", t):
            common = set(m.group(1, 2)) & set(m.group(3, 4))
            if len(common) == 1 and common <= set(names):
                apex = common.pop()
                break
        m = re.search(rf"основани\w*\s+({_P})({_P})", t)
        if apex is None and m and set(m.group(1, 2)) <= set(names):
            apex = (set(names) - set(m.group(1, 2))).pop()
        apex = apex or b
        others = [n for n in names if n != apex]
        pts = {others[0]: (0.0, 0.0), apex: (2.0, 3.2), others[1]: (4.0, 0.0)}
        return [pts[n] for n in names]
    # a generic, clearly scalene acute triangle
    return [(0.0, 0.0), (1.3, 2.9), (4.4, 0.0)]


def _vertices(kind: str, names: list[str], t: str):
    if kind == "triangle":
        return _triangle(t, names)
    if kind == "square":
        return [(0, 0), (0, 3), (3, 3), (3, 0)]
    if kind == "rectangle":
        return [(0, 0), (0, 2.6), (4.2, 2.6), (4.2, 0)]
    if kind == "rhombus":
        return [(0, 0), (1.5, 2.6), (4.5, 2.6), (3, 0)]
    if kind == "parallelogram":
        return [(0, 0), (1.1, 2.4), (4.7, 2.4), (3.6, 0)]
    if kind == "trapezoid":
        return [(0, 0), (1.1, 2.5), (3.3, 2.5), (4.8, 0)]
    if kind == "quad":
        return [(0, 0), (0.7, 2.6), (3.9, 3.0), (4.6, 0.3)]
    n = len(names)
    return [(2.5 * math.cos(math.pi / 2 + 2 * math.pi * k / n),
             2.5 * math.sin(math.pi / 2 + 2 * math.pi * k / n)) for k in range(n)]


class _Builder:
    def __init__(self):
        self.points: list[str] = []
        self.cons: list[dict] = []
        self.free: list[float] = []
        self.segments: list[list[str]] = []
        self.circles: list[list[str]] = []
        self.hidden: list[str] = []

    def has(self, *names) -> bool:
        return all(n in self.points for n in names)

    def free_point(self, name, xy):
        self.points.append(name)
        self.cons.append({"op": "free_point", "out": name})
        self.free.extend(float(v) for v in xy)

    def add(self, op, out, args, value=None):
        if out in self.points or not self.has(*args) or out in args:
            return False
        c = {"op": op, "out": out, "args": list(args)}
        if value is not None:
            c["value"] = value
        self.points.append(out)
        self.cons.append(c)
        return True

    def seg(self, a, b):
        if a != b and self.has(a, b) and [a, b] not in self.segments \
                and [b, a] not in self.segments:
            self.segments.append([a, b])


def sketch_plan(text: str):
    """Return (FigurePlan, free_values) or None if no figure is recognised."""
    t = _clean(text)
    base = _base_polygon(t)
    B = _Builder()
    if base is None:
        return _simple_sketch(t, B)
    kind, names, _ = base
    for n, xy in zip(names, _vertices(kind, names, t)):
        B.free_point(n, xy)
    for i, n in enumerate(names):
        B.seg(n, names[(i + 1) % len(names)])
    sentences = re.split(r"(?<=[.;!?])\s+", t)

    # --- explicit ratios XP : PY = m : n  -> P on XY
    ratio = {}
    for m in re.finditer(rf"({_P})({_P})\s*:\s*({_P})({_P})\s*=\s*"
                         r"(\d+(?:[.,]\d+)?)\s*:\s*(\d+(?:[.,]\d+)?)", t):
        x, p, p2, y = m.group(1, 2, 3, 4)
        if p == p2 and _num(m[5]) + _num(m[6]) > 0:
            ratio[p] = (x, y, _num(m[5]) / (_num(m[5]) + _num(m[6])))

    # --- midpoints: "M — середина BC", "середина BC — точка M", "M середина"
    mids = {}
    for m in re.finditer(rf"({_P})\s*(?:—|-|,)?\s*(?:это\s+)?середин\w*\s+"
                         rf"(?:сторон\w*\s+|отрезк\w*\s+|основани\w*\s+|диагонал\w*\s+)?{_SEG}", t):
        mids[m[1]] = (m[2], m[3])
    for m in re.finditer(rf"середин\w*\s+(?:сторон\w*\s+|отрезк\w*\s+|основани\w*\s+"
                         rf"|диагонал\w*\s+)?{_SEG}\s*(?:—|-|,)?\s*(?:точк\w*\s+)?({_P})\b", t):
        mids.setdefault(m[3], (m[1], m[2]))
    for m in re.finditer(rf"({_P})\s*,?\s*({_P})\s*(?:—|-)\s*середин\w*\s+"
                         rf"(?:сторон\w*\s+|отрезк\w*\s+)?{_SEG}\s+и\s+{_SEG}", t):
        mids.setdefault(m[1], (m[3], m[4]))
        mids.setdefault(m[2], (m[5], m[6]))

    # --- "на стороне XY ... точки P и Q" / "точка P на стороне XY"
    on_side: dict[str, tuple[str, str]] = {}
    order: dict[tuple[str, str], list[str]] = {}
    for s in sentences:
        for m in re.finditer(rf"на\s+(?:сторон\w*|отрезк\w*|основани\w*|диагонал\w*|"
                             rf"гипотенуз\w*|кат\w*|продолжени\w*\s+сторон\w*)?\s*{_SEG}"
                             rf"[^.;]*?точк\w*\s+((?:{_P})(?:\s*(?:,|и)\s*{_P})*)", s):
            for p in _names(m[3]):
                on_side.setdefault(p, (m[1], m[2]))
                order.setdefault((m[1], m[2]), []).append(p)
        for m in re.finditer(rf"точк\w*\s+((?:{_P})(?:\s*(?:,|и)\s*{_P})*)\s+"
                             rf"(?:лежит\s+|лежат\s+|взят\w*\s+|отмечен\w*\s+)?на\s+"
                             rf"(?:сторон\w*|отрезк\w*|основани\w*|диагонал\w*)\s+{_SEG}", s):
            for p in _names(m[1]):
                on_side.setdefault(p, (m[2], m[3]))
                order.setdefault((m[2], m[3]), []).append(p)

    # --- cevians: "медиана AM", "AH — высота", "биссектриса CD"
    cevians = []
    for m in re.finditer(rf"(медиан|высот|биссектрис)\w*\s+(?:треугольник\w*\s+(?:{_P}){{3}}\s+)?"
                         rf"((?:{_P}{_P})(?:\s*(?:,|и)\s*{_P}{_P})*)", t):
        for v, p in re.findall(rf"({_P})({_P})", m[2]):
            cevians.append((m[1], v, p))
    for m in re.finditer(rf"{_SEG}\s*(?:—|-)\s*(?:его\s+)?(медиан|высот|биссектрис)\w*", t):
        cevians.append((m[3], m[1], m[2]))

    # --- intersections "AD и BE пересекаются в точке O", diagonals of a quad
    inters = []
    for m in re.finditer(rf"{_SEG}\s+и\s+{_SEG}\b[^.;]*?пересекаются\s+в\s+точк\w*\s+({_P})", t):
        inters.append((m[5], (m[1], m[2]), (m[3], m[4])))
    m = re.search(rf"диагонал\w*[^.;]*?пересекаются\s+в\s+точке\s+({_P})", t)
    if m and len(names) == 4 and not any(i[0] == m[1] for i in inters):
        a, b, c, d = names
        inters.append((m[1], (a, c), (b, d)))

    # --- resolve in dependency order
    pending = True
    while pending:
        pending = False
        for p, (x, y, v) in list(ratio.items()):
            if B.add("divide_segment", p, [x, y], v):
                pending = True
        for p, (x, y) in list(mids.items()):
            if B.add("midpoint", p, [x, y]):
                pending = True
        for (x, y), pts in order.items():
            free = [p for p in pts if p not in B.points and p not in ratio and p not in mids]
            k = len(free)
            for i, p in enumerate(free):
                if B.add("divide_segment", p, [x, y], (i + 1) / (k + 1)):
                    pending = True
        for kind_, v, p in cevians:
            if p in B.points or v not in names or len(names) != 3:
                continue
            a, b = [n for n in names if n != v]
            op = {"медиан": "midpoint", "высот": "foot",
                  "биссектрис": "bisector_point"}[kind_]
            args = [a, b] if op == "midpoint" else [v, a, b]
            if B.add(op, p, args):
                pending = True
        for o, (a, b), (c, d) in inters:
            if o not in B.points and B.has(a, b, c, d):
                if B.add("line_intersect", o, [a, b, c, d]):
                    pending = True

    for kind_, v, p in cevians:
        B.seg(v, p)
    for o, (a, b), (c, d) in inters:
        B.seg(a, b), B.seg(c, d)
    for x, y in list(on_side.values()) + list(mids.values()) + \
            [(x, y) for x, y, _ in ratio.values()]:
        B.seg(x, y)

    # named segments / diagonals / lines
    for m in re.finditer(rf"(?:отрез\w*|диагонал\w*|прям\w*|луч\w*|хорд\w*|"
                         rf"медиан\w*|высот\w*|биссектрис\w*)\s+((?:{_P}{_P})(?:\s*(?:,|и)\s*{_P}{_P})*)", t):
        for seg in re.findall(rf"({_P})({_P})", m[1]):
            B.seg(*seg)

    # circles for triangles
    low = t.casefold()
    if len(names) == 3:
        a, b, c = names
        named = re.search(rf"центр\w*\s+(?:в\s+точк\w*\s+)?({_P})", t)
        incircle = re.search(r"(?<!о)вписан\w*\s+(?:\w+\s+)?окружност|окружност\w*\s*,?\s*вписан", low)
        if re.search(r"описан\w*\s+(?:\w+\s+)?окружност|окружност\w*\s*,?\s*описан"
                     r"|в\s+окружност\w*[^.;]*вписан|вписан\w*\s+в\s+окружност", low) or (
                named and "окружност" in low and not incircle):
            o = next((n for n in ((named[1],) if named and not incircle else ())
                      + ("O", "O_1", "Q") if n not in B.points), None)
            if o and B.add("circumcenter", o, [a, b, c]):
                B.circles.append([o, a])
        if incircle:
            i = next((n for n in ((named[1],) if named else ()) + ("I", "O", "J")
                      if n not in B.points), None)
            if i and B.add("incenter", i, [a, b, c]):
                foot = "T_" + i
                if B.add("foot", foot, [i, b, c]):
                    B.hidden.append(foot)
                    B.circles.append([i, foot])

    return _finish(B, cevians if len(names) == 3 else [], names)


def _finish(B: "_Builder", cevians=(), names=()):
    right = []
    for kind_, v, p in cevians:
        if kind_ == "высот" and len(names) == 3:
            a = next(n for n in names if n != v)
            right.append([v, p, a])
    try:
        plan = FigurePlan.from_dict({
            "points": B.points,
            "constructions": B.cons,
            "constraints": [],
            "draw": {"segments": B.segments, "circles": B.circles,
                     "right_angles": right, "hide_labels": B.hidden},
            "target": {"kind": "none", "args": []},
            "scale_free": True,
            "notes": "Схематичный чертёж по ключевым словам условия.",
        })
        validate_plan(plan)
    except PlanError:
        return None
    return plan, np.array(B.free, dtype=float)


def _simple_sketch(t: str, B: "_Builder"):
    """Circles, a single angle or a segment when there is no polygon."""
    centers = []
    for m in re.finditer(rf"центр\w*\s+(?:в\s+точк\w*\s+)?((?:{_P})(?:\s*(?:,|и)\s*{_P})*)", t):
        centers.extend(n for n in _names(m[1]) if n not in centers)
    if "окружност" in t and centers:
        for k, c in enumerate(centers[:3]):
            B.free_point(c, (3.2 * k, 0.0))
        for k, c in enumerate(centers[:3]):
            r = f"R_{c}"
            B.free_point(r, (3.2 * k, 2.0))   # radius witness, label hidden
            B.circles.append([c, r])
            B.hidden.append(r)
        if len(centers) >= 2:
            B.seg(centers[0], centers[1])
        chords = re.findall(rf"({_P})({_P})", " ".join(
            m[1] for m in re.finditer(rf"(?:хорд\w*|диаметр\w*)\s+((?:{_P}{_P})(?:\s*(?:,|и)\s*{_P}{_P})*)", t)))
        c0 = centers[0]
        angles = iter((160, 10, 100, 250, 60, 300, 200, 340))
        for a, b in chords[:4]:
            for n in (a, b):
                if n not in B.points:
                    th = math.radians(next(angles, 0))
                    B.free_point(n, (2.0 * math.cos(th), 2.0 * math.sin(th)))
            B.seg(a, b)
        m = re.search(rf"пересекаются\s+в\s+точк\w*\s+({_P})", t)
        if m and len(chords) >= 2:
            (a, b), (c, d) = chords[:2]
            B.add("line_intersect", m[1], [a, b, c, d])
        return _finish(B)
    m = re.search(rf"уг(?:о)?л\w*\s+({_P})({_P})({_P})\b", t)
    if m:
        a, o, b = m.group(1, 2, 3)
        if len({a, o, b}) == 3:
            B.free_point(o, (0.0, 0.0))
            B.free_point(a, (4.0, 0.0))
            B.free_point(b, (1.6, 3.0))
            B.seg(o, a), B.seg(o, b)
            return _finish(B)
    m = re.search(rf"отрез\w*\s+({_P})({_P})", t)
    if m and m[1] != m[2]:
        B.free_point(m[1], (0.0, 0.0))
        B.free_point(m[2], (4.0, 0.0))
        B.seg(m[1], m[2])
        return _finish(B)
    return None
