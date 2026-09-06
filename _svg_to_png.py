# -*- coding: utf-8 -*-
"""Render simple SVG (as produced by geometric_engine) to PNG via PIL.

Supports: line, circle, polygon, polyline, text, path (M/A arc).
Used only for local visual QA — not part of the product pipeline.
"""
import math
import sys
import xml.etree.ElementTree as ET

from PIL import Image, ImageDraw, ImageFont

NS = "{http://www.w3.org/2000/svg}"


def _color(c, default):
    if not c or c == "none":
        return default
    return c


def _dashed(draw, xy, fill, width, dash=(6, 4)):
    x1, y1, x2, y2 = xy
    dx = x2 - x1
    dy = y2 - y1
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return
    ux, uy = dx / length, dy / length
    pos = 0.0
    i = 0
    on = True
    while pos < length:
        seg_len = dash[i % 2]
        if on:
            end = min(pos + seg_len, length)
            draw.line((x1 + ux * pos, y1 + uy * pos,
                       x1 + ux * end, y1 + uy * end), fill=fill, width=width)
        pos += seg_len
        on = not on
        i += 1


def _arc_points(cx, cy, rx, ry, start, end, large, sweep, n=60):
    # convert start/end angles (radians) to points, honoring sweep/large.
    def ang(t):
        # arc param
        pass

    # Build the elliptical arc via param from start angle to end angle.
    a0 = math.atan2(start[1] - cy, start[0] - cx)
    # end angle from end point
    a1 = math.atan2(end[1] - cy, end[0] - cx)

    # Determine sweep direction.
    if sweep:
        while a1 <= a0:
            a1 += 2 * math.pi
    else:
        while a1 >= a0:
            a1 -= 2 * math.pi

    pts = []
    steps = n
    for i in range(steps + 1):
        t = a0 + (a1 - a0) * i / steps
        pts.append((cx + rx * math.cos(t), cy + ry * math.sin(t)))
    return pts


def render(svg_path, png_path, scale=2):
    tree = ET.parse(svg_path)
    root = tree.getroot()
    w = int(float(root.get("width")))
    h = int(float(root.get("height")))

    bg = "#0f172a"
    style = root.get("style") or ""
    if "background-color:" in style:
        bg = style.split("background-color:")[1].split(";")[0].strip()

    img = Image.new("RGB", (w * scale, h * scale), bg)
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype("arial.ttf", 16 * scale)

    def P(x, y):
        return (float(x) * scale, float(y) * scale)

    for el in root.iter():
        tag = el.tag.replace(NS, "")
        if tag == "line":
            x1, y1 = P(el.get("x1"), el.get("y1"))
            x2, y2 = P(el.get("x2"), el.get("y2"))
            stroke = _color(el.get("stroke"), "#c8d6e5")
            width = max(1, int(float(el.get("stroke-width") or 1.8) * scale))
            if el.get("stroke-dasharray"):
                _dashed(draw, (x1, y1, x2, y2), stroke, width)
            else:
                draw.line((x1, y1, x2, y2), fill=stroke, width=width)
        elif tag == "circle":
            cx, cy = P(el.get("cx"), el.get("cy"))
            r = float(el.get("r")) * scale
            stroke = _color(el.get("stroke"), "#c8d6e5")
            fill = el.get("fill") or "none"
            width = max(1, int(float(el.get("stroke-width") or 1.8) * scale))
            if fill != "none":
                draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=fill, outline=stroke, width=width)
            elif el.get("stroke-dasharray"):
                # dashed circle
                import math as _m
                n = 120
                for i in range(n):
                    a0 = 2 * _m.pi * i / n
                    a1 = 2 * _m.pi * (i + 0.6) / n
                    draw.arc((cx - r, cy - r, cx + r, cy + r),
                             int(_m.degrees(a0)), int(_m.degrees(a1)), fill=stroke, width=width)
            else:
                draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=stroke, width=width)
        elif tag == "polygon":
            pts = [P(*p.split(",")) for p in (el.get("points") or "").split()]
            if pts:
                draw.line(pts + [pts[0]], fill=_color(el.get("stroke"), "#c8d6e5"),
                          width=max(1, int(float(el.get("stroke-width") or 1.8) * scale)))
        elif tag == "polyline":
            pts = [P(*p.split(",")) for p in (el.get("points") or "").split()]
            if pts:
                draw.line(pts, fill=_color(el.get("stroke"), "#a0b8d8"),
                          width=max(1, int(float(el.get("stroke-width") or 1.2) * scale)))
        elif tag == "text":
            x, y = P(el.get("x"), el.get("y"))
            text = el.text or ""
            fill = _color(el.get("fill"), "#d0ddf0")
            # approximate text bbox for centering
            bbox = draw.textbbox((0, 0), text, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            draw.text((x - tw / 2, y - th / 2), text, fill=fill, font=font)
        elif tag == "path":
            d = el.get("d") or ""
            stroke = _color(el.get("stroke"), "#a0b8d8")
            width = max(1, int(float(el.get("stroke-width") or 1.2) * scale))
            # parse M x y A rx ry rot large sweep x y
            import re as _re
            m = _re.match(r"M\s*([-\d.]+)\s+([-\d.]+)\s+A\s+([-\d.]+)\s+([-\d.]+)\s+\d+\s+(\d)\s+(\d)\s+([-\d.]+)\s+([-\d.]+)", d)
            if m:
                sx, sy, rx, ry, large, sweep, ex, ey = (float(m.group(1)), float(m.group(2)),
                                                        float(m.group(3)), float(m.group(4)),
                                                        int(m.group(5)), int(m.group(6)),
                                                        float(m.group(7)), float(m.group(8)))
                pts = _arc_points(sx, sy, rx, ry, (sx, sy), (ex, ey), large, sweep)
                pts = [P(px, py) for px, py in pts]
                draw.line(pts, fill=stroke, width=width)

    img.save(png_path)
    print(f"wrote {png_path} ({img.size[0]}x{img.size[1]})")


if __name__ == "__main__":
    for f in ["ch151_f1_base", "ch151_f1_aux", "ch151_f2_base", "ch151_f2_aux"]:
        render(f"{f}.svg", f"{f}.png")
