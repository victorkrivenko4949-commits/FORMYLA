"""Correct mathematically inconsistent drawings in the methods atlas.

The coordinates below are explicit realizations of each problem's hypotheses,
not copies of the old diagrams. Every stage shares the same geometry.
"""

from html import escape
from math import cos, radians, sin, hypot


def num(value):
    return f"{value:.2f}" if isinstance(value, float) else str(value)


def line(a, b, color="#2b3742", width=2.6, dash=""):
    style = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<line x1="{num(a[0])}" y1="{num(a[1])}" x2="{num(b[0])}" '
            f'y2="{num(b[1])}" stroke="{color}" stroke-width="{width}"{style}/>')


def circle(center, r, color="#2b3742", width=2.6):
    return (f'<circle cx="{num(center[0])}" cy="{num(center[1])}" r="{num(r)}" '
            f'fill="none" stroke="{color}" stroke-width="{width}"/>')


def dot(label, p, dx=10, dy=-10):
    return (f'<circle cx="{num(p[0])}" cy="{num(p[1])}" r="4.5" fill="#19364a"/>'
            f'<text x="{num(p[0]+dx)}" y="{num(p[1]+dy)}" '
            f'font-size="18" fill="#19364a">{escape(label)}</text>')


def caption(text):
    return f'<text x="300" y="465" text-anchor="middle" font-size="17" fill="#176a73">{escape(text)}</text>'


def svg(label, shapes):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" role="img" '
            f'aria-label="{escape(label, quote=True)}" viewBox="0 0 600 500" width="600" height="500">'
            '<rect width="600" height="500" fill="#f7f6f2"/>'
            + "".join(shapes) + "</svg>")


def crossing(a, b, c, d):
    ax, ay = a
    bx, by = b
    cx, cy = c
    dx, dy = d
    den = (bx-ax)*(dy-cy) - (by-ay)*(dx-cx)
    t = ((cx-ax)*(dy-cy) - (cy-ay)*(dx-cx))/den
    return ax+t*(bx-ax), ay+t*(by-ay)


def tangent(stage):
    o, radius = (260, 265), 120
    a, b = (140, 265), (380, 265)
    c = (o[0] + radius*cos(radians(56)), o[1] - radius*sin(radians(56)))
    d = (o[0] + radius/cos(radians(56)), 265)
    parts = [circle(o, radius), line(a, d, width=2),
             line(c, d, color="#176a73"), dot("A", a, -21, 24),
             dot("B", b, 5, 25), dot("C", c, 8, -10),
             dot("D", d, 8, 24)]
    if stage != "condition":
        parts += [line(o, c, color="#718a99", dash="6 5"),
                  line(a, c), line(b, c), dot("O", o, -10, 25)]
    if stage == "result":
        parts.append(caption("∠CAB = 28°    ·    ∠CDB = 34°"))
    return svg("Касательная в C к окружности с диаметром AB проходит через D", parts)


def chords(stage):
    o, radius = (300, 240), 150
    edge = (radius**2-30**2)**0.5
    a, b = (300-edge, 270), (300+edge, 270)
    c, d = (270, 240-edge), (270, 240+edge)
    e = (270, 270)
    parts = [circle(o, radius), line(a, b), line(c, d, color="#176a73"),
             dot("A", a, -20, 25), dot("B", b, 8, 25),
             dot("C", c, 9, -12), dot("D", d, 10, 20), dot("E", e, 10, -10)]
    if stage != "condition":
        parts += [line(a, d, color="#83949d", width=2),
                  line(c, b, color="#83949d", width=2)]
    if stage == "result":
        parts.append(caption("△AED ∼ △CEB    ·    AE · EB = CE · ED"))
    return svg("Хорды AB и CD пересекаются внутри окружности в E", parts)


def reflection(stage):
    a, b, a1 = (140, 125), (445, 145), (140, 395)
    c = crossing(a1, b, (70, 260), (530, 260))
    parts = [line((70, 260), (530, 260), width=2), dot("A", a, -22),
             dot("B", b, 8), '<text x="523" y="250" font-size="20" fill="#19364a">ℓ</text>']
    if stage != "condition":
        parts += [line(a, a1, color="#83949d", dash="6 5"),
                  line(a1, b, color="#83949d", dash="6 5"),
                  dot("A′", a1, -26, 24), dot("C", c, 8, 23)]
    if stage == "result":
        parts += [line(a, c, color="#176a73", width=3.4),
                  line(c, b, color="#176a73", width=3.4),
                  caption("AC + CB = A′C + CB = A′B — наименьшая длина")]
    return svg("Отражение A относительно прямой ℓ, точка C лежит на ℓ", parts)


def bisector(stage):
    a, b, c = (125, 385), (290, 90), (495, 385)
    ab, bc = hypot(b[0]-a[0], b[1]-a[1]), hypot(b[0]-c[0], b[1]-c[1])
    d = (a[0]+(c[0]-a[0])*ab/(ab+bc), a[1])
    parts = [line(a, b), line(b, c), line(c, a),
             line(b, d, color="#176a73", width=3.4),
             dot("A", a, -24, 20), dot("B", b, -4, -14),
             dot("C", c, 10, 20), dot("D", d, 7, 23)]
    if stage != "condition":
        parts += ['<text x="213" y="228" font-size="20" fill="#176a73">β/2</text>',
                  '<text x="310" y="228" font-size="20" fill="#176a73">β/2</text>']
    if stage == "result":
        parts.append(caption("S(ABC) = S(ABD) + S(CBD)"))
    return svg("Биссектриса BD пересекает сторону AC в точке D", parts)


def ceva(stage, nagel=False):
    a, b, c = (110, 390), (510, 390), (260, 90)
    if nagel:
        side_a = hypot(c[0]-b[0], c[1]-b[1])
        side_b = hypot(c[0]-a[0], c[1]-a[1])
        s = (side_a+side_b+400)/2
        td = (s-400)/side_a  # BD = s-c
        te = (s-side_a)/side_b  # CE = s-a
        d = (b[0]+td*(c[0]-b[0]), b[1]+td*(c[1]-b[1]))
        e = (c[0]+te*(a[0]-c[0]), c[1]+te*(a[1]-c[1]))
        f = (a[0]+s-side_b, 390)  # AF = s-b
    else:
        d = ((b[0]+c[0])/2, (b[1]+c[1])/2)
        e = ((c[0]+a[0])/2, (c[1]+a[1])/2)
        f = ((a[0]+b[0])/2, 390)
    p = crossing(a, d, b, e)
    parts = [line(a, b), line(b, c), line(c, a),
             dot("A", a, -23, 19), dot("B", b, 8, 20),
             dot("C", c, -4, -14), dot("D", d, 10, 0),
             dot("E", e, -24, 0), dot("F", f, -5, 24)]
    if stage != "condition" or not nagel:
        parts += [line(a, d, color="#176a73"), line(b, e, color="#176a73"),
                  line(c, f, color="#176a73"), dot("N" if nagel else "P", p, 10, -8)]
    if stage == "result":
        parts.append(caption("AD, BE и CF пересекаются в одной точке" if nagel
                             else "(BD/DC) · (CE/EA) · (AF/FB) = 1"))
    return svg("Три чевианы треугольника пересекаются в одной точке", parts)


def locus(stage):
    o = (300, 245)
    parts = [line((85, 175), (515, 315)),
             line((165, 380), (435, 110)), dot("O", o, 10, 25),
             '<text x="90" y="165" font-size="20" fill="#19364a">ℓ₁</text>',
             '<text x="440" y="104" font-size="20" fill="#19364a">ℓ₂</text>']
    # Unit directions of the two angle bisectors; the second is perpendicular.
    vx, vy = cos(radians(-13.28)), sin(radians(-13.28))
    if stage != "condition":
        parts.append(line((o[0]-200*vx, o[1]-200*vy),
                          (o[0]+200*vx, o[1]+200*vy), "#176a73", 3))
    if stage == "result":
        parts += [line((o[0]+170*vy, o[1]-170*vx),
                       (o[0]-170*vy, o[1]+170*vx), "#bd8241", 3),
                  caption("ГМТ — две взаимно перпендикулярные биссектрисы")]
    return svg("Биссектрисы двух углов между пересекающимися прямыми", parts)


FIXES = {
    "f2-2": tangent,
    "f3-2": chords,
    "f4a-1": reflection,
    "f6-2": bisector,
    "f13-3": lambda stage: ceva(stage, nagel=True),
    "f14-1": locus,
    "f16-2": ceva,
    "f17-2": lambda stage: ceva(stage, nagel=True),
}
