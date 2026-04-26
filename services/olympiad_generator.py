#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Сервис генерации олимпиадных задач для раздела "Написать олимпиады".

Берёт few-shot примеры из OLYMPIADS_DB, формирует промпт,
вызывает DeepSeek Chat, валидирует результат, логирует.
"""

import json
import logging
import random
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# ─── Промпт ──────────────────────────────────────────────────────────────────

OLYMPIAD_WRITER_PROMPT = """Ты — составитель олимпиадных задач по математике с 20-летним опытом. \
Тебе нужно написать НОВУЮ задачу в стиле конкретной олимпиады.

═══════════════════════════════════════════════════════
ОЛИМПИАДА: {olympiad_name}
ЭТАП: {stage_name}
КЛАСС: {class_level}
═══════════════════════════════════════════════════════

ПРИМЕРЫ ЗАДАЧ ЭТОГО ЭТАПА (изучи стиль, сложность, темы):

{few_shot_examples}

═══════════════════════════════════════════════════════
ТВОЯ ЗАДАЧА:

Напиши ОДНУ НОВУЮ оригинальную задачу:
- Тот же уровень сложности что и в примерах выше
- Похожий стиль формулировки
- Тема может быть из тех что встречались в примерах
- Задача должна быть РАЗРЕШИМА учеником {class_level} класса
- Задача НЕ должна повторять условие ни одной из задач выше

═══════════════════════════════════════════════════════
СТРОГИЕ ПРАВИЛА ОФОРМЛЕНИЯ:

1. LATEX:
   ✅ Inline формулы: \\(...\\) — например \\(x^2 + 2x = 5\\)
   ✅ Block формулы: \\[...\\] — для больших выражений
   ✅ Дроби: \\frac{{a}}{{b}} — например \\frac{{1}}{{2}}
   ✅ Русские слова в формулах ОБЯЗАТЕЛЬНО в \\text{{}}: \\(\\text{{НОД}}(a, b) = 6\\)
   ❌ ЗАПРЕЩЕНО: $...$ или $$...$$ (конфликт со знаком доллара/рубля)
   ❌ ЗАПРЕЩЕНО: формулы без обёртки (просто x^2+5)
   ❌ ЗАПРЕЩЕНО: двойные backslash (\\\\frac)

2. ЯЗЫК:
   - Только русский в условии
   - Числа словами в начале предложения: "Десять учеников..."
   - Числа цифрами в формулах и подсчётах

3. КРИТИЧЕСКИ ВАЖНО — НЕ ВКЛЮЧАЙ В УСЛОВИЕ:
   ❌ Решение задачи
   ❌ Ответ
   ❌ Подсказки ("используйте теорему X", "обратите внимание что...")
   ❌ Слова "Решение:", "Доказательство:", "Ответ:"
   ❌ Готовые формулы для подстановки

   Условие должно ТОЛЬКО ставить вопрос. Решение и ответ возвращай в ОТДЕЛЬНЫХ полях JSON.

4. КРИТИЧЕСКИ ВАЖНО — ИНДЕКСЫ vs СТЕПЕНИ:

   ИНДЕКСЫ (нумерация элементов последовательности):
   ✅ В LaTeX: \\(f_1\\), \\(f_2\\), \\(x_1\\), \\(a_n\\), \\(b_{{100}}\\)
   ❌ НИКОГДА не пиши f1, f2, x1, x2 — это нечитаемо
   ❌ НИКОГДА не пиши f² когда имеешь в виду "вторая функция" — это означает "квадрат функции"

   СТЕПЕНИ (возведение в степень):
   ✅ В LaTeX: \\(x^2\\), \\(a^n\\), \\((x+1)^3\\)
   ❌ ^ — это ВОЗВЕДЕНИЕ В СТЕПЕНЬ, а не индекс

   ПРАВИЛЬНО:
   "Даны функции \\(f_1(x), f_2(x), \\ldots, f_{{100}}(x)\\). Их квадраты \\(f_1^2(x), f_2^2(x), \\ldots\\)"

   НЕПРАВИЛЬНО:
   "Даны функции f1(x), f²(x), ..." (перепутаны индексы и степени)

   КОГДА в задаче встречается "i-я функция", "j-й элемент", "n-е число", "k-й корень" —
   ВСЕГДА используй \\(f_i\\), \\(a_j\\), \\(x_n\\), \\(r_k\\) с подчёркиванием (индекс), а не ^ (степень).

   Числа в индексах больше 9 — ОБЯЗАТЕЛЬНО в фигурных скобках: \\(a_{{10}}\\), \\(x_{{100}}\\), НЕ \\(a_10\\).

5. ПОТЕРЯ СТЕПЕНИ — ЧАСТАЯ ОШИБКА:
   ❌ НЕПРАВИЛЬНО: (n+1)2, x2, 10100, n2 — цифра после переменной/скобки без ^
   ✅ ПРАВИЛЬНО: \\((n+1)^2\\), \\(x^2\\), \\(10^{{100}}\\), \\(n^2\\)

   Если ты пишешь степень — ОБЯЗАТЕЛЬНО используй ^ внутри \\(...\\).
   НИКОГДА не ставь цифру степени просто после переменной или скобки.

   Большие числа со степенями (10^100, 2^31, 10^9):
   ✅ ВСЕГДА в LaTeX: \\(10^{{100}}\\), \\(2^{{31}}\\), \\(10^9\\)
   ❌ НИКОГДА не пиши 10100, 231, 109 — это читается как обычные числа, а не степени


6. TY SOZDAYOSH NOVUYU ORIGINALNUYU ZADACHU - ne kopiyu!

Primery vyshe - eto OBRAZCY STILYA, TEMY I UROVNYA SLOZHNOSTI.
Oni NE DLYA KOPIROVANIYA.

TVOYA ZADACHA:
1. Izuchi primery - pojmi TEMU
2. Pojmi SLOZHNOST (kakoj klass, kakoj etap)
3. Pojmi STIL FORMULIROVKI (kratkij, strogij)
4. PRIDUMAJ NOVUYU zadachu toj zhe temy i slozhnosti

ZAPRESHCHENO:
- Kopirovat formulirovku primera slovo v slovo
- Menyat tolko chisla v primere (eto plagiat)
- Ispolzovat te zhe obekty chto v primere

RAZRESHENO:
- Zaimstvovat IDEYU metoda (naprimer razbieniena pary)
- Ispolzovat tu zhe temu (naprimer delimost na 7)
- Sokhraniyat uroven slozhnosti

KRITERII KACHESTVA:
1. KORREKTNOST: u zadachi SUSHCHESTVUET odnoznachnyj otvet
2. RESHAEMOST: reshenie umeshchaetsya v 5-15 shagov
3. OTVET: konkretnoe chislo, formula, ili yavnoe opisanie
   NE 'zavisit ot...', NE 'mozhet byt lyubym'
4. RESHENIE: polnoe poshagovoe obyasnenie, minimum 200 simvolov

PERED VYDACHEJ ZADACHI:
- Myslennno reshi ee sam
- Prover chto otvet sovpadaet s tem chto napishesh

═══════════════════════════════════════════════════════
ФОРМАТ ОТВЕТА — строго JSON, без markdown блоков:

{{
  "task_text": "условие задачи на русском с правильным LaTeX",
  "correct_answer": "короткий ответ (число, выражение, или 'требуется доказательство')",
  "solution": "полное решение с шагами и LaTeX",
  "topic": "тема задачи (например 'Делимость', 'Геометрия', 'Комбинаторика')",
  "difficulty": число от 1 до 5,
  "key_idea": "ключевая идея/приём в одно предложение"
}}

Возвращай ТОЛЬКО JSON, без пояснений до или после.
"""

# ─── Эталонный пример правильного оформления индексов ────────────────────────
# Всегда добавляется первым в few-shot, чтобы LLM видел правильную нотацию

ALWAYS_INCLUDE_INDEX_EXAMPLE = (
    "--- Образец правильного оформления индексов ---\n"
    "Даны числа \\(a_1, a_2, \\ldots, a_n\\) такие, что "
    "\\(a_1^2 + a_2^2 + \\ldots + a_n^2 = 1\\). "
    "Докажите, что \\(|a_1 + a_2 + \\ldots + a_n| \\leq \\sqrt{n}\\).\n\n"
    "Обрати внимание: \\(a_i\\) — i-й элемент (индекс через _), "
    "\\(a_i^2\\) — его квадрат (степень через ^)."
)

# ─── Дефолтные примеры по классу (если в БД нет задач) ──────────────────────

DEFAULT_EXAMPLES_BY_CLASS = {
    5: """--- Пример 1 ---
Петя написал на доске числа от 1 до 10. Вася стёр несколько чисел. Оказалось, что сумма оставшихся чисел равна 42. Какое наименьшее количество чисел мог стереть Вася?
Ответ: 3

--- Пример 2 ---
В ряд стоят 7 мальчиков и 5 девочек. Сколькими способами можно выбрать одного мальчика и одну девочку, стоящих рядом?
Ответ: 4""",

    6: """--- Пример 1 ---
Найдите наибольшее трёхзначное число, которое при делении на 7 даёт остаток 5, а при делении на 11 даёт остаток 3.
Ответ: 993

--- Пример 2 ---
На клетчатой бумаге нарисован прямоугольник \\(5 \\times 8\\). Сколько клеток пересекает его диагональ?
Ответ: 11""",

    7: """--- Пример 1 ---
Докажите, что для любого натурального \\(n\\) число \\(n^3 - n\\) делится на 6.
Ответ: требуется доказательство

--- Пример 2 ---
В треугольнике \\(ABC\\) угол \\(A = 60°\\). Биссектриса угла \\(A\\) делит противоположную сторону в отношении \\(2:3\\). Найдите отношение \\(AB:AC\\).
Ответ: 2:3""",

    8: """--- Пример 1 ---
Найдите все натуральные числа \\(n\\), при которых \\(n^2 + 3n + 5\\) является точным квадратом.
Ответ: нет таких натуральных n

--- Пример 2 ---
В выпуклом четырёхугольнике \\(ABCD\\) диагонали пересекаются в точке \\(O\\). Известно, что \\(S_{AOB} = S_{COD} = 4\\). Найдите наименьшее возможное значение площади четырёхугольника.
Ответ: 16""",

    9: """--- Пример 1 ---
Найдите все простые числа \\(p\\), при которых \\(p^2 + 2\\) тоже простое.
Ответ: p = 3

--- Пример 2 ---
Докажите, что в любой последовательности из 10 различных натуральных чисел найдутся два числа, разность которых делится на 9.
Ответ: требуется доказательство""",

    10: """--- Пример 1 ---
Найдите все функции \\(f: \\mathbb{R} \\to \\mathbb{R}\\) такие, что \\(f(x+y) = f(x) + f(y)\\) для всех \\(x, y \\in \\mathbb{R}\\) и \\(f(1) = 2\\).
Ответ: f(x) = 2x

--- Пример 2 ---
В треугольнике \\(ABC\\) вписана окружность радиуса \\(r\\). Докажите, что площадь треугольника равна \\(r \\cdot s\\), где \\(s\\) — полупериметр.
Ответ: требуется доказательство""",

    11: """--- Пример 1 ---
Найдите наибольшее значение выражения \\(\\sin x + \\sin y + \\sin z\\), если \\(x + y + z = \\pi\\) и \\(x, y, z \\geq 0\\).
Ответ: \\(\\frac{3\\sqrt{3}}{2}\\)

--- Пример 2 ---
Докажите, что для любых вещественных \\(a, b, c > 0\\) выполняется неравенство \\(\\frac{a}{b+c} + \\frac{b}{a+c} + \\frac{c}{a+b} \\geq \\frac{3}{2}\\).
Ответ: требуется доказательство""",
}


def _default_examples_by_class(class_level: int) -> str:
    """Возвращает дефолтные примеры для класса если в БД нет задач."""
    # Ближайший класс из словаря
    available = sorted(DEFAULT_EXAMPLES_BY_CLASS.keys())
    closest = min(available, key=lambda x: abs(x - class_level))
    return DEFAULT_EXAMPLES_BY_CLASS.get(closest, DEFAULT_EXAMPLES_BY_CLASS[9])


def get_few_shot_examples(
    olympiad_slug: str,
    round_key: str,
    class_level: int,
    olympiads_db: list,
    limit: int = 2
) -> str:
    """
    Берёт N случайных задач этого этапа/класса из OLYMPIADS_DB.
    Если их меньше limit — берёт все что есть.
    Если 0 — возвращает дефолтные примеры по классу.
    """
    # Собираем задачи из нужной олимпиады/этапа/класса
    matching_problems = []
    for combo in olympiads_db:
        if (combo.get('olympiad') == olympiad_slug
                and combo.get('round') == round_key
                and str(combo.get('grade', '')) == str(class_level)):
            year = combo.get('year', '?')
            for prob in combo.get('problems', []):
                text = prob.get('text', '').strip()
                answer = prob.get('answer', '').strip()
                num = prob.get('num', '?')
                if text and len(text) > 30:
                    matching_problems.append({
                        'year': year,
                        'num': num,
                        'text': text,
                        'answer': answer,
                    })

    # Если нет задач этого этапа — пробуем любой этап этой олимпиады/класса
    if not matching_problems:
        for combo in olympiads_db:
            if (combo.get('olympiad') == olympiad_slug
                    and str(combo.get('grade', '')) == str(class_level)):
                year = combo.get('year', '?')
                for prob in combo.get('problems', []):
                    text = prob.get('text', '').strip()
                    answer = prob.get('answer', '').strip()
                    num = prob.get('num', '?')
                    if text and len(text) > 30:
                        matching_problems.append({
                            'year': year,
                            'num': num,
                            'text': text,
                            'answer': answer,
                        })

    if not matching_problems:
        logger.info(
            f"Нет задач для {olympiad_slug}/{round_key}/класс {class_level} — "
            f"используем дефолтные примеры"
        )
        # Эталонный пример индексов всегда первым, затем дефолтные
        return ALWAYS_INCLUDE_INDEX_EXAMPLE + "\n\n" + _default_examples_by_class(class_level)

    # Случайная выборка
    sample = random.sample(matching_problems, min(limit, len(matching_problems)))

    formatted = []
    for i, prob in enumerate(sample, 1):
        answer_str = f"\nОтвет: {prob['answer']}" if prob['answer'] else ""
        formatted.append(
            f"--- Пример {i} ({prob['year']} год, задача №{prob['num']}) ---\n"
            f"{prob['text']}"
            f"{answer_str}\n"
        )

    # Эталонный пример индексов ВСЕГДА первым — LLM видит правильную нотацию
    return ALWAYS_INCLUDE_INDEX_EXAMPLE + "\n\n" + "\n".join(formatted)


def generate_olympiad_task(
    olympiad_slug: str,
    olympiad_name: str,
    round_key: str,
    round_name: str,
    class_level: int,
    olympiads_db: list,
    max_retries: int = 3,
    user_id: Optional[int] = None,
) -> dict:
    """
    Генерирует олимпиадную задачу с автоматической перегенерацией
    при невалидном результате.

    Returns:
        {
            'success': bool,
            'task': dict | None,
            'attempts': int,
            'last_errors': list,
        }
    """
    # Импортируем здесь чтобы избежать циклических импортов
    from services.task_validator import validate_generated_task

    # Получаем few-shot примеры (limit=2 для снижения плагиата)
    examples = get_few_shot_examples(
        olympiad_slug, round_key, class_level, olympiads_db
    )
    # Извлекаем тексты задач для проверки плагиата
    few_shot_raw = []
    for combo in olympiads_db:
        if (combo.get('olympiad') == olympiad_slug
                and str(combo.get('grade', '')) == str(class_level)):
            for prob in combo.get('problems', []):
                t = prob.get('text', '').strip()
                if t and len(t) > 30:
                    few_shot_raw.append(t)
    import random as _random
    few_shot_texts = _random.sample(few_shot_raw, min(20, len(few_shot_raw)))

    prompt = OLYMPIAD_WRITER_PROMPT.format(
        olympiad_name=olympiad_name,
        stage_name=round_name,
        class_level=class_level,
        few_shot_examples=examples,
    )

    # Инициализируем DeepSeek клиент
    try:
        from ai.deepseek_client import DeepSeekClient, DeepSeekAPIError
        client = DeepSeekClient()
    except Exception as e:
        logger.error(f"Не удалось инициализировать DeepSeek клиент: {e}")
        return {
            'success': False,
            'task': None,
            'attempts': 0,
            'last_errors': [f'DeepSeek недоступен: {str(e)}'],
        }

    attempts_log = []

    for attempt in range(1, max_retries + 1):
        # Растущая температура для разнообразия при перегенерации
        temperature = 1.0 + (attempt - 1) * 0.10

        logger.info(
            f"Генерация задачи: {olympiad_slug}/{round_key}/класс {class_level}, "
            f"попытка {attempt}/{max_retries}, температура={temperature:.2f}"
        )

        try:
            raw_response = client.generate(
                prompt=prompt,
                system_prompt=(
                    "Ты — опытный составитель олимпиадных задач по математике. "
                    "Отвечай ТОЛЬКО валидным JSON без markdown-блоков."
                ),
                temperature=temperature,
                max_tokens=2500,
            )
        except Exception as e:
            error_msg = f"Ошибка API на попытке {attempt}: {str(e)}"
            logger.warning(error_msg)
            attempts_log.append({
                'attempt': attempt,
                'temperature': temperature,
                'valid': False,
                'errors': [error_msg],
            })
            continue

        result = validate_generated_task(raw_response, few_shot_texts=few_shot_texts)

        attempts_log.append({
            'attempt': attempt,
            'temperature': temperature,
            'valid': result['valid'],
            'errors': result['errors'],
        })

        if result['valid']:
            task = result['task']

            # Логируем в БД
            _log_generation(
                olympiad_slug=olympiad_slug,
                round_key=round_key,
                class_level=class_level,
                attempts_log=attempts_log,
                success=True,
                user_id=user_id,
            )

            logger.info(
                f"✅ Задача сгенерирована за {attempt} попытку(и): "
                f"{olympiad_slug}/{round_key}/класс {class_level}"
            )

            return {
                'success': True,
                'task': task,
                'attempts': attempt,
                'last_errors': [],
            }

        logger.warning(
            f"Попытка {attempt} не прошла валидацию: {result['errors']}"
        )

    # Все попытки провалились
    _log_generation(
        olympiad_slug=olympiad_slug,
        round_key=round_key,
        class_level=class_level,
        attempts_log=attempts_log,
        success=False,
        user_id=user_id,
    )

    last_errors = attempts_log[-1]['errors'] if attempts_log else ['Неизвестная ошибка']
    logger.error(
        f"❌ Не удалось сгенерировать задачу за {max_retries} попытки: "
        f"{olympiad_slug}/{round_key}/класс {class_level}. Ошибки: {last_errors}"
    )

    return {
        'success': False,
        'task': None,
        'attempts': max_retries,
        'last_errors': last_errors,
    }


def _log_generation(
    olympiad_slug: str,
    round_key: str,
    class_level: int,
    attempts_log: list,
    success: bool,
    user_id: Optional[int] = None,
) -> None:
    """Логирует результат генерации в таблицу olympiad_generation_log."""
    try:
        from models import db, OlympiadGenerationLog
        log_entry = OlympiadGenerationLog(
            olympiad_slug=olympiad_slug,
            round_key=round_key,
            class_level=class_level,
            attempts=len(attempts_log),
            success=1 if success else 0,
            errors_json=json.dumps(attempts_log, ensure_ascii=False),
            user_id=user_id,
            created_at=datetime.utcnow(),
        )
        db.session.add(log_entry)
        db.session.commit()
    except Exception as e:
        # Логирование не должно ломать основной поток
        logger.warning(f"Не удалось записать лог генерации: {e}")


def get_available_olympiads_for_writer(olympiads_db: list) -> dict:
    """
    Возвращает структуру доступных олимпиад/этапов/классов для UI.

    Returns:
        {
            'vsosh': {
                'title': 'ВсОШ',
                'rounds': {
                    'final': {
                        'title': 'Заключительный этап',
                        'grades': [5, 6, 7, 8, 9, 10, 11]
                    },
                    ...
                }
            },
            ...
        }
    """
    result = {}
    for combo in olympiads_db:
        slug = combo.get('olympiad', '')
        title = combo.get('olympiad_title', slug)
        round_key = combo.get('round', '')
        round_title = combo.get('round_title', round_key)
        grade = combo.get('grade')

        if not slug or not round_key or grade is None:
            continue

        if slug not in result:
            result[slug] = {'title': title, 'rounds': {}}

        if round_key not in result[slug]['rounds']:
            result[slug]['rounds'][round_key] = {
                'title': round_title,
                'grades': []
            }

        grade_int = int(grade) if str(grade).isdigit() else grade
        if grade_int not in result[slug]['rounds'][round_key]['grades']:
            result[slug]['rounds'][round_key]['grades'].append(grade_int)

    # Сортируем классы
    for slug in result:
        for rnd in result[slug]['rounds']:
            result[slug]['rounds'][rnd]['grades'].sort()

    return result
