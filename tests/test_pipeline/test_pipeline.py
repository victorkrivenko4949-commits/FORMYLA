# -*- coding: utf-8 -*-
"""
Tests for OlympiadPipeline orchestrator.
"""
import pytest
from unittest.mock import MagicMock, patch
from services.pipeline import OlympiadPipeline
from services.pipeline.pipeline import MAX_UNIQUENESS_ATTEMPTS, MAX_LATEX_ATTEMPTS
from services.pipeline.types import (
    FoundTask, RewrittenTask, ProcessedTask, ValidationResult,
    PipelineResult, PipelineError,
)


@pytest.fixture
def mock_stages():
    """Моки всех 6 этапов с валидными данными."""
    found = FoundTask(
        olympiad="ВсОШ", year=2019, stage="regional",
        grade=9, problem_number=3, topic="t", difficulty="m",
        original_text="x" * 50, confidence=0.9,
    )
    rewritten = RewrittenTask(
        original=found, rewritten_text="y" * 50,
        changes=["a", "b", "c"], method_preserved="x",
        difficulty_same=True,
    )
    processed = ProcessedTask(
        rewritten=rewritten,
        processed_text="Final $x^2$ длинное условие задачи здесь.",
        formulas_count=1,
    )
    return found, rewritten, processed


def _make_pipeline(found, rewritten, processed,
                   unique_results=None, valid_results=None):
    """Helper: создаёт pipeline с замоканными этапами."""
    p = OlympiadPipeline.__new__(OlympiadPipeline)
    p.s1 = MagicMock()
    p.s1.find.return_value = found
    p.s2 = MagicMock()
    p.s2.rewrite.return_value = rewritten
    p.s3 = MagicMock()
    p.s3.is_unique.return_value = True if unique_results is None else None
    if unique_results is not None:
        p.s3.is_unique.side_effect = unique_results
    p.s4 = MagicMock()
    p.s4.process.return_value = processed
    p.s5 = MagicMock()
    if valid_results is None:
        p.s5.validate.return_value = ValidationResult(
            is_valid=True, errors=[],
        )
    else:
        p.s5.validate.side_effect = valid_results
    p.s6 = MagicMock()
    p.s6.save_task.return_value = PipelineResult(
        task_id=1, variant_id="v1", position=1,
        final_text="x", stages_log=[],
    )
    return p


class TestOlympiadPipeline:
    """Тесты для OlympiadPipeline."""

    def test_happy_path(self, mock_stages):
        """Все этапы проходят с первой попытки."""
        found, rewritten, processed = mock_stages
        p = _make_pipeline(found, rewritten, processed)

        result = p.generate_task("v1", 1, "ВсОШ", "regional", 9)

        assert result.task_id == 1
        p.s1.find.assert_called_once()
        p.s2.rewrite.assert_called_once()
        p.s3.is_unique.assert_called_once()
        p.s4.process.assert_called_once()
        p.s5.validate.assert_called_once()
        p.s6.save_task.assert_called_once()

    def test_retries_on_not_unique(self, mock_stages):
        """Stage 3 не уникальна → retry Stage 2+3."""
        found, rewritten, processed = mock_stages
        p = _make_pipeline(
            found, rewritten, processed,
            unique_results=[False, False, True],
        )

        result = p.generate_task("v1", 1, "ВсОШ", "regional", 9)

        assert p.s2.rewrite.call_count == 3
        assert p.s3.is_unique.call_count == 3

    def test_fails_after_uniqueness_exhausted(self, mock_stages):
        """Stage 3 всегда False → PipelineError stage3."""
        found, rewritten, processed = mock_stages
        p = _make_pipeline(
            found, rewritten, processed,
            unique_results=[False, False, False],
        )

        with pytest.raises(PipelineError) as exc:
            p.generate_task("v1", 1, "ВсОШ", "regional", 9)
        assert exc.value.stage == "stage3"

    def test_retries_on_invalid_latex(self, mock_stages):
        """Stage 5 невалидна → retry Stage 4+5 с previous_errors."""
        found, rewritten, processed = mock_stages
        p = _make_pipeline(
            found, rewritten, processed,
            valid_results=[
                ValidationResult(
                    is_valid=False, errors=["\\sqrt без {}"],
                ),
                ValidationResult(
                    is_valid=False, errors=["Непарные $"],
                ),
                ValidationResult(is_valid=True, errors=[]),
            ],
        )

        result = p.generate_task("v1", 1, "ВсОШ", "regional", 9)

        assert p.s4.process.call_count == 3
        # Вторая попытка получила ошибки первой
        second_call = p.s4.process.call_args_list[1]
        assert "\\sqrt без {}" in second_call.kwargs["previous_errors"]
        # Третья попытка получила ошибки второй
        third_call = p.s4.process.call_args_list[2]
        assert "Непарные $" in third_call.kwargs["previous_errors"]

    def test_fails_after_latex_exhausted(self, mock_stages):
        """Stage 5 всегда невалидна → PipelineError stage5."""
        found, rewritten, processed = mock_stages
        p = _make_pipeline(
            found, rewritten, processed,
            valid_results=[
                ValidationResult(is_valid=False, errors=["err"]),
                ValidationResult(is_valid=False, errors=["err"]),
                ValidationResult(is_valid=False, errors=["err"]),
            ],
        )

        with pytest.raises(PipelineError) as exc:
            p.generate_task("v1", 1, "ВсОШ", "regional", 9)
        assert exc.value.stage == "stage5"

    def test_stages_log_recorded(self, mock_stages):
        """stages_log содержит записи всех этапов."""
        found, rewritten, processed = mock_stages
        p = _make_pipeline(found, rewritten, processed)

        p.generate_task("v1", 1, "ВсОШ", "regional", 9)

        # stages_log передаётся в s6.save_task
        call_args = p.s6.save_task.call_args
        stages_log = call_args.args[3] if len(call_args.args) > 3 else call_args.kwargs.get('stages_log', [])
        stage_numbers = [e["stage"] for e in stages_log]
        assert 1 in stage_numbers
        assert 2 in stage_numbers
        assert 3 in stage_numbers
        assert 4 in stage_numbers
        assert 5 in stage_numbers

    def test_stage1_failure_raises_pipeline_error(self, mock_stages):
        """Stage 1 ошибка → PipelineError stage1."""
        found, rewritten, processed = mock_stages
        p = _make_pipeline(found, rewritten, processed)
        from services.pipeline.stage1_find import Stage1Error
        p.s1.find.side_effect = Stage1Error("not found")

        with pytest.raises(PipelineError) as exc:
            p.generate_task("v1", 1, "ВсОШ", "regional", 9)
        assert exc.value.stage == "stage1"

    def test_pipeline_has_all_stages(self, mock_deepseek, mock_gemini):
        """Pipeline должен иметь все 6 этапов."""
        p = OlympiadPipeline(mock_deepseek, mock_gemini)
        assert hasattr(p, 's1')
        assert hasattr(p, 's2')
        assert hasattr(p, 's3')
        assert hasattr(p, 's4')
        assert hasattr(p, 's5')
        assert hasattr(p, 's6')
