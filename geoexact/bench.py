# -*- coding: utf-8 -*-
"""Бенчмарк чертежей GeoExact (офлайн, без LLM).

Метрики на одну спецификацию (см. geoexact/offline.py):
  built        — конвейер вернул чертёж (ok) не из fallback/sketch;
  refused      — отказ (ok=False) или эскиз по ключевым словам;
  approximate  — чертёж из best-effort ветки (verification=approximate/simplified);
  violations   — нарушенные проверки `checks` спецификации (численно, по координатам
                 точек из SVG; проверяются только подобие-инвариантные отношения);
  overlaps     — пересечения подписей (bbox текста) с другими подписями, точками
                 и линиями чертежа;
  missing_aux  — элементы `expect` (точки/отрезки/окружности), которых нет на чертеже;
  small_font   — эффективный размер подписи на экране 360 px меньше 11 px.

Спецификация может содержать
  "checks": [{"type": "collinear", "args": [...]}, ...]  — типы как в schema.CONSTRAINTS
            (+ "angle_eq", "dist_eq", "dist_ratio" с value, "concyclic", "tangent":
            [O,P,A,B] — прямая AB касается окружности (O,|OP|));
  "expect": {"points": [...], "segments": [[A,B],...], "circles": [[O,P],...]}.

CLI: python -m geoexact.bench DIR_OR_JSONL [--aux|--no-aux] [--out report.json]
"""
from __future__ import annotations

import argparse
import json
import math
import pathlib
import sys
import time
import xml.etree.ElementTree as ET

import numpy as np

NS = "{http://www.w3.org/2000/svg}"
PHONE_WIDTH = 360.0


# ------------------------------------------------------------------ SVG parsing
def parse_svg(svg: str) -> dict:
    root = ET.fromstring(svg)
    width = float(root.get("width", "560").replace("px", ""))
    pts, labels, lines, circles, texts = {}, [], [], [], []
    for el in root.iter():
        tag = el.tag.replace(NS, "")
        cls = el.get("class", "") or ""
        if tag == "circle" and el.get("data-point"):
            pts[el.get("data-point")] = np.array([float(el.get("cx")), float(el.get("cy"))])
        elif tag == "circle":
            try:
                circles.append((float(el.get("cx")), float(el.get("cy")), float(el.get("r")), cls))
            except (TypeError, ValueError):
                pass
        elif tag == "line":
            try:
                lines.append(((float(el.get("x1")), float(el.get("y1"))),
                              (float(el.get("x2")), float(el.get("y2"))), cls))
            except (TypeError, ValueError):
                pass
        elif tag == "text":
            content = (el.text or "") + "".join((t.text or "") for t in el)
            try:
                x, y = float(el.get("x")), float(el.get("y"))
            except (TypeError, ValueError):
                continue
            fs = 15.0 if "lab" in cls.split() else 12.5
            if el.get("font-size"):
                try:
                    fs = float(el.get("font-size").replace("px", ""))
                except ValueError:
                    pass
            m = None
            import re
            m = re.search(r"\.%s\s*\{[^}]*font-size:\s*([\d.]+)px" % (cls.split()[0] if cls else "zz"), svg)
            if m:
                fs = float(m.group(1))
            w = max(1, len(content.strip())) * fs * 0.58
            h = fs * 0.9
            anchor = el.get("text-anchor", "start")
            x0 = x - w / 2 if anchor == "middle" else (x - w if anchor == "end" else x)
            box = (x0, y - h * 0.8, x0 + w, y + h * 0.2)
            texts.append({"text": content.strip(), "box": box, "fs": fs, "cls": cls,
                          "point": el.get("data-point")})
    return {"width": width, "points": pts, "lines": lines, "circles": circles, "texts": texts,
            "root": root}


def _rect_overlap(a, b, pad=0.0) -> float:
    w = min(a[2], b[2]) - max(a[0], b[0]) + pad
    h = min(a[3], b[3]) - max(a[1], b[1]) + pad
    return max(0.0, w) * max(0.0, h)


def _seg_rect(p, q, r) -> bool:
    (x1, y1), (x2, y2) = p, q
    for t in np.linspace(0, 1, 25):
        x, y = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
        if r[0] + 1 < x < r[2] - 1 and r[1] + 1 < y < r[3] - 1:
            return True
    return False


def overlaps(parsed: dict) -> list[str]:
    out = []
    T = parsed["texts"]
    for i in range(len(T)):
        for j in range(i + 1, len(T)):
            a, b = T[i]["box"], T[j]["box"]
            area = _rect_overlap(a, b)
            small = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
            if area > 0.12 * small:
                out.append(f"text/text {T[i]['text']}~{T[j]['text']}")
    for t in T:
        for name, p in parsed["points"].items():
            if t["point"] == name:
                continue
            r = t["box"]
            if r[0] < p[0] < r[2] and r[1] < p[1] < r[3]:
                out.append(f"text/point {t['text']}~{name}")
        if "lab" in t["cls"].split():
            hits = sum(1 for p, q, c in parsed["lines"] if _seg_rect(p, q, _shrink(t["box"], 0.25)))
            if hits:
                out.append(f"label/line {t['text']}×{hits}")
    return out


def _shrink(r, k):
    dx, dy = (r[2] - r[0]) * k / 2, (r[3] - r[1]) * k / 2
    return (r[0] + dx, r[1] + dy, r[2] - dx, r[3] - dy)


# ------------------------------------------------------------------ numeric checks
def _ang(A, B, C):
    u, v = A - B, C - B
    c = float(np.dot(u, v) / (np.linalg.norm(u) * np.linalg.norm(v) + 1e-12))
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def _cross(u, v):
    return float(u[0] * v[1] - u[1] * v[0])


def check_relation(c: dict, P: dict, span: float) -> float | None:
    """Относительная невязка (0 — выполнено). None — точек нет на чертеже."""
    t, a = c["type"], c.get("args", [])
    if any(n not in P for n in a):
        return None
    X = [P[n] for n in a]
    n = lambda v: float(np.linalg.norm(v))  # noqa: E731
    if t == "collinear":
        return abs(_cross(X[1] - X[0], X[2] - X[0])) / (span ** 2)
    if t == "perpendicular":
        u, v = X[1] - X[0], X[3] - X[2]
        return abs(float(np.dot(u, v))) / (n(u) * n(v) + 1e-12)
    if t == "parallel":
        u, v = X[1] - X[0], X[3] - X[2]
        return abs(_cross(u, v)) / (n(u) * n(v) + 1e-12)
    if t == "dist_eq":
        return abs(n(X[0] - X[1]) - n(X[2] - X[3])) / span
    if t == "dist_ratio":
        return abs(n(X[0] - X[1]) - c["value"] * n(X[2] - X[3])) / span
    if t == "angle_eq":
        return abs(_ang(*X[:3]) - _ang(*X[3:6])) / 180.0
    if t == "angle":
        return abs(_ang(*X) - c["value"]) / 180.0
    if t == "concyclic":
        rows = [[p[0] ** 2 + p[1] ** 2, p[0], p[1], 1.0] for p in X]
        return abs(float(np.linalg.det(np.array(rows)))) / span ** 4
    if t == "on_circle":
        return abs(n(X[0] - X[1]) - n(X[2] - X[3])) / span
    if t == "on_segment":
        col = abs(_cross(X[2] - X[1], X[0] - X[1])) / span ** 2
        tt = float(np.dot(X[0] - X[1], X[2] - X[1]) / (np.dot(X[2] - X[1], X[2] - X[1]) + 1e-12))
        return col + max(0.0, -tt) + max(0.0, tt - 1)
    if t == "tangent":            # [O, P, A, B]: прямая AB касается окружности (O,|OP|)
        O, Pp, A, B = X
        d = abs(_cross(B - A, O - A)) / (n(B - A) + 1e-12)
        return abs(d - n(Pp - O)) / span
    raise ValueError(f"unknown check {t}")


def numeric_violations(spec: dict, parsed: dict, tol: float = 2e-3) -> list[str]:
    P = parsed["points"]
    if len(P) < 2:
        return ["NO_POINTS"]
    arr = np.array(list(P.values()))
    span = float(np.max(np.ptp(arr, axis=0))) or 1.0
    bad = []
    for c in spec.get("checks", []):
        r = check_relation(c, P, span)
        if r is None:
            bad.append(f"MISSING {c['type']}({','.join(c.get('args', []))})")
        elif r > tol:
            bad.append(f"{c['type']}({','.join(c.get('args', []))}) err={r:.3g}")
    return bad


def missing_expected(spec: dict, parsed: dict) -> list[str]:
    exp = spec.get("expect") or {}
    P = parsed["points"]
    out = [f"point {p}" for p in exp.get("points", []) if p not in P]
    ends = [(np.array(p), np.array(q)) for p, q, _ in parsed["lines"]]

    def covered(a, b):
        A, B = P[a], P[b]
        L = float(np.linalg.norm(B - A)) or 1.0
        for p, q in ends:
            d = q - p
            ln = float(np.linalg.norm(d))
            if ln < 1e-9:
                continue
            # both A and B lie on the drawn line (within 1.5px) and the piece overlaps
            if all(abs(_cross(d, X - p)) / ln < 1.5 for X in (A, B)):
                ta = float(np.dot(A - p, d)) / ln ** 2
                tb = float(np.dot(B - p, d)) / ln ** 2
                lo, hi = sorted((ta, tb))
                if min(hi, 1.0) - max(lo, 0.0) > 0.5 * L / ln:
                    return True
        return False

    for s in exp.get("segments", []):
        if not all(x in P for x in s):
            out.append(f"segment {''.join(s)} (нет точки)")
        elif not covered(*s):
            out.append(f"segment {''.join(s)}")
    circles = parsed["circles"]
    for o, p in exp.get("circles", []):
        if o not in P or p not in P:
            out.append(f"circle ({o},{p}) (нет точки)")
            continue
        r = float(np.linalg.norm(P[o] - P[p]))
        if not any(abs(cx - P[o][0]) < 1.5 and abs(cy - P[o][1]) < 1.5 and abs(cr - r) < 1.5
                   for cx, cy, cr, _ in circles):
            out.append(f"circle ({o},{p})")
    return out


def check(spec: dict, res) -> dict:
    rep = {"uid": spec.get("uid", ""), "ok": bool(res.ok), "stage": res.stage,
           "reason": res.reason, "verification": res.verification,
           "seconds": round(res.seconds, 2)}
    rep["built"] = bool(res.ok and res.stage == "9-render")
    rep["approximate"] = bool(res.ok and res.verification in ("approximate", "simplified", "sketch"))
    rep["refused"] = not res.ok or res.verification == "sketch"
    rep["detail"] = (res.detail or "")[:300]
    rep["warnings"] = [w[:160] for w in res.warnings]
    if res.svg:
        parsed = parse_svg(res.svg)
        rep["violations"] = numeric_violations(spec, parsed)
        rep["overlaps"] = overlaps(parsed)
        rep["missing"] = missing_expected(spec, parsed)
        lab = [t["fs"] for t in parsed["texts"] if "lab" in t["cls"].split()]
        eff = (min(lab) if lab else 15.0) * PHONE_WIDTH / max(parsed["width"], PHONE_WIDTH)
        rep["phone_label_px"] = round(eff, 1)
        rep["small_font"] = eff < 11.0
    else:
        rep.update(violations=["NO_SVG"], overlaps=[], missing=["NO_SVG"], small_font=False)
    rep["clean"] = bool(rep["built"] and not rep["approximate"] and not rep["violations"]
                        and not rep["overlaps"] and not rep["missing"])
    return rep


def load_specs(path: str) -> list[dict]:
    p = pathlib.Path(path)
    if p.is_dir():
        return [dict(json.loads(f.read_text(encoding="utf-8")), _file=str(f))
                for f in sorted(p.glob("*.json"))]
    if p.suffix == ".jsonl":
        return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    return [json.loads(p.read_text(encoding="utf-8"))]


def summarize(reps: list[dict]) -> dict:
    n = len(reps) or 1
    return {
        "n": len(reps),
        "built": sum(r["built"] for r in reps) / n,
        "refused": sum(r["refused"] for r in reps) / n,
        "approximate": sum(r["approximate"] for r in reps) / n,
        "with_violations": sum(bool(r["violations"]) for r in reps) / n,
        "with_overlaps": sum(bool(r["overlaps"]) for r in reps) / n,
        "overlap_count": sum(len(r["overlaps"]) for r in reps),
        "with_missing": sum(bool(r["missing"]) for r in reps) / n,
        "small_font": sum(bool(r.get("small_font")) for r in reps) / n,
        "clean": sum(r["clean"] for r in reps) / n,
    }


def main(argv=None) -> int:
    from .offline import run_spec, svg_to_png
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--no-aux", action="store_true")
    ap.add_argument("--out")
    ap.add_argument("--svgdir")
    ap.add_argument("--only")
    a = ap.parse_args(argv)
    specs = load_specs(a.path)
    if a.only:
        specs = [s for s in specs if a.only in s.get("uid", "")]
    reps = []
    for s in specs:
        t0 = time.time()
        try:
            res = run_spec(s, with_aux=False if a.no_aux else None)
            rep = check(s, res)
        except Exception as e:  # noqa: BLE001
            rep = {"uid": s.get("uid"), "ok": False, "built": False, "refused": True,
                   "approximate": False, "violations": [f"CRASH {type(e).__name__}: {e}"],
                   "overlaps": [], "missing": [], "clean": False, "stage": "crash"}
            res = None
        reps.append(rep)
        if a.svgdir and res is not None and res.svg:
            d = pathlib.Path(a.svgdir); d.mkdir(parents=True, exist_ok=True)
            (d / f"{s.get('uid', 'x')}.svg").write_text(res.svg, encoding="utf-8")
        flag = "CLEAN" if rep["clean"] else ("OK" if rep["built"] else rep.get("stage"))
        print(f"{s.get('uid','?'):28s} {flag:14s} {time.time()-t0:5.1f}s "
              f"V{len(rep['violations'])} O{len(rep['overlaps'])} M{len(rep['missing'])} "
              f"{rep.get('reason','')}", flush=True)
    summ = summarize(reps)
    print(json.dumps(summ, ensure_ascii=False))
    if a.out:
        json.dump({"summary": summ, "items": reps}, open(a.out, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
