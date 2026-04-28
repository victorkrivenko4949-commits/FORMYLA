#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тесты для services/task_validator.py

Запуск:
    pytest tests/test_task_validator.py -v

Покрывает:
- Детект утечки решения в условии
- Автофикс LaTeX ($...$  -> \\(...\\), $$...$$ -> \\[...\\], двойные backslash)
- Детект путаницы индексов/степеней (f1(x) vs f_1(x), f² vs f^2)
- Полный цикл валидации (парсинг JSON + проверки)
"""

import sys
import os
import json

# Добавляем корень проекта в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.task_validator import (
    has_solution_leak,
    fix_latex,
    has_index_confusion,
    is_plagiarism,
    validate_generated_task,
)


# ─── Тесты: has_solution_leak ─────────────────────────────────────────────────

class TestHasSolutionLeak:

    def test_detect_solution_keyword(self):
        """Слово 'Решение:' в условии — утечка."""
        has_leak, msg = has_solution_leak("Найдите x, если 2x=10. Решение: x=5")
        assert has_leak, f"Должна быть утечка, но не обнаружена. msg={msg}"

    def test_detect_answer_keyword(self):
        """Слово 'Ответ:' в условии — утечка."""
        has_leak, msg = has_solution_leak("Сколько будет 2+2? Ответ: 4")
        assert has_leak

    def test_detect_proof_keyword(self):
        """Слово 'Доказательство:' в условии — утечка."""
        has_leak, msg = has_solution_leak(
            "Докажите что n^2 > 0. Доказательство: очевидно."
        )
        assert has_leak

    def test_detect_answer_with_number(self):
        """'Ответ: 18' в условии — утечка."""
        has_leak, _ = has_solution_leak(
            "Найдите периметр. Ответ: 18 см."
        )
        assert has_leak

    def test_detect_solution_english(self):
        """'Solution:' в условии — утечка."""
        has_leak, _ = has_solution_leak("Find x. Solution: x = 5")
        assert has_leak

    def test_clean_task_passes(self):
        """Чистое условие без утечки."""
        has_leak, _ = has_solution_leak(
            "Найдите наименьшее натуральное n такое, что n делится на 6."
        )
        assert not has_leak

    def test_clean_task_with_latex(self):
        """Условие с LaTeX без утечки."""
        has_leak, _ = has_solution_leak(
            r"Докажите, что для любого натурального \(n\) число \(n^3 - n\) делится на 6."
        )
        assert not has_leak

    def test_clean_task_with_numbers(self):
        """Условие с числами в тексте — не утечка."""
        has_leak, _ = has_solution_leak(
            "Десять учеников написали контрольную. Сколько пятёрок получили?"
        )
        assert not has_leak

    def test_case_insensitive(self):
        """Детект нечувствителен к регистру."""
        has_leak, _ = has_solution_leak("Задача. РЕШЕНИЕ: x=1")
        assert has_leak

    def test_empty_string(self):
        """Пустая строка — нет утечки."""
        has_leak, _ = has_solution_leak("")
        assert not has_leak


# ─── Тесты: fix_latex ────────────────────────────────────────────────────────

class TestFixLatex:

    def test_fix_dollar_inline(self):
        """$x^2 + 1$ -> \\(x^2 + 1\\)"""
        result = fix_latex("Найдите $x^2 + 1$ при x=3")
        assert '$' not in result
        assert r'\(x^2 + 1\)' in result

    def test_fix_dollar_display(self):
        """$$x^2 + 1$$ -> \\[x^2 + 1\\]"""
        result = fix_latex("Формула: $$x^2 + 1 = 0$$")
        assert '$$' not in result
        assert r'\[x^2 + 1 = 0\]' in result

    def test_fix_double_backslash_frac(self):
        """\\\\frac -> \\frac"""
        result = fix_latex(r"Дробь \\frac{1}{2}")
        assert r'\\frac' not in result
        assert r'\frac' in result

    def test_fix_frac_without_backslash(self):
        """frac{a}{b} без backslash -> \\frac{a}{b}"""
        result = fix_latex("Дробь frac{1}{2} равна половине")
        assert r'\frac{1}{2}' in result

    def test_fix_sqrt_without_backslash(self):
        """sqrt{x} без backslash -> \\sqrt{x}"""
        result = fix_latex("Корень sqrt{x} из x")
        assert r'\sqrt{x}' in result

    def test_preserve_correct_latex(self):
        """Правильный LaTeX не изменяется."""
        text = r"Найдите \(x^2 + 2x = 5\) при \(x > 0\)"
        result = fix_latex(text)
        assert r'\(x^2 + 2x = 5\)' in result
        assert r'\(x > 0\)' in result

    def test_empty_string(self):
        """Пустая строка возвращается без изменений."""
        assert fix_latex("") == ""

    def test_none_returns_none(self):
        """None возвращается без изменений."""
        assert fix_latex(None) is None

    def test_no_math_unchanged(self):
        """Текст без математики не изменяется."""
        text = "Петя пошёл в магазин и купил три яблока."
        result = fix_latex(text)
        assert result == text

    def test_fix_multiple_dollars(self):
        """Несколько $...$ в одном тексте."""
        result = fix_latex("Если $a > 0$ и $b > 0$, то $a + b > 0$.")
        assert '$' not in result
        assert result.count(r'\(') == 3
        assert result.count(r'\)') == 3


# ─── Тесты: validate_generated_task ──────────────────────────────────────────

class TestValidateGeneratedTask:

    def _make_valid_json(self, **overrides):
        """Создаёт валидный JSON-ответ LLM."""
        base = {
            "task_text": "Найдите наименьшее натуральное число, делящееся на 6 и на 10.",
            "correct_answer": "30",
            "solution": (
                "Нам нужно найти наименьшее общее кратное чисел 6 и 10. "
                "Разложим на простые множители: 6 = 2 * 3, 10 = 2 * 5. "
                "НОК(6, 10) = 2 * 3 * 5 = 30. "
                "Проверка: 30 / 6 = 5 (целое), 30 / 10 = 3 (целое). "
                "Числа меньше 30 не делятся одновременно на 6 и 10. "
                "Ответ: 30."
            ),
            "topic": "Делимость",
            "difficulty": 2,
            "key_idea": "Наименьшее общее кратное",
        }
        base.update(overrides)
        return json.dumps(base, ensure_ascii=False)

    def test_valid_task_passes(self):
        """Валидная задача проходит проверку."""
        raw = self._make_valid_json()
        result = validate_generated_task(raw)
        assert result['valid'], f"Должна пройти, ошибки: {result['errors']}"
        assert result['task'] is not None
        assert result['errors'] == []

    def test_solution_leak_rejected(self):
        """Задача с утечкой решения в условии отклоняется."""
        raw = self._make_valid_json(
            task_text="Найдите x, если 2x=10. Ответ: 5"
        )
        result = validate_generated_task(raw)
        assert not result['valid']
        assert any('утечка' in e.lower() or 'ответ' in e.lower() for e in result['errors'])

    def test_missing_field_rejected(self):
        """Задача без обязательного поля отклоняется."""
        data = {
            "task_text": "Найдите x.",
            "correct_answer": "5",
            # solution отсутствует
            "topic": "Алгебра",
            "difficulty": 2,
        }
        result = validate_generated_task(json.dumps(data))
        assert not result['valid']
        assert any('solution' in e for e in result['errors'])

    def test_invalid_difficulty_rejected(self):
        """Difficulty вне диапазона 1-5 отклоняется."""
        raw = self._make_valid_json(difficulty=10)
        result = validate_generated_task(raw)
        assert not result['valid']
        assert any('difficulty' in e.lower() or 'диапазон' in e.lower() for e in result['errors'])

    def test_difficulty_as_string_accepted(self):
        """Difficulty как строка '3' принимается и конвертируется."""
        raw = self._make_valid_json(difficulty="3")
        result = validate_generated_task(raw)
        assert result['valid'], f"Ошибки: {result['errors']}"
        assert result['task']['difficulty'] == 3

    def test_too_short_task_rejected(self):
        """Слишком короткое условие отклоняется."""
        raw = self._make_valid_json(task_text="Найди x.")
        result = validate_generated_task(raw)
        assert not result['valid']
        assert any('короткое' in e.lower() or 'символ' in e.lower() for e in result['errors'])

    def test_invalid_json_rejected(self):
        """Невалидный JSON отклоняется."""
        result = validate_generated_task("это не JSON вообще")
        assert not result['valid']
        assert result['task'] is None
        assert any('json' in e.lower() for e in result['errors'])

    def test_json_in_markdown_block_accepted(self):
        """JSON внутри markdown-блока парсится корректно."""
        raw = '```json\n' + self._make_valid_json() + '\n```'
        result = validate_generated_task(raw)
        assert result['valid'], f"Ошибки: {result['errors']}"

    def test_latex_autofix_applied(self):
        """LaTeX автоматически исправляется при валидации."""
        raw = self._make_valid_json(
            task_text="Найдите $x^2 + 1$ при $x = 3$. Это задача на подстановку."
        )
        result = validate_generated_task(raw)
        assert result['valid'], f"Ошибки: {result['errors']}"
        # После фикса не должно быть одиночных $
        assert '$' not in result['task']['task_text']

    def test_empty_response_rejected(self):
        """Пустой ответ отклоняется."""
        result = validate_generated_task("")
        assert not result['valid']
        assert result['task'] is None

    def test_solution_keyword_in_task_rejected(self):
        """Слово 'Решение:' в условии отклоняется."""
        raw = self._make_valid_json(
            task_text=(
                "Найдите наименьшее натуральное число, делящееся на 6. "
                "Решение: это число равно 6."
            )
        )
        result = validate_generated_task(raw)
        assert not result['valid']

    def test_valid_task_with_latex(self):
        """Задача с правильным LaTeX проходит валидацию."""
        raw = self._make_valid_json(
            task_text=(
                r"Найдите все натуральные числа \(n\), при которых "
                r"\(n^2 + 3n + 5\) является точным квадратом."
            )
        )
        result = validate_generated_task(raw)
        assert result['valid'], f"Ошибки: {result['errors']}"

    def test_key_idea_optional(self):
        """Поле key_idea необязательно — добавляется автоматически."""
        data = {
            "task_text": "Найдите наименьшее натуральное число, делящееся на 6 и на 10.",
            "correct_answer": "30",
            "solution": (
                "Нам нужно найти наименьшее общее кратное чисел 6 и 10. "
                "Разложим на простые множители: 6 = 2 * 3, 10 = 2 * 5. "
                "НОК(6, 10) = 2 * 3 * 5 = 30. "
                "Проверка: 30 / 6 = 5 (целое), 30 / 10 = 3 (целое). "
                "Числа меньше 30 не делятся одновременно на 6 и 10. Ответ: 30."
            ),
            "topic": "Делимость",
            "difficulty": 2,
            # key_idea отсутствует
        }
        result = validate_generated_task(json.dumps(data))
        assert result['valid'], f"Ошибки: {result['errors']}"
        assert 'key_idea' in result['task']  # добавляется автоматически


# ─── Тесты: has_index_confusion ──────────────────────────────────────────────

class TestHasIndexConfusion:

    def test_detect_index_confusion_no_latex(self):
        """f1(x), f2(x), f100(x) без LaTeX — путаница."""
        has_conf, _ = has_index_confusion("Даны функции f1(x), f2(x), ..., f100(x)")
        assert has_conf

    def test_detect_unicode_power_confusion(self):
        """f1(x) и f\u00b2(x) вместе — путаница нотаций."""
        has_conf, _ = has_index_confusion(
            "Даны f1(x), f\u00b2(x), ..., f100(x) с коэффициентами"
        )
        assert has_conf

    def test_correct_latex_indexes_pass(self):
        """Правильные LaTeX-индексы не вызывают ошибку."""
        has_conf, _ = has_index_confusion(
            r"Даны функции \(f_1(x)\), \(f_2(x)\), \(f_{100}(x)\)"
        )
        assert not has_conf

    def test_correct_power_pass(self):
        """Правильные LaTeX-степени с индексами не вызывают ошибку."""
        has_conf, _ = has_index_confusion(
            r"Сумма \(x_1^2 + x_2^2 + x_3^2\) равна 1"
        )
        assert not has_conf

    def test_real_buggy_example_caught(self):
        """Реальный баг из production — f1(x), f\u00b2(x), f100(x)."""
        buggy = (
            "Даны квадратные трёхчлены f1(x), f\u00b2(x), ..., f100(x) "
            "с одинаковыми коэффициентами при x\u00b2"
        )
        has_conf, msg = has_index_confusion(buggy)
        assert has_conf

    def test_big_index_without_braces(self):
        r"""Индексы >9 без фигурных скобок: \(a_10\) вместо \(a_{10}\)."""
        has_conf, _ = has_index_confusion(r"Рассмотрим \(a_10\) и \(x_100\)")
        assert has_conf

    def test_validate_full_flow_catches_index_confusion(self):
        """Полный цикл валидации отклоняет задачу с путаницей индексов."""
        raw = json.dumps({
            "task_text": "Даны f1(x), f\u00b2(x), ..., f100(x)",
            "correct_answer": "0",
            "solution": "решение",
            "topic": "Алгебра",
            "difficulty": 4,
        }, ensure_ascii=False)
        result = validate_generated_task(raw)
        assert not result['valid']
        assert any(
            'индекс' in e.lower() or 'путаниц' in e.lower()
            for e in result['errors']
        )

    def test_lost_power_after_paren(self):
        """Цифра сразу после ) вне LaTeX — потерянная степень."""
        has_conf, msg = has_index_confusion(
            "записи чисел n\u00b2 и (n + 1)2 отличаются перестановкой цифр"
        )
        assert has_conf, f"Должна быть путаница, msg={msg}"

    def test_lost_power_big_number(self):
        """Большое число без LaTeX в математическом контексте — потерянная степень."""
        has_conf, msg = has_index_confusion(
            "Существует ли натуральное число n > 10100 такое что"
        )
        assert has_conf, f"Должна быть путаница, msg={msg}"

    def test_correct_power_in_latex(self):
        r"""Правильные степени в LaTeX не вызывают ошибку."""
        has_conf, _ = has_index_confusion(
            r"число \(n > 10^{100}\) такое что \((n+1)^2\) равно"
        )
        assert not has_conf


# ─── Тесты: is_plagiarism + solution quality ─────────────────────────────────

class TestPlagiarismAndQuality:

    def test_plagiarism_detected(self):
        """Задача слишком похожа на пример из БД — плагиат."""
        examples = [
            "На доске написаны числа от 1 до 100. Можно ли их разбить на пары так чтобы"
        ]
        generated = (
            "На доске написаны числа от 1 до 100. "
            "Можно ли их разбить на пары так чтобы сумма каждой пары делилась на 3?"
        )
        is_plag, sim = is_plagiarism(generated, examples)
        assert is_plag, f"Должен быть плагиат, sim={sim:.2f}"
        assert sim > 0.65

    def test_original_task_passes(self):
        """Оригинальная задача не является плагиатом."""
        examples = [
            "На доске написаны числа от 1 до 100. Разбить на пары."
        ]
        generated = (
            "В таблице 5x5 расставлены числа. "
            "Докажите что найдётся строка с суммой больше 100."
        )
        is_plag, _ = is_plagiarism(generated, examples)
        assert not is_plag

    def test_vague_answer_rejected(self):
        """Размытый ответ 'зависит от n' отклоняется."""
        solution_long = "Решение длинное. " * 15
        raw = json.dumps({
            "task_text": "Найти все n такие что условие выполнено.",
            "correct_answer": "зависит от n",
            "solution": solution_long,
            "topic": "Алгебра",
            "difficulty": 4,
        }, ensure_ascii=False)
        result = validate_generated_task(raw)
        assert not result['valid']
        assert any('размыт' in e.lower() for e in result['errors'])

    def test_short_solution_rejected(self):
        """Слишком короткое решение отклоняется."""
        raw = json.dumps({
            "task_text": "Найдите наименьшее натуральное число делящееся на 6 и на 10.",
            "correct_answer": "30",
            "solution": "x = 30",
            "topic": "Алгебра",
            "difficulty": 2,
        }, ensure_ascii=False)
        result = validate_generated_task(raw)
        assert not result['valid']
        assert any('решение' in e.lower() and 'коротк' in e.lower() for e in result['errors'])

    def test_full_valid_task_passes(self):
        """Полноценная задача с длинным решением проходит валидацию."""
        long_solution = (
            "Заметим что n^3 - n = n(n-1)(n+1) — произведение трёх последовательных "
            "целых чисел. Среди трёх последовательных чисел всегда есть число делящееся "
            "на 3, поэтому произведение делится на 3. Также среди трёх последовательных "
            "чисел минимум одно чётное, поэтому произведение делится на 2. "
            "Так как НОД(2,3)=1, произведение делится на 2*3=6. "
            "Что и требовалось доказать. Ответ: утверждение верно для всех натуральных n."
        )
        raw = json.dumps({
            "task_text": (
                r"Докажите что для любого натурального \(n\) "
                r"число \(n^3 - n\) делится на 6."
            ),
            "correct_answer": "Доказательство приведено в решении",
            "solution": long_solution,
            "topic": "Теория чисел",
            "difficulty": 3,
        }, ensure_ascii=False)
        result = validate_generated_task(raw)
        assert result['valid'], f"Ошибки: {result['errors']}"


# ─── Запуск напрямую ──────────────────────────────────────────────────────────

if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v', '--tb=short'])
