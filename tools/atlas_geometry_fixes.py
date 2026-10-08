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


def intersecting_circles(stage):
    # AC=AD=120, AB is the common chord. Tangents CP and DP really are
    # perpendicular to their corresponding radii, and B,C,D,P are concyclic.
    a, b = (300, 200), (300, 110)
    c, d, p = (180, 200), (420, 200), (300, 360)
    parts = [circle((240, 155), 75, "#83949d", 2),
             circle((360, 155), 75, "#83949d", 2),
             line(c, d), dot("A", a, 8, 22), dot("B", b, 8, -12),
             dot("C", c, -22, 23), dot("D", d, 8, 23)]
    if stage != "condition":
        parts += [line(c, p, "#176a73", 3), line(d, p, "#176a73", 3),
                  dot("P", p, 10, 20)]
    if stage == "result":
        parts += [circle((300, 235), 125, "#bd8241", 2),
                  caption("B, C, D и P лежат на одной окружности")]
    return svg("Две окружности пересекаются в A, B; касательные в C и D встречаются в P", parts)


def circumcenter(a, b, c):
    ax, ay = a
    bx, by = b
    cx, cy = c
    determinant = 2*(ax*(by-cy) + bx*(cy-ay) + cx*(ay-by))
    return (
        ((ax*ax+ay*ay)*(by-cy) + (bx*bx+by*by)*(cy-ay) +
         (cx*cx+cy*cy)*(ay-by))/determinant,
        ((ax*ax+ay*ay)*(cx-bx) + (bx*bx+by*by)*(ax-cx) +
         (cx*cx+cy*cy)*(bx-ax))/determinant,
    )


def euler_line(stage):
    # Leave clear space below the circumcircle for the result caption.
    a, b, c = (141.6, 347.6), (436.4, 338.8), (181.2, 145.2)
    o = circumcenter(a, b, c)
    g = ((a[0]+b[0]+c[0])/3, (a[1]+b[1]+c[1])/3)
    h = (3*g[0]-2*o[0], 3*g[1]-2*o[1])
    midpoint = ((a[0]+b[0])/2, (a[1]+b[1])/2)
    parts = [line(a, b), line(b, c), line(c, a),
             dot("A", a, -24, 18), dot("B", b, 9, 18), dot("C", c, -4, -12)]
    if stage != "condition":
        parts += [circle(o, hypot(o[0]-a[0], o[1]-a[1]), "#83949d", 1.6),
                  line(c, midpoint, "#83949d", 2, "6 5"),
                  line(a, h, "#83949d", 2, "6 5"),
                  line(b, h, "#83949d", 2, "6 5"),
                  dot("O", o, 10, -12), dot("G", g, -8, 27),
                  dot("H", h, -25, -12)]
    if stage == "result":
        parts += [line(o, h, "#176a73", 3.6),
                  caption("O, G, H на одной прямой · HG = 2 · GO")]
    return svg("Прямая Эйлера: O, G, H коллинеарны и HG равно удвоенному GO", parts)


def rhombus(stage):
    a, b, c, d, center = ((115, 250), (300, 385), (485, 250),
                          (300, 115), (300, 250))
    corners = (a, b, c, d, a)
    parts = [line(corners[i], corners[i+1]) for i in range(4)]
    # One identical tick on each equal side, perpendicular at its midpoint.
    for first, second in zip(corners, corners[1:]):
        mx, my = (first[0]+second[0])/2, (first[1]+second[1])/2
        dx, dy = second[0]-first[0], second[1]-first[1]
        length = hypot(dx, dy)
        tick = (dy*6/length, -dx*6/length)
        parts.append(line((mx-tick[0], my-tick[1]),
                          (mx+tick[0], my+tick[1]), "#176a73", 2))
    parts += [dot("A", a, -23, 0), dot("B", b, -5, 25),
              dot("C", c, 10, 0), dot("D", d, -5, -14)]
    if stage != "condition":
        parts += [line(a, c, "#176a73", 2.5),
                  line(b, d, "#176a73", 2.5), dot("M", center, 9, 19)]
    if stage == "result":
        parts += [line((300, 238), (312, 238), "#bd8241", 1.6),
                  line((312, 238), (312, 250), "#bd8241", 1.6),
                  caption("AB = BC = CD = DA · AC ⟂ BD")]
    return svg("Ромб ABCD: четыре равные стороны и перпендикулярные диагонали", parts)


def axes(origin, scale, x_values=(), y_values=(), x_end=525, y_top=55):
    ox, oy = origin
    pieces = [line((ox-15, oy), (x_end, oy), "#83949d", 1.6),
              line((ox, oy+14), (ox, y_top), "#83949d", 1.6)]
    for value in x_values:
        x = ox + value*scale
        pieces += [line((x, oy-4), (x, oy+4), "#83949d", 1.4),
                   f'<text x="{num(x)}" y="{num(oy+22)}" text-anchor="middle" '
                   f'font-size="14" fill="#718a99">{value}</text>']
    for value in y_values:
        y = oy - value*scale
        pieces += [line((ox-4, y), (ox+4, y), "#83949d", 1.4),
                   f'<text x="{num(ox-12)}" y="{num(y+5)}" text-anchor="end" '
                   f'font-size="14" fill="#718a99">{value}</text>']
    pieces += [f'<text x="{num(x_end+5)}" y="{num(oy+5)}" font-size="17" fill="#718a99">x</text>',
               f'<text x="{num(ox-5)}" y="{num(y_top-8)}" font-size="17" fill="#718a99">y</text>']
    return pieces


def coordinate_circumcircle(stage):
    a, b, c, o = (120, 390), (360, 390), (120, 70), (240, 230)
    parts = axes(a, 40, (2, 4, 6), (2, 4, 6, 8), 480, 48)
    parts += [line(a, b), line(a, c), line(b, c),
              dot("A", a, 7, 19), dot("B", b, 7, -9),
              dot("C", c, 10, -9)]
    if stage != "condition":
        parts += [line(b, c, "#176a73", 3),
                  dot("O", o, 10, -10)]
    if stage == "result":
        parts += [circle(o, 200, "#bd8241", 2),
                  caption("O(3, 4) · R = 5")]
    return svg("A(0,0), B(6,0), C(0,8); центр описанной окружности O(3,4)", parts)


def apollonius(stage):
    a, b, o, m = (120, 300), (300, 300), (360, 300), (360, 180)
    parts = axes(a, 60, (1, 2, 3, 4, 5, 6), (1, 2), 505, 100)
    parts += [line(a, b, "#83949d", 2),
              dot("A", a, -8, 25), dot("B", b, -15, -12)]
    if stage != "condition":
        parts += [line(a, m, "#83949d", 2, "6 5"),
                  line(b, m, "#83949d", 2, "6 5"),
                  dot("M", m, 10, -12)]
    if stage == "result":
        parts += [circle(o, 120, "#176a73", 3), dot("O", o, 12, -12),
                  caption("MA / MB = 2 · центр (4, 0), радиус 2")]
    return svg("Окружность Аполлония для A(0,0), B(3,0), MA/MB=2", parts)


def orthocenter_coordinates(stage):
    a, b, c, h = (130, 390), (470, 390), (215, 135), (215, 305)
    # Foot of the altitude from B on AC is the projection of B-A onto AC.
    foot = (164, 288)
    parts = axes(a, 85, (1, 2, 3, 4), (1, 2, 3), 520, 78)
    parts += [line(a, b), line(b, c), line(c, a),
              dot("A", a, 9, 20), dot("B", b, -4, 22),
              dot("C", c, -21, -12)]
    if stage != "condition":
        parts += [line(c, (215, 390), "#176a73", 2.5, "6 5"),
                  line(b, foot, "#176a73", 2.5, "6 5")]
    if stage == "result":
        parts += [dot("H", h, 12, -10), caption("H = (1, 1)")]
    return svg("A(0,0), B(4,0), C(1,3); высоты пересекаются в H(1,1)", parts)


def inversion_of_line(stage):
    o, h, h_prime = (200, 250), (380, 250), (325, 250)
    p = (380, 120)
    inversion_radius = 150
    factor = inversion_radius**2/((p[0]-o[0])**2+(p[1]-o[1])**2)
    p_prime = (o[0]+factor*(p[0]-o[0]), o[1]+factor*(p[1]-o[1]))
    parts = [circle(o, inversion_radius, "#83949d", 2),
             line((380, 75), (380, 410), "#2b3742", 2.6),
             dot("O", o, -20, 22), dot("H", h, 10, 20),
             dot("P", p, 10, -10),
             '<text x="392" y="83" font-size="19" fill="#19364a">ℓ</text>']
    if stage != "condition":
        parts += [line(o, h, "#83949d", 1.5, "6 5"),
                  line(o, p, "#83949d", 1.5, "6 5"),
                  dot("H′", h_prime, 8, 25),
                  dot("P′", p_prime, 10, -12)]
    if stage == "result":
        parts += [circle((262.5, 250), 62.5, "#176a73", 3),
                  caption("Образ прямой ℓ — окружность с диаметром OH′")]
    return svg("Инверсия прямой ℓ: окружность-образ проходит через O и H′", parts)


FIXES = {
    "f2-2": tangent,
    "f3-2": chords,
    "f4a-1": reflection,
    "f4b-3": intersecting_circles,
    "f6-2": bisector,
    "f7-1": rhombus,
    "f7-2": euler_line,
    "f9-3": euler_line,
    "f9a-1": coordinate_circumcircle,
    "f9a-2": apollonius,
    "f9a-3": orthocenter_coordinates,
    "f13-3": lambda stage: ceva(stage, nagel=True),
    "f14-1": locus,
    "f15-2": inversion_of_line,
    "f16-2": ceva,
    "f17-2": lambda stage: ceva(stage, nagel=True),
    "f17-3": euler_line,
}
