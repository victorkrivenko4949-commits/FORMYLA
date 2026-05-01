# -*- coding: utf-8 -*-
"""
Tests for Stage 5: Validate LaTeX.
"""
import pytest
from services.pipeline.stage5_validate import Stage5Validate
from services.pipeline.types import ProcessedTask, ValidationResult


class TestStage5Validate:
    """Тесты для Stage5Validate."""

    def test_not_implemented_yet(self):
        """Stage 5 пока не реализован."""
        v = Stage5Validate()
        with pytest.raises(NotImplementedError):
            v.validate(None)

    def test_sqrt_without_braces_fails(self):
        """\\sqrt без фигурных скобок должен не пройти валидацию."""
        # Будет реализовано на шаге 6
        pass

    def test_double_index_fails(self):
        """Двойные индексы (a_1_2) должны не пройти валидацию."""
        # Будет реализовано на шаге 6
        pass

    def test_unicode_outside_dollars_fails(self):
        """Unicode-символы (∠, °, √) вне $...$ должны не пройти."""
        # Будет реализовано на шаге 6
        pass

    def test_valid_latex_passes(self):
        """Корректный LaTeX должен пройти валидацию."""
        # Будет реализовано на шаге 6
        pass

    def test_unclosed_dollar_fails(self):
        """Незакрытый $...$ должен не пройти."""
        # Будет реализовано на шаге 6
        pass

    def test_bare_variable_fails(self):
        """Голая переменная вне LaTeX должна не пройти."""
        # Будет реализовано на шаге 6
        pass

    def test_frac_without_two_args_fails(self):
        """\\frac без двух аргументов должен не пройти."""
        # Будет реализовано на шаге 6
        pass

    def test_bare_degree_sign_fails(self):
        """Голый символ ° вне LaTeX должен не пройти."""
        # Будет реализовано на шаге 6
        pass

    def test_bare_power_notation_fails(self):
        """x2 вместо $x^2$ должен не пройти."""
        # Будет реализовано на шаге 6
        pass
