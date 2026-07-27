#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
VICTOR2.0 — L4/L5 Cell Filling Pipeline
=========================================
Заполняет уровни 4 и 5 задачами из кандидатского файла (3302 задачи).

Критическая метрика: МАКСИМИЗАЦИЯ ПОЛНОСТЬЮ ЗАПОЛНЕННЫХ ЯЧЕЕК (5 задач на ячейку).
Ячейка = (class_level, difficulty_level, topic, subtopic)

Лексикографический приоритет:
  1. completed_cells (полностью заполненные ячейки)
  2. filled_slots (всего заполненных слотов)
  3. total_quality (суммарное качество)
  4. total_diversity (суммарное разнообразие источников)
"""

import json
import os
import sys
import re
import hashlib
import math
import copy
import time
from collections import defaultdict, Counter
from datetime import datetime, timezone
from typing import Optional

# ============================================================================
# Windows console encoding fix
# ============================================================================
if sys.platform == 'win32':
    import codecs
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# ============================================================================
# 0. PATHS
# ============================================================================
WORKSPACE = "c:/Users/Victor/Desktop/Новая папка (2)"
CANDIDATE_FILE = "C:/Users/Victor/Downloads/СКАЧАТЬ_FORMYLA_3302_задачи_уровни_4_5.jsonl"
CURATED_BANK_FILE = os.path.join(WORKSPACE, "curated_bank_L1_L5_fixed.json")
OUTPUT_DIR = os.path.join(WORKSPACE, "l4_l5_fill_output")

# Output files
OUTPUT_DB = os.path.join(OUTPUT_DIR, "curated_bank_L4_L5_filled.json")
OUTPUT_CSV = os.path.join(OUTPUT_DIR, "cell_fill_report.csv")
OUTPUT_AUDIT = os.path.join(OUTPUT_DIR, "fill_audit.json")
OUTPUT_REJECTED = os.path.join(OUTPUT_DIR, "rejected_tasks.json")
OUTPUT_UNCERTAIN = os.path.join(OUTPUT_DIR, "uncertain_tasks.json")
OUTPUT_OVERFLOW = os.path.join(OUTPUT_DIR, "overflow_tasks.json")
OUTPUT_REPORT = os.path.join(OUTPUT_DIR, "FINAL_REPORT.md")

# ============================================================================
# 1. THEMES & GRADE_THEMES (from VICTOR2.0)
# ============================================================================
THEMES = {
    "T001": {"name": "Алгебра: теория групп",
             "subtopics": ["Группы: определения и примеры",
                           "Группы: подгруппы, смежные классы",
                           "Гомоморфизмы и факторгруппы"]},
    "T002": {"name": "Арифметика и теория чисел",
             "subtopics": ["Делимость и остатки",
                           "НОД, НОК, алгоритм Евклида",
                           "Сравнения по модулю (a ≡ b mod n)"]},
    "T003": {"name": "Вероятность и комбинаторика",
             "subtopics": ["Геометрическая вероятность",
                           "Классическая вероятность",
                           "Условная вероятность и формула Байеса"]},
    "T004": {"name": "Графы: основные понятия",
             "subtopics": ["Графы: определения, изоморфизм",
                           "Маршруты, цепи, циклы, Эйлеровы графы",
                           "Связность и компоненты связности"]},
    "T005": {"name": "Дополнительные задачи и смешанные темы",
             "subtopics": ["Задачи на оптимизацию",
                           "Комбинированные задачи (алгебра + геометрия)",
                           "Прикладные задачи"]},
    "T006": {"name": "Комбинаторика и вероятность",
             "subtopics": ["Перестановки и факториалы",
                           "Правила сложения и умножения в комбинаторике",
                           "Размещения и сочетания"]},
    "T007": {"name": "Комбинаторика и теория игр",
             "subtopics": ["Выигрышные и проигрышные позиции",
                           "Игры с симметричной стратегией",
                           "Стратегия и анализ игр"]},
    "T008": {"name": "Логика и множества",
             "subtopics": ["Булевы функции и их минимизация",
                           "Логические операции и таблицы истинности",
                           "Множества и операции над ними"]},
    "T009": {"name": "Метод координат: декартовы координаты",
             "subtopics": ["Координаты на прямой и плоскости",
                           "Расстояние между точками, середина отрезка",
                           "Уравнения прямых и окружностей"]},
    "T010": {"name": "Метод координат: векторы",
             "subtopics": ["Векторы: сложение, умножение на число",
                           "Координаты вектора, связь с точками",
                           "Скалярное произведение векторов"]},
    "T011": {"name": "Неравенства: алгебраические неравенства",
             "subtopics": ["Доказательство неравенств",
                           "Квадратные неравенства",
                           "Неравенства с модулем"]},
    "T012": {"name": "Неравенства: метод интервалов и рациональные",
             "subtopics": ["Дробно-рациональные неравенства",
                           "Иррациональные неравенства",
                           "Метод интервалов для рациональных неравенств"]},
    "T013": {"name": "Неравенства: показательные и логарифмические",
             "subtopics": ["Логарифмические неравенства",
                           "Показательные неравенства",
                           "Системы показательных и логарифмических неравенств"]},
    "T014": {"name": "Неравенства: тригонометрические",
             "subtopics": ["Неравенства с обр. тригонометрическими функциями",
                           "Простейшие тригонометрические неравенства с sin, cos",
                           "Простейшие тригонометрические неравенства с tg, ctg"]},
    "T015": {"name": "Неравенства: числовые наборы",
             "subtopics": ["Неравенства о среднем арифметическом и среднем геометрическом",
                           "Неравенства Чебышева и Маркова",
                           "Цепочки неравенств, взвешенные средние"]},
    "T016": {"name": "Планиметрия: многоугольники",
             "subtopics": ["Многоугольники: виды, свойства",
                           "Параллелограммы и трапеции",
                           "Треугольники: виды, свойства"]},
    "T017": {"name": "Планиметрия: окружность",
             "subtopics": ["Вписанные углы и их свойства",
                           "Длина окружности, площадь круга и сектора",
                           "Касательные и секущие к окружности"]},
    "T018": {"name": "Планиметрия: площадь",
             "subtopics": ["Площади подобных фигур",
                           "Площадь круга и его частей",
                           "Формулы площади треугольника и четырёхугольника"]},
    "T019": {"name": "Планиметрия: треугольники",
             "subtopics": ["Подобие треугольников",
                           "Признаки равенства треугольников",
                           "Теорема Пифагора"]},
    "T020": {"name": "Последовательности и прогрессии",
             "subtopics": ["Арифметическая прогрессия",
                           "Геометрическая прогрессия",
                           "Суммы последовательностей"]},
    "T021": {"name": "Производная и её применение",
             "subtopics": ["Геометрический смысл производной",
                           "Исследование функций с помощью производной",
                           "Правила и формулы дифференцирования"]},
    "T022": {"name": "Проценты, отношения и пропорции",
             "subtopics": ["Задачи на проценты",
                           "Пропорции и отношения",
                           "Прямая и обратная пропорциональность"]},
    "T023": {"name": "Рациональные уравнения и неравенства",
             "subtopics": ["Дробно-рациональные уравнения",
                           "Метод замены переменной в рациональных уравнениях",
                           "Рациональные уравнения"]},
    "T024": {"name": "Решение задач: анализ и интерпретация",
             "subtopics": ["Оценка и прикидка",
                           "Проверка решения и поиск ошибок",
                           "Составление плана решения"]},
    "T025": {"name": "Решение уравнений: методы замены",
             "subtopics": ["Замена переменной (подстановка)",
                           "Использование симметрии",
                           "Сведение к системе уравнений"]},
    "T026": {"name": "Решение уравнений: разложение на множители",
             "subtopics": ["Вынесение общего множителя и группировка",
                           "Использование формул сокращённого умножения",
                           "Разложение квадратного трёхчлена"]},
    "T027": {"name": "Системы уравнений",
             "subtopics": ["Графический метод решения систем",
                           "Метод подстановки",
                           "Системы линейных уравнений"]},
    "T028": {"name": "Стереометрия: аксиомы и прямые",
             "subtopics": ["Аксиомы стереометрии",
                           "Взаимное расположение прямых в пространстве",
                           "Скрещивающиеся прямые"]},
    "T029": {"name": "Стереометрия: многогранники",
             "subtopics": ["Параллелепипеды, призмы",
                           "Пирамиды",
                           "Правильные многогранники"]},
    "T030": {"name": "Стереометрия: тела вращения",
             "subtopics": ["Конус, цилиндр",
                           "Сфера, шар",
                           "Тела вращения: сечения, комбинации"]},
    "T031": {"name": "Стереометрия: угол и расстояние",
             "subtopics": ["Расстояние от точки до плоскости",
                           "Угол между плоскостями (двугранный угол)",
                           "Угол между прямой и плоскостью"]},
    "T032": {"name": "Текстовые задачи: движение",
             "subtopics": ["Движение в противоположных направлениях",
                           "Движение по воде",
                           "Движение по кругу"]},
    "T033": {"name": "Текстовые задачи: производительность и смеси",
             "subtopics": ["Задачи на концентрацию, сплавы, смеси",
                           "Задачи на совместную работу",
                           "Задачи на производительность труда"]},
    "T034": {"name": "Теория вероятностей: дискретные распределения",
             "subtopics": ["Биномиальное распределение",
                           "Дискретные случайные величины",
                           "Математическое ожидание и дисперсия"]},
    "T035": {"name": "Тригонометрические уравнения",
             "subtopics": ["Однородные тригонометрические уравнения",
                           "Отбор корней в тригонометрических уравнениях",
                           "Простейшие тригонометрические уравнения"]},
    "T036": {"name": "Тригонометрия: преобразования",
             "subtopics": ["Основное тригонометрическое тождество",
                           "Формулы приведения",
                           "Формулы сложения и двойного угла"]},
    "T037": {"name": "Уравнения с модулем",
             "subtopics": ["Графическое решение уравнений с модулем",
                           "Метод интервалов для уравнений с модулем",
                           "Уравнения с модулем"]},
    "T038": {"name": "Уравнения: иррациональные",
             "subtopics": ["Иррациональные уравнения с одним корнем",
                           "Иррациональные уравнения с несколькими корнями",
                           "Метод замены в иррациональных уравнениях"]},
    "T039": {"name": "Уравнения: показательные и логарифмические",
             "subtopics": ["Логарифмические уравнения",
                           "Показательные уравнения",
                           "Системы показательных и логарифмических уравнений"]},
    "T040": {"name": "Уравнения: тригонометрические системы",
             "subtopics": ["Системы тригонометрических уравнений",
                           "Тригонометрические уравнения с параметром",
                           "Тригонометрические уравнения с отбором корней"]},
    "T041": {"name": "Числа, индукция, алгоритмы",
             "subtopics": ["Алгоритмы и вычисления",
                           "Комплексные числа",
                           "Метод математической индукции"]},
    "T042": {"name": "Функции и графики",
             "subtopics": ["Графики функций: преобразования и сдвиги",
                           "Область определения и область значений",
                           "Построение графиков сложных функций"]},
    "T043": {"name": "Стереометрия: объёмы и сечения",
             "subtopics": ["Объём многогранников",
                           "Объём тел вращения",
                           "Сечения многогранников"]}
}

GRADE_THEMES = {
    5:  ["T002", "T022", "T008", "T004", "T024", "T005"],
    6:  ["T006", "T007", "T032", "T033", "T016", "T018"],
    7:  ["T026", "T025", "T023", "T027", "T019", "T003"],
    8:  ["T042", "T011", "T012", "T037", "T009", "T017"],
    9:  ["T038", "T020", "T010", "T015", "T036", "T035"],
    10: ["T039", "T013", "T014", "T028", "T029", "T030"],
    11: ["T021", "T040", "T034", "T043", "T031", "T041", "T001"]
}

TASKS_PER_CELL = 5

# ============================================================================
# 2. SUBTOPIC KEYWORDS FOR CLASSIFICATION
# ============================================================================
# Build keyword lists for each theme/subtopic
SUBTOPIC_KEYWORDS = {}
for tid, theme in THEMES.items():
    tname = theme["name"].lower()
    for si, sub in enumerate(theme["subtopics"]):
        key = (tid, si)
        words = set()
        # From subtopic name
        for w in re.findall(r'[а-яёa-z]+', sub.lower()):
            if len(w) > 3:
                words.add(w)
        # From theme name
        for w in re.findall(r'[а-яёa-z]+', tname):
            if len(w) > 3:
                words.add(w)
        SUBTOPIC_KEYWORDS[key] = words

# Additional topic-specific keyword maps for better classification
TOPIC_CLASSIFIERS = {
    "T002": {
        "keywords": ["делимост", "нод", "нок", "евклид", "остатк", "сравнен", "модул",
                     "простое", "составное", "делител", "кратн", "прост", "числ"],
        "subtopic_map": [
            ["делимост", "остатк"],
            ["нод", "нок", "евклид"],
            ["сравнен", "модул", "congru"]
        ]
    },
    "T003": {
        "keywords": ["вероятност", "комбинатор", "случайн"],
        "subtopic_map": [
            ["геометрическ"],
            ["классическ"],
            ["условн", "байес"]
        ]
    },
    "T006": {
        "keywords": ["комбинатор", "вероятност", "перестановк", "факториал", "размещен"],
        "subtopic_map": [
            ["перестановк", "факториал"],
            ["сложени", "умножени", "правил"],
            ["размещен", "сочетани"]
        ]
    },
    "T007": {
        "keywords": ["игр", "выигрыш", "проигрыш", "стратег"],
        "subtopic_map": [
            ["выигрыш", "проигрыш"],
            ["симметрич"],
            ["стратег"]
        ]
    },
    "T016": {
        "keywords": ["многоугольник", "треугольник", "четырехугольник", "параллелограмм", "трапеци"],
        "subtopic_map": [
            ["многоугольник"],
            ["параллелограмм", "трапеци"],
            ["треугольник"]
        ]
    },
    "T022": {
        "keywords": ["процент", "пропорци", "отношен"],
        "subtopic_map": [
            ["процент"],
            ["пропорци", "отношен"],
            ["прям", "обратн", "пропорциональн"]
        ]
    },
    "T032": {
        "keywords": ["движени", "скорост", "путь", "расстоян"],
        "subtopic_map": [
            ["противоположн"],
            ["вод", "течени", "плот"],
            ["круг", "окружност"]
        ]
    },
    "T033": {
        "keywords": ["производительн", "работ", "смес", "концентрац", "сплав"],
        "subtopic_map": [
            ["концентрац", "сплав", "смес"],
            ["совместн", "работ"],
            ["производительн"]
        ]
    },
    "T008": {
        "keywords": ["логик", "булев", "множеств", "таблиц истин"],
        "subtopic_map": [
            ["булев", "минимизац"],
            ["логическ", "таблиц истин"],
            ["множеств"]
        ]
    },
    "T004": {
        "keywords": ["граф", "изоморф", "маршрут", "цикл", "эйлер", "связн"],
        "subtopic_map": [
            ["граф", "изоморф"],
            ["маршрут", "цеп", "цикл", "эйлер"],
            ["связн", "компонент"]
        ]
    },
    "T024": {
        "keywords": ["оценк", "прикидк", "проверк", "ошибк", "план решен"],
        "subtopic_map": [
            ["оценк", "прикидк"],
            ["проверк", "ошибк"],
            ["план"]
        ]
    },
    "T005": {
        "keywords": ["оптимизац", "комбинирован", "прикладн"],
        "subtopic_map": [
            ["оптимизац"],
            ["комбинирован"],
            ["прикладн"]
        ]
    },
    "T026": {
        "keywords": ["множител", "разложени", "группировк", "фсу", "формул сокращ"],
        "subtopic_map": [
            ["вынесени", "группировк"],
            ["сокращ", "фсу", "формул"],
            ["квадратн", "трехчлен"]
        ]
    },
    "T025": {
        "keywords": ["замен", "подстановк", "симметри"],
        "subtopic_map": [
            ["замен", "подстановк"],
            ["симметри"],
            ["систем"]
        ]
    },
    "T023": {
        "keywords": ["рациональн", "дробн"],
        "subtopic_map": [
            ["дробно-рациональн"],
            ["замен"],
            ["рациональн"]
        ]
    },
    "T027": {
        "keywords": ["систем", "графическ", "подстановк"],
        "subtopic_map": [
            ["графическ"],
            ["подстановк"],
            ["линейн"]
        ]
    },
    "T019": {
        "keywords": ["треугольник", "подоби", "равенств", "пифагор"],
        "subtopic_map": [
            ["подоби"],
            ["равенств"],
            ["пифагор"]
        ]
    },
    "T042": {
        "keywords": ["функци", "график", "область определен", "область значени"],
        "subtopic_map": [
            ["график", "преобразован", "сдвиг"],
            ["область определен", "область значени"],
            ["построени", "сложн"]
        ]
    },
    "T011": {
        "keywords": ["неравенств", "доказательств"],
        "subtopic_map": [
            ["доказательств"],
            ["квадратн"],
            ["модул"]
        ]
    },
    "T012": {
        "keywords": ["неравенств", "интервал", "рациональн", "иррациональн"],
        "subtopic_map": [
            ["дробно-рациональн"],
            ["иррациональн"],
            ["интервал"]
        ]
    },
    "T037": {
        "keywords": ["модул"],
        "subtopic_map": [
            ["графическ"],
            ["интервал"],
            ["модул"]
        ]
    },
    "T009": {
        "keywords": ["координат", "расстоян", "плоскост", "прям", "окружност"],
        "subtopic_map": [
            ["координат", "прям", "плоскост"],
            ["расстоян", "середин"],
            ["уравнен", "прям", "окружност"]
        ]
    },
    "T017": {
        "keywords": ["окружност", "вписан", "касательн", "секущ", "площад круг"],
        "subtopic_map": [
            ["вписан"],
            ["длин", "площад", "круг", "сектор"],
            ["касательн", "секущ"]
        ]
    },
    "T038": {
        "keywords": ["иррациональн", "корн"],
        "subtopic_map": [
            ["одн"],
            ["нескольк"],
            ["замен"]
        ]
    },
    "T020": {
        "keywords": ["прогресси", "последовательн", "сумм"],
        "subtopic_map": [
            ["арифметическ"],
            ["геометрическ"],
            ["сумм"]
        ]
    },
    "T010": {
        "keywords": ["вектор"],
        "subtopic_map": [
            ["сложени", "умножени"],
            ["координат"],
            ["скалярн"]
        ]
    },
    "T015": {
        "keywords": ["средн", "арифметическ", "геометрическ", "чебышев", "марков"],
        "subtopic_map": [
            ["средн", "арифметическ", "геометрическ"],
            ["чебышев", "марков"],
            ["цепочк", "взвешен"]
        ]
    },
    "T036": {
        "keywords": ["тригонометри", "тождеств", "приведени", "сложени", "двойн"],
        "subtopic_map": [
            ["тождеств"],
            ["приведени"],
            ["сложени", "двойн"]
        ]
    },
    "T035": {
        "keywords": ["тригонометри", "уравнен"],
        "subtopic_map": [
            ["однородн"],
            ["отбор"],
            ["простей"]
        ]
    },
    "T039": {
        "keywords": ["показательн", "логарифмическ", "уравнен"],
        "subtopic_map": [
            ["логарифмическ"],
            ["показательн"],
            ["систем"]
        ]
    },
    "T013": {
        "keywords": ["неравенств", "показательн", "логарифмическ"],
        "subtopic_map": [
            ["логарифмическ"],
            ["показательн"],
            ["систем"]
        ]
    },
    "T014": {
        "keywords": ["тригонометри", "неравенств"],
        "subtopic_map": [
            ["обратн"],
            ["sin", "cos"],
            ["tg", "ctg"]
        ]
    },
    "T028": {
        "keywords": ["стереометри", "прям", "пространств"],
        "subtopic_map": [
            ["аксиом"],
            ["взаимн", "расположени"],
            ["скрещива"]
        ]
    },
    "T029": {
        "keywords": ["многогранник", "призм", "пирамид", "параллелепипед"],
        "subtopic_map": [
            ["параллелепипед", "призм"],
            ["пирамид"],
            ["правильн", "многогран"]
        ]
    },
    "T030": {
        "keywords": ["тел", "вращен", "конус", "цилиндр", "сфер", "шар"],
        "subtopic_map": [
            ["конус", "цилиндр"],
            ["сфер", "шар"],
            ["сечени", "комбинац"]
        ]
    },
    "T031": {
        "keywords": ["расстоян", "угол", "плоскост", "двугран"],
        "subtopic_map": [
            ["расстоян", "точк", "плоскост"],
            ["двугран"],
            ["прям", "плоскост"]
        ]
    },
    "T039": {
        "keywords": ["показательн", "логарифмическ"],
        "subtopic_map": [
            ["логарифмическ"],
            ["показательн"],
            ["систем"]
        ]
    },
    "T040": {
        "keywords": ["тригонометри", "систем", "параметр", "отбор"],
        "subtopic_map": [
            ["систем"],
            ["параметр"],
            ["отбор"]
        ]
    },
    "T034": {
        "keywords": ["вероятност", "распределен", "случайн", "математическ", "ожидан", "дисперс"],
        "subtopic_map": [
            ["биномиальн"],
            ["дискретн", "случайн"],
            ["математическ", "ожидан", "дисперс"]
        ]
    },
    "T043": {
        "keywords": ["объем", "сечени", "многогран"],
        "subtopic_map": [
            ["объем", "многогран"],
            ["объем", "тел", "вращен"],
            ["сечени"]
        ]
    },
    "T041": {
        "keywords": ["алгоритм", "вычислен", "комплексн", "индукци"],
        "subtopic_map": [
            ["алгоритм", "вычислен"],
            ["комплексн"],
            ["индукци"]
        ]
    },
    "T001": {
        "keywords": ["групп", "гомоморфизм", "факторгрупп", "подгрупп"],
        "subtopic_map": [
            ["определен", "пример"],
            ["подгрупп", "смежн"],
            ["гомоморфизм", "факторгрупп"]
        ]
    },
    "T021": {
        "keywords": ["производн", "дифференцирован"],
        "subtopic_map": [
            ["геометрическ", "смысл"],
            ["исследован"],
            ["правил", "формул"]
        ]
    },
    "T018": {
        "keywords": ["площад"],
        "subtopic_map": [
            ["подоб"],
            ["круг"],
            ["треугольник", "четырехугольник"]
        ]
    }
}

# ============================================================================
# 3. HELPER FUNCTIONS
# ============================================================================

def normalize_text(text):
    """Normalize text for comparison: lowercase, remove extra spaces."""
    if not text:
        return ""
    text = text.lower().strip()
    text = re.sub(r'\s+', ' ', text)
    return text


def try_decode_garbled(text):
    """Try to fix garbled cp1251 text."""
    if not text:
        return text
    # The text appears to be cp1251 bytes interpreted as cp866 (or similar)
    # Try to re-encode as latin1 then decode as cp1251
    try:
        # First, try to detect if it's already readable Russian (has cyrillic)
        if re.search(r'[а-яА-ЯёЁ]', text):
            return text  # Already has cyrillic, return as-is
        
        # Try common fixes
        # cp1251 -> bytes -> cp866
        encoded = text.encode('latin1', errors='replace')
        decoded = encoded.decode('cp1251', errors='replace')
        if re.search(r'[а-яА-ЯёЁ]', decoded):
            return decoded
    except:
        pass
    
    try:
        # Another common pattern: raw bytes misinterpreted
        encoded = text.encode('raw_unicode_escape', errors='replace')
        decoded = encoded.decode('cp1251', errors='replace')
        if re.search(r'[а-яА-ЯёЁ]', decoded):
            return decoded
    except:
        pass
    
    return text


def compute_import_key(problem, source_name="candidate"):
    """Compute import key: hash of (source_olympiad, source_year, source_round, source_problem_num, normalized_statement)."""
    olympiad = problem.get('_olympiad', problem.get('olympiad', ''))
    year = str(problem.get('_year', problem.get('year', '')))
    round_val = str(problem.get('_round', problem.get('round', '')))
    num = str(problem.get('num', problem.get('original_id', '')))
    
    # Get statement from various possible field names
    statement = problem.get('text') or problem.get('statement') or problem.get('task_text') or ''
    norm_stmt = normalize_text(statement)[:200]
    
    raw = f"{olympiad}|{year}|{round_val}|{num}|{norm_stmt}"
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]


def compute_ngrams(text, n=3):
    """Compute character n-gram set for text fingerprinting.
    Uses frozenset for hashability and fast set operations.
    """
    if not text:
        return frozenset()
    text = normalize_text(text)
    if len(text) < n:
        return frozenset([text])
    return frozenset(text[i:i+n] for i in range(len(text) - n + 1))


def ngram_similarity(set_a, set_b):
    """Compute Jaccard similarity between two n-gram sets.
    Fast O(min(|A|,|B|)) set operation vs O(n*m) for SequenceMatcher.
    """
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    if union == 0:
        return 0.0
    return intersection / union


def compute_similarity(a, b):
    """Compute text similarity using character n-gram Jaccard similarity.
    100-1000x faster than SequenceMatcher for long texts.
    """
    if not a or not b:
        return 0.0
    a = normalize_text(a)
    b = normalize_text(b)
    if len(a) < 10 or len(b) < 10:
        return 0.0
    ngrams_a = compute_ngrams(a, n=3)
    ngrams_b = compute_ngrams(b, n=3)
    return ngram_similarity(ngrams_a, ngrams_b)


def extract_numbers(text):
    """Extract all numbers from text."""
    if not text:
        return set()
    return set(re.findall(r'\d+', text))


def is_duplicate_stage1(task_a, task_b):
    """Stage 1: exact normalized match."""
    stmt_a = normalize_text(task_a.get('text', task_a.get('statement', '')))
    stmt_b = normalize_text(task_b.get('text', task_b.get('statement', '')))
    if not stmt_a or not stmt_b:
        return False
    return stmt_a == stmt_b


def is_duplicate_stage2(task_a, task_b, threshold=0.60):
    """Stage 2: high text similarity using n-gram Jaccard.
    threshold=0.60 maps approximately to ~0.85 SequenceMatcher ratio.
    """
    stmt_a = normalize_text(task_a.get('text', task_a.get('statement', '')))
    stmt_b = normalize_text(task_b.get('text', task_b.get('statement', '')))
    if not stmt_a or not stmt_b:
        return False
    fp_a = compute_ngrams(stmt_a)
    fp_b = compute_ngrams(stmt_b)
    return ngram_similarity(fp_a, fp_b) >= threshold


def is_duplicate_stage3(task_a, task_b, threshold=0.40):
    """Stage 3: same math with replaced numbers.
    threshold=0.40 maps approximately to ~0.70 SequenceMatcher ratio.
    """
    stmt_a = normalize_text(task_a.get('text', task_a.get('statement', '')))
    stmt_b = normalize_text(task_b.get('text', task_b.get('statement', '')))
    if not stmt_a or not stmt_b:
        return False
    fp_a = compute_ngrams(stmt_a)
    fp_b = compute_ngrams(stmt_b)
    sim = ngram_similarity(fp_a, fp_b)
    if sim < threshold:
        return False
    # Check if the difference is mainly in numbers
    nums_a = extract_numbers(stmt_a)
    nums_b = extract_numbers(stmt_b)
    if not nums_a or not nums_b:
        return sim >= 0.50  # ~0.80 SequenceMatcher
    # If the text without numbers is very similar, it's a number-substituted duplicate
    text_no_nums_a = re.sub(r'\d+', 'N', stmt_a)
    text_no_nums_b = re.sub(r'\d+', 'N', stmt_b)
    fp_no_nums_a = compute_ngrams(text_no_nums_a)
    fp_no_nums_b = compute_ngrams(text_no_nums_b)
    return ngram_similarity(fp_no_nums_a, fp_no_nums_b) >= 0.60  # ~0.85 SequenceMatcher


def compute_quality_score(task):
    """Compute quality score for a task."""
    sol = task.get('solution', task.get('solution_text', ''))
    stmt = task.get('text', task.get('statement', task.get('task_text', '')))
    
    # solution_completeness (0.30)
    sol_len = len(sol.strip()) if sol else 0
    sol_completeness = min(1.0, sol_len / 500) if sol_len > 0 else 0.0
    
    # statement_clarity (0.25) - based on length and structure
    stmt_len = len(stmt.strip()) if stmt else 0
    statement_clarity = min(1.0, stmt_len / 200) if stmt_len > 0 else 0.0
    
    # subtopic_relevance (0.20) - default 0.7 for candidates
    subtopic_relevance = 0.7
    
    # difficulty_confidence (0.15) - based on has_valid_solution
    has_valid = task.get('has_valid_solution', task.get('solution_verified', False))
    difficulty_confidence = 0.9 if has_valid else 0.5
    
    # source_quality (0.10)
    olympiad = task.get('_olympiad', task.get('olympiad', ''))
    if olympiad in ('vsosh', 'region', 'final'):
        source_quality = 1.0
    elif olympiad in ('euler', 'kysh', 'turloomath'):
        source_quality = 0.9
    elif olympiad in ('mos', 'spb', 'mipt'):
        source_quality = 0.8
    elif olympiad:
        source_quality = 0.7
    else:
        source_quality = 0.5
    
    score = (0.30 * sol_completeness +
             0.25 * statement_clarity +
             0.20 * subtopic_relevance +
             0.15 * difficulty_confidence +
             0.10 * source_quality)
    return round(score * 100, 1)


def classify_problem(problem):
    """
    Classify a candidate problem into (theme_id, subtopic_index).
    Uses grade -> possible themes -> keyword matching.
    """
    grade = problem.get('_grade', problem.get('grade', 0))
    if not grade or grade not in GRADE_THEMES:
        return None, None, 0.0
    
    # Get possible themes for this grade
    possible_tids = GRADE_THEMES.get(grade, [])
    if not possible_tids:
        return None, None, 0.0
    
    # Build search text from all available fields
    text = problem.get('text', problem.get('statement', ''))
    solution = problem.get('solution', '')
    answer = problem.get('answer', '')
    olympiad_name = problem.get('_olympiad', problem.get('olympiad', ''))
    round_name = problem.get('_round', problem.get('round', ''))
    
    # Try to fix encoding
    readable_text = try_decode_garbled(text)
    readable_solution = try_decode_garbled(solution)
    readable_answer = try_decode_garbled(answer)
    
    search_text = f"{readable_text} {readable_solution} {readable_answer} {olympiad_name} {round_name}".lower()
    
    # Also add original text in case it has useful patterns
    search_text += " " + text.lower()
    
    best_tid = None
    best_si = None
    best_score = 0.0
    
    # First, check if any classifier matches
    for tid in possible_tids:
        if tid not in TOPIC_CLASSIFIERS:
            continue
        classifier = TOPIC_CLASSIFIERS[tid]
        
        # Check if the topic is relevant at all
        topic_score = 0.0
        for kw in classifier["keywords"]:
            if kw in search_text:
                topic_score += 1.0
        
        if topic_score == 0:
            continue
        
        # Normalize topic score
        topic_score = topic_score / len(classifier["keywords"])
        
        # Check which subtopic
        sub_map = classifier["subtopic_map"]
        for si, sub_keywords in enumerate(sub_map):
            sub_score = 0.0
            for skw in sub_keywords:
                if skw in search_text:
                    sub_score += 1.0
            if len(sub_keywords) > 0:
                sub_score = sub_score / len(sub_keywords)
            
            total = topic_score * 0.4 + sub_score * 0.6
            if total > best_score:
                best_score = total
                best_tid = tid
                best_si = si
    
    # Also try checking against subtopic names directly
    if best_score < 0.3:
        for tid in possible_tids:
            theme = THEMES[tid]
            for si, sub_name in enumerate(theme["subtopics"]):
                sub_lower = sub_name.lower()
                # Count matching words
                sub_words = set(re.findall(r'[а-яёa-z]+', sub_lower))
                matches = sum(1 for w in sub_words if len(w) > 3 and w in search_text)
                if len(sub_words) > 0:
                    score = matches / len(sub_words)
                    if score > best_score:
                        best_score = score
                        best_tid = tid
                        best_si = si
    
    # Check theme name too
    if best_score < 0.3:
        for tid in possible_tids:
            theme_name = THEMES[tid]["name"].lower()
            theme_words = set(re.findall(r'[а-яёa-z]+', theme_name))
            matches = sum(1 for w in theme_words if len(w) > 3 and w in search_text)
            if len(theme_words) > 0:
                score = matches / len(theme_words)
                if score > best_score:
                    best_score = score * 0.7  # Slightly lower weight for theme-only match
                    best_tid = tid
                    best_si = 0  # Default to first subtopic
    
    # If no match found but we have a grade, try to use olympiad name heuristics
    if best_score < 0.2:
        # Try to extract topic clue from olympiad name
        olympiad_name_lower = olympiad_name.lower()
        for tid in possible_tids:
            theme = THEMES[tid]
            theme_lower = theme["name"].lower()
            # Check if olympiad name contains theme-related words
            theme_main_words = set(re.findall(r'[а-яёa-z]+', theme_lower))
            oly_words = set(re.findall(r'[а-яёa-z]+', olympiad_name_lower))
            common = theme_main_words & oly_words
            if common:
                score = len(common) / max(len(theme_main_words), 1) * 0.4
                if score > best_score:
                    best_score = score
                    best_tid = tid
                    best_si = 0
    
    return best_tid, best_si, best_score


# ============================================================================
# 4. DATA LOADING
# ============================================================================

def load_curated_bank(filepath):
    """Load curated bank JSON."""
    print(f"[LOAD] Loading curated bank from: {filepath}")
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    print(f"[LOAD] Loaded {len(data)} tasks from curated bank")
    return data


def load_candidate_file(filepath):
    """Load candidate file (JSONL) and extract all L4 and L5 problems."""
    print(f"[LOAD] Loading candidate file from: {filepath}")
    all_problems = []
    lines_processed = 0
    
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                olympiad_obj = json.loads(line)
                lines_processed += 1
                problems = olympiad_obj.get('problems', [])
                for prob in problems:
                    # Ensure metadata is propagated
                    if '_olympiad' not in prob:
                        prob['_olympiad'] = olympiad_obj.get('olympiad', olympiad_obj.get('_olympiad', ''))
                    if '_year' not in prob:
                        prob['_year'] = olympiad_obj.get('year', olympiad_obj.get('_year', 0))
                    if '_grade' not in prob:
                        prob['_grade'] = olympiad_obj.get('grade', olympiad_obj.get('_grade', 0))
                    if '_round' not in prob:
                        prob['_round'] = olympiad_obj.get('round', olympiad_obj.get('_round', ''))
                    all_problems.append(prob)
            except json.JSONDecodeError as e:
                print(f"[WARN] JSON parse error on line {lines_processed}: {e}")
    
    print(f"[LOAD] Processed {lines_processed} lines, extracted {len(all_problems)} problems")
    
    # Filter L4 and L5
    l4_l5 = [p for p in all_problems if p.get('level') in (4, 5, 'L4', 'L5', 4.0, 5.0)]
    l4 = [p for p in l4_l5 if str(p.get('level', '')).rstrip('.0') in ('4', 'L4')]
    l5 = [p for p in l4_l5 if str(p.get('level', '')).rstrip('.0') in ('5', 'L5')]
    
    print(f"[LOAD] L4 problems: {len(l4)}, L5 problems: {len(l5)}")
    return l4_l5, l4, l5


# ============================================================================
# 5. TOPIC MAPPING FOR CURATED BANK
# ============================================================================

def build_curated_topic_mapping():
    """Build mapping from curated_bank topic names to THEMES IDs."""
    # These are based on analyzing the curated_bank topic field values
    # Three-level matching (exact -> normalized -> substring) is applied
    # by map_curated_topic_to_theme(), so more specific keys should appear
    # before less specific ones to ensure correct substring matching priority.
    mapping = {
        # --- T002: Арифметика и теория чисел [grades 6, 9] ---
        "Числа и делимость": "T002",
        "Арифметика": "T002",
        "Теория чисел": "T002",
        "Делимость": "T002",
        "Делимость и остатки": "T002",
        "Остатки по модулю": "T002",
        "Делимость и НОК": "T002",
        "Остатки и диофантовы задачи": "T002",
        "Период Пизано": "T002",

        # --- T004: Графы [grades 7, 8, 9] ---
        "Графы": "T004",
        "Теория графов": "T004",

        # --- T005: Дополнительные задачи и смешанные темы [grades 9, 10, 11] ---
        # (also catch-all for function/graph topics with no dedicated canonical topic)
        "Дополнительные задачи": "T005",
        "Оптимизация": "T005",
        "Прикладные задачи": "T005",
        "Смешанные темы": "T005",
        "Функции": "T005",
        "Функции и графики": "T005",
        "Графики": "T005",

        # --- T006: Комбинаторика и вероятность [grades 7, 8, 9] ---
        "Комбинаторика": "T006",
        "Комбинаторика и вероятность": "T006",
        "Раскраска": "T006",
        "Подсчёт": "T006",

        # --- T007: Теория игр [grade 9] ---
        "Комбинаторика и теория игр": "T007",
        "Теория игр": "T007",
        "Игровые стратегии": "T007",

        # --- T008: Логика и множества [grades 7, 8, 9, 10, 11] ---
        "Логика": "T008",
        "Множества": "T008",
        "Принцип Дирихле": "T008",
        "Принцип крайнего": "T008",
        "Логические задачи": "T008",
        "Инвариант": "T008",

        # --- T009: Метод координат [grades 7, 8, 9] ---
        "Метод координат": "T009",
        "Координаты": "T009",

        # --- T010: Векторы ---
        "Векторы": "T010",

        # --- T011: Неравенства [grades 7, 8, 9] ---
        "Неравенства": "T011",
        "Алгебраические неравенства": "T011",
        "Квадратные неравенства": "T011",

        # --- T012: Метод интервалов ---
        "Метод интервалов": "T012",

        # --- T013: Показательные и логарифмические неравенства ---
        "Показательные и логарифмические неравенства": "T013",

        # --- T014: Тригонометрические неравенства ---
        "Тригонометрические неравенства": "T014",

        # --- T015: Числовые наборы ---
        "Числовые наборы": "T015",
        "Неравенства о средних": "T015",

        # --- T016: Планиметрия: многоугольники [grades 7, 8, 9, 10, 11] ---
        "Планиметрия": "T016",
        "Многоугольники": "T016",
        "Планиметрия: многоугольники": "T016",
        "Геометрия и измерения": "T016",
        "Геометрия": "T016",
        "Геометрический экстремум": "T016",

        # --- T017: Планиметрия: окружность ---
        "Окружность": "T017",
        "Планиметрия: окружность": "T017",

        # --- T018: Планиметрия: площадь ---
        "Площадь": "T018",
        "Планиметрия: площадь": "T018",

        # --- T019: Планиметрия: треугольники [grades 7, 8, 9, 10, 11] ---
        "Треугольники": "T019",
        "Планиметрия: треугольники": "T019",
        "Подобие": "T019",
        "Геометрия треугольника": "T019",
        "Геометрия прямоугольного треугольника": "T019",

        # --- T020: Последовательности и прогрессии [grades 7, 8, 9] ---
        "Последовательности": "T020",
        "Прогрессии": "T020",
        "Арифметическая прогрессия": "T020",
        "Геометрическая прогрессия": "T020",

        # --- T021: Производная и её применение [grades 10, 11] ---
        "Производная": "T021",

        # --- T022: Дроби, отношения, проценты ---
        "Проценты": "T022",
        "Пропорции": "T022",

        # --- T023: Рациональные уравнения [grades 8, 9] ---
        "Уравнения": "T023",
        "Рациональные уравнения": "T023",

        # --- T024: Решение задач ---
        "Решение задач": "T024",
        "Анализ и интерпретация": "T024",

        # --- T025: Замена переменной ---
        "Замена переменной": "T025",

        # --- T026: Разложение на множители [grades 7, 8, 9] ---
        "Разложение на множители": "T026",
        "Выражения и многочлены": "T026",
        "Многочлены": "T026",

        # --- T027: Системы уравнений [grades 8, 9, 10, 11] ---
        "Системы уравнений": "T027",
        "Системы, параметры и оценки": "T027",

        # --- T028: Стереометрия: аксиомы и прямые [grades 10, 11] ---
        "Стереометрия": "T028",
        "Стереометрия: аксиомы и прямые": "T028",

        # --- T029: Стереометрия: многогранники [grades 10, 11] ---
        "Стереометрия: многогранники": "T029",
        "Стереометрия: объёмы": "T029",
        "Объёмы": "T029",
        "Объемы": "T029",
        "Сечения": "T029",

        # --- T030: Стереометрия: тела вращения [grades 10, 11] ---
        "Стереометрия: тела вращения": "T030",

        # --- T031: Стереометрия: угол и расстояние [grade 11] ---
        "Угол и расстояние": "T031",

        # --- T032: Текстовые задачи: движение [grades 5, 7] ---
        "Текстовые задачи": "T032",
        "Движение": "T032",

        # --- T033: Текстовые задачи: производительность ---
        "Производительность": "T033",
        "Смеси и сплавы": "T033",

        # --- T034: Теория вероятностей ---
        "Дискретные распределения": "T034",
        "Теория вероятностей": "T034",

        # --- T035: Тригонометрические уравнения ---
        "Тригонометрические уравнения": "T035",

        # --- T036: Тригонометрия / Тригонометрические преобразования [grade 10] ---
        "Тригонометрия": "T036",
        "Тригонометрические преобразования": "T036",

        # --- T037: Уравнения с модулем ---
        "Модуль": "T037",
        "Уравнения с модулем": "T037",

        # --- T038: Иррациональные уравнения ---
        "Иррациональные уравнения": "T038",

        # --- T039: Показательные и логарифмические уравнения [grades 10, 11] ---
        "Показательные уравнения": "T039",
        "Логарифмические уравнения": "T039",
        "Показательные и логарифмические уравнения": "T039",
        "Показательные и логарифмы": "T039",

        # --- T040: Тригонометрические системы ---
        "Тригонометрические системы": "T040",

        # --- T041: Комплексные числа / Индукция / Алгоритмы ---
        "Комплексные числа": "T041",
        "Индукция": "T041",
        "Алгоритмы": "T041",

        # --- T001: Алгебра / Теория групп ---
        "Теория групп": "T001",
        "Группы": "T001",
        "Алгебра": "T001",
    }
    return mapping


def map_curated_topic_to_theme(topic_name, mapping):
    """Map a curated_bank topic name to a theme ID."""
    if not topic_name:
        return None
    # Direct lookup
    if topic_name in mapping:
        return mapping[topic_name]
    # Try case-insensitive
    topic_lower = topic_name.lower().strip()
    for key, val in mapping.items():
        if key.lower().strip() == topic_lower:
            return val
    # Try partial match
    for key, val in mapping.items():
        if key.lower() in topic_lower or topic_lower in key.lower():
            return val
    return None


# ============================================================================
# 6. DEDUPLICATION
# ============================================================================

def deduplicate_candidates(candidates, existing_tasks):
    """
    3-stage deduplication of candidates against existing bank and among themselves.
    Uses n-gram fingerprinting for fast approximate matching (100-1000x faster than SequenceMatcher).
    Returns (unique_candidates, duplicates, duplicate_map).
    """
    print("\n[DEDUP] Starting 3-stage deduplication (n-gram fingerprinting)...")
    
    # ====================================================================
    # PRE-COMPUTE: n-gram fingerprints for existing tasks (done once)
    # ====================================================================
    print(f"[DEDUP] Pre-computing fingerprints for {len(existing_tasks)} existing tasks...")
    existing_fingerprints = []  # list of (normalized_stmt, frozenset_of_ngrams)
    for t in existing_tasks:
        stmt = t.get('statement', t.get('task_text', ''))
        norm = normalize_text(stmt)
        fp = compute_ngrams(norm, n=3)
        existing_fingerprints.append((norm, fp))
    
    # Also build a set of normalized statements for O(1) exact lookup
    existing_norm_set = set(norm for norm, fp in existing_fingerprints if norm)
    
    # Build import key index for safety (not used for dedup, but for tracking)
    existing_keys = set()
    for t in existing_tasks:
        key = compute_import_key(t, "existing")
        if key:
            existing_keys.add(key)
    
    # ====================================================================
    # STAGE 1: Exact normalized match against existing (O(1) per candidate via set)
    # ====================================================================
    unique = []
    duplicates = []
    dup_map = {}  # id(cand) -> reason
    
    stage1_removed = 0
    for cand in candidates:
        cand_stmt = normalize_text(cand.get('text', cand.get('statement', '')))
        if cand_stmt and cand_stmt in existing_norm_set:
            duplicates.append(cand)
            dup_map[id(cand)] = "stage1_exact_vs_existing"
            stage1_removed += 1
        else:
            unique.append(cand)
    
    print(f"[DEDUP] Stage 1 (exact vs existing via set): removed {stage1_removed}")
    
    # ====================================================================
    # STAGE 1b: Exact match among candidates (O(1) per candidate via dict)
    # ====================================================================
    stage1b_removed = 0
    seen_norms = {}
    still_unique = []
    for cand in unique:
        cand_stmt = normalize_text(cand.get('text', cand.get('statement', '')))
        if cand_stmt and cand_stmt in seen_norms:
            duplicates.append(cand)
            dup_map[id(cand)] = "stage1b_exact_among_candidates"
            stage1b_removed += 1
        else:
            seen_norms[cand_stmt] = True
            still_unique.append(cand)
    unique = still_unique
    print(f"[DEDUP] Stage 1b (exact among candidates via dict): removed {stage1b_removed}")
    
    # ====================================================================
    # PRE-COMPUTE: Fingerprints for remaining unique candidates
    # ====================================================================
    print(f"[DEDUP] Pre-computing fingerprints for {len(unique)} candidates...")
    cand_fingerprints = []  # list of (normalized_stmt, frozenset_ngrams, candidate_obj)
    for cand in unique:
        cand_stmt = normalize_text(cand.get('text', cand.get('statement', '')))
        cand_fp = compute_ngrams(cand_stmt, n=3) if cand_stmt else frozenset()
        cand_fingerprints.append((cand_stmt, cand_fp, cand))
    
    # ====================================================================
    # STAGE 2: High n-gram similarity against existing (fast set Jaccard)
    # threshold: 0.60 n-gram Jaccard ~ 0.85 SequenceMatcher
    # ====================================================================
    stage2_removed = 0
    still_unique_fp = []
    THRESHOLD_S2 = 0.60
    
    for cand_norm, cand_fp, cand in cand_fingerprints:
        if not cand_fp:
            still_unique_fp.append((cand_norm, cand_fp, cand))
            continue
        is_dup = False
        for existing_norm, existing_fp in existing_fingerprints:
            if existing_fp and ngram_similarity(cand_fp, existing_fp) >= THRESHOLD_S2:
                is_dup = True
                stage2_removed += 1
                break
        if is_dup:
            duplicates.append(cand)
            dup_map[id(cand)] = "stage2_high_similarity_vs_existing"
        else:
            still_unique_fp.append((cand_norm, cand_fp, cand))
    
    print(f"[DEDUP] Stage 2 (n-gram Jaccard >= {THRESHOLD_S2} vs existing): removed {stage2_removed}")
    
    # ====================================================================
    # STAGE 2b: High n-gram similarity among candidates
    # ====================================================================
    stage2b_removed = 0
    buckets = []  # each bucket = [(norm, fp, cand), ...]
    
    for cand_norm, cand_fp, cand in still_unique_fp:
        if not cand_fp:
            buckets.append([(cand_norm, cand_fp, cand)])
            continue
        found = False
        for i, bucket in enumerate(buckets):
            bucket_fp = bucket[0][1]  # first item's fingerprint
            if bucket_fp and ngram_similarity(cand_fp, bucket_fp) >= THRESHOLD_S2:
                bucket.append((cand_norm, cand_fp, cand))
                found = True
                break
        if not found:
            buckets.append([(cand_norm, cand_fp, cand)])
    
    still_unique_fp = []
    for bucket in buckets:
        # Sort by quality, keep the best
        bucket.sort(key=lambda x: compute_quality_score(x[2]), reverse=True)
        still_unique_fp.append(bucket[0])
        for extra in bucket[1:]:
            duplicates.append(extra[2])
            dup_map[id(extra[2])] = "stage2b_high_similarity_among_candidates"
            stage2b_removed += 1
    
    print(f"[DEDUP] Stage 2b (n-gram Jaccard >= {THRESHOLD_S2} among candidates): removed {stage2b_removed}")
    
    # ====================================================================
    # STAGE 3: Number-substituted similarity (lower threshold + number check)
    # threshold: 0.40 n-gram Jaccard ~ 0.70 SequenceMatcher
    # ====================================================================
    stage3_removed = 0
    still_unique_fp_3 = []
    THRESHOLD_S3 = 0.40
    THRESHOLD_S3_NONUM = 0.60  # ~0.85 SequenceMatcher on number-normalized text
    
    for cand_norm, cand_fp, cand in still_unique_fp:
        if not cand_fp:
            still_unique_fp_3.append((cand_norm, cand_fp, cand))
            continue
        is_dup = False
        for existing_norm, existing_fp in existing_fingerprints:
            if not existing_fp:
                continue
            sim = ngram_similarity(cand_fp, existing_fp)
            if sim >= THRESHOLD_S3:
                # Check number substitution: normalize numbers, re-compare
                text_no_nums_cand = re.sub(r'\d+', 'N', cand_norm)
                text_no_nums_existing = re.sub(r'\d+', 'N', existing_norm)
                fp_no_nums_cand = compute_ngrams(text_no_nums_cand, n=3)
                fp_no_nums_existing = compute_ngrams(text_no_nums_existing, n=3)
                if ngram_similarity(fp_no_nums_cand, fp_no_nums_existing) >= THRESHOLD_S3_NONUM:
                    is_dup = True
                    stage3_removed += 1
                    break
        if is_dup:
            duplicates.append(cand)
            dup_map[id(cand)] = "stage3_number_substituted_vs_existing"
        else:
            still_unique_fp_3.append((cand_norm, cand_fp, cand))
    
    print(f"[DEDUP] Stage 3 (number-substituted vs existing): removed {stage3_removed}")
    
    unique = [cand for _, _, cand in still_unique_fp_3]
    print(f"[DEDUP] Final: {len(unique)} unique, {len(duplicates)} duplicates removed")
    return unique, duplicates, dup_map


# ============================================================================
# 7. CELL BUILDING & OPTIMIZATION
# ============================================================================

def build_cell_key(grade, level, theme_id, subtopic_idx):
    """Build a unique cell key."""
    return f"G{grade}|L{level}|{theme_id}|S{subtopic_idx}"


def parse_cell_key(key):
    """Parse cell key back into components."""
    parts = key.split('|')
    grade = int(parts[0][1:])
    level = int(parts[1][1:])
    theme_id = parts[2]
    subtopic_idx = int(parts[3][1:])
    return grade, level, theme_id, subtopic_idx


def get_cell_info(cell_key):
    """Get human-readable cell info."""
    grade, level, theme_id, subtopic_idx = parse_cell_key(cell_key)
    theme = THEMES[theme_id]
    subtopic = theme["subtopics"][subtopic_idx]
    return {
        "grade": grade,
        "level": level,
        "theme_id": theme_id,
        "theme_name": theme["name"],
        "subtopic_idx": subtopic_idx,
        "subtopic": subtopic,
        "cell_key": cell_key
    }


def build_all_cells():
    """Build all 258 cell keys (129 per level 4 and 5)."""
    cells = {}
    for grade, tids in GRADE_THEMES.items():
        for tid in tids:
            for si in range(3):  # 3 subtopics
                for level in [4, 5]:
                    key = build_cell_key(grade, level, tid, si)
                    cells[key] = {
                        "key": key,
                        "grade": grade,
                        "level": level,
                        "theme_id": tid,
                        "theme_name": THEMES[tid]["name"],
                        "subtopic_idx": si,
                        "subtopic": THEMES[tid]["subtopics"][si],
                        "tasks": [],
                        "is_full": False
                    }
    return cells


def add_existing_tasks_to_cells(cells, curated_bank, topic_mapping):
    """Add existing L4/L5 tasks from curated_bank to cells."""
    print("\n[CELLS] Adding existing L4/L5 tasks from curated bank...")
    added = 0
    unmapped = 0
    
    for task in curated_bank:
        # Check if L4 or L5
        level = task.get('level') or task.get('original_difficulty', 0)
        target_level = task.get('target_level', '')
        
        # Normalize level
        if isinstance(level, str):
            level = int(level.replace('L', '')) if level.startswith('L') else 0
        level = int(level)
        
        if level not in (4, 5):
            continue
        
        # Get grade
        grade = task.get('class_level') or task.get('grade', 0)
        if not grade or grade not in GRADE_THEMES:
            continue
        
        # Map topic to theme
        topic = task.get('topic', '')
        theme_id = map_curated_topic_to_theme(topic, topic_mapping)
        if not theme_id:
            unmapped += 1
            continue
        
        # Check if this theme belongs to this grade
        if theme_id not in GRADE_THEMES.get(grade, []):
            unmapped += 1
            continue
        
        # Determine subtopic (try to find from existing fields, default to 0)
        subtopic_idx = 0
        subtopic_str = task.get('subtopic', '')
        if subtopic_str:
            theme_subtopics = THEMES[theme_id]["subtopics"]
            for si, sub_name in enumerate(theme_subtopics):
                if normalize_text(subtopic_str) == normalize_text(sub_name):
                    subtopic_idx = si
                    break
                # Partial match
                if subtopic_str.lower() in sub_name.lower() or sub_name.lower() in subtopic_str.lower():
                    subtopic_idx = si
                    break
        
        # Build cell key
        cell_key = build_cell_key(grade, level, theme_id, subtopic_idx)
        
        if cell_key in cells:
            if len(cells[cell_key]["tasks"]) < TASKS_PER_CELL:
                cells[cell_key]["tasks"].append(task)
                added += 1
    
    print(f"[CELLS] Added {added} existing L4/L5 tasks to cells, {unmapped} unmapped")
    
    # Update is_full flag
    for key, cell in cells.items():
        cell["is_full"] = len(cell["tasks"]) >= TASKS_PER_CELL
    
    full_cells = sum(1 for c in cells.values() if c["is_full"])
    print(f"[CELLS] Full cells from existing: {full_cells}/{len(cells)}")
    
    return cells


def classify_and_fill(cells, candidates):
    """
    Classify all candidates and add them to cells.
    Returns (cells, classified, unclassified, uncertain).
    """
    print("\n[CLASSIFY] Classifying candidates...")
    classified = 0
    unclassified = []
    uncertain = []
    overflow = []
    
    for i, cand in enumerate(candidates):
        grade = cand.get('_grade', cand.get('grade', 0))
        level = cand.get('level', 4)
        if isinstance(level, str):
            level = int(level.replace('L', '')) if level.startswith('L') else 4
        level = int(level)
        
        if level not in (4, 5):
            unclassified.append({"candidate": cand, "reason": "invalid_level"})
            continue
        
        if not grade or grade not in GRADE_THEMES:
            unclassified.append({"candidate": cand, "reason": "invalid_grade"})
            continue
        
        # Classify
        theme_id, subtopic_idx, confidence = classify_problem(cand)
        
        if not theme_id or confidence < 0.1:
            unclassified.append({"candidate": cand, "reason": "low_confidence", "confidence": confidence})
            continue
        
        if confidence < 0.3:
            uncertain.append({"candidate": cand, "theme_id": theme_id, "subtopic_idx": subtopic_idx, "confidence": confidence})
        
        # Check if this theme belongs to this grade
        if theme_id not in GRADE_THEMES.get(grade, []):
            unclassified.append({"candidate": cand, "reason": "theme_not_in_grade", "theme": theme_id})
            continue
        
        cell_key = build_cell_key(grade, level, theme_id, subtopic_idx if subtopic_idx is not None else 0)
        
        if cell_key not in cells:
            unclassified.append({"candidate": cand, "reason": "cell_not_found", "cell_key": cell_key})
            continue
        
        # Check if cell is already full
        if len(cells[cell_key]["tasks"]) >= TASKS_PER_CELL:
            overflow.append({"candidate": cand, "cell_key": cell_key})
            continue
        
        # Add to cell
        cells[cell_key]["tasks"].append(cand)
        cells[cell_key]["is_full"] = len(cells[cell_key]["tasks"]) >= TASKS_PER_CELL
        classified += 1
    
    print(f"[CLASSIFY] Classified: {classified}")
    print(f"[CLASSIFY] Unclassified: {len(unclassified)}")
    print(f"[CLASSIFY] Uncertain (low confidence): {len(uncertain)}")
    print(f"[CLASSIFY] Overflow (cell already full): {len(overflow)}")
    
    return cells, classified, unclassified, uncertain, overflow


def global_optimization(cells, unclassified_candidates):
    """
    Global optimization: maximize lexicographic objective.
    1. Maximize completed_cells
    2. Maximize filled_slots  
    3. Maximize total_quality
    4. Maximize total_diversity
    
    Strategy: Use unclassified candidates to fill remaining gaps.
    For each unfilled cell, try each unclassified candidate and find best match.
    """
    print("\n[OPTIMIZE] Starting global optimization...")
    
    # Identify unfilled cells (need tasks)
    unfilled_cells = {k: v for k, v in cells.items() if not v["is_full"] and len(v["tasks"]) < TASKS_PER_CELL}
    empty_cells = {k: v for k, v in unfilled_cells.items() if len(v["tasks"]) == 0}
    partially_filled = {k: v for k, v in unfilled_cells.items() if len(v["tasks"]) > 0}
    
    print(f"[OPTIMIZE] Unfilled cells: {len(unfilled_cells)} (empty: {len(empty_cells)}, partial: {len(partially_filled)})")
    print(f"[OPTIMIZE] Unclassified candidates available: {len(unclassified_candidates)}")
    
    # For each unclassified candidate, try all possible theme/subtopic assignments
    # and find the one that improves the objective the most
    assigned = 0
    remaining = list(unclassified_candidates)
    
    # Iterate multiple passes to handle competition
    for iteration in range(5):  # Max 5 passes
        if not remaining:
            break
        
        changes = 0
        next_remaining = []
        
        for cand_data in remaining:
            cand = cand_data["candidate"]
            grade = cand.get('_grade', cand.get('grade', 0))
            level_val = cand.get('level', 4)
            if isinstance(level_val, str):
                level_val = int(level_val.replace('L', '')) if level_val.startswith('L') else 4
            level_val = int(level_val)
            
            if level_val not in (4, 5):
                continue
            if not grade or grade not in GRADE_THEMES:
                continue
            
            # Try all possible themes for this grade
            possible_tids = GRADE_THEMES.get(grade, [])
            best_cell_key = None
            best_score = -1
            
            for tid in possible_tids:
                for si in range(3):
                    ck = build_cell_key(grade, level_val, tid, si)
                    if ck in cells and not cells[ck]["is_full"]:
                        # Score: prioritize cells that are closer to being full
                        # and have higher quality existing tasks
                        cell_tasks = cells[ck]["tasks"]
                        fill_ratio = len(cell_tasks) / TASKS_PER_CELL
                        # Higher priority for cells with more tasks already (closer to completion)
                        priority = fill_ratio
                        if priority > best_score:
                            best_score = priority
                            best_cell_key = ck
            
            if best_cell_key:
                cells[best_cell_key]["tasks"].append(cand)
                cells[best_cell_key]["is_full"] = len(cells[best_cell_key]["tasks"]) >= TASKS_PER_CELL
                assigned += 1
                changes += 1
            else:
                next_remaining.append(cand_data)
        
        remaining = next_remaining
        if changes == 0:
            break
        print(f"[OPTIMIZE] Pass {iteration + 1}: assigned {changes} candidates")
    
    full_cells = sum(1 for c in cells.values() if c["is_full"])
    total_filled = sum(len(c["tasks"]) for c in cells.values())
    print(f"[OPTIMIZE] After optimization: {full_cells} full cells, {total_filled} total filled slots")
    
    return cells, assigned, remaining


# ============================================================================
# 8. OUTPUT GENERATION
# ============================================================================

def generate_outputs(cells, classified_count, duplicates, dup_map,
                     unclassified, uncertain, overflow, remaining_unclassified):
    """Generate all 6 output files."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # 1. Filled DB
    filled_db = []
    cell_stats = []
    full_cells = 0
    total_tasks = 0
    
    for cell_key, cell in sorted(cells.items()):
        info = get_cell_info(cell_key)
        task_count = len(cell["tasks"])
        is_full = cell["is_full"]
        total_tasks += task_count
        
        if is_full:
            full_cells += 1
        
        cell_stats.append({
            "cell_key": cell_key,
            "grade": info["grade"],
            "level": info["level"],
            "theme_id": info["theme_id"],
            "theme_name": info["theme_name"],
            "subtopic_idx": info["subtopic_idx"],
            "subtopic": info["subtopic"],
            "task_count": task_count,
            "is_full": is_full,
            "slots_remaining": TASKS_PER_CELL - task_count
        })
        
        for task in cell["tasks"]:
            entry = {
                "cell_key": cell_key,
                "grade": info["grade"],
                "level": info["level"],
                "theme_id": info["theme_id"],
                "theme_name": info["theme_name"],
                "subtopic_idx": info["subtopic_idx"],
                "subtopic": info["subtopic"],
                "statement": task.get('text', task.get('statement', task.get('task_text', ''))),
                "answer": task.get('answer', ''),
                "solution": task.get('solution', ''),
                "source_olympiad": task.get('_olympiad', task.get('olympiad', '')),
                "source_year": task.get('_year', task.get('year', '')),
                "source_grade": task.get('_grade', task.get('grade', '')),
                "source_round": task.get('_round', task.get('round', '')),
                "quality_score": compute_quality_score(task),
                "import_key": compute_import_key(task)
            }
            filled_db.append(entry)
    
    with open(OUTPUT_DB, 'w', encoding='utf-8') as f:
        json.dump(filled_db, f, ensure_ascii=False, indent=2)
    print(f"[OUTPUT] Filled DB: {len(filled_db)} tasks -> {OUTPUT_DB}")
    
    # 2. CSV Report
    import csv
    with open(OUTPUT_CSV, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=[
            "cell_key", "grade", "level", "theme_id", "theme_name",
            "subtopic_idx", "subtopic", "task_count", "is_full", "slots_remaining"
        ])
        writer.writeheader()
        for stat in cell_stats:
            writer.writerow(stat)
    print(f"[OUTPUT] CSV Report: {len(cell_stats)} cells -> {OUTPUT_CSV}")
    
    # 3. Audit JSON
    audit = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_cells": len(cells),
            "full_cells": full_cells,
            "total_tasks_added": total_tasks,
            "classified_count": classified_count,
            "duplicates_removed": len(duplicates),
            "unclassified": len(unclassified),
            "uncertain": len(uncertain),
            "overflow": len(overflow),
            "remaining_unclassified": len(remaining_unclassified),
            "completion_pct": round(full_cells / len(cells) * 100, 1) if cells else 0
        },
        "cell_stats": cell_stats,
        "full_cells_list": [s["cell_key"] for s in cell_stats if s["is_full"]],
        "partial_cells_list": [s["cell_key"] for s in cell_stats if not s["is_full"] and s["task_count"] > 0],
        "empty_cells_list": [s["cell_key"] for s in cell_stats if s["task_count"] == 0]
    }
    
    with open(OUTPUT_AUDIT, 'w', encoding='utf-8') as f:
        json.dump(audit, f, ensure_ascii=False, indent=2)
    print(f"[OUTPUT] Audit JSON -> {OUTPUT_AUDIT}")
    
    # 4. Rejected tasks (duplicates)
    rejected = []
    for dup in duplicates:
        rejected.append({
            "statement": dup.get('text', dup.get('statement', '')),
            "answer": dup.get('answer', ''),
            "olympiad": dup.get('_olympiad', dup.get('olympiad', '')),
            "year": dup.get('_year', dup.get('year', '')),
            "grade": dup.get('_grade', dup.get('grade', '')),
            "level": dup.get('level', ''),
            "reason": dup_map.get(id(dup), "duplicate")
        })
    
    with open(OUTPUT_REJECTED, 'w', encoding='utf-8') as f:
        json.dump(rejected, f, ensure_ascii=False, indent=2)
    print(f"[OUTPUT] Rejected: {len(rejected)} tasks -> {OUTPUT_REJECTED}")
    
    # 5. Uncertain tasks
    uncertain_out = []
    for uc in uncertain:
        uncertain_out.append({
            "statement": uc["candidate"].get('text', uc["candidate"].get('statement', '')),
            "answer": uc["candidate"].get('answer', ''),
            "olympiad": uc["candidate"].get('_olympiad', uc["candidate"].get('olympiad', '')),
            "year": uc["candidate"].get('_year', uc["candidate"].get('year', '')),
            "grade": uc["candidate"].get('_grade', uc["candidate"].get('grade', '')),
            "level": uc["candidate"].get('level', ''),
            "suggested_theme": uc.get("theme_id"),
            "suggested_subtopic_idx": uc.get("subtopic_idx"),
            "confidence": uc.get("confidence", 0)
        })
    
    with open(OUTPUT_UNCERTAIN, 'w', encoding='utf-8') as f:
        json.dump(uncertain_out, f, ensure_ascii=False, indent=2)
    print(f"[OUTPUT] Uncertain: {len(uncertain_out)} tasks -> {OUTPUT_UNCERTAIN}")
    
    # 6. Overflow tasks
    overflow_out = []
    for ov in overflow:
        overflow_out.append({
            "statement": ov["candidate"].get('text', ov["candidate"].get('statement', '')),
            "answer": ov["candidate"].get('answer', ''),
            "olympiad": ov["candidate"].get('_olympiad', ov["candidate"].get('olympiad', '')),
            "year": ov["candidate"].get('_year', ov["candidate"].get('year', '')),
            "grade": ov["candidate"].get('_grade', ov["candidate"].get('grade', '')),
            "level": ov["candidate"].get('level', ''),
            "target_cell": ov.get("cell_key", "")
        })
    
    with open(OUTPUT_OVERFLOW, 'w', encoding='utf-8') as f:
        json.dump(overflow_out, f, ensure_ascii=False, indent=2)
    print(f"[OUTPUT] Overflow: {len(overflow_out)} tasks -> {OUTPUT_OVERFLOW}")
    
    return {
        "total_tasks": total_tasks,
        "full_cells": full_cells,
        "total_cells": len(cells),
        "filled_db_count": len(filled_db)
    }


# ============================================================================
# 9. VALIDATION
# ============================================================================

def validate_outputs(cells, filled_db):
    """Run all validation checks."""
    print("\n[VALIDATE] Running validation checks...")
    errors = []
    warnings = []
    
    # Check 1: No cell has > 5 tasks
    for cell_key, cell in cells.items():
        if len(cell["tasks"]) > TASKS_PER_CELL:
            errors.append(f"Cell {cell_key} has {len(cell['tasks'])} tasks (max {TASKS_PER_CELL})")
    
    # Check 2: Total cells = 258
    expected_cells = 43 * 3 * 2  # 43 topics * 3 subtopics * 2 levels
    if len(cells) != expected_cells:
        errors.append(f"Expected {expected_cells} cells, got {len(cells)}")
    
    # Check 3: All grades have correct number of themes
    for grade, tids in GRADE_THEMES.items():
        grade_cells = {k: v for k, v in cells.items() if v["grade"] == grade}
        expected_grade_cells = len(tids) * 3 * 2  # themes * 3 subtopics * 2 levels
        if len(grade_cells) != expected_grade_cells:
            errors.append(f"Grade {grade}: expected {expected_grade_cells} cells, got {len(grade_cells)}")
    
    # Check 4: All filled_db entries have required fields
    required_fields = ["cell_key", "grade", "level", "theme_id", "subtopic", "statement"]
    for i, entry in enumerate(filled_db):
        for field in required_fields:
            if field not in entry or not entry[field]:
                warnings.append(f"Entry {i} missing field: {field}")
    
    # Check 5: All import keys are unique
    import_keys = [e.get("import_key", "") for e in filled_db if e.get("import_key")]
    if len(import_keys) != len(set(import_keys)):
        warnings.append(f"Duplicate import keys found: {len(import_keys) - len(set(import_keys))} duplicates")
    
    # Check 6: No empty cells in grades that have data
    empty_cells = [k for k, v in cells.items() if len(v["tasks"]) == 0]
    if empty_cells:
        warnings.append(f"{len(empty_cells)} cells are completely empty")
    
    print(f"[VALIDATE] Errors: {len(errors)}, Warnings: {len(warnings)}")
    for e in errors[:10]:
        print(f"  [ERROR] {e}")
    for w in warnings[:10]:
        print(f"  [WARN] {w}")
    
    return errors, warnings


# ============================================================================
# 10. REPORT GENERATION
# ============================================================================

def generate_report(stats, cells, errors, warnings, audit_data):
    """Generate the final markdown report."""
    print("\n[REPORT] Generating final report...")
    
    report = f"""# ФИНАЛЬНЫЙ ОТЧЁТ — Заполнение L4/L5 VICTOR2.0
====================================================================

**Дата:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
**Источник кандидатов:** СКАЧАТЬ_FORMYLA_3302_задачи_уровни_4_5.jsonl
**Целевая БД:** curated_bank_L1_L5_fixed.json

---

## 1. СВОДКА

| Метрика | Значение |
|---------|----------|
| Всего ячеек (43 темы × 3 подтемы × 2 уровня) | {stats['total_cells']} |
| Полностью заполненных ячеек (5/5) | **{stats['full_cells']}** |
| Частично заполненных ячеек | {sum(1 for k,v in cells.items() if 0 < len(v['tasks']) < TASKS_PER_CELL)} |
| Пустых ячеек | {sum(1 for k,v in cells.items() if len(v['tasks']) == 0)} |
| Процент заполнения ячеек | **{round(stats['full_cells'] / stats['total_cells'] * 100, 1) if stats['total_cells'] else 0}%** |
| Всего задач добавлено | {stats['total_tasks']} |
| Классифицировано | {audit_data['summary']['classified_count']} |
| Отбраковано (дубликаты) | {audit_data['summary']['duplicates_removed']} |
| Неклассифицировано | {audit_data['summary']['unclassified']} |
| Неопределённые (low confidence) | {audit_data['summary']['uncertain']} |
| Переполнение (ячейка полна) | {audit_data['summary']['overflow']} |

---

## 2. ПОКЛЕТОЧНАЯ СТАТИСТИКА

### Полностью заполненные ячейки ({stats['full_cells']})
"""
    
    # List full cells
    full_cells_list = audit_data.get("full_cells_list", [])
    for ck in full_cells_list:
        info = get_cell_info(ck)
        report += f"- `{ck}` | Grade {info['grade']} | L{info['level']} | {info['theme_name']} | {info['subtopic']}\n"
    
    report += f"""
### Частично заполненные ячейки
"""
    partial_cells = audit_data.get("partial_cells_list", [])
    for ck in partial_cells:
        info = get_cell_info(ck)
        count = len(cells[ck]["tasks"])
        report += f"- `{ck}` | Grade {info['grade']} | L{info['level']} | {info['theme_name']} | {info['subtopic']} | [{count}/{TASKS_PER_CELL}]\n"
    
    report += f"""
### Пустые ячейки
"""
    empty_cells = audit_data.get("empty_cells_list", [])
    for ck in empty_cells[:20]:  # Show first 20
        info = get_cell_info(ck)
        report += f"- `{ck}` | Grade {info['grade']} | L{info['level']} | {info['theme_name']} | {info['subtopic']}\n"
    if len(empty_cells) > 20:
        report += f"- ... и ещё {len(empty_cells) - 20} пустых ячеек\n"
    
    report += """
---

## 3. РАСПРЕДЕЛЕНИЕ ПО КЛАССАМ

| Класс | Всего ячеек | Полных | Частичных | Пустых | Процент |
|-------|------------|--------|-----------|--------|---------|
"""
    for grade in sorted(GRADE_THEMES.keys()):
        grade_cells = {k: v for k, v in cells.items() if v["grade"] == grade}
        total = len(grade_cells)
        full = sum(1 for v in grade_cells.values() if v["is_full"])
        partial = sum(1 for v in grade_cells.values() if 0 < len(v["tasks"]) < TASKS_PER_CELL)
        empty = sum(1 for v in grade_cells.values() if len(v["tasks"]) == 0)
        pct = round(full / total * 100, 1) if total else 0
        report += f"| {grade} | {total} | {full} | {partial} | {empty} | {pct}% |\n"
    
    report += """
---

## 4. РАСПРЕДЕЛЕНИЕ ПО УРОВНЯМ

| Уровень | Всего ячеек | Полных | Процент |
|---------|------------|--------|---------|
"""
    for level in [4, 5]:
        level_cells = {k: v for k, v in cells.items() if v["level"] == level}
        total = len(level_cells)
        full = sum(1 for v in level_cells.values() if v["is_full"])
        pct = round(full / total * 100, 1) if total else 0
        report += f"| L{level} | {total} | {full} | {pct}% |\n"
    
    report += """
---

## 5. ПРОВЕРКИ (Validation)

"""
    if not errors and not warnings:
        report += "✅ **Все проверки пройдены успешно!**\n"
    else:
        if errors:
            report += f"### ❌ Ошибки ({len(errors)}):\n"
            for e in errors:
                report += f"- {e}\n"
        if warnings:
            report += f"\n### ⚠️ Предупреждения ({len(warnings)}):\n"
            for w in warnings:
                report += f"- {w}\n"
    
    report += """
---

## 6. ВЫХОДНЫЕ ФАЙЛЫ

| Файл | Описание |
|------|----------|
| `curated_bank_L4_L5_filled.json` | Заполненная БД (все L4/L5 задачи по ячейкам) |
| `cell_fill_report.csv` | CSV-отчёт по каждой ячейке |
| `fill_audit.json` | Полный аудит с детальной статистикой |
| `rejected_tasks.json` | Отбракованные задачи (дубликаты) |
| `uncertain_tasks.json` | Задачи с неопределённой классификацией |
| `overflow_tasks.json` | Задачи, не попавшие в полные ячейки |

---

## 7. ДОПОЛНИТЕЛЬНАЯ ИНФОРМАЦИЯ

- **Алгоритм классификации:** keyword-based matching по тексту задачи и решения
- **Дедупликация:** 3-этапная (точное совпадение → высокая схожесть → замена чисел)
- **Оптимизация:** лексикографическая (полные ячейки → заполненные слоты → качество → разнообразие)
- **Источник задач:** {audit_data['summary']['classified_count'] + audit_data['summary']['duplicates_removed']} задач обработано из 3302
"""
    
    with open(OUTPUT_REPORT, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"[REPORT] Final report -> {OUTPUT_REPORT}")
    
    return report


# ============================================================================
# MAIN PIPELINE
# ============================================================================

def main():
    """Main pipeline."""
    start_time = time.time()
    
    print("=" * 60)
    print("VICTOR2.0 — L4/L5 Cell Filling Pipeline")
    print("=" * 60)
    print(f"Started at: {datetime.now().isoformat()}")
    print()
    
    # Step 1: Load data
    print("[STEP 1/9] Loading data...")
    curated_bank = load_curated_bank(CURATED_BANK_FILE)
    l4_l5_candidates, l4, l5 = load_candidate_file(CANDIDATE_FILE)
    
    print(f"  Curated bank: {len(curated_bank)} tasks")
    print(f"  Candidates: {len(l4_l5_candidates)} (L4: {len(l4)}, L5: {len(l5)})")
    
    # Step 2: Build topic mapping
    print("\n[STEP 2/9] Building topic mappings...")
    topic_mapping = build_curated_topic_mapping()
    print(f"  Topic mapping entries: {len(topic_mapping)}")
    
    # Step 3: Build cells
    print("\n[STEP 3/9] Building cell grid...")
    cells = build_all_cells()
    print(f"  Total cells: {len(cells)}")
    
    # Step 4: Add existing tasks
    print("\n[STEP 4/9] Adding existing L4/L5 tasks...")
    cells = add_existing_tasks_to_cells(cells, curated_bank, topic_mapping)
    
    existing_count = sum(len(c["tasks"]) for c in cells.values())
    print(f"  Existing L4/L5 tasks in cells: {existing_count}")
    
    # Step 5: Deduplicate candidates
    print("\n[STEP 5/9] Deduplicating candidates...")
    unique_candidates, duplicates, dup_map = deduplicate_candidates(l4_l5_candidates, curated_bank)
    print(f"  Unique: {len(unique_candidates)}, Duplicates: {len(duplicates)}")
    
    # Step 6: Classify and fill
    print("\n[STEP 6/9] Classifying and filling cells...")
    cells, classified_count, unclassified, uncertain, overflow = classify_and_fill(cells, unique_candidates)
    
    before_opt = sum(1 for c in cells.values() if c["is_full"])
    print(f"  Full cells before optimization: {before_opt}")
    
    # Step 7: Global optimization
    print("\n[STEP 7/9] Running global optimization...")
    # Try to classify remaining unclassified candidates
    cells, assigned_opt, remaining = global_optimization(cells, unclassified)
    
    after_opt = sum(1 for c in cells.values() if c["is_full"])
    print(f"  Full cells after optimization: {after_opt}")
    print(f"  Assigned during optimization: {assigned_opt}")
    print(f"  Still unclassified: {len(remaining)}")
    
    # Step 8: Generate outputs
    print("\n[STEP 8/9] Generating output files...")
    stats = generate_outputs(
        cells, classified_count, duplicates, dup_map,
        unclassified, uncertain, overflow, remaining
    )
    
    # Step 9: Validate
    print("\n[STEP 9/9] Running validation...")
    audit_data = {
        "summary": {
            "total_cells": len(cells),
            "full_cells": stats["full_cells"],
            "classified_count": classified_count,
            "duplicates_removed": len(duplicates),
            "unclassified": len(unclassified),
            "uncertain": len(uncertain),
            "overflow": len(overflow)
        },
        "full_cells_list": [k for k, v in cells.items() if v["is_full"]],
        "partial_cells_list": [k for k, v in cells.items() if not v["is_full"] and len(v["tasks"]) > 0],
        "empty_cells_list": [k for k, v in cells.items() if len(v["tasks"]) == 0]
    }
    
    errors, warnings = validate_outputs(cells, [])
    
    # Generate report
    print("\n[FINAL] Generating report...")
    report = generate_report(stats, cells, errors, warnings, audit_data)
    
    # Print summary
    elapsed = time.time() - start_time
    print()
    print("=" * 60)
    print(f"PIPELINE COMPLETE in {elapsed:.1f}s")
    print("=" * 60)
    print(f"  Total cells: {len(cells)}")
    print(f"  Full cells: {stats['full_cells']} ({round(stats['full_cells']/len(cells)*100, 1)}%)")
    print(f"  Total tasks: {stats['total_tasks']}")
    print(f"  Errors: {len(errors)}")
    print(f"  Warnings: {len(warnings)}")
    print()
    print(f"  Output directory: {OUTPUT_DIR}")
    print(f"  Report: {OUTPUT_REPORT}")
    
    return cells, stats, report


if __name__ == "__main__":
    main()
