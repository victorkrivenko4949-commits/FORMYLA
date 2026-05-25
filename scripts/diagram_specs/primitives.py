"""Shared drawing primitives for matplotlib-based geometric diagrams.

All public helpers operate on a given Axes object and use the strict
FORMYLA style: black 2px lines, sans-serif 18-22px labels, single Latin
letters for vertices, white background, no chartjunk.
"""
from __future__ import annotations

import math
from typing import Iterable, Sequence, Tuple

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.patches import Arc, Circle, FancyArrowPatch, Polygon

LINE_KW = dict(color="black", linewidth=2.0, solid_capstyle="round")
DASH_KW = dict(color="black", linewidth=1.6, linestyle=(0, (5, 4)))
LABEL_KW = dict(fontsize=20, color="black", family="DejaVu Sans")
SMALL_LABEL_KW = dict(fontsize=16, color="black", family="DejaVu Sans")
POINT_KW = dict(color="black", s=22, zorder=5)

Point = Tuple[float, float]


def new_figure(width: float = 6.0, height: float = 6.0, dpi: int = 160) -> Tuple[Figure, Axes]:
    fig, ax = plt.subplots(figsize=(width, height), dpi=dpi)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.margins(0.18)
    return fig, ax


def finalize(ax: Axes, pad: float = 0.18) -> None:
    """Apply consistent margins so labels never touch the boundary."""
    ax.set_aspect("equal")
    ax.axis("off")
    ax.margins(pad)


def segment(ax: Axes, p: Point, q: Point, **kw) -> None:
    style = {**LINE_KW, **kw}
    ax.plot([p[0], q[0]], [p[1], q[1]], **style)


def dashed(ax: Axes, p: Point, q: Point, **kw) -> None:
    style = {**DASH_KW, **kw}
    ax.plot([p[0], q[0]], [p[1], q[1]], **style)


def polyline(ax: Axes, pts: Sequence[Point], close: bool = False, **kw) -> None:
    style = {**LINE_KW, **kw}
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    if close:
        xs.append(xs[0])
        ys.append(ys[0])
    ax.plot(xs, ys, **style)


def point(ax: Axes, p: Point, label: str | None = None, offset: Point = (0.08, 0.08), **kw) -> None:
    style = {**POINT_KW, **kw}
    ax.scatter([p[0]], [p[1]], **style)
    if label:
        ax.text(p[0] + offset[0], p[1] + offset[1], label, **LABEL_KW)


def circle(ax: Axes, center: Point, radius: float, label: str | None = None,
           label_offset: Point = (0.0, 0.0), **kw) -> None:
    style = {**LINE_KW, "fill": False}
    style.update(kw)
    style.pop("solid_capstyle", None)
    c = Circle(center, radius, **style)
    ax.add_patch(c)
    if label:
        lx = center[0] + radius * 0.75 + label_offset[0]
        ly = center[1] + radius * 0.75 + label_offset[1]
        ax.text(lx, ly, label, **LABEL_KW)


def arc(ax: Axes, center: Point, radius: float, t0: float, t1: float, **kw) -> None:
    style = {**LINE_KW}
    style.update(kw)
    style.pop("solid_capstyle", None)
    a = Arc(center, 2 * radius, 2 * radius, angle=0, theta1=math.degrees(t0), theta2=math.degrees(t1), **style)
    ax.add_patch(a)


def angle_mark(ax: Axes, vertex: Point, p1: Point, p2: Point, r: float = 0.35,
               label: str | None = None) -> None:
    """Small arc at `vertex` between rays to p1 and p2, with optional label."""
    a1 = math.atan2(p1[1] - vertex[1], p1[0] - vertex[0])
    a2 = math.atan2(p2[1] - vertex[1], p2[0] - vertex[0])
    if a2 < a1:
        a1, a2 = a2, a1
    if a2 - a1 > math.pi:
        a1, a2 = a2, a1 + 2 * math.pi
    arc(ax, vertex, r, a1, a2, linewidth=1.4)
    if label:
        am = (a1 + a2) / 2
        lx = vertex[0] + (r + 0.2) * math.cos(am)
        ly = vertex[1] + (r + 0.2) * math.sin(am)
        ax.text(lx, ly, label, ha="center", va="center", **SMALL_LABEL_KW)


def right_angle(ax: Axes, vertex: Point, p1: Point, p2: Point, size: float = 0.28) -> None:
    """Small square marking a right angle at `vertex`."""
    v = np.array(vertex)
    a = np.array(p1) - v
    b = np.array(p2) - v
    a = a / (np.linalg.norm(a) + 1e-12) * size
    b = b / (np.linalg.norm(b) + 1e-12) * size
    pts = [v + a, v + a + b, v + b]
    xs = [pts[0][0], pts[1][0], pts[2][0]]
    ys = [pts[0][1], pts[1][1], pts[2][1]]
    ax.plot(xs, ys, color="black", linewidth=1.6)


def tick(ax: Axes, p: Point, q: Point, n: int = 1, size: float = 0.12) -> None:
    """Equal-length tick marks across the midpoint of segment pq."""
    midx = (p[0] + q[0]) / 2
    midy = (p[1] + q[1]) / 2
    dx, dy = q[0] - p[0], q[1] - p[1]
    L = math.hypot(dx, dy)
    if L < 1e-9:
        return
    nx, ny = -dy / L, dx / L
    spacing = 0.06
    start = midx - (n - 1) * spacing * dx / L / 2, midy - (n - 1) * spacing * dy / L / 2
    for i in range(n):
        cx = start[0] + i * spacing * dx / L
        cy = start[1] + i * spacing * dy / L
        ax.plot([cx - size * nx, cx + size * nx], [cy - size * ny, cy + size * ny],
                color="black", linewidth=1.6)


def circumcircle(a: Point, b: Point, c: Point) -> Tuple[Point, float]:
    """Return (center, radius) of the circumscribed circle of triangle abc."""
    ax_, ay = a
    bx, by = b
    cx, cy = c
    d = 2.0 * (ax_ * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-12:
        raise ValueError("degenerate triangle")
    ux = ((ax_ ** 2 + ay ** 2) * (by - cy) + (bx ** 2 + by ** 2) * (cy - ay)
          + (cx ** 2 + cy ** 2) * (ay - by)) / d
    uy = ((ax_ ** 2 + ay ** 2) * (cx - bx) + (bx ** 2 + by ** 2) * (ax_ - cx)
          + (cx ** 2 + cy ** 2) * (bx - ax_)) / d
    r = math.hypot(ax_ - ux, ay - uy)
    return (ux, uy), r


def incircle(a: Point, b: Point, c: Point) -> Tuple[Point, float]:
    A = math.hypot(b[0] - c[0], b[1] - c[1])
    B = math.hypot(a[0] - c[0], a[1] - c[1])
    C = math.hypot(a[0] - b[0], a[1] - b[1])
    s = A + B + C
    ix = (A * a[0] + B * b[0] + C * c[0]) / s
    iy = (A * a[1] + B * b[1] + C * c[1]) / s
    p = s / 2
    area = abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])) / 2
    r = area / p
    return (ix, iy), r


def midpoint(p: Point, q: Point) -> Point:
    return ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
