#!/usr/bin/env python3
"""Audit: map all tasks to 6 canonical topics and show distribution."""
import psycopg2
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PG_URL = 'postgresql://formyla_user:HwFVHpWWNFZzLvB1m6aXAKfeijKLqtGe@dpg-d7n8uo0g4nts73b1n9k0-a.ohio-postgres.render.com/formyla?sslmode=require'

# Mapping from DB topics to 6 canonical topics
TOPIC_MAP = {
    # === Алгебра ===
    'Algebra': 'Алгебра',
    'Алгебраические тождества и преобразования': 'Алгебра',
    'Алгебра (уравнения, неравенства, системы)': 'Алгебра',
    'Алгебра (полиномы, системы, параметры)': 'Алгебра',
    'Линейные уравнения и системы': 'Алгебра',
    'Неравенства': 'Алгебра',
    'Уравнения и неравенства': 'Алгебра',
    'Функции и графики': 'Алгебра',
    'Функции и анализ (производная, экстремумы, интеграл)': 'Алгебра',
    'Тригонометрия': 'Алгебра',
    'Тригонометрия (уравнения, неравенства, тождества)': 'Алгебра',
    'Последовательности и прогрессии': 'Алгебра',
    'Комплексные числа и продвинутая алгебра': 'Алгебра',
    'Дроби, доли и пропорции': 'Алгебра',
    'Дроби и проценты': 'Алгебра',
    'Числовые ребусы и крипторифмы': 'Алгебра',
    'Текстовые задачи (совместная работа, обратный ход)': 'Алгебра',

    # === Геометрия ===
    'Geometry': 'Геометрия',
    'Геометрические доказательства': 'Геометрия',
    'Геометрия на клетчатой бумаге и разрезания': 'Геометрия',
    'Геометрия (периметры и площади)': 'Геометрия',
    'Геометрия (площади, углы)': 'Геометрия',
    'Геометрия (планиметрия, окружности)': 'Геометрия',
    'Начала геометрии': 'Геометрия',
    'Треугольники': 'Геометрия',
    'Планиметрия (окружности, подобие, площади)': 'Геометрия',
    'Стереометрия (объёмы, сечения, расстояния)': 'Геометрия',
    'Разрезания и замощения': 'Геометрия',

    # === Теория чисел ===
    'Теория чисел': 'Теория чисел',
    'Теория чисел (делимость, остатки)': 'Теория чисел',
    'Теория чисел (делимость, сравнения, диофантовы)': 'Теория чисел',
    'Делимость, остатки и последняя цифра': 'Теория чисел',
    'НОД, НОК и основная теорема арифметики': 'Теория чисел',
    'Признаки делимости и остатки': 'Теория чисел',

    # === Комбинаторика ===
    'Комбинаторика': 'Комбинаторика',
    'Комбинаторика (правило суммы и произведения)': 'Комбинаторика',
    'Комбинаторика (правилы суммы/произведения, деревья)': 'Комбинаторика',
    'Комбинаторика и теория вероятностей': 'Комбинаторика',
    'Комбинаторика и вероятность': 'Комбинаторика',
    'Графы (знакомства, турниры, маршруты)': 'Комбинаторика',
    'Принцип Дирихле': 'Комбинаторика',
    'Инварианты, четность и чередование': 'Комбинаторика',
    'Инварианты (четность, раскраски)': 'Комбинаторика',
    'Взвешивания, переливания и алгоритмы': 'Комбинаторика',
    'Комбинаторика и вероятность': 'Комбинаторика',

    # === Задачи на движение ===
    'Задачи на движение': 'Задачи на движение',

    # === Логика (рыцари и лжецы) ===
    'Логика (рыцари и лжецы, логические таблицы)': 'Логика (рыцари и лжецы)',
    'Логика и инварианты': 'Логика (рыцари и лжецы)',
    'Логика и комбинаторика': 'Логика (рыцари и лжецы)',
    'Логика и комбинаторика': 'Логика (рыцари и лжецы)',

    # === Прочее (не попало) ===
    'TEST_DELETE': '_мусор',
}

conn = psycopg2.connect(PG_URL, connect_timeout=15)
cur = conn.cursor()

cur.execute('SELECT class_level, topic, COUNT(*) FROM adaptive_tasks GROUP BY class_level, topic ORDER BY class_level, topic')
raw = cur.fetchall()
conn.close()

# Aggregate
from collections import defaultdict
data = defaultdict(lambda: defaultdict(int))
unmapped = defaultdict(int)

CANONICAL = ['Алгебра', 'Геометрия', 'Теория чисел', 'Комбинаторика', 'Задачи на движение', 'Логика (рыцари и лжецы)']

for grade, topic, count in raw:
    mapped = TOPIC_MAP.get(topic)
    if mapped and mapped != '_мусор':
        data[grade][mapped] += count
    elif mapped == '_мусор':
        pass  # skip
    else:
        unmapped[topic] += count
        # Try fuzzy match
        t_lower = topic.lower()
        if 'алгебр' in t_lower or 'уравнен' in t_lower or 'неравен' in t_lower or 'функц' in t_lower or 'тригон' in t_lower or 'дроб' in t_lower:
            data[grade]['Алгебра'] += count
        elif 'геометр' in t_lower or 'треугольн' in t_lower or 'планиметр' in t_lower or 'стереометр' in t_lower or 'разрезан' in t_lower:
            data[grade]['Геометрия'] += count
        elif 'теор' in t_lower and 'чис' in t_lower or 'делим' in t_lower or 'нод' in t_lower or 'нок' in t_lower or 'остат' in t_lower:
            data[grade]['Теория чисел'] += count
        elif 'комбинатор' in t_lower or 'граф' in t_lower or 'дирихле' in t_lower or 'инвариант' in t_lower or 'взвешив' in t_lower or 'вероятн' in t_lower:
            data[grade]['Комбинаторика'] += count
        elif 'движен' in t_lower:
            data[grade]['Задачи на движение'] += count
        elif 'логик' in t_lower or 'рыцар' in t_lower or 'лжец' in t_lower:
            data[grade]['Логика (рыцари и лжецы)'] += count
        else:
            data[grade]['Алгебра'] += count  # default fallback

# Print table
print(f'\n{"Класс":<8}', end='')
for t in CANONICAL:
    print(f'{t:<20}', end='')
print(f'{"ИТОГО":<10}')
print('=' * (8 + 20*6 + 10))

grand_totals = defaultdict(int)
for grade in sorted(data.keys()):
    row_total = 0
    print(f'{grade:<8}', end='')
    for t in CANONICAL:
        val = data[grade].get(t, 0)
        grand_totals[t] += val
        row_total += val
        print(f'{val:<20}', end='')
    print(f'{row_total:<10}')

print('=' * (8 + 20*6 + 10))
print(f'{"ИТОГО":<8}', end='')
gt = 0
for t in CANONICAL:
    print(f'{grand_totals[t]:<20}', end='')
    gt += grand_totals[t]
print(f'{gt:<10}')

if unmapped:
    print(f'\nНеклассифицированные темы (отнесены по ключевым словам):')
    for topic, count in sorted(unmapped.items(), key=lambda x: -x[1]):
        print(f'  {topic:<55} {count}')
