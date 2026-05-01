# -*- coding: utf-8 -*-
"""
Tests for Stage 1: Find prototype task.
"""
import pytest
from services.pipeline.stage1_find import Stage1Find
from services.pipeline.types import FoundTask


class TestStage1Find:
    """Тесты для Stage1Find."""

    def test_returns_found_task(self, mock_deepseek):
        """Stage 1 должен возвращать FoundTask (пока NotImplementedError)."""
        s1 = Stage1Find(mock_deepseek)
        with pytest.raises(NotImplementedError):
            s1.find("ВсОШ", "regional", 9)

    def test_confidence_below_threshold_raises(self, mock_deepseek):
        """Если confidence < порога — должен перегенерировать."""
        # Будет реализовано на шаге 2
        pass

    def test_invalid_json_retries(self, mock_deepseek):
        """Если LLM вернул невалидный JSON — retry."""
        # Будет реализовано на шаге 2
        pass
