# -*- coding: utf-8 -*-
"""
Geometry renderer: turns a strict JSON "spec" into a PNG drawing.

The spec is intentionally low-level — coordinates are already computed
(by services.geometry_spec or by the caller). The renderer's job is to
produce a clean, olympiad-grade black-and-white diagram.

Spec format
-----------
{
  "vertices": [
      {"name": "A", "x": 0.0, "y": 0.0, "label_offset": [0, 0.4]},
      {"name": "B", "x": 5.0, "y": 0.0},
      {"name": "C", "x": 3.5, "y": 6.06}
  ],
  "segments": [
      {"from": "A", "to": "B", "label": "5"},
      {"from": "A", "to": "C", "label": "7"},
      {"from": "B", "to": "C"}
  ],
  "angles": [          # arc + label at vertex
      {"at": "A", "from": "B", "to": "C", "label": "60°", "radius": 0.6}
  ],
  "right_angles": [    # tiny square marker
      {"at": "B", "from": "A", "to": "C", "size": 0.3}
  ],
  "equal_segments": [  # group of segments with the same tick count
      {"segments": [["A","M"], ["M","B"]], "ticks": 1}
  ],
  "equal_angles": [    # double-arc marks for equal angles
      {"angles": [{"at":"A","from":"B","to":"C"},
                  {"at":"B","from":"A","to":"C"}], "arcs": 2, "radius": 0.5}
  ],
  "circles": [
      {"center": "O", "radius": 3.0, "label": null}
  ],
  "title": null        # not drawn; kept for debugging
}

Renderer guarantees
-------------------
- Pure B/W on a true #FFFFFF background, 1024×1024 PNG.
- Sans-serif labels, no shadows / gradients / watermarks.
- Vertex names are placed automatically away from incident segments
  unless `label_offset` is provided.
- Auto-fit: scales & centers the whole figure with a small margin.
"""

from __future__ import annotations

import io
import logging
import math
from typing import Dict, List, Tuple, Optional

import matplotlib
matplotlib.use("Agg")  # headless backend (CRITICAL for Flask workers)
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Arc

logger = logging.getLogger(__name__)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _unit(vec: Tuple[float, float]) -> Tuple[float, float]:
    x, y = vec
    n = math.hypot(x, y)
    if n < 1e-9:
        return (0.0, 0.0)
    return (x / n, y / n)


def _angle_deg(p_center, p_ref) -> float:
    """Angle of vector (center → ref) in degrees, normalised to [0, 360)."""
    dx = p_ref[0] - p_center[0]
    dy = p_ref[1] - p_center[1]
    a = math.degrees(math.atan2(dy, dx))
    return a % 360.0


def _shortest_arc(a_start: float, a_end: float) -> Tuple[float, float]:
    """
    Returns (theta1, theta2) such that the arc drawn by
    matplotlib.patches.Arc goes the SHORT way from a_start to a_end.
    theta1 < theta2 always (matplotlib draws CCW from theta1 to theta2).
    """
    diff = (a_end - a_start) % 360.0
    if diff > 180.0:
        # short way is the other direction
        return (a_end, a_end + (360.0 - diff))
    return (a_start, a_start + diff)


def _midpoint(p1, p2):
    return ((p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0)


def _normal(p1, p2) -> Tuple[float, float]:
    """Unit vector perpendicular to p1→p2, rotated 90° CCW."""
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    return _unit((-dy, dx))


def _auto_label_offset(pts: Dict[str, Tuple[float, float]],
                       name: str,
                       segments: List[dict],
                       scale: float) -> Tuple[float, float]:
    """
    Pick a label position that points AWAY from all incident segments.
    Returns (dx, dy) in data units.
    """
    p = pts[name]
    # Collect unit vectors of all neighbours; the label goes opposite
    # to their sum.
    vecs = []
    for s in segments:
        a, b = s.get("from"), s.get("to")
        if a == name and b in pts:
            vecs.append(_unit((pts[b][0] - p[0], pts[b][1] - p[1])))
        elif b == name and a in pts:
            vecs.append(_unit((pts[a][0] - p[0], pts[a][1] - p[1])))
    if not vecs:
        return (0.0, 0.06 * scale)
    sx = sum(v[0] for v in vecs)
    sy = sum(v[1] for v in vecs)
    n = math.hypot(sx, sy)
    if n < 1e-6:
        # symmetric — push up
        return (0.0, 0.06 * scale)
    # Push label outward from the average neighbour direction.
    # Distance 0.06*span keeps the letter near the dot without crowding edges.
    return (-sx / n * 0.06 * scale, -sy / n * 0.06 * scale)


# ─── Public API ───────────────────────────────────────────────────────────────

class GeometrySpecError(ValueError):
    """Raised when the spec is malformed (missing vertex, bad ref, etc.)."""


def render_spec_to_png(spec: dict, size_px: int = 1024) -> bytes:
    """
    Render a geometry spec to PNG bytes.

    Args:
        spec: parsed JSON spec (see module docstring).
        size_px: output side in pixels (square).

    Returns:
        Raw PNG bytes.

    Raises:
        GeometrySpecError on missing references.
    """
    vertices = spec.get("vertices") or []
    if not vertices:
        raise GeometrySpecError("spec.vertices is empty")

    pts: Dict[str, Tuple[float, float]] = {}
    for v in vertices:
        name = v.get("name")
        if not isinstance(name, str) or not name:
            raise GeometrySpecError(f"vertex without name: {v}")
        try:
            pts[name] = (float(v["x"]), float(v["y"]))
        except (KeyError, TypeError, ValueError):
            raise GeometrySpecError(f"vertex {name!r} missing numeric x/y")

    def _pt(name: str) -> Tuple[float, float]:
        if name not in pts:
            raise GeometrySpecError(f"unknown vertex reference: {name!r}")
        return pts[name]

    segments = spec.get("segments") or []
    angles = spec.get("angles") or []
    right_angles = spec.get("right_angles") or []
    equal_segments = spec.get("equal_segments") or []
    equal_angles = spec.get("equal_angles") or []
    circles = spec.get("circles") or []

    # ── Bounding box & scale ───────────────────────────────────────────────
    xs = [p[0] for p in pts.values()]
    ys = [p[1] for p in pts.values()]
    for c in circles:
        cx, cy = _pt(c["center"])
        r = float(c["radius"])
        xs += [cx - r, cx + r]
        ys += [cy - r, cy + r]

    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    span = max(max_x - min_x, max_y - min_y, 1.0)
    scale = span                       # 1 "data unit" ≈ span/figure

    # ── Figure setup (1024×1024) ───────────────────────────────────────────
    dpi = 128
    fig_inches = size_px / dpi
    fig, ax = plt.subplots(figsize=(fig_inches, fig_inches), dpi=dpi)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    # Margin: 12% of span on every side, but at least 0.5
    margin = max(span * 0.14, 0.5)
    ax.set_xlim(min_x - margin, max_x + margin)
    ax.set_ylim(min_y - margin, max_y + margin)

    LINE_W = 2.0
    AUX_W = 1.4
    FONT_SIZE = 18
    LABEL_SIZE = 22

    # ── Circles (under segments) ───────────────────────────────────────────
    for c in circles:
        cx, cy = _pt(c["center"])
        r = float(c["radius"])
        circ = plt.Circle((cx, cy), r, fill=False,
                          edgecolor="black", linewidth=LINE_W)
        ax.add_patch(circ)
        if c.get("label"):
            ax.text(cx + r * 0.05, cy + r * 1.05, str(c["label"]),
                    fontsize=FONT_SIZE, color="black",
                    ha="left", va="bottom")

    # ── Segments ───────────────────────────────────────────────────────────
    seg_lookup: Dict[Tuple[str, str], dict] = {}
    for s in segments:
        a, b = s.get("from"), s.get("to")
        p1, p2 = _pt(a), _pt(b)
        ax.plot([p1[0], p2[0]], [p1[1], p2[1]],
                color="black", linewidth=LINE_W, solid_capstyle="round")
        seg_lookup[(a, b)] = s
        seg_lookup[(b, a)] = s

        label = s.get("label")
        if label:
            mid = _midpoint(p1, p2)
            n = _normal(p1, p2)
            off = scale * 0.04
            ax.text(mid[0] + n[0] * off, mid[1] + n[1] * off,
                    str(label), fontsize=FONT_SIZE, color="black",
                    ha="center", va="center")

    # ── Equal-segment tick marks ───────────────────────────────────────────
    for group in equal_segments:
        ticks = int(group.get("ticks", 1))
        for ref in group.get("segments", []):
            if not (isinstance(ref, (list, tuple)) and len(ref) == 2):
                continue
            a, b = ref
            p1, p2 = _pt(a), _pt(b)
            _draw_tick_marks(ax, p1, p2, ticks, scale, AUX_W)

    # ── Angles (arc + label) ───────────────────────────────────────────────
    for ang in angles:
        v = _pt(ang["at"])
        a = _pt(ang["from"])
        b = _pt(ang["to"])
        # Adapt arc radius to the shorter incident side so the arc never
        # overlaps the opposite segment. Cap at 22% of that side.
        len_va = math.hypot(a[0] - v[0], a[1] - v[1])
        len_vb = math.hypot(b[0] - v[0], b[1] - v[1])
        min_side = max(min(len_va, len_vb), 1e-6)
        default_radius = min(scale * 0.10, min_side * 0.22)
        r_data = float(ang.get("radius", default_radius))
        a_start = _angle_deg(v, a)
        a_end = _angle_deg(v, b)
        t1, t2 = _shortest_arc(a_start, a_end)
        arc = Arc((v[0], v[1]), 2 * r_data, 2 * r_data,
                  angle=0, theta1=t1, theta2=t2,
                  color="black", linewidth=AUX_W)
        ax.add_patch(arc)

        if ang.get("label"):
            # Place the label along the angular bisector, INWARD from the
            # vertex by 0.4 of the shorter incident side. This keeps the
            # text inside the angle, far from both edges.
            mid_angle = math.radians((t1 + t2) / 2.0)
            lr = min(min_side * 0.40, r_data * 1.7)
            lr = max(lr, r_data * 1.25)  # never fall inside the arc
            ax.text(v[0] + lr * math.cos(mid_angle),
                    v[1] + lr * math.sin(mid_angle),
                    str(ang["label"]),
                    fontsize=FONT_SIZE, color="black",
                    ha="center", va="center")

    # ── Right-angle squares ────────────────────────────────────────────────
    for ra in right_angles:
        v = _pt(ra["at"])
        a = _pt(ra["from"])
        b = _pt(ra["to"])
        size = float(ra.get("size", scale * 0.05))
        u1 = _unit((a[0] - v[0], a[1] - v[1]))
        u2 = _unit((b[0] - v[0], b[1] - v[1]))
        p_a = (v[0] + u1[0] * size, v[1] + u1[1] * size)
        p_b = (v[0] + u2[0] * size, v[1] + u2[1] * size)
        p_c = (v[0] + (u1[0] + u2[0]) * size, v[1] + (u1[1] + u2[1]) * size)
        ax.plot([p_a[0], p_c[0], p_b[0]],
                [p_a[1], p_c[1], p_b[1]],
                color="black", linewidth=AUX_W)

    # ── Equal-angle multi-arcs ─────────────────────────────────────────────
    for group in equal_angles:
        arcs_n = int(group.get("arcs", 1))
        base_r = float(group.get("radius", scale * 0.12))
        for spec_ang in group.get("angles", []):
            v = _pt(spec_ang["at"])
            a = _pt(spec_ang["from"])
            b = _pt(spec_ang["to"])
            a_start = _angle_deg(v, a)
            a_end = _angle_deg(v, b)
            t1, t2 = _shortest_arc(a_start, a_end)
            for k in range(arcs_n):
                r = base_r + k * scale * 0.025
                arc = Arc((v[0], v[1]), 2 * r, 2 * r,
                          angle=0, theta1=t1, theta2=t2,
                          color="black", linewidth=AUX_W)
                ax.add_patch(arc)

    # ── Vertex dots & names ────────────────────────────────────────────────
    for v in vertices:
        name = v["name"]
        x, y = pts[name]
        ax.plot(x, y, marker="o", color="black", markersize=5,
                markeredgecolor="black", markerfacecolor="black")
        # Hide name if explicitly disabled
        if v.get("hide_label"):
            continue
        if "label_offset" in v and isinstance(v["label_offset"], (list, tuple)) \
                and len(v["label_offset"]) == 2:
            dx, dy = float(v["label_offset"][0]), float(v["label_offset"][1])
        else:
            dx, dy = _auto_label_offset(pts, name, segments, scale)
        ax.text(x + dx, y + dy, name,
                fontsize=LABEL_SIZE, color="black",
                ha="center", va="center", weight="bold")

    # ── Export to PNG bytes ────────────────────────────────────────────────
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor="white", dpi=dpi,
                bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)
    return buf.getvalue()


def _draw_tick_marks(ax, p1, p2, ticks: int, scale: float, lw: float):
    """Draw `ticks` short perpendicular marks at the segment midpoint."""
    if ticks <= 0:
        return
    mid = _midpoint(p1, p2)
    along = _unit((p2[0] - p1[0], p2[1] - p1[1]))
    perp = (-along[1], along[0])
    half = scale * 0.025
    spacing = scale * 0.03
    # Center the cluster around the midpoint
    start = -(ticks - 1) / 2.0 * spacing
    for i in range(ticks):
        t = start + i * spacing
        cx = mid[0] + along[0] * t
        cy = mid[1] + along[1] * t
        x1 = cx - perp[0] * half
        y1 = cy - perp[1] * half
        x2 = cx + perp[0] * half
        y2 = cy + perp[1] * half
        ax.plot([x1, x2], [y1, y2], color="black", linewidth=lw)
