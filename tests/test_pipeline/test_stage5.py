# -*- coding: utf-8 -*-
"""
Tests for Stage 5: Validate LaTeX (pure regex).
"""
import pytest
from services.pipeline.stage5_validate import Stage5Validate
from services.pipeline.types import (
    ProcessedTask, RewrittenTask, FoundTask, ValidationResult,
)


def _make_processed(text: str) -> ProcessedTask:
    """Helper: создаёт ProcessedTask с заданным текстом."""
    f = FoundTask(
        olympiad="ВсОШ", year=2019, stage="regional",
        grade=9, problem_number=1, topic="x", difficulty="medium",
        original_text="orig", confidence=0.9,
    )
    r = RewrittenTask(
        original=f, rewritten_text="r",
        changes=["a", "b", "c"], method_preserved="m",
        difficulty_same=True,
    )
    return ProcessedTask(
        rewritten=r, processed_text=text, formulas_count=1,
    )


class TestStage5Validate:
    """Тесты для Stage5Validate."""

    def setup_method(self):
        self.v = Stage5Validate()

    # ─── Положительные сценарии ───

    def test_valid_simple_formula(self):
        """Простая формула $x^2 + y^2 = 25$ проходит."""
        p = _make_processed(
            "Найдите $x^2 + y^2 = 25$ в целых числах."
        )
        r = self.v.validate(p)
        assert r.is_valid, r.errors

    def test_valid_sqrt_frac(self):
        """\\sqrt{x} и \\frac{1}{2} с правильными скобками проходят."""
        p = _make_processed(
            "Докажите $\\sqrt{x} + \\frac{1}{2} \\geq 0$ для x > 0."
        )
        r = self.v.validate(p)
        assert r.is_valid, r.errors

    def test_valid_display_formula(self):
        """Display-формула $$...$$ проходит."""
        p = _make_processed(
            "Формула: $$\\sum_{i=1}^{n} i^2 = "
            "\\frac{n(n+1)(2n+1)}{6}$$ где n натуральное."
        )
        r = self.v.validate(p)
        assert r.is_valid, r.errors

    def test_valid_single_char_sub_sup(self):
        """Одиночные индексы/степени без скобок — ок."""
        p = _make_processed(
            "Пусть $a_1, a_2, x^n, S_n$ даны."
        )
        r = self.v.validate(p)
        assert r.is_valid, r.errors

    def test_valid_complex_index(self):
        """Сложный индекс в скобках $S_{m+1}$ — ок."""
        p = _make_processed(
            "Рассмотрим $S_{m+1} = 4 \\cdot S_m$ для некоторого m."
        )
        r = self.v.validate(p)
        assert r.is_valid, r.errors

    def test_valid_geometry(self):
        """Геометрические обозначения проходят."""
        p = _make_processed(
            "В $\\triangle ABC$ угол $\\angle A = 60^\\circ$ "
            "и сторона равна $5$."
        )
        r = self.v.validate(p)
        assert r.is_valid, r.errors

    # ─── \\sqrt ошибки ───

    def test_sqrt_without_braces(self):
        """\\sqrta → ошибка (нет скобок)."""
        p = _make_processed(
            "Формула $\\sqrta + b = c$ доказывается."
        )
        r = self.v.validate(p)
        assert not r.is_valid
        assert any('sqrt' in e.lower() for e in r.errors)

    def test_sqrt_with_space(self):
        """\\sqrt a → ошибка (пробел вместо скобок)."""
        p = _make_processed(
            "Формула $\\sqrt a + b = c$ доказывается."
        )
        r = self.v.validate(p)
        assert not r.is_valid
        assert any('sqrt' in e.lower() for e in r.errors)

    # ─── \\frac ошибки ───

    def test_frac_without_braces(self):
        """\\frac 1 2 → ошибка (без скобок)."""
        p = _make_processed(
            "Дробь $\\frac 1 2$ встречается часто в задачах."
        )
        r = self.v.validate(p)
        assert not r.is_valid
        assert any('frac' in e.lower() for e in r.errors)

    def test_frac_missing_second_arg(self):
        """\\frac{a}b → ошибка (второй аргумент без скобок)."""
        p = _make_processed(
            "Выражение $\\frac{a}b$ записано неверно для пробы."
        )
        r = self.v.validate(p)
        assert not r.is_valid

    # ─── Степени / индексы ───

    def test_long_exponent_without_braces(self):
        """x^10 → ошибка (степень >1 символа без скобок)."""
        p = _make_processed(
            "Число $x^10 + y^20$ — большое значение."
        )
        r = self.v.validate(p)
        assert not r.is_valid
        assert any(
            'степен' in e.lower() or 'индекс' in e.lower()
            for e in r.errors
        )

    def test_long_index_without_braces(self):
        """a_12 → ошибка (индекс >1 символа без скобок)."""
        p = _make_processed(
            "Последовательность $a_12, a_13$ задана рекурсивно."
        )
        r = self.v.validate(p)
        assert not r.is_valid

    # ─── Двойные индексы ───

    def test_double_index_plus(self):
        """S_m+_{1} → ошибка (подчерк после +)."""
        p = _make_processed(
            "Выражение $S_m+_{1} = 4 S_m$ здесь."
        )
        r = self.v.validate(p)
        assert not r.is_valid
        assert any(
            'двойной' in e.lower() or 'подчерк' in e.lower()
            for e in r.errors
        )

    def test_double_index_minus(self):
        """a_n -_{1} → ошибка (подчерк после -)."""
        p = _make_processed(
            "Выражение $a_n -_{1} = 0$ для всех n."
        )
        r = self.v.validate(p)
        assert not r.is_valid

    # ─── Юникод ───

    def test_unicode_geq_in_math(self):
        """≥ внутри $...$ → ошибка (должен быть \\geq)."""
        p = _make_processed(
            "Докажите $a + b ≥ 2\\sqrt{ab}$ для положительных."
        )
        r = self.v.validate(p)
        assert not r.is_valid
        assert any('≥' in e or 'geq' in e for e in r.errors)

    def test_unicode_allowed_in_plain_text(self):
        """≥ вне $...$ — разрешено (в обычном тексте)."""
        p = _make_processed(
            "Для x ≥ 0 рассмотрим $\\sqrt{x}$ и найдите минимум."
        )
        r = self.v.validate(p)
        assert r.is_valid, r.errors

    def test_unicode_cdot_in_math(self):
        """· внутри $...$ → ошибка (должен быть \\cdot)."""
        p = _make_processed(
            "Вычислите $2 · 3 = 6$ аккуратно."
        )
        r = self.v.validate(p)
        assert not r.is_valid

    # ─── Непарные $ ───

    def test_unpaired_dollar(self):
        """Непарный $ → ошибка."""
        p = _make_processed(
            "Формула $x + y = 5$ и $z = 3 неверна здесь."
        )
        r = self.v.validate(p)
        assert not r.is_valid
        assert any('непарн' in e.lower() for e in r.errors)

    def test_empty_dollars(self):
        """Пустая формула $$ $$ → ошибка."""
        p = _make_processed(
            "Текст $$ $$ пустой и ещё один текст длинный."
        )
        r = self.v.validate(p)
        assert not r.is_valid
        assert any('пуст' in e.lower() for e in r.errors)

    # ─── LaTeX-утечка в обычный текст ───

    def test_latex_command_outside_dollars(self):
        """\\sqrt{x} вне $...$ → ошибка."""
        p = _make_processed(
            "Выражение \\sqrt{x} записано неправильно "
            "вне формулы здесь."
        )
        r = self.v.validate(p)
        assert not r.is_valid
        assert any('вне' in e.lower() for e in r.errors)

    # ─── Неподдерживаемые команды ───

    def test_align_not_supported(self):
        """\\begin{align} → ошибка (KaTeX не поддерживает)."""
        p = _make_processed(
            "Система: $$\\begin{align} x &= 1 \\\\ "
            "y &= 2 \\end{align}$$ решение."
        )
        r = self.v.validate(p)
        assert not r.is_valid
        assert any('align' in e.lower() for e in r.errors)

    # ─── Несколько ошибок одновременно ───

    def test_multiple_errors_reported(self):
        """Несколько ошибок в одной формуле → все репортятся."""
        p = _make_processed(
            "Плохо: $\\sqrta + x^10 ≥ 0$ длинная формула здесь."
        )
        r = self.v.validate(p)
        assert not r.is_valid
        assert len(r.errors) >= 3  # sqrt + степень + юникод

    # ─── Структура ответа ───

    def test_returns_validation_result(self):
        """Возвращает ValidationResult."""
        p = _make_processed(
            "Просто $x$ и всё нормально с длиной текста здесь."
        )
        r = self.v.validate(p)
        assert isinstance(r, ValidationResult)
        assert isinstance(r.is_valid, bool)
        assert isinstance(r.errors, list)

    def test_error_messages_are_strings(self):
        """Ошибки — непустые строки."""
        p = _make_processed(
            "Плохо: $\\sqrta$ длинное условие задачи здесь."
        )
        r = self.v.validate(p)
        for e in r.errors:
            assert isinstance(e, str) and len(e) > 0
