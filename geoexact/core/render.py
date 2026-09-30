"""GeoExact: рендер чертежа в чистый SVG (без matplotlib и внешних зависимостей).

Слои: <g id="main">, <g id="aux">, <g id="labels">, <g id="marks"> — включаются/выключаются.
Типографика математическая: Georgia serif, имена точек курсивом.
"""
from __future__ import annotations

import math
import os
import re
from typing import TYPE_CHECKING, Any, Sequence

import numpy as np

from .schema import FigurePlan, PlanError

if TYPE_CHECKING:  # pragma: no cover
    from .solver import Solution

# ---------------------------------------------------------------- стиль
MARGIN_FRAC = 0.08
FONT = "Georgia, serif"
COL_MAIN = "#111111"
COL_AUX = "#1f6feb"
COL_MARK = "#111111"
COL_LABEL = "#111111"
# Равные отрезки — равные цвета: у каждой группы равенства свой цвет.
# Порядок устойчив (группы сортируются по count), палитра читается на белом
# и отличается от основного чёрного и вспомогательного синего.
EQ_COLORS = ("#d81e3f", "#1273b5", "#0f9d58", "#e8890c", "#8e44ad", "#0e8a84")
PT_R = 3.2
LABEL_FS = 15.0
MARK_FS = 12.5
CHAR_W = 0.52          # приближение ширины символа в долях кегля
LABEL_OFFSET = 13.0
DIRS8 = [(1, 0), (0.7071, 0.7071), (0, 1), (-0.7071, 0.7071),
         (-1, 0), (-0.7071, -0.7071), (0, -1), (0.7071, -0.7071)]


def _esc(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _f(x: float) -> str:
    # Arc centres are unusually sensitive to endpoint rounding at small angles.
    return f"{float(x):.6f}".rstrip("0").rstrip(".") or "0"


# ---------------------------------------------------------------- геометрия хелперы
def _rect_seg_hit(rect: tuple[float, float, float, float],
                  p: tuple[float, float], q: tuple[float, float]) -> bool:
    """Пересекает ли отрезок PQ прямоугольник (x0,y0,x1,y1) — алгоритм Лианга–Барски."""
    x0, y0, x1, y1 = rect
    dx, dy = q[0] - p[0], q[1] - p[1]
    t0, t1 = 0.0, 1.0
    for num, den in ((x0 - p[0], dx), (p[0] - x1, -dx), (y0 - p[1], dy), (p[1] - y1, -dy)):
        if abs(den) < 1e-12:
            if num > 0:
                return False
            continue
        t = num / den
        if den > 0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
        if t0 > t1:
            return False
    return True


def _rects_overlap(a: tuple[float, float, float, float],
                   b: tuple[float, float, float, float]) -> bool:
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


def _rect_has_point(r: tuple[float, float, float, float], p: tuple[float, float]) -> bool:
    return r[0] <= p[0] <= r[2] and r[1] <= p[1] <= r[3]


def _mark_text(value: Any) -> str:
    """Keep degree signs as real Unicode, including common model/LaTeX escapes."""
    text = str(value if value is not None else "")
    for token in (r"\u00b0", r"\u00B0", r"^{\circ}", r"^\circ",
                  r"\circ", r"\degree", "&deg;"):
        text = text.replace(token, "°")
    return text.strip("$")


def _numeric_angle(text: str) -> float | None:
    match = re.fullmatch(r"\s*([+-]?\d+(?:[.,]\d+)?)\s*(?:°|deg(?:rees)?)?\s*",
                         text, flags=re.IGNORECASE)
    return float(match[1].replace(",", ".")) if match else None


def _angle_delta(u: np.ndarray, v: np.ndarray, reflex: bool = False) -> float:
    """Signed sweep in SVG coordinates (positive = clockwise on the screen)."""
    cross = float(u[0] * v[1] - u[1] * v[0])
    delta = math.atan2(cross, float(np.dot(u, v)))
    # Resolve the exactly straight case reproducibly, without signed-zero noise.
    if abs(abs(delta) - math.pi) < 1e-12:
        delta = math.pi
    if reflex:
        delta -= math.copysign(2 * math.pi, delta)
    return delta


def _arc_path(center: np.ndarray, radius: float, start: float, delta: float) -> str:
    """SVG endpoint form with the flags selecting *this* centre, not its mirror."""
    p = center + radius * np.array([math.cos(start), math.sin(start)])
    q = center + radius * np.array([math.cos(start + delta), math.sin(start + delta)])
    return (f'M {_f(p[0])} {_f(p[1])} A {_f(radius)} {_f(radius)} 0 '
            f'{int(abs(delta) > math.pi + 1e-12)} {int(delta > 0)} {_f(q[0])} {_f(q[1])}')


def _text_box(text: str, center: Sequence[float], fs: float) -> tuple[float, float, float, float]:
    # Conservative Georgia metrics, including italic overhangs and prime labels.
    weight = sum(1.08 if c in "MW@%ЖШЩ" else
                 0.82 if c.isupper() or ord(c) > 127 else
                 0.42 if c in "il.,:'′ " else 0.65 for c in text)
    tw, th = max(fs * 0.55, weight * fs) + 6, fs * 1.3 + 2
    return center[0] - tw / 2, center[1] - th / 2, center[0] + tw / 2, center[1] + th / 2


def _count(mark: dict) -> int:
    value = mark.get("count", 1)
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 3:
        raise PlanError("BAD_MARK_COUNT", "число штрихов/дуг должно быть целым от 1 до 3")
    return value


def _point_on_primitive(p: np.ndarray, a: np.ndarray, b: np.ndarray, kind: str) -> bool:
    vec = b - a
    length = float(np.linalg.norm(vec))
    if length < 1e-12:
        return False
    rel = p - a
    if abs(float(vec[0] * rel[1] - vec[1] * rel[0])) > 1e-7 * length * max(length, float(np.linalg.norm(rel)), 1e-9):
        return False
    t = float(np.dot(rel, vec)) / (length * length)
    return kind == "lines" or (t >= -1e-7 and (kind == "rays" or t <= 1 + 1e-7))


def _visibility(draw: Any, points: dict[str, np.ndarray]):
    """Infer auxiliary-only points and marks without hiding points on main edges.

    Explicit aux_points is authoritative. Legacy marks inherit the layer of their
    supporting segments/rays; an explicit mark.layer always wins.
    """
    primitives: dict[str, list[tuple[list[str], str]]] = {"main": [], "aux": []}
    refs: dict[str, set[str]] = {"main": set(), "aux": set()}
    for layer, prefix in (("main", ""), ("aux", "aux_")):
        for kind in ("segments", "lines", "rays", "circles", "extensions"):
            for item in getattr(draw, prefix + kind, []):
                refs[layer].update(item)
                if len(item) == 2 and all(n in points for n in item):
                    primitives[layer].append((list(item), kind))
    for arc in getattr(draw, "arcs", []):
        layer = arc.get("layer", "main")
        refs[layer].update(arc.get(key) for key in ("center", "start", "end") if arc.get(key))
    for field in ("angle_marks", "right_angles", "length_marks", "equal_marks"):
        for mark in getattr(draw, field, []):
            if isinstance(mark, dict) and mark.get("layer") in refs:
                refs[mark["layer"]].update(mark.get("pts", []))

    def incident(name, layer):
        p = points[name]
        for pair, kind in primitives[layer]:
            a, b = (points[n] for n in pair)
            if kind == "circles":
                radius = float(np.linalg.norm(b - a))
                if radius > 1e-12 and abs(float(np.linalg.norm(p - a)) - radius) <= radius * 1e-7:
                    return True
            elif _point_on_primitive(p, a, b, kind):
                return True
        return False

    aux_only = set(getattr(draw, "aux_points", []))
    for name in points:
        if name not in refs["main"] and not incident(name, "main"):
            if name in refs["aux"] or incident(name, "aux"):
                aux_only.add(name)

    def supported(pair, layer):
        if any(n not in points for n in pair):
            return False
        for ends, kind in primitives[layer]:
            if kind != "circles" and all(_point_on_primitive(points[n], points[ends[0]],
                                                             points[ends[1]], kind) for n in pair):
                return True
        return False

    def mark_layer(mark):
        if isinstance(mark, dict) and mark.get("layer") in ("main", "aux"):
            return mark["layer"]
        pts = mark.get("pts", []) if isinstance(mark, dict) else mark
        if any(p in aux_only for p in pts):
            return "aux"
        pairs = [[pts[0], pts[1]], [pts[1], pts[2]]] if len(pts) == 3 else [pts]
        if any(len(pair) == 2 and supported(pair, "aux") and not supported(pair, "main") for pair in pairs):
            return "aux"
        return "main"

    return aux_only, mark_layer


# ---------------------------------------------------------------- рендер
def render_svg(plan: FigurePlan, sol: Any, gate: Any = None, show_aux: bool = True,
               width: int = 560) -> str:
    coords_raw = getattr(sol, "coords", None) or {}
    P: dict[str, np.ndarray] = {}
    for k, v in coords_raw.items():
        a = np.asarray(v, dtype=float).reshape(-1)[:2]
        if a.shape[0] == 2 and np.all(np.isfinite(a)):
            P[k] = a
    d = plan.draw
    notes: list[str] = []
    aux_only, mark_layer = _visibility(d, P)
    from .gates import _used_points
    # hide_labels still keeps points on drawn primitives (e.g. an unlabeled
    # vertex), but construction-only ray witnesses must not become black dots.
    hidden_helpers = set(d.hide_labels) - _used_points(plan)
    visible = {k: p for k, p in P.items()
               if k not in hidden_helpers and (show_aux or k not in aux_only)}

    if len(visible) == 0:
        return ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">'
                '<!-- EMPTY_FIGURE: нет конечных координат -->'
                '<g id="main"></g><g id="aux"></g><g id="labels"></g><g id="marks"></g></svg>'
                % (width, width, width, width))

    # ---- границы (точки + окружности)
    xs = [float(p[0]) for p in visible.values()]
    ys = [float(p[1]) for p in visible.values()]
    circles = [c for c in list(d.circles) + (list(d.aux_circles) if show_aux else []) if len(c) >= 2]
    for c in circles:
        if c[0] in P and c[1] in P:
            O, R = P[c[0]], float(np.hypot(*(P[c[1]] - P[c[0]])))
            xs += [float(O[0]) - R, float(O[0]) + R]
            ys += [float(O[1]) - R, float(O[1]) + R]
    # Reserve arc extrema as well as their defining points. Bounding the complete
    # supporting circle is conservative and avoids clipping reflex arcs.
    for arc in getattr(d, "arcs", []):
        if arc.get("layer", "main") == "aux" and not show_aux:
            continue
        if arc.get("center") in P and arc.get("start") in P:
            o = P[arc["center"]]
            r = float(np.linalg.norm(P[arc["start"]] - o))
            xs += [float(o[0]) - r, float(o[0]) + r]
            ys += [float(o[1]) - r, float(o[1]) + r]
    xmin, xmax, ymin, ymax = min(xs), max(xs), min(ys), max(ys)
    w_data, h_data = xmax - xmin, ymax - ymin
    base = max(w_data, h_data, 1e-9)
    if w_data < base * 1e-3:
        cx = (xmin + xmax) / 2
        xmin, xmax, w_data = cx - base * 0.05, cx + base * 0.05, base * 0.1
    if h_data < base * 1e-3:
        cy = (ymin + ymax) / 2
        ymin, ymax, h_data = cy - base * 0.05, cy + base * 0.05, base * 0.1

    pad = max(width * MARGIN_FRAC, min(28.0, width * 0.2))
    scale = (width - 2 * pad) / max(w_data, h_data)
    height = h_data * scale + 2 * pad

    def T(p) -> tuple[float, float]:
        """Мировые -> пиксельные координаты; ось y инвертирована."""
        return (pad + (float(p[0]) - xmin) * scale, pad + (ymax - float(p[1])) * scale)

    Q = {k: T(v) for k, v in P.items()}
    visible_q = {k: Q[k] for k in visible}
    span_px = max(w_data, h_data) * scale

    # ---- равные отрезки: каждая группа равенства получает свой цвет.
    # Черточки можно скрыть на клиенте — равенство останется видимым по цвету,
    # поэтому раскраска живёт в самом SVG, а не в переключателе.
    eq_group: dict[frozenset, int] = {}
    eq_layer: dict[frozenset, str] = {}
    for m in getattr(d, "equal_marks", []):
        pts = m.get("pts") or []
        if len(pts) == 2 and pts[0] != pts[1]:
            key = frozenset(pts)
            if key not in eq_group:
                eq_group[key] = int(m.get("count", 1))
                eq_layer[key] = mark_layer(m)
    eq_painted: set = set()        # пары, которые уже нарисованы отдельной цветной линией
    eq_color = {count: EQ_COLORS[i % len(EQ_COLORS)]
                for i, count in enumerate(sorted(set(eq_group.values())))}

    # ---- слой main / aux: сегменты и окружности
    main: list[str] = []
    aux: list[str] = []
    px_segs: list[tuple[tuple[float, float], tuple[float, float]]] = []
    straight_segs: list[tuple[tuple[float, float], tuple[float, float]]] = []
    geometry_boxes: list[tuple[float, float, float, float]] = []

    def emit_segments(items, out: list[str], cls: str, kind: str = "segments") -> None:
        for s in items:
            if len(s) < 2 or s[0] == s[1] or s[0] not in Q or s[1] not in Q:
                notes.append(f"SKIPPED_SEGMENT: {list(s)}")
                continue
            a, b = Q[s[0]], Q[s[1]]
            line_cls = cls + (f" eqc-{eq_group[frozenset((s[0], s[1]))]}"
                              if frozenset((s[0], s[1])) in eq_group else "")
            if frozenset((s[0], s[1])) in eq_group and kind == "segments":
                eq_painted.add(frozenset((s[0], s[1])))
            if math.dist(a, b) < 1e-9:
                notes.append(f"SKIPPED_SEGMENT: {list(s)} нулевая длина")
                continue
            if kind != "segments":
                # Clip infinite lines / half-lines against a padded diagram box.
                lo, hi = (-math.inf if kind == "lines" else 0.0), math.inf
                direction = (b[0] - a[0], b[1] - a[1])
                for axis, lower, upper in ((0, pad / 2, width - pad / 2),
                                            (1, pad / 2, height - pad / 2)):
                    if abs(direction[axis]) < 1e-12:
                        continue
                    ends = sorted(((lower - a[axis]) / direction[axis],
                                   (upper - a[axis]) / direction[axis]))
                    lo, hi = max(lo, ends[0]), min(hi, ends[1])
                if lo > hi:
                    continue
                a, b = (tuple(a[i] + t * direction[i] for i in (0, 1)) for t in (lo, hi))
            px_segs.append((a, b))
            straight_segs.append((a, b))
            geometry_boxes.append((min(a[0], b[0]) - 1, min(a[1], b[1]) - 1,
                                   max(a[0], b[0]) + 1, max(a[1], b[1]) + 1))
            out.append(f'<line class="{line_cls}" data-kind="{kind}" x1="{_f(a[0])}" y1="{_f(a[1])}" '
                       f'x2="{_f(b[0])}" y2="{_f(b[1])}"/>')

    def emit_circles(items, out: list[str], cls: str) -> None:
        for c in items:
            if len(c) < 2 or c[0] not in Q or c[1] not in Q:
                notes.append(f"SKIPPED_CIRCLE: {list(c)}")
                continue
            O = Q[c[0]]
            R = math.hypot(Q[c[1]][0] - O[0], Q[c[1]][1] - O[1])
            if R < 0.5:
                notes.append(f"SKIPPED_CIRCLE: {list(c)} нулевой радиус")
                continue
            out.append(f'<circle class="{cls}" cx="{_f(O[0])}" cy="{_f(O[1])}" r="{_f(R)}"/>')
            geometry_boxes.append((O[0] - R - 1, O[1] - R - 1, O[0] + R + 1, O[1] + R + 1))
            # Circle outlines participate in text layout, not their filled discs.
            samples = [(O[0] + R * math.cos(t), O[1] + R * math.sin(t))
                       for t in np.linspace(0, 2 * math.pi, 97)]
            px_segs.extend(zip(samples, samples[1:]))

    emit_segments(d.segments, main, "seg")
    def emit_extensions(items, out, cls):
        for a, b in items:
            if a not in Q or b not in Q:
                continue
            start, end = np.asarray(Q[a]), np.asarray(Q[b])
            direction = end - start
            length = float(np.linalg.norm(direction))
            if length < 1e-9:
                continue
            far = end + direction / length * min(32.0, max(15.0, length * 0.22))
            px_segs.append((tuple(end), tuple(far)))
            straight_segs.append((tuple(end), tuple(far)))
            geometry_boxes.append((min(end[0], far[0]), min(end[1], far[1]),
                                   max(end[0], far[0]), max(end[1], far[1])))
            out.append(f'<line class="{cls}" data-kind="extension" '
                       f'x1="{_f(end[0])}" y1="{_f(end[1])}" '
                       f'x2="{_f(far[0])}" y2="{_f(far[1])}"/>')
    emit_extensions(d.extensions, main, "seg")
    emit_segments(getattr(d, "lines", []), main, "seg", "lines")
    emit_segments(getattr(d, "rays", []), main, "seg", "rays")
    emit_circles(d.circles, main, "circ")
    if show_aux:
        emit_segments(d.aux_segments, aux, "aux-seg")
        emit_extensions(d.aux_extensions, aux, "aux-seg")
        emit_segments(getattr(d, "aux_lines", []), aux, "aux-seg", "lines")
        emit_segments(getattr(d, "aux_rays", []), aux, "aux-seg", "rays")
        emit_circles(d.aux_circles, aux, "aux-circ")

    # Равный отрезок может быть лишь частью нарисованной линии (половина стороны,
    # проведённой целиком): он красится цветным слоем поверх неё — в обоих режимах.
    def _on_drawn_line(p, q) -> bool:
        def near(pt, a, b) -> bool:
            ab = (b[0] - a[0], b[1] - a[1])
            den = ab[0] ** 2 + ab[1] ** 2
            if den < 1e-12:
                return False
            u = ((pt[0] - a[0]) * ab[0] + (pt[1] - a[1]) * ab[1]) / den
            if not -1e-6 <= u <= 1 + 1e-6:
                return False
            return math.dist(pt, (a[0] + u * ab[0], a[1] + u * ab[1])) < 0.6
        return any(near(p, a, b) and near(q, a, b) for a, b in straight_segs)

    for key, count in eq_group.items():
        if key in eq_painted or len(key) != 2:
            continue
        x, y = sorted(key)
        if x not in Q or y not in Q or (eq_layer[key] == "aux" and not show_aux):
            continue
        a, b = Q[x], Q[y]
        if math.dist(a, b) < 1e-9 or not _on_drawn_line(a, b):
            continue
        overlay = (f'<line class="seg eqc-{count}" data-kind="eq-part" x1="{_f(a[0])}" '
                   f'y1="{_f(a[1])}" x2="{_f(b[0])}" y2="{_f(b[1])}"/>')
        (aux if eq_layer[key] == "aux" else main).append(overlay)

    # Цветные линии — поверх чёрных: иначе дубль целой стороны, нарисованный
    # позже, закрывает раскрашенные половины.
    for layer_items in (main, aux):
        layer_items.sort(key=lambda s: ' eqc-' in s.split('data-kind', 1)[0])

    for arc in getattr(d, "arcs", []):
        layer = arc.get("layer", "main")
        if layer == "aux" and not show_aux:
            continue
        names = [arc.get(k) for k in ("center", "start", "end")]
        if any(n not in Q for n in names):
            notes.append(f"SKIPPED_ARC: {names}")
            continue
        o, a, b = (np.array(Q[n]) for n in names)
        r, r_end = float(np.linalg.norm(a - o)), float(np.linalg.norm(b - o))
        if r < 1e-9 or not math.isclose(r, r_end, rel_tol=1e-6, abs_tol=1e-6):
            raise PlanError("BAD_ARC_RADIUS", f"дуга {names}: концы не лежат на одной окружности")
        delta = _angle_delta((a - o) / r, (b - o) / r_end, bool(arc.get("reflex", False)))
        if abs(delta) < 1e-10 or abs(abs(delta) - 2 * math.pi) < 1e-10:
            raise PlanError("DEGENERATE_ARC", f"дуга {names}: совпадающие направления")
        start = math.atan2(a[1] - o[1], a[0] - o[0])
        out = aux if layer == "aux" else main
        cls = "aux-circ" if layer == "aux" else "circ"
        out.append(f'<path class="{cls}" data-kind="arc" d="{_arc_path(o, r, start, delta)}"/>')
        samples = [o + r * np.array([math.cos(t), math.sin(t)])
                   for t in np.linspace(start, start + delta, max(16, int(abs(delta) * 20)))]
        px_segs.extend(zip(samples, samples[1:]))
        geometry_boxes.append((min(p[0] for p in samples) - 1, min(p[1] for p in samples) - 1,
                               max(p[0] for p in samples) + 1, max(p[1] for p in samples) + 1))

    # ---- marks: geometry first, then text. Every text box becomes an obstacle
    # for later marks and point labels (not merely the text's centre).
    marks: list[str] = []
    mark_boxes: list[tuple[float, float, float, float]] = []
    text_boxes: list[tuple[float, float, float, float]] = []
    mark_segments: list[tuple[Any, Any]] = []
    angle_texts = []
    arc_r = max(18.0, min(30.0, 0.064 * span_px))
    sq = max(8.0, min(13.0, 0.032 * span_px))

    def reserve_path(samples):
        box = (min(p[0] for p in samples) - 2, min(p[1] for p in samples) - 2,
               max(p[0] for p in samples) + 2, max(p[1] for p in samples) + 2)
        mark_boxes.append(box)
        geometry_boxes.append(box)
        mark_segments.extend(zip(samples, samples[1:]))

    def collision_score(rect):
        pen = 0.0
        for a, b in px_segs + mark_segments:
            if _rect_seg_hit(rect, a, b):
                pen += 8.0
        for box in text_boxes:
            if _rects_overlap(rect, box):
                pen += 40.0
        for q in visible_q.values():
            if _rect_has_point((rect[0] - PT_R - 2, rect[1] - PT_R - 2,
                                rect[2] + PT_R + 2, rect[3] + PT_R + 2), q):
                pen += 20.0
        return pen

    def emit_text(text, candidates, layer):
        if not text:
            return
        best = None
        for preference, point in candidates:
            rect = _text_box(text, point, MARK_FS)
            penalty = collision_score(rect)
            # Prefer the existing viewport, but never clip a chosen position.
            outside = not (2 <= rect[0] and rect[2] <= width - 2 and
                           2 <= rect[1] and rect[3] <= height - 2)
            score = penalty + preference + (2.0 if outside else 0.0)
            if best is None or score < best[0]:
                best = score, penalty, point, rect
        if best is None:
            return
        _, penalty, tp, rect = best
        if penalty:
            notes.append(f"MARK_COLLISION: {text}")
        text_boxes.append(rect)
        marks.append(f'<text class="mark" data-layer="{layer}" x="{_f(tp[0])}" '
                     f'y="{_f(tp[1] + MARK_FS * 0.35)}" text-anchor="middle">{_esc(text)}</text>')

    # A right-angle declaration and an angle label may describe the same rays
    # in either order (or using different points on the same rays).
    angle_records: dict[tuple, dict] = {}
    declarations = [(m, True) for m in d.right_angles] + [(m, False) for m in d.angle_marks]
    for raw, explicit_right in declarations:
        m = dict(raw) if isinstance(raw, dict) else {"pts": list(raw)}
        layer = mark_layer(raw)
        if layer == "aux" and not show_aux:
            continue
        pts = list(m.get("pts") or [])
        if len(pts) != 3 or any(t not in Q for t in pts):
            notes.append(f"SKIPPED_ANGLE: {pts}")
            continue
        A, B, C = (np.array(Q[t]) for t in pts)
        u, v = A - B, C - B
        if m.get("reverse_first", False):
            u = -u
        nu, nv = float(np.linalg.norm(u)), float(np.linalg.norm(v))
        if min(nu, nv) < 1e-9:
            if explicit_right:
                raise PlanError("NON_RIGHT_ANGLE", f"нулевой луч прямого угла {pts}")
            notes.append(f"SKIPPED_ANGLE: {pts} нулевой луч")
            continue
        u, v = u / nu, v / nv
        reflex = bool(m.get("reflex", False))
        delta = _angle_delta(u, v, reflex)
        if abs(delta) < 1e-10 or abs(abs(delta) - 2 * math.pi) < 1e-10:
            if explicit_right:
                raise PlanError("NON_RIGHT_ANGLE", f"совпадающие лучи {pts}")
            notes.append(f"SKIPPED_ANGLE: {pts} совпадающие лучи")
            continue
        text = _mark_text(m.get("text", ""))
        value = _numeric_angle(text)
        is_right = explicit_right or (not reflex and value is not None and abs(value - 90) < 1e-9)
        if is_right and (reflex or abs(float(np.dot(u, v))) > math.sin(math.radians(0.05))):
            raise PlanError("NON_RIGHT_ANGLE", f"метка прямого угла {pts} не соответствует геометрии")
        key = (tuple(round(float(x), 7) for x in B),
               tuple(sorted(tuple(round(float(x), 9) for x in ray) for ray in (u, v))), reflex)
        count = _count(m)
        if key not in angle_records:
            angle_records[key] = dict(B=B, u=u, v=v, short=min(nu, nv), delta=delta,
                                      right=is_right, count=count, text=text, layer=layer)
        else:
            old = angle_records[key]
            old["right"] |= is_right
            old["count"] = max(old["count"], count)
            old["short"] = min(old["short"], nu, nv)
            old["layer"] = "main" if "main" in (old["layer"], layer) else "aux"
            if text and old["text"] and text != old["text"]:
                notes.append(f"DUPLICATE_ANGLE_TEXT: {old['text']} / {text}")
            old["text"] = old["text"] or text

    # Один квадратик прямого угла на вершину. Если прямой угол отмечен
    # дважды с разными лучами (∠AHB и ∠BHC у основания высоты), две отметки
    # по разные стороны линии выглядят странно: остаётся одна — та, чей
    # квадратик меньше перекрыт другими линиями чертежа.
    centroid_px = (float(np.mean([q[0] for q in visible_q.values()])),
                   float(np.mean([q[1] for q in visible_q.values()])))
    rt_groups: dict[tuple, list] = {}
    for rec in angle_records.values():
        if rec["right"]:
            key = (round(float(rec["B"][0]), 6), round(float(rec["B"][1]), 6))
            rt_groups.setdefault(key, []).append(rec)

    def _square_clutter(rec) -> tuple:
        B_, u_, v_ = rec["B"], rec["u"], rec["v"]
        side_ = min(sq, rec["short"] * 0.25)
        c_ = B_ + (u_ + v_) * (side_ / 2)
        h_ = side_ * 0.45
        box_ = (float(c_[0]) - h_, float(c_[1]) - h_, float(c_[0]) + h_, float(c_[1]) + h_)
        cross = sum(1 for a_, b_ in px_segs if _rect_seg_hit(box_, a_, b_))
        # стороны самого угла и их продолжения идут по границе квадратика и
        # во внутренний бокс не попадают; луч внутри угла (высота) — попадает.
        far = math.hypot(float(c_[0]) - centroid_px[0], float(c_[1]) - centroid_px[1])
        return (cross, far)

    rt_drawn: set = set()
    for recs in rt_groups.values():
        best = min(recs, key=_square_clutter)
        for rec in recs:
            if rec is not best:
                best["text"] = best["text"] or rec["text"]
        rt_drawn.add(id(best))

    for rec in angle_records.values():
        B, u, v = rec["B"], rec["u"], rec["v"]
        delta, count, layer = rec["delta"], rec["count"], rec["layer"]
        start = math.atan2(float(u[1]), float(u[0]))
        if rec["right"] and id(rec) not in rt_drawn:
            continue          # на этой вершине уже нарисован другой квадратик
        if rec["right"]:
            side = min(sq, rec["short"] * 0.25)
            p1, p2, p3 = B + u * side, B + (u + v) * side, B + v * side
            marks.append(f'<path class="rt" data-layer="{layer}" d="M {_f(p1[0])} {_f(p1[1])} '
                         f'L {_f(p2[0])} {_f(p2[1])} L {_f(p3[0])} {_f(p3[1])}"/>')
            reserve_path([p1, p2, p3])
            outer = side * math.sqrt(2)
        else:
            # Acute angles need a larger arc, but no arc may outgrow its rays.
            minor_deg = min(abs(math.degrees(delta)), 360 - abs(math.degrees(delta)))
            desired = arc_r + max(0.0, 70 - minor_deg) * 0.23
            outer = min(desired + 4 * (count - 1), rec["short"] * 0.30)
            # In a very obtuse triangle the opposite side can be much closer
            # than either ray endpoint. Keep the arc on the vertex side of it.
            for a, b in straight_segs:
                a, b = np.asarray(a), np.asarray(b)
                edge = b - a
                t = float(np.clip(np.dot(B - a, edge) / np.dot(edge, edge), 0, 1))
                near = a + t * edge - B
                clearance = float(np.linalg.norm(near))
                if clearance < 1e-6:  # the angle's own sides / incident lines
                    continue
                theta = math.atan2(float(near[1]), float(near[0]))
                along = ((theta - start) if delta > 0 else (start - theta)) % (2 * math.pi)
                if along <= abs(delta) + 1e-9:
                    outer = min(outer, clearance * 0.70)
            gap = min(4.0, outer / (count + 1))
            for index in range(count):
                r = outer - (count - 1 - index) * gap
                marks.append(f'<path class="arc" data-layer="{layer}" '
                             f'd="{_arc_path(B, r, start, delta)}"/>')
                samples = [B + r * np.array([math.cos(t), math.sin(t)])
                           for t in np.linspace(start, start + delta, max(12, int(abs(delta) * 18)))]
                reserve_path(samples)
        angle_texts.append((rec["text"], B, start + delta / 2, delta, outer, layer))

    # Equality ticks are strokes, not the character '/' (which changes with font).
    seen_ticks = set()

    def is_divided(pts) -> bool:
        pa, pb = np.array(Q[pts[0]]), np.array(Q[pts[1]])
        pt = pb - pa
        pl = float(np.linalg.norm(pt))
        if pl < 1e-9:
            return False
        for name, point in visible_q.items():
            if name in pts:
                continue
            q = np.asarray(point)
            frac_on = float(np.dot(q - pa, pt) / (pl * pl))
            if 0.05 < frac_on < 0.95 and abs(float(np.linalg.det(np.array([pt, q - pa])))) / pl < 1.0:
                return True
        return False

    # A group whose member is split by a visible point is not drawn at all: no
    # bracket, and no lone tick on the partner.
    skipped_groups = set()
    for m in getattr(d, "equal_marks", []):
        pts_ = m.get("pts", [])
        if len(pts_) == 2 and all(p in Q for p in pts_) and is_divided(pts_) \
                and not (mark_layer(m) == "aux" and not show_aux):
            skipped_groups.add((mark_layer(m), _count(m)))
    for m in getattr(d, "equal_marks", []):
        layer = mark_layer(m)
        if layer == "aux" and not show_aux:
            continue
        pts = m.get("pts", [])
        if len(pts) != 2 or any(p not in Q for p in pts):
            notes.append(f"SKIPPED_EQUAL_MARK: {pts}")
            continue
        count = _count(m)
        if (layer, count) in skipped_groups:
            continue
        key = (tuple(sorted(pts)), count)
        if key in seen_ticks:
            continue
        seen_ticks.add(key)
        a, b = (np.array(Q[p]) for p in pts)
        t = b - a
        length = float(np.linalg.norm(t))
        if length < 1e-9:
            notes.append(f"SKIPPED_EQUAL_MARK: {pts} нулевая длина")
            continue
        u = t / length
        n = np.array([-u[1], u[0]])
        # A tick directly on AB between A and an interior point D reads as
        # AD=... rather than AB=.... Span the *whole* AB on a short offset
        # dimension line whenever a visible named point divides the segment.
        divided = False
        for name, point in visible_q.items():
            if name in pts:
                continue
            q = np.asarray(point)
            frac_on = float(np.dot(q - a, t) / (length * length))
            deviation = abs(float(np.linalg.det(np.array([t, q - a])))) / length
            if 0.05 < frac_on < 0.95 and deviation < 1.0:
                divided = True
                break
        if divided:
            # No dimension bracket. A tick on one part of the segment would read as an
            # equality for that part only, so the whole group is not drawn (a lone tick
            # on the partner would look unpaired); the statement already gives it.
            continue
        gap, half = min(4.0, length / (count + 2)), min(5.0, length * 0.2)
        # Move a tick away from both point dots and crossing strokes. Merely
        # avoiding dots can put a tick directly over a transversal and make an
        # equality mark look like an unlabelled intersection.
        def tick_clearance(f):
            mid = a + t * f
            distances = [float(np.linalg.norm(mid - q)) for q in visible_q.values()]
            for start, end in px_segs:
                v = np.asarray(end) - np.asarray(start)
                den = float(v @ v)
                if den < 1e-12:
                    continue
                # The marked segment itself is not an obstacle.
                if (abs(float(np.linalg.det(np.array([t, v])))) < 1e-6 * length * math.sqrt(den)
                        and abs(float(np.linalg.det(np.array([t, np.asarray(start) - a]))))
                            < 2.0 * length):
                    continue
                fraction = float(np.clip(np.dot(mid - start, v) / den, 0, 1))
                distances.append(float(np.linalg.norm(mid - (np.asarray(start) + fraction * v))))
            return min(min(distances, default=18.0), 18.0)

        frac = max((0.5, 0.42, 0.58, 0.32, 0.68),
                   key=lambda f: (tick_clearance(f), -abs(f - 0.5)))
        for index in range(count):
            mid = a + t * frac + u * (index - (count - 1) / 2) * gap
            p, q = mid - n * half, mid + n * half
            marks.append(f'<path class="tick eqc-{count}" data-layer="{layer}" d="M {_f(p[0])} {_f(p[1])} '
                         f'L {_f(q[0])} {_f(q[1])}"/>')
            reserve_path([p, q])

    for text, B, middle, delta, outer, layer in angle_texts:
        box = _text_box(text, (0, 0), MARK_FS)
        halfdiag = math.hypot(box[2], box[3])
        # Text stays outside all nested arcs. Search radially first, then move
        # slightly off the bisector if another mark blocks it.
        candidates = []
        for offset in (0.0, -0.12, 0.12):
            theta = middle + offset * min(abs(delta), math.pi)
            direction = np.array([math.cos(theta), math.sin(theta)])
            for step in range(18):
                distance = outer + halfdiag + 5 + step * 9
                candidates.append((step * 0.11 + abs(offset) * 3, B + direction * distance))
        emit_text(text, candidates, layer)

    cen_px = np.mean(np.array(list(visible_q.values()), dtype=float), axis=0)
    for m in d.length_marks:
        layer = mark_layer(m)
        if layer == "aux" and not show_aux:
            continue
        pts = list(m.get("pts") or [])
        if len(pts) != 2 or any(t not in Q for t in pts):
            continue
        A, B = np.array(Q[pts[0]]), np.array(Q[pts[1]])
        t = B - A
        nt = float(np.linalg.norm(t))
        if nt < 1e-9:
            continue
        n = np.array([-t[1], t[0]]) / nt
        mid = (A + B) / 2
        text = _mark_text(m.get("text", ""))
        box = _text_box(text, (0, 0), MARK_FS)
        off = max(12.0, 0.035 * span_px, abs(n[0]) * box[2] + abs(n[1]) * box[3] + 4)
        candidates = []
        for frac in (0.5, 0.38, 0.62, 0.28, 0.72):
            for sgn in (1.0, -1.0):
                for extra in (0, 8, 18):
                    cand = A + t * frac + n * (off + extra) * sgn
                    interior = float(np.linalg.norm(cand - cen_px)) < float(np.linalg.norm(mid - cen_px))
                    preference = 1.0 * interior + abs(frac - 0.5) + extra * 0.02
                    candidates.append((preference, cand))
        emit_text(text, candidates, layer)

    # ---- слой labels: точки + подписи с выбором позиции из 8 направлений
    labels: list[str] = []
    hidden = set(d.hide_labels)
    placed: list[tuple[float, float, float, float]] = []
    all_px = list(visible_q.values())

    order = [p for p in plan.points if p in visible_q] + [p for p in visible_q if p not in set(plan.points)]
    # An unlabeled point whose only role is the radius witness of a circle is
    # an implementation detail: drawing its dot suggests a meaningful point.
    other_uses = set()
    for group in (d.segments, d.aux_segments, d.lines, d.rays, d.aux_lines, d.aux_rays,
                  d.extensions, d.aux_extensions, d.right_angles):
        for it in group:
            other_uses.update(it)
    for m in list(d.angle_marks) + list(d.length_marks) + list(d.equal_marks):
        other_uses.update(m.get("pts") or [])
    other_uses.update(c[0] for c in list(d.circles) + list(d.aux_circles) if c)
    other_uses.update(d.aux_points)
    radius_only = {c[1] for c in list(d.circles) + list(d.aux_circles) if len(c) > 1} \
        & hidden - other_uses
    for name in order:
        if name in radius_only:
            continue
        px, py = Q[name]
        layer = "aux" if name in aux_only else "main"
        labels.append(f'<circle class="pt" data-point="{_esc(name)}" data-layer="{layer}" '
                      f'cx="{_f(px)}" cy="{_f(py)}" r="{_f(PT_R)}"/>')
        geometry_boxes.append((px - PT_R - 1, py - PT_R - 1, px + PT_R + 1, py + PT_R + 1))
        if name in hidden:
            continue
        txt = _esc(name)
        box = _text_box(name, (0, 0), LABEL_FS)
        tw, th = box[2] * 2, box[3] * 2
        best: tuple[float, tuple[float, float, float, float], tuple[float, float]] | None = None
        for dx, dy, extra in ((dx, dy, extra) for extra in (0, 8, 18, 30) for dx, dy in DIRS8):
            ux, uy = dx, -dy          # мир -> пиксели: ось y инвертирована
            cx = px + ux * (LABEL_OFFSET + extra + abs(ux) * tw / 2)
            cy = py + uy * (LABEL_OFFSET + extra + abs(uy) * th / 2)
            rect = (cx - tw / 2, cy - th / 2, cx + tw / 2, cy + th / 2)
            pen = 0.0
            if not (2 <= rect[0] and rect[2] <= width - 2 and 2 <= rect[1] and rect[3] <= height - 2):
                pen += 6.0
            for a, b in px_segs + mark_segments:
                if _rect_seg_hit(rect, a, b):
                    pen += 4.0
            for r in placed:
                if _rects_overlap(rect, r):
                    pen += 5.0
            for q in all_px:
                if abs(q[0] - px) + abs(q[1] - py) > 1e-9 and _rect_has_point(rect, q):
                    pen += 3.0
            for mark_box in text_boxes + mark_boxes:
                if _rects_overlap(rect, mark_box):
                    pen += 12.0
            pen += 0.3 * abs(dx * dy) + extra * 0.025
            if best is None or pen < best[0]:
                best = (pen, rect, (cx, cy))
        assert best is not None
        pen, rect, (cx, cy) = best
        placed.append(rect)
        if pen > 0:
            notes.append(f"LABEL_COLLISION: подпись {name} размещена с компромиссом (штраф {pen:.1f})")
        labels.append(f'<text class="lab" data-point="{_esc(name)}" data-layer="{layer}" '
                      f'x="{_f(cx)}" y="{_f(cy + LABEL_FS * 0.35)}" '
                      f'text-anchor="middle">{txt}</text>')

    # ---- комментарии гейта
    if gate is not None:
        for f in list(getattr(gate, "failures", []) or []):
            notes.append(f"GATE_FAIL: {f}")
        for wr in list(getattr(gate, "warnings", []) or []):
            notes.append(f"GATE_WARN: {wr}")
        sc = getattr(gate, "score", None)
        if sc is not None:
            notes.append(f"GATE_SCORE: {float(sc):.3f}")

    # Expand the viewBox to the actual ink/text bounds. The requested CSS width
    # is retained; even long labels and exterior reflex-angle labels cannot clip.
    boxes = geometry_boxes + text_boxes + placed
    vx = min(0.0, min((b[0] - 6 for b in boxes), default=0.0))
    vy = min(0.0, min((b[1] - 6 for b in boxes), default=0.0))
    vw = max(float(width), max((b[2] + 6 for b in boxes), default=float(width))) - vx
    vh = max(float(height), max((b[3] + 6 for b in boxes), default=float(height))) - vy
    output_height = width * vh / vw
    comments = "\n".join(f"  <!-- {_esc(n).replace('--', '—')} -->" for n in notes)
    style = f"""  <style>
    .seg {{ stroke: {COL_MAIN}; stroke-width: 2; fill: none; stroke-linecap: round; }}
    .circ {{ stroke: {COL_MAIN}; stroke-width: 2; fill: none; }}
    .aux-seg, .aux-circ {{ stroke: {COL_AUX}; stroke-width: 1.5; fill: none;
      stroke-dasharray: 6 4; opacity: 0.6; }}
    .pt {{ fill: {COL_MAIN}; stroke: #ffffff; stroke-width: 0.8; }}
    .lab {{ font-family: {FONT}; font-style: italic; font-size: {LABEL_FS:.1f}px;
      fill: {COL_LABEL}; }}
    .mark {{ font-family: {FONT}; font-size: {MARK_FS:.1f}px; fill: {COL_MARK}; }}
    .arc, .rt, .tick {{ stroke: {COL_MARK}; stroke-width: 1.15; fill: none; stroke-linecap: round; }}
    .span {{ stroke: {COL_MARK}; stroke-width: 0.9; fill: none; opacity: 0.8; }}
  </style>"""
    # Правила цветов групп равенства идут ПОСЛЕ .seg/.tick: одинаковая
    # специфичность, побеждает последний — равные отрезки получают свой цвет.
    # Вставлять нужно ВНУТРЬ <style>: после </style> правило не применяется.
    eq_rules = "".join(f"\n    .eqc-{count} {{ stroke: {color}; }}"
                       for count, color in sorted(eq_color.items()))
    style = style.replace("  </style>", eq_rules + "\n  </style>")

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{_f(output_height)}" '
        f'viewBox="{_f(vx)} {_f(vy)} {_f(vw)} {_f(vh)}" font-family="{FONT}">',
        comments,
        style,
        f'  <rect x="{_f(vx)}" y="{_f(vy)}" width="{_f(vw)}" height="{_f(vh)}" fill="#ffffff"/>',
        '  <g id="main">' + "".join(main) + '</g>',
        '  <g id="aux">' + "".join(aux) + '</g>',
        '  <g id="labels">' + "".join(labels) + '</g>',
        '  <g id="marks">' + "".join(marks) + '</g>',
        '</svg>',
    ]
    return "\n".join(p for p in parts if p.strip())


def save_png(svg: str, path: str) -> str:
    """Пытается PNG через cairosvg; при ImportError сохраняет .svg. Никогда не падает."""
    d = os.path.dirname(os.path.abspath(path))
    if d:
        os.makedirs(d, exist_ok=True)
    try:
        import cairosvg  # type: ignore
    except ImportError:
        alt = path[:-4] + ".svg" if path.lower().endswith(".png") else path
        if not alt.lower().endswith(".svg"):
            alt += ".svg"
        with open(alt, "w", encoding="utf-8") as fh:
            fh.write(svg)
        return alt
    try:
        cairosvg.svg2png(bytestring=svg.encode("utf-8"), write_to=path)
        return path
    except Exception:
        alt = (path[:-4] if path.lower().endswith(".png") else path) + ".svg"
        with open(alt, "w", encoding="utf-8") as fh:
            fh.write(svg)
        return alt
