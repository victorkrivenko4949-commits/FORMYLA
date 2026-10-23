# -*- coding: utf-8 -*-
"""services/condition_coverage.py — детерминированная проверка полноты
base-чертежа относительно текста условия.

Дополняет:
  * services.figure_validator        — план ↔ схема движка
  * services.figure_plan_validator   — инварианты base ↔ aux

Отвечает на вопрос: «отражает ли чертёж ВСЁ, что сказано в условии,
и совпадает ли фактическая геометрия с заявленной?».

Без LLM. Только stdlib. Численная сверка выполняется через geometric_engine.geom,
если передан build_context (BuildContext после build_with_retry).
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    from . import figure_plan_validator as _fpv
    _extract_condition_points = _fpv.extract_condition_points
    _base_constructions = _fpv._base_constructions
    _declared_ids = _fpv._declared_ids
    _loads = _fpv._loads
except Exception:  # pragma: no cover — при изолированном импорте
    from services import figure_plan_validator as _fpv
    _extract_condition_points = _fpv.extract_condition_points
    _base_constructions = _fpv._base_constructions
    _declared_ids = _fpv._declared_ids
    _loads = _fpv._loads

try:
    from geometric_engine import geom as _geom
except Exception:  # pragma: no cover
    _geom = None


# ──────────────────────────────────────────────────────────────────────────
# Веса категорий для скоринга (сумма = 1.0).
# ──────────────────────────────────────────────────────────────────────────
COVERAGE_WEIGHTS = {
    "points":       0.25,
    "numeric":      0.25,
    "realization":  0.20,
    "incidences":   0.15,
    "marks":        0.10,
    "target":       0.05,
}

# Численные допуски (значения по умолчанию; EngineSettings их не содержит).
DEFAULT_ANGLE_TOL_DEG = 0.5
DEFAULT_LENGTH_REL_TOL = 0.01      # 1% относительный
DEFAULT_LENGTH_ABS_TOL = 1.0       # пиксель абсолютный минимум
DEFAULT_INCIDENCE_TOL = 2.0        # пиксели


# ──────────────────────────────────────────────────────────────────────────
# Регексы извлечения величин и свойств из условия.
# ──────────────────────────────────────────────────────────────────────────

_EQUALITY_TRIGGER_RE = re.compile(
    r"([A-Z]{2}\s*=\s*[A-Z]{2}|равн[ыоае]|равнобедренн|равносторонн|"
    r"ромб|квадрат|середин|медиан|биссектрис\w*\s+дел)",
    re.IGNORECASE,
)
_RIGHT_ANGLE_TRIGGER_RE = re.compile(
    r"(прям(ой|ым)\s+угол|перпендикуляр|90\s*°|высот[аыу]|"
    r"прямоугольн\w*\s+треугольник|прямоугольник|квадрат)",
    re.IGNORECASE,
)
_MIDPOINT_TRIGGER_RE = re.compile(
    r"(середин|медиан|дел\w*\s+пополам)",
    re.IGNORECASE,
)

# Величины углов: «угол B = 50°», «∠B=50°», «∠ABC равен 50».
_NUM_ANGLE_RE = re.compile(
    r"(?:угол|∠)\s*([A-Z]{1,3})\s*(?:равен|=|:)?\s*(\d+(?:[.,]\d+)?)\s*°?",
    re.IGNORECASE,
)
# Длины: «AB = 5 см».
_NUM_LEN_RE = re.compile(
    r"\b([A-Z]{2})\s*=\s*(\d+(?:[.,]\d+)?)\s*(см|мм|м)?\b"
)
# Голые градусы (без имени угла).
_BARE_DEG_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*°")
# Радиус.
_RADIUS_RE = re.compile(
    r"(?:радиус|R)\s*(?:равен|=)?\s*(\d+(?:[.,]\d+)?)", re.IGNORECASE
)

# Искомый объект: «Найдите ∠ADC», «найти угол B», «чему равен отрезок AB».
_TARGET_RE = re.compile(
    r"(?:найдите|найти|вычислите|чему\s+равен|определите|докажите)\s+"
    r"(?:величину\s+)?(?:угл\w+|отрез\w+|сторон\w+|площад\w+|радиус|длин\w+)?\s*"
    r"(∠?\s*[A-Z]{1,3})",
    re.IGNORECASE,
)


# ──────────────────────────────────────────────────────────────────────────
# Нормализация числовых подписей.
# ──────────────────────────────────────────────────────────────────────────

def _norm_number(text: Any) -> Optional[float]:
    """Нормализовать строку величины в float (None если не число)."""
    if text is None:
        return None
    s = str(text).strip().replace(" ", "").replace(",", ".")
    s = s.replace("°", "")
    m = re.search(r"(\d+(?:\.\d+)?)", s)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def _labels_in_plan(constructions: List[dict]) -> List[dict]:
    """Все angle_label / length_label из плана."""
    out = []
    for c in constructions:
        if c.get("type") in ("angle_label", "length_label"):
            out.append(c)
    return out


def _point_coord(build_context: Any, pid: str):
    """Координаты точки из BuildContext.points, либо None."""
    if build_context is None:
        return None
    pts = getattr(build_context, "points", None)
    if not pts:
        return None
    p = pts.get(pid)
    if p is None:
        return None
    if isinstance(p, (tuple, list)) and len(p) == 2:
        try:
            return (float(p[0]), float(p[1]))
        except (TypeError, ValueError):
            return None
    return None


# ──────────────────────────────────────────────────────────────────────────
# Проверки A–H
# ──────────────────────────────────────────────────────────────────────────

def _check_points(condition_text: str, constructions: List[dict]) -> Tuple[List[str], Set[str]]:
    """A · точки условия.  Каждая точка обязана быть порождена построением."""
    errors: List[str] = []
    points = _extract_condition_points(condition_text)
    declared = _declared_ids(constructions)
    for p in sorted(points):
        if p not in declared:
            errors.append(
                f"MISSING_CONDITION_POINT: точка '{p}' из условия не создана в плане"
            )
    return errors, points


def _check_numeric(condition_text: str, constructions: List[dict]) -> List[str]:
    """B · числовые данные условия должны быть отмечены на чертеже."""
    errors: List[str] = []
    labels = _labels_in_plan(constructions)

    label_texts: List[float] = []
    label_refs: Set[str] = set()
    for lab in labels:
        n = _norm_number(lab.get("text", lab.get("label")))
        if n is not None:
            label_texts.append(n)
        for f in ("vertex", "ray1", "ray2", "p1", "p2"):
            v = lab.get(f)
            if isinstance(v, str) and v:
                label_refs.add(v)

    # Углы с именем.
    named_expected: Set[float] = set()
    for m in _NUM_ANGLE_RE.finditer(condition_text):
        name = m.group(1)
        expected = float(m.group(2).replace(",", "."))
        named_expected.add(expected)
        matched = any(abs(n - expected) <= 1e-6 for n in label_texts)
        if not matched:
            errors.append(
                f"MISSING_NUMERIC_LABEL: угол {name} = {expected}° из условия "
                f"не отмечен angle_label на чертеже"
            )

    # Голые градусы (без имени угла) — только для значений, не покрытых
    # именованным углом выше (иначе дублируем одну и ту же ошибку).
    for m in _BARE_DEG_RE.finditer(condition_text):
        expected = float(m.group(1).replace(",", "."))
        if expected in named_expected:
            continue
        if not any(abs(n - expected) <= 1e-6 for n in label_texts):
            errors.append(
                f"MISSING_NUMERIC_LABEL: величина {expected}° из условия "
                f"не отмечена на чертеже"
            )

    # Длины отрезков.
    for m in _NUM_LEN_RE.finditer(condition_text):
        pair = m.group(1)
        expected = float(m.group(2).replace(",", "."))
        matched = any(abs(n - expected) <= 1e-6 for n in label_texts)
        if not matched:
            errors.append(
                f"MISSING_NUMERIC_LABEL: длина {pair} = {expected} из условия "
                f"не отмечена length_label на чертеже"
            )

    # Радиус.
    for m in _RADIUS_RE.finditer(condition_text):
        expected = float(m.group(1).replace(",", "."))
        if not any(abs(n - expected) <= 1e-6 for n in label_texts):
            errors.append(
                f"MISSING_NUMERIC_LABEL: радиус {expected} из условия "
                f"не отмечен на чертеже"
            )

    return errors


def _angle_abc_deg(ctx_points: Dict[str, Any], a: str, b: str, c: str) -> Optional[float]:
    """Фактический угол ABC (в вершине B) в градусах."""
    pa = ctx_points.get(a)
    pb = ctx_points.get(b)
    pc = ctx_points.get(c)
    if not pa or not pb or not pc:
        return None
    if _geom is None:
        return None
    rad = _geom.angle_between_three(pa, pb, pc)
    return math.degrees(rad)


def _check_realization(condition_text: str, build_context: Any,
                       constructions: List[dict], settings: Any) -> List[str]:
    """H · реализованность условия: фактическая геометрия ≈ заявленной."""
    errors: List[str] = []
    if build_context is None or _geom is None:
        # Структурная деградация: если нет контекста — UNDERSPECIFIED_PLAN.
        return []

    pts = getattr(build_context, "points", None) or {}

    angle_tol = getattr(settings, "angle_tol", None) or DEFAULT_ANGLE_TOL_DEG

    # REC-3: резолв угла по одной букве через контекст фигуры.
    try:
        from services.visual_audit import resolve_angle_triple
    except Exception:  # pragma: no cover
        resolve_angle_triple = None

    for m in _NUM_ANGLE_RE.finditer(condition_text):
        name = m.group(1)
        expected = float(m.group(2).replace(",", "."))
        if len(name) == 3:
            a, b, c = name[0], name[1], name[2]
        elif len(name) == 1 and resolve_angle_triple is not None:
            triple = resolve_angle_triple(name, constructions, condition_text)
            if triple is None:
                continue
            a, b, c = triple
        else:
            # ∠AB — неоднозначно, пропускаем (нет вершины).
            continue
        actual = _angle_abc_deg(pts, a, b, c)
        if actual is None:
            continue
        if abs(actual - expected) > angle_tol:
            errors.append(
                f"CONDITION_NOT_REALIZED: ∠{name} на чертеже {actual:.2f}°, "
                f"в условии {expected}°"
            )

    return errors


def _check_equalities(condition_text: str, constructions: List[dict]) -> List[str]:
    """C · равенства отрезков должны быть отмечены."""
    errors: List[str] = []
    if not _EQUALITY_TRIGGER_RE.search(condition_text):
        return errors
    has_mark = any(
        c.get("type") == "equal_segments_mark" for c in constructions
    )
    if not has_mark:
        errors.append(
            "MISSING_EQUALITY_MARK: условие содержит равенство отрезков, "
            "но equal_segments_mark отсутствует"
        )
    return errors


def _check_right_angles(condition_text: str, constructions: List[dict]) -> List[str]:
    """D · прямые углы должны быть отмечены."""
    errors: List[str] = []
    if not _RIGHT_ANGLE_TRIGGER_RE.search(condition_text):
        return errors
    has_mark = any(
        c.get("type") == "right_angle_mark" for c in constructions
    )
    if not has_mark:
        errors.append(
            "MISSING_RIGHT_ANGLE_MARK: условие содержит прямой угол, "
            "но right_angle_mark отсутствует"
        )
    return errors


def _check_midpoints(condition_text: str, constructions: List[dict]) -> List[str]:
    """E · середины должны быть отмечены (warning)."""
    warnings: List[str] = []
    if not _MIDPOINT_TRIGGER_RE.search(condition_text):
        return warnings
    has_mark = any(
        c.get("type") in ("midpoint_mark", "midpoint") for c in constructions
    )
    if not has_mark:
        warnings.append(
            "MISSING_MIDPOINT_MARK: условие содержит середину, "
            "но midpoint_mark отсутствует"
        )
    return warnings


def _check_target(condition_text: str, constructions: List[dict]) -> Tuple[List[str], List[str]]:
    """G · искомый объект: точки должны существовать, желательна подсветка."""
    errors: List[str] = []
    warnings: List[str] = []
    declared = _declared_ids(constructions)
    for m in _TARGET_RE.finditer(condition_text):
        raw = m.group(1)
        letters = re.findall(r"[A-Z]", raw)
        missing = [ch for ch in letters if ch not in declared]
        if missing:
            errors.append(
                f"TARGET_POINTS_MISSING: искомый объект '{raw}' содержит "
                f"отсутствующие точки {missing}"
            )
        # Подсветка: key_point или метка.
        highlighted = any(
            c.get("visual_role") == "key_point" or c.get("type") in ("angle_label", "length_label")
            for c in constructions
            if any(ch in str(c.get("id", "")) or ch in str(c.get("vertex", "")) for ch in letters)
        )
        if not highlighted:
            warnings.append(
                f"TARGET_NOT_HIGHLIGHTED: искомый объект '{raw}' не выделен "
                f"(visual_role=key_point или метка)"
            )
    return errors, warnings


def _check_incidences(condition_text: str, base_plan: Any) -> List[str]:
    """F · инцидентности (делегируем figure_plan_validator)."""
    try:
        return _fpv.check_missing_incidence(condition_text, base_plan)
    except Exception:
        return []


def _check_aux_in_base_only(constructions: List[dict]) -> List[str]:
    """Блокирующая проверка: в base-only режиме не должно быть aux-объектов."""
    errors: List[str] = []
    for c in constructions:
        if c.get("style") == "aux" or c.get("dashed") is True:
            errors.append(
                f"AUX_IN_BASE_ONLY_MODE: объект '{c.get('id')}' имеет style=aux "
                f"или dashed=true в base-only режиме"
            )
    return errors


# ──────────────────────────────────────────────────────────────────────────
# Главная точка входа.
# ──────────────────────────────────────────────────────────────────────────

def check_condition_coverage(
    condition_text: str,
    base_plan: Any,
    build_context: Optional[Any] = None,
    settings: Optional[Any] = None,
) -> Dict[str, Any]:
    """Детерминированная проверка полноты base-чертежа относительно условия.

    Args:
        condition_text: текст условия задачи.
        base_plan:      dict или JSON-строка base-плана.
        build_context:  BuildContext после успешного build_with_retry().
                        Без него проверки C/F/H работают в структурном режиме
                        (без численной сверки).
        settings:       EngineSettings для допусков.

    Returns:
        {
          "complete": bool,
          "errors":   [str],
          "warnings": [str],
          "coverage": {...},
          "score":    float,
          "repair_feedback": str,
        }
    """
    from services.text_normalize import normalize_condition
    condition_text = normalize_condition(condition_text)

    plan = _loads(base_plan)
    constructions: List[dict] = _base_constructions(plan)

    errors: List[str] = []
    warnings: List[str] = []

    # A · точки условия.
    a_errors, cond_points = _check_points(condition_text, constructions)
    errors.extend(a_errors)

    # B · числовые данные.
    errors.extend(_check_numeric(condition_text, constructions))

    # H · реализованность (численная сверка, если есть контекст).
    errors.extend(_check_realization(condition_text, build_context,
                                     constructions, settings))

    # C · равенства.
    errors.extend(_check_equalities(condition_text, constructions))

    # D · прямые углы.
    errors.extend(_check_right_angles(condition_text, constructions))

    # E · середины (warning).
    warnings.extend(_check_midpoints(condition_text, constructions))

    # F · инцидентности.
    errors.extend(_check_incidences(condition_text, base_plan))

    # G · искомый объект.
    g_errors, g_warnings = _check_target(condition_text, constructions)
    errors.extend(g_errors)
    warnings.extend(g_warnings)

    # Блокирующая проверка aux в base-only режиме.
    errors.extend(_check_aux_in_base_only(constructions))

    # ── Скоринг по категориям (0.0..1.0). ──
    coverage: Dict[str, Any] = {
        "points":       {"total": len(cond_points), "ok": len(cond_points) - len(a_errors)},
        "numeric":      {"errors": [e for e in errors if e.startswith("MISSING_NUMERIC_LABEL") or e.startswith("NUMERIC_LABEL_MISMATCH")]},
        "realization":  {"errors": [e for e in errors if e.startswith("CONDITION_NOT_REALIZED")]},
        "incidences":   {"errors": [e for e in errors if e.startswith("MISSING_INCIDENCE") or e.startswith("INCIDENCE_NOT_SATISFIED")]},
        "marks":        {"errors": [e for e in errors if e.startswith("MISSING_EQUALITY_MARK") or e.startswith("MISSING_RIGHT_ANGLE_MARK")]},
        "target":       {"errors": g_errors},
    }

    category_ratio: Dict[str, float] = {}
    # points
    total_points = len(cond_points)
    category_ratio["points"] = 1.0 if total_points == 0 else (
        (total_points - len(a_errors)) / total_points
    )
    # numeric
    numeric_errs = len(coverage["numeric"]["errors"])
    num_expected = len(_NUM_ANGLE_RE.findall(condition_text)) \
        + len(_NUM_LEN_RE.findall(condition_text)) \
        + len(_RADIUS_RE.findall(condition_text))
    category_ratio["numeric"] = 1.0 if num_expected == 0 else max(
        0.0, 1.0 - numeric_errs / num_expected
    )
    # realization
    real_errs = len(coverage["realization"]["errors"])
    category_ratio["realization"] = 1.0 if real_errs == 0 else 0.0
    # incidences
    inc_errs = len(coverage["incidences"]["errors"])
    category_ratio["incidences"] = 1.0 if inc_errs == 0 else 0.0
    # marks
    mark_errs = len(coverage["marks"]["errors"])
    category_ratio["marks"] = 1.0 if mark_errs == 0 else 0.0
    # target
    category_ratio["target"] = 1.0 if not g_errors else 0.0

    score = sum(
        COVERAGE_WEIGHTS[k] * category_ratio.get(k, 1.0)
        for k in COVERAGE_WEIGHTS
    )
    score = max(0.0, min(1.0, score))

    complete = len(errors) == 0

    # ── repair_feedback: только errors, компактно и адресно. ──
    repair_feedback = ""
    if errors:
        lines = []
        for i, e in enumerate(errors, 1):
            action = _repair_action(e)
            lines.append(f"[{i}] {e}\n    Действие: {action}")
        repair_feedback = (
            "Чертёж не соответствует условию. Исправь ТОЛЬКО перечисленное.\n\n"
            + "\n\n".join(lines)
        )

    result: Dict[str, Any] = {
        "complete": complete,
        "score": round(score, 4),
        "coverage": coverage,
        "repair_feedback": repair_feedback,
        "errors": errors,
        "warnings": warnings,
    }
    return result


def _repair_action(error: str) -> str:
    """Готовый текст действия для роли repair по коду ошибки."""
    code = error.split(":", 1)[0].strip()
    if code == "MISSING_CONDITION_POINT":
        m = re.search(r"точка '([^']+)'", error)
        return f"создай точку '{m.group(1)}' отдельной операцией (free_point / midpoint / altitude с foot_id)."
    if code == "MISSING_NUMERIC_LABEL":
        if "угол" in error:
            m = re.search(r"угол ([A-Z]{1,3})\s*=\s*([\d.]+)°", error)
            if m:
                return f"добавь angle_label с text=\"{m.group(2)}°\" при вершине {m.group(1)[0]}."
        if "радиус" in error:
            m = re.search(r"радиус\s*([\d.]+)", error)
            if m:
                return f"добавь length_label с text=\"{m.group(1)}\" на радиус."
        if "длина" in error:
            m = re.search(r"длина ([A-Z]{2})\s*=\s*([\d.]+)", error)
            if m:
                return f"добавь length_label с text=\"{m.group(2)}\" на отрезок {m.group(1)}."
        return "добавь соответствующую числовую метку (angle_label / length_label)."
    if code == "CONDITION_NOT_REALIZED":
        return ("задай угол операцией triangle_by_two_angles или angle_at_vertex, "
                "длину — segment_length, равенство — equal_segments. "
                "Не подбирай свободные координаты.")
    if code == "MISSING_INCIDENCE":
        m = re.search(r"точка '([^']+)'", error)
        return f"используй point_on_segment / point_on_circle / inscribed_polygon для '{m.group(1)}', а не free_point."
    if code == "MISSING_EQUALITY_MARK":
        return "добавь equal_segments_mark на равные отрезки."
    if code == "MISSING_RIGHT_ANGLE_MARK":
        return "добавь right_angle_mark при прямом угле."
    if code == "TARGET_POINTS_MISSING":
        return "создай отсутствующие точки искомого объекта."
    if code == "AUX_IN_BASE_ONLY_MODE":
        return "убери style=aux / dashed=true — это base-чертёж."
    return "исправь указанную ошибку."
