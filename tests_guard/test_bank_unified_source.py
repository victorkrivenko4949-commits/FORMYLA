# -*- coding: utf-8 -*-
"""Шаг 8.2. Единая выдача: daily_task_bank (приоритет) + JSONL (добор).

Таблица подменяется фейковым модулем services.daily_bank_source — Flask/БД не нужны.
Инварианты:
  * таблица пуста/недоступна -> выдача байт в байт как раньше (только JSONL);
  * таблица покрывает норму -> все задачи из таблицы, JSONL не трогается;
  * таблица покрывает часть -> сначала её задачи, остаток из JSONL того же уровня,
    без дублей по тексту;
  * user_id=None (служебные вызовы, тесты банка) -> таблица не опрашивается;
  * исключение внутри адаптера не роняет выдачу.
"""
from __future__ import annotations

import importlib.util
import sys
import types
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BANK_MODULE = ROOT / "daily_tasks" / "formyla_bank.py"
TOPIC = "Тест-тема"


def _fresh(name, monkeypatch, fake_pick=None):
    monkeypatch.delenv("FORMYLA_JSONL_FALLBACK", raising=False)
    if fake_pick is not None:
        pkg = types.ModuleType("services"); pkg.__path__ = []
        mod = types.ModuleType("services.daily_bank_source"); mod.pick_from_table = fake_pick
        monkeypatch.setitem(sys.modules, "services", pkg)
        monkeypatch.setitem(sys.modules, "services.daily_bank_source", mod)
    sys.modules.pop(name, None)
    spec = importlib.util.spec_from_file_location(name, BANK_MODULE)
    fb = importlib.util.module_from_spec(spec); spec.loader.exec_module(fb)
    fb._index = {(9, TOPIC, lv): [{"grade": 9, "topic": TOPIC, "level": lv, "position": i,
                                  "task_text": f"JSONL L{lv} #{i}", "correct_answer": "1"}
                                 for i in range(1, 36)] for lv in (1, 2, 3, 4)}
    fb._loaded = True
    fb._student_grade = lambda uid, g: g
    return fb


def _table_tasks(n, level=3):
    return [{"task_text": f"TABLE L{level} #{i}", "correct_answer": "1", "solution": "",
             "level": level, "position": i, "topic": TOPIC, "figure_svg_path": "",
             "source": "daily_task_bank", "bank_task_id": 1000 + i} for i in range(1, n + 1)]


def test_empty_table_is_identical_to_jsonl_only(monkeypatch):
    calls = []
    fb = _fresh("_u_a", monkeypatch, lambda *a, **k: calls.append(a) or [])
    got = fb.get_tasks(9, TOPIC, 3, count=5, user_id=42, day_seed=1)
    assert len(got) == 5 and all(t["task_text"].startswith("JSONL L3") for t in got)
    assert len(calls) == 1, "таблица опрашивается ровно один раз"


def test_table_covers_norm(monkeypatch):
    fb = _fresh("_u_b", monkeypatch, lambda g, t, lv, c, u, ex=None: _table_tasks(c, lv))
    got = fb.get_tasks(9, TOPIC, 3, count=5, user_id=42, day_seed=1)
    assert [t["source"] for t in got] == ["daily_task_bank"] * 5
    assert all(t["level"] == 3 for t in got)


def test_table_partial_then_jsonl_same_level(monkeypatch):
    fb = _fresh("_u_c", monkeypatch, lambda g, t, lv, c, u, ex=None: _table_tasks(2, lv))
    got = fb.get_tasks(9, TOPIC, 3, count=5, user_id=42, day_seed=1)
    assert len(got) == 5
    assert [t.get("source") for t in got[:2]] == ["daily_task_bank"] * 2
    assert all(t["task_text"].startswith("JSONL L3") for t in got[2:]), "остаток — JSONL точного уровня"
    assert len({t["task_text"] for t in got}) == 5


def test_none_user_skips_table(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("таблица не должна опрашиваться при user_id=None")
    fb = _fresh("_u_d", monkeypatch, boom)
    got = fb.get_tasks(9, TOPIC, 2, count=5, user_id=None)
    assert len(got) == 5 and all(t["level"] == 2 for t in got)


def test_adapter_exception_falls_back_to_jsonl(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("no app context")
    fb = _fresh("_u_e", monkeypatch, boom)
    got = fb.get_tasks(9, TOPIC, 4, count=5, user_id=42)
    assert len(got) == 5 and all(t["level"] == 4 for t in got)


def test_table_tasks_excluded_from_jsonl_dedupe(monkeypatch):
    def same_text(g, t, lv, c, u, ex=None):
        return [{"task_text": "JSONL L3 #1", "correct_answer": "1", "solution": "", "level": lv,
                 "position": 1, "topic": TOPIC, "figure_svg_path": "", "source": "daily_task_bank"}]
    fb = _fresh("_u_f", monkeypatch, same_text)
    got = fb.get_tasks(9, TOPIC, 3, count=5, user_id=42)
    assert len(got) == 5 and len({t["task_text"] for t in got}) == 5
