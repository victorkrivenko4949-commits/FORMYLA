# -*- coding: utf-8 -*-
"""
Difficulty Calibration Service for FORMYLA
Provides level labels, few-shot examples, and calibration utilities.
"""

# Level labels for UI display
LEVEL_LABELS = {
    1: 'Базовый',
    2: 'Школьный',
    3: 'Муниципальный',
    4: 'Региональный',
}

# Level colors for UI
LEVEL_COLORS = {
    1: '#22c55e',
    2: '#22c55e',
    3: '#fbbf24',
    4: '#ef4444',
}

# Expected solve rates per level (for calibration)
LEVEL_EXPECTED_RATES = {
    1: 0.95,
    2: 0.85,
    3: 0.45,
    4: 0.10,
}

# Level descriptions for prompts
LEVEL_DESCRIPTIONS = {
    1: "Базовый уровень. Прямое применение одной формулы. Решается за 1-2 минуты. 95% учеников решат.",
    2: "Школьный уровень. 2-3 шага, стандартные техники. Решается за 2-5 минут. 80-90% учеников решат.",
    3: "Школьная олимпиада / муниципальный этап. Требует нестандартного подхода или доказательства. 5-15 минут. 40-70% решат.",
    4: "Региональный/Заключительный. Турнир городов, финал Всерос, IMO. 60-120 минут. 5-15% решат.",
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
        "В таблице 3x3 расставлены числа 1-9. Докажи, что можно выбрать 3 клетки (не в одной строке и столбце) с суммой >= 15.",
        "Сколько трёхзначных чисел имеют сумму цифр, равную 5? Ответ: 15",
    ],
    4: [
        "Турнир городов 2019: Докажи, что среди любых 5 целых чисел найдутся три, сумма которых делится на 3.",
        "Найди все целые решения уравнения x^2 - y^2 = 2023.",
        "В выпуклом многоугольнике проведены все диагонали. Докажи, что не все они могут пересекаться в одной точке.",
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
        level: Difficulty level (1-4)
        
    Returns:
        Formatted prompt string
    """
    level_clamped = max(1, min(4, int(level)))
    examples = LEVEL_EXAMPLES.get(level_clamped, LEVEL_EXAMPLES[3])[:3]
    examples_text = '\n\n'.join([
        f'ПРИМЕР {i+1} (уровень {level_clamped}):\n{ex}'
        for i, ex in enumerate(examples)
    ])
    
    description = LEVEL_DESCRIPTIONS.get(level_clamped, LEVEL_DESCRIPTIONS[3])
    
    prompt = f"""Ты — генератор олимпиадных задач для платформы FORMYLA.

ТРЕБОВАНИЯ:
- Класс: {grade}
- Тема: {topic}
- Подтема: {subtopic}
- Уровень сложности: {level_clamped} из 4

КРИТИЧНО: Уровень {level_clamped} означает:
{description}

Вот ТРИ эталона задач точно такого же уровня {level_clamped}:

{examples_text}

Сгенерируй НОВУЮ задачу, которая по сложности эквивалентна этим эталонам.
НЕ упрощай. Если уровень {level_clamped} — задача должна соответствовать описанию выше.

Формат ответа (JSON):
{{
  "text": "текст задачи с LaTeX формулами в \\\\( \\\\) и \\\\[ \\\\]",
  "answer": "правильный ответ",
  "solution": "подробное решение",
  "estimated_time_minutes": {level_clamped * 10},
  "self_assessed_level": {level_clamped}
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
    exp = max(1, min(4, int(expected_level)))
    self_level = task_data.get('self_assessed_level', exp)
    estimated_time = task_data.get('estimated_time_minutes', 0)
    text = task_data.get('text', '')
    
    # Check self-assessed level
    if abs(self_level - exp) >= 2:
        return False, f"Self-assessed level {self_level} differs too much from expected {exp}"
    
    # Check text length (level 4 tasks should be longer)
    if exp >= 4 and len(text) < 150:
        return False, f"Level {exp} task text too short ({len(text)} chars)"
    
    # Check estimated time
    min_time = {1: 1, 2: 2, 3: 10, 4: 30}.get(exp, 5)
    if estimated_time < min_time * 0.5:
        return False, f"Estimated time {estimated_time} min too low for level {exp}"
    
    return True, "OK"


def get_level_by_solve_rate(actual_rate):
    """
    Suggest difficulty level based on actual solve rate.
    
    Args:
        actual_rate: Fraction of users who solved the task (0.0-1.0)
        
    Returns:
        Suggested level (1-4)
    """
    for level in range(4, 0, -1):
        expected = LEVEL_EXPECTED_RATES[level]
        if actual_rate <= expected * 1.5:
            return level
    return 1
