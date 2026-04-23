#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Таксономия подтем для 6 класса FORMYLA.
42 подтемы по 10 темам.
"""

# Словарь: тема → список (subtopic_key, subtopic_ru)
SUBTOPICS_GRADE_6 = {
    'Геометрия (периметры и площади)': [
        ('angles_basic', 'Углы и их виды'),
        ('triangles_intro', 'Виды треугольников'),
        ('perimeter_area', 'Периметр и площадь'),
        ('polygons', 'Многоугольники'),
        ('symmetry', 'Симметрия'),
    ],
    'Графы (знакомства, турниры, маршруты)': [
        ('vertex_degree', 'Степени вершин'),
        ('euler_paths', 'Эйлеровы пути'),
        ('handshake_lemma', 'Лемма о рукопожатиях'),
        ('trees_basic', 'Деревья'),
        ('coloring_graphs', 'Раскраски графов'),
    ],
    'Дроби, доли и пропорции': [
        ('fractions_basic', 'Основы дробей'),
        ('fractions_compare', 'Сравнение дробей'),
        ('fractions_operations', 'Операции с дробями'),
        ('decimals', 'Десятичные дроби'),
    ],
    'Инварианты (четность, раскраски)': [
        ('parity_invariant', 'Чётность'),
        ('sum_invariant', 'Инвариант суммы'),
        ('coloring_invariant', 'Раскраска-инвариант'),
        ('remainders_invariant', 'Инвариант остатков'),
    ],
    'Комбинаторика (правило суммы и произведения)': [
        ('product_rule', 'Правило произведения'),
        ('sum_rule', 'Правило суммы'),
        ('permutations_basic', 'Перестановки'),
        ('combinations_basic', 'Сочетания'),
        ('tree_counting', 'Деревья перебора'),
    ],
    'Логика (рыцари и лжецы, логические таблицы)': [
        ('truth_tellers', 'Рыцари и лжецы'),
        ('weighing', 'Взвешивания'),
        ('tournaments', 'Турниры'),
    ],
    'НОД, НОК и основная теорема арифметики': [
        ('gcd_basic', 'НОД'),
        ('lcm_basic', 'НОК'),
        ('gcd_word_problems', 'Задачи на НОД'),
        ('euclidean_basic', 'Алгоритм Евклида'),
    ],
    'Признаки делимости и остатки': [
        ('divisibility_rules', 'Признаки делимости'),
        ('primes_composite', 'Простые и составные'),
        ('factorization', 'Разложение на множители'),
        ('perfect_numbers', 'Совершенные числа'),
    ],
    'Принцип Дирихле': [
        ('pigeonhole_basic', 'Базовый Дирихле'),
        ('pigeonhole_geometric', 'Геометрический Дирихле'),
        ('pigeonhole_advanced', 'Усиленный Дирихле'),
    ],
    'Разрезания и замощения': [
        ('cutting_simple', 'Простые разрезания'),
        ('cutting_equal_parts', 'На равные части'),
        ('tangrams', 'Танграм и разрезания фигур'),
        ('polyominoes', 'Полимино'),
    ],
}

# Плоский словарь: subtopic_key → subtopic_ru
SUBTOPIC_LABELS = {}
for topic_subtopics in SUBTOPICS_GRADE_6.values():
    for key, label in topic_subtopics:
        SUBTOPIC_LABELS[key] = label

# Плоский словарь: topic → subtopic_keys
TOPIC_TO_SUBTOPICS = {
    topic: [key for key, _ in subtopics]
    for topic, subtopics in SUBTOPICS_GRADE_6.items()
}


def get_subtopics_for_topic(topic: str) -> list:
    """Возвращает список subtopic_key для данной темы."""
    return TOPIC_TO_SUBTOPICS.get(topic, [])


def get_subtopic_label(subtopic_key: str) -> str:
    """Возвращает русское название подтемы."""
    return SUBTOPIC_LABELS.get(subtopic_key, subtopic_key)


def get_all_subtopics() -> list:
    """Возвращает список всех (topic, subtopic_key, subtopic_ru)."""
    result = []
    for topic, subtopics in SUBTOPICS_GRADE_6.items():
        for key, label in subtopics:
            result.append((topic, key, label))
    return result


if __name__ == "__main__":
    all_subtopics = get_all_subtopics()
    print(f"Всего подтем: {len(all_subtopics)}")
    for topic, key, label in all_subtopics:
        print(f"  {topic[:30]:<30} | {key:<25} | {label}")
