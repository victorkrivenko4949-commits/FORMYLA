"""Выпуклость названных многоугольников: проверка, ограничения и мягкий штраф.

Повод (региональный этап ВсОШ, 9 класс): «Дан выпуклый четырёхугольник ABCD,
∠DAB = 90°, M — середина BC, ∠ADC = ∠BAM. Докажите, что ∠ADB = ∠CAM». Модель
не добавила opposite_side (правило 12 промпта — совет, не контракт), решатель
нашёл конфигурацию с C и D по разные стороны от AB: оба уравнения плана
выполнены, гейты пройдены, а четырёхугольник невыпуклый (во второй попытке —
самопересекающийся: CD пересекает AB) и утверждение задачи на чертеже ложно.

Что делает модуль (по образцу general_position / formalize_rules — обёртки без
правки semantics.py, llm.py, solver.py и pipeline.py):
  1) convexity_failures — независимая от плана проверка текста против координат:
     контур, названный выпуклым (или параллелограммом, ромбом, прямоугольником,
     квадратом, трапецией), обязан иметь все повороты одного знака — критерий и
     допуск как в semantics._rhombus_failures. Подключается к
     semantics.semantic_failures: невыпуклый чертёж больше не бывает «verified»,
     конвейер даёт модели подсказку, а при неудаче честно рисует approximate.
  2) convexity_constraints — для выпуклого ЧЕТЫРЁХугольника концы каждой
     диагонали лежат по разные стороны от другой диагонали; два opposite_side
     добавляются в план сразу после формализации (обёртка llm.formalize).
  3) Мягкий штраф в решателе. Невязка same_side/opposite_side в solver.residuals —
     ступенька (0 или скачок): у least_squares нет градиента к нужной
     полуплоскости, и верное решение находится только случайным стартом; иначе
     конвейер уходит в best-effort и показывает невыпуклую фигуру как
     approximate. Обёртки _soft_term_count/_soft_position_terms добавляют на
     ЭТАПЕ 1 решателя гладкий hinge по произведению знаковых расстояний для
     каждого side-ограничения. Ступенчатая невязка, полировка и гейт не меняются.
  4) Кэш: к pipeline.ENGINE_VERSION дописывается суффикс.

Текст нормализуется как в statement._plain / semantics._math_text ($, \\(, \\),
\\mathrm{...}), поэтому распознанное с фото «$ABCD$» тоже понимается.
GEOEXACT_CONVEXITY=0 выключает всё; GEOEXACT_CONVEXITY_INJECT=0 — инъекцию;
GEOEXACT_CONVEXITY_SOFT=0 — мягкий штраф.
"""
from __future__ import annotations

import os
import re

import numpy as np

ENABLED = (os.environ.get("GEOEXACT_CONVEXITY") or "1").strip().lower() not in ("0", "no", "off")
INJECT = (os.environ.get("GEOEXACT_CONVEXITY_INJECT") or "1").strip().lower() not in ("0", "no", "off")
SOFT = (os.environ.get("GEOEXACT_CONVEXITY_SOFT") or "1").strip().lower() not in ("0", "no", "off")
SOFT_FACTOR = float(os.environ.get("GEOEXACT_CONVEXITY_SOFT_FACTOR", "4") or "4")  # × solver.SOFT_WEIGHT
SOFT_MARGIN = 0.02      # безразмерный запас по произведению знаковых расстояний
CACHE_SUFFIX = "+cvx2"
PREFIX = "CONVEXITY: "
SIDE_TYPES = ("same_side", "opposite_side")

_NAME = r"[A-Z](?:_?\d{1,2})?"
_PT = re.compile(_NAME)
_POLY_WORD = r"(?:(?:четыр[её]х|пяти|шести|семи|восьми)угольник\w*|многоугольник\w*)"
# «выпуклый четырёхугольник ABCD», «в выпуклом пятиугольнике ABCDE»
_CONVEX_POLY = re.compile(rf"\bвыпукл\w*\s+{_POLY_WORD}\s+((?:{_NAME}){{4,8}})\b", re.I)
# «четырёхугольник ABCD выпуклый», «четырёхугольник ABCD — выпуклый»
_POLY_CONVEX = re.compile(rf"\b{_POLY_WORD}\s+((?:{_NAME}){{4,8}})\b[^.;!?]{{0,24}}?\bвыпукл", re.I)
# Фигуры, выпуклые по определению. Порядок «существительное + вершины»;
# «четырёхугольник CDEF — параллелограмм» намеренно не распознаётся (узость > ложные срабатывания).
_NAMED_QUAD = re.compile(
    rf"\b(?:параллелограмм\w*|ромб\w*|прямоугольник\w*|квадрат\w*|трапеци\w*)\s+((?:{_NAME}){{4}})\b", re.I)


def _plain(text: str) -> str:
    """LaTeX/OCR-обёртки имён точек: $ABCD$, \\(ABCD\\), \\mathrm{ABCD} -> ABCD."""
    text = text or ""
    try:
        from .semantics import _math_text
        text = _math_text(text)
    except Exception:  # noqa: BLE001
        pass
    text = re.sub(r"\\(?:mathrm|text|operatorname|mathit)\s*\{([^{}]*)\}", r"\1", text)
    for a in (r"\(", r"\)", "$", "{", "}"):
        text = text.replace(a, " " if a in ("$",) else "")
    return text


def convex_polygons(text: str) -> list[tuple[str, ...]]:
    """Многоугольники, обязанные быть выпуклыми, в порядке обхода вершин."""
    out: list[tuple[str, ...]] = []
    plain = _plain(text)
    for rx in (_CONVEX_POLY, _POLY_CONVEX, _NAMED_QUAD):
        for m in rx.finditer(plain):
            names = tuple(p.upper() for p in _PT.findall(m[1]))
            if len(names) >= 4 and len(set(names)) == len(names):
                out.append(names)
    return list(dict.fromkeys(out))


def _turns(V: list[np.ndarray]) -> list[float]:
    n = len(V)
    return [float(np.linalg.det(np.array([V[(i + 1) % n] - V[i],
                                          V[(i + 2) % n] - V[(i + 1) % n]])))
            for i in range(n)]


def convexity_failures(text: str, plan, coords: dict) -> list[str]:
    """Контур назван выпуклым -> все повороты одного знака (как _rhombus_failures)."""
    fails: list[str] = []
    for poly in convex_polygons(text):
        if not all(p in coords for p in poly):
            continue                 # отсутствие точек — забота _statement_failures
        try:
            V = [np.asarray(coords[p], dtype=float) for p in poly]
            if any(v.shape != (2,) or not np.isfinite(v).all() for v in V):
                continue
            n = len(V)
            scale = max(float(np.linalg.norm(V[(i + 1) % n] - V[i])) for i in range(n))
            if scale <= 1e-12:
                fails.append(f"{PREFIX}контур {''.join(poly)} вырожден")
                continue
            turns = _turns(V)
            eps = 1e-6 * scale * scale
            if all(t > eps for t in turns) or all(t < -eps for t in turns):
                continue
            major = 1 if sum(t > 0 for t in turns) * 2 >= n else -1
            bad = [poly[(i + 1) % n] for i, t in enumerate(turns) if t * major <= eps]
            fails.append(f"{PREFIX}{''.join(poly)} не является выпуклым при обходе "
                         f"{'→'.join(poly)} (невыпуклый или развёрнутый угол при "
                         f"{', '.join(bad)})")
        except Exception:  # noqa: BLE001 — проверка не должна ломать гейт
            continue
    return fails


def convexity_constraints(text: str, plan) -> list[dict]:
    """opposite_side для выпуклых четырёхугольников из текста (идемпотентно).

    Для четырёхугольника выпуклость <=> диагонали пересекаются <=> концы каждой
    диагонали по разные стороны от прямой другой диагонали. Для n > 4 условия
    нет: там работает только проверка.
    """
    points = set(getattr(plan, "points", None) or [])
    have = {(c.type, tuple(c.args)) for c in (getattr(plan, "constraints", None) or [])}
    out: list[dict] = []
    for poly in convex_polygons(text):
        if len(poly) != 4 or not set(poly) <= points:
            continue
        A, B, C, D = poly
        for args in ([A, C, B, D], [B, D, A, C]):
            if ("opposite_side", tuple(args)) not in have:
                out.append({"type": "opposite_side", "args": list(args)})
                have.add(("opposite_side", tuple(args)))
    return out


# ------------------------------------------------------------------ мягкий штраф
def side_constraints(plan) -> list[tuple[str, list[str]]]:
    out = []
    for c in (getattr(plan, "constraints", None) or []):
        t = getattr(c, "type", None) if not isinstance(c, dict) else c.get("type")
        a = getattr(c, "args", None) if not isinstance(c, dict) else c.get("args")
        if t in SIDE_TYPES and isinstance(a, (list, tuple)) and len(a) == 4:
            out.append((t, list(a)))
    return out


def side_penalties(plan, coords: dict, weight: float, margin: float = SOFT_MARGIN) -> list[float]:
    """Гладкий hinge на каждое side-ограничение: 0, когда полуплоскости верны с запасом."""
    out: list[float] = []
    for t, (a, b, c, d) in side_constraints(plan):
        try:
            A, B, C, D = (np.asarray(coords[k], dtype=float) for k in (a, b, c, d))
            v = D - C
            L = float(np.hypot(*v))
            if L <= 1e-12:
                out.append(weight)
                continue
            u = v / L
            da = float(u[0] * (A - C)[1] - u[1] * (A - C)[0]) / L
            db = float(u[0] * (B - C)[1] - u[1] * (B - C)[0]) / L
            s = da * db * (1.0 if t == "same_side" else -1.0)
            out.append(weight * max(0.0, margin - s) / margin)
        except Exception:  # noqa: BLE001
            out.append(0.0)
    return out


def _wrap_soft(solver_module) -> bool:
    orig_count = getattr(solver_module, "_soft_term_count", None)
    orig_terms = getattr(solver_module, "_soft_position_terms", None)
    if orig_count is None or orig_terms is None or getattr(orig_terms, "_convexity", False):
        return False

    def _soft_term_count(plan):
        return orig_count(plan) + len(side_constraints(plan))

    def _soft_position_terms(plan, coords, extent, n_terms):
        k = len(side_constraints(plan))
        base = np.asarray(orig_terms(plan, coords, extent, max(0, n_terms - k)), dtype=float)
        if k == 0:
            return base
        weight = float(getattr(solver_module, "SOFT_WEIGHT", 0.05) or 0.0) * SOFT_FACTOR
        extra = np.asarray(side_penalties(plan, coords, weight), dtype=float)
        out = np.concatenate([base, extra])
        if out.shape[0] != n_terms:           # защита длины вектора для least_squares
            fixed = np.zeros(n_terms, dtype=float)
            m = min(n_terms, out.shape[0])
            fixed[:m] = out[:m]
            return fixed
        return out

    for f, o in ((_soft_term_count, orig_count), (_soft_position_terms, orig_terms)):
        f._convexity = True
        f._original = o
        f.__doc__ = getattr(o, "__doc__", None)
        f.__name__ = o.__name__
    solver_module._soft_term_count = _soft_term_count
    solver_module._soft_position_terms = _soft_position_terms
    return True


# ------------------------------------------------------------------ обёртки LLM / семантики
def _problem_text(args, kwargs) -> str:
    if len(args) > 1 and isinstance(args[1], str):
        return args[1]
    for key in ("problem", "text"):
        if isinstance(kwargs.get(key), str):
            return kwargs[key]
    return ""


def _wrap_formalize(orig):
    def formalize(*args, **kwargs):
        res = orig(*args, **kwargs)
        if not INJECT:
            return res
        try:
            plan, warn = res
            extra = convexity_constraints(_problem_text(args, kwargs), plan)
            if extra:
                from .schema import Constraint
                plan.constraints.extend(Constraint(**c) for c in extra)
                warn = list(warn or []) + [
                    f"CONVEXITY_INJECTED: добавлено {len(extra)} opposite_side "
                    f"для выпуклого четырёхугольника"]
                return plan, warn
        except Exception:  # noqa: BLE001 — инъекция вспомогательная
            return res
        return res
    formalize._convexity = True
    formalize._original = orig
    formalize.__doc__ = getattr(orig, "__doc__", None)
    formalize.__name__ = "formalize"
    return formalize


def _wrap_semantic_failures(orig):
    def semantic_failures(text, plan, coords, *args, **kwargs):
        fails = orig(text, plan, coords, *args, **kwargs)
        try:
            extra = convexity_failures(text, plan, coords)
        except Exception:  # noqa: BLE001
            extra = []
        return list(fails) + extra if extra else fails
    semantic_failures._convexity = True
    semantic_failures._original = orig
    semantic_failures.__doc__ = getattr(orig, "__doc__", None)
    semantic_failures.__name__ = "semantic_failures"
    return semantic_failures


def install(semantics_module, llm_module, pipeline_module=None, solver_module=None) -> bool:
    """Обернуть semantics.semantic_failures, llm.formalize и мягкие штрафы решателя.
    Повторный вызов — no-op."""
    if not ENABLED:
        return False
    done = False
    orig_sf = getattr(semantics_module, "semantic_failures", None)
    if orig_sf is not None and not getattr(orig_sf, "_convexity", False):
        semantics_module.semantic_failures = _wrap_semantic_failures(orig_sf)
        done = True
    orig_f = getattr(llm_module, "formalize", None)
    if orig_f is not None and not getattr(orig_f, "_convexity", False):
        llm_module.formalize = _wrap_formalize(orig_f)
        done = True
    if SOFT:
        if solver_module is None:
            try:
                from . import solver as solver_module  # noqa: PLC0415
            except Exception:  # noqa: BLE001
                solver_module = None
        if solver_module is not None and _wrap_soft(solver_module):
            done = True
    if pipeline_module is None:
        try:
            from . import pipeline as pipeline_module  # noqa: PLC0415
        except Exception:  # noqa: BLE001
            pipeline_module = None
    ver = getattr(pipeline_module, "ENGINE_VERSION", None) if pipeline_module else None
    if isinstance(ver, str) and "+cvx" not in ver:
        pipeline_module.ENGINE_VERSION = ver + CACHE_SUFFIX
        done = True
    return done
