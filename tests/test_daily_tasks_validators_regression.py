# -*- coding: utf-8 -*-
"""Регрессионные тесты для daily_tasks/pipeline/validators.py.

Этот файл — точечное покрытие, синхронизирующее набор допустимых
значений в валидаторе с моделью БД (см. `daily_tasks/models.py`).
Сюда добавляются ТОЛЬКО тесты, фиксирующие конкретные исторические
баги, чтобы они не вернулись.

Полный набор unit-тестов валидатора находится в драфте
`tests/test_daily_tasks_validators.py` (не в репо) — он покрывает
ещё много кейсов, но требует синхронизации с реализацией.
"""
from __future__ import annotations

import json

from daily_tasks.pipeline.validators import (
    VALID_SLOT_KINDS,
    validate_gemini_plan,
)


def _make_minimal_gemini_spec(position: int, slot_kind: str = "weak_main") -> dict:
    """Минимальная валидная спецификация задачи Gemini.

    Только обязательные поля — чтобы тест не зависел от мелких
    изменений в опциональных полях валидатора.
    """
    return {
        "position": position,
        "slot_kind": slot_kind,
        "subject": "algebra",
        "topic": f"тема_{position}",
        "subtopic": f"подтема_{position}",
        "difficulty_level": 3,
        "task_archetype": "calc",
        "must_use_concepts": ["концепт"],
        "must_avoid": [],
        "answer_form": "number",
        "estimated_solve_minutes": 5,
        "reason_for_student": "мотивация",
    }


# ───────────────────────────────────────────────────────────────────────
# Регрессия: slot_kind='calibration' в VALID_SLOT_KINDS
# ───────────────────────────────────────────────────────────────────────


def test_valid_slot_kinds_includes_calibration() -> None:
    """`calibration` обязан быть в VALID_SLOT_KINDS.

    История бага:
    -------------
    В рамках PR «percent_to_level + calibration» в модель
    `DailyTaskItem.slot_kind` (см. `daily_tasks/models.py`) был
    добавлен новый допустимый вариант — `'calibration'` (для задач
    по темам, в которых ученик ещё не проходил диагностический тест).
    Планировщик Gemini корректно возвращал такие spec'ы, но
    `VALID_SLOT_KINDS` в `validators.py` про этот вариант не знал,
    из-за чего весь пайплайн падал с ошибкой:
        slot_kind='calibration' недопустим (допустимые: ...)
    Это приводило к failed-state у любого ученика с неполной
    калибровкой профиля (т.е. меньше 7 пройденных тестов).
    """
    assert "calibration" in VALID_SLOT_KINDS, (
        "'calibration' должен быть допустимым slot_kind. "
        "См. daily_tasks/models.py — поле DailyTaskItem.slot_kind."
    )


def test_validate_gemini_plan_accepts_calibration_slot_kind() -> None:
    """Полная валидация JSON-ответа Gemini не должна падать на
    spec'ах с `slot_kind='calibration'`.

    Эмулирует реальный сценарий (ученик 1/7): из 10 spec'ов три
    помечены как калибровочные, остальные семь — обычные слабые.
    """
    specs = [_make_minimal_gemini_spec(i, slot_kind="weak_main") for i in range(1, 11)]
    # Помечаем первые 3 spec'а как калибровочные — как делает планировщик
    # для ученика с малой долей measured-тем.
    for i in (0, 1, 2):
        specs[i]["slot_kind"] = "calibration"

    raw = json.dumps({"specs": specs})
    result = validate_gemini_plan(raw)

    assert result.valid is True, (
        "slot_kind='calibration' должен быть допустим. "
        f"Ошибки: {result.all_errors}"
    )
    slot_kind_errors = [e for e in result.all_errors if "slot_kind" in e]
    assert slot_kind_errors == [], (
        f"Не ожидали ошибок про slot_kind, получили: {slot_kind_errors}"
    )
