"""Радиус/диаметр описанной или вписанной окружности названного треугольника.

Повод: «Точка D лежит на основании AB равнобедренного тупоугольного треугольника
ABC так, что отрезок AD равен радиусу описанной окружности треугольника BCD.
Найдите угол ACD». Модель нарисовала описанную окружность треугольника ABC,
поставила D в середину AB и не задала AD = R(BCD) вовсе — а независимые проверки
semantics.py разбирают только равенства вида «XY = ZW» и числовые длины, поэтому
план прошёл как «проверенный». В словаре ограничений радиуса нет, но он
выражается штатно: O = circumcenter(B,C,D), затем dist_eq [A,D,O,B].

Что делает модуль (обёртки, как convexity / incircle_tangents):
  1) radius_claims(text) — утверждения вида «(отрезок) XY равен радиусу/диаметру
     описанной/вписанной окружности треугольника PQR» и «радиус … треугольника
     PQR равен XY / числу»; LaTeX ($, \\(…\\)) нормализуется; предложения
     с «докажите» пропускаются (цель — не данность, как в statement.py).
  2) radius_failures(text, plan, coords) — считает R = abc/4S или r = 2S/(a+b+c)
     по координатам и сравнивает с |XY| или числом (допуск 1e-4, как у остальных
     проверок). Сообщение RADIUS_CLAIM содержит рецепт для модели; подключается к
     semantics.semantic_failures, дальше работает штатный цикл: подсказка → повтор →
     approximate.
  3) Правила формализатора 33–35: радиус через circumcenter/incenter + dist_eq,
     запрет подменять окружность названного треугольника другой, точка «на
     стороне так, что …» — свободная точка с on_segment, а не середина.

GEOEXACT_RADIUS_CLAIMS=0 выключает всё.
"""
from __future__ import annotations

import functools
import math
import os
import re

import numpy as np

ENABLED = (os.environ.get("GEOEXACT_RADIUS_CLAIMS") or "1").strip().lower() not in ("0", "no", "off")
MARK = "dist_eq [P,Q,O,X]"
PREFIX = "RADIUS_CLAIM: "
REL_TOL = 1e-4

EXTRA_RULES = """
33. Радиус описанной окружности треугольника XYZ — это |OX|, где O=circumcenter(X,Y,Z)
    (O перечисли в points; если O не назван в условии — в hide_labels). Радиус
    вписанной окружности — |IT|, где I=incenter(X,Y,Z), T=foot(I,X,Y). Условие
    «отрезок PQ равен радиусу описанной окружности треугольника XYZ» задавай как
    dist_eq [P,Q,O,X]; «равен диаметру» — dist_ratio [P,Q,O,X] со значением 2.
    Числовой радиус — dist [O,X] = число. Это ОБЯЗАТЕЛЬНОЕ ограничение, его нельзя
    опустить или заменить удобной точкой.
34. Окружность, названная в условии (описанная около треугольника BCD, вписанная в
    треугольник XYZ), — именно она: рисуй circles [[O,B]] с её центром. НЕ подменяй
    её описанной окружностью всего чертежа или другого треугольника.
35. «Точка D лежит на стороне/основании AB так, что <условие>» — D=free_point плюс
    on_segment [D,A,B] плюс само условие ограничением. НЕ ставь D в середину
    (midpoint) и не дели отрезок (divide_segment), если это не сказано явно.
"""

_NAME = r"[A-Z](?:_?\d{1,2})?"
_SEG = rf"(?:{_NAME}){{2}}"
_TRI = rf"(?:{_NAME}){{3}}"
_NUM = r"\d+(?:[.,]\d+)?"
_KIND = r"(описанн\w*|вписанн\w*)"
# «(отрезок) AD равен радиусу описанной окружности треугольника BCD»
# «AD равен радиусу окружности, описанной около треугольника BCD»
_SEG_EQ_RADIUS = re.compile(
    rf"(?<![A-Za-z0-9_])({_SEG})\s+(?:равен|равна|равный|равного|равно)\s+(радиус\w*|диаметр\w*)\s+"
    rf"(?:{_KIND}\s+)?окружност\w*\s*,?\s*(?:{_KIND}\s+)?(?:около|в|вокруг)?\s*треугольник\w*\s+({_TRI})(?![A-Za-z0-9_])",
    re.I)
# «радиус описанной окружности треугольника BCD равен AD / 5»
_RADIUS_EQ = re.compile(
    rf"(радиус\w*|диаметр\w*)\s+(?:{_KIND}\s+)?окружност\w*\s*,?\s*(?:{_KIND}\s+)?(?:около|в|вокруг)?\s*"
    rf"треугольник\w*\s+({_TRI})\s*(?:равен|равна|равно|=)\s*({_SEG}|{_NUM})(?![A-Za-z0-9_])", re.I)
_PT = re.compile(_NAME)


def _plain(text: str) -> str:
    try:
        from .convexity import _plain as p
        return p(text)
    except Exception:  # noqa: BLE001
        return (text or "").replace("$", " ")


def _kind(*words) -> str | None:
    for w in words:
        if not w:
            continue
        w = w.lower()
        if w.startswith("описанн"):
            return "circum"
        if w.startswith("вписанн"):
            return "in"
    return None


def radius_claims(text: str) -> list[dict]:
    """[{seg:(X,Y)|None, value:float|None, factor:1|2, kind:'circum'|'in', tri:(P,Q,R)}]"""
    out: list[dict] = []
    # Утверждение из «докажите, что …» — цель, а не данность (как в statement.py).
    t = " ".join(s for s in re.split(r"(?<=[.;!?])\s+", _plain(text))
                 if not re.search(r"докаж|доказать|покаж", s, re.I))
    for m in _SEG_EQ_RADIUS.finditer(t):
        seg = tuple(p.upper() for p in _PT.findall(m[1]))
        tri = tuple(p.upper() for p in _PT.findall(m[5]))
        kind = _kind(m[3], m[4])
        if kind and len(seg) == 2 and len(set(tri)) == 3:
            out.append({"seg": seg, "value": None, "factor": 2 if m[2].lower().startswith("диаметр") else 1,
                        "kind": kind, "tri": tri})
    for m in _RADIUS_EQ.finditer(t):
        tri = tuple(p.upper() for p in _PT.findall(m[4]))
        kind = _kind(m[2], m[3])
        rhs = m[5]
        if not kind or len(set(tri)) != 3:
            continue
        claim = {"seg": None, "value": None, "factor": 2 if m[1].lower().startswith("диаметр") else 1,
                 "kind": kind, "tri": tri}
        if re.fullmatch(_NUM, rhs):
            claim["value"] = float(rhs.replace(",", "."))
        else:
            seg = tuple(p.upper() for p in _PT.findall(rhs))
            if len(seg) != 2:
                continue
            claim["seg"] = seg
        out.append(claim)
    uniq, seen = [], set()
    for c in out:
        key = (c["seg"], c["value"], c["factor"], c["kind"], c["tri"])
        if key not in seen:
            seen.add(key)
            uniq.append(c)
    return uniq


def triangle_radius(kind: str, P: np.ndarray, Q: np.ndarray, R: np.ndarray) -> float | None:
    """Радиус описанной (circum) или вписанной (in) окружности; None для вырожденного."""
    a, b, c = (float(np.linalg.norm(Q - R)), float(np.linalg.norm(P - R)), float(np.linalg.norm(P - Q)))
    area2 = abs(float((Q - P)[0] * (R - P)[1] - (Q - P)[1] * (R - P)[0]))   # 2·площадь
    if min(a, b, c) <= 1e-12 or area2 <= 1e-12 * max(a, b, c) ** 2:
        return None
    if kind == "circum":
        return a * b * c / (2.0 * area2)
    return area2 / (a + b + c)


def radius_failures(text: str, plan, coords: dict) -> list[str]:
    fails: list[str] = []
    for c in radius_claims(text):
        tri = c["tri"]
        need = list(tri) + list(c["seg"] or ())
        missing = list(dict.fromkeys(n for n in need if n not in coords))
        human = ("радиус" if c["factor"] == 1 else "диаметр") + " " + \
                ("описанной" if c["kind"] == "circum" else "вписанной") + \
                f" окружности треугольника {''.join(tri)}"
        if missing:
            fails.append(f"{PREFIX}нет точек {', '.join(missing)} для условия «{human}»")
            continue
        try:
            P, Q, R = (np.asarray(coords[n], dtype=float) for n in tri)
            radius = triangle_radius(c["kind"], P, Q, R)
            if radius is None:
                fails.append(f"{PREFIX}треугольник {''.join(tri)} вырожден, {human} не определён")
                continue
            want = radius * c["factor"]
            if c["seg"] is not None:
                X, Y = c["seg"]
                got = float(np.linalg.norm(np.asarray(coords[X], float) - np.asarray(coords[Y], float)))
                label = f"отрезок {X}{Y}"
            else:
                got = float(c["value"])
                label = f"заданное число {got:g}"
            if not math.isfinite(got) or abs(got - want) > REL_TOL * max(abs(want), abs(got), 1e-9):
                if c["kind"] == "circum":
                    centre = f"O=circumcenter({','.join(tri)})"
                    recipe = (f"dist_eq [{X},{Y},O,{tri[0]}]" if c["seg"] is not None
                              else f"dist [O,{tri[0]}] = {got:g}")
                else:
                    centre = f"I=incenter({','.join(tri)}), T=foot(I,{tri[0]},{tri[1]})"
                    recipe = (f"dist_eq [{X},{Y},I,T]" if c["seg"] is not None
                              else f"dist [I,T] = {got:g}")
                fails.append(f"{PREFIX}{label} = {got:.6g}, а {human} = {want:.6g}; условие не выполнено. "
                             f"Построй {centre} и задай {recipe}"
                             + (" (для диаметра — dist_ratio со значением 2)" if c["factor"] == 2 else ""))
        except Exception:  # noqa: BLE001 — проверка не должна ломать гейт
            continue
    return fails


def _wrap_semantic_failures(orig):
    def semantic_failures(text, plan, coords, *args, **kwargs):
        fails = orig(text, plan, coords, *args, **kwargs)
        try:
            extra = radius_failures(text, plan, coords)
        except Exception:  # noqa: BLE001
            extra = []
        return list(fails) + extra if extra else fails
    # functools.wraps копирует __dict__ внутренней обёртки: маркеры других
    # модулей (_convexity, …) не теряются на внешнем слое цепочки.
    functools.wraps(orig)(semantic_failures)
    semantic_failures._radius_claims = True
    semantic_failures._original = orig
    return semantic_failures


def _append_rules(llm_module) -> bool:
    base = getattr(llm_module, "SYS_FORMALIZE", None)
    aux = getattr(llm_module, "SYS_AUX", None)
    if not isinstance(base, str) or MARK in base:
        return False
    new_base = base.rstrip() + "\n" + EXTRA_RULES.rstrip() + "\n"
    llm_module.SYS_FORMALIZE = new_base
    if isinstance(aux, str):
        if aux.startswith(base):
            llm_module.SYS_AUX = new_base + aux[len(base):]
        elif MARK not in aux:
            llm_module.SYS_AUX = aux.rstrip() + "\n" + EXTRA_RULES.rstrip() + "\n"
    return True


def install(semantics_module, llm_module) -> bool:
    """Проверка радиусов в semantic_failures и правила формализатора. Повторно — no-op."""
    if not ENABLED:
        return False
    done = _append_rules(llm_module)
    orig = getattr(semantics_module, "semantic_failures", None)
    if orig is not None and not getattr(orig, "_radius_claims", False):
        semantics_module.semantic_failures = _wrap_semantic_failures(orig)
        done = True
    return done
