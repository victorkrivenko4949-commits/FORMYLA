# -*- coding: utf-8 -*-
"""Названная в условии точка не может быть скрытой (подпись обязательна).

Прод-ошибка (задача 2, живая генерация 24.10.2026): «Медианы AA₁, BB₁ и CC₁
пересекаются в точке M» — формализатор положил A_1, B_1, C_1 в
draw.hide_labels. Рендер рисует кружки точек, но подписи убирает: на чертеже
три безымянные точки. Известный пункт №2 аудита: если точка названа в
условии, её подпись обязана быть на чертеже.

Модуль оборачивает pipeline._strip_invented_labels — единственную точку
ядра, где есть одновременно текст условия и план: после оригинальной
чистки «выдуманных» подписей он возвращает в draw.hide_labels точки, чьи
имена встречаются в тексте (в любом формате: A, A_1, A1, A₁). Плюс правило
41 формализатора: не прятать названные точки. Точки, которых в тексте нет
(технические: S, W, центр окружности), остаются скрытыми как раньше.
GEOEXACT_NAMED_LABELS=0 выключает.
"""
from __future__ import annotations

import functools
import os
import re

ENABLED = (os.environ.get("GEOEXACT_NAMED_LABELS") or "1").strip().lower() not in ("0", "no", "off")

CACHE_SUFFIX = "+namedLabels1"

EXTRA_RULES = """
41. NAMED_LABEL_RULE: точки, названные в условии задачи (включая точки с
    индексами: A_1, B_1, C_1, K, M, O, I), НИКОГДА не добавляй в
    draw.hide_labels — у каждой названной точки на чертеже должна быть
    подпись. Прятать можно только технические точки, которых в тексте нет
    (промежуточные центры, вторые пересечения окружностей).
"""

_NAME = r"[A-Z](?:_?\d{1,2})?"


def _plain(text: str) -> str:
    """Юникод-индексы A₁ -> A_1, LaTeX-обёртки долой (общий препроцессор)."""
    try:
        from .convexity import _plain as p
        return p(text)
    except Exception:  # noqa: BLE001
        return (text or "").replace("$", " ")


def _names_in_text(text: str) -> set[str]:
    """Имена точек, встречающиеся в тексте: {'A', 'A_1', 'A1', ...}.

    Латинская заглавная буква с необязательным индексом; русские слова
    (В, С, А в кириллице) не совпадают с латинскими именами точек.
    """
    plain = _plain(text or "")
    found = set()
    for m in re.finditer(_NAME, plain):
        found.add(m[0])
        found.add(m[0].replace("_", ""))     # A_1 -> A1
        if "_" not in m[0]:
            found.add(re.sub(r"(\d)", r"_\1", m[0], count=1) or m[0])  # A1 -> A_1
    return found


def unhide_named_points(text: str, plan) -> None:
    """Убрать из draw.hide_labels точки, названные в тексте. In-place, тихий."""
    if plan is None:
        return
    draw = getattr(plan, "draw", None)
    if draw is None:
        return
    hidden = getattr(draw, "hide_labels", None)
    if not hidden:
        return
    names = _names_in_text(text)
    if not names:
        return
    keep = [n for n in hidden if not (isinstance(n, str) and n in names)]
    if len(keep) != len(hidden):
        draw.hide_labels = keep


def _wrap_strip(orig):
    @functools.wraps(orig)
    def _strip_invented_labels(text, plan, *args, **kwargs):
        res = orig(text, plan, *args, **kwargs)
        try:
            unhide_named_points(text, plan)
        except Exception:  # noqa: BLE001
            pass
        return res
    _strip_invented_labels._named_labels = True
    return _strip_invented_labels


def _append_rules(llm_module) -> bool:
    if not ENABLED:
        return False
    try:
        target = llm_module.SYS_FORMALIZE
        if "41." not in target:
            llm_module.SYS_FORMALIZE = target.rstrip("\n") + "\n" + EXTRA_RULES
        ok = "41." in llm_module.SYS_FORMALIZE
        if getattr(llm_module, "SYS_AUX", None) and "41." not in llm_module.SYS_AUX:
            llm_module.SYS_AUX = llm_module.SYS_AUX.rstrip("\n") + "\n" + EXTRA_RULES
        return ok
    except Exception:  # noqa: BLE001
        return False


def install(pipeline_module, llm_module) -> bool:
    """Обёртка _strip_invented_labels + правило 41 + суффикс версии кэша."""
    if not ENABLED:
        return False
    ok = _append_rules(llm_module)
    try:
        orig = getattr(pipeline_module, "_strip_invented_labels", None)
        if orig is not None and not getattr(orig, "_named_labels", False):
            pipeline_module._strip_invented_labels = _wrap_strip(orig)
            ok = True
    except Exception:  # noqa: BLE001
        return False
    ver = getattr(pipeline_module, "ENGINE_VERSION", None)
    if ver and CACHE_SUFFIX not in ver:
        pipeline_module.ENGINE_VERSION = ver + CACHE_SUFFIX
    return ok
