"""Quadrilateral & polygon generators."""
from __future__ import annotations

import math
from typing import Any, Dict

from matplotlib.figure import Figure

from . import primitives as P


def parallelogram(params: Dict[str, Any]) -> Figure:
    a = (0.0, 0.0)
    b = (4.5, 0.0)
    c = (5.6, 2.6)
    d = (1.1, 2.6)
    fig, ax = P.new_figure()
    P.polyline(ax, [a, b, c, d], close=True)
    P.point(ax, a, "A", offset=(-0.30, -0.30))
    P.point(ax, b, "B", offset=(0.15, -0.30))
    P.point(ax, c, "C", offset=(0.15, 0.18))
    P.point(ax, d, "D", offset=(-0.30, 0.18))
    P.tick(ax, a, b, n=1)
    P.tick(ax, d, c, n=1)
    P.tick(ax, a, d, n=2)
    P.tick(ax, b, c, n=2)
    P.finalize(ax)
    return fig


def trapezoid(params: Dict[str, Any]) -> Figure:
    a = (0.0, 0.0)
    b = (5.0, 0.0)
    c = (4.0, 2.6)
    d = (1.2, 2.6)
    fig, ax = P.new_figure()
    P.polyline(ax, [a, b, c, d], close=True)
    P.point(ax, a, "A", offset=(-0.30, -0.30))
    P.point(ax, b, "B", offset=(0.15, -0.30))
    P.point(ax, c, "C", offset=(0.15, 0.18))
    P.point(ax, d, "D", offset=(-0.30, 0.18))
    P.finalize(ax)
    return fig


def cyclic_quadrilateral(params: Dict[str, Any]) -> Figure:
    R = 2.0
    O = (0.0, 0.0)
    angles_deg = params.get("angles", [120, 35, -40, -150])
    pts = [(R * math.cos(math.radians(t)), R * math.sin(math.radians(t))) for t in angles_deg]
    fig, ax = P.new_figure()
    P.circle(ax, O, R, label="описанная окружность ABCD")
    P.polyline(ax, pts, close=True)
    labels = ["A", "B", "C", "D"]
    offs = [(-0.30, 0.20), (0.18, 0.18), (0.18, -0.30), (-0.30, -0.30)]
    for p, l, o in zip(pts, labels, offs):
        P.point(ax, p, l, offset=o)
    P.finalize(ax)
    return fig


def tangential_quadrilateral(params: Dict[str, Any]) -> Figure:
    """Quadrilateral with inscribed circle. AB+CD = BC+AD."""
    a = (0.0, 0.0)
    b = (5.0, 0.0)
    c = (4.5, 3.0)
    d = (0.4, 3.0)
    # approximate inscribed circle: center = average, radius ~ half-min-distance to sides
    cx = (a[0] + b[0] + c[0] + d[0]) / 4
    cy = (a[1] + b[1] + c[1] + d[1]) / 4
    r = 1.05
    fig, ax = P.new_figure()
    P.polyline(ax, [a, b, c, d], close=True)
    P.circle(ax, (cx, cy), r, label="ω")
    P.point(ax, a, "A", offset=(-0.30, -0.30))
    P.point(ax, b, "B", offset=(0.18, -0.30))
    P.point(ax, c, "C", offset=(0.18, 0.18))
    P.point(ax, d, "D", offset=(-0.30, 0.18))
    P.point(ax, (cx, cy), "I", offset=(0.15, 0.10))
    P.finalize(ax)
    return fig


def regular_polygon(params: Dict[str, Any]) -> Figure:
    n = int(params.get("n", 6))
    R = float(params.get("R", 2.0))
    fig, ax = P.new_figure()
    pts = [(R * math.cos(2 * math.pi * k / n + math.pi / 2), R * math.sin(2 * math.pi * k / n + math.pi / 2))
           for k in range(n)]
    P.polyline(ax, pts, close=True)
    for k, p in enumerate(pts):
        lbl = chr(ord("A") + k) if k < 26 else f"P{k+1}"
        ox = 0.22 * math.cos(2 * math.pi * k / n + math.pi / 2)
        oy = 0.22 * math.sin(2 * math.pi * k / n + math.pi / 2)
        P.point(ax, p, lbl, offset=(ox, oy))
    P.finalize(ax)
    return fig
