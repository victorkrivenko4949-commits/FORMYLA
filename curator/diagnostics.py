# -*- coding: utf-8 -*-
"""
diagnostics.py — Модуль адаптивного входного тестирования (диагностики).

Алгоритм:
  1. Начать с вопросов среднего уровня (уровень 4 из 8).
  2. После каждого ответа корректировать уровень сложности:
     - Правильный ответ -> уровень +1 (сложнее)
     - Неправильный ответ -> уровень -1 (проще)
  3. Каждая тема (алгебра, геометрия, комбинаторика, теория чисел, логика)
     получает минимум 3 вопроса.
  4. Результат: профиль ученика с оценкой по каждой теме (0-100%).

Использует банк задач из TaskBank (таблица task_bank) и
OpenRouter/DeepSeek для генерации AI-резюме.
"""

import json
import logging
import random
from datetime import datetime
from typing import Optional, List, Dict

from models import db
from curator.models import StudentDiagnostic
from curator.config import (
    DIAG_TOPICS, TOPIC_LABELS_RU,
    MIN_QUESTIONS_PER_TOPIC, MAX_QUESTIONS_PER_TOPIC,
    TOTAL_QUESTIONS_TARGET,
    MIN_DIFFICULTY, MAX_DIFFICULTY, START_DIFFICULTY,
    CALIBRATION_QUESTIONS, SUMMARY_MODEL,
)

logger = logging.getLogger(__name__)


# ─── Публичные функции ────────────────────────────────────────────────────────

def start_diagnostic_session(user_id: int, grade: int = None) -> StudentDiagnostic:
    """Создать новую сессию диагностики.

    Args:
        user_id: ID пользователя.
        grade: Класс ученика (5-11).

    Returns:
        StudentDiagnostic — новая сессия со статусом 'in_progress'.
    """
    session = StudentDiagnostic(
        user_id=user_id,
        grade=grade,
        status='in_progress',
        started_at=datetime.utcnow(),
        question_log='[]',
        profile_json=json.dumps({topic: {'pct': 0, 'level': 0, 'tasks_correct': 0, 'tasks_total': 0}
                                 for topic in DIAG_TOPICS}, ensure_ascii=False),
    )
    db.session.add(session)
    db.session.flush()
    db.session.commit()
    logger.info(f"[diagnostics] Session #{session.id} started for user={user_id}")
    return session


def get_next_question(session_id: int) -> Optional[dict]:
    """Получить следующий вопрос для диагностической сессии.

    Адаптивный алгоритм:
    - Отслеживает текущий уровень по каждой теме.
    - Выбирает тему с наименьшим количеством вопросов (или случайно).
    - Подбирает задачу подходящего уровня сложности.

    Args:
        session_id: ID сессии диагностики.

    Returns:
        dict с полями {task_id, topic, difficulty, question_text, ...}
        или None, если тест завершён.
    """
    session = db.session.get(StudentDiagnostic, session_id)
    if not session or session.status == 'completed':
        return None

    profile = session.profile
    question_log = session.question_log_list

    # Собираем статистику по темам
    topic_stats = _compute_topic_stats(profile, question_log)

    # Проверяем, достаточно ли вопросов
    if _is_test_complete(topic_stats):
        _finish_session(session, question_log)
        return None

    # Выбираем тему (наименее опрошенную или случайную)
    selected_topic = _select_topic(topic_stats)

    # Определяем текущий уровень сложности для темы
    current_diff = _get_topic_difficulty(profile, selected_topic, question_log)

    # Выбираем задачу из TaskBank
    task = _fetch_task_for_diagnostic(
        topic=selected_topic,
        difficulty=current_diff,
        grade=session.grade,
        exclude_ids=[q.get('task_id') for q in question_log if q.get('task_id')],
    )

    if not task:
        logger.warning(f"[diagnostics] No task found for topic={selected_topic} "
                       f"diff={current_diff}, trying adjacent difficulty")
        # Пробуем соседние уровни
        for adj in [current_diff - 1, current_diff + 1, current_diff - 2, current_diff + 2]:
            if adj < MIN_DIFFICULTY or adj > MAX_DIFFICULTY:
                continue
            task = _fetch_task_for_diagnostic(
                topic=selected_topic,
                difficulty=adj,
                grade=session.grade,
                exclude_ids=[q.get('task_id') for q in question_log if q.get('task_id')],
            )
            if task:
                break

    if not task:
        logger.warning(f"[diagnostics] No task at all for topic={selected_topic}, skipping")
        return None

    return {
        'session_id': session.id,
        'question_index': len(question_log) + 1,
        'task_id': task.id,
        'topic': selected_topic,
        'topic_label': TOPIC_LABELS_RU.get(selected_topic, selected_topic),
        'difficulty': task.difficulty or current_diff,
        'question_text': task.statement,
        'total_questions_target': TOTAL_QUESTIONS_TARGET,
        'questions_answered': len(question_log),
    }


def submit_answer(session_id: int, task_id: int, answer: str,
                  time_spent_sec: int = None) -> dict:
    """Принять ответ ученика и обновить профиль диагностики.

    Args:
        session_id: ID сессии.
        task_id: ID задачи.
        answer: Ответ ученика (текст).
        time_spent_sec: Время на ответ (секунды).

    Returns:
        dict с результатом проверки и обновлённым профилем.
    """
    session = db.session.get(StudentDiagnostic, session_id)
    if not session or session.status == 'completed':
        return {'error': 'Session not found or already completed'}

    # Получаем задачу из БД
    task = _get_task_by_id(task_id)
    if not task:
        return {'error': f'Task {task_id} not found'}

    # Определяем тему из задачи
    topic = _get_task_topic(task)

    # Проверяем ответ (сравниваем с правильным)
    is_correct = _check_answer(task, answer)

    # Обновляем question_log
    question_log = session.question_log_list
    question_log.append({
        'task_id': task_id,
        'topic': topic,
        'difficulty': task.difficulty,
        'user_answer': answer,
        'correct_answer': task.answer,
        'is_correct': is_correct,
        'time_spent_sec': time_spent_sec or 0,
        'answered_at': datetime.utcnow().isoformat(),
    })
    session.question_log_list = question_log

    # Обновляем профиль
    profile = session.profile
    if topic in profile:
        profile[topic]['tasks_total'] += 1
        if is_correct:
            profile[topic]['tasks_correct'] += 1
        pct = (profile[topic]['tasks_correct'] / max(profile[topic]['tasks_total'], 1)) * 100
        profile[topic]['pct'] = round(pct, 1)
        profile[topic]['level'] = _pct_to_level(profile[topic]['pct'])

    session.profile = profile

    # Обновляем общую статистику
    session.total_questions += 1
    if is_correct:
        session.correct_answers += 1

    # Пересчитываем overall_pct
    topic_values = [t['pct'] for t in profile.values()]
    session.overall_pct = round(sum(topic_values) / max(len(topic_values), 1), 1)

    db.session.commit()

    # Проверяем, завершён ли тест
    topic_stats = _compute_topic_stats(profile, question_log)
    is_complete = _is_test_complete(topic_stats)

    if is_complete:
        _finish_session(session, question_log)

    return {
        'is_correct': is_correct,
        'correct_answer': task.answer,
        'solution': task.solution,
        'topic': topic,
        'topic_label': TOPIC_LABELS_RU.get(topic, topic),
        'current_pct': profile.get(topic, {}).get('pct', 0),
        'overall_pct': session.overall_pct,
        'is_test_complete': is_complete,
        'questions_answered': session.total_questions,
        'questions_total': TOTAL_QUESTIONS_TARGET,
    }


def get_diagnostic_result(session_id: int) -> Optional[dict]:
    """Получить результаты диагностики.

    Args:
        session_id: ID сессии.

    Returns:
        dict с полным профилем или None.
    """
    session = db.session.get(StudentDiagnostic, session_id)
    if not session:
        return None

    profile = session.profile

    return {
        'session_id': session.id,
        'user_id': session.user_id,
        'status': session.status,
        'grade': session.grade,
        'overall_pct': session.overall_pct,
        'total_questions': session.total_questions,
        'correct_answers': session.correct_answers,
        'topics': [
            {
                'key': topic,
                'label': TOPIC_LABELS_RU.get(topic, topic),
                'pct': data.get('pct', 0),
                'level': data.get('level', 0),
                'tasks_correct': data.get('tasks_correct', 0),
                'tasks_total': data.get('tasks_total', 0),
            }
            for topic, data in profile.items()
            if data.get('tasks_total', 0) > 0
        ],
        'ai_summary': session.ai_summary,
        'started_at': session.started_at.isoformat() if session.started_at else None,
        'completed_at': session.completed_at.isoformat() if session.completed_at else None,
    }


def generate_ai_summary(session_id: int) -> str:
    """Сгенерировать AI-резюме по результатам диагностики.

    Вызывает DeepSeek через OpenRouter с системным промптом.

    Args:
        session_id: ID сессии.

    Returns:
        str — текст резюме.
    """
    session = db.session.get(StudentDiagnostic, session_id)
    if not session:
        return ''

    result = get_diagnostic_result(session_id)
    if not result:
        return ''

    prompt = _build_ai_summary_prompt(result)

    try:
        from services.openrouter_client import openrouter

        response = openrouter.chat(
            model=SUMMARY_MODEL,
            messages=[
                {'role': 'system', 'content': _DIAG_SUMMARY_SYSTEM_PROMPT},
                {'role': 'user', 'content': prompt},
            ],
            temperature=0.5,
            max_tokens=1024,
        )
        summary = response.get('content', '').strip()
    except Exception as e:
        logger.error(f"[diagnostics] AI summary failed: {e}")
        summary = _build_fallback_summary(result)

    session.ai_summary = summary
    db.session.commit()
    return summary


# ─── Константы AI-промптов ───────────────────────────────────────────────────

_DIAG_SUMMARY_SYSTEM_PROMPT = (
    "Ты — AI-куратор платформы FORMYLA. Твоя задача — написать краткое "
    "персонализированное резюме по результатам диагностики ученика.\n\n"
    "СТРУКТУРА РЕЗЮМЕ:\n"
    "1. Общий уровень подготовки (фраза, обнадёживающая и мотивирующая).\n"
    "2. Сильные стороны темы: какие темы у ученика лучше всего.\n"
    "3. Зоны роста: какие темы нужно подтянуть.\n"
    "4. Рекомендация: что делать дальше (2-3 конкретных шага).\n\n"
    "ПРАВИЛА:\n"
    "- Пиши на русском языке, обращайся на «ты».\n"
    "- Будь конкретным, используй проценты из результатов.\n"
    "- Не используй шаблонные фразы, персонализируй.\n"
    "- Максимум 500 символов.\n"
    "- Закончи мотивирующей фразой."
)


# ─── Внутренние функции ────────────────────────────────────────────────────────

def _compute_topic_stats(profile: dict, question_log: list) -> dict:
    """Вычислить статистику по каждой теме."""
    stats = {}
    for topic in DIAG_TOPICS:
        topic_qs = [q for q in question_log if q.get('topic') == topic]
        profile_topic = profile.get(topic, {})
        stats[topic] = {
            'total': profile_topic.get('tasks_total', len(topic_qs)),
            'correct': profile_topic.get('tasks_correct',
                                          sum(1 for q in topic_qs if q.get('is_correct'))),
            'pct': profile_topic.get('pct', 0),
            'level': profile_topic.get('level', 0),
        }
    return stats


def _is_test_complete(topic_stats: dict) -> bool:
    """Проверить, достаточно ли вопросов для завершения теста."""
    for topic, stats in topic_stats.items():
        if stats['total'] < MIN_QUESTIONS_PER_TOPIC:
            return False

    total = sum(s['total'] for s in topic_stats.values())
    if total < TOTAL_QUESTIONS_TARGET:
        return False

    return True


def _select_topic(topic_stats: dict) -> str:
    """Выбрать тему для следующего вопроса.

    Приоритет: темы с наименьшим количеством вопросов.
    """
    # Сортируем темы по количеству вопросов (возрастание)
    sorted_topics = sorted(topic_stats.items(), key=lambda x: x[1]['total'])

    # Берём тему с минимальным количеством вопросов
    min_count = sorted_topics[0][1]['total']

    # Из тем с минимальным количеством выбираем случайно
    candidates = [t for t, s in sorted_topics if s['total'] == min_count]

    # Если по всем темам уже MIN_QUESTIONS_PER_TOPIC, добираем до TOTAL
    if min_count >= MIN_QUESTIONS_PER_TOPIC:
        return random.choice(sorted_topics)[0]

    return random.choice(candidates)


def _get_topic_difficulty(profile: dict, topic: str, question_log: list) -> int:
    """Определить текущий уровень сложности для темы на основе ответов."""
    topic_questions = [q for q in question_log if q.get('topic') == topic]
    if not topic_questions:
        return START_DIFFICULTY

    last_q = topic_questions[-1]
    last_diff = last_q.get('difficulty', START_DIFFICULTY)
    last_correct = last_q.get('is_correct', False)

    # Адаптивное корректировка
    if last_correct:
        new_diff = last_diff + 1
    else:
        new_diff = last_diff - 1

    return max(MIN_DIFFICULTY, min(MAX_DIFFICULTY, new_diff))


def _fetch_task_for_diagnostic(topic: str, difficulty: int, grade: int = None,
                                exclude_ids: list = None) -> Optional[object]:
    """Выбрать задачу из банка TaskBank для диагностики.

    Использует таблицу task_bank.
    """
    from curator.task_bank import TaskBank

    if exclude_ids is None:
        exclude_ids = []

    # TaskBank не имеет поля grade, поэтому игнорируем grade
    query = TaskBank.query.filter(
        TaskBank.topic == topic,
        TaskBank.difficulty == difficulty,
    )

    if exclude_ids:
        query = query.filter(~TaskBank.id.in_(exclude_ids))

    # Случайный выбор
    tasks = query.all()
    if not tasks:
        return None

    return random.choice(tasks)


def _get_task_by_id(task_id: int) -> Optional[object]:
    """Получить задачу по ID из TaskBank."""
    from curator.task_bank import TaskBank
    return db.session.get(TaskBank, task_id)


def _get_task_topic(task) -> str:
    """Извлечь тему из задачи."""
    topic = getattr(task, 'topic', None) or getattr(task, 'subject', None) or ''
    topic = topic.lower().strip()

    # Маппинг подтем к каноническим темам
    topic_mapping = {
        'algebra': 'algebra',
        'geometry': 'geometry',
        'combinatorics': 'combinatorics',
        'number_theory': 'number_theory',
        'logic': 'logic',
        'knights_liars': 'logic',
        'movement': 'logic',
        'алгебра': 'algebra',
        'геометрия': 'geometry',
        'комбинаторика': 'combinatorics',
        'теория чисел': 'number_theory',
        'логика': 'logic',
        'движение': 'logic',
        'рыцари и лжецы': 'logic',
    }

    return topic_mapping.get(topic, 'algebra')


def _check_answer(task, user_answer: str) -> bool:
    """Проверить ответ ученика.

    Сначала пытается сравнить через существующий сервис ai_tutor_review,
    если недоступен — использует простое сравнение строк.
    """
    if not user_answer or not task.answer:
        return False

    # Пробуем использовать существующий AI-проверщик
    try:
        from services.ai_tutor_review import review_attempt
        result = review_attempt(
            task_text=task.statement,
            correct_answer=task.answer,
            student_answer=user_answer,
            solution=task.solution or '',
            problem_type='numeric',  # TaskBank не имеет answer_type
        )
        if result and 'answer_correct' in result:
            return result['answer_correct']
    except Exception:
        pass

    # Fallback: простое сравнение строк
    user_clean = user_answer.strip().lower()
    correct_clean = task.answer.strip().lower()
    return user_clean == correct_clean


def _pct_to_level(pct: float) -> int:
    """Конвертировать процент в уровень (1-5).

    Level 1: 0-20%  — начальный
    Level 2: 21-40% — базовый
    Level 3: 41-60% — средний
    Level 4: 61-80% — продвинутый
    Level 5: 81-100% — высокий
    """
    if pct >= 81:
        return 5
    elif pct >= 61:
        return 4
    elif pct >= 41:
        return 3
    elif pct >= 21:
        return 2
    return 1


def _finish_session(session: StudentDiagnostic, question_log: list):
    """Завершить сессию диагностики."""
    session.status = 'completed'
    session.completed_at = datetime.utcnow()
    session.question_log_list = question_log

    # Пересчитываем итоговый профиль
    profile = session.profile
    topic_values = [t['pct'] for t in profile.values()]
    session.overall_pct = round(sum(topic_values) / max(len(topic_values), 1), 1)

    db.session.commit()

    # Генерируем AI-резюме (в фоне, без блокировки)
    try:
        generate_ai_summary(session.id)
    except Exception as e:
        logger.error(f"[diagnostics] AI summary generation failed: {e}")

    logger.info(f"[diagnostics] Session #{session.id} completed. "
                f"Overall: {session.overall_pct}%")


def _build_ai_summary_prompt(result: dict) -> str:
    """Собрать промпт для AI-резюме."""
    topics_lines = []
    for t in result.get('topics', []):
        topics_lines.append(f"  - {t['label']}: {t['pct']}% (уровень {t['level']})")

    return (
        f"Результаты диагностики ученика {result.get('grade', '?')} класса:\n"
        f"Общий уровень: {result['overall_pct']}%\n"
        f"Правильных ответов: {result['correct_answers']}/{result['total_questions']}\n\n"
        f"По темам:\n" + "\n".join(topics_lines) + "\n\n"
        "Напиши персонализированное резюме."
    )


def _build_fallback_summary(result: dict) -> str:
    """Создать fallback-резюме без AI."""
    strong_topics = [t for t in result.get('topics', []) if t['pct'] >= 60]
    weak_topics = [t for t in result.get('topics', []) if t['pct'] < 40]

    lines = [
        f"Твой общий уровень: {result['overall_pct']}%.",
    ]

    if strong_topics:
        strong_names = ', '.join(t['label'] for t in strong_topics)
        lines.append(f"Сильные стороны: {strong_names}.")
    if weak_topics:
        weak_names = ', '.join(t['label'] for t in weak_topics)
        lines.append(f"Зоны роста: {weak_names}.")

    lines.append("Продолжай регулярно заниматься — результаты будут расти!")
    return ' '.join(lines)
