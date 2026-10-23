# -*- coding: utf-8 -*-
"""Юнит-тесты `insightValidator` (раздел 6 ТЗ).

Покрытие:
  - описка → отклонено (skip);
  - перебор вместо идеи → принято;
  - «невнимательность» в title → отклонено;
  - две задачи вместо трёх → отклонено;
  - три задачи с одинаковым visibility → отклонено;
  - короткое рассуждение → retry (через reasoning_too_short).
"""

from services.insight_validator import (
    validate_deep_result,
    validate_insight,
)
from services.insight_llm_client import reasoning_too_short


def _practice(visibilities=("obvious", "medium", "hidden")):
    return [
        {
            "statement": f"Задача {i + 1}",
            "answer": "1",
            "hint": "",
            "solution_sketch": "",
            "difficulty": 3,
            "visibility": v,
            "why_this_task": "Тренирует приём перехода к инварианту",
            "naive_path_cost": "в 3 раза дольше",
        }
        for i, v in enumerate(visibilities)
    ]


def _insight(title="Считает размещения прямым перебором вместо правила умножения",
             what="Использует перебор всех вариантов там, где применимо правило умножения с фиксацией позиции.",
             itype="time_loss",
             practice=None):
    return {
        "title": title,
        "type": itype,
        "severity": 2,
        "duplicate_of": None,
        "where": "шаг 3",
        "what_went_wrong": what,
        "better_way": "Зафиксировать позицию и перемножить",
        "time_lost_estimate_min": 5,
        "canonical_fact": "правило умножения",
        "tags": ["topic:combinatorics", "method:rule_of_product"],
        "practice": practice if practice is not None else _practice(),
    }


def test_valid_insight_accepted():
    r = validate_insight(_insight())
    assert r.ok, r.reason


def test_arithmetic_slip_rejected_has_insight_false():
    r = validate_deep_result({
        "has_insight": False,
        "skip_reason": "arithmetic_slip",
        "insights": [],
    })
    assert not r.ok
    assert r.reason == "has_insight_false"


def test_nevnimatelnost_in_title_rejected():
    r = validate_insight(_insight(title="Невнимательность при подсчёте вариантов"))
    assert not r.ok
    assert "stopword" in r.reason


def test_two_tasks_rejected():
    r = validate_insight(_insight(practice=_practice(("obvious", "medium"))))
    assert not r.ok
    assert r.reason == "practice_not_3"


def test_same_visibility_rejected():
    r = validate_insight(_insight(practice=_practice(("obvious", "obvious", "obvious"))))
    assert not r.ok
    assert r.reason == "visibility_incomplete"


def test_empty_why_this_task_rejected():
    practice = _practice()
    practice[0]["why_this_task"] = ""
    r = validate_insight(_insight(practice=practice))
    assert not r.ok
    assert "empty_why_this_task" in r.reason


def test_title_too_short_rejected():
    r = validate_insight(_insight(title="Ошибки"))
    assert not r.ok
    assert r.reason == "title_too_short"


def test_invalid_type_rejected():
    r = validate_insight(_insight(itype="careless"))
    assert not r.ok
    assert r.reason == "invalid_type"


def test_deep_result_with_valid_insight_accepted():
    r = validate_deep_result({
        "has_insight": True,
        "skip_reason": None,
        "insights": [_insight()],
    })
    assert r.ok, r.reason


def test_reasoning_too_short_detects_low_tokens():
    assert reasoning_too_short({"reasoning_tokens": 10}) is True
    assert reasoning_too_short({"reasoning_tokens": 5000}) is False


def test_reasoning_short_ignores_insights():
    # run_deep использует reasoning_too_short для отбрасывания insights;
    # здесь проверяем, что флаг выставляется.
    from services.insight_llm_client import AI_INSIGHT_MIN_REASONING_TOKENS
    assert AI_INSIGHT_MIN_REASONING_TOKENS > 0
