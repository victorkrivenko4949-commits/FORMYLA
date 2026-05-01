# -*- coding: utf-8 -*-
"""
Tests for Stage 2: Rewrite task.
"""
import json
import pytest
from unittest.mock import MagicMock
from services.pipeline.stage2_rewrite import Stage2Rewrite, Stage2Error
from services.pipeline.types import FoundTask, RewrittenTask


@pytest.fixture
def sample_found():
    """Прототип задачи для тестов Stage 2."""
    return FoundTask(
        olympiad="ВсОШ",
        year=2019,
        stage="regional",
        grade=9,
        problem_number=3,
        topic="неравенства",
        difficulty="medium",
        original_text=(
            "Для положительных чисел a, b, c, сумма которых равна 1, "
            "докажите неравенство √(a/(b+c)) + √(b/(a+c)) + √(c/(a+b)) ≥ 3/√2."
        ),
        author="Н. Агаханов",
        confidence=0.9,
    )


def _good_rewrite(**overrides):
    """Helper: возвращает валидный JSON-ответ Stage 2."""
    data = {
        "rewritten_text": (
            "Пусть x, y, z — положительные числа, сумма которых равна 2. "
            "Найдите наибольшее число m, при котором всегда выполняется "
            "неравенство √(x/(y+z+xy)) + √(y/(x+z+yz)) + √(z/(x+y+xz)) ≥ m."
        ),
        "changes": [
            "сумма 1 → сумма 2",
            "a,b,c → x,y,z",
            "добавлены xy/yz/xz в знаменатели",
            "докажите → найдите максимум",
        ],
        "method_preserved": "Коши-Буняковский + симметризация",
        "difficulty_same": True,
        "similarity_estimate": 0.35,
    }
    data.update(overrides)
    return json.dumps(data, ensure_ascii=False)


class TestStage2Rewrite:
    """Тесты для Stage2Rewrite."""

    def test_happy_path(self, mock_deepseek, sample_found):
        """Успешное переписывание с первой попытки."""
        mock_deepseek.generate.return_value = _good_rewrite()
        s2 = Stage2Rewrite(mock_deepseek)
        result = s2.rewrite(sample_found)
        assert isinstance(result, RewrittenTask)
        assert result.original is sample_found
        assert "x, y, z" in result.rewritten_text
        assert len(result.changes) >= 3
        assert result.method_preserved
        mock_deepseek.generate.assert_called_once()

    def test_strips_markdown_fence(self, mock_deepseek, sample_found):
        """JSON обёрнутый в ```json ... ``` должен парситься."""
        mock_deepseek.generate.return_value = (
            "```json\n" + _good_rewrite() + "\n```"
        )
        s2 = Stage2Rewrite(mock_deepseek)
        result = s2.rewrite(sample_found)
        assert result.rewritten_text

    def test_latex_backslash_rejected(self, mock_deepseek, sample_found):
        """Обратный слэш в rewritten_text → отклонение."""
        mock_deepseek.generate.return_value = _good_rewrite(
            rewritten_text=(
                "Докажите, что \\sqrt{x^2+1} \\geq x для всех x > 0. "
                "Условие два. Условие три."
            )
        )
        s2 = Stage2Rewrite(mock_deepseek)
        with pytest.raises(Stage2Error, match="обратный слэш"):
            s2.rewrite(sample_found)

    def test_dollar_rejected(self, mock_deepseek, sample_found):
        """Символ $ в rewritten_text → отклонение."""
        mock_deepseek.generate.return_value = _good_rewrite(
            rewritten_text=(
                "Решите $x^2 + y^2 = 25$ для всех x, y из Z. "
                "Условие два. Условие три."
            )
        )
        s2 = Stage2Rewrite(mock_deepseek)
        with pytest.raises(Stage2Error, match=r"\$"):
            s2.rewrite(sample_found)

    def test_too_few_changes_rejected(self, mock_deepseek, sample_found):
        """Менее 3 изменений → отклонение."""
        mock_deepseek.generate.return_value = _good_rewrite(
            changes=["a→x", "1→2"]
        )
        s2 = Stage2Rewrite(mock_deepseek)
        with pytest.raises(Stage2Error, match="Изменений"):
            s2.rewrite(sample_found)

    def test_no_method_rejected(self, mock_deepseek, sample_found):
        """Пустой method_preserved → отклонение."""
        mock_deepseek.generate.return_value = _good_rewrite(
            method_preserved=""
        )
        s2 = Stage2Rewrite(mock_deepseek)
        with pytest.raises(Stage2Error, match="метод"):
            s2.rewrite(sample_found)

    def test_difficulty_changed_rejected(self, mock_deepseek, sample_found):
        """difficulty_same=False → отклонение."""
        mock_deepseek.generate.return_value = _good_rewrite(
            difficulty_same=False
        )
        s2 = Stage2Rewrite(mock_deepseek)
        with pytest.raises(Stage2Error, match="сложность"):
            s2.rewrite(sample_found)

    def test_too_similar_rejected(self, mock_deepseek, sample_found):
        """Текст слишком похож на прототип → отклонение."""
        mock_deepseek.generate.return_value = _good_rewrite(
            rewritten_text=sample_found.original_text + " Добавлено одно слово."
        )
        s2 = Stage2Rewrite(mock_deepseek)
        with pytest.raises(Stage2Error, match="похож на прототип"):
            s2.rewrite(sample_found)

    def test_solution_hint_rejected(self, mock_deepseek, sample_found):
        """Намёк на решение в тексте → отклонение."""
        mock_deepseek.generate.return_value = _good_rewrite(
            rewritten_text=(
                "Пусть x, y, z положительные с суммой 2. "
                "Заметим, что √x+√y+√z ≥ что-то. Докажите. Ещё условие."
            )
        )
        s2 = Stage2Rewrite(mock_deepseek)
        with pytest.raises(Stage2Error, match="[Нн]амёк"):
            s2.rewrite(sample_found)

    def test_invalid_json_retries(self, mock_deepseek, sample_found):
        """Невалидный JSON → retry → на 3-й попытке успех."""
        mock_deepseek.generate.side_effect = [
            "не json",
            "{broken",
            _good_rewrite(),
        ]
        s2 = Stage2Rewrite(mock_deepseek)
        result = s2.rewrite(sample_found)
        assert result.rewritten_text
        assert mock_deepseek.generate.call_count == 3

    def test_retries_exhausted_raises(self, mock_deepseek, sample_found):
        """Все 3 попытки провалились → Stage2Error."""
        mock_deepseek.generate.return_value = "не json"
        s2 = Stage2Rewrite(mock_deepseek)
        with pytest.raises(Stage2Error):
            s2.rewrite(sample_found)
        assert mock_deepseek.generate.call_count == 3

    def test_missing_rewritten_text_field(self, mock_deepseek, sample_found):
        """Отсутствие поля rewritten_text → ошибка."""
        mock_deepseek.generate.return_value = json.dumps({
            "changes": ["a", "b", "c"],
            "method_preserved": "x",
            "difficulty_same": True,
        })
        s2 = Stage2Rewrite(mock_deepseek)
        with pytest.raises(Stage2Error):
            s2.rewrite(sample_found)

    def test_temperature_increases(self, mock_deepseek, sample_found):
        """Температура растёт с каждой попыткой: 0.7 → 0.8 → 0.9."""
        mock_deepseek.generate.side_effect = [
            "bad json 1",
            "bad json 2",
            _good_rewrite(),
        ]
        s2 = Stage2Rewrite(mock_deepseek)
        s2.rewrite(sample_found)
        calls = mock_deepseek.generate.call_args_list
        temps = [c.kwargs["temperature"] for c in calls]
        assert abs(temps[0] - 0.7) < 0.01
        assert abs(temps[1] - 0.8) < 0.01
        assert abs(temps[2] - 0.9) < 0.01
