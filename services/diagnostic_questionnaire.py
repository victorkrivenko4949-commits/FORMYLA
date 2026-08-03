# -*- coding: utf-8 -*-
"""
ТОНКИЙ АДАПТЕР: все функции остаются с теми же именами и подписями,
внутри делегируют новой анкете onboarding_tree + onboarding.py.

НИ ОДИН ИМПОРТ НЕ ДОЛЖЕН СЛОМАТЬСЯ.
"""

# ── QUESTIONNAIRE_FLOW — совместимый список из 3 вопросов ──
# Старый код импортирует len(QUESTIONNAIRE_FLOW) для total.
QUESTIONNAIRE_FLOW = [
    {"field": "daily_minutes", "question": "Сколько минут в день ты готов заниматься математикой? (напиши число)", "type": "number"},
    {"field": "goal_text",     "question": "Какая у тебя цель?", "type": "choice", "options": ["Школьная программа", "ОГЭ/ЕГЭ", "Олимпиады"]},
    {"field": "self_confidence","question": "Насколько уверенно ты себя чувствуешь в математике? (1-5)", "type": "number", "min": 1, "max": 5},
]


def get_question(index):
    """Вернуть вопрос анкеты по индексу (0-based). Совместимость со старым кодом."""
    if 0 <= index < len(QUESTIONNAIRE_FLOW):
        return QUESTIONNAIRE_FLOW[index]
    return None


def compute_provisional_level(answers, return_full=False):
    """Вычислить предварительный уровень (1-5) — делегирует onboarding_tree.

    Для обратной совместимости: если ответы в старом формате
    (daily_minutes, goal_text, self_confidence), эмулирует результат
    через новую логику. Если ответы уже в новом формате — использует
    compute_prior напрямую.

    Все поля answers опциональны — compute_prior обрабатывает
    недостающие ключи значениями по умолчанию.

    Параметры:
        answers:     словарь ответов старого формата
        return_full: если True — возвращает (level, OnboardingResult),
                     иначе только level (int) для обратной совместимости
    """
    from services.onboarding_tree import compute_prior as _compute_prior

    # Пытаемся привести старый формат к новому
    old_goal = str(answers.get('goal_text', '')).lower()
    if 'олимпиад' in old_goal:
        goal = 'olympiad'
    elif 'огэ' in old_goal or 'егэ' in old_goal:
        goal = 'exam'
    elif 'школ' in old_goal:
        goal = 'school'
    else:
        goal = answers.get('goal', 'fun')

    # Пытаемся извлечь self_confidence как приближение к mu
    try:
        confidence = int(answers.get('self_confidence', 3))
    except (ValueError, TypeError):
        confidence = 3

    try:
        minutes = int(answers.get('daily_minutes', 30))
    except (ValueError, TypeError):
        minutes = 30

    # Эмулируем ответы новой анкеты на основе старых.
    # ВСЕ ожидаемые compute_prior ключи должны присутствовать (хоть с дефолтами).
    new_answers = {
        'grade': str(answers.get('grade', 9)),
        'target': 'lvl3',
        'olymp_reach': 'none',
        'goal': goal,
        'load': 'm15' if minutes <= 15 else ('m60' if minutes >= 60 else 'm30'),
        'deadline': 'none',
    }

    # Подставляем маркер в зависимости от цели
    if goal == 'olympiad':
        level_map = {1: 'none', 2: 'school', 3: 'muni', 4: 'region', 5: 'region'}
        new_answers['olymp_reach'] = level_map.get(confidence, 'muni')
    elif goal == 'exam':
        score_map = {1: 'lt50', 2: 'lt50', 3: '50_70', 4: '70_85', 5: 'gt85'}
        new_answers['exam_score'] = score_map.get(confidence, '50_70')
    elif goal == 'school':
        mark_map = {1: '3', 2: '3', 3: '4', 4: '4', 5: '5'}
        new_answers['school_mark'] = mark_map.get(confidence, '4')
    else:
        exp_map = {1: 'never', 2: 'never', 3: 'some', 4: 'lot', 5: 'lot'}
        new_answers['prior_exp'] = exp_map.get(confidence, 'some')

    result = _compute_prior(new_answers, [])
    level = int(round(result.prior_mu))
    level = max(1, min(5, level))

    if return_full:
        return level, result
    return level


def get_test_start_level(level):
    """Стартовый уровень для адаптивного теста."""
    return max(1, level - 1)


def build_summary(answers, level):
    """Построить текстовое резюме после завершения анкеты."""
    labels = {
        1: ' Начальный',
        2: ' Базовый',
        3: ' Средний',
        4: ' Продвинутый',
        5: ' Высокий',
    }
    label = labels.get(level, ' Средний')

    goal = answers.get('goal_text', 'не указана')
    minutes = answers.get('daily_minutes', '?')

    return (
        f" <strong>Анкета пройдена!</strong>\n\n"
        f" <strong>Твой уровень:</strong> {label} (уровень {level}/5)\n"
        f" Цель: {goal}\n"
        f"⏱ Готов заниматься: {minutes} мин/день\n\n"
        f"Теперь ты можешь пройти тест по темам — "
        f"адаптивный тест будет настроен под твой уровень!"
    )
