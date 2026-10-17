"""Выпуклость названных многоугольников: проверка и детерминированные ограничения.

Повод (региональный этап ВсОШ, 9 класс): «Дан выпуклый четырёхугольник ABCD,
∠DAB = 90°, M — середина BC, ∠ADC = ∠BAM. Докажите, что ∠ADB = ∠CAM». Модель
не добавила opposite_side (правило 12 промпта — совет, не контракт), решатель
нашёл конфигурацию с C и D по разные стороны от AB: оба уравнения плана
выполнены, гейты пройдены, а четырёхугольник невыпуклый и утверждение задачи на
чертеже ложно. Ни gate_correctness, ни semantic_failures слово «выпуклый» не
разбирали.

Что делает модуль (по образцу general_position / formalize_rules — обёртки без
правки semantics.py, llm.py и pipeline.py):
  1) convexity_failures — независимая от плана проверка текста против координат:
     контур, названный выпуклым (или параллелограммом, ромбом, прямоугольником,
     квадратом, трапецией), обязан иметь все повороты одного знака — тот же
     критерий и допуск, что в semantics._rhombus_failures. Подключается к
     semantics.semantic_failures: невыпуклый чертёж больше не бывает «verified»,
     конвейер даёт модели подсказку и, если не вышло, честно рисует approximate.
  2) convexity_constraints — для выпуклого ЧЕТЫРЁХугольника концы каждой
     диагонали лежат по разные стороны от другой диагонали; два opposite_side
     добавляются в план сразу после формализации (обёртка llm.formalize), чтобы
     решатель отбрасывал невыпуклые старты, не дожидаясь ретрая модели.
  3) Кэш: к pipeline.ENGINE_VERSION дописывается суффикс, чтобы старые
     невыпуклые чертежи не возвращались из кэша.

Невязка same_side/opposite_side в solver.residuals — ступенька и трогать её
нельзя (гейт опирается на положительный скачок на границе); модуль её не меняет.
GEOEXACT_CONVEXITY=0 выключает всё; GEOEXACT_CONVEXITY_INJECT=0 — только инъекцию.
"""
from __future__ import annotations

import os
import re

import numpy as np

ENABLED = (os.environ.get("GEOEXACT_CONVEXITY") or "1").strip().lower() not in ("0", "no", "off")
INJECT = (os.environ.get("GEOEXACT_CONVEXITY_INJECT") or "1").strip().lower() not in ("0", "no", "off")
CACHE_SUFFIX = "+cvx1"
PREFIX = "CONVEXITY: "

_NAME = r"[A-Z](?:_?\d{1,2})?"
_PT = re.compile(_NAME)
# «выпуклый четырёхугольник ABCD», «в выпуклом пятиугольнике ABCDE», «выпуклого многоугольника A_1A_2A_3A_4»
_CONVEX_POLY = re.compile(
    rf"\bвыпукл\w*\s+(?:(?:четыр[её]х|пяти|шести|семи|восьми)угольник\w*|многоугольник\w*)\s+"
    rf"((?:{_NAME}){{4,8}})\b", re.I)
# Фигуры, выпуклые по определению. Порядок «существительное + вершины»;
# «четырёхугольник CDEF — параллелограмм» намеренно не распознаётся (узость > ложные срабатывания).
_NAMED_QUAD = re.compile(
    rf"\b(?:параллелограмм\w*|ромб\w*|прямоугольник\w*|квадрат\w*|трапеци\w*)\s+((?:{_NAME}){{4}})\b", re.I)


def convex_polygons(text: str) -> list[tuple[str, ...]]:
    """Многоугольники, обязанные быть выпуклыми, в порядке обхода вершин."""
    out: list[tuple[str, ...]] = []
    for rx in (_CONVEX_POLY, _NAMED_QUAD):
        for m in rx.finditer(text or ""):
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


def install(semantics_module, llm_module, pipeline_module=None) -> bool:
    """Обернуть semantics.semantic_failures и llm.formalize. Повторный вызов — no-op."""
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
    if pipeline_module is None:
        try:
            from . import pipeline as pipeline_module  # noqa: PLC0415
        except Exception:  # noqa: BLE001
            pipeline_module = None
    ver = getattr(pipeline_module, "ENGINE_VERSION", None) if pipeline_module else None
    if isinstance(ver, str) and CACHE_SUFFIX not in ver:
        pipeline_module.ENGINE_VERSION = ver + CACHE_SUFFIX
        done = True
    return done
