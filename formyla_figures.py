# -*- coding: utf-8 -*-
"""
FORMYLA — пакетное построение чертежей.
Один файл, без внешних зависимостей кроме requests.

  pip install requests
  set DEEPSEEK_API_KEY=...            (Windows CMD)
  $env:DEEPSEEK_API_KEY="..."         (PowerShell)

  python formyla_figures.py tasks.json --limit 10 --workers 2
  python formyla_figures.py tasks.json --workers 5 --resume

Результат:  out/figures/<task_uid>.svg  +  <task_uid>.json
Журнал:     out/figures_batch.jsonl
"""
import argparse, json, math, os, random, re, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("нет библиотеки requests. выполни: pip install requests")

API_URL = os.environ.get("DEEPSEEK_URL", "https://api.deepseek.com/v1/chat/completions")
API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
MODEL = os.environ.get("FIGURE_MODEL", "deepseek-v4-flash")

W = H = 620
PAD = 60
C_LINE, C_ACCENT, C_SOFT, C_LABEL, C_CIRC = "#C8D6E5", "#4C7DFF", "#8C9ABC", "#E6EBF7", "#A9BBD6"

# ────────────────────────── геометрия ──────────────────────────
class P:
    __slots__ = ("x", "y")
    def __init__(s, x, y): s.x, s.y = float(x), float(y)
    def __sub__(s, o): return P(s.x - o.x, s.y - o.y)
    def __add__(s, o): return P(s.x + o.x, s.y + o.y)
    def __mul__(s, k): return P(s.x * k, s.y * k)
    def n(s): return math.hypot(s.x, s.y)

def u(v):
    d = v.n()
    return P(v.x / d, v.y / d) if d > 1e-12 else P(0, 0)

def dot(a, b): return a.x * b.x + a.y * b.y
def cross(a, b): return a.x * b.y - a.y * b.x
def mid(a, b): return P((a.x + b.x) / 2, (a.y + b.y) / 2)
def dist(a, b): return (a - b).n()

def split_ref(s, known):
    """'AB' -> A,B ; 'AA1' -> A,A1 ; 'A-A1' -> A,A1"""
    s = s.strip()
    if "-" in s:
        a, b = s.split("-", 1)
        return a.strip(), b.strip()
    for i in range(1, len(s)):
        a, b = s[:i], s[i:]
        if a in known and b in known:
            return a, b
    if len(s) == 2:
        return s[0], s[1]
    raise ValueError(f"не разобрать ссылку {s}")


def foot(p, a, b):
    d = b - a
    t = dot(p - a, d) / dot(d, d)
    return P(a.x + d.x * t, a.y + d.y * t)

def line_inter(a, b, c, d):
    den = cross(b - a, d - c)
    if abs(den) < 1e-9: raise ValueError("прямые параллельны")
    t = cross(c - a, d - c) / den
    return P(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t)

def circle_line_inter(o, r, a, b, pick=0):
    d = u(b - a); f = a - o
    B = 2 * dot(f, d); C = dot(f, f) - r * r
    disc = B * B - 4 * C
    if disc < 0: raise ValueError("прямая не пересекает окружность")
    s = math.sqrt(disc)
    ts = sorted([(-B - s) / 2, (-B + s) / 2])
    t = ts[min(pick, 1)]
    return P(a.x + d.x * t, a.y + d.y * t)

def circle_circle_inter(o1, r1, o2, r2, pick=0):
    d = dist(o1, o2)
    if d > r1 + r2 or d < abs(r1 - r2) or d < 1e-9:
        raise ValueError("окружности не пересекаются")
    a = (r1 * r1 - r2 * r2 + d * d) / (2 * d)
    h2 = r1 * r1 - a * a
    if h2 < 0: raise ValueError("окружности не пересекаются")
    h = math.sqrt(h2)
    m = P(o1.x + (o2.x - o1.x) * a / d, o1.y + (o2.y - o1.y) * a / d)
    n = P(-(o2.y - o1.y) / d, (o2.x - o1.x) / d)
    return P(m.x + n.x * h, m.y + n.y * h) if pick == 0 else P(m.x - n.x * h, m.y - n.y * h)

def circumcenter(a, b, c):
    d = 2 * (a.x * (b.y - c.y) + b.x * (c.y - a.y) + c.x * (a.y - b.y))
    if abs(d) < 1e-9: raise ValueError("точки на одной прямой")
    qa, qb, qc = a.x**2 + a.y**2, b.x**2 + b.y**2, c.x**2 + c.y**2
    return P((qa * (b.y - c.y) + qb * (c.y - a.y) + qc * (a.y - b.y)) / d,
             (qa * (c.x - b.x) + qb * (a.x - c.x) + qc * (b.x - a.x)) / d)

def incenter(a, b, c):
    la, lb, lc = dist(b, c), dist(a, c), dist(a, b)
    s = la + lb + lc
    return P((la * a.x + lb * b.x + lc * c.x) / s, (la * a.y + lb * b.y + lc * c.y) / s)

def inradius(a, b, c):
    la, lb, lc = dist(b, c), dist(a, c), dist(a, b)
    s = (la + lb + lc) / 2
    ar = abs(cross(b - a, c - a)) / 2
    return ar / s

def angle_at(a, b, c):
    v1, v2 = a - b, c - b
    return math.degrees(math.acos(max(-1, min(1, dot(v1, v2) / (v1.n() * v2.n() + 1e-12)))))

# ────────────────────────── построение по спецификации ──────────────────────────
def build(spec, seed):
    rnd = random.Random(seed)
    pts, circ = {}, {}

    def g(name):
        if name not in pts: raise ValueError(f"точка {name} не объявлена")
        return pts[name]

    def two(s):
        a, b = split_ref(s, pts)
        return g(a), g(b)

    for it in spec.get("given", []):
        t = it["type"]; i = it["id"]
        if t == "triangle":
            kind = it.get("kind", "any")
            best = None
            for _ in range(400):
                angs = sorted(rnd.sample(range(0, 360), 3))
                q = [P(math.cos(math.radians(a)), math.sin(math.radians(a))) for a in angs]
                A, B, C = q
                aa = [angle_at(B, A, C), angle_at(A, B, C), angle_at(A, C, B)]
                sd = sorted([dist(B, C), dist(A, C), dist(A, B)])
                ok = min(aa) > 30 and sd[2] / sd[0] < 2.0
                if kind == "acute": ok = ok and max(aa) < 82
                if kind == "obtuse": ok = max(aa) > 100 and min(aa) > 22
                if kind == "right": ok = abs(max(aa) - 90) < 1.5 and min(aa) > 28
                if kind == "isosceles":
                    ok = ok and abs(dist(A, B) - dist(A, C)) < 0.03
                if ok: best = q; break
            if best is None:
                if kind == "right":
                    best = [P(-0.9, -0.5), P(0.9, -0.5), P(-0.9, 0.9)]
                elif kind == "isosceles":
                    best = [P(0, 1), P(-0.85, -0.6), P(0.85, -0.6)]
                else:
                    best = [P(-0.2, 1.0), P(-1.0, -0.7), P(1.0, -0.5)]
            for nm, p in zip(i, best): pts[nm] = p
        elif t == "quad":
            base = [P(-0.95, -0.65), P(0.95, -0.8), P(0.85, 0.7), P(-0.8, 0.85)]
            kind = it.get("kind", "any")
            if kind == "parallelogram":
                A = P(-0.95, -0.6); B = P(0.7, -0.75); D = P(-0.55, 0.8)
                base = [A, B, P(B.x + D.x - A.x, B.y + D.y - A.y), D]
            elif kind == "rectangle":
                base = [P(-0.95, -0.6), P(0.95, -0.6), P(0.95, 0.6), P(-0.95, 0.6)]
            elif kind == "trapezoid":
                base = [P(-1.0, -0.6), P(1.0, -0.6), P(0.55, 0.7), P(-0.7, 0.7)]
            elif kind == "cyclic":
                angs = [200, 320, 40, 130]
                base = [P(math.cos(math.radians(a)), math.sin(math.radians(a))) for a in angs]
            for nm, p in zip(i, base): pts[nm] = p
        elif t == "point":
            pts[i] = P(it["x"], it["y"])
        elif t == "midpoint":
            a, b = two(it["of"]); pts[i] = mid(a, b)
        elif t == "point_on_segment":
            a, b = two(it["of"]); k = float(it.get("ratio", 0.5))
            pts[i] = P(a.x + (b.x - a.x) * k, a.y + (b.y - a.y) * k)
        elif t == "foot":
            a, b = two(it["line"]); pts[i] = foot(g(it["from"]), a, b)
        elif t == "intersection":
            a, b = two(it["line1"]); c, d = two(it["line2"]); pts[i] = line_inter(a, b, c, d)
        elif t == "circumcenter":
            a, b, c = (g(x) for x in it["of"]); pts[i] = circumcenter(a, b, c)
        elif t == "incenter":
            a, b, c = (g(x) for x in it["of"]); pts[i] = incenter(a, b, c)
        elif t == "centroid":
            a, b, c = (g(x) for x in it["of"])
            pts[i] = P((a.x + b.x + c.x) / 3, (a.y + b.y + c.y) / 3)
        elif t == "orthocenter":
            a, b, c = (g(x) for x in it["of"])
            pts[i] = line_inter(a, foot(a, b, c), b, foot(b, a, c))
        elif t == "reflect_point":
            p, o = g(it["of"]), g(it["over"]); pts[i] = P(2 * o.x - p.x, 2 * o.y - p.y)
        elif t == "reflect_line":
            p = g(it["of"]); a, b = two(it["over"]); f = foot(p, a, b)
            pts[i] = P(2 * f.x - p.x, 2 * f.y - p.y)
        elif t == "circle":
            o = g(it["center"])
            r = dist(o, g(it["through"])) if "through" in it else float(it["r"])
            circ[i] = (o, r)
        elif t == "circumcircle":
            a, b, c = (g(x) for x in it["of"]); o = circumcenter(a, b, c); circ[i] = (o, dist(o, a))
        elif t == "incircle":
            a, b, c = (g(x) for x in it["of"]); circ[i] = (incenter(a, b, c), inradius(a, b, c))
        elif t == "point_on_circle":
            o, r = circ[it["circle"]]; ang = math.radians(float(it.get("angle", rnd.uniform(0, 360))))
            pts[i] = P(o.x + r * math.cos(ang), o.y + r * math.sin(ang))
        elif t == "line_circle":
            o, r = circ[it["circle"]]; a, b = two(it["line"])
            pts[i] = circle_line_inter(o, r, a, b, int(it.get("pick", 0)))
        elif t == "circle_circle":
            o1, r1 = circ[it["circle1"]]; o2, r2 = circ[it["circle2"]]
            pts[i] = circle_circle_inter(o1, r1, o2, r2, int(it.get("pick", 0)))
        elif t == "tangent_point":
            o, r = circ[it["circle"]]; e = g(it["from"]); m = mid(o, e)
            pts[i] = circle_circle_inter(o, r, m, dist(m, o), int(it.get("pick", 0)))
        else:
            raise ValueError(f"неизвестный тип построения: {t}")
    return pts, circ

# ────────────────────────── проверки ──────────────────────────
def check(pts, circ):
    bad = []
    names = list(pts)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            if dist(pts[names[i]], pts[names[j]]) < 0.09:
                bad.append(f"{names[i]} и {names[j]} слились")
    xs = [p.x for p in pts.values()] + [o.x for o, r in circ.values()]
    ys = [p.y for p in pts.values()] + [o.y for o, r in circ.values()]
    if max(xs) - min(xs) > 12 or max(ys) - min(ys) > 12:
        bad.append("чертёж разъехался")
    for n, p in pts.items():
        if not (math.isfinite(p.x) and math.isfinite(p.y)):
            bad.append(f"{n} ушла в бесконечность")
    return bad

# ────────────────────────── отрисовка ──────────────────────────
def render(spec, pts, circ):
    xs = [p.x for p in pts.values()]; ys = [p.y for p in pts.values()]
    for o, r in circ.values():
        xs += [o.x - r, o.x + r]; ys += [o.y - r, o.y + r]
    k = min((W - 2 * PAD) / max(max(xs) - min(xs), 1e-6), (H - 2 * PAD) / max(max(ys) - min(ys), 1e-6))
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    S = lambda p: P(W / 2 + (p.x - cx) * k, H / 2 - (p.y - cy) * k)
    sp = {n: S(p) for n, p in pts.items()}

    o_ = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
          '<style>text{font-family:system-ui,-apple-system,"Segoe UI",Arial,sans-serif}</style>',
          f'<rect width="{W}" height="{H}" fill="#070C18"/>']
    def L(a, b, col, wd, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        o_.append(f'<line x1="{a.x:.1f}" y1="{a.y:.1f}" x2="{b.x:.1f}" y2="{b.y:.1f}" '
                  f'stroke="{col}" stroke-width="{wd}" stroke-linecap="round"{d}/>')
    def pair(s):
        a, b = split_ref(s, sp)
        return sp[a], sp[b]

    def style_of(d):
        st = d.get("style", "")
        return ({"accent": C_ACCENT, "soft": C_SOFT, "hint": C_ACCENT}.get(st, C_LINE),
                2.0 if st in ("accent", "hint") else 1.7 if st == "soft" else 2.3,
                "6 5" if st == "hint" or st == "dashed" else None)

    for d in spec.get("draw", []):
        col, wd, dash = style_of(d)
        if "polygon" in d:
            nm = d["polygon"]
            ptsx = " ".join(f"{sp[c].x:.1f},{sp[c].y:.1f}" for c in nm)
            o_.append(f'<polygon points="{ptsx}" fill="none" stroke="{col}" stroke-width="{wd}" '
                      f'stroke-linejoin="round"/>')
        elif "segment" in d:
            a, b = pair(d["segment"]); L(a, b, col, wd, dash)
        elif "line" in d:
            a, b = pair(d["line"]); v = u(b - a); e = max(W, H)
            L(P(a.x - v.x * e, a.y - v.y * e), P(b.x + v.x * e, b.y + v.y * e), col, wd, dash)
        elif "circle" in d:
            o, r = circ[d["circle"]]; c0 = S(o)
            o_.append(f'<circle cx="{c0.x:.1f}" cy="{c0.y:.1f}" r="{r*k:.1f}" fill="none" '
                      f'stroke="{C_CIRC}" stroke-width="1.9"/>')

    for m in spec.get("marks", []):
        if "right_angle" in m:
            v3 = m["right_angle"]
            if not (isinstance(v3, (list, tuple)) and len(v3) == 3): continue
            a, v, b = v3
            if a not in sp or v not in sp or b not in sp: continue
            V, u1, u2 = sp[v], u(sp[a] - sp[v]), u(sp[b] - sp[v]); s = 13
            p1, p2 = V + u1 * s, V + u2 * s; p3 = p1 + u2 * s
            o_.append(f'<polyline points="{p1.x:.1f},{p1.y:.1f} {p3.x:.1f},{p3.y:.1f} {p2.x:.1f},{p2.y:.1f}" '
                      f'fill="none" stroke="{C_SOFT}" stroke-width="1.6"/>')
        if "equal" in m:
            for idx, s in enumerate(m["equal"]):
                a, b = pair(s); c0 = mid(a, b); nv = u(P(-(b.y - a.y), b.x - a.x)); tv = u(b - a)
                cnt = m.get("ticks", 1)
                for t in range(cnt):
                    off = (t - (cnt - 1) / 2) * 5
                    base = P(c0.x + tv.x * off, c0.y + tv.y * off)
                    o_.append(f'<line x1="{base.x - nv.x*6:.1f}" y1="{base.y - nv.y*6:.1f}" '
                              f'x2="{base.x + nv.x*6:.1f}" y2="{base.y + nv.y*6:.1f}" '
                              f'stroke="{C_ACCENT}" stroke-width="2"/>')
        if "angle" in m:
            v3 = m["angle"]
            if not (isinstance(v3, (list, tuple)) and len(v3) == 3): continue
            a, v, b = v3
            if a not in sp or v not in sp or b not in sp: continue
            V = sp[v]; r = 26
            a1 = math.atan2(sp[a].y - V.y, sp[a].x - V.x); a2 = math.atan2(sp[b].y - V.y, sp[b].x - V.x)
            d = (a2 - a1 + math.pi * 2) % (math.pi * 2)
            if d > math.pi: a1, a2, d = a2, a1, math.pi * 2 - d
            s0 = P(V.x + r * math.cos(a1), V.y + r * math.sin(a1))
            e0 = P(V.x + r * math.cos(a1 + d), V.y + r * math.sin(a1 + d))
            o_.append(f'<path d="M {s0.x:.1f} {s0.y:.1f} A {r} {r} 0 0 1 {e0.x:.1f} {e0.y:.1f}" '
                      f'fill="none" stroke="{C_SOFT}" stroke-width="1.5"/>')
            if m.get("text"):
                tp = P(V.x + (r + 15) * math.cos(a1 + d / 2), V.y + (r + 15) * math.sin(a1 + d / 2) + 5)
                o_.append(f'<text x="{tp.x:.1f}" y="{tp.y:.1f}" fill="{C_SOFT}" font-size="15" '
                          f'text-anchor="middle">{m["text"]}</text>')

    segs = []
    for d in spec.get("draw", []):
        if "segment" in d or "line" in d:
            segs.append(pair(d.get("segment") or d["line"]))
        if "polygon" in d:
            nm = d["polygon"]
            segs += [(sp[nm[i]], sp[nm[(i + 1) % len(nm)]]) for i in range(len(nm))]

    ccx = sum(p.x for p in sp.values()) / len(sp); ccy = sum(p.y for p in sp.values()) / len(sp)
    for n, p in sp.items():
        if n in spec.get("hide_labels", []): continue
        best, bs = None, -1
        for deg in range(0, 360, 15):
            v = P(math.cos(math.radians(deg)), math.sin(math.radians(deg)))
            q = P(p.x + v.x * 20, p.y + v.y * 20)
            score = min([dist(q, foot(q, a, b)) if 0 <= dot(q - a, b - a) <= dot(b - a, b - a)
                         else min(dist(q, a), dist(q, b)) for a, b in segs] or [99])
            score += 0.35 * (dot(v, u(P(p.x - ccx, p.y - ccy))) + 1) * 10
            if score > bs: bs, best = score, v
        tp = P(p.x + best.x * 20, p.y + best.y * 20 + 6)
        o_.append(f'<circle cx="{p.x:.1f}" cy="{p.y:.1f}" r="3.4" fill="{C_LABEL}"/>')
        o_.append(f'<text x="{tp.x:.1f}" y="{tp.y:.1f}" fill="{C_LABEL}" font-size="19" '
                  f'font-style="italic" text-anchor="middle">{n}</text>')
    o_.append("</svg>")
    return "\n".join(o_)

def draw(spec, seed0=1, tries=50):
    last = ["не удалось построить"]
    for a in range(tries):
        try:
            pts, circ = build(spec, seed0 + a * 137)
            bad = check(pts, circ)
            if not bad:
                return render(spec, pts, circ), a + 1, []
            last = bad
        except Exception as e:
            last = [str(e)]
    return None, tries, last

# ────────────────────────── договор с моделью ──────────────────────────
CONTRACT = """Ты строишь чертёж к задаче по планиметрии. Отвечай ТОЛЬКО JSON, без пояснений и без markdown.

Формат:
{"given":[...], "draw":[...], "marks":[...], "aux":[...], "draw_aux":[...]}

В "given" — список построений по порядку, каждое со своим "id":
{"type":"triangle","id":"ABC","kind":"acute|right|obtuse|isosceles|any"}
{"type":"quad","id":"ABCD","kind":"parallelogram|rectangle|trapezoid|cyclic|any"}
{"type":"midpoint","id":"M","of":"AB"}
{"type":"point_on_segment","id":"K","of":"AB","ratio":0.35}
{"type":"foot","id":"D","from":"A","line":"BC"}
{"type":"intersection","id":"H","line1":"AD","line2":"BE"}
{"type":"circumcenter","id":"O","of":"ABC"}
{"type":"incenter","id":"I","of":"ABC"}
{"type":"centroid","id":"G","of":"ABC"}
{"type":"orthocenter","id":"H","of":"ABC"}
{"type":"reflect_point","id":"A1","of":"A","over":"M"}
{"type":"reflect_line","id":"A2","of":"A","over":"BC"}
{"type":"circle","id":"w","center":"O","through":"A"}
{"type":"circumcircle","id":"w","of":"ABC"}
{"type":"incircle","id":"w","of":"ABC"}
{"type":"point_on_circle","id":"P","circle":"w","angle":40}
{"type":"line_circle","id":"X","circle":"w","line":"AD","pick":0}
{"type":"circle_circle","id":"X","circle1":"w1","circle2":"w2","pick":0}
{"type":"tangent_point","id":"T","circle":"w","from":"S","pick":0}

В "draw" — что видно:
{"polygon":"ABC"} {"segment":"AD","style":"soft"} {"line":"MN"} {"circle":"w"}
style: пусто основное, "soft" вспомогательное, "accent" то, о чём спрашивают, "dashed" пунктир.

В "marks":
{"right_angle":["A","D","B"]}
{"equal":["AM","MB"],"ticks":1}
{"angle":["B","A","C"],"text":"60°"}

В "aux" — дополнительные построения, нужные для решения, того же формата,
плюс поле "reason" одной строкой по-русски. В "draw_aux" — как их рисовать.
Если решение обходится без дополнительных построений, верни "aux":[] и "draw_aux":[].
Ничего не выдумывай ради заполнения.

Правила:
1. Никаких координат. Только построения. Исключение — {"type":"point","id":"X","x":0,"y":0}, применять в крайнем случае.
2. Каждое имя объявляется один раз, ссылаться можно только на объявленное ранее.
3. Обозначения бери из условия. Не переименовывай.
4. Не рисуй то, чего нет в условии, кроме блока aux.
5. Если задача не про планиметрию или чертёж не нужен — верни {"skip":"причина"}."""

def ask_model(task, retry_notes=None):
    msg = f"Условие:\n{task['text'][:2000]}"
    if task.get("solution"):
        msg += f"\n\nРешение (для понимания, что важно на чертеже):\n{task['solution'][:4000]}"
    if retry_notes:
        msg += f"\n\nПрошлый ответ отклонён: {retry_notes}. Исправь и верни JSON заново."
    r = requests.post(API_URL, timeout=90,
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        json={"model": MODEL, "temperature": 0.2,
              "messages": [{"role": "system", "content": CONTRACT}, {"role": "user", "content": msg}]})
    if r.status_code == 429: raise RuntimeError("429")
    r.raise_for_status()
    d = r.json()
    txt = d["choices"][0]["message"]["content"]
    usage = d.get("usage", {})
    m = re.search(r"\{.*\}", txt, re.S)
    if not m: raise ValueError("модель вернула не JSON")
    return json.loads(m.group(0)), usage

def normalize(spec):
    """модель иногда шлёт словарь вместо списка или строку вместо словаря"""
    if not isinstance(spec, dict):
        raise ValueError("ответ не объект")
    for key in ("given", "draw", "marks", "aux", "draw_aux"):
        v = spec.get(key)
        if v is None:
            spec[key] = []
        elif isinstance(v, dict):
            spec[key] = [v] if ("type" in v or "id" in v or "segment" in v or
                                "polygon" in v or "line" in v or "circle" in v) else list(v.values())
        elif not isinstance(v, list):
            spec[key] = []
        spec[key] = [x for x in spec[key] if isinstance(x, dict)]
    for it in spec["given"] + spec["aux"]:
        if not isinstance(it.get("id"), str):
            it["id"] = str(it.get("id", ""))
    return spec


def validate_spec(spec):
    if "skip" in spec: return []
    if not isinstance(spec.get("given"), list) or not spec["given"]:
        return ["пустой given"]
    bad, known = [], set()
    for it in spec["given"] + spec.get("aux", []):
        if "id" not in it or "type" not in it: bad.append("построение без id или type"); continue
        for ch in (it["id"] if it["type"] in ("triangle", "quad") else [it["id"]]): known.add(ch)
        known.add(it["id"])
    for d in spec.get("draw", []) + spec.get("draw_aux", []):
        if "polygon" in d:
            for ch in d["polygon"]:
                if ch not in known: bad.append(f"в draw ссылка на неизвестное: {ch}")
        ref = d.get("segment") or d.get("line")
        if ref:
            try:
                a, b = split_ref(ref, known)
                if a not in known or b not in known:
                    bad.append(f"в draw ссылка на неизвестное: {ref}")
            except ValueError:
                bad.append(f"в draw не разобрать ссылку: {ref}")
        if "circle" in d and d["circle"] not in known: bad.append(f"нет окружности {d['circle']}")
    return bad

# ────────────────────────── прогон ──────────────────────────
lock = threading.Lock()
stat = {"ok": 0, "fail": 0, "skip": 0, "in": 0, "out": 0, "sleep": 0}

def one(task, outdir, logf, aux_too):
    try:
        _one(task, outdir, logf, aux_too)
    except Exception as e:
        with lock: stat["fail"] += 1
        write_log(logf, task.get("task_uid", "?"), "fail", 0, f"{type(e).__name__}: {e}"[:200], 0)


def _one(task, outdir, logf, aux_too):
    uid = task["task_uid"]
    print(f"  ... {uid[:8]} отправлено в модель", flush=True)
    svg_path = outdir / f"{uid}.svg"
    notes, t0 = None, time.time()
    for attempt in range(3):
        try:
            spec, usage = ask_model(task, notes)
        except RuntimeError:
            with lock: stat["sleep"] += 1
            time.sleep(20); continue
        except Exception as e:
            notes = f"{type(e).__name__}: {e}"[:200]
            print(f"  !!! {uid[:8]} {notes}", flush=True)
            continue
        with lock:
            stat["in"] += usage.get("prompt_tokens", 0); stat["out"] += usage.get("completion_tokens", 0)
        try:
            spec = normalize(spec)
        except Exception as e:
            notes = f"кривой ответ: {e}"[:200]; continue
        if "skip" in spec:
            with lock: stat["skip"] += 1
            write_log(logf, uid, "skip", attempt + 1, spec["skip"], time.time() - t0); return
        bad = validate_spec(spec)
        if bad: notes = "; ".join(bad)[:300]; continue
        svg, tries, errs = draw(spec)
        if svg is None: notes = "; ".join(errs)[:300]; continue
        svg_path.write_text(svg, encoding="utf-8")
        (outdir / f"{uid}.json").write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
        if aux_too and isinstance(spec.get("aux"), list) and spec["aux"]:
            merged = dict(spec)
            merged["given"] = spec["given"] + spec["aux"]
            merged["draw"] = spec["draw"] + spec.get("draw_aux", [])
            s2, _, e2 = draw(merged)
            if s2: (outdir / f"{uid}_aux.svg").write_text(s2, encoding="utf-8")
        with lock: stat["ok"] += 1
        write_log(logf, uid, "ok", attempt + 1, f"семян: {tries}", time.time() - t0); return
    with lock: stat["fail"] += 1
    write_log(logf, uid, "fail", 3, notes or "", time.time() - t0)

def write_log(logf, uid, status, attempts, note, sec):
    with lock:
        mark = {"ok": "готово", "fail": "не вышло", "skip": "пропущено"}[status]
        print(f"  [{stat['ok']+stat['fail']+stat['skip']}] {uid[:8]} — {mark}, "
              f"попыток {attempts}, {sec:.0f} c  {note[:70]}", flush=True)
        logf.write(json.dumps({"uid": uid, "status": status, "attempts": attempts,
                               "note": note, "sec": round(sec, 1)}, ensure_ascii=False) + "\n")
        logf.flush()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tasks"); ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=5); ap.add_argument("--grade", type=int, default=0)
    ap.add_argument("--resume", action="store_true"); ap.add_argument("--out", default="out")
    ap.add_argument("--no-aux", action="store_true")
    ap.add_argument("--check", action="store_true", help="проверить связь и выйти")
    a = ap.parse_args()
    if a.check:
        t0 = time.time()
        r = requests.post(API_URL, timeout=90,
            headers={"Authorization": f"Bearer {API_KEY}"},
            json={"model": MODEL, "messages": [{"role": "user", "content": "ответь одним словом: работает"}]})
        print("код", r.status_code, "за", round(time.time() - t0, 1), "сек")
        print(r.text[:600]); return
    if not API_KEY: sys.exit("не задан DEEPSEEK_API_KEY")

    tasks = json.loads(Path(a.tasks).read_text(encoding="utf-8"))
    if a.grade: tasks = [t for t in tasks if t.get("grade") == a.grade]
    outdir = Path(a.out) / "figures"; outdir.mkdir(parents=True, exist_ok=True)
    if a.resume: tasks = [t for t in tasks if not (outdir / f"{t['task_uid']}.svg").exists()]
    if a.limit: tasks = tasks[:a.limit]
    print(f"модель: {MODEL} | к построению: {len(tasks)} | потоков: {a.workers}")

    t0 = time.time()
    with open(Path(a.out) / "figures_batch.jsonl", "a", encoding="utf-8") as logf:
        with ThreadPoolExecutor(max_workers=a.workers) as ex:
            futs = [ex.submit(one, t, outdir, logf, not a.no_aux) for t in tasks]
            done = 0
            for f in futs:
                try:
                    f.result()
                except Exception as e:
                    print(f"  !!! сбой потока: {e}", flush=True)
                done += 1
                el = time.time() - t0
                print(f"{done}/{len(tasks)} | готово {stat['ok']} | не вышло {stat['fail']} | "
                      f"пропущено {stat['skip']} | {el/done:.1f} c на задачу", flush=True)
    cost = stat["in"] / 1e6 * 0.14 + stat["out"] / 1e6 * 0.28
    print(f"\nитого готово: {stat['ok']}, не вышло: {stat['fail']}, пропущено: {stat['skip']}")
    print(f"токенов вход {stat['in']}, выход {stat['out']}, ожиданий 429: {stat['sleep']}")
    print(f"стоимость по тарифу V4 Flash: ${cost:.3f}")
    print(f"время: {(time.time()-t0)/60:.1f} мин | файлы: {outdir}")

if __name__ == "__main__":
    main()
