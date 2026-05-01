# -*- coding: utf-8 -*-
"""
Tests for OlympiadPipeline orchestrator.
"""
import pytest
from services.pipeline import OlympiadPipeline


class TestOlympiadPipeline:
    """Тесты для OlympiadPipeline."""

    def test_generate_task_not_implemented(self, mock_deepseek, mock_gemini):
        """generate_task пока не реализован."""
        p = OlympiadPipeline(mock_deepseek, mock_gemini)
        with pytest.raises(NotImplementedError):
            p.generate_task("v1", 1, "ВсОШ", "regional", 9)

    def test_generate_variant_not_implemented(self, mock_deepseek, mock_gemini):
        """generate_variant пока не реализован."""
        p = OlympiadPipeline(mock_deepseek, mock_gemini)
        with pytest.raises(NotImplementedError):
            p.generate_variant("ВсОШ", "regional", 9)

    def test_pipeline_has_all_stages(self, mock_deepseek, mock_gemini):
        """Pipeline должен иметь все 6 этапов."""
        p = OlympiadPipeline(mock_deepseek, mock_gemini)
        assert hasattr(p, 's1')
        assert hasattr(p, 's2')
        assert hasattr(p, 's3')
        assert hasattr(p, 's4')
        assert hasattr(p, 's5')
        assert hasattr(p, 's6')
