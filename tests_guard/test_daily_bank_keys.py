# -*- coding: utf-8 -*-
"""Шаг 8 (вариант Б), PR 1: единый ключ темы основного банка.

Фиксирует решения:
  * ключ темы = theme_id вида G<класс>_T<номер>, класс зашит в префикс;
  * регистр имеет значение — 'g9_t16' невалиден (этап 2, дефект D1: bank_daily
    приводил ключ к нижнему регистру, и раздел всегда становился 'algebra');
  * раздел и название берутся из data/theme_to_section.json / theme_titles.json.
Без Flask и БД.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _keys():
    name = "_daily_bank_keys_guard"
    sys.modules.pop(name, None)
    spec = importlib.util.spec_from_file_location(name, ROOT / "services" / "daily_bank_keys.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_parse_theme_id():
    k = _keys()
    assert k.parse_theme_id("G9_T16") == (9, 16)
    assert k.parse_theme_id("G11_T20") == (11, 20)
    assert k.parse_theme_id(" G5_T01 ") == (5, 1)
    assert k.parse_theme_id("g9_t16") is None, "нижний регистр должен быть невалиден"
    assert k.parse_theme_id("G12_T01") is None
    assert k.parse_theme_id("quadratic_equations") is None
    assert k.parse_theme_id("") is None and k.parse_theme_id(None) is None


def test_grade_of_theme():
    k = _keys()
    assert k.grade_of_theme("G7_T03") == 7
    assert k.grade_of_theme("algebra") is None


def test_section_lookup_preserves_case():
    k = _keys()
    assert k.section_of_theme("G9_T16") == "geometry"
    assert k.section_of_theme("g9_t16") is None, "регрессия D1: lowercase не должен находить раздел"


def test_registry_keys_are_uppercase_theme_ids():
    """Все ключи справочника разделов — валидные theme_id (иначе выборка по классу сломается)."""
    k = _keys()
    data = json.loads((ROOT / "data" / "theme_to_section.json").read_text(encoding="utf-8"))
    bad = [t for t in data if k.parse_theme_id(t) is None]
    assert not bad, f"невалидные ключи в theme_to_section.json: {bad[:10]}"
    bad_sec = [t for t, s in data.items() if s not in k.CANONICAL_SECTIONS]
    assert not bad_sec, f"неканонические разделы: {bad_sec[:10]}"


def test_titles_cover_all_section_keys():
    k = _keys()
    sections = json.loads((ROOT / "data" / "theme_to_section.json").read_text(encoding="utf-8"))
    titles = json.loads((ROOT / "data" / "theme_titles.json").read_text(encoding="utf-8"))
    missing = [t for t in sections if t not in titles]
    assert not missing, f"темы без названия (выдача по JSONL не найдёт ячейку): {missing[:10]}"
    assert k.title_of_theme("G9_T16")
