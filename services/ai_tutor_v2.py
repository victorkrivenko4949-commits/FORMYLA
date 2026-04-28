# -*- coding: utf-8 -*-
"""
AI-тьютор v2: тьютор САМОСТОЯТЕЛЬНО решает задачу.

Ключевое изменение: тьютор решает задачу с нуля и доверяет
своему решению, а не БД-эталону. Если решение расходится
с БД — помечает задачу как needs_review.

Подключается к эндпоинту /api/check_adaptive_answer в app.py.
"""

import json
import re
import logging
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SYSTEM PROMPT — тьютор решает задачу САМ
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """Ты — AI-тьютор по математике на платформе FORMYLA. Помогаешь школьникам разбирать задачи адаптивного теста.

═══ ГЛАВНОЕ ПРАВИЛО ═══

ТЫ САМОСТОЯТЕЛЬНО РЕШАЕШЬ ЗАДАЧУ С НУЛЯ.
Ответ из БД — это ПОДСКАЗКА, а не истина.

Если БД-ответ противоречит твоему решению:
- ДОВЕРЯЙ СВОЕМУ РЕШЕНИЮ (если оно математически строгое и проверено).
- Покажи ученику ПРАВИЛЬНЫЙ разбор и СВОЙ ответ.
- Не упоминай ученику что в БД был другой ответ — это его запутает.
- Помечай задачу для пересмотра через служебное поле needs_review в JSON-ответе.

ТЫ ИМЕЕШЬ ПРАВО ПРОТИВОРЕЧИТЬ БД. Это твоя ОБЯЗАННОСТЬ как учителя. Ученик заслуживает правильный ответ.

═══ АЛГОРИТМ РАБОТЫ ═══

1. Прочитай условие задачи внимательно.
2. РЕШИ задачу сам, шаг за шагом, не подглядывая в БД-ответ.
3. Сравни свой ответ с БД-ответом (поле expected_answer).
4. Сравни ответ ученика (поле user_answer) со СВОИМ ответом (не с БД).
5. Сформируй разбор, как будто БД-ответа не существует.

═══ ФОРМАТ ОТВЕТА — СТРОГО JSON ═══

{
  "my_solution": "<твоё пошаговое решение>",
  "my_answer": "<твой итоговый ответ>",
  "user_correct": true или false,
  "explanation_for_student": "<доброжелательный разбор для ученика: где он ошибся, как правильно. НЕ упоминай БД и расхождения с ней>",
  "needs_review": true или false,
  "review_reason": "<если needs_review=true: краткое техническое объяснение для админа, почему БД-ответ неверный. Иначе пустая строка>",
  "confidence": 0.95
}

═══ КОГДА СОМНЕВАЕШЬСЯ ═══

Если задача неоднозначна или у тебя confidence < 0.7:
- needs_review = true
- review_reason = "неоднозначная формулировка / несколько трактовок"
- В explanation_for_student покажи СВОЮ трактовку и решение, без упоминания альтернатив.

═══ СТИЛЬ ОБЪЯСНЕНИЯ ═══

- Доброжелательно, как живой учитель.
- LaTeX в формате: \\( формула \\) для inline, \\[ формула \\] для display.
- 3-7 шагов в решении.
- Без морализаторства и "ты молодец что попробовал".

Никакого текста вне JSON. Никаких ```json блоков. Только чистый JSON."""

# ---------------------------------------------------------------------------
# USER PROMPT TEMPLATE
# ---------------------------------------------------------------------------

USER_TEMPLATE = """Задача:
{task_text}

Ответ из БД (используй только для пометки needs_review):
{expected_answer}

Ответ ученика: {user_answer}

Реши задачу сам и верни строго JSON."""


def build_prompt(task, user_answer: Optional[str]) -> str:
    """
    Собирает user-промпт для LLM.

    task — объект AdaptiveTask с полями:
        task_text, correct_answer, solution,
        и опционально official_solution_latex.
    user_answer — ответ ученика (может быть None).
    """
    correct = getattr(task, 'correct_answer', None) or 'не указан'
    text = getattr(task, 'task_text', '') or ''

    return USER_TEMPLATE.format(
        task_text=text,
        expected_answer=correct,
        user_answer=user_answer or '(не дан)',
    )


# ---------------------------------------------------------------------------
# ПАРСИНГ JSON-ОТВЕТА
# ---------------------------------------------------------------------------

def _safe_parse_json(raw: str) -> Optional[dict]:
    """
    Парсит JSON-ответ от LLM, обрабатывая типичные проблемы:
    - markdown-обёртки ```json ... ```
    - LaTeX-слеши внутри строк
    """
    # 1. Убираем markdown-обёртки
    s = re.sub(r'```json\s*', '', raw.strip())
    s = re.sub(r'```\s*', '', s).strip()

    # 2. Пробуем распарсить как есть
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass

    # 3. Экранируем одиночные \ которые не являются валидными JSON-escape
    def fix_backslashes(m):
        content = m.group(0)
        fixed = re.sub(
            r'\\(?!["\\/bfnrtu])',
            r'\\\\',
            content
        )
        return fixed

    s_fixed = re.sub(r'"(?:[^"\\]|\\.)*"', fix_backslashes, s, flags=re.DOTALL)

    try:
        return json.loads(s_fixed)
    except json.JSONDecodeError:
        pass

    # 4. Последний шанс: ищем JSON-объект в тексте
    m = re.search(r'\{.*\}', s, flags=re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
        # Пробуем с фиксом слешей
        fixed_obj = re.sub(r'"(?:[^"\\]|\\.)*"', fix_backslashes, m.group(0), flags=re.DOTALL)
        try:
            return json.loads(fixed_obj)
        except json.JSONDecodeError:
            pass

    return None


def _validate_tutor_response(data: dict) -> list:
    """
    Проверяет что JSON-ответ содержит все обязательные поля.
    Возвращает список ошибок (пустой = всё ок).
    """
    required_fields = [
        'my_solution', 'my_answer', 'user_correct',
        'explanation_for_student', 'needs_review',
    ]
    errors = []
    for field in required_fields:
        if field not in data:
            errors.append(f'missing_field_{field}')

    return errors


# ---------------------------------------------------------------------------
# ПОМЕТКА ЗАДАЧИ ДЛЯ ПЕРЕСМОТРА
# ---------------------------------------------------------------------------

def mark_for_review(task_id: int, llm_answer: str, llm_solution: str, reason: str):
    """
    Помечает задачу в БД как needs_review.
    Вызывается когда LLM нашёл расхождение с БД-ответом.
    """
    try:
        from models import db
        from sqlalchemy import text

        db.session.execute(
            text("""
                UPDATE adaptive_tasks
                SET needs_review = 1,
                    llm_suggested_answer = :llm_answer,
                    llm_suggested_solution = :llm_solution,
                    review_reason = :reason,
                    review_flagged_at = :now
                WHERE id = :task_id
            """),
            {
                'task_id': task_id,
                'llm_answer': str(llm_answer)[:2000],
                'llm_solution': str(llm_solution)[:5000],
                'reason': str(reason)[:1000],
                'now': datetime.utcnow().isoformat(),
            }
        )
        db.session.commit()
        logger.info(f'[tutor_v2] Task {task_id} marked needs_review: {reason[:100]}')
    except Exception as e:
        logger.error(f'[tutor_v2] Failed to mark task {task_id} for review: {e}')


# ---------------------------------------------------------------------------
# ГЛАВНАЯ ФУНКЦИЯ
# ---------------------------------------------------------------------------

def tutor_explain(
    task,
    user_answer: Optional[str],
    ai_client,
    max_tokens: int = 4000,
) -> dict:
    """
    Главная функция AI-тьютора v2.

    Тьютор САМОСТОЯТЕЛЬНО решает задачу и сравнивает с БД.
    Если расхождение — помечает задачу needs_review.

    Args:
        task:        объект AdaptiveTask
        user_answer: ответ ученика (строка или None)
        ai_client:   экземпляр DeepSeekClient из ai/deepseek_client.py
        max_tokens:  максимум токенов

    Returns:
        dict с ключами:
            solution          — текст разбора для показа ученику
            answer            — ответ от LLM (НЕ из БД!)
            user_correct      — совпадает ли ответ ученика с LLM
            status            — 'ok' | 'fallback'
            errors            — список кодов ошибок валидации
            raw_response      — полный ответ модели (для логов)
            needs_review      — True если LLM нашёл расхождение с БД
    """
    user_prompt = build_prompt(task, user_answer)

    try:
        raw = ai_client.generate(
            prompt=user_prompt,
            system_prompt=SYSTEM_PROMPT,
            temperature=0.3,
            max_tokens=max_tokens,
        )
    except Exception as e:
        logger.error(f'[tutor_v2] DeepSeek call failed for task {task.id}: {e}')
        return _fallback(task, errors=['api_error'], raw='')

    # Парсим JSON-ответ
    data = _safe_parse_json(raw)
    if not data:
        logger.warning(f'[tutor_v2] JSON parse failed for task {task.id}')
        return _fallback(task, errors=['json_parse_error'], raw=raw)

    # Валидируем поля
    errs = _validate_tutor_response(data)
    if errs:
        logger.warning(
            f'[tutor_v2] Validation failed for task {task.id}: errors={errs}'
        )
        return _fallback(task, errors=errs, raw=raw)

    # Извлекаем данные
    my_solution = str(data.get('my_solution', ''))
    my_answer = str(data.get('my_answer', ''))
    user_correct = bool(data.get('user_correct', False))
    explanation = str(data.get('explanation_for_student', ''))
    needs_review = bool(data.get('needs_review', False))
    review_reason = str(data.get('review_reason', ''))
    confidence = float(data.get('confidence', 0.5))

    # Если LLM нашёл расхождение — помечаем задачу в БД
    if needs_review:
        mark_for_review(
            task_id=task.id,
            llm_answer=my_answer,
            llm_solution=my_solution,
            reason=review_reason,
        )

    logger.info(
        f'[tutor_v2] OK for task {task.id}: '
        f'my_answer={my_answer!r}, needs_review={needs_review}, '
        f'confidence={confidence}'
    )

    return {
        'solution':       explanation,
        'answer':         my_answer,
        'my_solution':    my_solution,
        'user_correct':   user_correct,
        'status':         'ok',
        'errors':         [],
        'raw_response':   raw,
        'needs_review':   needs_review,
        'review_reason':  review_reason,
        'confidence':     confidence,
    }


def _fallback(task, errors: list, raw: str) -> dict:
    """Формирует fallback-ответ когда валидация упала."""
    correct = getattr(task, 'correct_answer', None) or 'см. решение'
    text = (
        f"Разбор этой задачи временно недоступен.\n\n"
        f"**Правильный ответ: {correct}**\n\n"
        f"Попробуй решить её позже или обратись к учителю."
    )
    return {
        'solution':      text,
        'answer':        correct,
        'my_solution':   '',
        'user_correct':  False,
        'status':        'fallback',
        'errors':        errors,
        'raw_response':  raw,
        'needs_review':  False,
        'review_reason': '',
        'confidence':    0.0,
    }
