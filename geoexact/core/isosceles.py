# -*- coding: utf-8 -*-
"""«Равнобедренный треугольник ABC с основанием AC»: проверка по координатам.

Хвост из батча 2 (25.10.2026): «В равнобедренном треугольнике ABC с
основанием AC ... биссектриса угла ABC пересекает описанную окружность в
точке D» — равенство боковых сторон было дано в тексте явно (AB = BC =
13), и его поймал STATEMENT_MARK. Но если длины НЕ названы числами
(«В равнобедренном треугольнике ABC с основанием AC угол BAC = 55°»),
координатной проверки нет: формализатор, нарисовавший разносторонний
треугольник, прошёл бы молча. Здесь — независимая проверка: у
«равнобедренного треугольника XYZ с основанием YZ» боковые |XY| = |XZ|,
у «равностороннего» — все три стороны равны. Плюс правило 43
формализатора: dist_eq вместо выдуманных dist. GEOEXACT_ISOSCELES=0
выключает.
"""
from __future__ import annotations

import functools
import os
import re

import numpy as np

ENABLED = (os.environ.get("GEOEXACT_ISOSCELES") or "1").strip().lower() not in ("0", "no", "off")

# Суффикс версии движка: новая проверка текста меняет приёмку чертежей.
CACHE_SUFFIX = "+isosceles1"

EXTRA_RULES = """
43. ISOSCELES_RULE («равнобедренный треугольник XYZ с основанием YZ»):
    боковые стороны равны — закодируй dist_eq([X,Y,X,Z]) (|XY| = |XZ|),
    НЕ выдумывай числовые dist для боковых, если в тексте нет чисел.
    Основание YZ — единственная сторона с числом (или без равенства).
    «Равносторонний треугольник XYZ» — три dist_eq([X,Y,X,Z]),
    dist_eq([Y,X,Y,Z]), dist_eq([Z,X,Z,Y]) либо одно число стороны с
    scale_free: false. Числа углов при основании оставь углами (angle_eq
    или два angle) — равенство сторон уже следует из dist_eq.
"""

_NAME = r"[A-Z](?:_?\d{1,2})?"
_HYPOTHETICAL = re.compile(r"может\s+ли|верно\s+ли|возможно\s+ли|если\s+бы|предполож|неверно",
                           re.I)
# «равнобедренный/равносторонний треугольник ABC» (любой падеж «треугольник»).
_ISO_TRI = re.compile(
    rf"(равнобедренн\w*|равнобок\w*|равносторонн\w*)\s+треугольник\w*\s+({_NAME})({_NAME})({_NAME})(?![A-Za-z0-9_])",
    re.I)
# «с основанием AC» / «с основанием BC» — пара букв (может быть с длиной).
_BASE = re.compile(
    rf"основани\w*\s+({_NAME})({_NAME})(?![A-Za-z0-9_])", re.I)

_TOL_REL = 1e-4          # относительный допуск равенства сторон


def _plain(text: str) -> str:
    """Юникод-индексы A₁ -> A_1, LaTeX-обёртки долой (общий препроцессор)."""
    try:
        from .convexity import _plain as p
        return p(text)
    except Exception:  # noqa: BLE001
        return (text or "").replace("$", " ")


def _point_key(name: str, P: dict) -> str | None:
    for candidate in (name, name.replace("_", ""), re.sub(r"(\d)", r"_\1", name, count=1)):
        if candidate in P:
            return candidate
    return None


def isosceles_failures(text: str, coords: dict) -> list[str]:
    """Независимая проверка «равнобедренного/равностороннего треугольника»
    по координатам: боковые равны (равнобедренный), все стороны равны
    (равносторонний). Основание — явное «с основанием YZ» или пара
    вершин, не совпадающая с боковыми в тексте (AB = BC и т. п. ловит
    STATEMENT_MARK)."""
    fails: list[str] = []
    if not isinstance(coords, dict) or not coords:
        return fails
    plain = _plain(text or "")
    for sentence in re.split(r"(?<=[.;!?])\s+", plain):
        if _HYPOTHETICAL.search(sentence):
            continue
        P = {k: np.asarray(v, dtype=float).reshape(-1)[:2]
             for k, v in coords.items()
             if np.all(np.isfinite(np.asarray(v, dtype=float).reshape(-1)[:2]))}
        for m in _ISO_TRI.finditer(sentence):
            kind = (m[1] or "").lower()
            v1, v2, v3 = m[2].upper(), m[3].upper(), m[4].upper()
            k1, k2, k3 = (_point_key(v, P) for v in (v1, v2, v3))
            if not (k1 and k2 and k3):
                continue          # отсутствие точек ловит семантика имён

            def side(a, b):
                return float(np.linalg.norm(P[b] - P[a]))

            if kind.startswith("равносторон"):
                pairs = [(v1, v2, k1, k2), (v2, v3, k2, k3), (v3, v1, k3, k1)]
                for pa, pb, ka, kb in pairs:
                    s = side(ka, kb)
                    if abs(side(k1, k2) - s) > _TOL_REL * max(1.0, s):
                        fails.append(
                            f"стороны {v1}{v2} и {pa}{pb} не равны "
                            f"({side(k1, k2):.3f} и {s:.3f}) в равностороннем "
                            f"треугольнике {v1}{v2}{v3}")
                        break
                continue
            # равнобедренный: боковые — две стороны от вершины, не лежащей
            # на названном основании; основание по умолчанию — пара,
            # названная в «AB = BC» (STATEMENT_MARK), иначе без проверки.
            bases = _BASE.findall(sentence)
            base_pairs = {tuple(sorted((b[0].upper(), b[1].upper()))) for b in bases}
            # кандидаты боковых: все пары (вершина, вершина) от каждой из
            # трёх вершин; вершина против основания — та, чьи две стороны
            # не являются основанием.
            verts = [v1, v2, v3]
            for apex_i in range(3):
                a1 = verts[(apex_i + 1) % 3]
                a2 = verts[(apex_i + 2) % 3]
                if tuple(sorted((a1, a2))) in base_pairs:
                    apex, arm1, arm2 = verts[apex_i], a1, a2
                    s1, s2 = side(verts[apex_i], a1), side(verts[apex_i], a2)
                    if abs(s1 - s2) > _TOL_REL * max(1.0, s1, s2):
                        fails.append(
                            f"боковые стороны {apex}{arm1} и {apex}{arm2} не равны "
                            f"({s1:.3f} и {s2:.3f}) в равнобедренном "
                            f"треугольнике {v1}{v2}{v3}")
                    break
    return list(dict.fromkeys(fails))


def _wrap_semantic_failures(orig):
    @functools.wraps(orig)
    def semantic_failures(text, plan, coords, *args, **kwargs):
        base = orig(text, plan, coords, *args, **kwargs)
        try:
            if isinstance(base, list):
                return base + [f for f in isosceles_failures(text, coords) if f not in base]
            return base
        except Exception:  # noqa: BLE001
            return base
    semantic_failures._isosceles = True
    semantic_failures._original = orig
    return semantic_failures


def _install_llm_rules(llm_module) -> bool:
    try:
        target = llm_module.SYS_FORMALIZE
        if "43." not in target:
            llm_module.SYS_FORMALIZE = target.rstrip("\n") + "\n" + EXTRA_RULES
        ok = "43." in llm_module.SYS_FORMALIZE
        ok = ok and "ISOSCELES_RULE" in llm_module.SYS_FORMALIZE
        return bool(ok)
    except Exception:  # noqa: BLE001
        return False


def install(semantics_module, llm_module, pipeline_module=None) -> bool:
    """Подключение: обёртка semantic_failures + правило 43 + суффикс кэша."""
    if not ENABLED:
        return False
    try:
        if not getattr(semantics_module.semantic_failures, "_isosceles", False):
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
