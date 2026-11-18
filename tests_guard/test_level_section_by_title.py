# -*- coding: utf-8 -*-
"""Шаг 8.3. Ответы на задачи дня (JSONL и daily_task_bank) двигают уровень ПО РАЗДЕЛУ.

record_daily_answer берёт раздел как SECTION_RU_TO_SLUG.get(item.topic, item.topic),
а item.topic у задач дня — русское название темы. Без карты «название -> раздел»
раздел не распознаётся и уровень по геометрии/алгебре не обновляется (дефект U6).

Тесты без Flask/БД: модуль ключей грузится по пути, level_engine проверяется
статически (текст файла содержит подмешивание карты).
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _keys():
    name = "_keys_8_3"
    sys.modules.pop(name, None)
    spec = importlib.util.spec_from_file_location(name, ROOT / "services" / "daily_bank_keys.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_title_map_covers_registry():
    k = _keys()
    m = k.title_section_map()
    titles = json.loads((ROOT / "data" / "theme_titles.json").read_text(encoding="utf-8"))
    distinct = {v.strip() for v in titles.values() if v}
    assert len(m) >= 0.8 * len(distinct), f"карта покрывает {len(m)} из {len(distinct)} названий"
    assert set(m.values()) <= set(k.CANONICAL_SECTIONS)


def test_incident_topic_resolves_to_geometry():
    k = _keys()
    assert k.section_of_title("Углы и вписанные конфигурации") == "geometry"
    assert k.section_of_title("  Углы и вписанные конфигурации ") == "geometry"
    assert k.section_of_title("нет такой темы") is None


def test_ambiguous_titles_are_excluded():
    """Если одно название в разных классах относится к разным разделам — его нет в карте."""
    k = _keys()
    titles = json.loads((ROOT / "data" / "theme_titles.json").read_text(encoding="utf-8"))
    sections = json.loads((ROOT / "data" / "theme_to_section.json").read_text(encoding="utf-8"))
    by_title = {}
    for tid, t in titles.items():
        by_title.setdefault(t.strip(), set()).add(sections.get(tid))
    ambiguous = {t for t, s in by_title.items() if len(s) > 1}
    m = k.title_section_map()
    assert not (ambiguous & set(m)), f"неоднозначные названия попали в карту: {ambiguous & set(m)}"


def test_level_engine_mixes_titles_into_section_map():
    """record_daily_answer использует SECTION_RU_TO_SLUG из level_engine — карта должна подмешиваться там."""
    src = (ROOT / "services" / "level_engine.py").read_text(encoding="utf-8")
    assert "title_section_map" in src, "level_engine не подмешивает названия тем в SECTION_RU_TO_SLUG"
    assert re.search(r"SECTION_RU_TO_SLUG\.setdefault\(", src), "ожидался setdefault, чтобы не перетирать штатные ключи"


def test_rotation_lookup_simulation():
    """Имитация daily_task_rotation._normalize_section: _map.get(topic, topic)."""
    k = _keys()
    base = {"Алгебра": "algebra", "Геометрия": "geometry"}
    for t, s in k.title_section_map().items():
        base.setdefault(t, s)
    assert base.get("Углы и вписанные конфигурации", "Углы и вписанные конфигурации") == "geometry"
    assert base.get("Геометрия") == "geometry", "штатные ключи не перетираются"
