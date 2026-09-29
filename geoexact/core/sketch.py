"""Deterministic last-resort sketch built from the wording alone (no LLM).

Used only when every model attempt failed to produce anything drawable
(refusal, broken JSON, network/budget failure, impossible condition). The
sketch recognises the main figure and the most common school relations:

* triangles (right, isosceles, equilateral), quadrilaterals, regular polygons,
  circles with named or implicit centres, a single angle or segment;
* points on sides / segments / extensions (ratios, midpoints, even spacing);
* medians, altitudes, bisectors (also of polygon angles), midlines;
* intersections of named segments, diagonals, cevians through a point;
* circumscribed / inscribed circles, chords, diameters, tangents.

Every point is produced by an exact construction, so each recognised
relation holds exactly on the sketch; only unrecognised metric data (lengths,
angles) is conventional. The result is always labelled as a sketch.
"""
from __future__ import annotations

import math
import re

import numpy as np

from .schema import FigurePlan, PlanError, validate_plan

_P0 = r"[A-Z](?:_?\d{1,2})?"
_P = rf"{_P0}(?![A-Za-z0-9_])"   # A, A1, A_1 (single point name)
_PP = r"[A-Z](?:_?\d{1,2})?[A-Z](?:_?\d{1,2})?(?![A-Za-z0-9_])"
_LIST_P = rf"{_P}(?:\s*(?:,|и)\s*{_P})*"
_LIST_PP = rf"{_PP}(?:\s*(?:,|и)\s*{_PP})*"
_SIDE = r"(?:сторон\w*|отрезк\w*|основани\w*|диагонал\w*|гипотенуз\w*|кат\w*|хорд\w*|луч\w*|прям\w*)"


def _clean(text: str) -> str:
    t = re.sub(r"\\(?:mathrm|text|operatorname|mathit)\s*\{([^{}]*)\}", r"\1", text)
    t = re.sub(r"\\(?:angle|measuredangle)", "∠", t)
    t = re.sub(r"\^\s*\{?\\circ\}?", "°", t)
    t = re.sub(r"\\(?:parallel)", "∥", t)
    t = re.sub(r"\\(?:perp)", "⊥", t)
    t = re.sub(r"[_]\{(\d{1,2})\}", r"_\1", t)                 # A_{1} -> A_1
    t = re.sub(r"\\[()\[\]]|\$", " ", t)
    t = re.sub(r"[\u0000-\u0008\u000b-\u001f\u200b-\u200f\u2060\ufeff]", "", t)
    t = t.replace("ё", "е").replace("Ё", "Е").replace("–", "—").replace("−", "-")
    # Russian words are matched in lower case; Latin point names keep case.
    t = re.sub(r"[А-Я]", lambda m: m[0].lower(), t)
    t = t.replace("δ", "Δ")
    return re.sub(r"\s+", " ", t).strip()


def _names(s: str) -> list[str]:
    return re.findall(_P, s)


def _pairs(s: str) -> list[tuple[str, str]]:
    out = []
    for pp in re.findall(_PP, s):
        a = re.match(r"[A-Z](?:_?\d{1,2})?", pp)[0]
        out.append((a, pp[len(a):]))
    return out


def _num(s: str) -> float:
    return float(s.replace(",", "."))


_SHAPES = [
    ("square", r"квадрат\w*"),
    ("rectangle", r"прямоугольник\w*"),
    ("rhombus", r"ромб\w*"),
    ("parallelogram", r"параллелограмм\w*"),
    ("trapezoid", r"трапеци\w*"),
    ("quad", r"четырехугольник\w*"),
    ("polygon", r"(?:пяти|шести|семи|восьми|много)угольник\w*"),
    ("triangle", r"(?:треугольник\w*|△|Δ|∆)"),
]
_SIZE = {"square": 4, "rectangle": 4, "rhombus": 4, "parallelogram": 4,
         "trapezoid": 4, "quad": 4, "triangle": 3}


def _base_polygon(t: str):
    for kind, word in _SHAPES:
        for m in re.finditer(rf"{word}\s*((?:{_P0}){{3,8}})(?![A-Za-z0-9_])", t):
            names = _names_run(m[1])
            if kind in _SIZE and len(names) != _SIZE[kind]:
                continue
            if len(set(names)) != len(names):
                continue
            return kind, names
    # "треугольник со сторонами 3, 4, 5": a figure without point names
    for kind, word in _SHAPES:
        m = re.search(word, t)
        if m:
            n = _SIZE.get(kind, 5)
            m2 = re.match(r"(пяти|шести|семи|восьми)", m[0])
            if m2:
                n = {"пяти": 5, "шести": 6, "семи": 7, "восьми": 8}[m2[1]]
            return kind, list("ABCDEFGH"[:n])
    return None


def _names_run(s: str) -> list[str]:
    return re.findall(r"[A-Z](?:_?\d{1,2})?", s)


def _triangle(t: str, names: list[str]) -> list[tuple[float, float]]:
    a, b, c = names
    sides = {frozenset(pq) for pq in [(a, b), (b, c), (a, c)]}
    eq_sides = set()
    for m in re.finditer(rf"({_PP}(?:\s*=\s*{_PP})+)", t):
        group = {frozenset(pq) for pq in _pairs(m[1])} & sides
        if len(group) >= 2:
            eq_sides |= group
    if len(eq_sides) == 3:
        t = t + " равносторонний"
    elif len(eq_sides) == 2 and "равнобедренн" not in t:
        t = t + " равнобедренный"
    if re.search(rf"(?:∠\s*(?:(?:{_P0}){{1,2}})?{_P0}\s*=\s*90|прям\w*\s+угл|угол\s+{_P0}\s+(?:равен\s+)?90)", t):
        t = t + " прямоугольный"
    if re.search(r"равносторонн|правильн", t):
        return [(0, 0), (2, 2 * math.sqrt(3)), (4, 0)]
    if re.search(r"прямоугольн", t):
        right = None
        for pat in (rf"прям\w*\s+угл\w*\s+({_P})", rf"∠\s*({_P})\s*=\s*90",
                    rf"угол\s+({_P})\s+(?:равен\s+|=\s*)?90",
                    rf"∠\s*{_P0}({_P0}){_P0}\s*=\s*90"):
            m = re.search(pat, t)
            if m and m[1] in names:
                right = m[1]
                break
        m = re.search(rf"гипотенуз\w*\s+({_PP})", t)
        if right is None and m:
            hyp = set(_pairs(m[1])[0])
            if hyp <= set(names):
                right = (set(names) - hyp).pop()
        right = right or c
        others = [n for n in names if n != right]
        pts = {right: (0.0, 0.0), others[0]: (0.0, 3.0), others[1]: (4.0, 0.0)}
        return [pts[n] for n in names]
    if "равнобедренн" in t:
        apex = None
        for m in re.finditer(rf"({_PP})\s*=\s*({_PP})", t):
            (p, q), (r, s) = _pairs(m[1])[0], _pairs(m[2])[0]
            common = {p, q} & {r, s}
            if len(common) == 1 and common <= set(names):
                apex = common.pop()
                break
        m = re.search(rf"основани\w*\s+({_PP})", t)
        if apex is None and m and set(_pairs(m[1])[0]) <= set(names):
            apex = (set(names) - set(_pairs(m[1])[0])).pop()
        apex = apex or b
        others = [n for n in names if n != apex]
        top = 1.2 if re.search(r"(?:тупоугольн|12\d\s*°|1[3-7]\d\s*°)", t) else 3.2
        pts = {others[0]: (0.0, 0.0), apex: (2.0, top), others[1]: (4.0, 0.0)}
        return [pts[n] for n in names]
    if "тупоугольн" in t:
        return [(0.0, 0.0), (1.0, 1.4), (4.4, 0.0)]
    return [(0.0, 0.0), (1.3, 2.9), (4.4, 0.0)]      # generic acute, scalene


def _on_circle(n: int, r=2.5, start=90.0, uneven=False):
    steps = [0, 70, 160, 230, 300, 330][:n] if uneven and n <= 6 else \
        [360.0 * k / n for k in range(n)]
    return [(r * math.cos(math.radians(start + a)), r * math.sin(math.radians(start + a)))
            for a in steps]


def _vertices(kind: str, names: list[str], t: str):
    cyclic = bool(re.search(r"вписан\w*\s+в\s+окружност|в\s+окружност\w*[^.;]*вписан"
                            r"|описан\w*\s+(?:\w+\s+)?окружност|окружност\w*[^.;]*описан", t))
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
        # bases AD and BC unless the text names AB and CD as the bases
        m = re.search(rf"основани\w*\s+({_PP})\s+и\s+({_PP})", t)
        if m and {frozenset(_pairs(m[1])[0]), frozenset(_pairs(m[2])[0])} == \
                {frozenset(names[0:2]), frozenset(names[2:4])}:
            return [(0, 0), (4.8, 0), (3.3, 2.5), (1.1, 2.5)]
        if cyclic or "равнобедренн" in t:
            return [(0, 0), (1.2, 2.5), (3.6, 2.5), (4.8, 0)]
        return [(0, 0), (1.1, 2.5), (3.3, 2.5), (4.8, 0)]
    if kind == "quad":
        if cyclic or re.search(r"одной\s+окружност", t):
            return _on_circle(4, start=200, uneven=True)
        return [(0, 0), (0.7, 2.6), (3.9, 3.0), (4.6, 0.3)]
    n = len(names)
    if cyclic and not re.search(r"правильн", t):
        return _on_circle(n, start=200, uneven=True)
    return _on_circle(n, start=90 + 180.0 / n if n % 2 == 0 else 90)


class _Builder:
    def __init__(self):
        self.points: list[str] = []
        self.cons: list[dict] = []
        self.free: list[float] = []
        self.segments: list[list[str]] = []
        self.circles: list[list[str]] = []
        self.hidden: list[str] = []
        self.right: list[list[str]] = []
        self.polygon: list[str] = []
        self.angle: tuple[str, str, str] | None = None

    def has(self, *names) -> bool:
        return all(n in self.points for n in names)

    def free_point(self, name, xy):
        if name in self.points:
            return False
        self.points.append(name)
        self.cons.append({"op": "free_point", "out": name})
        self.free.extend(float(v) for v in xy)
        return True

    def add(self, op, out, args, value=None):
        if out in self.points or not self.has(*args) or out in args:
            return False
        c = {"op": op, "out": out, "args": list(args)}
        if value is not None:
            c["value"] = value
        # try the construction now: a degenerate one is simply skipped
        from .constructions import execute
        try:
            probe = FigurePlan.from_dict({"points": self.points + [out],
                                         "constructions": self.cons + [c]})
            execute(probe, free_values=np.array(self.free, dtype=float))
        except (PlanError, ValueError, ZeroDivisionError, FloatingPointError):
            return False
        self.points.append(out)
        self.cons.append(c)
        return True

    def seg(self, a, b):
        if a != b and self.has(a, b) and [a, b] not in self.segments \
                and [b, a] not in self.segments:
            self.segments.append([a, b])

    def helper(self, prefix: str) -> str:
        k = 1
        while f"{prefix}{k}" in self.points:
            k += 1
        name = f"{prefix}{k}"
        self.hidden.append(name)
        return name

    def neighbours(self, v):
        if v not in self.polygon:
            return None
        i = self.polygon.index(v)
        n = len(self.polygon)
        return self.polygon[(i - 1) % n], self.polygon[(i + 1) % n]


def _circle_centre_names(t: str) -> list[str]:
    out = []
    for m in re.finditer(rf"центр\w*\s+(?:в\s+точк\w*\s+)?({_LIST_P})", t):
        out.extend(n for n in _names(m[1]) if n not in out)
    return out


def _base(t: str, B: _Builder):
    """Place the base figure; returns the polygon vertex list (maybe empty)."""
    base = _base_polygon(t)
    centres = _circle_centre_names(t)
    if base:
        kind, names = base
        for n, xy in zip(names, _vertices(kind, names, t)):
            B.free_point(n, xy)
        for i, n in enumerate(names):
            B.seg(n, names[(i + 1) % len(names)])
        B.polygon = names
        return names
    if "окружност" in t:
        centres = centres or ["O"]
        if centres == ["O"] and "O" not in t:
            B.hidden.append("O")
        external = []
        m = re.search(rf"из\s+точк\w*\s+({_P})", t)
        if m and "касательн" in t:
            external.append(m[1])
        tangent_ext = re.search(r"касаются\s+внешн|внешн\w*\s+касани", t)
        tangent_int = re.search(r"касаются\s+внутренн|внутренн\w*\s+касани", t)
        if tangent_ext:
            layout = [((0.0, 0.0), 1.8), ((3.0, 0.0), 1.2), ((5.0, 0.0), 0.8)]
        elif tangent_int:
            layout = [((0.0, 0.0), 2.0), ((0.8, 0.0), 1.2), ((-0.6, 0.0), 1.4)]
        else:
            layout = [((3.2 * k, 0.0), 2.0) for k in range(3)]
        for c, ((x, y), r) in zip(centres[:3], layout):
            B.free_point(c, (x, y))
            rw = f"R_{c}"
            # the witness lies on the line of centres for tangent circles
            B.free_point(rw, (x + r, y) if (tangent_ext or tangent_int) else (x, y + r))
            B.hidden.append(rw)
            B.circles.append([c, rw])
        if len(centres) >= 2:
            B.seg(centres[0], centres[1])
        for e in external:
            B.free_point(e, (5.2, 0.4))
        return []
    m = re.search(rf"уг(?:о)?л\w*\s+({_P0})({_P0})({_P0})(?![A-Za-z0-9_])", t)
    if m and len(set(m.group(1, 2, 3))) == 3:
        a, o, b = m.group(1, 2, 3)
        B.free_point(o, (0.0, 0.0))
        B.free_point(a, (4.0, 0.0))
        value = re.search(r"(\d+(?:[.,]\d+)?)\s*°", t)
        theta = min(max(_num(value[1]), 15.0), 165.0) if value else 55.0
        B.free_point(b, (3.2 * math.cos(math.radians(theta)), 3.2 * math.sin(math.radians(theta))))
        B.seg(o, a), B.seg(o, b)
        B.angle = (a, o, b)
        return []
    m = re.search(rf"(?:отрез\w*|прям\w*)\s+({_PP})", t)
    if m:
        a, b = _pairs(m[1])[0]
        if a != b:
            B.free_point(a, (0.0, 0.0))
            B.free_point(b, (4.0, 0.0))
            B.seg(a, b)
            return []
    return None


def sketch_plan(text: str):
    """Return (FigurePlan, free_values) or None if no figure is recognised."""
    if not isinstance(text, str) or len(text) > 20000:
        return None
    t = _clean(text)
    B = _Builder()
    names = _base(t, B)
    if names is None:
        return None
    rules: list[tuple] = []           # (out, op, args, value)
    weak: list[tuple] = []            # even spacing on a side: only if nothing better
    draw: list[tuple[str, str]] = []  # segments drawn when both ends exist

    # ratios XP : PY = m : n  -> P on XY
    for m in re.finditer(rf"({_P0})({_P0})\s*:\s*({_P0})({_P0})\s*=\s*"
                         r"(\d+(?:[.,]\d+)?)\s*:\s*(\d+(?:[.,]\d+)?)", t):
        x, p, p2, y = m.group(1, 2, 3, 4)
        a, b = _num(m[5]), _num(m[6])
        if p == p2 and a > 0 and b > 0 and len({x, p, y}) == 3:
            rules.append((p, "divide_segment", [x, y], a / (a + b)))
            draw.append((x, y))

    # midpoints: "M — середина BC", "K и L — середины сторон AB и BC",
    # "середина BC — точка M", "точка M — середина стороны BC"
    for m in re.finditer(rf"({_LIST_P})\s*(?:—|-|,)?\s*(?:это\s+|—\s*)?середин\w*\s+"
                         rf"(?:(?:сторон|отрезк|основани|диагонал|ребр|катет|гипотенуз)\w*\s+)?({_LIST_PP})", t):
        for p, (x, y) in zip(_names(m[1]), _pairs(m[2])):
            rules.append((p, "midpoint", [x, y], None))
            draw.append((x, y))
    for m in re.finditer(rf"середин\w*\s+(?:(?:сторон|отрезк|основани|диагонал)\w*\s+)?({_PP})"
                         rf"\s*(?:—|-|,)?\s*(?:точк\w*\s+)({_P})", t):
        (x, y), p = _pairs(m[1])[0], m[2]
        rules.append((p, "midpoint", [x, y], None))

    # median line of a trapezoid / triangle: MN with M on AB, N on CD
    for m in re.finditer(rf"средн\w*\s+лини\w*\s+({_PP})", t):
        for p in _pairs(m[1])[0]:
            s = re.search(rf"(?<![A-Za-z]){p}\s+(?:лежит\s+)?(?<![а-я])на\s+(?:{_SIDE}\s+)?({_PP})", t)
            if s:
                rules.append((p, "midpoint", list(_pairs(s[1])[0]), None))
        if len(B.polygon) == 4 and not any(r[0] in _pairs(m[1])[0] for r in rules):
            a, b, c, d = B.polygon
            p, q = _pairs(m[1])[0]
            rules += [(p, "midpoint", [a, b], None), (q, "midpoint", [c, d], None)]
        draw.append(_pairs(m[1])[0])

    # extensions: "на продолжении стороны AB за точку B взята точка D"
    for m in re.finditer(rf"продолжени\w*\s+(?:{_SIDE}\s+)?({_PP})[^.;]{{0,40}}?\s+за\s+(?:точк\w*\s+)?({_P})"
                         rf"[^.;]*?точк\w*\s+({_P})", t):
        x, y = _pairs(m[1])[0]
        beyond, p = m[2], m[3]
        start, end = (x, y) if beyond == y else (y, x)
        value = 1.5
        eq = re.search(rf"(?:{end}{p}|{p}{end})\s*=\s*(?:{start}{end}|{end}{start})", t)
        if eq:
            value = 2.0
        rules.append((p, "divide_segment", [start, end], value))
        draw.append((end, p))

    # "на стороне XY ... точки P и Q" / "точка P (лежит) на стороне XY" / "P на XY"
    spread: dict[tuple[str, str], list[str]] = {}
    for sentence in re.split(r"(?<=[.;!?])\s+", t):
        for m in re.finditer(rf"(?<![а-я])на\s+(?:{_SIDE}\s+)?({_PP})[^.;]*?точк\w*\s+({_LIST_P})", sentence):
            if re.search(r"продолжени\w*\s*$", sentence[:m.start()]):
                continue
            for p in _names(m[2]):
                spread.setdefault(_pairs(m[1])[0], []).append(p)
        for m in re.finditer(rf"(?:точк\w*\s+)?({_LIST_P})\s+(?:лежит\s+|лежат\s+|взят\w*\s+|отмечен\w*\s+)?"
                             rf"(?<![а-я])на\s+(?:{_SIDE}\s+)({_PP})", sentence):
            for p in _names(m[1]):
                spread.setdefault(_pairs(m[2])[0], []).append(p)
    for (x, y), pts in spread.items():
        draw.append((x, y))
        free = [p for p in dict.fromkeys(pts) if p not in (x, y)]
        for i, p in enumerate(free):
            weak.append((p, "divide_segment", [x, y], (i + 1) / (len(free) + 1)))

    # cevians: "медиана AM", "медианы AA1 и BB1", "CH — высота"
    kinds = {"медиан": "midpoint", "высот": "foot", "биссектрис": "bisector_point"}
    cevians = []
    for m in re.finditer(rf"(медиан|высот|биссектрис)\w*\s+(?:(?:треугольник\w*|угл\w*)\s+(?:{_P0}){{1,3}}\s+)?"
                         rf"({_LIST_PP})", t):
        cevians += [(m[1], v, p) for v, p in _pairs(m[2])]
    for m in re.finditer(rf"({_LIST_PP})\s*(?:—|-)\s*(?:его\s+|ее\s+)?(медиан|высот|биссектрис)\w*", t):
        cevians += [(m[2], v, p) for v, p in _pairs(m[1])]
    for kind, v, p in cevians:
        if len(B.polygon) == 3 and v in B.polygon:
            a, b = [n for n in B.polygon if n != v]
            op = kinds[kind]
            rules.append((p, op, [a, b] if op == "midpoint" else [v, a, b], None))
            if op == "foot":
                B.right.append([v, p, a])
        elif B.angle and v == B.angle[1] and kind == "биссектрис":
            a, o, b = B.angle
            rules.append((p, "bisector_point", [o, a, b], None))
        draw.append((v, p))
    # bisector of a polygon angle hitting a side: "биссектриса угла A ... пересекает сторону BC в точке K"
    for m in re.finditer(rf"биссектрис\w*\s+угл\w*\s+({_P})[^.;]*?пересека\w*\s+(?:{_SIDE}\s+)?"
                         rf"({_PP})\s+в\s+точк\w*\s+({_P})", t):
        v, (x, y), p = m[1], _pairs(m[2])[0], m[3]
        nb = B.neighbours(v)
        if nb:
            w = B.helper("W")
            rules.append((w, "bisector_point", [v, nb[0], nb[1]], None))
            rules.append((p, "line_intersect", [v, w, x, y], None))
            draw.append((v, p))

    # intersections: "AD и BE пересекаются в точке O", "отрезок AM пересекает BD в точке K"
    for m in re.finditer(rf"({_PP})\s+и\s+({_PP})[^.;]*?пересека(?:ются|ющиеся|ющихся|ются)\s+в\s+точк\w*\s+({_P})", t):
        (a, b), (c, d) = _pairs(m[1])[0], _pairs(m[2])[0]
        rules.append((m[3], "line_intersect", [a, b, c, d], None))
        draw += [(a, b), (c, d)]
    for m in re.finditer(rf"({_LIST_PP})[^.;]*?пересека(?:ются|ющиеся|ющихся|ются)\s+в\s+точк\w*\s+({_P})", t):
        pairs = _pairs(m[1])
        if len(pairs) >= 2:
            (a, b), (c, d) = pairs[:2]
            rules.append((m[2], "line_intersect", [a, b, c, d], None))
            draw += pairs
    for m in re.finditer(rf"({_PP})\s+пересека\w*\s+(?:{_SIDE}\s+)?({_PP})\s+в\s+точк\w*\s+({_P})", t):
        (a, b), (c, d) = _pairs(m[1])[0], _pairs(m[2])[0]
        rules.append((m[3], "line_intersect", [a, b, c, d], None))
        draw += [(a, b), (c, d)]
    # "прямые AM, BM, CM пересекают стороны BC, CA, AB в точках A1, B1, C1"
    for m in re.finditer(rf"({_LIST_PP})\s+пересекают\s+(?:{_SIDE}\s+)?({_LIST_PP})\s+"
                         rf"(?:соответственно\s+)?в\s+точках\s+({_LIST_P})", t):
        for (a, b), (c, d), p in zip(_pairs(m[1]), _pairs(m[2]), _names(m[3])):
            rules.append((p, "line_intersect", [a, b, c, d], None))
            draw.append((a, p))
    m = re.search(rf"диагонал\w*[^.;]*?пересека(?:ются|ющиеся|ющихся|ются)\s+в\s+точк\w*\s+({_P})", t)
    if m and len(B.polygon) == 4:
        a, b, c, d = B.polygon
        rules.append((m[1], "line_intersect", [a, c, b, d], None))
        draw += [(a, c), (b, d)]

    # interior point / centre of a triangle
    m = re.search(rf"точк\w*\s+({_P})\s+(?:лежит\s+)?внутри\s+треугольник", t)
    if m and len(B.polygon) == 3:
        a, b, c = B.polygon
        xy = [np.array(B.free[2 * B.points.index(v):2 * B.points.index(v) + 2]) for v in (a, b, c)]
        B.free_point(m[1], tuple(0.28 * xy[0] + 0.33 * xy[1] + 0.39 * xy[2]))
    m = re.search(rf"({_P})\s*(?:—|-)\s*(?:центр\s+(?:правильного\s+|равностороннего\s+)?"
                  r"треугольник|точк\w*\s+пересечени\w*\s+медиан|центроид)", t)
    if m and len(B.polygon) == 3:
        rules.append((m[1], "centroid", list(B.polygon), None))
    m = re.search(rf"({_P})\s*(?:—|-)\s*(?:ортоцентр|точк\w*\s+пересечени\w*\s+высот)", t)
    if m and len(B.polygon) == 3:
        rules.append((m[1], "orthocenter", list(B.polygon), None))

    # circles around / inside polygons
    centres = _circle_centre_names(t)
    incircle = re.search(r"(?<!о)вписан\w*\s+(?!в\s)(?:\w+\s+)?окружност|окружност\w*\s*,?\s*вписан\w*\s+в"
                         r"|в\s+(?:\w+\s+){0,2}(?:треугольник|четырехугольник|ромб|квадрат)\w*[^.;]*вписан\w*\s+окружност", t)
    circum = re.search(r"описан\w*\s+(?:\w+\s+)?окружност|окружност\w*\s*,?\s*описан"
                       r"|в\s+окружност\w*[^.;]*вписан|вписан\w*\s+в\s+окружност|одной\s+окружност", t)
    poly = B.polygon
    if len(poly) >= 3 and (incircle or circum or (centres and "окружност" in t)):
        a, b, c = poly[:3]
        if incircle and (len(poly) == 3 or re.search(r"квадрат|ромб|правильн", t) or len(poly) > 4):
            i = centres[0] if centres else "I"
            if len(poly) == 3:
                made = B.add("incenter", i, [a, b, c])
            elif len(poly) == 4:
                made = B.add("midpoint", i, [poly[0], poly[2]])
            else:
                made = B.add("circumcenter", i, [a, b, c])
            if made:
                touch = re.search(rf"касающ\w*\s+(?:{_SIDE}\s+)?({_PP})\s+в\s+точк\w*\s+({_P})", t)
                x, y = (_pairs(touch[1])[0] if touch else (poly[1], poly[2]))
                foot = touch[2] if touch else B.helper("T")
                if B.add("foot", foot, [i, x, y]):
                    B.circles.append([i, foot])
        if circum or (centres and not incircle):
            o = next((n for n in (centres[:1] if centres and not incircle else []) + ["O", "Q", "O_1"]
                      if n not in B.points), None)
            if o and B.add("circumcenter", o, [a, b, c]):
                B.circles.append([o, a])
                if "O" == o and "O" not in text:
                    B.hidden.append(o)

    # chords / diameters / tangents on the first circle without a polygon
    if not poly and B.circles:
        c0, r0 = B.circles[0]
        radius = 2.0
        cx, cy = B.free[0], B.free[1]
        angles = iter((160, 10, 100, 250, 60, 300, 200, 340, 130, 30))
        chords = []
        for m in re.finditer(rf"(хорд\w*|диаметр\w*)\s+({_LIST_PP})", t):
            for a, b in _pairs(m[2]):
                chords.append((m[1].startswith("диаметр"), a, b))
        perpendicular = bool(re.search(r"перпендикуляр", t))
        diam = None

        def on_circle(name):
            th = math.radians(next(angles, 0))
            B.free_point(name, (cx + radius * math.cos(th), cy + radius * math.sin(th)))

        for diameter, a, b in chords[:4]:
            if a not in B.points:
                on_circle(a)
            if diameter:
                B.add("reflect_point", b, [a, c0])
                diam = diam or (a, b)
            elif b not in B.points:
                if perpendicular and diam and B.has(*diam):
                    # a chord perpendicular to the diameter is symmetric about it
                    B.add("reflect_line", b, [a, diam[0], diam[1]])
                if b not in B.points:
                    on_circle(b)
            B.seg(a, b)
        m = re.search(rf"пересека(?:ются|ющиеся|ющихся|ются)\s+в\s+точк\w*\s+({_P})", t)
        real = [(a, b) for _, a, b in chords if B.has(a, b)]
        if m and len(real) >= 2:
            (a, b), (c, d) = real[:2]
            B.add("line_intersect", m[1], [a, b, c, d])
        # tangents from an external point: "касательные MA и MB"
        for m in re.finditer(rf"касательн\w*\s+({_LIST_PP})", t):
            for k, (e, p) in enumerate(_pairs(m[1])[:2]):
                if B.has(e) and B.add("tangent_point", p, [e, c0, r0], k % 2):
                    B.seg(e, p)
                    B.right.append([c0, p, e])
                    B.seg(c0, p)

    # resolve rules in dependency order
    strong = {r[0] for r in rules}
    rules += [w for w in weak if w[0] not in strong]
    progress = True
    while progress:
        progress = False
        for out, op, args, value in rules:
            if out not in B.points and B.has(*args) and B.add(op, out, args, value):
                progress = True
    for a, b in draw:
        B.seg(a, b)

    # quadrilateral diagonals mentioned without names
    if len(B.polygon) == 4 and re.search(r"диагонал", t) \
            and not re.search(rf"диагонал\w*\s+{_PP}", t):
        a, b, c, d = B.polygon
        B.seg(a, c), B.seg(b, d)
    # angles and asked segments: "угол AEF", "∠BOC", "найдите BM"
    for m in re.finditer(rf"(?:∠|уг(?:о)?л\w*\s+)\s*({_P0})({_P0})({_P0})(?![A-Za-z0-9_])", t):
        a, o, b = m.group(1, 2, 3)
        if len({a, o, b}) == 3:
            B.seg(a, o), B.seg(o, b)
    for m in re.finditer(rf"найдите\s+(?:длин\w*\s+|отрез\w*\s+)?({_LIST_PP})", t):
        for a, b in _pairs(m[1]):
            B.seg(a, b)
    # named segments / diagonals / lines
    for m in re.finditer(rf"(?:отрез\w*|диагонал\w*|прям\w*|луч\w*|хорд\w*|сторон\w*|"
                         rf"медиан\w*|высот\w*|биссектрис\w*)\s+({_LIST_PP})", t):
        for a, b in _pairs(m[1]):
            B.seg(a, b)
    return _finish(B)


def _finish(B: _Builder):
    right = [r for r in B.right if all(n in B.points for n in r)]
    try:
        plan = FigurePlan.from_dict({
            "points": B.points,
            "constructions": B.cons,
            "constraints": [],
            "draw": {"segments": B.segments, "circles": B.circles,
                     "right_angles": right,
                     "hide_labels": [h for h in dict.fromkeys(B.hidden) if h in B.points]},
            "target": {"kind": "none", "args": []},
            "scale_free": True,
            "notes": "Схематичный чертёж по ключевым словам условия.",
        })
        validate_plan(plan)
    except PlanError:
        return None
    return plan, np.array(B.free, dtype=float)
