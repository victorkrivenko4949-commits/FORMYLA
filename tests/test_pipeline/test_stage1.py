# -*- coding: utf-8 -*-
"""
Tests for Stage 1: Find prototype task.
"""
import json
import pytest
from unittest.mock import MagicMock
from services.pipeline.stage1_find import Stage1Find, Stage1Error
from services.pipeline.types import FoundTask


def _good_response(**overrides):
    """Helper: возвращает валидный JSON-ответ Stage 1."""
    data = {
        "olympiad": "ВсОШ",
        "year": 2019,
        "stage": "regional",
        "grade": 9,
        "problem_number": 3,
        "topic": "неравенства",
        "difficulty": "medium",
        "original_text": (
            "Для положительных a, b, c с суммой 1 докажите, что "
            "√(a/(b+c)) + √(b/(a+c)) + √(c/(a+b)) ≥ 3/√2."
        ),
        "author": "Н. Агаханов",
        "confidence": 0.88,
    }
    data.update(overrides)
    return json.dumps(data, ensure_ascii=False)


class TestStage1Find:
    """Тесты для Stage1Find."""

    def test_happy_path(self, mock_deepseek):
        """Успешный поиск задачи с первой попытки."""
        mock_deepseek.generate.return_value = _good_response()
        s1 = Stage1Find(mock_deepseek)
        result = s1.find("ВсОШ", "regional", 9)
        assert isinstance(result, FoundTask)
        assert result.year == 2019
        assert result.confidence == 0.88
        assert "положительных" in result.original_text
        mock_deepseek.generate.assert_called_once()

    def test_strips_markdown_code_fence(self, mock_deepseek):
        """JSON обёрнутый в ```json ... ``` должен парситься."""
        raw = "```json\n" + _good_response() + "\n```"
        mock_deepseek.generate.return_value = raw
        s1 = Stage1Find(mock_deepseek)
        result = s1.find("ВсОШ", "regional", 9)
        assert result.year == 2019

    def test_low_confidence_retries_then_fails(self, mock_deepseek):
        """Confidence < 0.7 → retry 3 раза → Stage1Error."""
        mock_deepseek.generate.return_value = _good_response(confidence=0.4)
        s1 = Stage1Find(mock_deepseek)
        with pytest.raises(Stage1Error, match="Confidence"):
            s1.find("ВсОШ", "regional", 9)
        assert mock_deepseek.generate.call_count == 3

    def test_invalid_json_retries_then_succeeds(self, mock_deepseek):
        """Невалидный JSON → retry → на 3-й попытке успех."""
        mock_deepseek.generate.side_effect = [
            "это не json вообще",
            "{broken json",
            _good_response(),
        ]
        s1 = Stage1Find(mock_deepseek)
        result = s1.find("ВсОШ", "regional", 9)
        assert result.year == 2019
        assert mock_deepseek.generate.call_count == 3

    def test_latex_leak_backslash_rejected(self, mock_deepseek):
        """Обратный слэш в original_text → отклонение."""
        mock_deepseek.generate.return_value = _good_response(
            original_text="Докажите \\sqrt{x^2+1} \\geq 1 для всех x."
        )
        s1 = Stage1Find(mock_deepseek)
        with pytest.raises(Stage1Error, match="обратный слэш"):
            s1.find("ВсОШ", "regional", 9)

    def test_dollar_sign_rejected(self, mock_deepseek):
        """Символ $ в original_text → отклонение."""
        mock_deepseek.generate.return_value = _good_response(
            original_text="Решите уравнение $x^2 = 4$ для x из R."
        )
        s1 = Stage1Find(mock_deepseek)
        with pytest.raises(Stage1Error, match="\\$"):
            s1.find("ВсОШ", "regional", 9)

    def test_short_text_rejected(self, mock_deepseek):
        """Слишком короткий текст → отклонение."""
        mock_deepseek.generate.return_value = _good_response(
            original_text="Короткая."
        )
        s1 = Stage1Find(mock_deepseek)
        with pytest.raises(Stage1Error, match="короткий"):
            s1.find("ВсОШ", "regional", 9)

    def test_year_out_of_range_rejected(self, mock_deepseek):
        """Год вне 2015-2024 → отклонение."""
        mock_deepseek.generate.return_value = _good_response(year=2008)
        s1 = Stage1Find(mock_deepseek)
        with pytest.raises(Stage1Error, match="Год"):
            s1.find("ВсОШ", "regional", 9)

    def test_invalid_stage_input(self, mock_deepseek):
        """Невалидный stage → Stage1Error без вызова LLM."""
        s1 = Stage1Find(mock_deepseek)
        with pytest.raises(Stage1Error, match="stage"):
            s1.find("ВсОШ", "invalid_stage", 9)
        mock_deepseek.generate.assert_not_called()

    def test_invalid_grade_input(self, mock_deepseek):
        """Невалидный grade → Stage1Error без вызова LLM."""
        s1 = Stage1Find(mock_deepseek)
        with pytest.raises(Stage1Error, match="grade"):
            s1.find("ВсОШ", "regional", 15)
        mock_deepseek.generate.assert_not_called()

    def test_missing_required_field_raises(self, mock_deepseek):
        """Отсутствие обязательного поля original_text → ошибка."""
        mock_deepseek.generate.return_value = json.dumps({
            "year": 2019,
            "confidence": 0.9,
        })
        s1 = Stage1Find(mock_deepseek)
        with pytest.raises(Stage1Error):
            s1.find("ВсОШ", "regional", 9)

    def test_temperature_increases_per_attempt(self, mock_deepseek):
        """Температура растёт с каждой попыткой: 0.3 → 0.5 → 0.7."""
        mock_deepseek.generate.side_effect = [
            "bad json 1",
            "bad json 2",
            _good_response(),
        ]
        s1 = Stage1Find(mock_deepseek)
        s1.find("ВсОШ", "regional", 9)
        calls = mock_deepseek.generate.call_args_list
        temps = [c.kwargs.get("temperature") for c in calls]
        assert abs(temps[0] - 0.3) < 0.01
        assert abs(temps[1] - 0.5) < 0.01
        assert abs(temps[2] - 0.7) < 0.01
