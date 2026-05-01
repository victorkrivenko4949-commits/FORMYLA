# -*- coding: utf-8 -*-
"""
Stage 5: Валидация LaTeX (pure regex, без LLM).
"""
from .types import ProcessedTask, ValidationResult


class Stage5Validate:
    """Валидирует LaTeX в задаче с помощью регулярных выражений."""

    def validate(self, processed: ProcessedTask) -> ValidationResult:
        """
        Проверяет корректность LaTeX в тексте задачи.

        Проверки:
        - \\sqrt без фигурных скобок
        - Двойные индексы (a_1_2)
        - Unicode-символы вне $...$ (∠, °, √, ≤, ≥, ≠)
        - Незакрытые $...$ или $$...$$
        - \\frac без двух аргументов
        - Голые переменные вне LaTeX

        Args:
            processed: задача из Stage 4

        Returns:
            ValidationResult с is_valid и списком ошибок

        Raises:
            NotImplementedError: пока не реализовано
        """
        raise NotImplementedError("Stage 5 будет реализован на шаге 6")
