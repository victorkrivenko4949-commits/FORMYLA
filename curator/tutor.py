# -*- coding: utf-8 -*-
"""
tutor.py — Модуль AI-тьютора для помощи с олимпиадными задачами.

Функции:
  - Выдача задач, соответствующих текущему уровню и теме плана.
  - Пошаговые подсказки (hints) без выдачи готового решения.
  - Проверка решения ученика и разбор ошибок.
  - Объяснение методов и идей.

Использует OpenRouter/DeepSeek для генерации подсказок и проверки.
Интегрируется с существующим сервисом ai_tutor_review.
"""

import json
import logging
from datetime import datetime
from typing import List, Dict, Optional, Tuple

from models import db
from curator.models import CuratorTaskAttempt, LearningPlan

logger = logging.getLogger(__name__)

# AI-модели
HINT_MODEL = "deepseek/deepseek-chat"
REVIEW_MODEL = "deepseek/deepseek-chat"

# Максимум подсказок на задачу
MAX_HINTS = 3


# ─── Публичные функции ────────────────────────────────────────────────────────

def get_hints(
    task_id: int,
    task_text: str,
    topic: str,
    difficulty: int,
    hints_already_shown: int = 0,
) -> List[str]:
    """Сгенерировать пошаговые подсказки для задачи.

    Args:
        task_id: ID задачи.
        task_text: Текст задачи.
        topic: Тема задачи.
        difficulty: Уровень сложности (1-8).
        hints_already_shown: Сколько подсказок уже показано.

    Returns:
        list[str] — список подсказок (1-3 шт.).
    """
    remaining = MAX_HINTS - hints_already_shown
    if remaining <= 0:
        return ['Ты использовал все подсказки для этой задачи.']

    prompt = _build_hint_prompt(task_text, topic, difficulty, hints_already_shown)

    try:
        from services.openrouter_client import openrouter

        response = openrouter.chat(
            model=HINT_MODEL,
            messages=[
                {'role': 'system', 'content': _HINT_SYSTEM_PROMPT},
                {'role': 'user', 'content': prompt},
            ],
            temperature=0.4,
            max_tokens=1024,
        )
        content = response.get('content', '').strip()

        # Парсим JSON-ответ
        hints = _parse_hints_response(content, remaining)
        return hints

    except Exception as e:
        logger.error(f"[tutor] Hint generation failed for task {task_id}: {e}")
        return _get_fallback_hints(topic, difficulty, hints_already_shown)


def review_solution(
    user_id: int,
    task_id: int,
    task_text: str,
    user_answer: str,
    correct_answer: str,
    solution: str = '',
    topic: str = '',
    difficulty: int = None,
    plan_id: int = None,
    task_source: str = 'curator_plan',
) -> dict:
    """Проверить решение ученика и записать попытку.

    Args:
        user_id: ID пользователя.
        task_id: ID задачи.
        task_text: Текст задачи.
        user_answer: Ответ ученика.
        correct_answer: Правильный ответ.
        solution: Эталонное решение.
        topic: Тема задачи.
        difficulty: Уровень сложности.
        plan_id: ID плана (если задача из плана).
        task_source: Источник задачи.

    Returns:
        dict с результатом проверки.
    """
    # Пытаемся использовать существующий сервис AI-проверки
    review_result = _ai_review(task_text, correct_answer, user_answer, solution)

    # Определяем правильность
    is_correct = review_result.get('answer_correct', False)

    # Записываем попытку
    attempt = CuratorTaskAttempt(
        user_id=user_id,
        task_id=task_id,
        task_source=task_source,
        task_type='practice',
        plan_id=plan_id,
        topic=topic,
        difficulty=difficulty,
        user_answer=user_answer,
        correct_answer=correct_answer,
        is_correct=is_correct,
        time_spent_sec=review_result.get('time_spent_sec'),
        ai_feedback=json.dumps(review_result, ensure_ascii=False),
        method_score=review_result.get('confidence', 0.5),
        attempted_at=datetime.utcnow(),
    )
    db.session.add(attempt)
    db.session.commit()

    return {
        'attempt_id': attempt.id,
        'is_correct': is_correct,
        'method_correct': review_result.get('method_correct', False),
        'category': review_result.get('category', 'unknown'),
        'confidence': review_result.get('confidence', 0.5),
        'feedback': review_result.get('feedback', ''),
        'error_location': review_result.get('error_location'),
        'topic': topic,
        'difficulty': difficulty,
    }


def get_task_explanation(task_text: str, solution: str, topic: str) -> str:
    """Сгенерировать объяснение метода решения задачи.

    Args:
        task_text: Текст задачи.
        solution: Эталонное решение.
        topic: Тема задачи.

    Returns:
        str — объяснение метода на русском языке.
    """
    prompt = (
        f"Объясни метод решения этой {TOPIC_LABELS_RU.get(topic, 'олимпиадной')} задачи "
        f"так, чтобы ученик понял ключевую идею, а не просто запомнил шаги.\n\n"
        f"ЗАДАЧА:\n{task_text}\n\n"
        f"РЕШЕНИЕ:\n{solution}\n\n"
        f"ОБЪЯСНЕНИЕ (максимум 300 символов, на русском):"
    )

    try:
        from services.openrouter_client import openrouter

        response = openrouter.chat(
            model=HINT_MODEL,
            messages=[
                {'role': 'system', 'content': _EXPLANATION_SYSTEM_PROMPT},
                {'role': 'user', 'content': prompt},
            ],
            temperature=0.3,
            max_tokens=512,
        )
        return response.get('content', '').strip()
    except Exception as e:
        logger.error(f"[tutor] Explanation failed: {e}")
        return 'Попробуй разобрать решение по шагам. Если что-то непонятно, задай вопрос куратору.'


def get_user_attempts(user_id: int, task_id: int) -> List[dict]:
    """Получить историю попыток пользователя по задаче.

    Args:
        user_id: ID пользователя.
        task_id: ID задачи.

    Returns:
        list[dict] — список попыток.
    """
    attempts = (
        CuratorTaskAttempt.query
        .filter_by(user_id=user_id, task_id=task_id)
        .order_by(CuratorTaskAttempt.attempted_at.desc())
        .all()
    )

    return [
        {
            'id': a.id,
            'is_correct': a.is_correct,
            'user_answer': a.user_answer,
            'method_score': a.method_score,
            'time_spent_sec': a.time_spent_sec,
            'used_hints': a.used_hints,
            'hints_shown': a.hints_shown,
            'attempted_at': a.attempted_at.isoformat() if a.attempted_at else None,
        }
        for a in attempts
    ]


# ─── Константы AI-промптов ───────────────────────────────────────────────────

_HINT_SYSTEM_PROMPT = (
    "Ты — AI-тьютор платформы FORMYLA. Твоя задача — давать пошаговые подсказки "
    "к олимпиадным задачам по математике.\n\n"
    "ПРАВИЛА:\n"
    "1. НЕ давай полное решение сразу. Подсказки должны наводить на мысль.\n"
    "2. Первая подсказка — самая общая (идея, метод).\n"
    "3. Вторая подсказка — конкретнее (ключевой шаг).\n"
    "4. Третья подсказка — почти решение (но не до конца).\n"
    "5. Используй математические обозначения LaTeX где уместно ($...$).\n"
    "6. Пиши на русском языке, обращайся на «ты».\n\n"
    "ФОРМАТ ОТВЕТА — СТРОГО JSON (без markdown):\n"
    '{"hints": ["подсказка 1", "подсказка 2", ...]}\n\n'
    "Верни ровно столько подсказок, сколько запрошено (не больше 3)."
)

_EXPLANATION_SYSTEM_PROMPT = (
    "Ты — AI-тьютор платформы FORMYLA. Объясни метод решения задачи "
    "так, чтобы ученик понял ключевую идею.\n\n"
    "ПРАВИЛА:\n"
    "- Не просто пересказывай решение, а объясни ПОЧЕМУ этот метод работает.\n"
    "- Выдели ключевой инсайт / трюк.\n"
    "- Используй LaTeX для формул ($...$).\n"
    "- Пиши на русском, обращайся на «ты».\n"
    "- Максимум 300 символов."
)


# ─── Внутренние функции ──────────────────────────────────────────────────────

def _build_hint_prompt(task_text: str, topic: str, difficulty: int,
                       hints_already_shown: int) -> str:
    """Собрать промпт для генерации подсказок."""
    remaining = MAX_HINTS - hints_already_shown
    topic_label = TOPIC_LABELS_RU.get(topic, topic)

    return (
        f"Задача по {topic_label}, уровень сложности {difficulty}/8.\n\n"
        f"УСЛОВИЕ:\n{task_text}\n\n"
        f"Уже показано подсказок: {hints_already_shown}.\n"
        f"Требуется сгенерировать {remaining} новых подсказок "
        f"(всего {hints_already_shown + remaining} из {MAX_HINTS}).\n\n"
        f"Подсказка #{hints_already_shown + 1} должна быть "
        f"{'общей (идея/метод)' if hints_already_shown == 0 else 'конкретной (ключевой шаг)' if hints_already_shown == 1 else 'детальной (почти решение)'}.\n"
        f"ВАЖНО: Если hints_already_shown >= {MAX_HINTS}, верни пустой массив."
    )


def _parse_hints_response(content: str, expected_count: int) -> List[str]:
    """Распарсить JSON-ответ от AI."""
    # Очищаем от markdown-обёртки
    content = content.strip()
    if content.startswith('```'):
        content = content.split('\n', 1)[-1]
        content = content.rsplit('```', 1)[0].strip()

    try:
        data = json.loads(content)
        hints = data.get('hints', [])
        if isinstance(hints, list):
            return hints[:expected_count]
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning(f"[tutor] Failed to parse hints JSON: {e}")
        # Пробуем извлечь как plain text
        if content:
            return [content]

    return _get_fallback_hints('algebra', 4, 0)


def _get_fallback_hints(topic: str, difficulty: int, hints_shown: int) -> List[str]:
    """Fallback-подсказки без AI."""
    remaining = MAX_HINTS - hints_shown

    fallbacks = [
        'Попробуй переформулировать условие задачи своими словами.',
        'Какие известные теоремы или методы можно применить?',
        'Попробуй решить задачу с конца — какой ответ должен получиться?',
    ]

    return fallbacks[hints_shown:hints_shown + remaining]


def _ai_review(task_text: str, correct_answer: str, user_answer: str,
               solution: str) -> dict:
    """Проверить решение через AI.

    Сначала пробует существующий сервис ai_tutor_review, затем fallback.
    """
    # Пробуем существующий сервис
    try:
        from services.ai_tutor_review import review_attempt

        result = review_attempt(
            task_text=task_text,
            correct_answer=correct_answer,
            student_answer=user_answer,
            solution=solution,
            problem_type='numeric',  # Определяем тип
        )
        if result and isinstance(result, dict):
            return result
    except Exception as e:
        logger.debug(f"[tutor] ai_tutor_review not available: {e}")

    # Fallback: простой AI-запрос
    prompt = (
        f"Задача: {task_text}\n\n"
        f"Правильный ответ: {correct_answer}\n\n"
        f"Ответ ученика: {user_answer}\n\n"
        f"Эталонное решение: {solution}\n\n"
        f"Проверь ответ ученика. Верни JSON."
    )

    try:
        from services.openrouter_client import openrouter

        response = openrouter.chat(
            model=REVIEW_MODEL,
            messages=[
                {'role': 'system', 'content': _REVIEW_FALLBACK_SYSTEM_PROMPT},
                {'role': 'user', 'content': prompt},
            ],
            temperature=0.2,
            max_tokens=512,
        )
        content = response.get('content', '').strip()

        # Парсим JSON
        content = content.strip()
        if content.startswith('```'):
            content = content.split('\n', 1)[-1]
            content = content.rsplit('```', 1)[0].strip()

        result = json.loads(content)
        return result
    except Exception as e:
        logger.error(f"[tutor] AI review fallback failed: {e}")

    # Последний fallback: простое сравнение
    is_correct = user_answer.strip().lower() == correct_answer.strip().lower()
    return {
        'answer_correct': is_correct,
        'method_correct': is_correct,
        'category': 'correct' if is_correct else 'wrong_answer_wrong_method',
        'confidence': 0.5,
        'error_location': None,
        'feedback': 'Верно!' if is_correct else 'Проверь свой ответ. Попробуй ещё раз.',
    }


_REVIEW_FALLBACK_SYSTEM_PROMPT = (
    "Ты — проверяющий математических задач платформы FORMYLA.\n"
    "У тебя ЕСТЬ правильный ответ из БД. Сравни ответ ученика с каноном.\n\n"
    "ФОРМАТ ОТВЕТА — СТРОГО JSON (без markdown):\n"
    '{"answer_correct": true/false, "method_correct": true/false, '
    '"category": "correct|wrong_answer_wrong_method|wrong_answer_good_method|'
    'correct_no_justification|blank|suspicious", '
    '"confidence": 0.0-1.0, "error_location": "... или null", '
    '"feedback": "..."}'
)

# Маппинг тем
TOPIC_LABELS_RU = {
    'algebra': 'алгебраической',
    'geometry': 'геометрической',
    'combinatorics': 'комбинаторной',
    'number_theory': 'теоретико-числовой',
    'logic': 'логической',
    'algebraic': 'алгебраической',
    'geometric': 'геометрической',
}
