# -*- coding: utf-8 -*-
"""Качественные условия чертежа: «остроугольный», «диаметрально противоположная»,
«точка лежит на отрезке/стороне».

Повод (задача 2, живая генерация 23.10.2026): «Дан остроугольный треугольник
ABC. На его описанной окружности отмечена точка D, диаметрально
противоположная вершине A. Точки X и Y на стороне BC таковы, что BX = XD и
CY = YD (точка X лежит на отрезке BY)». Прод-чертёж вышел прямоугольным
(угол B = 90° установлен по fallback-SVG: антипод A совпал с C, и весь
чертёж выродился — C, D, X, Y слиплись в одну точку). Исходный план
формализатора не сохранён, поэтому «острота не была закодирована» — гипотеза,
не установленная причина. Автопроверка тогда честно сказала «равенства не
выполняются [APPROXIMATE]», но корневая причина — прямоугольность — нигде
не называлась.

Обёртка без правки ядра (semantics, llm):
- правило 37 в промпты формализатора: качественные условия НЕ превращаются в
  выдуманные числа (остроту движок обеспечивает отбором решений), антипод —
  circumcenter + reflect_point, «равноудалённая точка на прямой» —
  серединный перпендикуляр;
- независимые проверки по тексту условия (обёртка semantic_failures):
  острота треугольника, антипод на описанной окружности, принадлежность
  отрезку/стороне. Решения, не прошедшие проверки, исключаются из «верных» —
  конвейер показывает верный чертёж или честно называет нарушенную фразу.
GEOEXACT_ACUTE_TRIANGLE=0 выключает.
"""
from __future__ import annotations

import functools
import os
import re

import numpy as np

ENABLED = (os.environ.get("GEOEXACT_ACUTE_TRIANGLE") or "1").strip().lower() not in ("0", "no", "off")

MARK = "ACUTE_CONFIG"        # признак того, что правило уже дописано

EXTRA_RULES = """
37. ACUTE_CONFIG: качественные условия не превращай в выдуманные числа:
    «остроугольный треугольник» движок обеспечивает сам — независимой проверкой
    углов и отбором решений. НЕ добавляй angle-ограничения с придуманными
    значениями — ни первым шагом, ни после отказа: повторная формализация
    сохраняет исходные условия. «Точка D диаметрально противоположна вершине A на описанной
    окружности ABC» → O = circumcenter(A,B,C), D = reflect_point(A,O).
    «Точка P на прямой l такова, что MP = PN» → P — пересечение l с серединным
    перпендикуляром MN: S = midpoint(M,N), T = perp_point(S,M,N,1),
    P = line_intersect(<две точки прямой l>, S, T). Так конструируй, а не
    подбирай ограничениями: конструкция точна, ограничение приближённо.
"""


def _strip_latex(text: str) -> str:
    r"""\(ABC\) → ABC: имена точек из условия приходят в LaTeX-обёртке."""
    return re.sub(r"\\\(\s*([^)]*?)\s*\\\)", lambda m: re.sub(r"\s+", "", m.group(1)), text)


def _pt(coords, name):
    return np.asarray(coords[name], dtype=float)


def _angle_at(coords, vertex, other1, other2) -> float:
    v = _pt(coords, vertex)
    a = _pt(coords, other1) - v
    b = _pt(coords, other2) - v
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    if na < 1e-12 or nb < 1e-12:
        return float("nan")
    cosv = float(np.clip(a @ b / (na * nb), -1.0, 1.0))
    import math
    return math.degrees(math.acos(cosv))


def acute_failures(text: str, coords: dict) -> list[str]:
    """«Остроугольный треугольник ABC» — все углы меньше 90°."""
    t = _strip_latex(text)
    fails: list[str] = []
    for m in re.finditer(r"[Оо]строугольн\w*\s+треугольник\w*\s+([A-Z]{3})", t):
        a, b, c = m.group(1)
        if not all(p in coords for p in (a, b, c)):
            fails.append(f"в плане отсутствует остроугольный треугольник {a}{b}{c}")
            continue
        for v, o1, o2 in ((a, b, c), (b, a, c), (c, a, b)):
            ang = _angle_at(coords, v, o1, o2)
            if ang != ang:              # nan — слепленные точки
                fails.append(f"треугольник {a}{b}{c} вырожден (угол {v} не определён)")
            elif ang >= 90.0 - 1e-6:
                fails.append(f"треугольник {a}{b}{c} не остроугольный: угол {v} = {ang:.1f}°")
    return fails


def antipode_failures(text: str, coords: dict) -> list[str]:
    """«Точка D диаметрально противоположна вершине A» на описанной окружности
    опорного треугольника: D = 2O - A."""
    t = _strip_latex(text)
    fails: list[str] = []
    tri = re.search(r"[Оо]строугольн\w*\s+треугольник\w*\s+([A-Z]{3})", t) \
        or re.search(r"[Тт]реугольник\w*\s+([A-Z]{3})", t)
    if not tri:
        return fails
    ref = tri.group(1)
    for m in re.finditer(
            r"[Тт]очк[аи]\s+([A-Z]\w*)\s*,?\s*диаметрально\s+противоположн\w*\s+вершин\w*\s+([A-Z]\w*)", t):
        d, a = m.group(1), m.group(2)
        need = [d, a] + list(ref)
        if not all(p in coords for p in need):
            continue
        try:
            from .constructions import _circumcenter
            O = _circumcenter(_pt(coords, ref[0]), _pt(coords, ref[1]), _pt(coords, ref[2]))
        except Exception:              # noqa: BLE001 - вырожденный опорный треугольник
            fails.append(f"не удалось построить центр описанной окружности {ref}: треугольник вырожден")
            continue
        A, D = _pt(coords, a), _pt(coords, d)
        scale = max(float(np.linalg.norm(A - O)), 1e-9)
        if float(np.linalg.norm(D - (2.0 * O - A))) > 1e-5 * scale:
            fails.append(f"точка {d} не диаметрально противоположна вершине {a}"
                         f" на описанной окружности {ref}")
    return fails


def _segment_geometry(coords, p, u, v):
    """(t, длина, отклонение) точки p относительно прямой UV."""
    P, U, V = _pt(coords, p), _pt(coords, u), _pt(coords, v)
    w = V - U
    den = float(w @ w)
    if den < 1e-20:
        return None, 0.0, float("inf")
    length = den ** 0.5
    tt = float((P - U) @ w) / den
    dev = float(np.linalg.norm(P - (U + tt * w)))
    return tt, length, dev


def _membership_failure(coords, p, u, v) -> str | None:
    """Принадлежность ЗАМКНУТОМУ отрезку [u, v]: параметр в [0, 1] и малое
    перпендикулярное отклонение. Концы отрезка ДОПУСТИМЫ — порядок и
    различимость точек проверяет отдельная order_failures."""
    tt, length, dev = _segment_geometry(coords, p, u, v)
    if dev > 1e-6 * length or tt < -1e-6 or tt > 1.0 + 1e-6:
        return f"точка {p} не лежит на отрезке {u}{v}"
    return None


def order_failures(text: str, coords: dict) -> list[str]:
    """Различимость и порядок точек — ТОЛЬКО для связанной пары фраз этой
    конфигурации: «Точки X и Y на стороне BC» + «точка X лежит на отрезке BY»
    (сегмент соединяет конец стороны и другую точку перечисления). Такая пара
    задаёт строгий порядок B-X-Y-C без слипания. По отдельности ни одна из
    фраз порядка не задаёт: «точка P лежит на отрезке AB» допускает P=A,
    «точки X и Y на стороне BC» допускают любой их порядок вдоль стороны."""
    t = _strip_latex(text)
    side = re.search(r"[Тт]очки\s+([A-Z]\w*)\s+и\s+([A-Z]\w*)\s+на\s+стороне\s+([A-Z])([A-Z])(?![A-Za-z0-9])", t)
    if not side:
        return []                       # нет перечисления на стороне — порядка нет
    p1, p2, u, v = side.groups()
    if not all(n in coords for n in (p1, p2, u, v)):
        return []
    seg = None
    for m in re.finditer(r"[Тт]очк[аи]\s+([A-Z]\w*)\s+лежит\s+на\s+отрезке\s+([A-Z])([A-Z])(?![A-Za-z0-9])", t):
        p, s1, s2 = m.groups()
        if p not in (p1, p2) or p in (s1, s2):
            continue
        pair = {s1, s2}
        if s1 in (u, v) and s2 in (p1, p2) and s1 != s2:
            seg = (p, s1, s2)
            break
        if s2 in (u, v) and s1 in (p1, p2) and s1 != s2:
            seg = (p, s2, s1)
            break
    if seg is None:
        return []                       # нет связанной фразы порядка — не проверяем
    p, endpoint, other = seg             # p строго внутри [endpoint, other]
    if endpoint not in (u, v) or other not in (p1, p2):
        return []
    fails: list[str] = []

    def _collapsed(pt, a, b):
        tt, length, _ = _segment_geometry(coords, pt, a, b)
        if tt is None:
            return True
        P, A_, B_ = _pt(coords, pt), _pt(coords, a), _pt(coords, b)
        return (float(np.linalg.norm(P - A_)) < 1e-6 * length
                or float(np.linalg.norm(P - B_)) < 1e-6 * length)

    if _collapsed(p, endpoint, other):
        fails.append(f"точка {p} совпала с концом отрезка {endpoint}{other}")
    # направление порядка — из СВЯЗАННОЙ фразы (endpoint → far), а не из
    # порядка перечисления и не из записи стороны (BC vs CB)
    far = v if endpoint == u else u
    for pt in (p, other):
        if _collapsed(pt, u, v):
            fails.append(f"точка {pt} совпала с концом стороны {u}{v}")
    tp, _, _ = _segment_geometry(coords, p, endpoint, far)
    to, _, _ = _segment_geometry(coords, other, endpoint, far)
    if tp is not None and to is not None and tp >= to:
        fails.append(f"нарушен порядок точек на стороне {u}{v}: "
                     f"ожидался {endpoint}-{p}-{other}-{far}")
    return fails


def between_failures(text: str, coords: dict) -> list[str]:
    """«Точка X лежит на отрезке BY» и «Точки X и Y на стороне BC»:
    принадлежность ЗАМКНУТОМУ отрезку (концы допустимы)."""
    t = _strip_latex(text)
    fails: list[str] = []
    for m in re.finditer(r"[Тт]очк[аи]\s+([A-Z]\w*)\s+лежит\s+на\s+отрезке\s+([A-Z])([A-Z])(?![A-Za-z0-9])", t):
        p, u, v = m.groups()
        if not all(n in coords for n in (p, u, v)):
            continue
        msg = _membership_failure(coords, p, u, v)
        if msg:
            fails.append(msg)
    for m in re.finditer(r"[Тт]очки\s+([A-Z]\w*)\s+и\s+([A-Z]\w*)\s+на\s+стороне\s+([A-Z])([A-Z])(?![A-Za-z0-9])", t):
        p1, p2, u, v = m.groups()
        for p in (p1, p2):
            if not all(n in coords for n in (p, u, v)):
                continue
            if _membership_failure(coords, p, u, v):
                fails.append(f"точка {p} не лежит на стороне {u}{v}")
    return fails


def _failures(text: str, coords: dict) -> list[str]:
    out: list[str] = []
    for fn in (acute_failures, antipode_failures, between_failures, order_failures):
        try:
            out.extend(fn(text, coords))
        except Exception:              # noqa: BLE001 - проверка не должна валить конвейер
            pass
    return out


def _wrap_semantic_failures(orig):
    def semantic_failures(text, plan, coords, *args, **kwargs):
        fails = orig(text, plan, coords, *args, **kwargs)
        try:
            extra = _failures(text, coords)
        except Exception:              # noqa: BLE001
            extra = []
        return list(fails) + extra if extra else fails
    # functools.wraps копирует __dict__ внутренней обёртки: маркеры других
    # модулей (_radius_claims, …) не теряются на внешнем слое цепочки.
    functools.wraps(orig)(semantic_failures)
    semantic_failures._acute_triangle = True
    semantic_failures._original = orig
    return semantic_failures


def _append_rules(llm_module) -> bool:
    base = getattr(llm_module, "SYS_FORMALIZE", None)
    aux = getattr(llm_module, "SYS_AUX", None)
    if not isinstance(base, str) or MARK in base:
        return False
    llm_module.SYS_FORMALIZE = base.rstrip() + "\n" + EXTRA_RULES.rstrip() + "\n"
    if isinstance(aux, str):
        if aux.startswith(base):
            llm_module.SYS_AUX = llm_module.SYS_FORMALIZE + aux[len(base):]
        elif MARK not in aux:
            llm_module.SYS_AUX = aux.rstrip() + "\n" + EXTRA_RULES.rstrip() + "\n"
    return True


def install(semantics_module, llm_module) -> bool:
    """Правило в промпты + независимые проверки по тексту. Повторно — no-op."""
    if not ENABLED:
        return False
    done = _append_rules(llm_module)
    orig = getattr(semantics_module, "semantic_failures", None)
    if orig is not None and not getattr(orig, "_acute_triangle", False):
        semantics_module.semantic_failures = _wrap_semantic_failures(orig)
        done = True
    return done
