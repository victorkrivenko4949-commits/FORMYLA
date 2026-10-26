# -*- coding: utf-8 -*-
"""Плечи и дуги углов из утверждения — на чертёж.

Прод-кейс (AKX=CKY, 26.10.2026): чертёж точный (constraints_only), но
отрезки KX и KY не проведены — углы из «докажите, что ∠AKX = ∠CKY» на
чертеже не видны, пользователю фигура кажется неверной. Формализатор
рисует плечи углов не всегда; добираем недостающие сегменты и дуги-метки
сами — по любым углам, упомянутым в тексте (∠ABC, \\angle ABC, «угол ABC»).

Правило контракта: финальный вид полный — утверждение должно быть видно
на чертеже. Добавление — только в draw (отрисовка), план и решение не
меняются, солвер не затрагивается.

GEOEXACT_CLAIM_ARMS=0 выключает.
"""
from __future__ import annotations

import functools
import os
import re

ENABLED = (os.environ.get("GEOEXACT_CLAIM_ARMS") or "1").strip().lower() not in ("0", "no", "off")

CACHE_SUFFIX = "+claimArms1"

# ∠ABC / \angle ABC / «угол(ом/у/ы…) ABC» — три латинские заглавные подряд.
# (?<![А-Яа-яЁё]) не даёт матчиться внутрим «треугольник/остроугольный».
_ANGLE_RE = re.compile(
    r"(?:∠|\\angle|(?<![А-Яа-яЁё])уг\w*)\s*([A-Z])\s*([A-Z])\s*([A-Z])")


def add_claim_arms(text: str, plan) -> list:
    """Добавить недостающие плечи углов, упомянутых в тексте.

    Возвращает список добавленных сегментов (для диагностики/тестов).
    План и решение не меняются — только draw.segments.
    """
    added: list = []
    draw = getattr(plan, "draw", None)
    segs = getattr(draw, "segments", None)
    if not isinstance(segs, list):
        return added
    known = set(plan.points)
    have = set()
    for it in segs:
        if (isinstance(it, (list, tuple)) and len(it) == 2
                and all(isinstance(a, str) for a in it)):
            have.add((it[0], it[1]))
            have.add((it[1], it[0]))
    for m in _ANGLE_RE.finditer(text or ""):
        p, q, r = m.group(1), m.group(2), m.group(3)
        if len({p, q, r}) != 3 or not {p, q, r} <= known:
            continue
        for a, b in ((p, q), (q, r)):
            if (a, b) not in have:
                segs.append([a, b])
                have.add((a, b))
                have.add((b, a))
                added.append(a + b)
    return added


def add_claim_angle_marks(text: str, plan) -> list:
    """Добавить дуги-метки для углов из текста, если метки ещё нет.

    Возвращает список добавленных меток (вершины). Дуга делает утверждение
    видимым даже там, где плечи уже проведены.
    """
    added: list = []
    draw = getattr(plan, "draw", None)
    marks = getattr(draw, "angle_marks", None)
    if not isinstance(marks, list):
        return added
    known = set(plan.points)
    covered = set()
    for m in marks:
        pts = m.get("pts") if isinstance(m, dict) else None
        if (isinstance(pts, (list, tuple)) and len(pts) == 3
                and all(isinstance(t, str) for t in pts)):
            covered.add((pts[1], pts[0], pts[2]))
            covered.add((pts[1], pts[2], pts[0]))
    for ra in getattr(draw, "right_angles", None) or []:
        if (isinstance(ra, (list, tuple)) and len(ra) == 3
                and all(isinstance(t, str) for t in ra)):
            covered.add((ra[1], ra[0], ra[2]))
            covered.add((ra[1], ra[2], ra[0]))
    for m in _ANGLE_RE.finditer(text or ""):
        p, q, r = m.group(1), m.group(2), m.group(3)
        if len({p, q, r}) != 3 or not {p, q, r} <= known:
            continue
        if (q, p, r) in covered:
            continue
        marks.append({"pts": [p, q, r]})
        covered.add((q, p, r))
        covered.add((q, r, p))
        added.append(q)
    return added


def _wrap_strip(orig):
    @functools.wraps(orig)
    def _strip(text, plan):
        orig(text, plan)
        try:
            add_claim_arms(text, plan)
            add_claim_angle_marks(text, plan)
        except Exception:  # noqa: BLE001
            pass
    _strip._claim_arms = True
    _strip._original = orig
    return _strip


def install(semantics_module, llm_module, pipeline_module=None) -> bool:
    if not ENABLED:
        return False
    try:
        if pipeline_module is not None:
            if not getattr(pipeline_module._strip_invented_labels, "_claim_arms", False):
                pipeline_module._strip_invented_labels = _wrap_strip(
                    pipeline_module._strip_invented_labels)
            ver = getattr(pipeline_module, "ENGINE_VERSION", None)
            if ver is not None and CACHE_SUFFIX not in ver:
                pipeline_module.ENGINE_VERSION = ver + CACHE_SUFFIX
        return True
    except Exception:  # noqa: BLE001
        return False
