# -*- coding: utf-8 -*-
"""scripts/ch19_qa.py — детерминированный QA завершённых задач (CH19 Step 5).

БЕЗ LLM и БЕЗ vision.  Парсинг JSON-планов и SVG как XML.

Проверки (14):
  1. base не содержит style="aux" и dashed=true.
  2. Каждый aux-объект имеет purpose и solution_evidence.quote.
  3. Все ID-ссылки разрешимы.
  4. Операции, создающие точку, имеют foot_id.
  5. Все точки плана имеют label в SVG.
  6. Все подписи внутри границ canvas.
  7. stroke-цвета только из темы dark_geometry.
  8. visual_role только из разрешённого enum.
  9. has_aux=true -> aux SVG существует и непуст.
  10. has_aux=false -> aux SVG отсутствует.
  11. Число точек в SVG равно числу точек в плане.
  12. Точки, названные в statement, присутствуют в base plan.
  13. Предупреждение AUX_EXPECTED_BUT_MISSING: constructive & !has_aux.
  14. Предупреждение AUX_UNEXPECTED: analytic & has_aux & >=2 aux objects.

Пишет output/ch19/qa_report.md (таблица «код -> количество -> примеры»).
"""
import argparse
import csv
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts.ch19_lib import (  # noqa: E402
    allowed_colors,
    aux_constructions,
    base_constructions,
    classify_solution_style,
    extract_hex_colors,
    has_aux_flag,
    loads,
    merge_base_aux_plan,
    plan_point_labels,
    visible_points,
)
from services.figure_plan_validator import (  # noqa: E402
    _POINT_CREATING_TYPES,
    _VALID_VISUAL_ROLES,
)

# Ссылочные поля (зеркало figure_plan_validator).
_REFERENCE_FIELDS = [
    'p1', 'p2', 'p3', 'p4', 'center', 'line1', 'line2',
    'circle', 'circle1', 'circle2', 'origin',
    'a', 'b', 'vertex', 'side_a', 'side_b', 'points',
    'ray1', 'ray2',
]


def _refs(c):
    out = set()
    for f in _REFERENCE_FIELDS:
        v = c.get(f)
        if isinstance(v, str) and v:
            out.add(v)
        elif isinstance(v, list):
            for x in v:
                if isinstance(x, str) and x:
                    out.add(x)
                elif isinstance(x, (list, tuple)):
                    for y in x:
                        if isinstance(y, str) and y:
                            out.add(y)
    return out


def _parse_svg(path):
    try:
        tree = ET.parse(path)
        return tree.getroot()
    except Exception:
        return None


def _svg_labels(root):
    labels = []
    if root is None:
        return labels
    for t in root.iter():
        tag = t.tag.split('}')[-1]
        if tag == 'text' and t.text:
            labels.append(t.text.strip())
    return labels


def _svg_circles(root):
    """Число точек-кружков (circle с r ~ point_radius)."""
    n = 0
    if root is None:
        return 0
    for c in root.iter():
        tag = c.tag.split('}')[-1]
        if tag == 'circle':
            r = float(c.get('r') or 0)
            if 1.0 <= r <= 10.0:  # точки движка r=3.5; окружности крупнее
                n += 1
    return n


def _statement_point_names(statement):
    # Латинские буквы-имена точек: A, B, C, D, M, O, K, P, H, X, Y, Z ...
    toks = re.findall(r"\b[A-Z]\b", statement or "")
    return set(toks)


def qa_task(rec, out_dir, results_row=None):
    """Вернуть список кодов проблем для одной задачи."""
    uid = str(rec.get("task_uid"))
    codes = []
    style = classify_solution_style(rec)

    base_plan = None
    aux_plan = None
    base_svg_path = os.path.join(out_dir, "svg", f"{_safe(uid)}_base.svg")
    aux_svg_path = os.path.join(out_dir, "svg", f"{_safe(uid)}_aux.svg")

    # Планы ищем в артефактах, а при их отсутствии — в results (не хранится)
    base_plan_path = os.path.join(out_dir, "plans", f"{_safe(uid)}_base.json")
    aux_plan_path = os.path.join(out_dir, "plans", f"{_safe(uid)}_aux.json")

    base_plan = loads(open(base_plan_path, encoding="utf-8").read()) \
        if os.path.exists(base_plan_path) else None
    aux_plan = loads(open(aux_plan_path, encoding="utf-8").read()) \
        if os.path.exists(aux_plan_path) else None

    has_aux = has_aux_flag(aux_plan) if aux_plan is not None else \
        (bool(results_row and results_row.get("has_aux") == "1"))

    base_cs = base_constructions(base_plan) if base_plan is not None else []
    aux_cs = aux_constructions(aux_plan) if aux_plan is not None else []

    # ── 1. base без aux/dashed ──
    for i, c in enumerate(base_cs):
        cid = c.get("id", f"#{i}")
        if c.get("style") == "aux":
            codes.append("BASE_LEAK_AUX_STYLE")
        if c.get("dashed") is True:
            codes.append("BASE_LEAK_DASHED")

    # ── 2. aux purpose + evidence.quote ──
    for i, c in enumerate(aux_cs):
        if not (c.get("purpose") or "").strip():
            codes.append("AUX_MISSING_PURPOSE")
        ev = c.get("solution_evidence")
        if not isinstance(ev, dict) or not (ev.get("quote") or "").strip():
            codes.append("AUX_MISSING_QUOTE")

    # ── 3. ID-ссылки разрешимы (base + aux последовательно) ──
    avail = set()
    for c in base_cs:
        cid = c.get("id")
        if cid:
            avail.add(cid)
    for c in base_cs:
        cid = c.get("id", "?")
        for r in _refs(c):
            if r and r not in avail and r != cid:
                codes.append("UNRESOLVED_REF")
    # aux
    for c in aux_cs:
        cid = c.get("id")
        foot = c.get("foot_id")
        for r in _refs(c):
            if r and r not in avail and r != cid:
                codes.append("UNRESOLVED_REF")
        if cid:
            avail.add(cid)
        if foot:
            avail.add(foot)

    # ── 4. point-creating операции имеют foot_id ──
    for c in aux_cs:
        ctype = c.get("type") or ""
        if ctype in _POINT_CREATING_TYPES and not c.get("foot_id"):
            codes.append("MISSING_FOOT_ID")

    # ── 5/6/7/8/11: SVG-парсинг ──
    base_svg_root = _parse_svg(base_svg_path) if os.path.exists(base_svg_path) else None
    aux_svg_root = _parse_svg(aux_svg_path) if os.path.exists(aux_svg_path) else None

    # 9 / 10
    if has_aux:
        if aux_svg_root is None or not os.path.getsize(aux_svg_path):
            codes.append("AUX_SVG_MISSING")
    else:
        if os.path.exists(aux_svg_path) and os.path.getsize(aux_svg_path):
            codes.append("AUX_SVG_UNEXPECTED")

    # 5. точки плана имеют label в SVG
    labels = set(_svg_labels(base_svg_root)) | set(_svg_labels(aux_svg_root))
    for name, disp in plan_point_labels(base_plan).items():
        if disp and disp not in labels:
            codes.append("POINT_LABEL_MISSING")

    # 6. подписи внутри canvas — парсим x/y text-элементов и viewBox
    def _check_bounds(root):
        if root is None:
            return
        vb = root.get("viewBox") or ""
        w = h = 0
        m = re.match(r"0 0 (\d+(?:\.\d+)?) (\d+(?:\.\d+)?)", vb)
        if m:
            w = float(m.group(1))
            h = float(m.group(2))
        if not w:
            w = float(root.get("width") or 0)
            h = float(root.get("height") or 0)
        if not w:
            return
        for t in root.iter():
            if t.tag.split('}')[-1] == 'text':
                try:
                    x = float(t.get("x") or 0)
                    y = float(t.get("y") or 0)
                except ValueError:
                    continue
                if x < 0 or y < 0 or x > w or y > h:
                    codes.append("LABEL_OUT_OF_BOUNDS")
                    break
    _check_bounds(base_svg_root)
    _check_bounds(aux_svg_root)

    # 7. stroke-цвета только из dark_geometry
    allowed = allowed_colors()
    for root in (base_svg_root, aux_svg_root):
        if root is None:
            continue
        for el in root.iter():
            for attr in ("stroke", "fill"):
                val = el.get(attr)
                if not val:
                    continue
                hexes = re.findall(r"#[0-9a-fA-F]{3,8}\b", val)
                for hx in hexes:
                    if hx.upper() not in allowed:
                        codes.append("COLOR_NOT_IN_THEME")

    # 8. visual_role только из enum (проверяем в планах)
    for c in base_cs + aux_cs:
        vr = c.get("visual_role")
        if vr is not None and vr not in _VALID_VISUAL_ROLES:
            codes.append("INVALID_VISUAL_ROLE")

    # 11. число точек в SVG == числу точек плана (видимых)
    expected_points = len(visible_points(base_plan))
    if has_aux and aux_plan is not None:
        merged = merge_base_aux_plan(base_plan, aux_plan)
        expected_points = len(visible_points(merged))
    if base_svg_root is not None:
        svg_points = _svg_circles(base_svg_root)
        if has_aux and aux_svg_root is not None:
            svg_points = max(svg_points, _svg_circles(aux_svg_root))
        if expected_points > 0 and svg_points != expected_points:
            codes.append("POINT_COUNT_MISMATCH")

    # 12. точки statement в base plan
    stmt_names = _statement_point_names(rec.get("statement") or "")
    declared = set()
    for c in base_cs:
        cid = c.get("id")
        if cid:
            declared.add(cid)
        for r in _refs(c):
            if r:
                declared.add(r)
    # только «стандартные» имена точек (одна заглавная латинская буква)
    missing = {n for n in stmt_names if n not in declared}
    if missing:
        codes.append("STATEMENT_POINT_MISSING")

    # 13. AUX_EXPECTED_BUT_MISSING
    if style == "constructive" and not has_aux:
        codes.append("AUX_EXPECTED_BUT_MISSING")

    # 14. AUX_UNEXPECTED
    if style in ("coordinate", "complex", "trig") and has_aux and len(aux_cs) >= 2:
        codes.append("AUX_UNEXPECTED")

    return codes, {
        "style": style,
        "has_aux": has_aux,
        "aux_ops": len(aux_cs),
        "base_ops": len(base_cs),
        "expected_points": expected_points,
    }


def _safe(uid):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(uid))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join("output", "ch19"))
    ap.add_argument("--input", default=os.path.join("output", "ch19", "pilot_100.jsonl"))
    args = ap.parse_args()

    results = {}
    results_path = os.path.join(args.out, "results.csv")
    if os.path.exists(results_path):
        with open(results_path, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                results[r["task_uid"]] = r

    problems = Counter()
    examples = defaultdict(list)
    detail = []

    with open(args.input, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            uid = str(rec.get("task_uid"))
            row = results.get(uid)
            if row is None or row.get("status") != "done":
                continue
            codes, meta = qa_task(rec, args.out, row)
            for c in codes:
                problems[c] += 1
                if len(examples[c]) < 5:
                    examples[c].append(uid)
            detail.append((uid, meta["style"], meta["has_aux"],
                           meta["aux_ops"], meta["base_ops"], codes))

    lines = []
    lines.append("# CH19 QA report (детерминированный, без LLM/vision)\n")
    lines.append("")
    lines.append("| код проблемы | количество | до 5 примеров task_uid |")
    lines.append("|---|---|---|")
    if not problems:
        lines.append("| (нет проблем) | 0 | — |")
    for code, cnt in problems.most_common():
        ex = ", ".join(examples[code])
        lines.append(f"| {code} | {cnt} | {ex} |")

    lines.append("")
    lines.append("## Сводка по задачам (done)\n")
    lines.append("| task_uid | style | has_aux | aux_ops | base_ops | codes |")
    lines.append("|---|---|---|---|---|---|")
    for uid, style, ha, aops, bops, codes in detail:
        lines.append(f"| {uid} | {style} | {ha} | {aops} | {bops} | {', '.join(codes) or 'OK'} |")

    with open(os.path.join(args.out, "qa_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"QA: {len(detail)} done-задач, {len(problems)} кодов проблем")
    for code, cnt in problems.most_common():
        print(f"  {code}: {cnt}")


if __name__ == "__main__":
    main()
