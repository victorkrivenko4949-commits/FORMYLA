"""Circle-family diagram generators."""
from __future__ import annotations

import math
from typing import Any, Dict

from matplotlib.figure import Figure

from . import primitives as P


def two_circles_external_tangent(params: Dict[str, Any]) -> Figure:
    r1 = float(params.get("r1", 1.6))
    r2 = float(params.get("r2", 1.0))
    d = r1 + r2
    o1 = (0.0, 0.0)
    o2 = (d, 0.0)
    t = (r1, 0.0)
    fig, ax = P.new_figure()
    P.circle(ax, o1, r1, label="ω₁")
    P.circle(ax, o2, r2, label="ω₂")
    P.point(ax, o1, "O₁", offset=(-0.40, -0.30))
    P.point(ax, o2, "O₂", offset=(0.15, -0.30))
    P.point(ax, t, "T", offset=(0.05, 0.25))
    P.segment(ax, o1, o2, linewidth=1.4)
    P.finalize(ax)
    return fig


def two_circles_internal_tangent(params: Dict[str, Any]) -> Figure:
    R = float(params.get("R", 2.2))
    r = float(params.get("r", 0.9))
    O = (0.0, 0.0)
    o2 = (R - r, 0.0)
    t = (R, 0.0)
    fig, ax = P.new_figure()
    P.circle(ax, O, R, label="Ω")
    P.circle(ax, o2, r, label="ω")
    P.point(ax, O, "O", offset=(-0.35, -0.30))
    P.point(ax, o2, "O′", offset=(0.10, -0.30))
    P.point(ax, t, "T", offset=(0.15, 0.20))
    P.segment(ax, O, t, linewidth=1.4)
    P.finalize(ax)
    return fig


def chord_with_inscribed_angle(params: Dict[str, Any]) -> Figure:
    R = float(params.get("R", 2.0))
    O = (0.0, 0.0)
    a_ang = math.radians(float(params.get("a_deg", 200.0)))
    b_ang = math.radians(float(params.get("b_deg", 340.0)))
    c_ang = math.radians(float(params.get("c_deg", 80.0)))
    A = (R * math.cos(a_ang), R * math.sin(a_ang))
    B = (R * math.cos(b_ang), R * math.sin(b_ang))
    C = (R * math.cos(c_ang), R * math.sin(c_ang))
    fig, ax = P.new_figure()
    P.circle(ax, O, R, label="ω")
    P.segment(ax, A, B)
    P.segment(ax, A, C)
    P.segment(ax, B, C)
    P.point(ax, A, "A", offset=(-0.35, -0.25))
    P.point(ax, B, "B", offset=(0.18, -0.25))
    P.point(ax, C, "C", offset=(-0.05, 0.20))
    P.angle_mark(ax, C, A, B, r=0.38, label="α")
    P.finalize(ax)
    return fig


def tangent_from_external_point(params: Dict[str, Any]) -> Figure:
    R = float(params.get("R", 1.6))
    d = float(params.get("d", 4.0))
    O = (0.0, 0.0)
    M = (d, 0.0)
    L = math.sqrt(d * d - R * R)
    # tangent points
    a = math.atan2(R, L)
    t1 = (R * math.sin(math.acos(R / d)), R * math.cos(math.acos(R / d)))
    # easier: tangent point coords using known formula
    tx = R * R / d
    ty = R * L / d
    T1 = (tx, ty)
    T2 = (tx, -ty)
    fig, ax = P.new_figure()
    P.circle(ax, O, R, label="ω")
    P.segment(ax, M, T1)
    P.segment(ax, M, T2)
    P.segment(ax, O, T1, linewidth=1.4)
    P.segment(ax, O, T2, linewidth=1.4)
    P.right_angle(ax, T1, O, M, size=0.20)
    P.right_angle(ax, T2, O, M, size=0.20)
    P.point(ax, O, "O", offset=(-0.30, -0.30))
    P.point(ax, M, "M", offset=(0.20, -0.20))
    P.point(ax, T1, "T₁", offset=(-0.15, 0.25))
    P.point(ax, T2, "T₂", offset=(-0.15, -0.40))
    P.finalize(ax)
    return fig


def two_intersecting_chords(params: Dict[str, Any]) -> Figure:
    R = 2.0
    O = (0.0, 0.0)
    A = (R * math.cos(math.radians(150)), R * math.sin(math.radians(150)))
    B = (R * math.cos(math.radians(-20)), R * math.sin(math.radians(-20)))
    C = (R * math.cos(math.radians(60)), R * math.sin(math.radians(60)))
    D = (R * math.cos(math.radians(-110)), R * math.sin(math.radians(-110)))
    fig, ax = P.new_figure()
    P.circle(ax, O, R, label="ω")
    P.segment(ax, A, B)
    P.segment(ax, C, D)
    # find intersection
    x1, y1 = A; x2, y2 = B; x3, y3 = C; x4, y4 = D
    den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    px = ((x1 * y2 - y1 * x2) * (x3 - x4) - (x1 - x2) * (x3 * y4 - y3 * x4)) / den
    py = ((x1 * y2 - y1 * x2) * (y3 - y4) - (y1 - y2) * (x3 * y4 - y3 * x4)) / den
    M = (px, py)
    P.point(ax, A, "A", offset=(-0.30, 0.20))
    P.point(ax, B, "B", offset=(0.15, -0.30))
    P.point(ax, C, "C", offset=(0.15, 0.20))
    P.point(ax, D, "D", offset=(-0.30, -0.30))
    P.point(ax, M, "P", offset=(0.15, 0.15))
    P.finalize(ax)
    return fig
