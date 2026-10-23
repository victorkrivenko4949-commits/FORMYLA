# -*- coding: utf-8 -*-
import os, re, math
from geometric_engine import engine

specs = {
    'triangle_isosceles': {'type': 'triangle', 'labels': ['A','B','C'], 'equal_sides': [['AB','AC']]},
    'triangle_equal_angles': {'type': 'triangle', 'labels': ['A','B','C'], 'equal_angles': [['B','C']]},
    'square': {'type': 'square', 'labels': ['A','B','C','D']},
    'trapezoid': {'type': 'trapezoid', 'labels': ['A','B','C','D'], 'equal_sides': [['AB','CD']]},
    'parallelogram': {'type': 'parallelogram', 'labels': ['A','B','C','D']},
    'circle_with_chord': {'type': 'circle', 'labels': ['O','A','B']},
    'pentagon': {'type': 'pentagon', 'labels': ['A','B','C','D','E']},
}

os.makedirs('_recon/p1_svg', exist_ok=True)

RX_SEG = r'<line[^>]*x1="([\d.\-]+)"[^>]*y1="([\d.\-]+)"[^>]*x2="([\d.\-]+)"[^>]*y2="([\d.\-]+)"'
RX_LAB = r'<text[^>]*x="([\d.\-]+)"[^>]*y="([\d.\-]+)"[^>]*>([^<]+)</text>'

def d_seg(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    if dx == dy == 0:
        return math.hypot(px - x1, py - y1)
    t = max(0, min(1, ((px-x1)*dx + (py-y1)*dy) / (dx*dx + dy*dy)))
    return math.hypot(px - (x1 + t*dx), py - (y1 + t*dy))

THRESHOLD = 8.0

for name, spec in specs.items():
    svg_text = engine.build_svg(spec)
    with open(f'_recon/p1_svg/{name}.svg', 'w', encoding='utf-8') as f:
        f.write(svg_text)
    segs = [tuple(map(float, m)) for m in re.findall(RX_SEG, svg_text)]
    labs = [(float(x), float(y), t) for x, y, t in re.findall(RX_LAB, svg_text)]
    for i, (lx, ly, lt) in enumerate(labs):
        ms = min((d_seg(lx, ly, *s) for s in segs), default=float('inf'))
        ml = min((math.hypot(lx-ox, ly-oy) for j, (ox, oy, _) in enumerate(labs) if j != i), default=float('inf'))
        flag = 'OK' if ms >= THRESHOLD and ml >= THRESHOLD else 'BELOW_THRESHOLD'
        print('{:22s} {:6s} {:8.2f} {:8.2f} {}'.format(name, lt, ms, ml, flag))
    print(name, 'TICKS', svg_text.count('equal-tick'), 'ARCS', svg_text.count('equal-arc'))
