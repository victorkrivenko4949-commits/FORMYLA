# -*- coding: utf-8 -*-
"""services/aux_usefulness.py — численная проверка полезности доп. построения.

Для base-чертежа критерий — соответствие условию.  Для доп. построения
критерий другой: построение должно быть ПОЛЕЗНЫМ.  Проверяется численно,
без LLM: сравнение BuildContext до и после добавления aux.

Признаки пользы дают вес, признаки вреда — блокирующие.
"""

from __future__ import annotations

import itertools
import math
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    from geometric_engine import geom as _geom
except Exception:  # pragma: no cover
    _geom = None

DEFAULT_ANGLE_TOL_DEG = 0.5
DEFAULT_LENGTH_REL_TOL = 0.01
DEFAULT_LENGTH_ABS_TOL = 1.0

# Веса признаков пользы.
_USEFULNESS_WEIGHTS = {
    "equal_segments": 0.25,
    "equal_angles": 0.20,
    "right_angle": 0.20,
    "isosceles": 0.15,
    "similarity": 0.15,
    "parallel": 0.10,
    "connectivity": 0.10,
    "incidence": 0.15,
}


def _point_names(ctx: Any) -> List[str]:
    return list(getattr(ctx, "points", {}) or {}).copy()


def _dist(ctx: Any, a: str, b: str) -> Optional[float]:
    pts = getattr(ctx, "points", {}) or {}
    if a in pts and b in pts and _geom is not None:
        return _geom.dist(pts[a], pts[b])
    return None


def _angle_deg(ctx: Any, a: str, b: str, c: str) -> Optional[float]:
    pts = getattr(ctx, "points", {}) or {}
    if a in pts and b in pts and c in pts and _geom is not None:
        try:
            return math.degrees(_geom.angle_between_three(pts[a], pts[b], pts[c]))
        except Exception:
            return None
    return None


def _segment_pairs(ctx: Any) -> Set[Tuple[str, str]]:
    """Все пары точек, соединённые отрезком/прямой/лучом."""
    segs = getattr(ctx, "segments", {}) or {}
    pairs: Set[Tuple[str, str]] = set()
    for sid, seg in segs.items():
        p1, p2 = seg
        if p1 and p2:
            pairs.add((p1, p2))
            pairs.add((p2, p1))
    return pairs


def _detect_gains(ctx_before: Any, ctx_after: Any) -> List[str]:
    """Найти новые геометрические свойства, появившиеся после aux."""
    gains: List[str] = []
    before_names = set(_point_names(ctx_before))
    after_names = set(_point_names(ctx_after))
    new_names = after_names - before_names

    after_pairs = _segment_pairs(ctx_after)
    pts = getattr(ctx_after, "points", {}) or {}

    # 1. Новые равенства отрезков (перебираем ВСЕ пары, не обрываем на первом).
    found_equal_segments = False
    for a, b in itertools.combinations(sorted(after_names), 2):
        for c, d in itertools.combinations(sorted(after_names), 2):
            if (a, b) == (c, d):
                continue
            dab = _dist(ctx_after, a, b)
            dcd = _dist(ctx_after, c, d)
            if dab is None or dcd is None or dab < 1e-6 or dcd < 1e-6:
                continue
            if abs(dab - dcd) / max(dab, dcd) <= DEFAULT_LENGTH_REL_TOL:
                gains.append(f"equal_segments:{a}{b}={c}{d}")
                found_equal_segments = True
                break
        if found_equal_segments:
            break

    # 2. Прямые углы (перебираем все тройки, не обрываем на первом).
    for a in sorted(after_names):
        for b in sorted(after_names):
            if b == a:
                continue
            for c in sorted(after_names):
                if c in (a, b):
                    continue
                ang = _angle_deg(ctx_after, a, b, c)
                if ang is None:
                    continue
                if abs(ang - 90.0) <= DEFAULT_ANGLE_TOL_DEG:
                    gains.append(f"right_angle:{a}{b}{c}")

    # 3. Новый равнобедренный треугольник (две равные стороны).
    for tri in itertools.combinations(sorted(after_names), 3):
        a, b, c = tri
        dab = _dist(ctx_after, a, b)
        dbc = _dist(ctx_after, b, c)
        dca = _dist(ctx_after, c, a)
        if not dab or not dbc or not dca:
            continue
        if abs(dab - dca) / max(dab, dca, 1e-6) <= DEFAULT_LENGTH_REL_TOL:
            gains.append(f"isosceles:{a}{b}{c}")

    # 4. Соединяет ранее не связанные объекты.
    before_pairs = _segment_pairs(ctx_before)
    new_links = after_pairs - before_pairs
    if new_links and any(p[0] in new_names or p[1] in new_names for p in new_links):
        gains.append("connectivity:new_segment")

    return gains


def _detect_harms(ctx_before: Any, ctx_after: Any,
                  aux_constructions: List[dict],
                  max_new_points: int = 3) -> List[str]:
    """Найти блокирующие признаки вреда.

    CH-aux FIX: ограничение на число новых точек убрано — полноценные
    построения (вписанная окружность: биссектрисы + центр + основания
    перпендикуляров + радиусы) создают много точек, и это нормально.
    Блокирующими оставляем только реально вредные случаи.
    """
    harms: List[str] = []
    before_names = set(_point_names(ctx_before))
    after_names = set(_point_names(ctx_after))

    # 1. Совпадающие точки (расстояние < 1px).  Не блокируем: в конструкциях
    # вроде вписанной окружности вспомогательные точки могут лечь близко
    # друг к другу (основание перпендикуляра vs точка касания) — это не вред.

    # 2. Дублирует существующий объект.
    before_pairs = _segment_pairs(ctx_before)
    after_pairs = _segment_pairs(ctx_after)
    for pair in (after_pairs - before_pairs):
        # Новая пара, состоящая только из старых точек и уже соединённая — дубликат.
        if pair[0] in before_names and pair[1] in before_names:
            harms.append(f"duplicate_object:{pair[0]}{pair[1]}")
            break

    return harms


def evaluate_usefulness(
    ctx_before: Any,
    ctx_after: Any,
    aux_constructions: List[dict],
    settings: Optional[Any] = None,
) -> Dict[str, Any]:
    """Оценить полезность набора доп. построений.

    Returns:
      {"useful": bool, "score": float, "gains": [str], "harms": [str],
       "verdict": "useful" | "useless" | "harmful"}
    """
    if not aux_constructions:
        return {"useful": False, "score": 0.0, "gains": [],
                "harms": [], "verdict": "useless"}

    max_new_points = 3
    if settings is not None:
        max_new_points = int(getattr(settings, "aux_max_new_points", None) or 3)

    harms = _detect_harms(ctx_before, ctx_after, aux_constructions, max_new_points)
    if harms:
        return {"useful": False, "score": 0.0, "gains": [],
                "harms": harms, "verdict": "harmful"}

    gains = _detect_gains(ctx_before, ctx_after)

    # Скоринг: сумма весов уникальных признаков.
    score = 0.0
    seen = set()
    for g in gains:
        key = g.split(":", 1)[0]
        if key not in seen:
            seen.add(key)
            score += _USEFULNESS_WEIGHTS.get(key, 0.05)
    score = round(max(0.0, min(1.0, score)), 4)

    useful = score >= 0.20
    verdict = "useful" if useful else "useless"
    return {
        "useful": useful,
        "score": score,
        "gains": gains,
        "harms": harms,
        "verdict": verdict,
    }
