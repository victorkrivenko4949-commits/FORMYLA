"""
AI-тьютор v2: паттерн think → distill.

Разделяет внутренние рассуждения модели (<thinking>) и чистый
вывод для ученика (<solution>).  Использует существующий
DeepSeekClient из ai/deepseek_client.py — не дублирует HTTP-логику.

Подключается к эндпоинту /api/check_adaptive_answer в app.py.
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SYSTEM PROMPT
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """Ты — математический тьютор на платформе FORMYLA для школьников 5–11 классов.

ГЛАВНОЕ ПРАВИЛО:
Тебе ДАНО правильный ответ из официальной базы данных.
НЕ оспаривай его. НЕ предлагай альтернативы. НЕ выражай сомнений.

╔══════════════════════════════════════════════════════╗
║  ОБЯЗАТЕЛЬНЫЙ ФОРМАТ ОТВЕТА — НАРУШЕНИЕ НЕДОПУСТИМО  ║
╚══════════════════════════════════════════════════════╝

Твой ответ ДОЛЖЕН содержать ОБА тега в точности как показано:

<thinking>
[Здесь свободно размышляй, проверяй выкладки, сомневайся.
 Этот блок ученик НЕ УВИДИТ.]
</thinking>

<solution>
[Здесь ЧИСТОЕ финальное объяснение для ученика.
 Уверенный тон. Пошагово. 3–8 шагов максимум.
 Формулы: \\( ... \\) inline, \\[ ... \\] display.
 Последняя строка ОБЯЗАТЕЛЬНО: **Ответ: {ОТВЕТ_ИЗ_БД}**]
</solution>

ЕСЛИ ТЫ НЕ НАПИШЕШЬ ОБА ТЕГА — ОТВЕТ БУДЕТ ОТКЛОНЁН СИСТЕМОЙ.

╔══════════════════════════════════════════════════════╗
║  ОСОБЫЙ СЛУЧАЙ: ПРОТИВОРЕЧИВАЯ ЗАДАЧА                ║
╚══════════════════════════════════════════════════════╝

Если в <thinking> ты убедился, что условие задачи противоречиво
(например, два условия несовместимы) — в <solution> напиши:

<solution>
Разбор этой задачи требует помощи учителя.

**Ответ: {ОТВЕТ_ИЗ_БД}**
</solution>

НЕ пытайся натянуть решение силой. Лучше честный fallback.

╔══════════════════════════════════════════════════════╗
║  СТРОГО ЗАПРЕЩЕНО в блоке <solution>:                ║
╚══════════════════════════════════════════════════════╝
- слова: «возможно», «вероятно», «скорее всего», «наверное»
- фразы: «проверим: может быть...», «а что если...», «не уверен»
- упоминание альтернативных ответов
- любая фраза «Ответ: X» где X ≠ ответ из БД
"""

# ---------------------------------------------------------------------------
# USER PROMPT TEMPLATE
# ---------------------------------------------------------------------------

USER_TEMPLATE = """УСЛОВИЕ ЗАДАЧИ:
{task_text}

ПРАВИЛЬНЫЙ ОТВЕТ (из официальной БД, не оспаривай):
{correct_answer}
{solution_block}
ОТВЕТ УЧЕНИКА: {user_answer}

Объясни ученику почему его ответ неверный и как правильно решить задачу.

ОБЯЗАТЕЛЬНО используй структуру (оба тега обязательны!):
<thinking>
[твои рассуждения — ученик не увидит]
</thinking>

<solution>
[чистое объяснение для ученика]
**Ответ: {correct_answer}**
</solution>

НАПОМИНАНИЕ: в <solution> запрещены слова «возможно», «вероятно», «скорее всего».
Если задача противоречива — напиши в <solution> только: «Разбор требует помощи учителя. **Ответ: {correct_answer}**»
"""


def build_prompt(task, user_answer: Optional[str]) -> str:
    """
    Собирает user-промпт для DeepSeek.

    task — объект AdaptiveTask с полями:
        task_text, correct_answer, solution,
        и опционально official_solution_latex (от Comet-импорта).
    user_answer — ответ ученика (может быть None).
    """
    # Приоритет: official_solution_latex (авторское) > solution (LLM-сгенерированное)
    sol = getattr(task, 'official_solution_latex', None) \
          or getattr(task, 'solution', None)

    if sol and sol.strip():
        solution_block = (
            "\nРЕШЕНИЕ ИЗ БД (опирайся на него, переформулируй для ученика):\n"
            + sol.strip()[:1500]  # ограничиваем длину
            + "\n"
        )
    else:
        solution_block = ""

    correct = getattr(task, 'correct_answer', None) or 'не указан'
    text = getattr(task, 'task_text', '') or ''

    return USER_TEMPLATE.format(
        task_text=text,
        correct_answer=correct,
        solution_block=solution_block,
        user_answer=user_answer or '(не дан)',
    )


# ---------------------------------------------------------------------------
# ПАРСИНГ И ВАЛИДАЦИЯ
# ---------------------------------------------------------------------------

# Запрещённые паттерны в финальном <solution>
# Правило: ловим ГАЛЛЮЦИНАЦИИ, а не математические методы.
#
# РАЗРЕШЕНО (не ловим):
#   "проверим случай 1", "проверим: если A — рыцарь"  → разбор случаев
#   "возможно только одно значение"                    → математический вывод
#   "рассмотрим случай А"                              → метод доказательства
#
# ЗАПРЕЩЕНО (ловим):
#   "проверим: может быть n=6?"                        → гадание
#   "возможно, правильный ответ 72"                    → неуверенность в ответе
#   "ответ: 18 или 72"                                 → несколько ответов
_FORBIDDEN = [
    # Гадание: "проверим: может/а может/что если/вдруг"
    # НО НЕ "проверим: если A — рыцарь" (разбор случаев)
    (r'проверим[,:]?\s*(?:может\b(?!\s+быть\s+только)|а\s+может|что\s+если|вдруг)',
     'hedging_guess'),

    # Неуверенность в ответе: "возможно, правильный/ответ/это <число>"
    # НО НЕ "возможно только", "возможны следующие варианты"
    (r'возможно[,\s]+(?:правильный|ответ\s+равен|это\s+\d)',
     'uncertainty_answer'),

    # Прямая неуверенность: "вероятно, ответ/правильный"
    (r'вероятно[,\s]+(?:правильный|ответ|это)',
     'uncertainty_veroyatno'),

    # "скорее всего, ответ/правильный"
    (r'скорее\s+всего[,\s]+(?:ответ|это|правильный)',
     'uncertainty_skoree'),

    # Прямое сомнение
    (r'\bне\s+уверен',
     'uncertainty_direct'),

    # Несколько альтернативных числовых ответов: "ответ: 18 или 72"
    (r'(?:ответ|answer)[:\s]+\d+\s+или\s+\d+',
     'multiple_answers'),
]


def extract_solution(raw: str) -> tuple:
    """
    Извлекает блок <solution>...</solution> из сырого ответа модели.

    Поддерживает:
    - Нормальный случай: <solution>...</solution>
    - Незакрытый тег: <solution>... (до конца строки)
    - Markdown-вариант: ```solution ... ```

    Возвращает (text: str, status: str).
    status = 'ok' | 'no_solution_tag'
    """
    # 1. Нормальный случай: открывающий и закрывающий теги
    m = re.search(
        r'<solution>(.*?)</solution>',
        raw,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if m:
        return m.group(1).strip(), 'ok'

    # 2. Незакрытый тег: берём всё после <solution>
    m2 = re.search(
        r'<solution>(.*)',
        raw,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if m2:
        text = m2.group(1).strip()
        # Убираем возможный </thinking> хвост если он попал
        text = re.sub(r'</thinking>.*', '', text, flags=re.DOTALL | re.IGNORECASE).strip()
        if len(text) > 50:  # минимальная длина осмысленного ответа
            return text, 'ok'

    return raw.strip(), 'no_solution_tag'


def validate_solution(sol: str, correct_answer: str) -> list:
    """
    Проверяет solution на запрещённые паттерны и совпадение ответа с БД.

    Возвращает список кодов ошибок (пустой = всё ок).
    """
    errs = []
    low = sol.lower()

    for pattern, code in _FORBIDDEN:
        if re.search(pattern, low):
            errs.append(code)

    # Проверяем что финальный «Ответ: X» совпадает с БД
    m = re.search(r'\*\*ответ[:\s*]+([^\n*]+)', low)
    if m and correct_answer:
        claimed = re.sub(r'[\s$\\*]', '', m.group(1))
        ref = re.sub(r'[\s$\\*]', '', str(correct_answer).lower())
        if ref and ref not in claimed and claimed not in ref:
            errs.append('answer_mismatch_with_db')

    return errs


# ---------------------------------------------------------------------------
# ГЛАВНАЯ ФУНКЦИЯ
# ---------------------------------------------------------------------------

def tutor_explain(
    task,
    user_answer: Optional[str],
    ai_client,
    max_tokens: int = 3000,
) -> dict:
    """
    Главная функция AI-тьютора v2.

    Args:
        task:        объект AdaptiveTask
        user_answer: ответ ученика (строка или None)
        ai_client:   экземпляр DeepSeekClient из ai/deepseek_client.py
        max_tokens:  максимум токенов (2000 для Free, 8000 для Premium)

    Returns:
        dict с ключами:
            solution      — текст для показа ученику
            status        — 'ok' | 'fallback'
            errors        — список кодов ошибок валидации
            raw_response  — полный ответ модели (для логов)
    """
    user_prompt = build_prompt(task, user_answer)

    try:
        raw = ai_client.generate(
            prompt=user_prompt,
            system_prompt=SYSTEM_PROMPT,
            temperature=0.2,   # низкая — меньше фантазий
            max_tokens=max_tokens,
        )
    except Exception as e:
        logger.error(f'[tutor_v2] DeepSeek call failed for task {task.id}: {e}')
        return _fallback(task, errors=['api_error'], raw='')

    sol, status = extract_solution(raw)
    errs = validate_solution(sol, getattr(task, 'correct_answer', ''))

    if status != 'ok' or errs:
        logger.warning(
            f'[tutor_v2] Validation failed for task {task.id}: '
            f'status={status}, errors={errs}'
        )
        return _fallback(task, errors=errs or ['no_solution_tag'], raw=raw)

    logger.info(f'[tutor_v2] OK for task {task.id}')
    return {
        'solution':     sol,
        'status':       'ok',
        'errors':       [],
        'raw_response': raw,
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
        'solution':     text,
        'status':       'fallback',
        'errors':       errors,
        'raw_response': raw,
    }
