#!/usr/bin/env python3
"""Automated QA over diagram assets under static/images/problems.

Flags:
  - duplicates of "копия" / "копия (N)" files (exact byte-identical)
  - blank / near-blank rasters (low pixel variance)
  - very small images (<200 px on either side)
  - extreme aspect ratios (>4:1)
  - text/ink touching the image boundary (no white margin)

Writes a JSON+Markdown report next to itself.
Usage:
    python scripts/image_qa.py [--root static/images/problems]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

from PIL import Image, ImageStat


KOPIYA_RE = re.compile(r" — копия( \(\d+\))?\.png$")


def md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def boundary_touches(img: Image.Image, ink_thresh: int = 200, edge_px: int = 2) -> bool:
    """True if dark ink reaches the outermost `edge_px` of any side.

    A "white margin" image will have only near-white pixels in the border strip.
    """
    g = img.convert("L")
    w, h = g.size
    if w < 2 * edge_px or h < 2 * edge_px:
        return True
    px = g.load()
    for x in range(w):
        for y in range(edge_px):
            if px[x, y] < ink_thresh:
                return True
            if px[x, h - 1 - y] < ink_thresh:
                return True
    for y in range(h):
        for x in range(edge_px):
            if px[x, y] < ink_thresh:
                return True
            if px[w - 1 - x, y] < ink_thresh:
                return True
    return False


def is_blank(img: Image.Image, var_thresh: float = 2.0) -> bool:
    g = img.convert("L")
    stat = ImageStat.Stat(g)
    return stat.stddev[0] < var_thresh


def scan(root: Path) -> dict:
    files = sorted(root.glob("*.png"))
    report = {
        "root": str(root),
        "total": len(files),
        "kopiya_duplicates": [],
        "kopiya_orphans": [],
        "kopiya_diverged": [],
        "blank": [],
        "tiny": [],
        "extreme_aspect": [],
        "boundary_touch": [],
        "errors": [],
    }
    by_basename: dict[str, Path] = {f.name: f for f in files}

    for f in files:
        name = f.name
        m = KOPIYA_RE.search(name)
        if m:
            base_name = KOPIYA_RE.sub(".png", name)
            base = by_basename.get(base_name)
            if base is None:
                report["kopiya_orphans"].append(name)
                continue
            if md5(f) == md5(base):
                report["kopiya_duplicates"].append({"copy": name, "base": base_name})
            else:
                report["kopiya_diverged"].append({"copy": name, "base": base_name})
            continue
        try:
            with Image.open(f) as img:
                img.load()
                w, h = img.size
                if w < 200 or h < 200:
                    report["tiny"].append({"file": name, "size": [w, h]})
                ar = max(w, h) / max(1, min(w, h))
                if ar > 4.0:
                    report["extreme_aspect"].append({"file": name, "size": [w, h], "ar": round(ar, 2)})
                if is_blank(img):
                    report["blank"].append(name)
                elif boundary_touches(img):
                    report["boundary_touch"].append(name)
        except Exception as e:
            report["errors"].append({"file": name, "error": str(e)})

    return report


def write_md(report: dict, out_md: Path) -> None:
    lines = []
    lines.append(f"# Image QA report — {report['root']}\n")
    lines.append(f"Total PNGs scanned: **{report['total']}**\n")
    lines.append("## Counts\n")
    lines.append(f"- Identical 'копия' duplicates: **{len(report['kopiya_duplicates'])}**")
    lines.append(f"- 'копия' files whose base is missing: **{len(report['kopiya_orphans'])}**")
    lines.append(f"- 'копия' files diverged from base: **{len(report['kopiya_diverged'])}**")
    lines.append(f"- Blank / near-blank: **{len(report['blank'])}**")
    lines.append(f"- Tiny (<200px side): **{len(report['tiny'])}**")
    lines.append(f"- Extreme aspect ratio (>4:1): **{len(report['extreme_aspect'])}**")
    lines.append(f"- Ink touches image boundary (no white margin): **{len(report['boundary_touch'])}**")
    lines.append(f"- Read errors: **{len(report['errors'])}**\n")

    def block(title: str, items: list, fmt=lambda x: str(x), limit: int = 25):
        if not items:
            return
        lines.append(f"## {title} ({len(items)})\n")
        for it in items[:limit]:
            lines.append(f"- `{fmt(it)}`")
        if len(items) > limit:
            lines.append(f"- … and {len(items) - limit} more")
        lines.append("")

    block("Blank / near-blank", report["blank"])
    block("Ink touches boundary", report["boundary_touch"])
    block("Tiny images", report["tiny"], fmt=lambda x: f"{x['file']} {x['size']}")
    block("Extreme aspect ratio", report["extreme_aspect"], fmt=lambda x: f"{x['file']} {x['size']} ar={x['ar']}")
    block("Diverged копия", report["kopiya_diverged"], fmt=lambda x: f"{x['copy']} ≠ {x['base']}")
    block("Orphan копия", report["kopiya_orphans"])
    out_md.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="static/images/problems")
    ap.add_argument("--out-json", default="scripts/_image_qa_report.json")
    ap.add_argument("--out-md", default="scripts/_image_qa_report.md")
    args = ap.parse_args()

    root = Path(args.root)
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2
    report = scan(root)
    Path(args.out_json).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_md(report, Path(args.out_md))
    print(f"scanned {report['total']} files; wrote {args.out_json} and {args.out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
