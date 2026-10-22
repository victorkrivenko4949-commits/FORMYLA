# -*- coding: utf-8 -*-
"""Широкий угол (>= 110°): компактная дуга и подпись у дуги, а не за стороной.

Дуга угла рисуется радиусом arc_r (~18–30px). Для тупого угла это съедает
заметную часть чертежа («дуга должна быть меньше»). Хуже того, подпись ищет
место радиально от вершины со стартовым отступом outer + halfdiag + 5:
для угла 150° между медианами этот отступ выводит прямоугольник подписи ЗА
противоположную сторону (AB), шаги 0–1 получают штраф за пересечение
отрезка, и подпись прыгает НАД сторону — «слетело 150».

render.py — ядро, правим обёрткой (post-processing готового SVG):

1) дуга широкого угла сжимается до ~0.62 радиуса (не меньше 12px), засечки
   равных углов на ней переезжают вместе с ней; если у вершины несколько
   дуг (группа неоднозначна) — ничего не трогаем;
2) подпись угла возвращается к дуге: ищем первое свободное окно ВПЛОТНУЮ
   к дуге (отступ halfdiag*0.55 вместо halfdiag) и переносим подпись
   туда, если она улетела дальше окна + 10px. Если окно не найдено —
   подпись не трогаем (безопасный отказ).
"""
from __future__ import annotations

import functools
import math
import re
import xml.etree.ElementTree as ET

NS = "http://www.w3.org/2000/svg"

WIDE_ANGLE_DEG = 110.0        # с какого угла дуга считается «широкой»
ARC_SHRINK = 0.62             # новый радиус = старый * 0.62
MIN_ARC_R = 12.0              # но не меньше 12px
MOVED_MARKER = "_angle_marks_layout"


def install(renderer):
    original = renderer.render_svg
    if getattr(original, MOVED_MARKER, False):
        return False

    @functools.wraps(original)
    def render_svg(plan, sol, *args, **kwargs):
        svg = original(plan, sol, *args, **kwargs)
        return _adjust(svg, renderer, plan, sol)

    setattr(render_svg, MOVED_MARKER, True)
    renderer.render_svg = render_svg
    return True


# ── разбор SVG ────────────────────────────────────────────────────────────

def screen_coords(root, p):
    """Экранная система координат: аффинная рамка мир -> экран по двум самым
    удалённым точкам чертежа (те же круги, что и в svg_presentation._frame).
    Возвращает словарь имя -> (x, y) или None. Используется и тестами."""
    dots = {e.get("data-point"): (float(e.get("cx")), float(e.get("cy")))
            for e in root.iter("{" + NS + "}circle") if e.get("data-point") in p}
    if len(dots) < 2:
        return None
    a, b = max(((a, b) for i, a in enumerate(dots) for b in dots if b > a),
               key=lambda q: math.dist(dots[q[0]], dots[q[1]]))
    length = math.dist(p[a], p[b])
    if length <= 1e-12:
        return None
    scale = math.dist(dots[a], dots[b]) / length
    return {n: (dots[a][0] + scale * (v[0] - p[a][0]),
                dots[a][1] - scale * (v[1] - p[a][1])) for n, v in p.items()}


def _arcs(root):
    """Список (element, start, end, r, large, sweep) для path.arc."""
    out = []
    for el in root.iter("{" + NS + "}path"):
        if "arc" not in (el.get("class") or "").split():
            continue
        t = (el.get("d") or "").split()
        if len(t) != 11 or t[0] != "M" or t[3] != "A":
            continue
        try:
            r = float(t[4])
            if r <= 0 or abs(r - float(t[5])) > 1e-5 or float(t[6]) != 0:
                continue
            out.append((el, (float(t[1]), float(t[2])), (float(t[9]), float(t[10])),
                        r, int(t[7]), int(t[8])))
        except ValueError:
            continue
    return out


def _arc_center(start, end, r, vertex):
    """Центр дуги: точка на расстоянии r от обоих концов, ближайшая к вершине."""
    dx, dy = end[0] - start[0], end[1] - start[1]
    d = math.hypot(dx, dy)
    if d < 1e-9 or d > 2 * r + 1e-9:
        return None
    h2 = r * r - (d / 2) ** 2
    h = math.sqrt(h2) if h2 >= 0 else 0.0
    mx, my = (start[0] + end[0]) / 2, (start[1] + end[1]) / 2
    nx, ny = -dy / d, dx / d
    cands = ((mx + h * nx, my + h * ny), (mx - h * nx, my - h * ny))
    return min(cands, key=lambda c: math.dist(c, vertex))


def _arc_samples(center, start, end, r, sweep, n=24):
    """Полилиния дуги (для проверки столкновений подписи)."""
    a0 = math.atan2(start[1] - center[1], start[0] - center[0])
    a1 = math.atan2(end[1] - center[1], end[0] - center[0])
    delta = (a1 - a0) % (2 * math.pi) if sweep else -((a0 - a1) % (2 * math.pi))
    return [(center[0] + r * math.cos(a0 + delta * i / n),
             center[1] + r * math.sin(a0 + delta * i / n)) for i in range(n + 1)]


def _move_ticks(root, vertex, old_r, new_r, bisector):
    """Засечки равных углов стоят на старом радиусе дуги — переезжают вместе с ней.

    finish_svg рисует их полилинией class="arc" с data-kind="angle-equality-tick";
    середина такой засечки лежит на расстоянии ~old_r от вершины. Сдвигаем
    каждую вдоль биссектрисы на (new_r - old_r)."""
    delta = (bisector[0] * (new_r - old_r), bisector[1] * (new_r - old_r))
    for el in root.iter("{" + NS + "}path"):
        if el.get("data-kind") != "angle-equality-tick":
            continue
        nums = [float(t) for t in (el.get("d") or "").split()
                if re.fullmatch(r"-?\d+(\.\d+)?", t)]
        if len(nums) < 6:
            continue
        pts = [(nums[i], nums[i + 1]) for i in range(0, 6, 2)]
        mid = pts[1] if len(pts) > 2 else pts[0]
        if abs(math.dist(mid, vertex) - old_r) > 8:
            continue                       # засечка чужой дуги
        el.set("d", "M " + " L ".join(
            f"{x + delta[0]:.6f} {y + delta[1]:.6f}" for x, y in pts))


def _adjust(svg, renderer, plan, sol):
    if not isinstance(svg, str) or not svg.lstrip().startswith("<svg"):
        return svg
    ET.register_namespace("", NS)
    try:
        root = ET.fromstring(svg)
    except ET.ParseError:
        return svg
    d = getattr(plan, "draw", None)
    marks = list(getattr(d, "angle_marks", []) or []) if d is not None else []
    if not marks:
        return svg
    p = {n: (float(v[0]), float(v[1])) for n, v in (sol.coords or {}).items()
         if len(v) >= 2 and all(math.isfinite(float(x)) for x in v[:2])}
    frame = screen_coords(root, p)
    if frame is None:
        return svg
    q = frame

    fs = getattr(renderer, "MARK_FS", 12.5)
    text_box = renderer._text_box
    rect_seg_hit = renderer._rect_seg_hit
    rects_overlap = renderer._rects_overlap

    width = float(root.get("width") or 0) or 1e9
    height = float(root.get("height") or 0) or 1e9

    # статические препятствия: отрезки чертежа, точки, чужие подписи
    segments = []
    for el in root.iter("{" + NS + "}line"):
        try:
            segments.append(((float(el.get("x1")), float(el.get("y1"))),
                             (float(el.get("x2")), float(el.get("y2")))))
        except (TypeError, ValueError):
            continue
    points = [(float(e.get("cx")), float(e.get("cy")))
              for e in root.iter("{" + NS + "}circle") if e.get("data-point")]
    texts = []
    for el in root.iter("{" + NS + "}text"):
        if el.get("x") is None or el.get("y") is None:
            continue
        content = (el.text or "") + "".join(t.text or "" for t in el)
        texts.append((el, content, float(el.get("x")), float(el.get("y"))))

    arcs = _arcs(root)
    changed = False

    for m in marks:
        pts = m.get("pts") or []
        text = str(m.get("text") or "").strip()
        if len(pts) != 3 or not text or any(n not in q for n in pts):
            continue
        v0, v1, v2 = q[pts[0]], q[pts[1]], q[pts[2]]
        u1 = (v0[0] - v1[0], v0[1] - v1[1])
        u2 = (v2[0] - v1[0], v2[1] - v1[1])
        l1, l2 = math.hypot(*u1), math.hypot(*u2)
        if l1 < 1e-9 or l2 < 1e-9:
            continue
        cosang = max(-1.0, min(1.0, (u1[0] * u2[0] + u1[1] * u2[1]) / (l1 * l2)))
        if math.degrees(math.acos(cosang)) < WIDE_ANGLE_DEG:
            continue                      # узкий угол — прежнее поведение
        # своя дуга: центр совпадает с вершиной. Если у вершины несколько дуг
        # (две отметки на одном угле, концентрические дуги) — группа
        # неоднозначна, ничего не сжимаем и не двигаем.
        own = [(el, s, e, r, lg, sw, c) for el, s, e, r, lg, sw in arcs
               for c in [_arc_center(s, e, r, v1)] if c and math.dist(c, v1) < 6]
        if len(own) != 1:
            continue
        el, s, e, r, large, sweep, center = own[0]

        # биссектриса НАРИСОВАННОЙ дуги (не лучей: дуга бывает в вертикальном углу)
        mid = _arc_samples(v1, s, e, r, sweep, 2)
        b = (mid[1][0] - v1[0], mid[1][1] - v1[1])
        bl = math.hypot(*b)
        if bl < 1e-9:
            continue
        b = (b[0] / bl, b[1] / bl)

        # 1) компактная дуга + перенос засечек равных углов (одной группой)
        new_r = max(MIN_ARC_R, min(r, r * ARC_SHRINK))
        if new_r < r - 0.5:
            ns = (v1[0] + (s[0] - v1[0]) / r * new_r, v1[1] + (s[1] - v1[1]) / r * new_r)
            ne = (v1[0] + (e[0] - v1[0]) / r * new_r, v1[1] + (e[1] - v1[1]) / r * new_r)
            el.set("d", f"M {ns[0]:.6f} {ns[1]:.6f} A {new_r:.6f} {new_r:.6f} "
                        f"0 {large} {sweep} {ne[0]:.6f} {ne[1]:.6f}")
            _move_ticks(root, v1, r, new_r, b)
            s, e, r = ns, ne, new_r
            changed = True

        # 2) подпись — в первое свободное окно у дуги
        cand = [t for t in texts if t[1].strip() == text]
        if not cand:
            continue
        label = min(cand, key=lambda t: math.dist((t[2], t[3] - fs * 0.35), v1))
        lx, ly = label[2], label[3] - fs * 0.35          # базовая точка текста
        cur_d = math.dist((lx, ly), v1)
        x0, y0, x1, y1 = text_box(text, (0, 0), fs)
        halfdiag = math.hypot(x1 - x0, y1 - y0) / 2
        arc_pol = _arc_samples(v1, s, e, r, sweep)
        arc_segs = list(zip(arc_pol, arc_pol[1:]))

        target = None
        for step in range(10):
            dist = r + halfdiag * 0.55 + 3 + step * 5
            tp = (v1[0] + b[0] * dist, v1[1] + b[1] * dist)
            rect = text_box(text, tp, fs)
            if not (2 <= rect[0] and rect[2] <= width - 2 and
                    2 <= rect[1] and rect[3] <= height - 2):
                continue
            hit = (any(rect_seg_hit(rect, a, b2) for a, b2 in segments + arc_segs)
                   or any(rects_overlap(rect, text_box(c, (tx, ty - fs * 0.35), fs))
                          for _, c, tx, ty in texts if c.strip() != text)
                   or any(rect_seg_hit(rect, pt, (pt[0] + .01, pt[1])) for pt in points))
            if not hit:
                target = tp
                break
        if target is not None and cur_d > math.dist(target, v1) + 10:
            label[0].set("x", f"{target[0]:.6f}")
            label[0].set("y", f"{target[1] + fs * 0.35:.6f}")
            changed = True

    if not changed:
        return svg
    return ET.tostring(root, encoding="unicode")
