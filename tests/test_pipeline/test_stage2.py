# -*- coding: utf-8 -*-
"""
Tests for Stage 2: Rewrite task.
"""
import pytest
from services.pipeline.stage2_rewrite import Stage2Rewrite
from services.pipeline.types import RewrittenTask


class TestStage2Rewrite:
    """Тесты для Stage2Rewrite."""

    def test_returns_rewritten_task(self, mock_deepseek, sample_found_task):
        """Stage 2 должен возвращать RewrittenTask (пока NotImplementedError)."""
        s2 = Stage2Rewrite(mock_deepseek)
        with pytest.raises(NotImplementedError):
            s2.rewrite(sample_found_task)

    def test_rewrite_no_latex_leakage(self, mock_deepseek):
        """Переписанная задача не должна содержать LaTeX-артефакты."""
        # Будет реализовано на шаге 3
        pass

    def test_rewrite_preserves_method(self, mock_deepseek):
        """Метод решения должен быть сохранён."""
        # Будет реализовано на шаге 3
        pass
