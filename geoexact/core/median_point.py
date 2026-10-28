# -*- coding: utf-8 -*-
"""Медиана VM треугольника XYZ: M обязана быть серединой стороны XY.

Прод-ошибка (28.10.2026, задача пользователя): «В остроугольном треугольнике
ABC со стороной AC = 1 провели высоту BH, в треугольнике BHC — биссектрису CL,
в треугольнике BLC — медиану BM. Прямая AL пересекает сторону BC в точке K,
причём ∠BHK = ∠MHC = 15°. Найдите площадь четырёхугольника KLHM.» — модель
построила M = midpoint(B, L) вместо midpoint(L, C): B, H, L, M легли на одну
прямую, ∠MHC получился 90° вместо 15°, система ограничений стала нерешаемой,
все попытки провалились — пользователь увидел схематичный эскиз.

Здесь:
 1) детерминированный ремонт плана: «медиана VM» + «свой» треугольник XYZ
    (ближайшее упоминание в том же предложении) → midpoint-конструкция M
    переписывается на середину стороны XY, вместе с on_segment(M, …);
    ремонт узкий — только полностью распознанная фраза и только op=midpoint,
    иначе no-op (координатная проверка в semantics.py даст точный feedback);
 2) правило 49 формализатора;
 3) суффикс версии движка.

GEOEXACT_MEDIAN_POINT=0 выключает.
"""
from __future__ import annotations

import functools
import os
import re

ENABLED = (os.environ.get("GEOEXACT_MEDIAN_POINT") or "1").strip().lower() not in ("0", "no", "off")

# Суффикс версии движка: ремонт и проверка меняют приёмку чертежей.
CACHE_SUFFIX = "+medianFix1"

EXTRA_RULES = """
49. MEDIAN_RULE: «медиана VM» в треугольнике XYZ — точка M обязана быть
СЕРЕДИНОЙ стороны XY, противоположной вершине V (M = midpoint(X, Y)):
«в треугольнике BLC — медиану BM» даёт M = midpoint(L, C), а НЕ midpoint(B, L)
и НЕ midpoint(B, C). Проверь каждую медиану: вершина — первая буква, середина —
второй буквы на стороне из двух ОСТАЛЬНЫХ букв треугольника.
"""

_MEDIAN = re.compile(r"\bмедиан\w*\s+([A-Z])([A-Z])\b")
_TRIANGLE = re.compile(r"\bтреугольник\w*\s+([A-Z]{3})\b", re.I)


def _plain(text: str) -> str:
    """LaTeX-условия к обычному тексту: \\(BM\\) → BM (как в statement._plain)."""
    for a, b in ((r"\(", " "), (r"\)", " "), (r"\[", " "), (r"\]", " "), ("$", " ")):
        text = text.replace(a, b)
    return text


def median_claims(text: str) -> list[tuple[str, str, str, str]]:
    """[(вершина, основание, x, y)]: медиана VM треугольника VX Y.

    Треугольник — ближайшее упоминание СЛЕВА от медианы в том же предложении
    (чевиана относится к уже названному треугольнику), иначе первый
    треугольник текста. Как в semantics.cevian_triangle. Нераспознанное
    не попадает в список.
    """
    t = _plain(text or "")
    out: list[tuple[str, str, str, str]] = []
    first = _TRIANGLE.search(t)
    for m in _MEDIAN.finditer(t):
        vertex, foot = m[1].upper(), m[2].upper()
        start = max((s.end() for s in re.finditer(r"[.;!?]", t[:m.start()])), default=0)
        end_m = re.search(r"[.;!?]", t[start:])
        end = start + (end_m.start() if end_m else len(t) - start)
        sentence = t[start:end]
        nearest = None
        for tm in _TRIANGLE.finditer(sentence):
            if tm.start() <= m.start() - start and (nearest is None
                                                   or tm.start() > nearest[0]):
                nearest = (tm.start(), tm[1].upper())
        tri = nearest[1] if nearest else (first[1].upper() if first else "")
        if not tri or vertex not in tri or foot in tri:
            continue
        x, y = [n for n in tri if n != vertex]
        if len({x, y}) == 2:
            out.append((vertex, foot, x, y))
    return out


def repair(text: str, plan) -> str | None:
    """Переставить midpoint-конструкцию медианы на середину правильной стороны.

    Возвращает описание починки или None (не распознано / нечего чинить).
    """
    claims = median_claims(text)
    if not claims:
        return None
    known = set(getattr(plan, "points", None) or [])
    messages: list[str] = []
    for _vertex, foot, x, y in claims:
        if foot not in known or not {x, y} <= known:
            continue
        for c in getattr(plan, "constructions", None) or []:
            if (getattr(c, "out", None) == foot and getattr(c, "op", "") == "midpoint"
                    and len(getattr(c, "args", None) or []) == 2
                    and {c.args[0], c.args[1]} != {x, y}):
                old = (c.args[0], c.args[1])
                c.args = [x, y]
                for cn in getattr(plan, "constraints", None) or []:
                    # on_segment(M, u, v) про старую сторону — про новую
                    if (getattr(cn, "type", "") == "on_segment"
                            and len(getattr(cn, "args", None) or []) == 3
                            and cn.args[0] == foot
                            and {cn.args[1], cn.args[2]} == set(old)):
                        cn.args = [foot, x, y]
                messages.append(f"медиана: {foot} переставлена на середину "
                                f"{x}{y} (была середина {old[0]}{old[1]})")
                break
    if not messages:
        return None
    return "; ".join(messages)


def _log_plan(tag: str, plan) -> None:
    try:
        from .equidistant_repair import _log_plan as _base
        _base(tag, plan)
    except Exception:  # noqa: BLE001 - журнал не должен ломать ремонт
        pass


def install(llm_module, pipeline_module=None) -> bool:
    """Правило в промпты + пост-ремонт плана после formalize. Повторно — no-op."""
    if not ENABLED:
        return False
    try:
        target = getattr(llm_module, "SYS_FORMALIZE", None)
        if target and "49." not in target:
            llm_module.SYS_FORMALIZE = target.rstrip("\n") + "\n" + EXTRA_RULES
        ok = "49." in (llm_module.SYS_FORMALIZE or "")
        orig = getattr(llm_module, "formalize", None)
        if orig is not None and not getattr(orig, "_median_point", False):
            @functools.wraps(orig)
            def formalize(sess, text, *args, **kwargs):
                plan, warn = orig(sess, text, *args, **kwargs)
                try:
                    msg = repair(text, plan)
                    if msg:
                        _log_plan("MEDIAN_REPAIRED", plan)
                        warn = [str(w) for w in (warn or [])] + [f"MEDIAN_FIXED: {msg}"]
                except Exception:  # noqa: BLE001 - ремонт не должен валить формализацию
                    pass
                return plan, warn
            formalize._median_point = True
            llm_module.formalize = formalize
            ok = True
        if pipeline_module is not None:
            ver = getattr(pipeline_module, "ENGINE_VERSION", None)
            if ver is not None and CACHE_SUFFIX not in ver:
                pipeline_module.ENGINE_VERSION = ver + CACHE_SUFFIX
        return bool(ok)
    except Exception:  # noqa: BLE001
        return False
