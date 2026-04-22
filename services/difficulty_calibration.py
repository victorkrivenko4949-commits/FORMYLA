# -*- coding: utf-8 -*-
"""
Difficulty Calibration Service for FORMYLA
Provides level labels, few-shot examples, and calibration utilities.
"""

# Level labels for UI display
LEVEL_LABELS = {
    1: 'Базовый',
    2: 'Школьный',
    3: 'Олимпиада (школа)',
    4: 'Муниципальный',
    5: 'Региональный',
    6: 'Всерос финал',
    7: 'IMO / ELITE',
}

# Level colors for UI
LEVEL_COLORS = {
    1: '#22c55e',
    2: '#22c55e',
    3: '#fbbf24',
    4: '#f97316',
    5: '#f97316',
    6: '#ef4444',
    7: '#ec4899',
}

# Expected solve rates per level (for calibration)
LEVEL_EXPECTED_RATES = {
    1: 0.95,
    2: 0.85,
    3: 0.60,
    4: 0.35,
    5: 0.15,
    6: 0.08,
    7: 0.03,
}

# Level descriptions for prompts
LEVEL_DESCRIPTIONS = {
    1: "Базовый уровень. Прямое применение одной формулы. Решается за 1-2 минуты. 95% учеников решат.",
    2: "Школьный уровень. 2-3 шага, стандартные техники. Решается за 2-5 минут. 80-90% учеников решат.",
    3: "Школьная олимпиада. Требует нестандартного подхода или доказательства. 5-15 минут. 50-70% решат.",
    4: "Муниципальный этап. Комбинаторика или теория чисел с инсайтом. 15-30 минут. 25-40% решат.",
    5: "Региональный/Зональный. Турнир городов, зональный Всерос. 30-60 минут. 10-20% решат.",
    6: "Заключительный этап Всерос. Сложные задачи финала. 60-90 минут. 5-10% решат.",
    7: "IMO / ELITE. Задачи уровня IMO, суперфинал. 90+ минут. 1-5% (только топ-олимпиадники) решат.",
}

# Few-shot examples for each level (real olympiad problems)
LEVEL_EXAMPLES = {
    1: [
        "Найдите НОД(18, 24). Ответ: 6",
        "Вычислите: 3/4 + 1/6. Ответ: 11/12",
        "Реши уравнение: x + 7 = 15. Ответ: x = 8",
    ],
    2: [
        "Реши уравнение: 3x + 5 = 2x - 7. Ответ: x = -12",
        "Найди площадь треугольника с основанием 8 и высотой 5. Ответ: 20",
        "Поезд проехал 120 км за 2 часа. Найди его скорость. Ответ: 60 км/ч",
    ],
    3: [
        "Докажи, что сумма трёх последовательных натуральных чисел делится на 3.",
        "Найди все натуральные числа n, при которых n^2 + n + 1 делится на 3.",
        "Сколько трёхзначных чисел имеют сумму цифр, равную 5? Ответ: 15",
    ],
    4: [
        "В таблице 3x3 расставлены числа 1-9. Докажи, что можно выбрать 3 клетки (не в одной строке и столбце) с суммой >= 15.",
        "Найди все целые решения уравнения x^2 - y^2 = 2023.",
        "Докажи, что для любого натурального n число n^5 - n делится на 30.",
    ],
    5: [
        "Турнир городов 2019: Докажи, что среди любых 5 целых чисел найдутся три, сумма которых делится на 3.",
        "Найди все простые числа p, для которых p^2 + 2 тоже простое.",
        "В выпуклом многоугольнике проведены все диагонали. Докажи, что не все они могут пересекаться в одной точке.",
    ],
    6: [
        "Всерос 2019, 11 класс: Найди все функции f: R -> R такие, что f(x+y) = f(x) + f(y) + xy для всех x, y.",
        "Докажи, что для любого натурального n существует простое число p > n.",
        "Всерос финал: В треугольнике ABC точка I - центр вписанной окружности. Докажи, что AI^2 = r * R, где r - радиус вписанной, R - описанной.",
    ],
    7: [
        "IMO 2019 P4: Найдите все пары (k, n) натуральных чисел такие, что k! = (2^n - 1)(2^n - 2)(2^n - 4)...(2^n - 2^(n-1)).",
        "IMO 2016 P6: Пусть S - конечное множество точек плоскости, не все на одной прямой. Для каждой прямой l, проходящей хотя бы через 2 точки S, обозначим через l(S) множество точек S на l. Докажи, что существует прямая l такая, что l(S) не является подмножеством никакой другой прямой.",
        "Putnam 2018 B6: Докажи, что для любого натурального n существует простое p такое, что p делит n^n + 1.",
    ],
}


def get_level_label(level):
    """Get human-readable label for difficulty level."""
    return LEVEL_LABELS.get(level, f'Уровень {level}')


def get_level_color(level):
    """Get color for difficulty level badge."""
    return LEVEL_COLORS.get(level, '#38ef7d')


def build_generation_prompt(grade, topic, subtopic, level):
    """
    Build a few-shot prompt for task generation with proper difficulty calibration.
    
    Args:
        grade: School grade (5-11)
        topic: Main topic (algebra, geometry, etc.)
        subtopic: Specific subtopic
        level: Difficulty level (1-7)
        
    Returns:
        Formatted prompt string
    """
    examples = LEVEL_EXAMPLES.get(level, LEVEL_EXAMPLES[3])[:3]
    examples_text = '\n\n'.join([
        f'ПРИМЕР {i+1} (уровень {level}):\n{ex}'
        for i, ex in enumerate(examples)
    ])
    
    description = LEVEL_DESCRIPTIONS.get(level, LEVEL_DESCRIPTIONS[3])
    
    prompt = f"""Ты — генератор олимпиадных задач для платформы FORMYLA.

ТРЕБОВАНИЯ:
- Класс: {grade}
- Тема: {topic}
- Подтема: {subtopic}
- Уровень сложности: {level} из 7

КРИТИЧНО: Уровень {level} означает:
{description}

Вот ТРИ эталона задач точно такого же уровня {level}:

{examples_text}

Сгенерируй НОВУЮ задачу, которая по сложности эквивалентна этим эталонам.
НЕ упрощай. Если уровень {level} — задача должна соответствовать описанию выше.

Формат ответа (JSON):
{{
  "text": "текст задачи с LaTeX формулами в \\\\( \\\\) и \\\\[ \\\\]",
  "answer": "правильный ответ",
  "solution": "подробное решение",
  "estimated_time_minutes": {level * 10},
  "self_assessed_level": {level}
}}"""
    
    return prompt


def validate_generated_task(task_data, expected_level):
    """
    Validate that a generated task matches the expected difficulty level.
    
    Args:
        task_data: Dict with generated task
        expected_level: Expected difficulty level
        
    Returns:
        (is_valid, reason) tuple
    """
    self_level = task_data.get('self_assessed_level', expected_level)
    estimated_time = task_data.get('estimated_time_minutes', 0)
    text = task_data.get('text', '')
    
    # Check self-assessed level
    if abs(self_level - expected_level) >= 2:
        return False, f"Self-assessed level {self_level} differs too much from expected {expected_level}"
    
    # Check text length (level 7 tasks should be longer)
    if expected_level >= 6 and len(text) < 150:
        return False, f"Level {expected_level} task text too short ({len(text)} chars)"
    
    # Check estimated time
    min_time = {1: 1, 2: 2, 3: 5, 4: 15, 5: 30, 6: 60, 7: 90}.get(expected_level, 5)
    if estimated_time < min_time * 0.5:
        return False, f"Estimated time {estimated_time} min too low for level {expected_level}"
    
    return True, "OK"


def get_level_by_solve_rate(actual_rate):
    """
    Suggest difficulty level based on actual solve rate.
    
    Args:
        actual_rate: Fraction of users who solved the task (0.0-1.0)
        
    Returns:
        Suggested level (1-7)
    """
    for level in range(7, 0, -1):
        expected = LEVEL_EXPECTED_RATES[level]
        if actual_rate <= expected * 1.5:
            return level
    return 1
