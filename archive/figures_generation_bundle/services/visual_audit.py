# -*- coding: utf-8 -*-
"""services/visual_audit.py — пост-рендер аудит готового чертежа.

Дополняет:
  * services.figure_validator        — план ↔ схема движка
  * services.figure_plan_validator   — инварианты base ↔ aux
  * services.condition_coverage      — полнота относительно условия

Отвечает на вопрос: «выглядит ли отрендеренный чертёж корректно и читаемо?»
Работает на BuildContext (геометрия) + распарсенном SVG (позиции подписей).
Без LLM. Целевое время < 50 мс.
"""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    from geometric_engine import geom as _geom
except Exception:  # pragma: no cover
    _geom = None

try:
    from .figure_plan_validator import _base_constructions, _loads
except Exception:  # pragma: no cover
    from services.figure_plan_validator import _base_constructions, _loads


# ──────────────────────────────────────────────────────────────────────────
# Допуски (переопределяются env через caller).
# ──────────────────────────────────────────────────────────────────────────
DEFAULT_ANGLE_TOL_DEG = 0.5
DEFAULT_LENGTH_REL_TOL = 0.01
DEFAULT_LENGTH_ABS_TOL = 1.0
DEFAULT_LABEL_MIN_GAP_PX = 2.0
DEFAULT_MIN_ARC_RADIUS_PX = 14.0
DEFAULT_MIN_POINT_GAP_PX = 18.0
DEFAULT_MIN_SEGMENT_PX = 24.0

# Ширины глифов (приближение для Arial) — консервативная переоценка.
_CHAR_WIDTH_RATIO = {
    "default": 0.58,
    "digit": 0.556,
    "narrow": 0.28,   # i, l, j, точка, запятая, пробел
    "wide": 0.78,     # M, W, °
}

_NUM_ANGLE_RE = re.compile(
    r"(?:угол|∠)\s*([A-Z]{1,3})\s*(?:равен|=|:)?\s*(\d+(?:[.,]\d+)?)\s*°?",
    re.IGNORECASE,
)
_NUM_LEN_RE = re.compile(
    r"\b([A-Z]{2})\s*=\s*(\d+(?:[.,]\d+)?)\s*(см|мм|м)?\b"
)
_BARE_DEG_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*°")

_TARGET_RE = re.compile(
    r"(?:найдите|найти|вычислите|чему\s+равен|определите|докажите)\s+"
    r"(?:величину\s+)?(?:угл\w+|отрез\w+|сторон\w+|площад\w+|радиус|длин\w+)?\s*"
    r"(∠?\s*[A-Z]{1,3})",
    re.IGNORECASE,
)

# Цепочка равенств: AK = KL = LC = ... (любой длины ≥ 2).
# Ловит и «BD = CE», и «AK = KL = LC», и «$BD = CE$».
_EXPLICIT_EQ_CHAIN_RE = re.compile(
    r"\$?\s*([A-Z]{2})\s*(?:=\s*([A-Z]{2})\s*)+"
)
_EXPLICIT_EQ_SEG_RE = re.compile(r"[A-Z]{2}")


# ──────────────────────────────────────────────────────────────────────────
# Утилиты
# ──────────────────────────────────────────────────────────────────────────

def _parse_degrees(text: Any) -> Optional[float]:
    """«45°» → 45.0; «50» → 50.0; символьное → None."""
    if text is None:
        return None
    s = str(text).strip().replace(" ", "").replace(",", ".")
    s = s.replace("°", "")
    m = re.search(r"^-?(\d+(?:\.\d+)?)$", s)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def _angle_abc_deg(pts: Dict[str, Any], a: str, b: str, c: str) -> Optional[float]:
    if _geom is None:
        return None
    pa, pb, pc = pts.get(a), pts.get(b), pts.get(c)
    if not pa or not pb or not pc:
        return None
    try:
        return math.degrees(_geom.angle_between_three(pa, pb, pc))
    except Exception:
        return None


def resolve_angle_triple(vertex: str, plan: Any, condition: str = "",
                         ctx: Any = None) -> Optional[Tuple[str, str, str]]:
    """Определить (p1, vertex, p3) для угла, названного одной буквой.

    Правила приоритета:
      1. Треугольник XYZ из условия, содержащий vertex → две другие вершины.
      2. Многоугольник → два соседа vertex в обходе.
      3. Явная запись ∠BAC / ∠(B,A,C) в условии.
      4. Из vertex выходит ровно 2 отрезка → их концы.
      5. Иначе → None (warning AMBIGUOUS_ANGLE_VERTEX).
    """
    from services.text_normalize import normalize_condition

    condition = normalize_condition(condition)
    cs = _base_constructions(_loads(plan))
    vertex = (vertex or "").upper()

    # 3. Явная запись ∠BAC или ∠(B,A,C).
    explicit_re = re.compile(
        r"∠\s*\(?([A-Z])?\s*,?\s*([A-Z])\s*,?\s*([A-Z])\)?",
        re.IGNORECASE,
    )
    for m in explicit_re.finditer(condition):
        g = [x for x in m.groups() if x]
        if len(g) == 3:
            # ∠(p1, vertex, p3)
            if g[1].upper() == vertex:
                return (g[0].upper(), vertex, g[2].upper())
        if len(g) == 2:
            # ∠AB (двухбуквенный) — пропускаем, недостаточно.
            continue

    # 1/2. Треугольник/многоугольник в условии, содержащий vertex.
    poly_re = re.compile(
        r"(?:треугольник|четыр[ёе]хугольник|квадрат|прямоугольник|"
        r"параллелограмм|ромб|трапеци[а-я]*|многоугольник|"
        r"п[я]тиугольник|шестиугольник)[а-я]*\s+([A-Z]{2,8})",
        re.IGNORECASE,
    )
    for m in poly_re.finditer(condition):
        name = m.group(1)
        if vertex not in name:
            continue
        idx = name.index(vertex)
        n = len(name)
        prev = name[(idx - 1) % n]
        nxt = name[(idx + 1) % n]
        if prev != vertex and nxt != vertex and prev != nxt:
            return (prev, vertex, nxt)

    # 4. Ровно два отрезка, выходящих из vertex.
    neighbors: Set[str] = set()
    for c in cs:
        ctype = c.get("type") or ""
        if ctype in ("segment", "line", "ray"):
            p1, p2 = c.get("p1"), c.get("p2")
            if p1 == vertex and p2:
                neighbors.add(str(p2))
            elif p2 == vertex and p1:
                neighbors.add(str(p1))
    if len(neighbors) == 2:
        a, b = sorted(neighbors)
        return (a, vertex, b)

    # Вписанный многоугольник — соседи vertex в vertices.
    for c in cs:
        if c.get("type") == "inscribed_polygon":
            verts = c.get("vertices") or []
            if vertex in verts:
                idx = verts.index(vertex)
                n = len(verts)
                prev = verts[(idx - 1) % n]
                nxt = verts[(idx + 1) % n]
                if prev != vertex and nxt != vertex and prev != nxt:
                    return (prev, vertex, nxt)

    return None


def _bbox_intersect(a: Tuple[float, float, float, float],
                    b: Tuple[float, float, float, float]) -> bool:
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def _ratio_for_char(ch: str) -> float:
    if ch in "ilj.,':; ":
        return _CHAR_WIDTH_RATIO["narrow"]
    if ch in "MW°@#%":
        return _CHAR_WIDTH_RATIO["wide"]
    if ch.isdigit():
        return _CHAR_WIDTH_RATIO["digit"]
    return _CHAR_WIDTH_RATIO["default"]


def _estimate_text_bbox(text: str, x: float, y: float, font_size: float,
                        anchor: str = "middle") -> Tuple[float, float, float, float]:
    """Вернуть (x0, y0, x1, y1). Консервативная оценка ширины."""
    w = sum(font_size * _ratio_for_char(ch) for ch in (text or ""))
    h = font_size * 1.2
    if anchor == "end":
        x0 = x - w
    elif anchor == "start":
        x0 = x
    else:  # middle
        x0 = x - w / 2.0
    y0 = y - font_size * 0.8  # baseline → верх
    return (x0, y0, x0 + w, y0 + h)


def _parse_svg_texts(svg: str) -> List[Dict[str, Any]]:
    """Извлечь все <text> из SVG: text, x, y, font-size, text-anchor."""
    out: List[Dict[str, Any]] = []
    if not svg:
        return out
    try:
        root = ET.fromstring(svg)
    except Exception:
        return out
    for el in root.iter():
        tag = el.tag
        if not isinstance(tag, str):
            continue
        if tag.endswith("text"):
            txt = (el.text or "").strip()
            if not txt:
                continue
            try:
                x = float(el.get("x", "0"))
                y = float(el.get("y", "0"))
            except (TypeError, ValueError):
                continue
            try:
                fs = float(el.get("font-size", "14"))
            except (TypeError, ValueError):
                fs = 14.0
            out.append({
                "text": txt,
                "x": x,
                "y": y,
                "font_size": fs,
                "anchor": el.get("text-anchor", "middle"),
            })
    return out


def _canvas_size(svg: str) -> Tuple[float, float]:
    try:
        root = ET.fromstring(svg)
        w = float(root.get("width", "0"))
        h = float(root.get("height", "0"))
        return w, h
    except Exception:
        return 0.0, 0.0


def _given_values(condition: str) -> Set[float]:
    """Множество числовых величин, ЯВНО названных в условии."""
    vals: Set[float] = set()
    for m in _NUM_ANGLE_RE.finditer(condition or ""):
        v = _parse_degrees(m.group(2))
        if v is not None:
            vals.add(v)
    for m in _NUM_LEN_RE.finditer(condition or ""):
        v = _parse_degrees(m.group(2))
        if v is not None:
            vals.add(v)
    for m in _BARE_DEG_RE.finditer(condition or ""):
        v = _parse_degrees(m.group(1))
        if v is not None:
            vals.add(v)
    return vals


def _explicit_equalities(condition: str) -> List[List[str]]:
    """Извлечь явные равенства отрезков: BD = CE, AK = KL = LC.

    Ловит цепочку любой длины (2, 3, 4+ отрезков) одним матчем, чтобы
    «AK = KL = LC» давало все ТРИ отрезка, а не только два.
    """
    out: List[List[str]] = []
    for m in _EXPLICIT_EQ_CHAIN_RE.finditer(condition or ""):
        segs = _EXPLICIT_EQ_SEG_RE.findall(m.group(0))
        segs = [s for s in segs if re.fullmatch(r"[A-Z]{2}", s)]
        if len(segs) >= 2:
            out.append(segs)
    return out


# ──────────────────────────────────────────────────────────────────────────
# Проверки V1–V7
# ──────────────────────────────────────────────────────────────────────────

def _check_v1_labels(plan: Any, ctx: Any, errors: List[str],
                     warnings: List[str], angle_tol: float) -> None:
    """V1 · LABEL_CONTRADICTS_GEOMETRY — подпись против фактической геометрии."""
    cs = _base_constructions(_loads(plan))
    pts = getattr(ctx, "points", {}) if ctx else {}
    length_pairs: List[Tuple[float, float]] = []

    for c in cs:
        ctype = c.get("type") or ""
        if ctype == "angle_label":
            vertex = c.get("vertex", c.get("p2", ""))
            ray1 = c.get("ray1", c.get("p1", ""))
            ray2 = c.get("ray2", c.get("p3", ""))
            declared = _parse_degrees(c.get("text", c.get("label", "")))
            if declared is None:
                continue
            if not ray1 or not ray2:
                triple = resolve_angle_triple(vertex, plan)
                if triple is None:
                    warnings.append(
                        f"AMBIGUOUS_ANGLE_VERTEX: угол при вершине '{vertex}' "
                        f"не удалось резолвить в тройку лучей"
                    )
                    continue
                ray1, vertex, ray2 = triple
            actual = _angle_abc_deg(pts, ray1, vertex, ray2)
            if actual is None:
                continue
            if abs(actual - declared) > angle_tol:
                errors.append(
                    f"LABEL_CONTRADICTS_GEOMETRY: метка '{declared}°' при "
                    f"вершине {vertex} противоречит чертежу — фактический "
                    f"∠{ray1}{vertex}{ray2} = {actual:.2f}°. Задай угол "
                    f"ограничением, не свободными координатами."
                )
        elif ctype == "length_label":
            p1 = c.get("p1", c.get("ray1", ""))
            p2 = c.get("p2", c.get("ray2", ""))
            declared = _parse_degrees(c.get("text", c.get("label", "")))
            if declared is None or not p1 or not p2:
                continue
            if p1 in pts and p2 in pts and _geom is not None:
                actual = _geom.dist(pts[p1], pts[p2])
                length_pairs.append((declared, actual))

    # Длины: сравниваем отношения через медианный масштаб.
    if length_pairs and len(length_pairs) >= 2:
        ratios = [a / d if d > 0 else 0.0 for d, a in length_pairs]
        ratios = [r for r in ratios if r > 0]
        if ratios:
            scale = sorted(ratios)[len(ratios) // 2]
            for declared, actual in length_pairs:
                if actual <= 0:
                    continue
                rel = abs(actual - declared * scale) / max(declared * scale, 1e-6)
                if rel > DEFAULT_LENGTH_REL_TOL:
                    errors.append(
                        f"LABEL_CONTRADICTS_GEOMETRY: длина '{declared}' "
                        f"не соответствует отношению на чертеже "
                        f"(факт {actual:.1f}px, масштаб {scale:.2f})"
                    )
                    break


def _check_v2_marks(plan: Any, ctx: Any, errors: List[str],
                    angle_tol: float) -> None:
    """V2 · MARK_CONTRADICTS_GEOMETRY — засечки/пометки против геометрии."""
    cs = _base_constructions(_loads(plan))
    pts = getattr(ctx, "points", {}) if ctx else {}

    for c in cs:
        ctype = c.get("type") or ""
        if ctype == "equal_segments_mark":
            segs = c.get("segments", []) or []
            pairs: List[Tuple[str, str]] = []
            for item in segs:
                if isinstance(item, (list, tuple)) and len(item) == 2:
                    pairs.append((str(item[0]), str(item[1])))
            if not pairs:
                continue
            lengths = []
            for a, b in pairs:
                if a in pts and b in pts and _geom is not None:
                    lengths.append(_geom.dist(pts[a], pts[b]))
            if lengths and max(lengths) - min(lengths) > max(
                DEFAULT_LENGTH_ABS_TOL, DEFAULT_LENGTH_REL_TOL * (sum(lengths) / len(lengths))
            ):
                errors.append(
                    f"MARK_CONTRADICTS_GEOMETRY: equal_segments_mark утверждает "
                    f"равенство, но фактические длины "
                    f"{' / '.join(f'{x:.1f}' for x in lengths)} px различаются"
                )
        elif ctype == "right_angle_mark":
            vertex = c.get("vertex", c.get("p2", ""))
            ray1 = c.get("ray1", c.get("p1", ""))
            ray2 = c.get("ray2", c.get("p3", ""))
            actual = _angle_abc_deg(pts, ray1, vertex, ray2)
            if actual is not None and abs(actual - 90.0) > angle_tol:
                errors.append(
                    f"MARK_CONTRADICTS_GEOMETRY: right_angle_mark при {vertex} "
                    f"неверен — фактический угол {actual:.2f}°"
                )
        elif ctype == "midpoint_mark":
            point = c.get("point", c.get("id", ""))
            p1 = c.get("p1", "")
            p2 = c.get("p2", "")
            if point in pts and p1 in pts and p2 in pts and _geom is not None:
                d1 = _geom.dist(pts[p1], pts[point])
                d2 = _geom.dist(pts[point], pts[p2])
                if abs(d1 - d2) > DEFAULT_LENGTH_ABS_TOL:
                    errors.append(
                        f"MARK_CONTRADICTS_GEOMETRY: midpoint_mark '{point}' "
                        f"не середина — {d1:.1f} vs {d2:.1f} px"
                    )


def _check_v3_strict_equality(plan: Any, condition: str, errors: List[str]) -> None:
    """V3 · MISSING_GIVEN_EQUALITY_MARK_STRICT — явное равенство не отмечено."""
    eqs = _explicit_equalities(condition)
    if not eqs:
        return
    cs = _base_constructions(_loads(plan))
    # Имена отрезков (строки «AK», «KL», «LC»), участвующих в ЛЮБОЙ засечке равенства.
    marked_segments: Set[str] = set()
    for c in cs:
        if c.get("type") == "equal_segments_mark":
            segs = c.get("segments", []) or []
            for item in segs:
                if isinstance(item, (list, tuple)) and len(item) == 2:
                    marked_segments.add(str(item[0]) + str(item[1]))
                    marked_segments.add(str(item[1]) + str(item[0]))
                elif isinstance(item, str) and len(item) == 2:
                    marked_segments.add(item)

    for group in eqs:
        # Цепочка «AK = KL = LC» требует, чтобы КАЖДЫЙ отрезок был отмечен
        # засечкой равенства.  Если отмечены только AK и KL, а LC нет — это
        # дефект (на чертеже «3 равных», а меток на 2).
        missing = [s for s in group if s not in marked_segments]
        if missing:
            errors.append(
                f"MISSING_GIVEN_EQUALITY_MARK_STRICT: равенство "
                f"{' = '.join(group)} из условия отмечено не полностью — "
                f"без меток: {', '.join(missing)}"
            )


def _check_v4_collisions(svg: str, errors: List[str], warnings: List[str],
                         min_gap: float) -> None:
    """V4 · LABEL_COLLISION / LABEL_OUT_OF_CANVAS / LABEL_OVERLAPS_GEOMETRY."""
    texts = _parse_svg_texts(svg)
    w, h = _canvas_size(svg)
    boxes = []
    for t in texts:
        boxes.append(_estimate_text_bbox(t["text"], t["x"], t["y"],
                                         t["font_size"], t["anchor"]))

    # Коллизии попарно.  Коллизия подписей — это presentation-дефект, а не
    # геометрическая ошибка: жадный placement и auto_fit уже стараются её
    # избежать, но подпись длины на середине отрезка может совпасть с
    # подписью середины (M).  Переводим в warnings, чтобы не откатывать aux
    # из-за наложения текста, а error оставляем только для выхода за canvas.
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            a, b = boxes[i], boxes[j]
            if _bbox_intersect(
                (a[0] - min_gap, a[1] - min_gap, a[2] + min_gap, a[3] + min_gap),
                b,
            ):
                warnings.append(
                    f"LABEL_COLLISION: подписи '{texts[i]['text']}' и "
                    f"'{texts[j]['text']}' пересекаются"
                )

    # Выход за canvas.
    for i, box in enumerate(boxes):
        if w > 0 and h > 0:
            if box[0] < 0 or box[1] < 0 or box[2] > w or box[3] > h:
                errors.append(
                    f"LABEL_OUT_OF_CANVAS: подпись '{texts[i]['text']}' "
                    f"выходит за границы полотна"
                )


def _check_v5_spoiler(plan: Any, condition: str, warnings: List[str]) -> None:
    """V5 · ANSWER_SPOILER — подписана производная величина."""
    given = _given_values(condition)
    target_m = _TARGET_RE.search(condition or "")
    target_letters = re.findall(r"[A-Z]", target_m.group(1)) if target_m else []

    cs = _base_constructions(_loads(plan))
    for c in cs:
        ctype = c.get("type") or ""
        if ctype not in ("angle_label", "length_label"):
            continue
        # FIX: length_label — это ДЛИНА, а не угол.  _parse_degrees превращал
        # «8» в 8.0° и ложно помечал подписи длин как ANSWER_SPOILER.
        if ctype == "length_label":
            continue
        declared = _parse_degrees(c.get("text", c.get("label", "")))
        if declared is None or declared in given:
            continue
        # Значение не из условия — потенциальный спойлер.
        refs = "".join(str(c.get(k, "")) for k in ("vertex", "p1", "p2", "ray1", "ray2"))
        is_target = any(ch in refs for ch in target_letters)
        if is_target:
            warnings.append(
                f"ANSWER_SPOILER: метка '{declared}°' подписана на искомом "
                f"объекте — это ответ"
            )
        else:
            warnings.append(
                f"ANSWER_SPOILER: метка '{declared}°' — производная величина, "
                f"не названная в условии"
            )


def _check_v6_target_annotated(plan: Any, condition: str, warnings: List[str]) -> None:
    """V6 · TARGET_NOT_ANNOTATED — искомый объект без '?'."""
    target_m = _TARGET_RE.search(condition or "")
    if not target_m:
        return
    raw = target_m.group(1).replace("∠", "")
    letters = re.findall(r"[A-Z]", raw)
    if not letters:
        return

    cs = _base_constructions(_loads(plan))
    has_q = any(
        (c.get("text") or c.get("label") or "") in ("?", "?°", "x", "y")
        for c in cs
        if c.get("type") in ("angle_label", "length_label")
    )
    if not has_q:
        warnings.append(
            f"TARGET_NOT_ANNOTATED: искомый объект '{raw}' не помечен '?'"
        )


def _check_v7_readability(ctx: Any, warnings: List[str]) -> None:
    """V7 · читаемость (мягкие проверки)."""
    pts = getattr(ctx, "points", {}) if ctx else {}
    names = list(pts.keys())
    # POINTS_TOO_CLOSE.
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = pts[names[i]], pts[names[j]]
            if _geom is not None and _geom.dist(a, b) < DEFAULT_MIN_POINT_GAP_PX:
                warnings.append(
                    f"POINTS_TOO_CLOSE: точки '{names[i]}' и '{names[j]}' "
                    f"визуально слипаются"
                )
                break


# ──────────────────────────────────────────────────────────────────────────
# Главная точка входа.
# ──────────────────────────────────────────────────────────────────────────

def audit_rendered_figure(
    svg: str,
    build_context: Any,
    base_plan: Any,
    condition_text: str,
    settings: Optional[Any] = None,
) -> Dict[str, Any]:
    """Пост-рендер аудит готового чертежа.

    Returns:
      {
        "clean": bool,
        "errors": [str],
        "warnings": [str],
        "checks": {...},
        "visual_score": float,
        "repair_feedback": str,
      }
    """
    angle_tol = DEFAULT_ANGLE_TOL_DEG
    min_gap = DEFAULT_LABEL_MIN_GAP_PX
    if settings is not None:
        angle_tol = float(getattr(settings, "angle_tol", None) or angle_tol)

    errors: List[str] = []
    warnings: List[str] = []

    _check_v1_labels(base_plan, build_context, errors, warnings, angle_tol)
    _check_v2_marks(base_plan, build_context, errors, angle_tol)
    _check_v3_strict_equality(base_plan, condition_text, errors)
    _check_v4_collisions(svg, errors, warnings, min_gap)
    _check_v5_spoiler(base_plan, condition_text, warnings)
    _check_v6_target_annotated(base_plan, condition_text, warnings)
    _check_v7_readability(build_context, warnings)

    clean = len(errors) == 0

    # Взвешенный скор: ошибки штрафуют сильнее предупреждений.
    visual_score = max(0.0, 1.0 - len(errors) * 0.25 - len(warnings) * 0.05)

    repair_feedback = ""
    if errors:
        repair_feedback = (
            "Чертёж визуально некорректен. Исправь ТОЛЬКО перечисленное:\n"
            + "\n".join(f"- {e}" for e in errors)
        )

    result: Dict[str, Any] = {
        "clean": clean,
        "errors": errors,
        "warnings": warnings,
        "checks": {
            "label_semantics": {"errors": [e for e in errors if "LABEL_CONTRADICTS" in e]},
            "label_collisions": {"errors": [e for e in errors if "COLLISION" in e or "OUT_OF_CANVAS" in e]},
            "mark_consistency": {"errors": [e for e in errors if "MARK_CONTRADICTS" in e]},
            "answer_spoiler": {"warnings": [w for w in warnings if "SPOILER" in w]},
            "target_marked": {"warnings": [w for w in warnings if "TARGET_NOT_ANNOTATED" in w]},
            "readability": {"warnings": [w for w in warnings if w.split(":")[0] in ("POINTS_TOO_CLOSE", "LOW_CANVAS_USAGE", "ARC_TOO_SMALL", "SEGMENT_TOO_SHORT")]},
        },
        "visual_score": round(max(0.0, min(1.0, visual_score)), 4),
        "repair_feedback": repair_feedback,
    }
    return result
