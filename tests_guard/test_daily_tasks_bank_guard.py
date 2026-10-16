# -*- coding: utf-8 -*-
"""Страховка «Задачи дня»: банк FORMYLA_BANK.jsonl должен быть включён и выдавать задачи.

Этот тест появился после инцидента 14.10.2026: коммит #118 отключил запасной
банк по умолчанию, страница «Задачи дня» опустела для всех учеников на ~10 часов.

Тест намеренно не зависит от Flask, базы данных и секретов: модуль
daily_tasks/formyla_bank.py загружается напрямую по пути, минуя пакет
daily_tasks (который тянет за собой всё приложение). Запускается без
pip install зависимостей проекта — только стандартная библиотека и pytest.

Запуск: python -m pytest tests_guard -q
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BANK_MODULE = ROOT / "daily_tasks" / "formyla_bank.py"
BANK_FILE = ROOT / "FORMYLA_BANK.jsonl"

MIN_TOTAL_TASKS = 10_000      # в банке ~18.7k задач; порог ловит обрезанный/битый файл
DAILY_COUNT = 5               # минимальная дневная норма ученика


def _load_bank(monkeypatch, env_value=None):
    """Загрузить formyla_bank.py как отдельный модуль с нужным окружением."""
    if env_value is None:
        monkeypatch.delenv("FORMYLA_JSONL_FALLBACK", raising=False)
    else:
        monkeypatch.setenv("FORMYLA_JSONL_FALLBACK", env_value)
    name = f"_formyla_bank_guard_{env_value or 'unset'}"
    sys.modules.pop(name, None)
    spec = importlib.util.spec_from_file_location(name, BANK_MODULE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_bank_file_present():
    assert BANK_FILE.exists(), "FORMYLA_BANK.jsonl отсутствует в корне репозитория"
    assert BANK_FILE.stat().st_size > 1_000_000, "FORMYLA_BANK.jsonl подозрительно мал"


def test_fallback_enabled_by_default(monkeypatch):
    """Без переменной окружения банк ОБЯЗАН работать — именно это сломал #118."""
    bank = _load_bank(monkeypatch, None)
    assert bank.FALLBACK_ENABLED is True
    assert bank.has_rows() is True


def test_fallback_enabled_with_one(monkeypatch):
    bank = _load_bank(monkeypatch, "1")
    assert bank.FALLBACK_ENABLED is True
    assert bank.has_rows() is True


def test_fallback_disabled_only_by_explicit_zero(monkeypatch):
    bank = _load_bank(monkeypatch, "0")
    assert bank.FALLBACK_ENABLED is False
    assert bank.has_rows() is False
    assert bank.get_tasks(9, "любая тема", 2, count=5) == []


@pytest.fixture(scope="module")
def bank():
    os.environ.pop("FORMYLA_JSONL_FALLBACK", None)
    spec = importlib.util.spec_from_file_location("_formyla_bank_guard_main", BANK_MODULE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.load()
    return mod


def test_bank_index_is_big_enough(bank):
    total = sum(len(rows) for rows in bank._index.values())
    assert total >= MIN_TOTAL_TASKS, f"в банке только {total} задач — файл обрезан или битый"


def test_every_grade_has_topics(bank):
    grades = sorted({g for (g, _, _) in bank._index})
    assert grades, "в банке нет ни одного класса"
    for g in grades:
        assert bank.available_topics(g), f"класс {g}: нет ни одной темы"


def test_every_topic_yields_daily_tasks(bank):
    """Для каждой пары (класс, тема) банк должен отдавать хотя бы одну задачу
    с текстом; для самой наполненной темы класса — полную норму с ответами."""
    grades = sorted({g for (g, _, _) in bank._index})
    problems = []
    for g in grades:
        best_topic, best_rows = None, -1
        for topic in bank.available_topics(g):
            rows = sum(len(bank._index.get((g, topic, lv), ())) for lv in range(1, 5))
            if rows > best_rows:
                best_topic, best_rows = topic, rows
            tasks = bank.get_tasks(g, topic, 2, count=DAILY_COUNT, user_id=None)
            if not tasks:
                problems.append(f"класс {g}, тема «{topic}»: get_tasks вернул пусто")
                continue
            for t in tasks:
                if not (t.get("task_text") or t.get("statement") or "").strip():
                    problems.append(f"класс {g}, тема «{topic}»: задача без текста")
                    break
        full = bank.get_tasks(g, best_topic, 2, count=DAILY_COUNT, user_id=None)
        if len(full) < DAILY_COUNT:
            problems.append(f"класс {g}, тема «{best_topic}»: только {len(full)} задач вместо {DAILY_COUNT}")
        if any(not str(t.get("correct_answer") or t.get("answer") or "").strip() for t in full):
            problems.append(f"класс {g}, тема «{best_topic}»: есть задача без ответа")
    assert not problems, "\n".join(problems)


def test_user_specific_pick_is_deterministic_and_full(bank):
    """Выдача для конкретного ученика (как в pick_daily_set) непустая и повторяемая."""
    g = sorted({gr for (gr, _, _) in bank._index})[0]
    topic = bank.available_topics(g)[0]
    a = bank.get_tasks(g, topic, 2, count=DAILY_COUNT, user_id=123456, day_seed=3)
    b = bank.get_tasks(g, topic, 2, count=DAILY_COUNT, user_id=123456, day_seed=3)
    assert a, "пустая выдача для ученика"
    assert [t.get("position") for t in a] == [t.get("position") for t in b]
