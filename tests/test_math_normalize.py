# -*- coding: utf-8 -*-
"""Тесты нормализатора формул «Задач дня»."""
from daily_tasks.math_normalize import (
    normalize_math_full,
    normalize_hints_json,
    normalize_task_item,
)


def test_slash_fraction_and_unicode_sqrt_inside_math():
    src = "Найдите наименьшее значение выражения $(x^2+2)/√(x^2+1)$, где x — число."
    assert normalize_math_full(src) == (
        "Найдите наименьшее значение выражения $\\frac{x^2+2}{\\sqrt{x^2+1}}$, где x — число."
    )


def test_good_latex_untouched():
    src = "Числа $x$ и $y$ принадлежат отрезку $[0;1]$. $$x\\sqrt{1-y^2}+y\\sqrt{1-x^2}.$$"
    assert normalize_math_full(src) == src


def test_bare_commands_get_wrapped():
    src = "Вычислите √5 + \\frac{1}{2}, дробь 3/4, угол 60°."
    assert normalize_math_full(src) == (
        "Вычислите $\\sqrt{5} + \\frac{1}{2}$, дробь $\\frac{3}{4}$, угол $60^{\\circ}$."
    )


def test_plain_text_and_dates_untouched():
    src = "Обычный текст, 2025 год, дата 12/10/2025."
    assert normalize_math_full(src) == src


def test_idempotent():
    src = "Решите $\\sqrt(x+1)/x = 1/2$ и √3."
    once = normalize_math_full(src)
    assert normalize_math_full(once) == once


def test_hints_json():
    out = normalize_hints_json('["Подставь x=1/2", "Корень √(x+1)"]')
    assert "\\\\frac{1}{2}" in out and "\\\\sqrt{x+1}" in out


def test_task_item():
    item = normalize_task_item({"task_text": "$a/b$", "hints": ["√2"]})
    assert item["task_text"] == "$\\frac{a}{b}$"
    assert item["hints"] == ["$\\sqrt{2}$"]
