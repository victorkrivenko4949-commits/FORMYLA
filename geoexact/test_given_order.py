# -*- coding: utf-8 -*-
"""«Равны a и b соответственно»: проверка порядка данных длин (given_order).

Прод-инцидент (задача о медианах, живая генерация 23.10.2026): условие
«медианы из A и B ... равны 9 и 12 соответсвенно» формализатор переложил на
план с переставленными dist (AA_1 = 12, BB_1 = 9). Чертёж самосогласован,
поэтому верификация проходила, и неверный чертёж уходил без предупреждений.
"""
import pytest

from geoexact.core import given_order
from geoexact.core.given_order import _alt, repair
from geoexact.test_angle_marks_layout import _medians_plan

PROBLEM = ("в треугольнике ABC медианы из A и B соотвественно пересекают стороны "
           "в точках A1 и B1, и медианы пересекаються под углом 150% они равны "
           "9 и 12 соответсвенно, найти площадь ABC")


def _swapped():
    """План с переставленными данными (как выдал прод-формализатор)."""
    plan = _medians_plan()
    for c in plan.constraints:
        if c.type == "dist" and set(c.args) == {"A", "A_1"}:
            c.value = 12
        if c.type == "dist" and set(c.args) == {"B", "B_1"}:
            c.value = 9
    plan.draw.length_marks[0]["text"] = "AA_1 = 12"
    plan.draw.length_marks[1]["text"] = "BB_1 = 9"
    return plan


def _dists_of(plan):
    return {frozenset(c.args): c.value for c in plan.constraints if c.type == "dist"}


def test_swapped_order_repaired():
    plan = _swapped()
    assert repair(PROBLEM, plan) is True
    d = _dists_of(plan)
    assert d[frozenset(("A", "A_1"))] == 9
    assert d[frozenset(("B", "B_1"))] == 12
    texts = [m["text"] for m in plan.draw.length_marks]
    assert "AA_1 = 9" in texts and "BB_1 = 12" in texts
    assert "соответственно" in (plan.notes or "")


def test_correct_order_untouched():
    plan = _medians_plan()
    before = _dists_of(plan)
    assert repair(PROBLEM, plan) is False
    assert _dists_of(plan) == before
    assert plan.notes in (None, "")


def test_equal_lengths_not_swapped():
    plan = _swapped()
    for c in plan.constraints:
        if c.type == "dist":
            c.value = 9
    assert repair(PROBLEM, plan) is False


def test_ambiguous_not_repaired():
    """Обе пары условия двусмысленны (каждая точка — в двух dist): нет
    однозначного сигнала — ремонт не запускается."""
    plan = _swapped()
    c0 = type(plan.constraints[0])
    plan.constraints.append(c0(**{"type": "dist", "args": ["A", "B"], "value": 7}))
    plan.constraints.append(c0(**{"type": "dist", "args": ["A_1", "C"], "value": 5}))
    assert repair(PROBLEM, plan) is False


def test_alt_name_normalization():
    assert _alt("A1") == "A_1"
    assert _alt("A") == "A"
    assert _alt("M_1") == "M_1"


def test_install_wraps_formalize():
    class FakeLLM:
        SYS_FORMALIZE = "BASE PROMPT"
        SYS_AUX = "BASE PROMPT" + " + AUX"

        @staticmethod
        def formalize(sess, text, *a, **k):
            return _swapped(), []

    assert given_order.install(FakeLLM) is True
    assert "GIVEN_ORDER" in FakeLLM.SYS_FORMALIZE
    assert "GIVEN_ORDER" in FakeLLM.SYS_AUX
    assert "36." in FakeLLM.SYS_FORMALIZE
    plan, warn = FakeLLM.formalize(None, PROBLEM)
    assert warn and warn[0].startswith("GIVEN_ORDER_FIXED")
    assert _dists_of(plan)[frozenset(("A", "A_1"))] == 9


def test_install_idempotent():
    class FakeLLM2:
        SYS_FORMALIZE = "BASE"

        @staticmethod
        def formalize(sess, text, *a, **k):
            return _medians_plan(), []

    given_order.install(FakeLLM2)
    wrapped = FakeLLM2.formalize
    given_order.install(FakeLLM2)               # повторно — no-op
    assert FakeLLM2.formalize is wrapped
