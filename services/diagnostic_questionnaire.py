# -*- coding: utf-8 -*-
"""
Анкета из 3 вопросов для определения стартового уровня ученика.
Используется куратором после выбора класса вместо 21-задачной диагностики.
"""

QUESTIONNAIRE_FLOW = [
    {
        "field": "daily_minutes",
        "question": "Сколько минут в день ты готов заниматься математикой? (напиши число)",
        "type": "number",
    },
    {
        "field": "goal_text",
        "question": "Какая у тебя цель? Напиши один из вариантов:\n"
                     "• «Школьная программа» — подтянуть текущие темы\n"
                     "• «ОГЭ/ЕГЭ» — подготовиться к экзаменам\n"
                     "• «Олимпиады» — ВсОШ и другие олимпиады",
        "type": "choice",
        "options": ["Школьная программа", "ОГЭ/ЕГЭ", "Олимпиады"],
    },
    {
        "field": "self_confidence",
        "question": "Насколько уверенно ты себя чувствуешь в математике?\n"
                     "1 — совсем не уверен\n"
                     "5 — очень уверен\n"
                     "(напиши число от 1 до 5)",
        "type": "number",
        "min": 1,
        "max": 5,
    },
]


def get_question(index):
    """Вернуть вопрос анкеты по индексу (0-based)."""
    if 0 <= index < len(QUESTIONNAIRE_FLOW):
        return QUESTIONNAIRE_FLOW[index]
    return None


def compute_provisional_level(answers):
    """Вычислить предварительный уровень (1-5) на основе ответов анкеты.

    Логика:
    - База: self_confidence (1-5)
    - Цель «Олимпиады» → +1 уровень (амбициозный)
    - Цель «Школьная программа» → без изменений
    - Готов заниматься ≤ 15 мин → −1 (меньше практики)
    - Готов заниматься ≥ 60 мин → +1 (больше практики)
    """
    try:
        confidence = int(answers.get('self_confidence', 3))
    except (ValueError, TypeError):
        confidence = 3
    base = max(1, min(5, confidence))

    goal = str(answers.get('goal_text', '')).lower()
    if 'олимпиад' in goal:
        base = min(5, base + 1)
    elif 'огэ' in goal or 'егэ' in goal:
        base = base  # нейтрально

    try:
        minutes = int(answers.get('daily_minutes', 30))
    except (ValueError, TypeError):
        minutes = 30

    if minutes <= 15:
        base = max(1, base - 1)
    elif minutes >= 60:
        base = min(5, base + 1)

    return base


def get_test_start_level(level):
    """Стартовый уровень для адаптивного теста на основе анкетного уровня."""
    return max(1, level - 1)


def build_summary(answers, level):
    """Построить текстовое резюме после завершения анкеты."""
    labels = {
        1: '🔵 Начальный',
        2: '🟢 Базовый',
        3: '🟡 Средний',
        4: '🟠 Продвинутый',
        5: '🔴 Высокий',
    }
    label = labels.get(level, '🟡 Средний')

    goal = answers.get('goal_text', 'не указана')
    minutes = answers.get('daily_minutes', '?')

    return (
        f"🎉 <strong>Анкета пройдена!</strong>\n\n"
        f"📊 <strong>Твой уровень:</strong> {label} (уровень {level}/5)\n"
        f"📝 Цель: {goal}\n"
        f"⏱ Готов заниматься: {minutes} мин/день\n\n"
        f"Теперь ты можешь пройти тест по темам — "
        f"адаптивный тест будет настроен под твой уровень!"
    )
