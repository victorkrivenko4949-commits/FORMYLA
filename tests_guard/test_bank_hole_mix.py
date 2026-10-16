# -*- coding: utf-8 -*-
"""Добор при пустой ячейке уровня: ученик уровня 3 не должен получать подборку
почти целиком из уровня 2 (инцидент 15.10.2026, геометрия L3 = 0 после чисток).

Синтетический индекс подставляется напрямую — реальный FORMYLA_BANK.jsonl не нужен.
"""
from __future__ import annotations

import importlib.util
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BANK_MODULE = ROOT / "daily_tasks" / "formyla_bank.py"


def _load(monkeypatch, hole_share=None):
    monkeypatch.delenv("FORMYLA_JSONL_FALLBACK", raising=False)
    if hole_share is None:
        monkeypatch.delenv("FORMYLA_BANK_HOLE_LOWER_SHARE", raising=False)
    else:
        monkeypatch.setenv("FORMYLA_BANK_HOLE_LOWER_SHARE", hole_share)
    name = f"_fb_hole_{hole_share or 'default'}"
    sys.modules.pop(name, None)
    spec = importlib.util.spec_from_file_location(name, BANK_MODULE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _cell(level, n, grade=9, topic="Тест-тема"):
    return [{"grade": grade, "topic": topic, "level": level, "position": i,
             "task_text": f"{topic} L{level} #{i}", "correct_answer": "1"}
            for i in range(1, n + 1)]


def _levels(tasks):
    return Counter(int(t["level"]) for t in tasks)


def test_hole_mix_prefers_upper(monkeypatch):
    fb = _load(monkeypatch)
    fb._index = {(9, "Тест-тема", 1): _cell(1, 35), (9, "Тест-тема", 2): _cell(2, 35),
                 (9, "Тест-тема", 4): _cell(4, 35)}
    fb._loaded = True
    for seed in (0, 1):
        got = _levels(fb.get_tasks(9, "Тест-тема", 3, count=5, user_id=None, day_seed=seed))
        assert sum(got.values()) == 5
        assert got[4] >= 3, f"при пустом L3 ожидали >=3 задач L4, получили {dict(got)}"
        assert got[2] <= 2, f"при пустом L3 ожидали <=2 задач L2, получили {dict(got)}"
        assert got[1] == 0 and got[3] == 0


def test_partial_shortage_keeps_70_30(monkeypatch):
    fb = _load(monkeypatch)
    fb._index = {(9, "Тест-тема", 2): _cell(2, 35), (9, "Тест-тема", 3): _cell(3, 2),
                 (9, "Тест-тема", 4): _cell(4, 35)}
    fb._loaded = True
    got = _levels(fb.get_tasks(9, "Тест-тема", 3, count=5, user_id=None, day_seed=0))
    assert got[3] == 2
    assert got[2] >= got[4], f"при частичной нехватке добор снизу остаётся основным: {dict(got)}"


def test_exact_level_full_is_untouched(monkeypatch):
    fb = _load(monkeypatch)
    fb._index = {(9, "Тест-тема", lv): _cell(lv, 35) for lv in (1, 2, 3, 4)}
    fb._loaded = True
    got = _levels(fb.get_tasks(9, "Тест-тема", 3, count=5, user_id=None, day_seed=0))
    assert got == Counter({3: 5})


def test_hole_share_env_override(monkeypatch):
    fb = _load(monkeypatch, "1")
    fb._index = {(9, "Тест-тема", 2): _cell(2, 35), (9, "Тест-тема", 4): _cell(4, 35)}
    fb._loaded = True
    got = _levels(fb.get_tasks(9, "Тест-тема", 3, count=5, user_id=None, day_seed=1))
    assert got[2] == 5, f"FORMYLA_BANK_HOLE_LOWER_SHARE=1 должен вернуть прежнее поведение: {dict(got)}"


def test_top_level_hole_falls_to_level3(monkeypatch):
    fb = _load(monkeypatch)
    fb._index = {(9, "Тест-тема", 2): _cell(2, 35), (9, "Тест-тема", 3): _cell(3, 35)}
    fb._loaded = True
    got = _levels(fb.get_tasks(9, "Тест-тема", 4, count=5, user_id=None, day_seed=0))
    assert got[3] == 5
