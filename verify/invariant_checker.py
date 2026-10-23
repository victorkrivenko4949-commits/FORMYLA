# -*- coding: utf-8 -*-
"""Геометрический верификатор инвариантов ФОРМУЛА.

Принцип: каждое равенство/параллельность/прямой угол, заявленное в плане
(данное или продиктованное solver'ом), проверяется по вычисленной геометрии
ctx. Если заявлено «MD=BC», а длины не равны — это баг, ловится автоматически,
без глаз.

Запуск:
  python verify/run_corpus.py
"""
import math, re
from services.aux_compiler import compile_solver_aux
from services.base_normalizer import normalize_base_plan
from geometric_engine import engine as E

EPS = 1e-6


def _pairs_from_segments(seg):
    """Разложить segments=[P1,P2,...] или [[P1,P2],...] или pairs=[[P1,P2],...]
    в список пар. Поддерживает оба поля (segments и pairs)."""
    if not seg:
        return []
    pairs = []
    if isinstance(seg[0], (list, tuple)):
        for p in seg:
            if isinstance(p, (list, tuple)) and len(p) >= 2:
                pairs.append((p[0], p[1]))
    else:
        for i in range(0, len(seg) - 1, 2):
            pairs.append((seg[i], seg[i + 1]))
    return [(a, b) for (a, b) in pairs if isinstance(a, str) and isinstance(b, str)]


def _equal_mark_pairs(c):
    """Достать пары равных отрезков из equal_segments_mark.
    Поддерживает поля segments=[A,B,C,D,...] и pairs=[[A,B],[C,D]]."""
    seg = c.get("segments")
    if seg is None:
        seg = c.get("pairs")
    return _pairs_from_segments(seg)


def _seg_length(ctx, p, q):
    """Длина отрезка между точками P, Q (по найденному сегменту или напрямую)."""
    for sid, sdata in ctx.segments.items():
        sp = [x for x in (ctx.meta.get(sid, {}).get("parents") or [])
              if isinstance(x, str)]
        if len(sp) >= 2 and set(sp[:2]) == {p, q}:
            return math.hypot(sdata[1][0] - sdata[0][0],
                              sdata[1][1] - sdata[0][1])
    if p in ctx.points and q in ctx.points:
        a, b = ctx.points[p], ctx.points[q]
        return math.hypot(b[0] - a[0], b[1] - a[1])
    return None


def _parse_svg_marks(svg):
    """Извлечь из SVG позиции подписей и насечек (regex, устойчиво к ns)."""
    labels = []
    for m in re.finditer(r'<text\b[^>]*>([^<]*)</text>', svg):
        txt = m.group(1).strip()
        if not txt:
            continue
        tag = m.group(0)
        xm = re.search(r'\bx="([\d.-]+)"', tag)
        ym = re.search(r'\by="([\d.-]+)"', tag)
        sm = re.search(r'font-size="([\d.-]+)"', tag)
        if xm and ym:
            fs = float(sm.group(1)) if sm else 12.0
            labels.append((txt, float(xm.group(1)),
                           float(ym.group(1)), fs))
    ticks = []
    for m in re.finditer(r'<line\b[^>]*class="equal-tick"[^>]*/>', svg):
        tag = m.group(0)
        x1 = float(re.search(r'x1="([\d.-]+)"', tag).group(1))
        x2 = float(re.search(r'x2="([\d.-]+)"', tag).group(1))
        y1 = float(re.search(r'y1="([\d.-]+)"', tag).group(1))
        y2 = float(re.search(r'y2="([\d.-]+)"', tag).group(1))
        ticks.append(((x1 + x2) / 2.0, (y1 + y2) / 2.0))
    # E21: дуги/маркеры углов — <path> с A-командой (дуга) или маленькие дуги
    # равенства углов. Собираем опорные точки путей, чтобы потом проверить,
    # не проходит ли дуга сквозь bbox подписи.
    arc_pts = []
    for m in re.finditer(r'<path\b[^>]*\bd="([^"]+)"', svg):
        d = m.group(1)
        nums = [float(v) for v in re.findall(r'-?[\d.]+', d)]
        # берём первые ~6 координат (M ... A ...): start + end дуги.
        if len(nums) >= 4:
            arc_pts.append((nums[0], nums[1]))
            arc_pts.append((nums[-2], nums[-1]))
    return labels, ticks, arc_pts


def check_invariants(base_plan, solver_result, canvas=(620, 500)):
    """Прогнать base+solver через компилятор+движок и проверить инварианты.

    Возвращает dict: errors[], warnings[], checks[], stats{}.
    """
    rep = {"errors": [], "warnings": [], "checks": []}
    base = normalize_base_plan(base_plan)
    aux, issues = compile_solver_aux(solver_result, base)
    merged = list(base.get("constructions", [])) + list(aux.get("constructions", []))

    ctx = E.BuildContext()
    exec_fails = []
    for c in merged:
        try:
            E.execute_construction(ctx, c)
        except Exception as e:
            msg = str(e)
            if "уже существует" not in msg:
                exec_fails.append(f"{c.get('type','?')}({c.get('id','?')}): {msg}")
    # E21: явно объявленные в плане инцидентности (поле incidences) —
    # GeometricEngine.build регистрирует их в ctx.incidences, но верификатор
    # прогоняет конструкции поштучно, поэтому регистрируем сами.
    for src in (base, aux):
        for inc in (src.get("incidences") or []):
            if isinstance(inc, dict) and inc.get("point"):
                ctx.incidences.append(dict(inc))
    if exec_fails:
        rep["errors"].append(f"EXEC_FAILS: {len(exec_fails)}")
        for ef in exec_fails:
            rep["errors"].append("  " + ef)

    # ── Структурные инварианты ──
    for name, pt in ctx.points.items():
        if not (math.isfinite(pt[0]) and math.isfinite(pt[1])):
            rep["errors"].append(f"NaN_POINT {name}: {pt}")
    for sid, sdata in ctx.segments.items():
        sm = ctx.meta.get(sid, {})
        if sm.get("hidden", False):
            continue
        (x1, y1), (x2, y2) = sdata[0], sdata[1]
        if not (math.isfinite(x1) and math.isfinite(x2)
                and math.isfinite(y1) and math.isfinite(y2)):
            rep["errors"].append(f"NaN_SEGMENT {sid}")
            continue
        if math.hypot(x2 - x1, y2 - y1) < EPS:
            rep["warnings"].append(f"DEGENERATE_SEGMENT {sid}")

    # ── Дубликаты-точки: разные ID в одной координате (с обеими подписями) ──
    # Типичный баг: solver создаёт точку O=line_intersection(AD,BE), не зная,
    # что base уже имеет incenter I в той же точке → две подписи у одного места.
    labeled_pts = []  # (id, x, y)
    pts = list(ctx.points.items())
    for i in range(len(pts)):
        na, pa = pts[i]
        for j in range(i + 1, len(pts)):
            nb, pb = pts[j]
            d = math.hypot(pa[0] - pb[0], pa[1] - pb[1])
            if d < 3.0:
                rep["warnings"].append(
                    f"DUPLICATE_POINT {na}≈{nb}: совпадают (Δ={d:.2f})")

    # E20: применить дедуп совпадающих точек к ctx ДО рендера, чтобы на
    # чертеже не было сдвоенных подписей (дубликаты помечаются hidden).
    # Детекция выше уже зарегистрировала их как warning — это корневой фикс.
    n_dedup = E.dedup_coincident_points(ctx)
    if n_dedup:
        rep["warnings"].append(
            f"DEDUP: скрыто {n_dedup} дубликатов-точек при рендере")

    # ── Заявленные равенства / параллельности / углы ──
    for c in merged:
        t = c.get("type")
        if t == "equal_segments_mark":
            pairs = _equal_mark_pairs(c)
            lengths = [L for L in (_seg_length(ctx, p, q) for (p, q) in pairs)
                       if L is not None]
            if len(lengths) >= 2:
                mx, mn = max(lengths), min(lengths)
                tol = max(0.6, mx * 0.02)  # 2% или 0.6px
                if mx - mn > tol:
                    rep["errors"].append(
                        f"INEQUAL_SEGMENTS {c.get('id')}: "
                        f"Δ={mx-mn:.2f} lengths={[round(x,1) for x in lengths]} "
                        f"pairs={pairs}")
                else:
                    rep["checks"].append(
                        f"equal_segments {c.get('id')}: OK "
                        f"({len(lengths)} пар, Δ={mx-mn:.2f})")
        elif t == "parallel_mark":
            # пары могут быть в segments=[[P,Q],[R,S]] или в p1/p2,p3/p4
            segs = c.get("segments", [])
            if not segs and c.get("p1") and c.get("p2") and c.get("p3") and c.get("p4"):
                segs = [[c["p1"], c["p2"]], [c["p3"], c["p4"]]]
            dirs = []
            for ref in segs:
                if isinstance(ref, (list, tuple)) and len(ref) >= 2:
                    p, q = ref[0], ref[1]
                    if p in ctx.points and q in ctx.points:
                        dx = ctx.points[q][0] - ctx.points[p][0]
                        dy = ctx.points[q][1] - ctx.points[p][1]
                        n = math.hypot(dx, dy)
                        if n > EPS:
                            dirs.append((dx / n, dy / n))
            if len(dirs) >= 2:
                bad = False
                for i in range(1, len(dirs)):
                    cross = dirs[0][0] * dirs[i][1] - dirs[0][1] * dirs[i][0]
                    if abs(cross) > 0.05:
                        bad = True
                if bad:
                    rep["errors"].append(f"NOT_PARALLEL {c.get('id')}")
                else:
                    rep["checks"].append(f"parallel_mark {c.get('id')}: OK")
        elif t == "midpoint":
            m, p1, p2 = c.get("id"), c.get("p1"), c.get("p2")
            if m in ctx.points and p1 in ctx.points and p2 in ctx.points:
                d1 = math.hypot(ctx.points[m][0] - ctx.points[p1][0],
                                ctx.points[m][1] - ctx.points[p1][1])
                d2 = math.hypot(ctx.points[m][0] - ctx.points[p2][0],
                                ctx.points[m][1] - ctx.points[p2][1])
                tol = max(0.6, 0.02 * max(d1, d2))
                if abs(d1 - d2) > tol:
                    rep["errors"].append(
                        f"BAD_MIDPOINT {m}: не середина {p1}-{p2}: "
                        f"d1={d1:.1f} d2={d2:.1f}")
                else:
                    rep["checks"].append(f"midpoint {m}: OK")
        elif t == "midpoint_mark":
            p1, p2, p3, p4 = (c.get("p1"), c.get("p2"),
                              c.get("p3"), c.get("p4"))
            # p2 — середина p1-p4 (если p2==p3)
            if p1 in ctx.points and p2 in ctx.points and p4 in ctx.points:
                d1 = math.hypot(ctx.points[p2][0] - ctx.points[p1][0],
                                ctx.points[p2][1] - ctx.points[p1][1])
                d2 = math.hypot(ctx.points[p2][0] - ctx.points[p4][0],
                                ctx.points[p2][1] - ctx.points[p4][1])
                tol = max(0.6, 0.02 * max(d1, d2))
                if abs(d1 - d2) > tol:
                    rep["errors"].append(
                        f"BAD_MIDPOINT_MARK {p2}: не середина {p1}-{p4}: "
                        f"d1={d1:.1f} d2={d2:.1f}")
                else:
                    rep["checks"].append(f"midpoint_mark {p2}: OK")
        elif t == "equal_angles_mark":
            # E21: равенство углов. angles=[[P1,V1,P2],[P3,V2,P4],...] —
            # каждый тройка задаёт угол при средней точке (вершине).
            angles = c.get("angles") or []
            vals = []
            ok_all = True
            for trip in angles:
                if not (isinstance(trip, (list, tuple)) and len(trip) >= 3):
                    continue
                p1, v, p2 = trip[0], trip[1], trip[2]
                if not (p1 in ctx.points and v in ctx.points and p2 in ctx.points):
                    ok_all = False
                    break
                pv, pp1, pp2 = ctx.points[v], ctx.points[p1], ctx.points[p2]
                a1 = (pp1[0] - pv[0], pp1[1] - pv[1])
                a2 = (pp2[0] - pv[0], pp2[1] - pv[1])
                n1, n2 = math.hypot(*a1), math.hypot(*a2)
                if n1 > EPS and n2 > EPS:
                    cosang = (a1[0] * a2[0] + a1[1] * a2[1]) / (n1 * n2)
                    cosang = max(-1.0, min(1.0, cosang))
                    vals.append(math.degrees(math.acos(cosang)))
                else:
                    ok_all = False
                    break
            if ok_all and len(vals) >= 2:
                mx, mn = max(vals), min(vals)
                if mx - mn > 2.5:
                    rep["errors"].append(
                        f"INEQUAL_ANGLES {c.get('id')}: "
                        f"Δ={mx-mn:.2f}° angles="
                        f"{[round(x, 1) for x in vals]}")
                else:
                    rep["checks"].append(
                        f"equal_angles {c.get('id')}: OK "
                        f"({len(vals)} углов, Δ={mx-mn:.2f}°)")
        elif t == "right_angle_mark":
            v, r1, r2 = c.get("vertex"), c.get("ray1"), c.get("ray2")
            if v in ctx.points and r1 in ctx.points and r2 in ctx.points:
                pv, p1, p2 = ctx.points[v], ctx.points[r1], ctx.points[r2]
                a1 = (p1[0] - pv[0], p1[1] - pv[1])
                a2 = (p2[0] - pv[0], p2[1] - pv[1])
                n1, n2 = math.hypot(*a1), math.hypot(*a2)
                if n1 > EPS and n2 > EPS:
                    cosang = (a1[0] * a2[0] + a1[1] * a2[1]) / (n1 * n2)
                    cosang = max(-1.0, min(1.0, cosang))
                    ang = math.degrees(math.acos(cosang))
                    if abs(ang - 90) > 2.5:
                        rep["errors"].append(
                            f"NOT_RIGHT_ANGLE {c.get('id')}: {ang:.1f}°")
                    else:
                        rep["checks"].append(
                            f"right_angle {c.get('id')}: OK ({ang:.1f}°)")
        elif t in ("circumcircle", "circle_center_radius", "incircle"):
            # E21: инцидентность — точки, объявленные на окружности, обязаны
            # лежать на ней (расстояние до центра = радиусу ±1.5px).
            cid = c.get("id")
            if cid in ctx.circles:
                center, radius = ctx.circles[cid]
                # какие точки должны лежать на этой окружности:
                on_pts = []
                if t == "circumcircle":
                    on_pts = [p for p in (c.get("p1"), c.get("p2"), c.get("p3"))
                              if p in ctx.points]
                elif t == "circle_center_radius":
                    # точка, задающая радиус (radius_point/through):
                    rp = (c.get("radius_point")
                          or c.get("through") or c.get("radius_from"))
                    if rp and rp in ctx.points:
                        on_pts = [rp]
                bad = []
                for pn in on_pts:
                    px, py = ctx.points[pn]
                    d = math.hypot(px - center[0], py - center[1])
                    if abs(d - radius) > max(1.5, 0.02 * radius):
                        bad.append(f"{pn}: d={d:.1f}≠R={radius:.1f}")
                if bad:
                    rep["errors"].append(
                        f"POINT_NOT_ON_CIRCLE {cid}: " + ", ".join(bad))
                elif on_pts:
                    rep["checks"].append(
                        f"circle_incidence {cid}: OK "
                        f"({len(on_pts)} точек на R={radius:.1f})")

    # E21: проверка декларированных инцидентностей из плана/aux.
    # Каждая запись {point, on, object} — точка обязана лежать на объекте.
    for inc in ctx.incidences:
        pid = inc.get("point")
        kind = inc.get("on")
        obj = inc.get("object")
        if pid not in ctx.points:
            continue
        px, py = ctx.points[pid]
        if kind == "circle" and obj in ctx.circles:
            center, radius = ctx.circles[obj]
            d = math.hypot(px - center[0], py - center[1])
            if abs(d - radius) > max(1.5, 0.02 * radius):
                rep["errors"].append(
                    f"POINT_NOT_ON_CIRCLE {pid}: "
                    f"d={d:.1f}≠R={radius:.1f} (circle {obj})")
            else:
                rep["checks"].append(
                    f"point_on_circle {pid}: OK (d={d:.1f}, R={radius:.1f})")
        elif kind == "segment" and isinstance(obj, (list, tuple)) and len(obj) >= 2:
            p1, p2 = obj[0], obj[1]
            if p1 in ctx.points and p2 in ctx.points:
                a = ctx.points[p1]
                b = ctx.points[p2]
                ab = math.hypot(b[0] - a[0], b[1] - a[1])
                if ab > EPS:
                    t = ((px - a[0]) * (b[0] - a[0]) +
                         (py - a[1]) * (b[1] - a[1])) / (ab * ab)
                    t = max(0.0, min(1.0, t))
                    cx, cy = a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])
                    dist = math.hypot(px - cx, py - cy)
                    if dist > 2.0:
                        rep["errors"].append(
                            f"POINT_NOT_ON_SEGMENT {pid}: "
                            f"d={dist:.1f} (segment {p1}-{p2})")
                    else:
                        rep["checks"].append(
                            f"point_on_segment {pid}: OK (d={dist:.1f})")

    # ── Рендер + коллизии подписей/насечек ──
    _s = E.EngineSettings()
    _s.auto_fit = True
    try:
        svg = E.render_svg(ctx, canvas[0], canvas[1], _s)
        rep["checks"].append("render: OK")
    except Exception as e:
        rep["errors"].append(f"RENDER_CRASH: {e}")
        svg = ""

    labels, ticks, arc_pts = _parse_svg_marks(svg)

    # Коллизии подпись-подпись (bbox перекрытие)
    for i in range(len(labels)):
        for j in range(i + 1, len(labels)):
            t1, x1, y1, f1 = labels[i]
            t2, x2, y2, f2 = labels[j]
            w1, h1 = f1 * len(t1) * 0.55, f1 * 0.6
            w2, h2 = f2 * len(t2) * 0.55, f2 * 0.6
            if abs(x1 - x2) < (w1 + w2) * 0.6 and abs(y1 - y2) < (h1 + h2) * 0.7:
                rep["warnings"].append(
                    f"LABEL_OVERLAP '{t1}'@({x1:.0f},{y1:.0f}) & "
                    f"'{t2}'@({x2:.0f},{y2:.0f})")

    # E21: дуга/маркер проходит сквозь bbox подписи точки (косметика).
    # Опорные точки дуг — это концы дуг равенства углов/отрезков; если такая
    # точка лежит внутри bbox подписи — маркер налезает на букву.
    for (ax, ay) in arc_pts:
        for (txt, lx, ly, fs) in labels:
            if abs(ax - lx) < fs * 0.6 and abs(ay - ly) < fs * 0.6:
                rep["warnings"].append(
                    f"ARC_ON_LABEL '{txt}'@({lx:.0f},{ly:.0f}) "
                    f"(дуга @({ax:.0f},{ay:.0f}))")
                break

    # Насечки на подписях точек
    for (tx, ty) in ticks:
        for (txt, lx, ly, fs) in labels:
            if abs(tx - lx) < fs * 0.6 and abs(ty - ly) < fs * 0.6:
                rep["warnings"].append(
                    f"TICK_ON_LABEL '{txt}'@({lx:.0f},{ly:.0f})")
                break

    rep["stats"] = {
        "points": len(ctx.points), "segments": len(ctx.segments),
        "labels": len(labels), "ticks": len(ticks),
        "compile_issues": len(issues),
    }
    return rep
