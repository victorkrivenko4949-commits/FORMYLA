# -*- coding: utf-8 -*-
"""«Трапеция ABCD (с основаниями BC и AD)»: проверка по координатам.

Прод-ошибка (баг-хант 25.10.2026): «В равнобедренной трапеции ABCD с
основаниями BC и AD известно, что BC = 6, AD = 16, боковая сторона
AB = CD = 13. Диагонали AC и BD пересекаются в точке O. Найдите BO».
Формализатор собрал нерешаемую систему ограничений — конвейер честно ушёл
в схематичный фолбэк (FALLBACK_FROM: 6-solve RESIDUAL_TOO_HIGH), но
неверные пропорции трапеции (BC:AD = 1:2 вместо 3:8) ушли бы незамеченными,
если бы фолбэк не сработал: параллельность оснований никто не проверял.

Здесь — независимая проверка по координатам: у «трапеции ABCD» основания
AD ∥ BC (стандартная нотация; явные «основания XY и ZW» имеют приоритет),
у «равнобедренной трапеции» боковые стороны равны. Плюс правило 42
формализатора: трапеция кодируется свободными точками + parallel и dist,
а не углами. GEOEXACT_TRAPEZOID=0 выключает.
"""
from __future__ import annotations

import functools
import math
import os
import re

import numpy as np

ENABLED = (os.environ.get("GEOEXACT_TRAPEZOID") or "1").strip().lower() not in ("0", "no", "off")

# Суффикс версии движка: новая проверка текста меняет приёмку чертежей.
CACHE_SUFFIX = "+trapezoid1"

EXTRA_RULES = """
42. TRAPEZOID_RULE («трапеция ABCD с основаниями BC и AD»): не кодируй
    трапецию углами и не выдумывай вспомогательные точки — сделай все четыре
    вершины free_point и задай ограничения: parallel([A,D,B,C]) для оснований
    AD ∥ BC (порядок аргументов: два конца первого основания, затем два конца
    второго), dist для длин оснований и dist_eq([A,B,C,D]) для равных боковых
    сторон («равнобедренная трапеция»: |AB| = |CD|). Диагонали и точки
    пересечения — как обычно, line_intersect. Вершин свободных точек с
    on_segment для сторон трапеции не нужно: параллельность и длины уже
    всё определяют. Если solve падает по невязке — проверь, что не задал
    лишний угол или лишнюю dist сверх независимых данных.
"""

_NAME = r"[A-Z](?:_?\d{1,2})?"
_HYPOTHETICAL = re.compile(r"может\s+ли|верно\s+ли|возможно\s+ли|если\s+бы|предполож|неверно",
                           re.I)
# «трапеция ABCD», «трапеции ABCD», «трапецией ABCD» — четыре вершины подряд.
_TRAPEZOID = re.compile(
    rf"трапец\w*\s+({_NAME})({_NAME})({_NAME})({_NAME})(?![A-Za-z0-9_])", re.I)
# «с основаниями BC и AD», «основания BC и AD», «с основанием BC» (одно).
_BASES = re.compile(
    rf"основани\w*\s+({_NAME})({_NAME})(?:\s+и\s+({_NAME})({_NAME}))?(?![A-Za-z0-9_])",
    re.I)

_TOL_PAR_DEG = 0.01    # жёсткость как у проверки биссектрис
_TOL_REL = 1e-4        # относительный допуск равенства боковых сторон


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


def _pair_key(seg: tuple[str, str], P: dict) -> tuple[str, str] | None:
    a, b = _point_key(seg[0], P), _point_key(seg[1], P)
    if a is None or b is None or a == b:
        return None
    return (a, b)


def _line_dev_deg(u: np.ndarray, w: np.ndarray) -> float:
    """Отклонение направлений двух прямых от параллельности, градусы [0, 90]."""
    nu, nw = np.linalg.norm(u), np.linalg.norm(w)
    if nu <= 1e-12 or nw <= 1e-12:
        return 90.0
    c = abs(float(np.dot(u, w)) / (nu * nw))
    return math.degrees(math.asin(max(0.0, min(1.0, (1.0 - c * c) ** 0.5))))


def _trapezoids(sentence: str) -> list[tuple[str, str, str, str]]:
    """Вершины всех «трапеций ABCD» в предложении."""
    return [(m[1].upper(), m[2].upper(), m[3].upper(), m[4].upper())
            for m in _TRAPEZOID.finditer(sentence)]


def _named_bases(sentence: str) -> list[tuple[str, str, str, str]]:
    """Явно названные основания: [(P1, Q1, P2, Q2)] (второе может отсутствовать)."""
    out = []
    for m in _BASES.finditer(sentence):
        p1, q1 = m[1].upper(), m[2].upper()
        p2, q2 = (m[3].upper(), m[4].upper()) if m[3] and m[4] else (None, None)
        out.append((p1, q1, p2, q2))
    return out


def trapezoid_failures(text: str, coords: dict) -> list[str]:
    """Независимая проверка «трапеции» по координатам: параллельность оснований,
    равенство боковых сторон у «равнобедренной»."""
    fails: list[str] = []
    if not isinstance(coords, dict) or not coords:
        return fails
    plain = _plain(text or "")
    for sentence in re.split(r"(?<=[.;!?])\s+", plain):
        if _HYPOTHETICAL.search(sentence):
            continue
        quads = _trapezoids(sentence)
        if not quads:
            continue
        P = {k: np.asarray(v, dtype=float).reshape(-1)[:2]
             for k, v in coords.items()
             if np.all(np.isfinite(np.asarray(v, dtype=float).reshape(-1)[:2]))}
        iso = re.search(r"равнобедренн\w*|равнобок\w*", sentence, re.I)
        bases_explicit = _named_bases(sentence)
        for v1, v2, v3, v4 in quads:
            # Основания: явные имена приоритетны; иначе стандартная нотация
            # ABCD: AD ∥ BC. Явное одно основание дополняется противоположной
            # парой вершин.
            pairs: list[tuple[tuple[str, str], tuple[str, str]]] = []
            named = [p for p in bases_explicit
                     if {p[0], p[1]} <= {v1, v2, v3, v4}
                     or (p[2] and {p[2], p[3]} <= {v1, v2, v3, v4})]
            if named:
                p1, q1, p2, q2 = named[0]
                b1 = (p1, q1)
                if p2:
                    b2 = (p2, q2)
                else:
                    rest = [v for v in (v1, v2, v3, v4)
                            if v not in (p1, q1)]
                    b2 = (rest[0], rest[1])
                pairs = [(b1, b2)]
            else:
                pairs = [((v1, v4), (v2, v3))]
            for (bp, bq), (cp, cq) in pairs:
                B, C = _pair_key((bp, bq), P), _pair_key((cp, cq), P)
                if B is None or C is None:
                    continue          # отсутствие точек ловит семантика имён
                dev = _line_dev_deg(P[B[1]] - P[B[0]], P[C[1]] - P[C[0]])
                if dev > _TOL_PAR_DEG:
                    fails.append(
                        f"основания {bp}{bq} и {cp}{cq} трапеции "
                        f"{v1}{v2}{v3}{v4} не параллельны "
                        f"(отклонение {dev:.2f}°)")
                if iso:
                    L1, L2 = _pair_key((v1, v2), P), _pair_key((v3, v4), P)
                    if L1 is None or L2 is None:
                        continue
                    l1 = float(np.linalg.norm(P[L1[1]] - P[L1[0]]))
                    l2 = float(np.linalg.norm(P[L2[1]] - P[L2[0]]))
                    if abs(l1 - l2) > _TOL_REL * max(1.0, max(l1, l2)):
                        fails.append(
                            f"боковые стороны {v1}{v2} и {v3}{v4} не равны "
                            f"({l1:.3f} и {l2:.3f}) в равнобедренной трапеции")
    return list(dict.fromkeys(fails))


def _wrap_semantic_failures(orig):
    @functools.wraps(orig)
    def semantic_failures(text, plan, coords, *args, **kwargs):
        base = orig(text, plan, coords, *args, **kwargs)
        try:
            if isinstance(base, list):
                return base + [f for f in trapezoid_failures(text, coords) if f not in base]
            return base
        except Exception:  # noqa: BLE001
            return base
    semantic_failures._trapezoid = True
    semantic_failures._original = orig
    return semantic_failures


def _install_llm_rules(llm_module) -> bool:
    try:
        target = llm_module.SYS_FORMALIZE
        if "42." not in target:
            llm_module.SYS_FORMALIZE = target.rstrip("\n") + "\n" + EXTRA_RULES
        ok = "42." in llm_module.SYS_FORMALIZE
        ok = ok and "TRAPEZOID_RULE" in llm_module.SYS_FORMALIZE
        return bool(ok)
    except Exception:  # noqa: BLE001
        return False


def install(semantics_module, llm_module, pipeline_module=None) -> bool:
    """Подключение: обёртка semantic_failures + правило 42 + суффикс кэша."""
    if not ENABLED:
        return False
    try:
        if not getattr(semantics_module.semantic_failures, "_trapezoid", False):
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
