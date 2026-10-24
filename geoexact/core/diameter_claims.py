# -*- coding: utf-8 -*-
"""«Полуокружность/окружность с диаметром XY»: X и Y — концы диаметра и лежат
НА окружности, центр — их середина, отрезок XY виден из точек «на
полуокружности» под прямым углом (Фалес), для полуокружности — по одну
сторону от XY.

Повод (задача 4, живая генерация 24.10.2026): «На полуокружности с диаметром
AD отмечены точки B и C. Точка M — середина отрезка BC. Точка N такова,
что M — середина отрезка AN. Докажите, что прямые BC и DN перпендикулярны.» Формализатор (v4-pro, план FORMALIZE_PLAN #1
в журнале) закодировал «с диаметром AD» как окружность с ЦЕНТРОМ A:
on_circle(B,A,A,D), on_circle(C,A,A,D) — AD стал радиусом, A — центром.
Прямой угол AN⊥BC в M получился автоматически (серединный перпендикуляр из
центра к хорде), но целевое BC⊥DN на чертеже не выполнялось (угол ABD ≈ 73°
вместо 90°), и ни одна проверка этого не называла: «диаметр» не разбирался
нигде, кроме эскиз-фолбэка.

Обёртка без правки ядра (semantics, llm):
- правило 39 в промпты формализатора: центр — середина XY (O=midpoint(X,Y),
  подпись можно скрыть), точки на окружности — on_circle(P,O,O,X), окружность
  рисуется circles=[[O,X]]; конец диаметра — НЕ центр;
- независимая проверка по тексту условия и координатам (обёртка
  semantic_failures): Фалес для точек, названных лежащими на (полу)
  окружности с диаметром XY (угол XPY = 90°); одна сторона прямой XY для
  полуокружности (противоречие «по разные стороны» называется, а не
  молча трактуется как полная окружность); центр нарисованной окружности
  не совпадает с концом диаметра.
GEOEXACT_DIAMETER_CLAIMS=0 выключает.
"""
from __future__ import annotations

import functools
import os
import re

import numpy as np

from .acute_triangle import _strip_latex

ENABLED = (os.environ.get("GEOEXACT_DIAMETER_CLAIMS") or "1").strip().lower() not in ("0", "no", "off")

# Суффикс версии движка: смена проверок текста меняет приёмку чертежей —
# старый дисковый кеш конвейера не подставляется под новую логику (очередь
# задаёт GeoExact REUSE_NOT_BEFORE отдельно).
CACHE_SUFFIX = "+diameterClaims1"

EXTRA_RULES = """
39. DIAMETER_RULE («полуокружность/окружность с диаметром XY»): X и Y лежат НА
    окружности, центр — их середина: O=midpoint(X,Y) (подпись O можно скрыть);
    рисуй окружность в основном слое circles=[[O,X]] и проведи сам отрезок XY
    в draw.segments основного слоя — диаметр назван в условии. Точки P на этой
    окружности задаются как on_circle(P,O,O,X). НЕ делай X центром окружности:
    on_circle(P,X,X,Y) — это окружность радиуса |XY| вокруг X, другая фигура
    (для «полуокружности с диаметром AD» центр не A, а середина AD).
"""

_CIRC = r"(?:полуокружност\w*|окружност\w*|полукруг\w*)"
_NAME = r"[A-Z]\w*"
_LIST = _NAME + r"(?:\s*(?:,|и)\s*" + _NAME + r")*"
_VERBS = r"(?:отмечен\w*|взят\w*|выбран\w*|расположен\w*|леж\w*)"

# «На полуокружности с диаметром AD отмечены точки B и C»
_ON_CIRC = re.compile(
    r"[Нн]а\s+(" + _CIRC + r")\s+с\s+диаметром\s+(" + _NAME + r")\s*(" + _NAME + r")\s+"
    + _VERBS + r"\s+точк\w*\s+(" + _LIST + r")")

# «Точки B и C отмечены на полуокружности с диаметром AD»
_ON_CIRC_REV = re.compile(
    r"[Тт]очк\w*\s+(" + _LIST + r")\s+" + _VERBS + r"\s+на\s+(" + _CIRC + r")"
    r"\s+с\s+диаметром\s+(" + _NAME + r")\s*(" + _NAME + r")")

# Сама фраза «(полу)окружность с диаметром XY» без названных точек —
# для проверки нарисованной окружности (центр не должен быть концом диаметра).
_BARE = re.compile(r"(" + _CIRC + r")\s+с\s+диаметром\s+(" + _NAME + r")\s*(" + _NAME + r")")

_OPPOSITE_SIDES = re.compile(r"по\s+(?:разные|обеих|обе)\s+стороны|в\s+разных\s+полуплоскостях")

# Терпимость чисел: Фалес — косинус угла XPY (угол при точке P на окружности,
# между лучами на концы диаметра); численное решение держит остаток ~1e-7,
# прод-баг давал ~0.3 (угол 73° вместо 90°).
_COS_TOL = 1e-3
_REL_TOL = 1e-5


def _pt(coords, name):
    c = coords.get(name) if isinstance(coords, dict) else None
    if c is None:
        return None
    try:
        return np.array([float(c.x), float(c.y)])
    except AttributeError:
        return np.asarray(c, dtype=float)


def _semi(word: str) -> bool:
    return "полу" in word or "полукруг" in word


def _names(chunk: str) -> list[str]:
    return re.findall(_NAME, chunk)


def diameter_claims(text: str) -> list[tuple[str, str, bool, list[str]]]:
    """[(x, y, полуокружность, точки-на-ней)] из фраз про «диаметр XY»."""
    t = _strip_latex(text)
    out: list[tuple[str, str, bool, list[str]]] = []
    seen: set[tuple[str, str]] = set()
    for m in _ON_CIRC.finditer(t):
        x, y, chunk = m.group(2), m.group(3), m.group(4)
        if (x, y) in seen or x == y:
            continue
        seen.add((x, y))
        out.append((x, y, _semi(m.group(1)), _names(chunk)))
    for m in _ON_CIRC_REV.finditer(t):
        chunk, x, y = m.group(1), m.group(3), m.group(4)
        if (x, y) in seen or x == y:
            continue
        seen.add((x, y))
        out.append((x, y, _semi(m.group(2)), _names(chunk)))
    for m in _BARE.finditer(t):
        x, y = m.group(2), m.group(3)
        if (x, y) not in seen and x != y:
            seen.add((x, y))
            out.append((x, y, _semi(m.group(1)), []))
    return out


def _thales_failure(coords, p: str, x: str, y: str, scale: float) -> str | None:
    P, X, Y = _pt(coords, p), _pt(coords, x), _pt(coords, y)
    if P is None or X is None or Y is None or scale <= 0:
        return None
    a, b = X - P, Y - P
    na, nb = float(np.hypot(*a)), float(np.hypot(*b))
    if na < _REL_TOL * scale or nb < _REL_TOL * scale:
        return None  # вырожденность — не тема этой проверки
    cos = float(a @ b) / (na * nb)
    if abs(cos) <= _COS_TOL:
        return None
    ang = float(np.degrees(np.arccos(np.clip(cos, -1.0, 1.0))))
    return (f"(полу)окружность с диаметром {x}{y}: угол {x}{p}{y} = {ang:.1f}° "
            f"вместо 90° — точка {p} не лежит на этой окружности (Фалес); "
            f"возможно, {x} — центр, а не конец диаметра")


def _center_failure(plan, coords, x: str, y: str, scale: float) -> str | None:
    """Подпись ошибки из прода: окружность «диаметра XY» с центром в конце XY.

    Флажим только если правильной окружности нет, а круг с центром X (или Y)
    через второй конец — нарисован: это ровно след чтения «диаметр XY» как
    «центр X, через Y». Когда правильная окружность (центр — середина XY,
    радиус |XY|/2) нарисована, чужой круг с центром X не трогаем.
    """
    if plan is None or scale <= 0:
        return None
    draw = getattr(plan, "draw", None)
    circles = getattr(draw, "circles", None) or []
    X, Y = _pt(coords, x), _pt(coords, y)
    if X is None or Y is None:
        return None
    mid = (X + Y) / 2
    wrong = None
    for pair in circles:
        if not isinstance(pair, (list, tuple)) or len(pair) < 2:
            continue
        C = _pt(coords, pair[0])
        R = _pt(coords, pair[1])
        if C is None or R is None:
            continue
        r = float(np.hypot(*(R - C)))
        if r <= 0:
            continue
        if (float(np.hypot(*(C - mid))) < 1e-2 * scale
                and abs(r - scale / 2) < 1e-2 * scale):
            return None  # правильная окружность нарисована
        for end, name, other in ((X, x, Y), (Y, y, X)):
            on_other = abs(float(np.hypot(*(other - C))) - r) < 1e-2 * scale
            if float(np.hypot(*(end - C))) < _REL_TOL * scale and on_other:
                wrong = name
    if wrong:
        return (f"(полу)окружность с диаметром {x}{y}: точка {wrong} — конец "
                f"диаметра, а не центр; центр должен быть серединой {x}{y}")
    return None


def _side_failure(coords, points: list[str], x: str, y: str, scale: float,
                  sentence: str) -> str | None:
    """Полуокружность: названные точки — по одну сторону от прямой XY.

    «По разные стороны» вместе со словом «полуокружность» — противоречие в
    самом условии, оно не зависит от координат: называем его раньше анализа
    расположения точек, а не молча трактуем фигуру как полную окружность.
    """
    if not points:
        return None
    if _OPPOSITE_SIDES.search(sentence):
        return (f"условие противоречиво: на одной полуокружности с диаметром "
                f"{x}{y} точки {', '.join(points)} не могут лежать по разные "
                f"стороны от прямой {x}{y}")
    X, Y = _pt(coords, x), _pt(coords, y)
    if X is None or Y is None:
        return None
    d = Y - X
    signs = []
    for p in points:
        P = _pt(coords, p)
        if P is None:
            continue
        cross = float(d[0] * (P - X)[1] - d[1] * (P - X)[0])
        if abs(cross) < 1e-6 * scale * scale:
            continue  # на самой прямой — поймает проверка Фалеса
        signs.append(1 if cross > 0 else -1)
    if len(signs) < 2 or len(set(signs)) == 1:
        return None
    return (f"полуокружность с диаметром {x}{y}: названные на ней точки должны "
            f"лежать по одну сторону от прямой {x}{y}")


def _sentence_at(t: str, pos: int) -> str:
    start = max(t.rfind(end, 0, pos) for end in ".!?") + 1
    stop_candidates = [j for j in (t.find(end, pos) for end in ".!?") if j != -1]
    stop = min(stop_candidates) if stop_candidates else len(t)
    return t[start:stop]


def diameter_failures(text: str, coords, plan=None) -> list[str]:
    if not ENABLED:
        return []
    t = _strip_latex(text)
    fails: list[str] = []
    for x, y, semi, points in diameter_claims(t):
        X, Y = _pt(coords, x), _pt(coords, y)
        scale = float(np.hypot(*(Y - X))) if X is not None and Y is not None else 0.0
        for p in points:
            f = _thales_failure(coords, p, x, y, scale)
            if f:
                fails.append(f)
        if semi:
            m = re.search(r"диаметром\s*" + re.escape(x) + r"\s*" + re.escape(y), t)
            sentence = _sentence_at(t, m.start()) if m else t
            f = _side_failure(coords, points, x, y, scale, sentence)
            if f:
                fails.append(f)
        f = _center_failure(plan, coords, x, y, scale)
        if f:
            fails.append(f)
    return fails


def _wrap_semantic_failures(orig):
    @functools.wraps(orig)
    def semantic_failures(text, plan, coords, *args, **kwargs):
        fails = orig(text, plan, coords, *args, **kwargs)
        try:
            extra = diameter_failures(text, coords, plan)
        except Exception:
            extra = []
        if extra:
            return list(fails) + extra
        return fails

    semantic_failures._diameter_claims = True
    semantic_failures._original = orig
    return semantic_failures


def _wrap_statement_requirements(orig):
    """«Диаметр XY» — названный в условии отрезок: он обязан быть проведён.

    named_segments знает «отрезок/медиана/хорда/диагональ/прямая», но не
    «диаметр» — без обёртки слой «проведено и отмечено» (complete_statement_display)
    не проводит XY и не предупреждает. Дополняем требования — тогда конвейер
    сам проведёт отрезок с пометкой STATEMENT_DRAW или честно предупредит.
    """
    @functools.wraps(orig)
    def statement_requirements(text):
        req = orig(text)
        try:
            t = _strip_latex(text or "")
            extra = []
            for x, y, _semi, _pts in diameter_claims(t):
                if x != y:
                    extra.append((f"{x}{y}", (x, y)))
            if extra:
                req = dict(req)
                segs = list(req.get("segments") or [])
                have = {tuple(p) for _, p in segs}
                for label, pair in extra:
                    if tuple(pair) not in have:
                        segs.append((label, pair))
                req["segments"] = segs
        except Exception:
            pass
        return req

    statement_requirements._diameter_claims = True
    statement_requirements._original = orig
    return statement_requirements


def _append_rules(llm_module) -> bool:
    if not ENABLED:
        return False
    ok = False
    try:
        target = llm_module.SYS_FORMALIZE
        if "39." not in target:
            llm_module.SYS_FORMALIZE = target.rstrip("\n") + "\n" + EXTRA_RULES
        if getattr(llm_module, "SYS_AUX", None) and "39." not in llm_module.SYS_AUX:
            llm_module.SYS_AUX = llm_module.SYS_AUX.rstrip("\n") + "\n" + EXTRA_RULES
        ok = "39." in llm_module.SYS_FORMALIZE
    except Exception:
        ok = False
    return ok


def install(semantics_module, llm_module, pipeline_module=None,
            statement_module=None) -> bool:
    ok = _append_rules(llm_module)
    try:
        if not getattr(semantics_module.semantic_failures, "_diameter_claims", False):
            semantics_module.semantic_failures = _wrap_semantic_failures(
                semantics_module.semantic_failures)
    except Exception:
        return False
    if statement_module is not None:
        try:
            if not getattr(statement_module.statement_requirements,
                           "_diameter_claims", False):
                statement_module.statement_requirements = _wrap_statement_requirements(
                    statement_module.statement_requirements)
        except Exception:
            pass
    if pipeline_module is not None:
        try:
            ver = getattr(pipeline_module, "ENGINE_VERSION", None)
            if ver and CACHE_SUFFIX not in ver:
                pipeline_module.ENGINE_VERSION = ver + CACHE_SUFFIX
        except Exception:
            pass
    return ok
