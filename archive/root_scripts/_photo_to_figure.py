# -*- coding: utf-8 -*-
"""
Photo → Geometry Figure Pipeline
================================
  1. Tesseract OCR (rus+eng) — extract task text from photo
  2. DeepSeek cleanup      — fix OCR errors
  3. DeepSeek figure spec   — text → {"given":[...],"draw":[...]}
  4. build() + render()     — figure_json → SVG

One command:
    python _photo_to_figure.py photo.png
    python _photo_to_figure.py                   (auto-last-screenshot)

Output: out_figures/<name>.svg + .json
"""
import io
import json
import math
import os
import random
import re
import shutil
import subprocess
import sys
import time

import requests

# Windows console: UTF-8
if sys.platform == "win32":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__)) or "."
OUT_DIR = os.path.join(PROJECT_DIR, "out_figures")
os.makedirs(OUT_DIR, exist_ok=True)

# ----- Config ------------------------------------------------------
ENV_PATH = os.path.join(PROJECT_DIR, ".env")
if os.path.exists(ENV_PATH):
    with open(ENV_PATH, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip("\"'"))

DEEPSEEK_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
MODEL = os.environ.get("FIGURE_MODEL", "deepseek-v4-flash")

# ----- Tesseract ---------------------------------------------------
TESSCACHE = os.path.join(os.path.expanduser("~"), "tessdata_both")
os.makedirs(TESSCACHE, exist_ok=True)

for p in [
    os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "Tesseract-OCR", "tesseract.exe"),
    os.path.join(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"), "Tesseract-OCR", "tesseract.exe"),
]:
    if os.path.exists(p):
        TESSERACT = p
        break
else:
    TESSERACT = shutil.which("tesseract") or ""

SYSTEM_TESSDATA = os.path.join(os.path.dirname(TESSERACT), "tessdata")
if os.path.exists(os.path.join(SYSTEM_TESSDATA, "eng.traineddata")):
    for fname in ["eng.traineddata", "rus.traineddata"]:
        src = os.path.join(SYSTEM_TESSDATA, fname)
        dst = os.path.join(TESSCACHE, fname)
        if os.path.exists(src) and not os.path.exists(dst):
            shutil.copy2(src, dst)

# Check for rus in project
rus_dst = os.path.join(TESSCACHE, "rus.traineddata")
if not os.path.exists(rus_dst):
    for src in [os.path.join(PROJECT_DIR, "rus.traineddata"),
                os.path.join(PROJECT_DIR, "tessdata", "rus.traineddata")]:
        if os.path.exists(src):
            shutil.copy2(src, rus_dst)

USE_RUS = os.path.exists(rus_dst)

# ----- DeepSeek API helper -----------------------------------------
def ask_deepseek(system_prompt, user_message, temperature=0.2, max_tokens=2000):
    r = requests.post(DEEPSEEK_URL, timeout=90,
        headers={"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"},
        json={"model": MODEL, "temperature": temperature, "max_tokens": max_tokens,
              "messages": [{"role": "system", "content": system_prompt},
                           {"role": "user", "content": user_message}]})
    if r.status_code == 429:
        raise RuntimeError("429 rate limit")
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]

# ----- Stage 1: OCR ------------------------------------------------
def ocr_photo(image_path):
    """Tesseract OCR. Returns raw text."""
    lang = "rus+eng" if USE_RUS else "eng"
    temp_img = os.path.join(TESSCACHE, "_ocr_work.png")
    shutil.copy2(image_path, temp_img)
    t0 = time.time()
    result = subprocess.run(
        [TESSERACT, temp_img, "stdout", "-l", lang, "--psm", "3", "--tessdata-dir", TESSCACHE],
        capture_output=True, encoding="utf-8", errors="replace", timeout=30)
    elapsed = time.time() - t0
    text = (result.stdout or "").strip()
    try:
        os.remove(temp_img)
    except OSError:
        pass
    print(f"  [OCR] {elapsed:.1f}s, {len(text)} chars")
    return text

# ----- Stage 2: Clean OCR text -------------------------------------
def clean_task_text(raw_ocr):
    """DeepSeek fixes OCR errors, restores proper math problem text."""
    prompt = (
        "OCR result from a photo of a Russian math problem. Fix errors:\n"
        "1. Restore correct Russian text (fix cyrillic/latin mixups).\n"
        "2. Formulas as plain text: x^2, a/b, sqrt(...), <=, >=.\n"
        "3. Return ONLY the clean task statement, nothing else.\n\n"
        f"OCR text:\n{raw_ocr}"
    )
    t0 = time.time()
    try:
        text = ask_deepseek("Ты — корректор OCR-текста математических задач.", prompt, 0.1, 800)
        print(f"  [Clean] {time.time()-t0:.1f}s")
        return text.strip()
    except Exception as e:
        print(f"  [Clean] Failed: {e}")
        return raw_ocr

# ----- Stage 3: Text → Figure JSON ---------------------------------
# Same CONTRACT as formyla_figures.py
FIGURE_CONTRACT = """Ты строишь чертёж к задаче по планиметрии. Отвечай ТОЛЬКО JSON, без пояснений и без markdown.

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

В "aux" — доп. построения для решения того же формата + "reason".
Если не нужно — верни "aux":[] и "draw_aux":[].
Если задача НЕ про планиметрию — верни {"skip":"причина"}."""


def task_to_spec(task_text, retry_notes=None):
    """DeepSeek generates figure JSON spec from task text."""
    msg = f"Условие:\n{task_text[:2000]}"
    if retry_notes:
        msg += f"\n\nПрошлый ответ отклонён: {retry_notes}. Исправь и верни JSON заново."
    
    # Use deepseek-chat for better instruction following
    r = requests.post(DEEPSEEK_URL, timeout=90,
        headers={"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"},
        json={"model": "deepseek-chat", "temperature": 0.1, "max_tokens": 2000,
              "messages": [{"role": "system", "content": FIGURE_CONTRACT},
                           {"role": "user", "content": msg}]})
    if r.status_code == 429:
        raise RuntimeError("429 rate limit")
    r.raise_for_status()
    raw = r.json()["choices"][0]["message"]["content"]
    
    # Debug: log raw response
    print(f"  [Figure] Raw response ({len(raw)} chars): {raw[:200]}...")
    
    # Try multiple JSON extraction strategies
    # 1. Find JSON between ```json``` blocks
    m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw, re.S)
    if m:
        return json.loads(m.group(1))
    # 2. Find first { ... } with balanced braces
    m = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', raw, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    # 3. Try whole response
    stripped = raw.strip()
    if stripped.startswith("{"):
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass
    raise ValueError(f"модель вернула не JSON: {raw[:300]}")


# ----- Geometry engine (copied from formyla_figures.py) ------------
W, H = 620, 620
PAD = 60
C_LINE, C_ACCENT, C_SOFT, C_LABEL, C_CIRC = "#C8D6E5", "#4C7DFF", "#8C9ABC", "#E6EBF7", "#A9BBD6"


class P:
    __slots__ = ("x", "y")
    def __init__(s, x, y):
        s.x, s.y = float(x), float(y)
    def __sub__(s, o):
        return P(s.x - o.x, s.y - o.y)
    def __add__(s, o):
        return P(s.x + o.x, s.y + o.y)
    def __mul__(s, k):
        return P(s.x * k, s.y * k)
    def n(s):
        return math.hypot(s.x, s.y)


def u(v):
    d = v.n()
    return P(v.x / d, v.y / d) if d > 1e-12 else P(0, 0)


def dot(a, b):
    return a.x * b.x + a.y * b.y


def cross(a, b):
    return a.x * b.y - a.y * b.x


def mid(a, b):
    return P((a.x + b.x) / 2, (a.y + b.y) / 2)


def dist(a, b):
    return (a - b).n()


def split_ref(s, known):
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


def line_inter(a, b, c, d_pt):
    den = cross(b - a, d_pt - c)
    if abs(den) < 1e-9:
        raise ValueError("прямые параллельны")
    t = cross(c - a, d_pt - c) / den
    return P(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t)


def circle_line_inter(o, r, a, b, pick=0):
    d_v = u(b - a)
    f = a - o
    B = 2 * dot(f, d_v)
    C = dot(f, f) - r * r
    disc = B * B - 4 * C
    if disc < 0:
        raise ValueError("прямая не пересекает окружность")
    s = math.sqrt(disc)
    ts = sorted([(-B - s) / 2, (-B + s) / 2])
    t = ts[min(pick, 1)]
    return P(a.x + d_v.x * t, a.y + d_v.y * t)


def circle_circle_inter(o1, r1, o2, r2, pick=0):
    d = dist(o1, o2)
    if d > r1 + r2 or d < abs(r1 - r2) or d < 1e-9:
        raise ValueError("окружности не пересекаются")
    a = (r1 * r1 - r2 * r2 + d * d) / (2 * d)
    h2 = r1 * r1 - a * a
    if h2 < 0:
        raise ValueError("окружности не пересекаются")
    h = math.sqrt(h2)
    m = P(o1.x + (o2.x - o1.x) * a / d, o1.y + (o2.y - o1.y) * a / d)
    n = P(-(o2.y - o1.y) / d, (o2.x - o1.x) / d)
    return P(m.x + n.x * h, m.y + n.y * h) if pick == 0 else P(m.x - n.x * h, m.y - n.y * h)


def circumcenter(a, b, c):
    d = 2 * (a.x * (b.y - c.y) + b.x * (c.y - a.y) + c.x * (a.y - b.y))
    if abs(d) < 1e-9:
        raise ValueError("точки на одной прямой")
    qa, qb, qc = a.x ** 2 + a.y ** 2, b.x ** 2 + b.y ** 2, c.x ** 2 + c.y ** 2
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


def build(spec, seed):
    rnd = random.Random(seed)
    pts, circ = {}, {}

    def g(name):
        if name not in pts:
            raise ValueError(f"точка {name} не объявлена")
        return pts[name]

    def two(s):
        a, b = split_ref(s, pts)
        return g(a), g(b)

    for it in spec.get("given", []):
        t, i = it["type"], it["id"]
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
                if kind == "acute":
                    ok = ok and max(aa) < 82
                if kind == "obtuse":
                    ok = max(aa) > 100 and min(aa) > 22
                if kind == "right":
                    ok = abs(max(aa) - 90) < 1.5 and min(aa) > 28
                if kind == "isosceles":
                    ok = ok and abs(dist(A, B) - dist(A, C)) < 0.03
                if ok:
                    best = q
                    break
            if best is None:
                if kind == "right":
                    best = [P(-0.9, -0.5), P(0.9, -0.5), P(-0.9, 0.9)]
                elif kind == "isosceles":
                    best = [P(0, 1), P(-0.85, -0.6), P(0.85, -0.6)]
                else:
                    best = [P(-0.2, 1.0), P(-1.0, -0.7), P(1.0, -0.5)]
            for nm, p_pt in zip(i, best):
                pts[nm] = p_pt
        elif t == "quad":
            base = [P(-0.95, -0.65), P(0.95, -0.8), P(0.85, 0.7), P(-0.8, 0.85)]
            kind = it.get("kind", "any")
            if kind == "parallelogram":
                A, B, D = P(-0.95, -0.6), P(0.7, -0.75), P(-0.55, 0.8)
                base = [A, B, P(B.x + D.x - A.x, B.y + D.y - A.y), D]
            elif kind == "rectangle":
                base = [P(-0.95, -0.6), P(0.95, -0.6), P(0.95, 0.6), P(-0.95, 0.6)]
            elif kind == "trapezoid":
                base = [P(-1.0, -0.6), P(1.0, -0.6), P(0.55, 0.7), P(-0.7, 0.7)]
            for nm, p_pt in zip(i, base):
                pts[nm] = p_pt
        elif t == "point":
            pts[i] = P(it["x"], it["y"])
        elif t == "midpoint":
            a, b = two(it["of"])
            pts[i] = mid(a, b)
        elif t == "point_on_segment":
            a, b = two(it["of"])
            k = float(it.get("ratio", 0.5))
            pts[i] = P(a.x + (b.x - a.x) * k, a.y + (b.y - a.y) * k)
        elif t == "foot":
            a, b = two(it["line"])
            pts[i] = foot(g(it["from"]), a, b)
        elif t == "intersection":
            a, b = two(it["line1"])
            c_pt, d_pt = two(it["line2"])
            pts[i] = line_inter(a, b, c_pt, d_pt)
        elif t == "circumcenter":
            a, b, c_pt = (g(x) for x in it["of"])
            pts[i] = circumcenter(a, b, c_pt)
        elif t == "incenter":
            a, b, c_pt = (g(x) for x in it["of"])
            pts[i] = incenter(a, b, c_pt)
        elif t == "centroid":
            a, b, c_pt = (g(x) for x in it["of"])
            pts[i] = P((a.x + b.x + c_pt.x) / 3, (a.y + b.y + c_pt.y) / 3)
        elif t == "orthocenter":
            a, b, c_pt = (g(x) for x in it["of"])
            pts[i] = line_inter(a, foot(a, b, c_pt), b, foot(b, a, c_pt))
        elif t == "reflect_point":
            p_pt, o = g(it["of"]), g(it["over"])
            pts[i] = P(2 * o.x - p_pt.x, 2 * o.y - p_pt.y)
        elif t == "circle":
            o = g(it["center"])
            r = dist(o, g(it["through"])) if "through" in it else float(it["r"])
            circ[i] = (o, r)
        elif t == "circumcircle":
            a, b, c_pt = (g(x) for x in it["of"])
            o = circumcenter(a, b, c_pt)
            circ[i] = (o, dist(o, a))
        elif t == "incircle":
            a, b, c_pt = (g(x) for x in it["of"])
            circ[i] = (incenter(a, b, c_pt), inradius(a, b, c_pt))
        elif t == "point_on_circle":
            o, r = circ[it["circle"]]
            ang = math.radians(float(it.get("angle", rnd.uniform(0, 360))))
            pts[i] = P(o.x + r * math.cos(ang), o.y + r * math.sin(ang))
        elif t == "line_circle":
            o, r = circ[it["circle"]]
            a, b = two(it["line"])
            pts[i] = circle_line_inter(o, r, a, b, int(it.get("pick", 0)))
    return pts, circ


def check(pts, circ):
    bad = []
    for a, b in pts.items():
        if abs(b.x) > 1.8 or abs(b.y) > 1.8:
            bad.append(f"точка {a} выходит")
    for k, (o, r) in circ.items():
        if abs(o.x) > 1.8 or abs(o.y) > 1.8:
            bad.append(f"центр {k} выходит")
    pairs = list(pts.values())
    for i in range(len(pairs)):
        for j in range(i + 1, len(pairs)):
            if dist(pairs[i], pairs[j]) < 0.08:
                bad.append("слияние точек")
                return bad
    return bad


def render(spec, pts_in, circ):
    mnx = min(p.x for p in pts_in.values())
    mxx = max(p.x for p in pts_in.values())
    mny = min(p.y for p in pts_in.values())
    mxy = max(p.y for p in pts_in.values())
    sc = min((W - PAD * 2) / max(mxx - mnx, 0.01), (H - PAD * 2) / max(mxy - mny, 0.01))
    def mp(p):
        return P(PAD + (p.x - mnx) * sc, H - PAD - (p.y - mny) * sc)

    sp = {n: mp(p) for n, p in pts_in.items()}
    o_ = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
          f'viewBox="0 0 {W} {H}">',
          f'<rect width="{W}" height="{H}" fill="#16162A"/>']

    def pair(s):
        a, b = split_ref(s, sp)
        return sp[a], sp[b]

    for d in spec.get("draw", []):
        if "polygon" in d:
            nm = d["polygon"]
            st = d.get("style", "")
            col = {"soft": C_SOFT, "accent": C_ACCENT}.get(st, C_LINE)
            fill = "#2A2A4A" if st != "soft" else "none"
            pts_str = " ".join(f"{sp[c].x:.1f},{sp[c].y:.1f}" for c in nm)
            o_.append(f'<polygon points="{pts_str}" fill="{fill}" stroke="{col}" stroke-width="2"/>')
        if "segment" in d or "line" in d:
            ref = d.get("segment") or d["line"]
            a, b = pair(ref)
            st = d.get("style", "")
            col = {"soft": C_SOFT, "accent": C_ACCENT, "dashed": C_ACCENT}.get(st, C_LINE)
            dash = ' stroke-dasharray="6,4"' if st == "dashed" else ""
            o_.append(f'<line x1="{a.x:.1f}" y1="{a.y:.1f}" x2="{b.x:.1f}" y2="{b.y:.1f}" '
                      f'stroke="{col}" stroke-width="2"{dash}/>')
        if "circle" in d:
            if d["circle"] in circ:
                o_pt, r = circ[d["circle"]]
                c = mp(o_pt)
                rr = r * sc
                o_.append(f'<circle cx="{c.x:.1f}" cy="{c.y:.1f}" r="{rr:.1f}" '
                          f'fill="none" stroke="{C_CIRC}" stroke-width="1.8"/>')

    # Labels
    segs = []
    for d in spec.get("draw", []):
        if "segment" in d or "line" in d:
            segs.append(pair(d.get("segment") or d["line"]))
        if "polygon" in d:
            nm = d["polygon"]
            segs += [(sp[nm[i]], sp[nm[(i + 1) % len(nm)]]) for i in range(len(nm))]

    ccx = sum(p.x for p in sp.values()) / max(len(sp), 1)
    ccy = sum(p.y for p in sp.values()) / max(len(sp), 1)
    for n, p in sp.items():
        if n in spec.get("hide_labels", []):
            continue
        best, bs = None, -1
        for deg in range(0, 360, 15):
            v = P(math.cos(math.radians(deg)), math.sin(math.radians(deg)))
            q = P(p.x + v.x * 20, p.y + v.y * 20)
            score = min([dist(q, foot(q, a, b)) if 0 <= dot(q - a, b - a) <= dot(b - a, b - a)
                         else min(dist(q, a), dist(q, b)) for a, b in segs] or [99])
            score += 0.35 * (dot(v, u(P(p.x - ccx, p.y - ccy))) + 1) * 10
            if score > bs:
                bs, best = score, v
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


def normalize_spec(spec):
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
    for it in spec.get("given", []) + spec.get("aux", []):
        if not isinstance(it.get("id"), str):
            it["id"] = str(it.get("id", ""))
    return spec


# ----- Main pipeline -----------------------------------------------
def pipeline(image_path, name=None):
    """Full pipeline: photo → SVG."""
    t_total = time.time()
    name = name or os.path.splitext(os.path.basename(image_path))[0]

    print(f"\n{'='*60}")
    print(f"  PHOTO → FIGURE PIPELINE")
    print(f"  Image: {image_path}")
    print(f"{'='*60}\n")

    # 1. OCR
    if not os.path.exists(image_path):
        print(f"[FAIL] File not found: {image_path}")
        return None
    raw_ocr = ocr_photo(image_path)
    if not raw_ocr:
        print("[FAIL] OCR returned empty text")
        return None

    # 2. Clean
    clean_text = clean_task_text(raw_ocr)
    print(f"  Text: {clean_text[:200]}...")

    # 3. Figure spec
    print(f"  [Figure] Asking DeepSeek for geometry spec...")
    t0 = time.time()
    notes = None
    for attempt in range(3):
        try:
            spec = task_to_spec(clean_text, notes)
            break
        except Exception as e:
            notes = f"{type(e).__name__}: {e}"
            if attempt < 2:
                print(f"  [Figure] Attempt {attempt+1} failed: {notes}, retrying...")
    else:
        print(f"[FAIL] Could not generate figure spec after 3 attempts")
        return None
    print(f"  [Figure] Spec generated in {time.time()-t0:.1f}s")

    if "skip" in spec:
        print(f"[SKIP] {spec['skip']}")
        return spec

    # Normalize
    spec = normalize_spec(spec)

    # 4. Build + Render
    print(f"  [Draw] Building figure...")
    t0 = time.time()
    svg, tries, errs = draw(spec)
    if svg is None:
        print(f"[FAIL] Could not draw: {'; '.join(errs[:3])}")
        return spec
    print(f"  [Draw] Built in {tries} attempts, {time.time()-t0:.1f}s")

    # Save
    svg_path = os.path.join(OUT_DIR, f"{name}.svg")
    json_path = os.path.join(OUT_DIR, f"{name}.json")
    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(svg)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False, indent=2)

    total = time.time() - t_total
    print(f"\n{'='*60}")
    print(f"  DONE!")
    print(f"  SVG:  {svg_path}")
    print(f"  JSON: {json_path}")
    print(f"  Total: {total:.1f}s")
    print(f"{'='*60}")
    return svg


# ----- CLI ---------------------------------------------------------
if __name__ == "__main__":
    if not DEEPSEEK_KEY:
        print("[FAIL] DEEPSEEK_API_KEY not set in .env")
        sys.exit(1)

    image_path = sys.argv[1] if len(sys.argv) > 1 else None
    if not image_path:
        import glob
        screens = glob.glob(os.path.join(os.path.expanduser("~"), "Pictures", "Screenshots", "*.png"))
        if screens:
            image_path = screens[-1]
            print(f"[AUTO] Using last screenshot: {os.path.basename(image_path)}")
        else:
            print("[FAIL] No image provided and no screenshots found")
            sys.exit(1)

    pipeline(image_path)
