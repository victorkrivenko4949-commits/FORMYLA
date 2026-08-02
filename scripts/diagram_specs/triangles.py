"""Triangle-family diagram generators."""
from __future__ import annotations

import math
from typing import Any, Dict

from matplotlib.figure import Figure

from . import primitives as P


def triangle_with_circumcircle(params: Dict[str, Any]) -> Figure:
    """Triangle ABC with its circumscribed circle ω. Label format strict.

    Params:
        a, b, c: optional vertex coordinates; default a non-degenerate acute triangle
        label_circle: caption for the circle (default 'ω')
    """
    a = tuple(params.get("a", (0.0, 0.0)))
    b = tuple(params.get("b", (4.0, 0.0)))
    c = tuple(params.get("c", (1.4, 3.0)))
    lbl_w = params.get("label_circle", "ω")
    fig, ax = P.new_figure()
    o, r = P.circumcircle(a, b, c)
    P.circle(ax, o, r, label=lbl_w)
    P.polyline(ax, [a, b, c], close=True)
    P.point(ax, a, "A", offset=(-0.25, -0.30))
    P.point(ax, b, "B", offset=(0.15, -0.30))
    P.point(ax, c, "C", offset=(-0.05, 0.18))
    P.point(ax, o, "O", offset=(0.10, 0.10))
    P.finalize(ax)
    return fig


def triangle_with_incircle(params: Dict[str, Any]) -> Figure:
    a = tuple(params.get("a", (0.0, 0.0)))
    b = tuple(params.get("b", (5.0, 0.0)))
    c = tuple(params.get("c", (1.6, 3.2)))
    lbl_w = params.get("label_circle", "ω")
    fig, ax = P.new_figure()
    i, r = P.incircle(a, b, c)
    P.circle(ax, i, r, label=lbl_w)
    P.polyline(ax, [a, b, c], close=True)
    P.point(ax, a, "A", offset=(-0.25, -0.30))
    P.point(ax, b, "B", offset=(0.15, -0.30))
    P.point(ax, c, "C", offset=(-0.05, 0.18))
    P.point(ax, i, "I", offset=(0.10, 0.10))
    P.finalize(ax)
    return fig


def triangle_with_median(params: Dict[str, Any]) -> Figure:
    a = tuple(params.get("a", (0.0, 0.0)))
    b = tuple(params.get("b", (4.5, 0.0)))
    c = tuple(params.get("c", (1.2, 2.8)))
    fig, ax = P.new_figure()
    P.polyline(ax, [a, b, c], close=True)
    m = P.midpoint(b, c)
    P.dashed(ax, a, m)
    P.point(ax, a, "A", offset=(-0.25, -0.30))
    P.point(ax, b, "B", offset=(0.15, -0.30))
    P.point(ax, c, "C", offset=(-0.05, 0.18))
    P.point(ax, m, "M", offset=(0.15, 0.10))
    P.tick(ax, b, m, n=1)
    P.tick(ax, m, c, n=1)
    P.finalize(ax)
    return fig


def triangle_with_altitude(params: Dict[str, Any]) -> Figure:
    a = tuple(params.get("a", (0.0, 0.0)))
    b = tuple(params.get("b", (5.0, 0.0)))
    c = tuple(params.get("c", (1.8, 2.6)))
    fig, ax = P.new_figure()
    P.polyline(ax, [a, b, c], close=True)
    # Foot of altitude from C onto AB
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = ((c[0] - a[0]) * dx + (c[1] - a[1]) * dy) / (dx * dx + dy * dy)
    h = (a[0] + t * dx, a[1] + t * dy)
    P.dashed(ax, c, h)
    P.right_angle(ax, h, a, c, size=0.22)
    P.point(ax, a, "A", offset=(-0.25, -0.30))
    P.point(ax, b, "B", offset=(0.15, -0.30))
    P.point(ax, c, "C", offset=(-0.05, 0.18))
    P.point(ax, h, "H", offset=(0.10, -0.30))
    P.finalize(ax)
    return fig


def right_triangle_with_hypotenuse_circle(params: Dict[str, Any]) -> Figure:
    """Right triangle with circle on the hypotenuse as a diameter."""
    a = tuple(params.get("a", (0.0, 0.0)))
    b = tuple(params.get("b", (4.0, 0.0)))
    c = tuple(params.get("c", (0.0, 3.0)))
    fig, ax = P.new_figure()
    P.polyline(ax, [a, b, c], close=True)
    P.right_angle(ax, a, b, c)
    o = P.midpoint(b, c)
    r = math.hypot(b[0] - c[0], b[1] - c[1]) / 2
    P.circle(ax, o, r, label="окружность с диаметром BC")
    P.point(ax, a, "A", offset=(-0.30, -0.30))
    P.point(ax, b, "B", offset=(0.15, -0.30))
    P.point(ax, c, "C", offset=(-0.30, 0.18))
    P.point(ax, o, "O", offset=(0.15, 0.10))
    P.finalize(ax)
    return fig


def isoceles_triangle(params: Dict[str, Any]) -> Figure:
    base = float(params.get("base", 4.0))
    height = float(params.get("height", 3.2))
    a = (-base / 2, 0.0)
    b = (base / 2, 0.0)
    c = (0.0, height)
    fig, ax = P.new_figure()
    P.polyline(ax, [a, b, c], close=True)
    P.tick(ax, a, c, n=1)
    P.tick(ax, b, c, n=1)
    P.point(ax, a, "A", offset=(-0.30, -0.30))
    P.point(ax, b, "B", offset=(0.18, -0.30))
    P.point(ax, c, "C", offset=(-0.05, 0.18))
    P.finalize(ax)
    return fig
