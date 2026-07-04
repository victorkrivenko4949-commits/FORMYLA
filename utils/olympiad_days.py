"""
Хелпер для определения двухдневных олимпиад и разделения задач по дням.

Используется в каталоге просмотра олимпиад (olympiad_detail / olympiad_solutions).
НЕ затрагивает раздел "написать олимпиаду" с таймером.
"""

import re

# (slug, round) -> множество классов, для которых олимпиада двухдневная
TWO_DAY_RULES = {
    # ВсОШ Заключительный — 9, 10, 11 классы (2 дня по 4 задачи)
    ('vsosh', 'final'): {9, 10, 11},
    # ВсОШ Региональный — в реальности 2 дня, но в БД только 5 задач,
    # поэтому разделение сработает только если задач >= 6 и чётное число
    ('vsosh', 'regional'): {9, 10, 11},
    # Олимпиада Эйлера
    ('euler', 'regional'): {8, 9},
    ('euler', 'final'): {8, 9},
    ('euler', 'distance'): {8, 9},
    # Турнир городов — осенний/весенний туры (базовый и сложный)
    ('turgor', 'autumn_base'): {8, 9, 10, 11},
    ('turgor', 'autumn_hard'): {8, 9, 10, 11},
    ('turgor', 'spring_base'): {8, 9, 10, 11},
    ('turgor', 'spring_hard'): {8, 9, 10, 11},
    ('turgor', 'fall_basic'): {8, 9, 10, 11},
    ('turgor', 'fall_hard'): {8, 9, 10, 11},
    ('turgor', 'spring_basic'): {8, 9, 10, 11},
    # Ломоносов — 1-й и 2-й тур как отдельные round_key
    ('lomonosov', '1'): {7, 8, 9, 10, 11},
    ('lomonosov', '2'): {7, 8, 9, 10, 11},
    # Московская — заключительный этап (2 дня)
    ('mos', 'final'): {6, 7, 8, 9, 10, 11},
    # Высшая проба — второй этап / заключительный
    ('vysshaya_proba', '2'): {7, 8, 9, 10, 11},
    ('vysshaya_proba', 'final'): {7, 8, 9, 10, 11},
    # Формула Единства
    ('formula_unity', 'final'): {7, 8, 9, 10, 11},
    # Курчатов
    ('kurchatov', '2'): {7, 8, 9, 10, 11},
    # ПВГ
    ('pvg', '2'): {7, 8, 9, 10, 11},
    # СПбГУ
    ('spbgu', 'final'): {7, 8, 9, 10, 11},
    # Физтех
    ('phystech', 'final'): {7, 8, 9, 10, 11},
}


# Паттерны для определения номера дня из round_title
_DAY_PATTERNS = [
    (re.compile(r'1[-\s]й\s*тур'), 1),
    (re.compile(r'2[-\s]й\s*тур'), 2),
    (re.compile(r'3[-\s]й\s*тур'), 3),
    (re.compile(r'День\s*[№]?\s*1'), 1),
    (re.compile(r'День\s*[№]?\s*2'), 2),
    (re.compile(r'День\s*[№]?\s*3'), 3),
    (re.compile(r'тур\s*1'), 1),
    (re.compile(r'тур\s*2'), 2),
    (re.compile(r'Тур\s*[№]?\s*1'), 1),
    (re.compile(r'Тур\s*[№]?\s*2'), 2),
    (re.compile(r'Второй\s*этап'), 2),
]


def detect_day_from_round(round_title, round_key):
    """Определить номер дня (1 или 2) из round_title или round_key.

    Для олимпиад с раздельными round_key (lomonosov: '1'/'2', vysshaya_proba: '2')
    возвращает соответствующий номер дня. Для комбинированных (одна запись на оба дня)
    возвращает None.

    Args:
        round_title: название этапа (например '1-й тур заключительного этапа')
        round_key: ключ этапа (например '1', '2', 'final')

    Returns:
        1, 2, или None (если день не определён / комбинированная запись)
    """
    # Сначала проверяем round_key — числовые значения напрямую
    if round_key in ('1', '2', '3'):
        return int(round_key)

    # Затем проверяем round_title по паттернам
    if round_title:
        for pattern, day_num in _DAY_PATTERNS:
            if pattern.search(round_title):
                return day_num

        # Проверка на "(2 дня)" в round_title — это комбинированная запись
        if re.search(r'\(2\s*дня\)', round_title):
            return None

    return None


def is_two_day(olymp_slug, round_key, grade):
    """Определить, является ли данный вариант двухдневным.

    Args:
        olymp_slug: slug олимпиады (например 'vsosh')
        round_key: ключ этапа (например 'final', 'regional')
        grade: класс (int или str, будет приведён к int)

    Returns:
        True если олимпиада двухдневная для данного класса
    """
    try:
        grade_int = int(grade)
    except (ValueError, TypeError):
        return False
    classes = TWO_DAY_RULES.get((olymp_slug, round_key), set())
    return grade_int in classes


def split_problems_by_day(problems, olymp_slug, round_key, grade):
    """Разделить задачи по дням.

    Возвращает список блоков:
      [{'day': 1, 'problems': [...]}, {'day': 2, 'problems': [...]}]
    или
      [{'day': None, 'problems': [все]}]  — если один день.

    Логика:
      A) Если у задач есть поле 'day' — группируем по нему.
      B) Если олимпиада двухдневная И задач >= 4 — делим на 2 дня.
         Нечётное число: лишняя задача уходит в День 1 (ceil/floor).
      C) Иначе — один день, без разделителя.
    """
    if not problems:
        return []

    # Случай A — у задач уже есть поле "day"
    if any(p.get('day') for p in problems):
        days = {}
        for p in problems:
            d = p.get('day') or 1
            days.setdefault(d, []).append(p)
        return [{'day': d, 'problems': days[d]} for d in sorted(days)]

    # Случай B — плоский список + правило двух дней
    if is_two_day(olymp_slug, round_key, grade) and len(problems) >= 4:
        half = len(problems) // 2
        if len(problems) % 2 == 0:
            return [
                {'day': 1, 'problems': problems[:half]},
                {'day': 2, 'problems': problems[half:]},
            ]
        else:
            # Нечётное количество: ceil в день 1, floor в день 2
            return [
                {'day': 1, 'problems': problems[:half + 1]},
                {'day': 2, 'problems': problems[half + 1:]},
            ]

    # Случай C — один день
    return [{'day': None, 'problems': problems}]
