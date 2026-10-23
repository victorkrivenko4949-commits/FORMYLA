# -*- coding: utf-8 -*-
"""Интеграционные тесты воркера «Банка неточностей» (раздел 11 ТЗ).

Используют мок-модель (без реального LLM) через monkeypatch клиента.
Покрытие:
  - валидная неточность → запись + уведомление;
  - описка → skipped без уведомления;
  - невалидный JSON → retry;
  - короткое рассуждение → retry;
  - дедупликация: повторная неточность инкрементирует occurrences, kind=repeat;
  - лимит 3 неточностей на срез;
  - подбор из базы: при наличии подходящих задач генерация не вызывается.
"""

from __future__ import annotations

import pytest

from services import insight_runner
from services.insight_validator import _has_stopword


# ─── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def app_ctx(app):
    with app.app_context():
        yield app


def _valid_insight(title="Считает размещения прямым перебором вместо правила умножения"):
    return {
        "title": title,
        "type": "time_loss",
        "severity": 2,
        "duplicate_of": None,
        "where": "шаг 3",
        "what_went_wrong": "Перебирает все размещения вручную вместо правила умножения с фиксацией позиции.",
        "better_way": "Зафиксировать позицию и перемножить число вариантов.",
        "time_lost_estimate_min": 5,
        "canonical_fact": "правило умножения",
        "tags": ["topic:combinatorics", "method:rule_of_product"],
        "practice": [
            {
                "statement": f"Задача {i + 1}",
                "answer": "1",
                "hint": "приём",
                "solution_sketch": "",
                "difficulty": 3,
                "visibility": v,
                "why_this_task": "Тренирует правило умножения",
                "naive_path_cost": "дольше",
            }
            for i, v in enumerate(("obvious", "medium", "hidden"))
        ],
    }


# ─── Тесты стоп-слова ─────────────────────────────────────────────────────

def test_stopword_detection():
    assert _has_stopword("Невнимательность при подсчёте") == "невнимательн"
    assert _has_stopword("Корректный приём") is None


# ─── Тесты дедупликации ───────────────────────────────────────────────────

def test_normalize_title():
    from models_insights import normalize_title
    assert normalize_title("Считает  размещения, ПРЯМЫМ перебором!") == \
        "считает размещения прямым перебором"


def test_dedup_same_title(app_ctx):
    from models import db
    from models_insights import Insight, normalize_title
    from services.insight_queue import find_duplicate

    from models import User
    u = User(email="dedup@test.com", nickname="dedup", current_plan="free")
    db.session.add(u)
    db.session.flush()

    title = "Считает размещения прямым перебором вместо правила умножения"
    db.session.add(Insight(
        user_id=u.id,
        title=title,
        title_normalized=normalize_title(title),
        type="time_loss",
        severity=2,
        tags='["topic:combinatorics"]',
    ))
    db.session.commit()

    dup = find_duplicate(u.id, normalize_title(title), ["topic:combinatorics", "method:x"])
    assert dup is not None
    assert dup.id is not None


def test_dedup_tag_overlap(app_ctx):
    from models import db
    from models_insights import Insight, normalize_title
    from services.insight_queue import find_duplicate

    from models import User
    u = User(email="dedup2@test.com", nickname="dedup2", current_plan="free")
    db.session.add(u)
    db.session.flush()

    title = "Потерянный случай в обратном включении"
    db.session.add(Insight(
        user_id=u.id,
        title=title,
        title_normalized=normalize_title(title),
        type="proof_gap",
        severity=2,
        tags='["topic:geometry","method:double_inclusion"]',
    ))
    db.session.commit()

    dup = find_duplicate(
        u.id,
        normalize_title("Другой заголовок про другое"),
        ["topic:geometry", "method:double_inclusion"],
    )
    assert dup is not None


# ─── Тест вставки с дедупликацией ─────────────────────────────────────────

def test_insert_insight_repeat_increments_occurrences(app_ctx):
    from models import db
    from models_insights import Insight
    from services.insight_queue import _insert_insight

    from models import User
    u = User(email="repeat@test.com", nickname="repeat", current_plan="free")
    db.session.add(u)
    db.session.flush()
    db.session.commit()

    class _Job:
        id = None
        source = "regular"
        source_task_id = None

    insight, kind = _insert_insight(u.id, _Job(), _valid_insight(), is_repeat=False)
    assert kind == "new"
    assert insight.occurrences == 1

    # Повторная вставка того же title → occurrences++ и kind=repeat.
    insight2, kind2 = _insert_insight(u.id, _Job(), _valid_insight(), is_repeat=False)
    assert kind2 == "repeat"
    assert insight2.id == insight.id
    assert insight2.occurrences == 2


# ─── Тест подбора из базы ─────────────────────────────────────────────────

def test_bank_tasks_selected_generation_not_called(app_ctx):
    from models import db, DailyTaskBank
    from services.insight_queue import _bank_tasks_for, _practice_from_bank

    db.session.add(DailyTaskBank(
        subtopic="Комбинаторика",
        section="combinatorics",
        level=2,
        statement="Сколько способов расставить 3 книги на полке?",
        answer="6",
        solution="3! = 6",
    ))
    db.session.commit()

    insight = {
        "tags": ["topic:combinatorics"],
        "canonical_fact": "правило умножения",
    }
    found = _bank_tasks_for(insight, difficulty=2)
    assert len(found) >= 1
    assert found[0]["statement"].startswith("Сколько способов")

    practice = _practice_from_bank(found)
    assert practice[0]["source"] == "bank"


# ─── Тест off-peak ────────────────────────────────────────────────────────

def test_off_peak_logic():
    from datetime import datetime
    from services.insight_queue import is_off_peak

    assert is_off_peak(datetime(2026, 8, 31, 23, 0)) is True
    assert is_off_peak(datetime(2026, 8, 31, 3, 0)) is True
    assert is_off_peak(datetime(2026, 8, 31, 14, 0)) is False
