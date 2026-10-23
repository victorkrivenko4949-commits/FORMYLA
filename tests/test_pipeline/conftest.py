# -*- coding: utf-8 -*-
"""
Fixtures for pipeline tests.
"""
import pytest
from unittest.mock import MagicMock


@pytest.fixture
def mock_deepseek():
    """Mock DeepSeekClient."""
    client = MagicMock()
    client.generate = MagicMock(return_value='{}')
    return client


@pytest.fixture
def mock_gemini():
    """Mock GeminiClient."""
    client = MagicMock()
    client.generate = MagicMock(return_value='{}')
    return client


@pytest.fixture
def sample_found_task():
    """Пример найденного прототипа задачи."""
    from services.pipeline.types import FoundTask
    return FoundTask(
        olympiad="ВсОШ",
        year=2019,
        stage="regional",
        grade=9,
        problem_number=3,
        topic="неравенства",
        difficulty="medium",
        original_text=(
            "Для положительных чисел $a$, $b$, $c$ с условием "
            "$a + b + c = 1$ докажите, что "
            "$\\frac{1}{a} + \\frac{1}{b} + \\frac{1}{c} \\geq 9$."
        ),
        author="Н. Агаханов",
        confidence=0.9,
    )


@pytest.fixture
def sample_rewritten_task(sample_found_task):
    """Пример переписанной задачи."""
    from services.pipeline.types import RewrittenTask
    return RewrittenTask(
        original=sample_found_task,
        rewritten_text=(
            "Пусть $x$, $y$, $z$ — положительные числа, сумма которых "
            "равна $3$. Докажите, что "
            "$\\frac{1}{x} + \\frac{1}{y} + \\frac{1}{z} \\geq 3$."
        ),
        solution="По неравенству AM-HM...",
        answer="требуется доказательство",
        changes=["числа", "переменные", "формулировка"],
        method_preserved="AM-HM неравенство",
        difficulty_same=True,
    )


@pytest.fixture
def sample_processed_task(sample_rewritten_task):
    """Пример задачи после LaTeX-обработки."""
    from services.pipeline.types import ProcessedTask
    return ProcessedTask(
        rewritten=sample_rewritten_task,
        processed_text=(
            "Пусть $x$, $y$, $z$ — положительные числа, сумма которых "
            "равна $3$. Докажите, что "
            "$\\frac{1}{x} + \\frac{1}{y} + \\frac{1}{z} \\geq 3$."
        ),
        processed_solution="По неравенству AM-HM...",
        formulas_count=5,
        notes="",
    )
