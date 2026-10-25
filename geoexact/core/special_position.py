# -*- coding: utf-8 -*-
"""Частное положение: на чертеже не должно быть равенств, которых нет в условии.

Прод-ошибка (26.10.2026): «В выпуклом четырёхугольнике ABCD стороны AB и BC
равны, K — точка пересечения диагоналей... Докажите, что ∠AKX = ∠CKY» —
формализатор добавил к равенству из «докажите» лишнюю симметрию (по сути
сделал K серединой AC), и решателю осталось только вырожденное семейство:
нарисовался дельтоид с AD = CD и AC ⟂ BD, хотя это НЕ следует из условия.
Чертёж «доказал» утверждение, навязав читателю лишние равенства.

Здесь — независимая проверка по координатам: у названного четырёхугольника
(или трапеции) стороны, равные на чертеже, должны быть заявлены в условии
(«XY = ZW», «равны», «ромб», «равнобедренная» и т. п.) или следовать из
ограничений плана (dist_eq, dist с одинаковым значением). Незаявленное
равенство — частное положение, предупреждение. Плюс правило 44
формализатора: никаких симметрий, которых нет в тексте. Треугольники не
проверяются: там равенство сторон часто следует из равенства углов в
условии, и проверка ложно срабатывала бы. GEOEXACT_SPECIAL_POSITION=0
выключает.
"""
from __future__ import annotations

import functools
import itertools
import os
import re

import numpy as np

ENABLED = (os.environ.get("GEOEXACT_SPECIAL_POSITION") or "1").strip().lower() not in ("0", "no", "off")

# Суффикс версии движка: новая проверка текста меняет приёмку чертежей.
CACHE_SUFFIX = "+specialPos1"

EXTRA_RULES = """
44. SPECIAL_POSITION_RULE («докажите, что ...» / «точка пересечения
    диагоналей»): равенство из «докажите» кодируй РОВНО одним
    angle_eq / dist_eq — без вспомогательных симметрий. K — точка
    пересечения диагоналей — это line_intersect(A,C,B,D), НЕ midpoint и
    НЕ divide_segment. Никаких отражений (reflect_point/reflect_line),
    середин и перпендикулярностей, которых нет в тексте: лишняя симметрия
    сужает семейство решений до частного случая (дельтоид вместо общего
    четырёхугольника), и чертёж навязывает равенства, которых нет в
    условии — проверка частного положения такой чертёж забракует.
"""

_NAME = r"[A-Z](?:_?\d{1,2})?"
# «четырёхугольник ABCD», «трапеции ABCD» — 4 вершины подряд.
_QUAD = re.compile(
    rf"(?:четырёхугольник\w*|четырехугольник\w*|трапец\w*)\s+({_NAME})({_NAME})({_NAME})({_NAME})(?![A-Za-z0-9_])",
    re.I)
# Заявленные равенства: «AB = BC», «AB и BC равны», «стороны AB и BC равны».
_EQ_DIRECT = re.compile(
    rf"({_NAME})({_NAME})\s*=\s*({_NAME})({_NAME})(?![A-Za-z0-9_])")
_EQ_WORDS = re.compile(
    rf"({_NAME})({_NAME})\s+и\s+({_NAME})({_NAME})\s+(?:равны|равные|одинаковы)(?![A-Za-z0-9_])")
# Слова, после которых равенство сторон может следовать из условия неявно
# (равнобедренность, ромб, медиана...) — такие предложения пропускаем.
_IMPLICIT = re.compile(
    r"равнобедренн\w*|равнобок\w*|равносторонн\w*|ромб\w*|квадрат\w*|правильн\w*|медиан\w*|середин\w*|симметрич\w*|параллелограмм\w*|прямоугольник\w*",
    re.I)

_TOL_REL = 3e-4        # относительный допуск равенства сторон на чертеже


def _plain(text: str) -> str:
    try:
        from .convexity import _plain as p
        return p(text)
    except Exception:  # noqa: BLE001
        return (text or "").replace("$", " ")


def _key(name: str, P: dict) -> str | None:
    for cand in (name, name.replace("_", ""), re.sub(r"(\d)", r"_\1", name, count=1)):
        if cand in P:
            return cand
    return None


def _side_len(P: dict, side: frozenset) -> float | None:
    if len(side) != 2:
        return None
    a, b = tuple(side)
    ka, kb = _key(a, P), _key(b, P)
    if ka is None or kb is None:
        return None
    return float(np.linalg.norm(P[ka] - P[kb]))


def _stated_pairs(text: str) -> set[frozenset]:
    """Пары сторон, равенство которых заявлено в тексте."""
    out: set[frozenset] = set()
    for rx in (_EQ_DIRECT, _EQ_WORDS):
        for m in rx.finditer(text):
            s1 = frozenset((m[1].upper(), m[2].upper()))
            s2 = frozenset((m[3].upper(), m[4].upper()))
            out.add(frozenset((s1, s2)))
    return out


def _plan_pairs(plan) -> set[frozenset]:
    """Пары сторон, равенство которых следует из ограничений плана."""
    out: set[frozenset] = set()
    if plan is None:
        return out
    distvals: dict[float, list[frozenset]] = {}
    for c in (getattr(plan, "constraints", None) or []):
        ctype = c.get("type") if isinstance(c, dict) else getattr(c, "type", None)
        args = (c.get("args") if isinstance(c, dict) else getattr(c, "args", None)) or []
        value = c.get("value") if isinstance(c, dict) else getattr(c, "value", None)
        try:
            if ctype == "dist_eq" and len(args) == 4:
                s1 = frozenset(map(str, args[:2]))
                s2 = frozenset(map(str, args[2:]))
                out.add(frozenset((s1, s2)))
            elif ctype == "dist" and len(args) == 2 and isinstance(value, (int, float)):
                distvals.setdefault(round(float(value), 6), []).append(
                    frozenset(map(str, args)))
        except Exception:  # noqa: BLE001
            continue
    for segs in distvals.values():
        for s1, s2 in itertools.combinations(segs, 2):
            out.add(frozenset((s1, s2)))
    return out


def special_position_failures(text: str, plan, coords: dict) -> list[str]:
    """Незаявленные равенства сторон названного четырёхугольника/трапеции."""
    fails: list[str] = []
    if not isinstance(coords, dict) or not coords:
        return fails
    P = {k: np.asarray(v, dtype=float).reshape(-1)[:2]
         for k, v in coords.items()
         if np.all(np.isfinite(np.asarray(v, dtype=float).reshape(-1)[:2]))}
    if len(P) < 4:
        return fails
    plain = _plain(text or "")
    stated = _stated_pairs(plain) | _plan_pairs(plan)
    for sentence in re.split(r"(?<=[.;!?])\s+", plain):
        if _IMPLICIT.search(sentence):
            continue          # равенство может следовать из условия неявно
        for m in _QUAD.finditer(sentence):
            v = [m[i].upper() for i in range(1, 5)]
            if len(set(v)) != 4:
                continue
            sides = [frozenset((v[0], v[1])), frozenset((v[1], v[2])),
                     frozenset((v[2], v[3])), frozenset((v[3], v[0]))]
            lens = [_side_len(P, s) for s in sides]
            if any(L is None for L in lens):
                continue       # отсутствие точек ловит семантика имён
            for i, j in itertools.combinations(range(4), 2):
                if frozenset((sides[i], sides[j])) in stated:
                    continue
                s1, s2 = sorted((lens[i], lens[j]), reverse=True)
                if s2 > 1e-12 and (s1 - s2) / s1 < _TOL_REL:
                    n1 = "".join(sorted(sides[i]))
                    n2 = "".join(sorted(sides[j]))
                    fails.append(
                        f"стороны {n1} и {n2} равны на чертеже, но это не "
                        f"следует из условия (частное положение — чертёж "
                        f"навязывает лишнее равенство)")
    return list(dict.fromkeys(fails))


def _wrap_semantic_failures(orig):
    @functools.wraps(orig)
    def semantic_failures(text, plan, coords, *args, **kwargs):
        base = orig(text, plan, coords, *args, **kwargs)
        try:
            if isinstance(base, list):
                return base + [f for f in special_position_failures(text, plan, coords)
                               if f not in base]
            return base
        except Exception:  # noqa: BLE001
            return base
    semantic_failures._special_position = True
    semantic_failures._original = orig
    return semantic_failures


def _install_llm_rules(llm_module) -> bool:
    try:
        target = llm_module.SYS_FORMALIZE
        if "44." not in target:
            llm_module.SYS_FORMALIZE = target.rstrip("\n") + "\n" + EXTRA_RULES
        ok = "44." in llm_module.SYS_FORMALIZE
        ok = ok and "SPECIAL_POSITION_RULE" in llm_module.SYS_FORMALIZE
        return bool(ok)
    except Exception:  # noqa: BLE001
        return False


def install(semantics_module, llm_module, pipeline_module=None) -> bool:
    """Подключение: обёртка semantic_failures + правило 44 + суффикс кэша."""
    if not ENABLED:
        return False
    try:
        if not getattr(semantics_module.semantic_failures, "_special_position", False):
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
