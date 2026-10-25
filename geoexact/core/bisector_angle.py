# -*- coding: utf-8 -*-
"""«Биссектриса угла XYZ пересекает ... в точке T»: проверка по координатам.

Прод-ошибка (задача 1, живая генерация 24.10.2026): «В параллелограмме ABCD
биссектриса угла BAD пересекает сторону BC в точке E и диагональ BD в точке F.
Известно, что AB = 6, AD = 10, угол BAD равен 60°». Формализатор не закодировал
биссектрису: чертёж самосогласован, луч AE идёт под ~19° к AB вместо 30°,
BE = 3 вместо BE = AB = 6, «измерено» EF = 1.83 вместо ~3.90 — гейты это
пропустили (score 0.870), неверный чертёж ушёл без предупреждения.

Существующая проверка биссектрис в semantics.py понимает только «биссектриса
CD» (две буквы, треугольник). Здесь — независимая проверка трёхбуквенного
угла «биссектриса угла XYZ ... в точке T» в любой фигуре: углы XYT и TYZ
равны, луч YT внутри угла XYZ (сумма половинок равна целому углу), T лежит
на названной прямой/стороне/диагонали (прод-ошибка №2: E построили на
диагонали BD вместо стороны BC — углы сошлись, прямая нет). Плюс правило 40
формализатора:
каноническое построение bisector_point + line_intersect вместо свободной
точки с angle_eq. GEOEXACT_BISECTOR_ANGLE=0 выключает.
"""
from __future__ import annotations

import functools
import math
import os
import re

import numpy as np

ENABLED = (os.environ.get("GEOEXACT_BISECTOR_ANGLE") or "1").strip().lower() not in ("0", "no", "off")

# Суффикс версии движка: новая проверка текста меняет приёмку чертежей —
# старый дисковый кеш конвейера не подставляется под новую логику.
CACHE_SUFFIX = "+bisectorAngle2"

EXTRA_RULES = """
40. BISECTOR_ANGLE_RULE («биссектриса угла XYZ пересекает сторону/прямую/
    диагональ PQ в точке T»): не задавай T свободной точкой и не полагайся
    только на angle_eq — строй канонически: S = bisector_point(Y, X, Z)
    (точка, где биссектриса угла XYZ встречает прямую XZ), затем
    T = line_intersect(P, Q, Y, S). Если биссектриса пересекает несколько
    прямых, каждую точку пересечения строй как line_intersect от луча YS.
    Точка S — техническая: добавь её в draw.hide_labels.
"""

_NAME = r"[A-Z](?:_?\d{1,2})?"
_HYPOTHETICAL = re.compile(r"может\s+ли|верно\s+ли|возможно\s+ли|если\s+бы|предполож|неверно",
                           re.I)
# «биссектриса угла BAD» (вершина — вторая буква); «внешней биссектрисы»
# пропускаем — у внешней другое свойство (см. external_bisector_point).
_BISECTOR = re.compile(
    r"(внешн\w*\s+)?биссектрис\w*[^.!?]{0,80}?угла\s+([A-Z])([A-Z])([A-Z])(?![A-Za-z0-9_])",
    re.I)
# «... пересекает сторону BC в точке E», «... пересекает её в точке T».
# Слово-название прямой (или местоимение) обязательно: иначе «медианы
# пересекаются в точке M» в том же предложении дало бы ложную проверку M
# против биссектрисы.
_CROSS = re.compile(
    rf"пересек\w*\s+(?:сторону|стороны|диагональ|диагонали|прямую|прямой|луч|луча|отрезок|отрезка|её|ее|его|их)\s*({_NAME})?({_NAME})?\s*(?:[-–—]\s*)?в\s+точке\s+({_NAME})(?![A-Za-z0-9_])",
    re.I)
# «... и диагональ BD в точке F» / «... а прямую PQ — в точке T» (глагол
# опущен во втором однородном сказуемом).
_LISTED = re.compile(
    rf"(?:и|а)\s+(?:сторону|стороны|диагональ|диагонали|прямую|прямой|луч|луча|отрезок|отрезка)\s+({_NAME})({_NAME})(?![A-Za-z0-9_])\s*(?:[-–—]\s*)?в\s+точке\s+({_NAME})(?![A-Za-z0-9_])",
    re.I)

_TOL_DEG = 0.01   # та же жёсткость, что у проверки биссектрис в треугольнике


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


def _angle(u: np.ndarray, v: np.ndarray) -> float:
    """Угол между векторами, градусы [0, 180]."""
    nu, nv = np.linalg.norm(u), np.linalg.norm(v)
    if nu <= 1e-12 or nv <= 1e-12:
        return 0.0
    c = float(np.dot(u, v) / (nu * nv))
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def _sentence_bisectors(sentence: str) -> list[tuple[str, str, str, list[tuple[str | None, str | None, str]]]]:
    """[(arm1, vertex, arm2, [(P, Q, T), ...])] — T на прямой PQ (если названа)."""
    out: list[tuple[str, str, str, list[tuple[str | None, str | None, str]]]] = []
    for m in _BISECTOR.finditer(sentence):
        if m[1]:                      # «внешней биссектрисой» — не проверяем
            continue
        pts = [(m[1].upper() or None, m[2].upper() or None, m[3].upper())
               for m in _CROSS.finditer(sentence)]
        pts += [(m[1].upper(), m[2].upper(), m[3].upper())
                for m in _LISTED.finditer(sentence)]
        out.append((m[2].upper(), m[3].upper(), m[4].upper(), pts))
    return out


def bisector_failures(text: str, coords: dict) -> list[str]:
    """Независимая проверка «биссектриса угла XYZ ... в точке T» по координатам."""
    fails: list[str] = []
    if not isinstance(coords, dict) or not coords:
        return fails
    plain = _plain(text or "")
    for sentence in re.split(r"(?<=[.;!?])\s+", plain):
        if _HYPOTHETICAL.search(sentence):
            continue
        for arm1, vertex, arm2, targets in _sentence_bisectors(sentence):
            P = {k: np.asarray(v, dtype=float).reshape(-1)[:2]
                 for k, v in coords.items()
                 if np.all(np.isfinite(np.asarray(v, dtype=float).reshape(-1)[:2]))}
            v_arm1, v_vertex, v_arm2 = (_point_key(n, P) for n in (arm1, vertex, arm2))
            if not (v_arm1 and v_vertex and v_arm2):
                continue
            va1 = P[v_arm1] - P[v_vertex]
            va2 = P[v_arm2] - P[v_vertex]
            full = _angle(va1, va2)
            for line_p, line_q, name in targets:
                t = _point_key(name, P)
                if t is None:
                    continue          # отсутствие точки ловит семантика имён
                vt = P[t] - P[v_vertex]
                left, right = _angle(va1, vt), _angle(vt, va2)
                if abs(left - right) > _TOL_DEG or abs(left + right - full) > _TOL_DEG:
                    fails.append(
                        f"точка {name} не лежит на биссектрисе угла "
                        f"{arm1}{vertex}{arm2} (делит его как "
                        f"{left:.1f}°/{right:.1f}° вместо {full / 2:.1f}°/{full / 2:.1f}°)")
                    continue
                if line_p and line_q:
                    # точка пересечения обязана лежать на названной прямой
                    lp, lq = _point_key(line_p, P), _point_key(line_q, P)
                    if lp is None or lq is None or np.linalg.norm(P[lq] - P[lp]) <= 1e-12:
                        continue
                    d = P[lq] - P[lp]
                    off = float(np.cross(P[t] - P[lp], d)) / float(np.linalg.norm(d))
                    if abs(off) > 1e-6 * max(1.0, float(np.linalg.norm(d))):
                        fails.append(
                            f"точка {name} не лежит на прямой {line_p}{line_q}, "
                            f"которую пересекает биссектриса угла "
                            f"{arm1}{vertex}{arm2}")
    return list(dict.fromkeys(fails))


def _wrap_semantic_failures(orig):
    def semantic_failures(text, plan, coords, *args, **kwargs):
        fails = list(orig(text, plan, coords, *args, **kwargs))
        try:
            fails += bisector_failures(text, coords)
        except Exception:  # noqa: BLE001
            pass
        return fails
    functools.wraps(orig)(semantic_failures)
    semantic_failures._bisector_angle = True
    semantic_failures._original = orig
    return semantic_failures


def _append_rules(llm_module) -> bool:
    if not ENABLED:
        return False
    try:
        target = llm_module.SYS_FORMALIZE
        if "40." not in target:
            llm_module.SYS_FORMALIZE = target.rstrip("\n") + "\n" + EXTRA_RULES
        ok = "40." in llm_module.SYS_FORMALIZE
        if getattr(llm_module, "SYS_AUX", None) and "40." not in llm_module.SYS_AUX:
            llm_module.SYS_AUX = llm_module.SYS_AUX.rstrip("\n") + "\n" + EXTRA_RULES
        return ok
    except Exception:  # noqa: BLE001
        return False


def install(semantics_module, llm_module, pipeline_module=None) -> bool:
    """Правило в промпты + проверка по тексту + суффикс версии кэша. Повторно — no-op."""
    if not ENABLED:
        return False
    ok = _append_rules(llm_module)
    try:
        if not getattr(semantics_module.semantic_failures, "_bisector_angle", False):
            semantics_module.semantic_failures = _wrap_semantic_failures(
                semantics_module.semantic_failures)
            ok = True
    except Exception:  # noqa: BLE001
        return False
    if pipeline_module is not None:
        ver = getattr(pipeline_module, "ENGINE_VERSION", None)
        if ver and CACHE_SUFFIX not in ver:
            pipeline_module.ENGINE_VERSION = ver + CACHE_SUFFIX
    return ok
