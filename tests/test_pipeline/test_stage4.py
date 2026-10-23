# -*- coding: utf-8 -*-
"""
Tests for Stage 4: LaTeX formatting via Gemini.
"""
import json
import pytest
from unittest.mock import MagicMock
from services.pipeline.stage4_latex import Stage4Latex, Stage4Error
from services.pipeline.types import (
    RewrittenTask, FoundTask, ProcessedTask,
)


@pytest.fixture
def sample_rewritten_s4():
    """Переписанная задача для тестов Stage 4."""
    f = FoundTask(
        olympiad="ВсОШ",
        year=2019,
        stage="regional",
        grade=9,
        problem_number=3,
        topic="неравенства",
        difficulty="medium",
        original_text="оригинал",
        confidence=0.9,
    )
    return RewrittenTask(
        original=f,
        rewritten_text=(
            "Для положительных чисел x, y, z с суммой 2 докажите, "
            "что √(x/(y+z)) + √(y/(x+z)) + √(z/(x+y)) ≥ 3/√2."
        ),
        changes=["a->x", "1->2", "доб знаменатель"],
        method_preserved="Коши",
        difficulty_same=True,
    )


def _good_response(**overrides):
    """Helper: возвращает валидный JSON-ответ Stage 4."""
    data = {
        "processed_text": (
            "Для положительных чисел $x, y, z$ с $x+y+z=2$ докажите, "
            "что $\\sqrt{\\dfrac{x}{y+z}} + \\sqrt{\\dfrac{y}{x+z}} "
            "+ \\sqrt{\\dfrac{z}{x+y}} \\geq \\dfrac{3}{\\sqrt{2}}$."
        ),
        "formulas_count": 3,
        "notes": "обёрнуто в $, замены сделаны",
    }
    data.update(overrides)
    return json.dumps(data, ensure_ascii=False)


class TestStage4Latex:
    """Тесты для Stage4Latex."""

    def test_happy_path(self, mock_gemini, sample_rewritten_s4):
        """Успешное оформление LaTeX с первой попытки."""
        mock_gemini.generate.return_value = _good_response()
        s4 = Stage4Latex(mock_gemini)
        result = s4.process(sample_rewritten_s4)
        assert isinstance(result, ProcessedTask)
        assert result.rewritten is sample_rewritten_s4
        assert '$' in result.processed_text
        assert result.formulas_count == 3
        mock_gemini.generate.assert_called_once()

    def test_strips_markdown_fence(self, mock_gemini, sample_rewritten_s4):
        """JSON обёрнутый в ```json ... ``` должен парситься."""
        raw = "```json\n" + _good_response() + "\n```"
        mock_gemini.generate.return_value = raw
        s4 = Stage4Latex(mock_gemini)
        result = s4.process(sample_rewritten_s4)
        assert result.processed_text

    def test_unpaired_dollars_rejected(self, mock_gemini, sample_rewritten_s4):
        """Непарное количество $ -> отклонение."""
        mock_gemini.generate.return_value = json.dumps({
            "processed_text": (
                "Для $x$ и $y$ и $z с суммой два докажите "
                "что корень из дроби больше единицы."
            ),
            "formulas_count": 1,
            "notes": "",
        }, ensure_ascii=False)
        s4 = Stage4Latex(mock_gemini)
        with pytest.raises(Stage4Error, match="Непарное"):
            s4.process(sample_rewritten_s4)

    def test_triple_dollar_rejected(self, mock_gemini, sample_rewritten_s4):
        """$$$ в тексте -> отклонение (склейка inline + display)."""
        mock_gemini.generate.return_value = _good_response(
            processed_text=(
                "Условие $$$x$$$ формула длиной больше "
                "тридцати символов здесь обязательно."
            )
        )
        s4 = Stage4Latex(mock_gemini)
        with pytest.raises(Stage4Error, match=r"\$\$\$"):
            s4.process(sample_rewritten_s4)

    def test_short_text_rejected(self, mock_gemini, sample_rewritten_s4):
        """Слишком короткий текст -> отклонение."""
        mock_gemini.generate.return_value = _good_response(
            processed_text="Коротко."
        )
        s4 = Stage4Latex(mock_gemini)
        with pytest.raises(Stage4Error, match="коротк"):
            s4.process(sample_rewritten_s4)

    def test_invalid_json_retries(self, mock_gemini, sample_rewritten_s4):
        """Невалидный JSON -> retry -> на 3-й попытке успех."""
        mock_gemini.generate.side_effect = [
            "не json",
            "{broken",
            _good_response(),
        ]
        s4 = Stage4Latex(mock_gemini)
        result = s4.process(sample_rewritten_s4)
        assert result.processed_text
        assert mock_gemini.generate.call_count == 3

    def test_retries_exhausted(self, mock_gemini, sample_rewritten_s4):
        """Все 3 попытки провалились -> Stage4Error."""
        mock_gemini.generate.return_value = "не json"
        s4 = Stage4Latex(mock_gemini)
        with pytest.raises(Stage4Error):
            s4.process(sample_rewritten_s4)
        assert mock_gemini.generate.call_count == 3

    def test_missing_processed_text_field(self, mock_gemini, sample_rewritten_s4):
        """Отсутствие поля processed_text -> ошибка."""
        mock_gemini.generate.return_value = json.dumps({
            "formulas_count": 3,
            "notes": "",
        })
        s4 = Stage4Latex(mock_gemini)
        with pytest.raises(Stage4Error):
            s4.process(sample_rewritten_s4)

    def test_previous_errors_passed_to_prompt(self, mock_gemini, sample_rewritten_s4):
        """Ошибки предыдущей попытки передаются в промпт."""
        mock_gemini.generate.return_value = _good_response()
        s4 = Stage4Latex(mock_gemini)
        s4.process(
            sample_rewritten_s4,
            previous_errors=["\\sqrt без {}", "Непарные $"],
            previous_output="старый ответ с ошибкой",
        )
        call = mock_gemini.generate.call_args
        prompt_text = call.kwargs["prompt"]
        assert "\\sqrt без {}" in prompt_text
        assert "Непарные $" in prompt_text
        assert "старый ответ" in prompt_text

    def test_empty_previous_errors_no_block(self, mock_gemini, sample_rewritten_s4):
        """Без ошибок -> блок ПРЕДЫДУЩАЯ ПОПЫТКА не появляется."""
        mock_gemini.generate.return_value = _good_response()
        s4 = Stage4Latex(mock_gemini)
        s4.process(sample_rewritten_s4)
        prompt_text = mock_gemini.generate.call_args.kwargs["prompt"]
        assert "ПРЕДЫДУЩАЯ ПОПЫТКА ОТКЛОНЕНА" not in prompt_text

    def test_temperature_increases(self, mock_gemini, sample_rewritten_s4):
        """Температура растёт с каждой попыткой: 0.2 -> 0.3 -> 0.4."""
        mock_gemini.generate.side_effect = [
            "bad json 1",
            "bad json 2",
            _good_response(),
        ]
        s4 = Stage4Latex(mock_gemini)
        s4.process(sample_rewritten_s4)
        temps = [
            c.kwargs["temperature"]
            for c in mock_gemini.generate.call_args_list
        ]
        assert abs(temps[0] - 0.2) < 0.01
        assert abs(temps[1] - 0.3) < 0.01
        assert abs(temps[2] - 0.4) < 0.01

    def test_preserves_rewritten_reference(self, mock_gemini, sample_rewritten_s4):
        """ProcessedTask сохраняет ссылку на RewrittenTask."""
        mock_gemini.generate.return_value = _good_response()
        s4 = Stage4Latex(mock_gemini)
        result = s4.process(sample_rewritten_s4)
        assert result.rewritten is sample_rewritten_s4
        assert result.rewritten.original.olympiad == "ВсОШ"
