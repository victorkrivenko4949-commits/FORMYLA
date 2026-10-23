# -*- coding: utf-8 -*-
"""
Реестр тем адаптивного теста для 7–11 классов.

Каждой паре (grade, topic_key) сопоставляется ТОЧНАЯ строка темы
из поля `AdaptiveTask.topic` в БД. Это позволяет фильтровать задачи
жёстким равенством `AdaptiveTask.topic == db_topic` без эвристик
по ключевым словам.

Темы 5 и 6 классов умышленно не описаны здесь — они идут через
`models_grade.GradeTask` / `GRADE_DOMAINS` (не ломаем существующий
рабочий путь `start_grade`).
"""

# Структура одной записи:
#   {
#     'key':        str  — URL-safe идентификатор темы (используется в URL и в session),
#     'name':       str  — отображаемое имя в UI,
#     'emoji':      str  — иконка,
#     'db_topic':   str  — ТОЧНАЯ строка темы из БД (AdaptiveTask.topic == db_topic),
#     'aliases':    list[str] — (опц.) альтернативные строки на случай разночтений.
#   }

# ВНИМАНИЕ: db_topic ниже ТОЧНО совпадает со строками AdaptiveTask.topic в БД
# (8778+ задач с тонким разделением по темам). Эти строки также видны
# в TOPIC_MAP сидера services/adaptive_full_seed.py.
ADAPTIVE_TOPICS_BY_GRADE = {
    7: [
        {
            'key': 'expressions_polynomials',
            'name': 'Выражения, степени, многочлены',
            'emoji': '',
            'db_topic': 'Алгебра. Выражения, степени, многочлены',
        },
        {
            'key': 'linear_systems',
            'name': 'Линейные уравнения и системы',
            'emoji': '',
            'db_topic': 'Алгебра. Линейные уравнения и системы',
        },
        {
            'key': 'functions_graphs',
            'name': 'Функции и графики',
            'emoji': '',
            'db_topic': 'Алгебра. Функции и графики',
        },
        {
            'key': 'geometry_triangles',
            'name': 'Геометрия треугольников и углов',
            'emoji': '',
            'db_topic': 'Геометрия. Геометрия треугольников и углов',
        },
        {
            'key': 'divisibility_remainders',
            'name': 'Делимость и остатки',
            'emoji': '',
            'db_topic': 'Теория чисел. Делимость и остатки',
        },
        {
            'key': 'combinatorics_graphs',
            'name': 'Комбинаторика и графы',
            'emoji': '',
            'db_topic': 'Комбинаторика. Комбинаторика и графы',
        },
        {
            'key': 'logic_invariants',
            'name': 'Логика и инварианты',
            'emoji': '',
            'db_topic': 'Логика. Логика и инварианты',
        },
    ],
    8: [
        {
            'key': 'quadratic_vieta',
            'name': 'Квадратные уравнения и теорема Виета',
            'emoji': '',
            'db_topic': 'Алгебра. Квадратные уравнения и теорема Виета',
        },
        {
            'key': 'inequalities_transformations',
            'name': 'Неравенства и преобразования',
            'emoji': '≷',
            'db_topic': 'Алгебра. Неравенства и преобразования',
        },
        {
            'key': 'functions_graphs',
            'name': 'Функции и графики',
            'emoji': '',
            'db_topic': 'Алгебра. Функции и графики',
        },
        {
            'key': 'systems_word_problems',
            'name': 'Системы и текстовые задачи',
            'emoji': '',
            'db_topic': 'Алгебра. Системы и текстовые задачи',
        },
        {
            'key': 'geometry_similarity_circle',
            'name': 'Геометрия: подобие и окружность',
            'emoji': '',
            'db_topic': 'Геометрия. Геометрия: подобие и окружность',
        },
        {
            'key': 'number_theory_diophantine',
            'name': 'Теория чисел: остатки и диофантовы',
            'emoji': '',
            'db_topic': 'Теория чисел. Теория чисел: остатки и диофантовы',
        },
        {
            'key': 'combinatorics_logic_invariants',
            'name': 'Комбинаторика, логика, инварианты',
            'emoji': '',
            'db_topic': 'Комбинаторика. Комбинаторика, логика, инварианты',
        },
    ],
    9: [
        {
            'key': 'quadratic_parameters',
            'name': 'Квадратные уравнения, Виет, параметры',
            'emoji': '',
            'db_topic': 'Алгебра. Квадратные уравнения, Виет, параметры',
        },
        {
            'key': 'systems_modules_radicals',
            'name': 'Системы, модули, радикалы, неравенства',
            'emoji': '≷',
            'db_topic': 'Алгебра. Системы, модули, радикалы, неравенства',
        },
        {
            'key': 'functions_sequences_olymp',
            'name': 'Функции, последовательности и олимпиадные конструкции',
            'emoji': '',
            'db_topic': 'Алгебра. Функции, последовательности и олимпиадные конструкции',
        },
        {
            'key': 'geometry_triangle_circle',
            'name': 'Геометрия треугольника и окружности',
            'emoji': '',
            'db_topic': 'Геометрия. Геометрия треугольника и окружности',
        },
        {
            'key': 'number_theory',
            'name': 'Теория чисел',
            'emoji': '',
            'db_topic': 'Теория чисел. Теория чисел',
        },
        {
            'key': 'combinatorics_graphs',
            'name': 'Комбинаторика и графы',
            'emoji': '',
            'db_topic': 'Комбинаторика. Комбинаторика и графы',
        },
        {
            'key': 'logic_invariants_strategies',
            'name': 'Логика, инварианты, стратегии',
            'emoji': '',
            'db_topic': 'Логика. Логика, инварианты, стратегии',
        },
    ],
    10: [
        {
            'key': 'systems_parameters_inequalities',
            'name': 'Системы, параметры и неравенства',
            'emoji': '≷',
            'db_topic': 'Алгебра. Системы, параметры и неравенства',
        },
        {
            'key': 'trigonometry',
            'name': 'Тригонометрия',
            'emoji': '',
            'db_topic': 'Алгебра. Тригонометрия',
        },
        {
            'key': 'exp_log',
            'name': 'Показательные и логарифмические выражения',
            'emoji': '',
            'db_topic': 'Алгебра. Показательные и логарифмические выражения',
        },
        {
            'key': 'stereometry_vectors',
            'name': 'Стереометрия и векторы',
            'emoji': '',
            'db_topic': 'Геометрия. Стереометрия и векторы',
        },
        {
            'key': 'number_theory_advanced',
            'name': 'Теория чисел старшего уровня',
            'emoji': '',
            'db_topic': 'Теория чисел. Теория чисел старшего уровня',
        },
        {
            'key': 'combinatorics_graphs_probability',
            'name': 'Комбинаторика, графы, вероятностный подсчёт',
            'emoji': '',
            'db_topic': 'Комбинаторика. Комбинаторика, графы, вероятностный подсчёт',
        },
        {
            'key': 'logic_sets_functions',
            'name': 'Логика, множества, функции и отображения',
            'emoji': '',
            'db_topic': 'Логика. Логика, множества, функции и отображения',
        },
    ],
    11: [
        {
            'key': 'functions_graphs_parameters',
            'name': 'Функции, графики и параметры',
            'emoji': '',
            'db_topic': 'Алгебра. Функции, графики и параметры',
        },
        {
            'key': 'trigonometry_mixed',
            'name': 'Тригонометрия и смешанные уравнения',
            'emoji': '',
            'db_topic': 'Алгебра. Тригонометрия и смешанные уравнения',
        },
        {
            'key': 'inequalities_estimates',
            'name': 'Неравенства и оценки',
            'emoji': '≷',
            'db_topic': 'Алгебра. Неравенства и оценки',
        },
        {
            'key': 'polynomials_sequences_fe',
            'name': 'Многочлены, последовательности, функциональные уравнения',
            'emoji': '',
            'db_topic': 'Алгебра. Многочлены, последовательности, функциональные уравнения',
        },
        {
            'key': 'stereometry_coordinates_vectors',
            'name': 'Стереометрия, координаты и векторы',
            'emoji': '',
            'db_topic': 'Геометрия. Стереометрия, координаты и векторы',
        },
        {
            'key': 'number_theory_diophantine',
            'name': 'Теория чисел и диофантовы задачи',
            'emoji': '',
            'db_topic': 'Теория чисел. Теория чисел и диофантовы задачи',
        },
        {
            'key': 'combinatorics_graphs_logic',
            'name': 'Комбинаторика, графы, логика',
            'emoji': '',
            'db_topic': 'Комбинаторика. Комбинаторика, графы, логика',
        },
    ],
}


def get_topic_entry(grade, topic_key):
    """Найти запись о теме по (grade, topic_key).

    Возвращает dict с ключами 'key', 'name', 'emoji', 'db_topic' либо None,
    если такая комбинация не зарегистрирована (например, для 5–6 классов
    или для устаревших ключей вроде 'algebra'/'kl_movement').
    """
    try:
        grade_int = int(grade)
    except (TypeError, ValueError):
        return None
    for entry in ADAPTIVE_TOPICS_BY_GRADE.get(grade_int, []):
        if entry['key'] == topic_key:
            return entry
    return None


def get_db_topic(grade, topic_key):
    """Вернуть точную строку темы в БД для пары (grade, topic_key) или None."""
    entry = get_topic_entry(grade, topic_key)
    return entry['db_topic'] if entry else None


def is_registered(grade, topic_key):
    """Проверить, есть ли пара (grade, topic_key) в новом реестре."""
    return get_topic_entry(grade, topic_key) is not None
