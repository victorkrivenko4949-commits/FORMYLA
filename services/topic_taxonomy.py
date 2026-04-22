#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Таксономия тем и подтем для адаптивных тестов FORMYLA.
Используется для обеспечения уникальности подтем в пробниках.
"""

# Словарь подтем по темам (английские ключи для БД)
SUBTOPICS = {
    # 5 класс - темы (точные названия из БД)
    'Логика (рыцари и лжецы, логические таблицы)': [
        'knights_liars_basic',
        'knights_liars_groups',
        'logic_tables',
        'logic_deduction',
        'logic_paradoxes',
    ],
    'Принцип Дирихле': [
        'pigeonhole_basic',
        'pigeonhole_numbers',
        'pigeonhole_geometry',
        'pigeonhole_coloring',
    ],
    'Числовые ребусы и крипторифмы': [
        'cryptarithmetic_addition',
        'cryptarithmetic_multiplication',
        'digit_puzzles',
        'number_patterns',
    ],
    'Делимость, остатки и последняя цифра': [
        'divisibility_rules',
        'remainders_basic',
        'last_digit',
        'divisibility_proofs',
        'modular_arithmetic',
    ],
    'Инварианты, четность и чередование': [
        'parity_basic',
        'invariants_coloring',
        'invariants_operations',
        'alternating_sequences',
    ],
    'Графы (знакомства, турниры, маршруты)': [
        'graph_handshakes',
        'graph_tournaments',
        'graph_paths',
        'graph_coloring',
        'graph_trees',
    ],
    # Точное название из БД для 5 класса
    'Комбинаторика (правилы суммы/произведения, деревья)': [
        'counting_sum_rule',
        'counting_product_rule',
        'counting_trees',
        'counting_arrangements',
        'counting_selections',
    ],
    # Альтернативное написание
    'Комбинаторика (правила суммы/произведения, деревья)': [
        'counting_sum_rule',
        'counting_product_rule',
        'counting_trees',
        'counting_arrangements',
        'counting_selections',
    ],
    'Геометрия на клетчатой бумаге и разрезания': [
        'grid_areas',
        'grid_perimeters',
        'cutting_shapes',
        'tiling_domino',
        'tiling_polyomino',
    ],
    'Взвешивания, переливания и алгоритмы': [
        'weighing_balance',
        'weighing_fake_coin',
        'pouring_water',
        'algorithms_sorting',
    ],
    'Текстовые задачи (движение, совместная работа, обратный ход)': [
        'motion_basic',
        'motion_meeting',
        'work_together',
        'work_pipes',
        'reverse_operations',
    ],
    # Точное название из БД
    'Текстовые задачи (совместная работа, обратный ход)': [
        'motion_basic',
        'motion_meeting',
        'work_together',
        'work_pipes',
        'reverse_operations',
    ],
    
    # 6 класс - темы
    'Признаки делимости и остатки': [
        'divisibility_by_2_5',
        'divisibility_by_3_9',
        'divisibility_by_4_8',
        'divisibility_by_11',
        'remainders_system',
        'last_digits_powers',
    ],
    'НОД, НОК и основная теорема арифметики': [
        'gcd_basic',
        'lcm_basic',
        'prime_factorization',
        'gcd_lcm_problems',
        'coprime_numbers',
    ],
    'Дроби, доли и пропорции': [
        'fractions_basic',
        'fractions_comparison',
        'proportions_direct',
        'proportions_inverse',
        'percentages',
    ],
    'Графы (знакомства, турниры, маршруты)': [
        'graph_handshakes',
        'graph_tournaments',
        'graph_paths',
        'graph_euler',
        'graph_bipartite',
    ],
    'Принцип Дирихле': [
        'pigeonhole_basic',
        'pigeonhole_numbers',
        'pigeonhole_geometry',
        'pigeonhole_advanced',
    ],
    'Логика (рыцари и лжецы, логические таблицы)': [
        'knights_liars_basic',
        'knights_liars_groups',
        'logic_tables',
        'logic_deduction',
    ],
    'Разрезания и замощения': [
        'cutting_rectangles',
        'cutting_chessboard',
        'tiling_domino',
        'tiling_L_shape',
        'tiling_coloring_proof',
    ],
    'Инварианты (четность, раскраски)': [
        'parity_operations',
        'coloring_2colors',
        'coloring_chessboard',
        'invariants_monovariant',
    ],
    'Геометрия (периметры и площади)': [
        'perimeter_rectangles',
        'area_rectangles',
        'area_triangles',
        'area_composite',
        'grid_geometry',
    ],
    'Комбинаторика (правило суммы и произведения)': [
        'counting_sum_rule',
        'counting_product_rule',
        'permutations_no_repeat',
        'combinations_basic',
        'counting_paths',
    ],
}

# Русские названия подтем для UI
SUBTOPIC_NAMES_RU = {
    # Логика
    'knights_liars_basic': 'Рыцари и лжецы (базовый)',
    'knights_liars_groups': 'Рыцари и лжецы (группы)',
    'logic_tables': 'Логические таблицы',
    'logic_deduction': 'Логические выводы',
    'logic_paradoxes': 'Логические парадоксы',
    
    # Дирихле
    'pigeonhole_basic': 'Принцип Дирихле (базовый)',
    'pigeonhole_numbers': 'Дирихле в числах',
    'pigeonhole_geometry': 'Дирихле в геометрии',
    'pigeonhole_coloring': 'Дирихле и раскраски',
    'pigeonhole_advanced': 'Дирихле (продвинутый)',
    
    # Ребусы
    'cryptarithmetic_addition': 'Ребусы на сложение',
    'cryptarithmetic_multiplication': 'Ребусы на умножение',
    'digit_puzzles': 'Цифровые головоломки',
    'number_patterns': 'Числовые закономерности',
    
    # Делимость
    'divisibility_rules': 'Признаки делимости',
    'remainders_basic': 'Остатки от деления',
    'last_digit': 'Последняя цифра',
    'divisibility_proofs': 'Доказательства делимости',
    'modular_arithmetic': 'Модульная арифметика',
    'divisibility_by_2_5': 'Делимость на 2 и 5',
    'divisibility_by_3_9': 'Делимость на 3 и 9',
    'divisibility_by_4_8': 'Делимость на 4 и 8',
    'divisibility_by_11': 'Делимость на 11',
    'remainders_system': 'Системы остатков',
    'last_digits_powers': 'Последние цифры степеней',
    
    # Инварианты
    'parity_basic': 'Чётность (базовая)',
    'invariants_coloring': 'Инварианты и раскраски',
    'invariants_operations': 'Инварианты операций',
    'alternating_sequences': 'Чередующиеся последовательности',
    'parity_operations': 'Чётность операций',
    'coloring_2colors': 'Раскраска в 2 цвета',
    'coloring_chessboard': 'Шахматная раскраска',
    'invariants_monovariant': 'Монотонные инварианты',
    
    # Графы
    'graph_handshakes': 'Рукопожатия',
    'graph_tournaments': 'Турниры',
    'graph_paths': 'Маршруты в графах',
    'graph_coloring': 'Раскраска графов',
    'graph_trees': 'Деревья',
    'graph_euler': 'Эйлеровы пути',
    'graph_bipartite': 'Двудольные графы',
    
    # Комбинаторика
    'counting_sum_rule': 'Правило суммы',
    'counting_product_rule': 'Правило произведения',
    'counting_trees': 'Деревья вариантов',
    'counting_arrangements': 'Размещения',
    'counting_selections': 'Выборки',
    'permutations_no_repeat': 'Перестановки без повторений',
    'combinations_basic': 'Сочетания',
    'counting_paths': 'Подсчёт путей',
    
    # Геометрия
    'grid_areas': 'Площади на клетчатой бумаге',
    'grid_perimeters': 'Периметры на клетчатой бумаге',
    'cutting_shapes': 'Разрезание фигур',
    'tiling_domino': 'Замощение домино',
    'tiling_polyomino': 'Замощение полимино',
    'cutting_rectangles': 'Разрезание прямоугольников',
    'cutting_chessboard': 'Разрезание шахматной доски',
    'tiling_L_shape': 'Замощение Г-образными фигурами',
    'tiling_coloring_proof': 'Доказательство через раскраску',
    'perimeter_rectangles': 'Периметры прямоугольников',
    'area_rectangles': 'Площади прямоугольников',
    'area_triangles': 'Площади треугольников',
    'area_composite': 'Площади составных фигур',
    'grid_geometry': 'Геометрия на клетчатой бумаге',
    
    # Взвешивания
    'weighing_balance': 'Взвешивание на весах',
    'weighing_fake_coin': 'Фальшивая монета',
    'pouring_water': 'Переливания',
    'algorithms_sorting': 'Алгоритмы сортировки',
    
    # Текстовые задачи
    'motion_basic': 'Движение (базовое)',
    'motion_meeting': 'Встречное движение',
    'work_together': 'Совместная работа',
    'work_pipes': 'Трубы и бассейны',
    'reverse_operations': 'Обратный ход',
    
    # НОД/НОК
    'gcd_basic': 'НОД (базовый)',
    'lcm_basic': 'НОК (базовый)',
    'prime_factorization': 'Разложение на простые',
    'gcd_lcm_problems': 'Задачи на НОД и НОК',
    'coprime_numbers': 'Взаимно простые числа',
    
    # Дроби
    'fractions_basic': 'Дроби (базовые)',
    'fractions_comparison': 'Сравнение дробей',
    'proportions_direct': 'Прямая пропорция',
    'proportions_inverse': 'Обратная пропорция',
    'percentages': 'Проценты',
}

# Русские названия тем
TOPIC_NAMES_RU = {
    'Логика (рыцари и лжецы, логические таблицы)': 'Логика',
    'Принцип Дирихле': 'Принцип Дирихле',
    'Числовые ребусы и крипторифмы': 'Числовые ребусы',
    'Делимость, остатки и последняя цифра': 'Делимость',
    'Инварианты, четность и чередование': 'Инварианты',
    'Графы (знакомства, турниры, маршруты)': 'Графы',
    'Комбинаторика (правила суммы/произведения, деревья)': 'Комбинаторика',
    'Геометрия на клетчатой бумаге и разрезания': 'Геометрия',
    'Взвешивания, переливания и алгоритмы': 'Взвешивания',
    'Текстовые задачи (движение, совместная работа, обратный ход)': 'Текстовые задачи',
    'Признаки делимости и остатки': 'Делимость',
    'НОД, НОК и основная теорема арифметики': 'НОД и НОК',
    'Дроби, доли и пропорции': 'Дроби',
    'Разрезания и замощения': 'Разрезания',
    'Инварианты (четность, раскраски)': 'Инварианты',
    'Геометрия (периметры и площади)': 'Геометрия',
    'Комбинаторика (правило суммы и произведения)': 'Комбинаторика',
}


def get_subtopics_for_topic(topic: str) -> list:
    """Возвращает список подтем для данной темы."""
    return SUBTOPICS.get(topic, [])


def get_subtopic_name_ru(subtopic: str) -> str:
    """Возвращает русское название подтемы."""
    return SUBTOPIC_NAMES_RU.get(subtopic, subtopic)


def get_topic_name_ru(topic: str) -> str:
    """Возвращает короткое русское название темы."""
    return TOPIC_NAMES_RU.get(topic, topic)


def get_all_subtopics_for_grade(grade: int) -> list:
    """
    Возвращает список всех (topic, subtopic) для данного класса.
    """
    # Темы для 5 класса
    grade5_topics = [
        'Логика (рыцари и лжецы, логические таблицы)',
        'Принцип Дирихле',
        'Числовые ребусы и крипторифмы',
        'Делимость, остатки и последняя цифра',
        'Инварианты, четность и чередование',
        'Графы (знакомства, турниры, маршруты)',
        'Комбинаторика (правила суммы/произведения, деревья)',
        'Геометрия на клетчатой бумаге и разрезания',
        'Взвешивания, переливания и алгоритмы',
        'Текстовые задачи (движение, совместная работа, обратный ход)',
    ]
    
    # Темы для 6 класса
    grade6_topics = [
        'Признаки делимости и остатки',
        'НОД, НОК и основная теорема арифметики',
        'Дроби, доли и пропорции',
        'Графы (знакомства, турниры, маршруты)',
        'Принцип Дирихле',
        'Логика (рыцари и лжецы, логические таблицы)',
        'Разрезания и замощения',
        'Инварианты (четность, раскраски)',
        'Геометрия (периметры и площади)',
        'Комбинаторика (правило суммы и произведения)',
    ]
    
    if grade == 5:
        topics = grade5_topics
    elif grade == 6:
        topics = grade6_topics
    else:
        # Для других классов используем все темы
        topics = list(SUBTOPICS.keys())
    
    result = []
    for topic in topics:
        for subtopic in SUBTOPICS.get(topic, []):
            result.append((topic, subtopic))
    
    return result
