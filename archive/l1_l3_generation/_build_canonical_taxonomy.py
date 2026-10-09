#!/usr/bin/env python
"""Build canonical taxonomy files from authoritative user specification.

Generates:
  - canonical_taxonomy.json  (full structured taxonomy)
  - canonical_taxonomy.csv   (flat table)
  - canonical_taxonomy_audit.json (invariant checks + SHA-256)
"""

import json, csv, hashlib, os, sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ═══════════════════════════════════════════════════════════════════
# AUTHORITATIVE TAXONOMY — directly from user specification
# 43 topics (T001–T043), each with exactly 3 subtopics (S0, S1, S2)
# ═══════════════════════════════════════════════════════════════════

TOPICS = [
    {
        "order": 1, "topic_id": "T001", "topic_name": "Алгебра: теория групп",
        "subtopics": [
            {"order": 1, "subtopic_id": "S0", "subtopic_name": "Группы: определения и примеры"},
            {"order": 2, "subtopic_id": "S1", "subtopic_name": "Группы: подгруппы, смежные классы"},
            {"order": 3, "subtopic_id": "S2", "subtopic_name": "Гомоморфизмы и факторгруппы"},
        ]
    },
    {
        "order": 2, "topic_id": "T002", "topic_name": "Арифметика и теория чисел",
        "subtopics": [
            {"order": 1, "subtopic_id": "S0", "subtopic_name": "Делимость и остатки"},
            {"order": 2, "subtopic_id": "S1", "subtopic_name": "НОД, НОК, алгоритм Евклида"},
            {"order": 3, "subtopic_id": "S2", "subtopic_name": "Сравнения по модулю (a \u2261 b mod n)"},
        ]
    },
    {
        "order": 3, "topic_id": "T003", "topic_name": "Графы: основные понятия",
        "subtopics": [
            {"order": 1, "subtopic_id": "S0", "subtopic_name": "Графы: определения, изоморфизм"},
            {"order": 2, "subtopic_id": "S1", "subtopic_name": "Маршруты, цепи, циклы, Эйлеровы графы"},
            {"order": 3, "subtopic_id": "S2", "subtopic_name": "Связность и компоненты связности"},
        ]
    },
    {
        "order": 4, "topic_id": "T004", "topic_name": "Дополнительные задачи и смешанные темы",
        "subtopics": [
            {"order": 1, "subtopic_id": "S0", "subtopic_name": "Задачи на оптимизацию"},
            {"order": 2, "subtopic_id": "S1", "subtopic_name": "Комбинированные задачи (алгебра + геометрия)"},
            {"order": 3, "subtopic_id": "S2", "subtopic_name": "Задачи на составление уравнений по условию"},
        ]
    },
    {
        "order": 5, "topic_id": "T005", "topic_name": "Комбинаторика и теория игр",
        "subtopics": [
            {"order": 1, "subtopic_id": "S0", "subtopic_name": "Выигрышные и проигрышные позиции"},
            {"order": 2, "subtopic_id": "S1", "subtopic_name": "Игры с симметричной стратегией"},
            {"order": 3, "subtopic_id": "S2", "subtopic_name": "Стратегия и анализ игр"},
        ]
    },
    {
        "order": 6, "topic_id": "T006", "topic_name": "Комбинаторика: счётные техники",
        "subtopics": [
            {"order": 1, "subtopic_id": "S0", "subtopic_name": "Перестановки и факториалы"},
            {"order": 2, "subtopic_id": "S1", "subtopic_name": "Правила сложения и умножения в комбинаторике"},
            {"order": 3, "subtopic_id": "S2", "subtopic_name": "Размещения и сочетания"},
        ]
    },
    {
        "order": 7, "topic_id": "T007", "topic_name": "Логика и множества",
        "subtopics": [
            {"order": 1, "subtopic_id": "S0", "subtopic_name": "Высказывания и предикаты"},
            {"order": 2, "subtopic_id": "S1", "subtopic_name": "Логические операции и таблицы истинности"},
            {"order": 3, "subtopic_id": "S2", "subtopic_name": "Множества и операции над ними"},
        ]
    },
    {
        "order": 8, "topic_id": "T008", "topic_name": "Метод координат: декартовы координаты",
        "subtopics": [
            {"order": 1, "subtopic_id": "S0", "subtopic_name": "Координаты на прямой и плоскости"},
            {"order": 2, "subtopic_id": "S1", "subtopic_name": "Расстояние между точками, середина отрезка"},
            {"order": 3, "subtopic_id": "S2", "subtopic_name": "Уравнения прямых и окружностей"},
        ]
    },
    {
        "order": 9, "topic_id": "T009", "topic_name": "Метод координат: векторы",
        "subtopics": [
            {"order": 1, "subtopic_id": "S0", "subtopic_name": "Векторы: сложение, умножение на число"},
            {"order": 2, "subtopic_id": "S1", "subtopic_name": "Координаты вектора, связь с точками"},
            {"order": 3, "subtopic_id": "S2", "subtopic_name": "Скалярное произведение векторов"},
        ]
    },
    {
        "order": 10, "topic_id": "T010", "topic_name": "Неравенства: алгебраические неравенства",
        "subtopics": [
            {"order": 1, "subtopic_id": "S0", "subtopic_name": "Доказательство неравенств"},
            {"order": 2, "subtopic_id": "S1", "subtopic_name": "Квадратные неравенства"},
            {"order": 3, "subtopic_id": "S2", "subtopic_name": "Неравенства с модулем"},
        ]
    },
    {
        "order": 11, "topic_id": "T011", "topic_name": "Неравенства: метод интервалов и рациональные",
        "subtopics": [
            {"order": 1, "subtopic_id": "S0", "subtopic_name": "Дробно-рациональные неравенства"},
            {"order": 2, "subtopic_id": "S1", "subtopic_name": "Иррациональные неравенства"},
            {"order": 3, "subtopic_id": "S2", "subtopic_name": "Метод интервалов для рациональных неравенств"},
        ]
    },
    {
        "order": 12, "topic_id": "T012", "topic_name": "Неравенства: показательные и логарифмические",
        "subtopics": [
            {"order": 1, "subtopic_id": "S0", "subtopic_name": "Логарифмические неравенства"},
            {"order": 2, "subtopic_id": "S1", "subtopic_name": "Показательные неравенства"},
            {"order": 3, "subtopic_id": "S2", "subtopic_name": "Системы показательных и логарифмических неравенств"},
        ]
    },
    {
        "order": 13, "topic_id": "T013", "topic_name": "Неравенства: тригонометрические",
        "subtopics": [
            {"order": 1, "subtopic_id": "S0", "subtopic_name": "Неравенства с обратными тригонометрическими функциями"},
            {"order": 2, "subtopic_id": "S1", "subtopic_name": "Простейшие тригонометрические неравенства с sin, cos"},
            {"order": 3, "subtopic_id": "S2", "subtopic_name": "Простейшие тригонометрические неравенства с tg, ctg"},
        ]
    },
    {
        "order": 14, "topic_id": "T014", "topic_name": "Неравенства: числовые наборы",
        "subtopics": [
            {"order": 1, "subtopic_id": "S0", "subtopic_name": "Неравенства о среднем арифметическом и среднем геометрическом"},
            {"order": 2, "subtopic_id": "S1", "subtopic_name": "Неравенство Чебышева для числовых наборов"},
            {"order": 3, "subtopic_id": "S2", "subtopic_name": "Цепочки неравенств, взвешенные средние"},
        ]
    },
    {
        "order": 15, "topic_id": "T015", "topic_name": "Планиметрия: многоугольники",
        "subtopics": [
            {"order": 1, "subtopic_id": "S0", "subtopic_name": "Многоугольники: виды, свойства"},
            {"order": 2, "subtopic_id": "S1", "subtopic_name": "Параллелограммы и трапеции"},
            {"order": 3, "subtopic_id": "S2", "subtopic_name": "Треугольники: виды, свойства"},
        ]
    },
    {
        "order": 16, "topic_id": "T016", "topic_name": "Планиметрия: окружность",
        "subtopics": [
            {"order": 1, "subtopic_id": "S0", "subtopic_name": "Вписанные углы и их свойства"},
            {"order": 2, "subtopic_id": "S1", "subtopic_name": "Длина окружности, площадь круга и сектора"},
            {"order": 3, "subtopic_id": "S2", "subtopic_name": "Касательные и секущие к окружности"},
        ]
    },
    {
        "order": 17, "topic_id": "T017", "topic_name": "Планиметрия: площадь",
        "subtopics": [
            {"order": 1, "subtopic_id": "S0", "subtopic_name": "Площади подобных фигур"},
            {"order": 2, "subtopic_id": "S1", "subtopic_name": "Площадь многоугольников (через разбиение и дополнение)"},
            {"order": 3, "subtopic_id": "S2", "subtopic_name": "Формулы площади треугольника и четырёхугольника"},
        ]
    },
    {
        "order": 18, "topic_id": "T018", "topic_name": "Планиметрия: треугольники",
        "subtopics": [
            {"order": 1, "subtopic_id": "S0", "subtopic_name": "Подобие треугольников"},
            {"order": 2, "subtopic_id": "S1", "subtopic_name": "Признаки равенства треугольников"},
            {"order": 3, "subtopic_id": "S2", "subtopic_name": "Теорема Пифагора"},
        ]
    },
    {
        "order": 19, "topic_id": "T019", "topic_name": "Последовательности и прогрессии",
        "subtopics": [
            {"order": 1, "subtopic_id": "S0", "subtopic_name": "Арифметическая прогрессия"},
            {"order": 2, "subtopic_id": "S1", "subtopic_name": "Геометрическая прогрессия"},
            {"order": 3, "subtopic_id": "S2", "subtopic_name": "Суммы последовательностей"},
        ]
    },
    {
        "order": 20, "topic_id": "T020", "topic_name": "Производная и её применение",
        "subtopics": [
            {"order": 1, "subtopic_id": "S0", "subtopic_name": "Геометрический смысл производной"},
            {"order": 2, "subtopic_id": "S1", "subtopic_name": "Исследование функций с помощью производной"},
            {"order": 3, "subtopic_id": "S2", "subtopic_name": "Правила и формулы дифференцирования"},
        ]
    },
    {
        "order": 21, "topic_id": "T021", "topic_name": "Проценты, отношения и пропорции",
        "subtopics": [
            {"order": 1, "subtopic_id": "S0", "subtopic_name": "Задачи на проценты"},
            {"order": 2, "subtopic_id": "S1", "subtopic_name": "Пропорции и отношения"},
            {"order": 3, "subtopic_id": "S2", "subtopic_name": "Прямая и обратная пропорциональность"},
        ]
    },
    {
        "order": 22, "topic_id": "T022", "topic_name": "Рациональные уравнения и неравенства",
        "subtopics": [
            {"order": 1, "subtopic_id": "S0", "subtopic_name": "Дробно-рациональные уравнения"},
            {"order": 2, "subtopic_id": "S1", "subtopic_name": "Метод замены переменной в рациональных уравнениях"},
            {"order": 3, "subtopic_id": "S2", "subtopic_name": "Целые рациональные уравнения (линейные и квадратные)"},
        ]
    },
    {
        "order": 23, "topic_id": "T023", "topic_name": "Решение задач: анализ и интерпретация",
        "subtopics": [
            {"order": 1, "subtopic_id": "S0", "subtopic_name": "Оценка и прикидка"},
            {"order": 2, "subtopic_id": "S1", "subtopic_name": "Проверка решения и поиск ошибок"},
            {"order": 3, "subtopic_id": "S2", "subtopic_name": "Составление плана решения"},
        ]
    },
    {
        "order": 24, "topic_id": "T024", "topic_name": "Решение уравнений: методы замены",
        "subtopics": [
            {"order": 1, "subtopic_id": "S0", "subtopic_name": "Замена переменной (подстановка)"},
            {"order": 2, "subtopic_id": "S1", "subtopic_name": "Использование симметрии"},
            {"order": 3, "subtopic_id": "S2", "subtopic_name": "Сведение к системе уравнений"},
        ]
    },
    {
        "order": 25, "topic_id": "T025", "topic_name": "Решение уравнений: разложение на множители",
        "subtopics": [
            {"order": 1, "subtopic_id": "S0", "subtopic_name": "Вынесение общего множителя и группировка"},
            {"order": 2, "subtopic_id": "S1", "subtopic_name": "Использование формул сокращённого умножения"},
            {"order": 3, "subtopic_id": "S2", "subtopic_name": "Разложение квадратного трёхчлена"},
        ]
    },
    {
        "order": 26, "topic_id": "T026", "topic_name": "Системы уравнений",
        "subtopics": [
            {"order": 1, "subtopic_id": "S0", "subtopic_name": "Графический метод решения систем"},
            {"order": 2, "subtopic_id": "S1", "subtopic_name": "Метод подстановки"},
            {"order": 3, "subtopic_id": "S2", "subtopic_name": "Системы линейных уравнений"},
        ]
    },
    {
        "order": 27, "topic_id": "T027", "topic_name": "Стереометрия: аксиомы и прямые",
        "subtopics": [
            {"order": 1, "subtopic_id": "S0", "subtopic_name": "Аксиомы стереометрии"},
            {"order": 2, "subtopic_id": "S1", "subtopic_name": "Взаимное расположение прямых в пространстве"},
            {"order": 3, "subtopic_id": "S2", "subtopic_name": "Параллельность прямых и плоскостей"},
        ]
    },
    {
        "order": 28, "topic_id": "T028", "topic_name": "Стереометрия: многогранники",
        "subtopics": [
            {"order": 1, "subtopic_id": "S0", "subtopic_name": "Параллелепипеды, призмы"},
            {"order": 2, "subtopic_id": "S1", "subtopic_name": "Пирамиды"},
            {"order": 3, "subtopic_id": "S2", "subtopic_name": "Правильные многогранники"},
        ]
    },
    {
        "order": 29, "topic_id": "T029", "topic_name": "Стереометрия: объёмы и сечения",
        "subtopics": [
            {"order": 1, "subtopic_id": "S0", "subtopic_name": "Сечения многогранников"},
            {"order": 2, "subtopic_id": "S1", "subtopic_name": "Объём многогранников"},
            {"order": 3, "subtopic_id": "S2", "subtopic_name": "Объём тел вращения"},
        ]
    },
    {
        "order": 30, "topic_id": "T030", "topic_name": "Стереометрия: тела вращения",
        "subtopics": [
            {"order": 1, "subtopic_id": "S0", "subtopic_name": "Конус, цилиндр"},
            {"order": 2, "subtopic_id": "S1", "subtopic_name": "Сфера, шар"},
            {"order": 3, "subtopic_id": "S2", "subtopic_name": "Тела вращения: сечения, комбинации"},
        ]
    },
    {
        "order": 31, "topic_id": "T031", "topic_name": "Стереометрия: угол и расстояние",
        "subtopics": [
            {"order": 1, "subtopic_id": "S0", "subtopic_name": "Расстояние от точки до плоскости"},
            {"order": 2, "subtopic_id": "S1", "subtopic_name": "Угол между плоскостями (двугранный угол)"},
            {"order": 3, "subtopic_id": "S2", "subtopic_name": "Угол между прямой и плоскостью"},
        ]
    },
    {
        "order": 32, "topic_id": "T032", "topic_name": "Текстовые задачи: движение",
        "subtopics": [
            {"order": 1, "subtopic_id": "S0", "subtopic_name": "Движение в противоположных направлениях"},
            {"order": 2, "subtopic_id": "S1", "subtopic_name": "Движение по воде"},
            {"order": 3, "subtopic_id": "S2", "subtopic_name": "Движение по кругу"},
        ]
    },
    {
        "order": 33, "topic_id": "T033", "topic_name": "Текстовые задачи: производительность и смеси",
        "subtopics": [
            {"order": 1, "subtopic_id": "S0", "subtopic_name": "Задачи на концентрацию, сплавы, смеси"},
            {"order": 2, "subtopic_id": "S1", "subtopic_name": "Задачи на совместную работу"},
            {"order": 3, "subtopic_id": "S2", "subtopic_name": "Задачи на производительность труда"},
        ]
    },
    {
        "order": 34, "topic_id": "T034", "topic_name": "Теория вероятностей: дискретные распределения",
        "subtopics": [
            {"order": 1, "subtopic_id": "S0", "subtopic_name": "Биномиальное распределение"},
            {"order": 2, "subtopic_id": "S1", "subtopic_name": "Дискретные случайные величины"},
            {"order": 3, "subtopic_id": "S2", "subtopic_name": "Математическое ожидание и дисперсия"},
        ]
    },
    {
        "order": 35, "topic_id": "T035", "topic_name": "Теория вероятностей: классическая модель",
        "subtopics": [
            {"order": 1, "subtopic_id": "S0", "subtopic_name": "Геометрическая вероятность"},
            {"order": 2, "subtopic_id": "S1", "subtopic_name": "Классическая вероятность"},
            {"order": 3, "subtopic_id": "S2", "subtopic_name": "Условная вероятность и формула Байеса"},
        ]
    },
    {
        "order": 36, "topic_id": "T036", "topic_name": "Тригонометрические уравнения",
        "subtopics": [
            {"order": 1, "subtopic_id": "S0", "subtopic_name": "Однородные тригонометрические уравнения"},
            {"order": 2, "subtopic_id": "S1", "subtopic_name": "Отбор корней в тригонометрических уравнениях"},
            {"order": 3, "subtopic_id": "S2", "subtopic_name": "Простейшие тригонометрические уравнения"},
        ]
    },
    {
        "order": 37, "topic_id": "T037", "topic_name": "Тригонометрия: преобразования",
        "subtopics": [
            {"order": 1, "subtopic_id": "S0", "subtopic_name": "Основное тригонометрическое тождество"},
            {"order": 2, "subtopic_id": "S1", "subtopic_name": "Формулы приведения"},
            {"order": 3, "subtopic_id": "S2", "subtopic_name": "Формулы сложения и двойного угла"},
        ]
    },
    {
        "order": 38, "topic_id": "T038", "topic_name": "Уравнения с модулем",
        "subtopics": [
            {"order": 1, "subtopic_id": "S0", "subtopic_name": "Графическое решение уравнений с модулем"},
            {"order": 2, "subtopic_id": "S1", "subtopic_name": "Метод интервалов для уравнений с модулем"},
            {"order": 3, "subtopic_id": "S2", "subtopic_name": "Решение уравнений с модулем (раскрытие по случаям)"},
        ]
    },
    {
        "order": 39, "topic_id": "T039", "topic_name": "Уравнения: иррациональные",
        "subtopics": [
            {"order": 1, "subtopic_id": "S0", "subtopic_name": "Уравнения с одним радикалом"},
            {"order": 2, "subtopic_id": "S1", "subtopic_name": "Уравнения с двумя и более радикалами"},
            {"order": 3, "subtopic_id": "S2", "subtopic_name": "Иррациональные уравнения: метод возведения в степень"},
        ]
    },
    {
        "order": 40, "topic_id": "T040", "topic_name": "Уравнения: показательные и логарифмические",
        "subtopics": [
            {"order": 1, "subtopic_id": "S0", "subtopic_name": "Логарифмические уравнения"},
            {"order": 2, "subtopic_id": "S1", "subtopic_name": "Показательные уравнения"},
            {"order": 3, "subtopic_id": "S2", "subtopic_name": "Системы показательных и логарифмических уравнений"},
        ]
    },
    {
        "order": 41, "topic_id": "T041", "topic_name": "Уравнения: тригонометрические системы",
        "subtopics": [
            {"order": 1, "subtopic_id": "S0", "subtopic_name": "Системы тригонометрических уравнений"},
            {"order": 2, "subtopic_id": "S1", "subtopic_name": "Тригонометрические уравнения с параметром"},
            {"order": 3, "subtopic_id": "S2", "subtopic_name": "Универсальная тригонометрическая подстановка и метод вспомогательного угла"},
        ]
    },
    {
        "order": 42, "topic_id": "T042", "topic_name": "Числа, индукция, алгоритмы",
        "subtopics": [
            {"order": 1, "subtopic_id": "S0", "subtopic_name": "Системы счисления и запись чисел"},
            {"order": 2, "subtopic_id": "S1", "subtopic_name": "Комплексные числа"},
            {"order": 3, "subtopic_id": "S2", "subtopic_name": "Метод математической индукции"},
        ]
    },
    {
        "order": 43, "topic_id": "T043", "topic_name": "Функции и графики",
        "subtopics": [
            {"order": 1, "subtopic_id": "S0", "subtopic_name": "Область определения и область значений функции"},
            {"order": 2, "subtopic_id": "S1", "subtopic_name": "Чтение, построение и преобразование графиков"},
            {"order": 3, "subtopic_id": "S2", "subtopic_name": "Композиция и обратная функция"},
        ]
    },
]


def build_json():
    """Build the full canonical_taxonomy.json structure."""
    topics_dict = {}
    for t in TOPICS:
        subtopics_dict = {}
        for s in t["subtopics"]:
            subtopics_dict[s["subtopic_id"]] = {
                "subtopic_id": s["subtopic_id"],
                "subtopic_name": s["subtopic_name"],
                "order": s["order"],
            }
        topics_dict[t["topic_id"]] = {
            "topic_id": t["topic_id"],
            "topic_name": t["topic_name"],
            "order": t["order"],
            "subtopics": subtopics_dict,
        }
    return {
        "schema_version": "1.0",
        "authority": "direct_user_specification",
        "numbering_rule": {
            "topics": "ordered_1_based_T001_to_T043",
            "subtopics": {
                "ПОДТЕМА 1": "S0",
                "ПОДТЕМА 2": "S1",
                "ПОДТЕМА 3": "S2",
            },
        },
        "topics": topics_dict,
    }


def build_csv_rows():
    """Build rows for canonical_taxonomy.csv."""
    rows = []
    for t in TOPICS:
        for s in t["subtopics"]:
            rows.append({
                "topic_order": t["order"],
                "topic_id": t["topic_id"],
                "topic_name": t["topic_name"],
                "subtopic_order": s["order"],
                "subtopic_id": s["subtopic_id"],
                "subtopic_name": s["subtopic_name"],
                "authority": "direct_user_specification",
            })
    return rows


def compute_sha256(filepath):
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def run_audit(json_path):
    """Run invariant checks on the taxonomy and build audit report."""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    topics = data["topics"]
    topic_ids = sorted(topics.keys())
    topic_names = [t["topic_name"] for t in topics.values()]

    subtopic_counts = {}
    subtopic_ids_set = {}
    empty_topic_names = 0
    empty_subtopic_names = 0
    duplicate_topic_names = 0
    duplicate_topic_ids = 0
    duplicate_pairs = 0

    seen_topic_names = {}
    seen_pairs = {}

    for tid, t in topics.items():
        if not t["topic_name"].strip():
            empty_topic_names += 1
        seen_topic_names[t["topic_name"]] = seen_topic_names.get(t["topic_name"], 0) + 1

        sub_ids = sorted(t["subtopics"].keys())
        subtopic_counts[tid] = len(sub_ids)
        subtopic_ids_set[tid] = sub_ids

        for sid, s in t["subtopics"].items():
            if not s["subtopic_name"].strip():
                empty_subtopic_names += 1
            pair = (tid, sid)
            if pair in seen_pairs:
                duplicate_pairs += 1
            seen_pairs[pair] = True

    for name, count in seen_topic_names.items():
        if count > 1:
            duplicate_topic_names += count - 1

    # Check topic IDs are T001-T043
    expected_ids = [f"T{i:03d}" for i in range(1, 44)]
    topic_ids_ok = topic_ids == expected_ids
    if not topic_ids_ok:
        duplicate_topic_ids = len(set(topic_ids) - set(expected_ids)) + len(set(expected_ids) - set(topic_ids))

    # Check each topic has exactly 3 subtopics S0, S1, S2
    each_has_3 = all(c == 3 for c in subtopic_counts.values())
    each_has_s0s1s2 = all(subtopic_ids_set[tid] == ["S0", "S1", "S2"] for tid in topic_ids)

    audit = {
        "audit_timestamp": None,  # filled after file write
        "file": "canonical_taxonomy.json",
        "sha256": None,  # filled after file write
        "invariants": {
            "topics_count": len(topics),
            "subtopics_count": sum(subtopic_counts.values()),
            "each_topic_has_exactly_3_subtopics": each_has_3,
            "topic_ids_are_T001_through_T043": topic_ids_ok,
            "each_topic_has_S0_S1_S2": each_has_s0s1s2,
            "empty_topic_names": empty_topic_names,
            "empty_subtopic_names": empty_subtopic_names,
            "duplicate_topic_names": duplicate_topic_names,
            "duplicate_topic_ids": duplicate_topic_ids,
            "duplicate_topic_subtopic_pairs": duplicate_pairs,
        },
        "all_invariants_pass": (
            len(topics) == 43
            and sum(subtopic_counts.values()) == 129
            and each_has_3
            and topic_ids_ok
            and each_has_s0s1s2
            and empty_topic_names == 0
            and empty_subtopic_names == 0
            and duplicate_topic_names == 0
            and duplicate_topic_ids == 0
            and duplicate_pairs == 0
        ),
        "status": None,
    }
    audit["status"] = "TAXONOMY_OK" if audit["all_invariants_pass"] else "TAXONOMY_PARSE_ERROR"
    return audit


def main():
    out_dir = SCRIPT_DIR

    # 1. Write canonical_taxonomy.json
    json_data = build_json()
    json_path = os.path.join(out_dir, "canonical_taxonomy.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)
    print(f"[OK] Created {json_path}")

    # 2. Write canonical_taxonomy.csv
    csv_rows = build_csv_rows()
    csv_path = os.path.join(out_dir, "canonical_taxonomy.csv")
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "topic_order", "topic_id", "topic_name",
            "subtopic_order", "subtopic_id", "subtopic_name",
            "authority",
        ])
        writer.writeheader()
        writer.writerows(csv_rows)
    print(f"[OK] Created {csv_path} ({len(csv_rows)} rows)")

    # 3. Compute SHA-256 of JSON file
    sha256 = compute_sha256(json_path)
    print(f"[OK] SHA-256: {sha256}")

    # 4. Write canonical_taxonomy_audit.json
    from datetime import datetime, timezone
    audit = run_audit(json_path)
    audit["sha256"] = sha256
    audit["audit_timestamp"] = datetime.now(timezone.utc).isoformat()

    audit_path = os.path.join(out_dir, "canonical_taxonomy_audit.json")
    with open(audit_path, "w", encoding="utf-8") as f:
        json.dump(audit, f, ensure_ascii=False, indent=2)
    print(f"[OK] Created {audit_path}")

    # 5. Summary
    print()
    print("=" * 60)
    print("TAXONOMY BUILD SUMMARY")
    print("=" * 60)
    print(f"  Topics: {len(json_data['topics'])} (T001-T043)")
    total_sub = sum(len(t["subtopics"]) for t in json_data["topics"].values())
    print(f"  Subtopics: {total_sub} (3 per topic)")
    print(f"  Status: {audit['status']}")
    print(f"  SHA-256: {sha256}")
    if audit["all_invariants_pass"]:
        print("  All invariants: PASS")
    else:
        print("  All invariants: FAIL")
        for k, v in audit["invariants"].items():
            if v is False or (isinstance(v, int) and v > 0):
                print(f"    - {k}: {v}")
        sys.exit(1)
    print("=" * 60)


if __name__ == "__main__":
    main()
