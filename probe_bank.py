# -*- coding: utf-8 -*-
"""Банк пробников: 10 задач из одного probeid. Тема дня меняется каждый день.
Файлы рядом с app.py: formyla_grade{5..11}.json (список probe-объектов)."""
from __future__ import annotations
import json, logging, os
from datetime import date
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)
_DIR = os.path.dirname(os.path.abspath(__file__))
_CACHE: Dict[int, List[Dict[str, Any]]] = {}
EPOCH = date(2026, 1, 1)

def _load(grade: int) -> List[Dict[str, Any]]:
    if grade not in _CACHE:
        path = os.path.join(_DIR, f"formyla_grade{grade}.json")
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
            probes = raw if isinstance(raw, list) else raw.get("probes", raw.get("tasks", []))
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("probe_bank: cannot load %s: %s", path, exc)
            probes = []
        probes.sort(key=lambda p: (str(p.get("theme","")), int(p.get("level",0)), int(p.get("day",0))))
        _CACHE[grade] = probes
    return _CACHE[grade]

def themes_for(grade: int, level: int) -> List[str]:
    seen, out = set(), []
    for p in _load(grade):
        if int(p.get("level",0)) == level:
            th = str(p.get("theme","")).strip()
            if th and th not in seen:
                seen.add(th); out.append(th)
    return out

def theme_of_day(grade: int, level: int, d: Optional[date] = None) -> Optional[str]:
    d = d or date.today()
    themes = themes_for(grade, level)
    if not themes:
        return None
    return themes[(d - EPOCH).days % len(themes)]

def next_probe(*, grade: int, level: int, theme: str, solved_probeids: set) -> Optional[Dict[str, Any]]:
    probes = [p for p in _load(grade)
              if int(p.get("level",0)) == level
              and str(p.get("theme","")).strip() == theme.strip()]
    if not probes:
        logger.warning("probe_bank: no probes grade=%s level=%s theme=%s", grade, level, theme)
        return None
    target = next((p for p in probes if p.get("probeid") not in solved_probeids), probes[0])
    tasks = target.get("tasks", [])[:10]
    if len(tasks) < 10:
        logger.warning("probe_bank: %s has only %d tasks", target.get("probeid"), len(tasks))
    out = dict(target); out["tasks"] = tasks
    return out
