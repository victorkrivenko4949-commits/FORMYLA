# -*- coding: utf-8 -*-
"""Внешние построения (квадраты/правильные треугольники на сторонах):
правило 46 + семантическая проверка стороны.

Прод-ошибка (баг-хант 26.10.2026): «На сторонах AB и AC треугольника ABC во
внешнюю сторону построены квадраты ABDE и ACFG. Докажите, что BG = CE и
BG перпендикулярно CE.» — формализатор строил ОБА квадрата поворотами
одного знака вокруг общей вершины A. Но внешность обоих квадратов
математически требует ПРОТИВОПОЛОЖНЫХ знаков (внешняя сторона AB — это
сторона, противоположная C; внешняя сторона AC — противоположная B; для
обхода треугольника эти условия означают разные направления поворота).
Система с двумя opposite_side не решалась вовсе — конвейер ушёл в
приближённый фолбэк (APPROXIMATE: условия выполнены лишь приближённо),
хотя конфигурация допускает точное решение (15 решений).

Вторая опасность, которую ловит проверка: формализатор вовсе не добавляет
opposite_side — решатель тогда выбирает произвольную ориентацию, и квадрат
может оказаться ВНУТРИ треугольника, а чертёж всё равно покажется точным.

Здесь:
  1) правило 46 формализатора: циклическое кодирование квадрата на
     стороне, opposite_side для внешности, ПРОТИВОПОЛОЖНЫЕ знаки для двух
     внешних фигур на сторонах, выходящих из одной вершины;
  2) семантическая проверка: «внешним образом» в тексте + квадрат на
     стороне треугольника нарисован с внутренней стороны — отказ.

GEOEXACT_EXTERNAL_FIGURES=0 выключает.
"""
from __future__ import annotations

import functools
import os
import re

import numpy as np

ENABLED = (os.environ.get("GEOEXACT_EXTERNAL_FIGURES") or "1").strip().lower() not in ("0", "no", "off")

# Суффикс версии движка: новая проверка меняет приёмку чертежей.
CACHE_SUFFIX = "+extFig1"

EXTRA_RULES = """
46. EXTERNAL_FIGURE_RULE («на стороне AB построен квадрат ABDE (внешним
    образом)»): квадрат на стороне AB кодируй ЦИКЛИЧЕСКИ: E = rotate([B, A],
    -90) (вершина при A), D = rotate([A, B], +90) (вершина при B).
    «Внешним образом / во внешнюю сторону / вне треугольника» — добавь
    ОБЯЗАТЕЛЬНО opposite_side([D, C, A, B]) И opposite_side([E, C, A, B])
    (C — третья вершина треугольника), иначе решатель нарисует квадрат
    внутри. Для ДВУХ внешних фигур на сторонах AB и AC, выходящих из
    одной вершины A, знаки поворотов ПРОТИВОПОЛОЖНЫ: E = rotate([B, A],
    -90), D = rotate([A, B], +90), но G = rotate([C, A], +90), F =
    rotate([A, C], -90). Одинаковые знаки делают внешность ОБЕИХ фигур
    математически невозможной — система ограничений не решается. Если
    текст не требует внешности — opposite_side не добавляй.
"""

_L = r"[A-Z](?:_?\d{1,2})?"

# «треугольника ABC» — опорный треугольник для стороны
_TRI = re.compile(rf"треугольник\w*\s+({_L})({_L})({_L})", re.I)

# «квадрат ABDE» / «равносторонний треугольник ABE»
_SQUARE = re.compile(rf"квадрат\w*\s+({_L})({_L})({_L})({_L})", re.I)
_EQUILATERAL = re.compile(
    rf"равносторонн\w*\s+треугольник\w*\s+({_L})({_L})({_L})", re.I)

_EXTERNAL = re.compile(r"внешн\w*\s+(?:образом|сторону|стороне)|вне\s+треугольник", re.I)


def _plain(text: str) -> str:
    try:
        from .convexity import _plain as p
        return p(text or "")
    except Exception:  # noqa: BLE001
        return (text or "").replace("$", " ")


def _cross(o, a, b) -> float:
    return float((a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]))


def _pt(coords, name):
    v = coords[name]
    return (float(v[0]), float(v[1]))


def external_figure_failures(text: str, coords) -> list[str]:
    """«внешним образом» + фигура на стороне треугольника нарисована
    изнутри — отказ: чертёж противоречит условию."""
    fails: list[str] = []
    if not coords or not _EXTERNAL.search(_plain(text or "")):
        return fails
    statement = _plain(text or "")
    m_tri = _TRI.search(statement)
    if m_tri is None:
        return fails
    tri = {m_tri[i].upper() for i in range(1, 4)}
    if len(tri) != 3:
        return fails

    def check_figure(side_a: str, side_b: str, far: list[str], kind: str):
        if side_a.upper() not in tri or side_b.upper() not in tri:
            return
        ref = (tri - {side_a.upper(), side_b.upper()})
        ref = next(iter(ref)) if ref else None
        if ref is None:
            return
        names = [side_a, side_b, ref, *far]
        if not all(n in coords for n in names):
            return
        A, B, R = _pt(coords, side_a), _pt(coords, side_b), _pt(coords, ref)
        if _cross(A, B, R) == 0.0:
            return  # вырожденный чертёж — не ориентация
        ref_sign = 1.0 if _cross(A, B, R) > 0 else -1.0
        for f in far:
            if f not in coords:
                continue
            fs = _cross(A, B, _pt(coords, f))
            if fs == 0.0:
                continue
            if (fs > 0) == (ref_sign > 0):
                fails.append(
                    f"EXTERNAL_FIGURE: {kind} {''.join([side_a, side_b, *far])} "
                    f"построен с внутренней стороны прямой {side_a}{side_b} — "
                    f"в условии сказано «внешним образом»")

    for m in _SQUARE.finditer(statement):
        check_figure(m[1], m[2], [m[3], m[4]], "квадрат")
    for m in _EQUILATERAL.finditer(statement):
        check_figure(m[1], m[2], [m[3]], "равносторонний треугольник")
    return fails


def _wrap_semantic_failures(orig):
    @functools.wraps(orig)
    def semantic_failures(text, plan, coords, *args, **kwargs):
        base = orig(text, plan, coords, *args, **kwargs)
        try:
            if isinstance(base, list):
                return base + [f for f in external_figure_failures(text, coords)
                               if f not in base]
            return base
        except Exception:  # noqa: BLE001
            return base
    semantic_failures._external_figures = True
    semantic_failures._original = orig
    return semantic_failures


def _install_llm_rules(llm_module) -> bool:
    try:
        target = llm_module.SYS_FORMALIZE
        if "46." not in target:
            llm_module.SYS_FORMALIZE = target.rstrip("\n") + "\n" + EXTRA_RULES
        ok = "46." in llm_module.SYS_FORMALIZE
        ok = ok and "EXTERNAL_FIGURE_RULE" in llm_module.SYS_FORMALIZE
        return bool(ok)
    except Exception:  # noqa: BLE001
        return False


def install(semantics_module, llm_module, pipeline_module=None) -> bool:
    """Подключение: проверка внешности + правило 46 + суффикс кэша."""
    if not ENABLED:
        return False
    try:
        if not getattr(semantics_module.semantic_failures, "_external_figures", False):
            semantics_module.semantic_failures = _wrap_semantic_failures(
                semantics_module.semantic_failures)
        ok = _install_llm_rules(llm_module)
        if pipeline_module is not None:
            ver = getattr(pipeline_module, "ENGINE_VERSION", None)
            if ver is not None and CACHE_SUFFIX not in ver:
                pipeline_module.ENGINE_VERSION = ver + CACHE_SUFFIX
        return bool(ok)
    except Exception:  # noqa: BLE001
        return False
