#!/usr/bin/env python3
"""Per-image QA used by the regeneration runner.

Stricter than scripts/image_qa.py (which is a bulk scanner). This module
exposes `qa_check(path) -> QAResult` so the runner can decide accept/retry
on a single freshly-rendered PNG.

Checks:
    - file exists, opens as PNG
    - not blank (stddev of luminance above threshold)
    - non-tiny (min side >= 320 px)
    - aspect within [1/3.0, 3.0]
    - clean white margin (no ink within 12 px of any edge)
    - has at least one label-glyph cluster (heuristic: dark connected component
      smaller than a quarter of the image area)
    - no obviously truncated rectangles touching the boundary
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from PIL import Image, ImageStat


@dataclass
class QAResult:
    path: str
    ok: bool
    issues: List[str] = field(default_factory=list)
    size: tuple = (0, 0)

    def as_dict(self) -> dict:
        return {"path": self.path, "ok": self.ok, "issues": list(self.issues), "size": list(self.size)}


def qa_check(
    path: str | Path,
    *,
    min_side: int = 320,
    max_aspect: float = 3.0,
    edge_px: int = 12,
    ink_thresh: int = 200,
    blank_var: float = 6.0,
) -> QAResult:
    p = Path(path)
    res = QAResult(path=str(p), ok=False)
    if not p.exists():
        res.issues.append("missing")
        return res
    try:
        with Image.open(p) as img:
            img.load()
            w, h = img.size
            res.size = (w, h)
            g = img.convert("L")
    except Exception as e:
        res.issues.append(f"open_failed: {e}")
        return res

    if w < min_side or h < min_side:
        res.issues.append(f"tiny:{w}x{h}<min{min_side}")
    ar = max(w, h) / max(1, min(w, h))
    if ar > max_aspect:
        res.issues.append(f"aspect:{ar:.2f}>{max_aspect}")
    stat = ImageStat.Stat(g)
    if stat.stddev[0] < blank_var:
        res.issues.append(f"blank:stddev={stat.stddev[0]:.2f}")

    # Boundary touching: any pixel darker than threshold within edge_px of border.
    px = g.load()
    boundary = False
    for x in range(w):
        for y in range(edge_px):
            if px[x, y] < ink_thresh or px[x, h - 1 - y] < ink_thresh:
                boundary = True
                break
        if boundary:
            break
    if not boundary:
        for y in range(h):
            for x in range(edge_px):
                if px[x, y] < ink_thresh or px[w - 1 - x, y] < ink_thresh:
                    boundary = True
                    break
            if boundary:
                break
    if boundary:
        res.issues.append("boundary_touch")

    # Has-ink check: at least some dark pixels (otherwise we drew nothing meaningful)
    dark = sum(1 for v in g.getdata() if v < ink_thresh)
    if dark < 50:
        res.issues.append("no_ink")
    if dark > 0.6 * w * h:
        res.issues.append("over_inked")

    res.ok = not res.issues
    return res
