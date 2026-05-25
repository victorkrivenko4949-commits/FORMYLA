"""Combinatorial-geometry generators: grid layouts, point clouds, etc."""
from __future__ import annotations

from typing import Any, Dict

from matplotlib.figure import Figure

from . import primitives as P


def grid_of_points(params: Dict[str, Any]) -> Figure:
    n = int(params.get("n", 4))
    m = int(params.get("m", 4))
    fig, ax = P.new_figure()
    for i in range(n):
        for j in range(m):
            P.point(ax, (i, j))
    P.finalize(ax)
    return fig


def colored_squares_4x4(params: Dict[str, Any]) -> Figure:
    """4x4 board with diagonal squares highlighted — used for parity/invariant problems."""
    import matplotlib.patches as mpatches
    fig, ax = P.new_figure(width=6, height=6)
    n = int(params.get("n", 4))
    for i in range(n):
        for j in range(n):
            face = "lightgray" if (i + j) % 2 else "white"
            rect = mpatches.Rectangle((i, j), 1, 1, facecolor=face, edgecolor="black", linewidth=1.4)
            ax.add_patch(rect)
    ax.set_xlim(-0.4, n + 0.4)
    ax.set_ylim(-0.4, n + 0.4)
    P.finalize(ax, pad=0.1)
    return fig


def number_line_segment(params: Dict[str, Any]) -> Figure:
    a = float(params.get("a", 0.0))
    b = float(params.get("b", 8.0))
    label_a = str(params.get("label_a", "a"))
    label_b = str(params.get("label_b", "b"))
    fig, ax = P.new_figure(width=8, height=2.4)
    ax.axhline(0.0, color="black", linewidth=2.0)
    P.segment(ax, (a, 0), (b, 0))
    P.point(ax, (a, 0), label_a, offset=(-0.10, 0.30))
    P.point(ax, (b, 0), label_b, offset=(-0.10, 0.30))
    ax.set_xlim(a - 1.5, b + 1.5)
    ax.set_ylim(-1.5, 1.5)
    P.finalize(ax, pad=0.2)
    return fig
