# -*- coding: utf-8 -*-
"""Починка планов формализатора: порядок конструкций и якорь line_circle_other.

Прод-ошибки (баг-хант 26.10.2026, задачи пользователя):
 1. «В треугольнике ABC на медиане BM отмечена точка K так, что BK:KM = 3:1.
    Через точку K проведена прямая, параллельная AC, пересекающая стороны
    AB и BC в точках P и Q соответственно...» — формализатор сослался в
    line_intersect на точку Q до её построения (FORWARD_REF), три повтора
    с подсказкой не помогли — конвейер ушёл в схематичный эскиз.
 2. «В выпуклом четырёхугольнике ABCD ... Y — второе пересечение BC с
    описанной окружностью ABD, X — второе пересечение AB с описанной
    окружностью BCD. Докажите, что ∠AKX = ∠CKY.» — формализатор дал
    line_circle_other с якорем A, который НЕ лежит на окружности BCD
    (на ней лежит B): операция вернула произвольный корень, чертёж не
    прошёл проверки, показан эскиз.

Здесь:
  1) перестановка конструкций: ссылка вперёд лечится стабильной
     топологической сортировкой (циклы не трогаем — валидация честно
     откажет с причиной);
  2) семантическая проверка: якорь line_circle_other не на своей
     окружности — отказ с причиной;
  3) правила 47 (порядок) и 48 (якорь) формализатора.

GEOEXACT_PLAN_REPAIR=0 выключает.
"""
from __future__ import annotations

import functools
import os

ENABLED = (os.environ.get("GEOEXACT_PLAN_REPAIR") or "1").strip().lower() not in ("0", "no", "off")

# Суффикс версии движка: починка планов меняет приёмку чертежей.
CACHE_SUFFIX = "+planFix1"

EXTRA_RULES = """
47. ORDER_RULE: конструкции упорядочивай по зависимостям — каждая операция
ссылается ТОЛЬКО на уже построенные точки. Прямую через K параллельную AC
НЕ задавай через ещё не построенную точку (например [K,Q] — это цикл):
построй вспомогательную X = parallel_point(K, A, C, 1.0) (точка K + вектор
C−A) или translate(K, A, C), затем P = line_intersect([K,X],[A,B]) и
Q = line_intersect([K,X],[B,C]).
48. LINE_CIRCLE_OTHER_RULE: line_circle_other(P1, P2, O, R) возвращает
второе пересечение прямой P1P2 с окружностью (центр O, радиус |OR|) —
ПЕРВЫЙ аргумент P1 ОБЯЗАН лежать на этой окружности (|P1O| = |OR|).
Для «второго пересечения стороны AB с описанной окружностью XYZ» якорь —
тот конец стороны, который лежит на этой окружности (проверь, какой:
например, для окружности BCD и прямой AB якорь B, а НЕ A).
"""


def repair_construction_order(plan) -> bool:
    """Стабильная топологическая сортировка конструкций плана.

    Конструкция, ссылающаяся на ещё не построенную точку, откладывается
    до её определения. Циклы (и ссылки на вовсе отсутствующие точки) не
    трогаем — их честно отвергнет валидация с причиной. Возвращает True,
    если порядок изменился.
    """
    try:
        cons = list(getattr(plan, "constructions", None) or [])
        if not cons:
            return False
        defined: set = set()
        out = []
        pending = list(cons)
        while True:
            rest = []
            progressed = False
            for c in pending:
                args = [a for a in (getattr(c, "args", None) or [])]
                if all(a in defined for a in args):
                    out.append(c)
                    if getattr(c, "out", None):
                        defined.add(c.out)
                    progressed = True
                else:
                    rest.append(c)
            pending = rest
            if not pending or not progressed:
                break
        new = out if not pending else out + pending
        if [id(c) for c in new] == [id(c) for c in cons]:
            return False
        plan.constructions = new
        return True
    except Exception:  # noqa: BLE001
        return False


def line_circle_anchor_failures(plan, coords) -> list:
    """Якорь line_circle_other обязан лежать на своей окружности."""
    fails: list = []
    try:
        import numpy as np
        for c in getattr(plan, "constructions", None) or []:
            if getattr(c, "op", "") != "line_circle_other":
                continue
            args = list(getattr(c, "args", None) or [])
            if len(args) != 4:
                continue
            p1, _p2, o, r = args
            if not all(x in coords for x in (p1, o, r)):
                continue
            P1, O, R = (np.asarray(coords[k], dtype=float) for k in (p1, o, r))
            d_anchor = float(np.linalg.norm(P1 - O))
            d_radius = float(np.linalg.norm(R - O))
            if d_radius <= 0.0:
                continue
            if abs(d_anchor - d_radius) > 1e-6 * max(1.0, d_radius):
                fails.append(
                    f"LINE_CIRCLE_ANCHOR: line_circle_other({p1}, ...) — якорь "
                    f"{p1} не лежит на окружности (|{p1}{o}| = {d_anchor:.6g} != "
                    f"|{o}{r}| = {d_radius:.6g}); первый аргумент обязан быть "
                    f"точкой окружности")
    except Exception:  # noqa: BLE001
        pass
    return fails


def _sanitize_target(plan) -> bool:
    """Невалидная цель (ARITY/UNKNOWN_TARGET) не должна ронять задачу в
    схему: чертим точный чертёж без измерения. Остальные ошибки валидации
    не трогаем — ими занимается цикл повторов с обратной связью.

    Прод-кейс (26.10.2026, медиана BK:KM=3:1 с доп. построением): цель
    ratio с неверным числом точек — 3 повтора формализатора не исправили,
    конвейер упал в 9-render-sketch. Измерение — украшение, а не условие:
    чертёж важнее ответа в подписи.
    """
    try:
        from .schema import validate_plan, PlanError
        try:
            validate_plan(plan)
            return False
        except PlanError as e:
            if e.code not in ("ARITY", "UNKNOWN_TARGET"):
                return False
            if "цель" not in str(e):
                return False
        if getattr(plan.target, "kind", "none") == "none":
            return False
        dropped = f"{plan.target.kind}({', '.join(plan.target.args)})"
        plan.target.kind = "none"
        plan.target.args = []
        try:
            validate_plan(plan)
        except Exception:  # noqa: BLE001
            return False                      # не помогло — обычный путь
        return True
    except Exception:  # noqa: BLE001
        return False


def _wrap_coerce_formalized(orig):
    @functools.wraps(orig)
    def _coerce_formalized(res):
        plan, warn = orig(res)
        try:
            repair_construction_order(plan)
        except Exception:  # noqa: BLE001
            pass
        try:
            if _sanitize_target(plan):
                warn = (list(warn or []) + [
                    "TARGET_DROPPED: цель измерения некорректна (неверное "
                    "число точек); чертёж построен без измерения — ответ "
                    "смотрите в полном решении"])
        except Exception:  # noqa: BLE001
            pass
        return plan, warn
    _coerce_formalized._plan_repair = True
    _coerce_formalized._original = orig
    return _coerce_formalized


def _wrap_semantic_failures(orig):
    @functools.wraps(orig)
    def semantic_failures(text, plan, coords, *args, **kwargs):
        base = orig(text, plan, coords, *args, **kwargs)
        try:
            if isinstance(base, list):
                return base + [f for f in line_circle_anchor_failures(plan, coords)
                              if f not in base]
            return base
        except Exception:  # noqa: BLE001
            return base
    semantic_failures._plan_repair = True
    semantic_failures._original = orig
    return semantic_failures


def _install_llm_rules(llm_module) -> bool:
    try:
        target = llm_module.SYS_FORMALIZE
        if "47." not in target:
            llm_module.SYS_FORMALIZE = target.rstrip("\n") + "\n" + EXTRA_RULES
        ok = "47." in llm_module.SYS_FORMALIZE
        ok = ok and "ORDER_RULE" in llm_module.SYS_FORMALIZE
        ok = ok and "48." in llm_module.SYS_FORMALIZE
        ok = ok and "LINE_CIRCLE_OTHER_RULE" in llm_module.SYS_FORMALIZE
        return bool(ok)
    except Exception:  # noqa: BLE001
        return False


def install(semantics_module, llm_module, pipeline_module=None) -> bool:
    """Подключение: починка порядка + проверка якоря + правила + суффикс."""
    if not ENABLED:
        return False
    try:
        if pipeline_module is not None:
            fn = getattr(pipeline_module, "_coerce_formalized", None)
            if fn is not None and not getattr(fn, "_plan_repair", False):
                pipeline_module._coerce_formalized = _wrap_coerce_formalized(fn)
        if not getattr(semantics_module.semantic_failures, "_plan_repair", False):
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
