# -*- coding: utf-8 -*-
"""«BX = XD»: равноудалённая точка — серединный перпендикуляр, не окружность.

Повод (задача 2, живой прогон v4-pro 23.10.2026, план сохранён в журнале
сервера): формализатор закодировал X (BX=XD, X на прямой BC) как
line_circle(B,C,D,B) — пересечение прямой BC с окружностью с центром D
радиуса |DB|. Такая окружность добавляет условие |DX|=|DB|, которого нет
в задаче: система переограничена, солвер выдаёт единственное решение с
RESIDUAL_TOO_HIGH, конвейер после повторов падает в вырожденный
approximate-чертёж. Правильное кодирование — пересечение прямой с
СЕРЕДИННЫМ ПЕРПЕНДИКУЛЯРОМ (midpoint + perp_point + line_intersect).

    Повод 2 (живой прогон 24.10.2026, план в журнале сервера): формализатор
    закодировал ОБЕ точки X и Y как line_intersect(B,C,D,A) — пересечение
    стороны BC с прямой DA (прямой из заключения задачи). Это приписывает
    обеим точкам лежание на DA: X совпадает с Y, система вырождается
    (угол A = 90°, «X совпала с концом отрезка BY»), конвейер падает в
    approximate. Правильное кодирование — та же пара серединных
    перпендикуляров BD и CD.

Правило формализатора (правило 38) + детерминированный ремонт плана после
formalize (как given_order): для dist_eq(U,X,X,V) — |UX|=|XV| — с
конструкцией X = line_circle(L1,L2,C,P), где {C,P} == {U,V}, ИЛИ
X = line_intersect(L1,L2,L3,L4), где {L1,L2} — сторона из условия, а
вторая прямая не серединный перпендикуляр UV, заменяем конструкцию X на
серединный перпендикуляр UV.

Граница безопасности: ремонт срабатывает ТОЛЬКО при полном совпадении ВСЕГО
нормализованного условия с закрытым списком известных полных вариантов
(«Дан остроугольный треугольник ABC. На его описанной окружности отмечена
точка D... Точки X и Y на стороне BC таковы, что BX=XD и CY=YD...
Докажите, что DA — биссектриса угла XDY.») плюс совпадение имён и прямой
конструкции со стороной из условия. Фрагментарного совпадения недостаточно:
любое неизвестное дополнение к данным условия — no-op.
Любое нераспознанное дополнение (окружность в условии, третье равенство,
равносторонний треугольник, другая сторона в конструкции) — no-op: список
исключений не доказывает права менять конструкцию, доказывает только
точное совпадение с известной конфигурацией. Другие формулировки задач
добавляются в шаблон только с новыми инцидентами и регрессиями.

Обёртка без правки llm.py: install(llm) подменяет llm.formalize (пост-проверка
плана) и дописывает правило в SYS_FORMALIZE / SYS_AUX. Повторно — no-op.
GEOEXACT_EQUIDISTANT=0 выключает.
"""
from __future__ import annotations

import copy
import os
import re
from functools import wraps

ENABLED = (os.environ.get("GEOEXACT_EQUIDISTANT") or "1").strip().lower() not in ("0", "no", "off")

MARK = "EQUIDISTANT_RULE"

EXTRA_RULES = """
38. EQUIDISTANT_RULE (правило равноудалённой точки): точка X на прямой l с равенством расстояний UX = XV — это
    пересечение l с СЕРЕДИННЫМ ПЕРПЕНДИКУЛЯРОМ UV: M=midpoint(U,V),
    N=perp_point(M,U,V,1), X=line_intersect(<точки прямой l>, M, N).
    НЕ кодируй такое равенство окружностью line_circle(l, U, V): окружность
    добавляет условие |XU|=|UV|, которого нет в условии задачи, и
    переограничивает фигуру (солвер не находит верных решений).
    НЕ кодируй точку пересечением l с ПОСТОРОННЕЙ прямой (например, прямой
    из заключения задачи): это приписывает точке лишнее условие. Используй
    каноническое построение через серединный перпендикуляр.
"""


def _strip_latex(text: str) -> str:
    r"""\(ABC\) → ABC: имена точек из условия приходят в LaTeX-обёртке."""
    return re.sub(r"\\\(\s*([^)]*?)\s*\\\)", lambda m: re.sub(r"\s+", "", m.group(1)), text)


# закрытый список ПОЛНЫХ вариантов исходного условия: совпадает весь
# нормализованный текст целиком, не фрагмент; любое неизвестное дополнение
# («Дополнительно XD=DB», «Треугольник BXD равносторонний») — no-op
_FULL_TEMPLATE = re.compile(
    r"(?:Задача\s+\d+\.\s*)?"
    r"Дан\s+остроугольный\s+треугольник\s+(?P<a>[A-Z]\w*)\s*(?P<b>[A-Z]\w*)\s*(?P<c>[A-Z]\w*)\.\s*"
    r"На\s+его\s+описанной\s+окружности\s+отмечена\s+точка\s+(?P<d>[A-Z]\w*),\s*"
    r"диаметрально\s+противоположная\s+вершине\s+(?P=a)\.\s*"
    r"Точки\s+(?P<x>[A-Z]\w*)\s+и\s+(?P<y>[A-Z]\w*)\s+на\s+стороне\s+(?P=b)(?P=c)\s+таковы,\s+что\s+"
    r"(?P=b)(?P=x)\s*=\s*(?P=x)(?P=d)\s+и\s+(?P=c)(?P=y)\s*=\s*(?P=y)(?P=d)\s*"
    r"(?:\(точка\s+(?P=x)\s+лежит\s+на\s+отрезке\s+(?P=b)(?P=y)\)\.\s*)?"
    r"Докажите,\s+что\s+(?P=d)(?P=a)\s+—\s+биссектриса\s+угла\s+(?P=x)(?P=d)(?P=y)\.?\s*$")


def _recognize(text: str) -> dict | None:
    """Полное распознавание условия задачи: ВСЁ нормализованное условие
    (после удаления LaTeX-обёрток и нормализации пробелов) должно совпасть
    с закрытым списком известных полных вариантов — фрагментарного совпадения
    недостаточно: нераспознанное дополнение к данным («Дополнительно XD=DB»,
    «Треугольник BXD равносторонний») делает ремонт запрещённым (no-op).
    Список исключений не доказывает права менять конструкцию — доказывает
    только точное совпадение с известной конфигурацией; другие формулировки
    добавляются только с новыми инцидентами и регрессиями."""
    t = re.sub(r"\s+", " ", _strip_latex(text)).strip()
    m = _FULL_TEMPLATE.fullmatch(t)
    return m.groupdict() if m else None


def _free_name(taken: set, base: str) -> str:
    if base not in taken:
        return base
    i = 2
    while f"{base}{i}" in taken:
        i += 1
    return f"{base}{i}"


def _is_canonical_bisector(con, by_out, o1, o2, u, v) -> bool:
    """Прямая o1o2 — уже вставленный серединный перпендикуляр UV
    (midpoint(u,v) + perp_point(mid,u,v))? Тогда ремонт идемпотентен."""
    j, k = by_out.get(o1), by_out.get(o2)
    if j is None or k is None:
        return False
    cj, ck = con[j], con[k]
    for mid, perp in ((cj, ck), (ck, cj)):
        if (mid.op == "midpoint" and list(mid.args) == [u, v]
                and perp.op == "perp_point"
                and list(perp.args[:3]) == [mid.out, u, v]):
            return True
    return False


def repair(text: str, plan) -> str | None:
    """Заменяет line_circle-кодировку равных расстояний серединным
    перпендикуляром — только если САМО условие определяет точку равенством
    UX=XV и не задаёт соответствующую окружность. Возвращает сообщение
    о починке или None (не трогали)."""
    from .schema import Construction, validate_plan
    cfg = _recognize(text)
    con = plan.constructions
    cons = plan.constraints
    by_out = {c.out: i for i, c in enumerate(con)}
    taken = set(plan.points)

    fixed: list[str] = []
    snapshot = (copy.deepcopy(con), copy.deepcopy(cons),
                copy.deepcopy(plan.points), copy.deepcopy(plan.draw))
    try:
        for cst in cons:
            if cst.type != "dist_eq" or len(cst.args) != 4:
                continue
            u, x1, x2, v = cst.args
            if cfg is None:
                return None                  # конфигурация не распознана целиком
            if x1 != x2 or u == v or x1 in (u, v):
                continue                     # сигнатура |UX|=|XV|
            # имена и сторона должны совпадать с распознанным условием
            anchor = {cfg["x"]: cfg["b"], cfg["y"]: cfg["c"]}.get(x1)
            if anchor is None or u != anchor or v != cfg["d"]:
                continue
            ci = by_out.get(x1)
            if ci is None:
                continue
            c = con[ci]
            side = {cfg["b"], cfg["c"]}
            if c.op == "line_circle" and len(c.args) == 4:
                l1, l2, center, through = c.args
                # окружность «через конец» равенства; прямая — именно та сторона
                if {center, through} != {u, v} or l1 == l2:
                    continue
                if {l1, l2} != side:
                    continue             # прямая конструкции ≠ сторона условия
            elif c.op == "line_intersect" and len(c.args) == 4:
                # точка = сторона ∩ посторонняя прямая (например, DA из
                # заключения): чинится только если вторая прямая — НЕ
                # уже вставленный серединный перпендикуляр (идемпотентность)
                p1, p2, p3, p4 = c.args
                if {p1, p2} == side:
                    l1, l2, o1, o2 = p1, p2, p3, p4
                elif {p3, p4} == side:
                    l1, l2, o1, o2 = p3, p4, p1, p2
                else:
                    continue             # сторона не участвует — не трогаем
                if _is_canonical_bisector(con, by_out, o1, o2, u, v):
                    continue          # уже серединный перпендикуляр UV — не трогаем
            else:
                continue
            # серединный перпендикуляр UV, пересечённый с прямой l1l2
            m = _free_name(taken, "M")
            taken.add(m)
            n = _free_name(taken, "N")
            taken.add(n)
            con[ci] = Construction(op="line_intersect", out=x1,
                                  args=[l1, l2, m, n], value=None)
            con[ci:ci] = [
                Construction(op="midpoint", out=m, args=[u, v], value=None),
                Construction(op="perp_point", out=n, args=[m, u, v], value=1),
            ]
            for k in by_out:
                if by_out[k] >= ci:
                    by_out[k] += 2
            idx = plan.points.index(x1)
            plan.points[idx:idx] = [m, n]
            # вспомогательная прямая (слой доп. построений) + скрытые подписи:
            # без участия в draw точки M/N дают ORPHAN_POINT
            draw = plan.draw
            if [m, n] not in (draw.aux_lines or []):
                draw.aux_lines = list(draw.aux_lines or []) + [[m, n]]
            for nm in (m, n):
                if nm not in (draw.hide_labels or []):
                    draw.hide_labels = list(draw.hide_labels or []) + [nm]
            fixed.append(f"{x1}: {u}{x1}={x1}{v} — серединный перпендикуляр "
                         f"{u}{v}, не окружность")
        if not fixed:
            return None
        errs = validate_plan(plan)
        if errs:
            raise ValueError("; ".join(errs[:3]))
    except Exception:                       # noqa: BLE001 - откат, не валить план
        plan.constructions, plan.constraints, plan.points, plan.draw = snapshot
        return None
    return "; ".join(fixed)


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


def install(llm_module) -> bool:
    """Правило в промпты + пост-ремонт плана после formalize. Повторно — no-op."""
    if not ENABLED:
        return False
    _append_rules(llm_module)
    orig = getattr(llm_module, "formalize", None)
    if orig is not None and not getattr(orig, "_equidistant", False):
        @wraps(orig)
        def formalize(sess, text, *args, **kwargs):
            plan, warn = orig(sess, text, *args, **kwargs)
            try:
                msg = repair(text, plan)
                if msg:
                    warn = [str(w) for w in (warn or [])] + \
                        [f"EQUIDISTANT_FIXED: {msg}"]
            except Exception:               # noqa: BLE001 - проверка не должна валить формализацию
                pass
            return plan, warn
        formalize._equidistant = True
        llm_module.formalize = formalize
    return True
