# -*- coding: utf-8 -*-
"""Вид с построением: полная длина скрывается, если отмечены её части.

«В этой задаче можно было отметить только 6 3 4 8 отрезки»: когда доп.
построение даёт проверенные куски медианы (AG = 6, GA1 = 3), полная длина
AA1 = 9 в виде с построением дублирует их — показываем только куски.
В базовом виде (без построения) исходные полные длины остаются.

render.py — ядро, правим обёрткой (паттерн как у angle_marks_layout):
при show_aux=True из плана на время рендера убираются полные длины,
полностью покрытые aux-кусками; план не мутирует после вызова."""
from __future__ import annotations

import functools

MOVED_MARKER = "_aux_view_marks"


def install(renderer):
    original = renderer.render_svg
    if getattr(original, MOVED_MARKER, False):
        return False

    @functools.wraps(original)
    def render_svg(plan, sol, *args, **kwargs):
        # сигнатура render_svg(plan, sol, gate=None, show_aux=True, width=560):
        # позиционно show_aux — args[1] (args[0] — gate)
        show_aux = kwargs.get("show_aux")
        if show_aux is None:
            show_aux = bool(args[1]) if len(args) >= 2 else True
        if not show_aux:
            return original(plan, sol, *args, **kwargs)
        marks = getattr(getattr(plan, "draw", None), "length_marks", None)
        if not marks:
            return original(plan, sol, *args, **kwargs)
        coords = getattr(sol, "coords", None) or {}
        keep = [m for m in marks if not _covered_by_pieces(m, marks, coords)]
        backup = plan.draw.length_marks
        plan.draw.length_marks = keep
        try:
            svg = original(plan, sol, *args, **kwargs)
        finally:
            plan.draw.length_marks = backup
        return _disambiguate(svg, renderer, [m for m in marks if m.get("layer") == "aux"])

    setattr(render_svg, MOVED_MARKER, True)
    renderer.render_svg = render_svg
    return True


NS = "http://www.w3.org/2000/svg"


def _disambiguate(svg, renderer, aux_marks):
    """Тесное место: если числовая подпись результата налегла на линию — подпись
    выносится прочь от отрезка и получает однозначное имя «AG = 6» (голое «6»,
    оторванное от своего отрезка, читается неоднозначно). Только aux-метки —
    главное поведение рендера не трогаем."""
    if not isinstance(svg, str) or not svg.lstrip().startswith("<svg") or not aux_marks:
        return svg
    import math
    import xml.etree.ElementTree as ET
    try:
        ET.register_namespace("", NS)
        root = ET.fromstring(svg)
    except ET.ParseError:
        return svg
    fs = getattr(renderer, "MARK_FS", 12.5)
    text_box = renderer._text_box
    rect_seg_hit = renderer._rect_seg_hit
    numeric = []
    for m in aux_marks:
        try:
            float(str(m.get("text", "")).strip())
        except (TypeError, ValueError):
            continue
        if len(m.get("pts") or []) == 2:
            numeric.append(m)
    if not numeric:
        return svg
    width = float(root.get("width") or 0) or 1e9
    height = float(root.get("height") or 0) or 1e9
    dots = {e.get("data-point"): (float(e.get("cx")), float(e.get("cy")))
            for e in root.iter("{" + NS + "}circle") if e.get("data-point")}
    segs = []
    for el in root.iter("{" + NS + "}line"):
        try:
            segs.append(((float(el.get("x1")), float(el.get("y1"))),
                         (float(el.get("x2")), float(el.get("y2")))))
        except (TypeError, ValueError):
            continue
    texts = []
    for el in root.iter("{" + NS + "}text"):
        if el.get("x") is None or el.get("y") is None:
            continue
        content = (el.text or "") + "".join(t.text or "" for t in el)
        texts.append((el, content.strip(), float(el.get("x")), float(el.get("y"))))
    changed = False
    for m in numeric:
        plain = str(m.get("text")).strip()
        cand = [t for t in texts if t[1] == plain]
        if len(cand) != 1:
            continue                       # не нашли однозначно — не трогаем
        el, _, x, y = cand[0]
        rect = text_box(plain, (x, y - fs * 0.35), fs)
        if not any(rect_seg_hit(rect, a, b) for a, b in segs):
            continue                       # чисто — имя не нужно
        p0, p1 = m["pts"]
        named = f"{p0}{p1} = {plain}"
        # вынос: перпендикулярно своему отрезку прочь от линии
        ux, uy = 0.0, -1.0
        if p0 in dots and p1 in dots:
            dx, dy = dots[p1][0] - dots[p0][0], dots[p1][1] - dots[p0][1]
            ln = math.hypot(dx, dy)
            if ln > 1e-9:
                ux, uy = -dy / ln, dx / ln
                if (x - dots[p0][0]) * ux + (y - dots[p0][1]) * uy < 0:
                    ux, uy = -ux, -uy
        best = (x, y)
        for step in range(1, 13):
            nx, ny = x + ux * 6 * step, y + uy * 6 * step
            nrect = text_box(named, (nx, ny - fs * 0.35), fs)
            if not (2 <= nrect[0] and nrect[2] <= width - 2 and
                    2 <= nrect[1] and nrect[3] <= height - 2):
                break
            best = (nx, ny)
            if not any(rect_seg_hit(nrect, a, b) for a, b in segs):
                break
        el.text = named
        for t in el.findall("{" + NS + "}tspan"):
            el.remove(t)
        el.set("x", f"{best[0]:.6f}")
        el.set("y", f"{best[1]:.6f}")
        changed = True
    return ET.tostring(root, encoding="unicode") if changed else svg


def _on_segment(name_p, name_q, a, b, coords):
    """Оба конца (p, q) лежат на отрезке [a, b] (в долях: t_p, t_q)."""
    import math
    pa, pb = coords.get(a), coords.get(b)
    pp, pq = coords.get(name_p), coords.get(name_q)
    if pa is None or pb is None or pp is None or pq is None:
        return None
    ax, ay = float(pa[0]), float(pa[1])
    bx, by = float(pb[0]), float(pb[1])
    dx, dy = bx - ax, by - ay
    length = math.hypot(dx, dy)
    if length < 1e-12:
        return None
    out = []
    for pt in (pp, pq):
        t = ((float(pt[0]) - ax) * dx + (float(pt[1]) - ay) * dy) / (length * length)
        d = abs((float(pt[0]) - ax) * dy - (float(pt[1]) - ay) * dx) / length
        if d > 1e-6 * length or not (-1e-9 <= t <= 1.0 + 1e-9):
            return None
        out.append(min(1.0, max(0.0, t)))
    return out


def _covered_by_pieces(mark, marks, coords):
    """Полная длина на [a,b] покрыта aux-кусками: куски с обоими концами на [a,b]
    накрывают весь отрезок от a до b без дыр. Годятся только числовые куски —
    символическая подпись «x» ничего не доказывает и полную длину не заменяет."""
    import math
    pts = list(mark.get("pts") or [])
    if len(pts) != 2 or mark.get("layer") == "aux":
        return False
    a, b = pts
    intervals = []
    for m in marks:
        if m is mark or m.get("layer") != "aux":
            continue
        mpts = list(m.get("pts") or [])
        if len(mpts) != 2:
            continue
        try:
            float(str(m.get("text", "")).strip())
        except (TypeError, ValueError):
            continue                       # не число — не замена
        ts = _on_segment(mpts[0], mpts[1], a, b, coords)
        if ts is None:
            continue
        intervals.append(sorted(ts))
    if not intervals:
        return False
    intervals.sort()
    covered_to = 0.0
    for lo, hi in intervals:
        if lo > covered_to + 1e-9:      # дыра между кусками
            return False
        covered_to = max(covered_to, hi)
        if covered_to >= 1.0 - 1e-9:
            return True
    return covered_to >= 1.0 - 1e-9
