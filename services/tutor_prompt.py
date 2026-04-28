# -*- coding: utf-8 -*-
"""
tutor_prompt.py — Построитель промптов для AI-тьютора FORMYLA.

Ключевое улучшение: тьютор получает правильный ответ и эталонное
решение из БД — не решает задачу заново, а направляет ученика
к известному ответу.

Использование:
    from services.tutor_prompt import build_tutor_messages, detect_final_answer

    messages = build_tutor_messages(
        task=task_dict,
        user_message="Дай подсказку",
        chat_history=[...],
        hint_mode=True,
        user=current_user,
    )
    response = deepseek_client.chat_raw(messages)
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── Тема → русское название ───────────────────────────────────────────────────

TOPIC_NAMES = {
    'algebra': 'Алгебра',
    'geometry': 'Геометрия',
    'number_theory': 'Теория чисел',
    'combinatorics': 'Комбинаторика',
    'movement': 'Задачи на движение',
    'logic': 'Логика',
    'arithmetic': 'Арифметика',
    'kl_movement': 'Задачи на движение',
    'general': 'Математика',
}


def _topic_ru(topic: str) -> str:
    return TOPIC_NAMES.get(topic, topic.replace('_', ' ').capitalize())


# ── Основной prompt builder ───────────────────────────────────────────────────

def build_tutor_messages(
    task: Optional[dict],
    user_message: str,
    chat_history: list,
    hint_mode: bool = True,
    user=None,
    max_history: int = 15,
) -> list:
    """
    Строит список messages для LLM с контекстом задачи из БД.

    Args:
        task: dict с полями task_text, correct_answer, solution, topic,
              class_level, difficulty. Может быть None (общий чат).
        user_message: текущее сообщение пользователя
        chat_history: список {'role': ..., 'content': ...}
        hint_mode: True = подсказки, False = полное решение
        user: объект User (для персонализации)
        max_history: максимум сообщений из истории

    Returns:
        list of {'role': ..., 'content': ...} для LLM
    """
    system = _build_system_prompt(task, hint_mode, user)

    messages = [{'role': 'system', 'content': system}]

    # История (последние N сообщений)
    for msg in chat_history[-max_history:]:
        role = msg.get('role', 'user')
        content = msg.get('content', '')
        if role in ('user', 'assistant') and content:
            messages.append({'role': role, 'content': content})

    messages.append({'role': 'user', 'content': user_message})
    return messages


def _build_system_prompt(task: Optional[dict], hint_mode: bool, user) -> str:
    """Строит системный промпт с контекстом задачи."""

    # ── Базовая информация о пользователе ─────────────────────────────────────
    grade_info = ''
    if task:
        grade = task.get('class_level') or task.get('grade')
        if grade:
            grade_info = f'для ученика {grade} класса'

    user_level = ''
    if user and hasattr(user, 'math_level') and user.math_level:
        level_map = {
            'beginner': 'начинающего уровня',
            'intermediate': 'среднего уровня',
            'advanced': 'продвинутого уровня',
        }
        user_level = level_map.get(user.math_level, '')

    # ── Блок с задачей (если есть) ────────────────────────────────────────────
    task_block = ''
    if task:
        task_text = task.get('task_text') or task.get('text') or ''
        correct_answer = task.get('correct_answer') or task.get('answer') or ''
        solution = task.get('solution') or ''
        topic = task.get('topic') or task.get('subject') or 'general'
        difficulty = task.get('difficulty') or task.get('level') or ''

        topic_ru = _topic_ru(topic)
        diff_str = f', сложность {difficulty}/5' if difficulty else ''

        task_block = f"""
══════════════════════════════════════════════════════
ЗАДАЧА КОТОРУЮ РЕШАЕТ УЧЕНИК (тема: {topic_ru}{diff_str}):

{task_text}
══════════════════════════════════════════════════════
ВНУТРЕННЯЯ ИНФОРМАЦИЯ — НЕ ПОКАЗЫВАЙ УЧЕНИКУ НАПРЯМУЮ:

ПРАВИЛЬНЫЙ ОТВЕТ: {correct_answer if correct_answer else '(не указан)'}

ЭТАЛОННОЕ РЕШЕНИЕ:
{solution if solution else '(решение не загружено из БД)'}
══════════════════════════════════════════════════════"""

    # ── Режим работы ──────────────────────────────────────────────────────────
    if hint_mode:
        mode_instruction = """
РЕЖИМ: ПОДСКАЗКИ (не раскрывай решение полностью)
- Задавай наводящие вопросы
- Указывай на ключевую идею или метод
- Если ученик близок к ответу — подтверди направление
- Если ученик ошибся — укажи где именно, без раскрытия пути
- Если ученик прямо просит "покажи решение" — покажи эталонное"""
    else:
        mode_instruction = """
РЕЖИМ: ПОЛНОЕ РЕШЕНИЕ
- Покажи эталонное решение пошагово
- Объясни каждый шаг
- Укажи ключевую идею метода"""

    # ── Правила оформления ────────────────────────────────────────────────────
    formatting_rules = """
ПРАВИЛА ОФОРМЛЕНИЯ:
- Формулы: используй $...$ для inline и $$...$$ для display (рендерится через KaTeX)
- Например: $x^2 + y^2 = r^2$ или $$\\frac{a}{b} = c$$
- Шаги решения: **Шаг 1**, **Шаг 2** (жирный)
- Ответ: **Ответ: 42** (жирный)
- Стиль: дружелюбно, на "ты", кратко (3-5 предложений в подсказке)
- Эмодзи: только при правильном ответе (✓, 🎉)"""

    # ── Запреты ───────────────────────────────────────────────────────────────
    prohibitions = """
ЗАПРЕЩЕНО:
- Говорить "по эталонному решению..." или "согласно БД..."
- Решать задачу заново своим способом (используй эталон)
- Выдавать ответ если ученик не просил
- Отказываться помогать из-за "специализации" — помогай с любой математикой"""

    # ── Сборка промпта ────────────────────────────────────────────────────────
    intro = f"Ты — терпеливый математический тьютор {grade_info} {user_level} на платформе FORMYLA."

    if task:
        core = f"""{intro}

Ты ЗНАЕШЬ правильный ответ и эталонное решение — используй их как опору.
НЕ решай задачу заново. Направляй ученика к известному ответу.
{task_block}
{mode_instruction}
{formatting_rules}
{prohibitions}"""
    else:
        # Общий чат без конкретной задачи
        core = f"""{intro}

Помогай с любыми математическими вопросами.
Если ученик присылает задачу — помогай решить её шаг за шагом.
{mode_instruction}
{formatting_rules}
{prohibitions}"""

    return core.strip()


# ── Детектор финального ответа ────────────────────────────────────────────────

def detect_final_answer(user_message: str) -> bool:
    """
    Определяет, похоже ли сообщение на финальный ответ ученика.

    Используется для self-check: сравнить ответ ученика с correct_answer.

    Returns:
        True если похоже на финальный ответ
    """
    msg_lower = user_message.lower().strip()

    # Триггеры финального ответа
    triggers = [
        'ответ:', 'ответ =', 'ответ:',
        'итого', 'итог:', 'итого:',
        'получилось', 'получается',
        'у меня получилось', 'я получил', 'я получила',
        'мой ответ', 'мой результат',
        'это и есть', 'значит ответ',
        'ответ равен', 'равно',
        'проверь мой', 'правильно ли',
        'я думаю ответ', 'наверное',
    ]

    for trigger in triggers:
        if trigger in msg_lower:
            return True

    # Если сообщение короткое и содержит число/выражение — вероятно ответ
    if len(user_message.strip()) < 30:
        import re
        # Содержит число или математическое выражение
        if re.search(r'\d+', user_message):
            return True

    return False


def check_answer_match(user_message: str, correct_answer: str) -> Optional[str]:
    """
    Простая проверка: совпадает ли ответ ученика с правильным.

    Используется для быстрого self-check без дополнительного LLM-вызова.

    Returns:
        'correct' | 'incorrect' | 'unclear'
    """
    if not correct_answer:
        return 'unclear'

    import re

    # Нормализуем: убираем пробелы, приводим к нижнему регистру
    def normalize(s: str) -> str:
        s = s.lower().strip()
        s = re.sub(r'\s+', '', s)
        s = s.replace(',', '.').replace('−', '-')
        return s

    user_norm = normalize(user_message)
    correct_norm = normalize(correct_answer)

    # Прямое совпадение
    if correct_norm in user_norm or user_norm == correct_norm:
        return 'correct'

    # Числовое совпадение
    user_nums = re.findall(r'-?\d+\.?\d*', user_norm)
    correct_nums = re.findall(r'-?\d+\.?\d*', correct_norm)

    if user_nums and correct_nums:
        try:
            if abs(float(user_nums[-1]) - float(correct_nums[0])) < 1e-6:
                return 'correct'
        except ValueError:
            pass

    return 'unclear'


# ── Загрузка задачи из БД ─────────────────────────────────────────────────────

def load_task_for_tutor(task_id: int, task_source: str = 'adaptive') -> Optional[dict]:
    """
    Загружает задачу из БД для передачи тьютору.

    Args:
        task_id: ID задачи
        task_source: 'adaptive' (adaptive_tasks) | 'problems' (PROBLEMS_DB)

    Returns:
        dict с полями task_text, correct_answer, solution, topic, class_level
        или None если задача не найдена
    """
    try:
        if task_source == 'adaptive':
            from models import AdaptiveTask
            task = AdaptiveTask.query.get(task_id)
            if task:
                return {
                    'task_text': task.task_text or '',
                    'correct_answer': task.correct_answer or '',
                    'solution': task.solution or '',
                    'topic': task.topic or 'general',
                    'class_level': task.class_level,
                    'difficulty': task.difficulty,
                    'source': 'adaptive',
                    'id': task.id,
                }
        elif task_source == 'problems':
            # Из in-memory PROBLEMS_DB
            try:
                from app import PROBLEMS_DB, _RAW_DB
                problem = next((p for p in PROBLEMS_DB if p.get('id') == task_id), None)
                if not problem:
                    problem = next((p for p in _RAW_DB if p.get('id') == task_id), None)
                if problem:
                    return {
                        'task_text': problem.get('text') or problem.get('task_text') or '',
                        'correct_answer': problem.get('answer') or problem.get('correct_answer') or '',
                        'solution': problem.get('solution') or '',
                        'topic': problem.get('subject') or problem.get('topic') or 'general',
                        'class_level': problem.get('grade'),
                        'difficulty': problem.get('difficulty') or problem.get('level'),
                        'source': 'problems',
                        'id': task_id,
                    }
            except ImportError:
                pass
    except Exception as e:
        logger.warning(f'[tutor_prompt] load_task_for_tutor({task_id}, {task_source}): {e}')

    return None
