# -*- coding: utf-8 -*-
"""
Tests for Stage 6: Save to DB.
"""
import json
import pytest
from unittest.mock import MagicMock, patch
from services.pipeline.stage6_save import Stage6Save, Stage6Error
from services.pipeline.types import (
    ProcessedTask, RewrittenTask, FoundTask, PipelineResult,
)


def _sample_processed():
    """Helper: создаёт ProcessedTask для тестов."""
    f = FoundTask(
        olympiad="ВсОШ", year=2019, stage="regional",
        grade=9, problem_number=3, topic="неравенства",
        difficulty="medium", original_text="orig text here",
        author="N.A.", confidence=0.9,
    )
    r = RewrittenTask(
        original=f, rewritten_text="rewritten text",
        solution="Решение: шаг 1, шаг 2",
        answer="42",
        changes=["a", "b", "c"], method_preserved="Cauchy",
        difficulty_same=True,
    )
    return ProcessedTask(
        rewritten=r,
        processed_text="Final $x^2$ text длинное условие задачи.",
        formulas_count=1, notes="ok",
    )


class TestStage6Save:
    """Тесты для Stage6Save."""

    @patch('models.db')
    @patch('models.OlympiadTask')
    def test_save_creates_task_and_returns_result(self, MockTask, mock_db):
        """save_task создаёт OlympiadTask и возвращает PipelineResult."""
        mock_instance = MagicMock()
        mock_instance.id = 42
        MockTask.return_value = mock_instance

        s6 = Stage6Save()
        result = s6.save_task(
            "v-uuid", 1, _sample_processed(),
            stages_log=[{"stage": 1}],
        )

        assert isinstance(result, PipelineResult)
        assert result.task_id == 42
        assert result.variant_id == "v-uuid"
        assert result.position == 1
        assert "Final" in result.final_text
        mock_db.session.add.assert_called_once_with(mock_instance)
        mock_db.session.flush.assert_called_once()

    @patch('models.db')
    @patch('models.OlympiadTask')
    def test_save_sets_correct_fields(self, MockTask, mock_db):
        """save_task устанавливает все поля OlympiadTask."""
        mock_instance = MagicMock()
        mock_instance.id = 7
        MockTask.return_value = mock_instance

        s6 = Stage6Save()
        s6.save_task("v1", 2, _sample_processed(), [])

        kwargs = MockTask.call_args.kwargs
        assert kwargs['variant_id'] == 'v1'
        assert kwargs['position'] == 2
        assert kwargs['status'] == 'validated'
        assert kwargs['topic'] == 'неравенства'
        assert kwargs['source_year'] == 2019
        assert kwargs['source_problem'] == 3
        assert kwargs['author'] == 'N.A.'
        assert kwargs['pipeline_version'] == '1.0'
        assert kwargs['validation_errors'] is None
        assert 'orig text' in kwargs['original_text']

    @patch('models.db')
    @patch('models.OlympiadTask')
    def test_save_rollback_on_error(self, MockTask, mock_db):
        """Ошибка БД → rollback + Stage6Error."""
        MockTask.return_value = MagicMock()
        mock_db.session.add.side_effect = Exception("DB error")

        s6 = Stage6Save()
        with pytest.raises(Stage6Error, match="Ошибка сохранения"):
            s6.save_task("v1", 1, _sample_processed(), [])
        mock_db.session.rollback.assert_called_once()

    @patch('models.db')
    @patch('models.OlympiadTask')
    def test_save_failed_task_sets_status(self, MockTask, mock_db):
        """save_failed_task сохраняет задачу со статусом 'failed'."""
        mock_instance = MagicMock()
        mock_instance.id = 99
        MockTask.return_value = mock_instance

        s6 = Stage6Save()
        s6.save_failed_task(
            "v1", 2, "broken text",
            ["err1", "err2"], [],
        )

        kwargs = MockTask.call_args.kwargs
        assert kwargs['status'] == 'failed'
        assert 'err1' in kwargs['validation_errors']
        assert 'err2' in kwargs['validation_errors']
        mock_db.session.add.assert_called_once()
        mock_db.session.flush.assert_called_once()
