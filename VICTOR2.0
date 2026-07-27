#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
VICTOR2.0 — Генерация задач в 5 параллельных потоков.
Использует РОВНО ОДНУ ТЕМУ НА ОДИН КЛАСС (распределение от пользователя).

Уровни:
  L1 — Обычная школьная задача (НЕ 43+25, такого в ячейниках нет)
  L2 — Олимпиадная уровня школьного этапа ВСОШ
  L3 — Уровень муниципа (заметно сложнее L2)
  L4, L5 — НЕ ТРОГАТЬ

Счёт: количество ПОЛНОСТЬЮ ЗАПОЛНЕННЫХ ячеек (5 задач на ячейку grade×theme×level).
"""

import json
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Optional

# Windows console encoding fix
if sys.platform == 'win32':
    import codecs
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger('VICTOR2.0')

# ============================================================================
# 1. ВСЕ ТЕМЫ (41 каноническая + 2 добавленные из Section 3)
# ============================================================================

THEMES = {
    # --- Канонические 41 тема (Section 1) ---
    "T001": {
        "name": "Алгебра: теория групп",
        "subtopics": [
            "Группы: определения и примеры",
            "Группы: подгруппы, смежные классы",
            "Гомоморфизмы и факторгруппы"
        ]
    },
    "T002": {
        "name": "Арифметика и теория чисел",
        "subtopics": [
            "Делимость и остатки",
            "НОД, НОК, алгоритм Евклида",
            "Сравнения по модулю (a ≡ b mod n)"
        ]
    },
    "T003": {
        "name": "Вероятность и комбинаторика",
        "subtopics": [
            "Геометрическая вероятность",
            "Классическая вероятность",
            "Условная вероятность и формула Байеса"
        ]
    },
    "T004": {
        "name": "Графы: основные понятия",
        "subtopics": [
            "Графы: определения, изоморфизм",
            "Маршруты, цепи, циклы, Эйлеровы графы",
            "Связность и компоненты связности"
        ]
    },
    "T005": {
        "name": "Дополнительные задачи и смешанные темы",
        "subtopics": [
            "Задачи на оптимизацию",
            "Комбинированные задачи (алгебра + геометрия)",
            "Прикладные задачи"
        ]
    },
    "T006": {
        "name": "Комбинаторика и вероятность",
        "subtopics": [
            "Перестановки и факториалы",
            "Правила сложения и умножения в комбинаторике",
            "Размещения и сочетания"
        ]
    },
    "T007": {
        "name": "Комбинаторика и теория игр",
        "subtopics": [
            "Выигрышные и проигрышные позиции",
            "Игры с симметричной стратегией",
            "Стратегия и анализ игр"
        ]
    },
    "T008": {
        "name": "Логика и множества",
        "subtopics": [
            "Булевы функции и их минимизация",
            "Логические операции и таблицы истинности",
            "Множества и операции над ними"
        ]
    },
    "T009": {
        "name": "Метод координат: декартовы координаты",
        "subtopics": [
            "Координаты на прямой и плоскости",
            "Расстояние между точками, середина отрезка",
            "Уравнения прямых и окружностей"
        ]
    },
    "T010": {
        "name": "Метод координат: векторы",
        "subtopics": [
            "Векторы: сложение, умножение на число",
            "Координаты вектора, связь с точками",
            "Скалярное произведение векторов"
        ]
    },
    "T011": {
        "name": "Неравенства: алгебраические неравенства",
        "subtopics": [
            "Доказательство неравенств",
            "Квадратные неравенства",
            "Неравенства с модулем"
        ]
    },
    "T012": {
        "name": "Неравенства: метод интервалов и рациональные",
        "subtopics": [
            "Дробно-рациональные неравенства",
            "Иррациональные неравенства",
            "Метод интервалов для рациональных неравенств"
        ]
    },
    "T013": {
        "name": "Неравенства: показательные и логарифмические",
        "subtopics": [
            "Логарифмические неравенства",
            "Показательные неравенства",
            "Системы показательных и логарифмических неравенств"
        ]
    },
    "T014": {
        "name": "Неравенства: тригонометрические",
        "subtopics": [
            "Неравенства с обратными тригонометрическими функциями",
            "Простейшие тригонометрические неравенства с sin, cos",
            "Простейшие тригонометрические неравенства с tg, ctg"
        ]
    },
    "T015": {
        "name": "Неравенства: числовые наборы",
        "subtopics": [
            "Неравенства о среднем арифметическом и среднем геометрическом",
            "Неравенства Чебышева и Маркова",
            "Цепочки неравенств, взвешенные средние"
        ]
    },
    "T016": {
        "name": "Планиметрия: многоугольники",
        "subtopics": [
            "Многоугольники: виды, свойства",
            "Параллелограммы и трапеции",
            "Треугольники: виды, свойства"
        ]
    },
    "T017": {
        "name": "Планиметрия: окружность",
        "subtopics": [
            "Вписанные углы и их свойства",
            "Длина окружности, площадь круга и сектора",
            "Касательные и секущие к окружности"
        ]
    },
    "T018": {
        "name": "Планиметрия: площадь",
        "subtopics": [
            "Площади подобных фигур",
            "Площадь круга и его частей",
            "Формулы площади треугольника и четырёхугольника"
        ]
    },
    "T019": {
        "name": "Планиметрия: треугольники",
        "subtopics": [
            "Подобие треугольников",
            "Признаки равенства треугольников",
            "Теорема Пифагора"
        ]
    },
    "T020": {
        "name": "Последовательности и прогрессии",
        "subtopics": [
            "Арифметическая прогрессия",
            "Геометрическая прогрессия",
            "Суммы последовательностей"
        ]
    },
    "T021": {
        "name": "Производная и её применение",
        "subtopics": [
            "Геометрический смысл производной",
            "Исследование функций с помощью производной",
            "Правила и формулы дифференцирования"
        ]
    },
    "T022": {
        "name": "Проценты, отношения и пропорции",
        "subtopics": [
            "Задачи на проценты",
            "Пропорции и отношения",
            "Прямая и обратная пропорциональность"
        ]
    },
    "T023": {
        "name": "Рациональные уравнения и неравенства",
        "subtopics": [
            "Дробно-рациональные уравнения",
            "Метод замены переменной в рациональных уравнениях",
            "Рациональные уравнения"
        ]
    },
    "T024": {
        "name": "Решение задач: анализ и интерпретация",
        "subtopics": [
            "Оценка и прикидка",
            "Проверка решения и поиск ошибок",
            "Составление плана решения"
        ]
    },
    "T025": {
        "name": "Решение уравнений: методы замены",
        "subtopics": [
            "Замена переменной (подстановка)",
            "Использование симметрии",
            "Сведение к системе уравнений"
        ]
    },
    "T026": {
        "name": "Решение уравнений: разложение на множители",
        "subtopics": [
            "Вынесение общего множителя и группировка",
            "Использование формул сокращённого умножения",
            "Разложение квадратного трёхчлена"
        ]
    },
    "T027": {
        "name": "Системы уравнений",
        "subtopics": [
            "Графический метод решения систем",
            "Метод подстановки",
            "Системы линейных уравнений"
        ]
    },
    "T028": {
        "name": "Стереометрия: аксиомы и прямые",
        "subtopics": [
            "Аксиомы стереометрии",
            "Взаимное расположение прямых в пространстве",
            "Скрещивающиеся прямые"
        ]
    },
    "T029": {
        "name": "Стереометрия: многогранники",
        "subtopics": [
            "Параллелепипеды, призмы",
            "Пирамиды",
            "Правильные многогранники"
        ]
    },
    "T030": {
        "name": "Стереометрия: тела вращения",
        "subtopics": [
            "Конус, цилиндр",
            "Сфера, шар",
            "Тела вращения: сечения, комбинации"
        ]
    },
    "T031": {
        "name": "Стереометрия: угол и расстояние",
        "subtopics": [
            "Расстояние от точки до плоскости",
            "Угол между плоскостями (двугранный угол)",
            "Угол между прямой и плоскостью"
        ]
    },
    "T032": {
        "name": "Текстовые задачи: движение",
        "subtopics": [
            "Движение в противоположных направлениях",
            "Движение по воде",
            "Движение по кругу"
        ]
    },
    "T033": {
        "name": "Текстовые задачи: производительность и смеси",
        "subtopics": [
            "Задачи на концентрацию, сплавы, смеси",
            "Задачи на совместную работу",
            "Задачи на производительность труда"
        ]
    },
    "T034": {
        "name": "Теория вероятностей: дискретные распределения",
        "subtopics": [
            "Биномиальное распределение",
            "Дискретные случайные величины",
            "Математическое ожидание и дисперсия"
        ]
    },
    "T035": {
        "name": "Тригонометрические уравнения",
        "subtopics": [
            "Однородные тригонометрические уравнения",
            "Отбор корней в тригонометрических уравнениях",
            "Простейшие тригонометрические уравнения"
        ]
    },
    "T036": {
        "name": "Тригонометрия: преобразования",
        "subtopics": [
            "Основное тригонометрическое тождество",
            "Формулы приведения",
            "Формулы сложения и двойного угла"
        ]
    },
    "T037": {
        "name": "Уравнения с модулем",
        "subtopics": [
            "Графическое решение уравнений с модулем",
            "Метод интервалов для уравнений с модулем",
            "Уравнения с модулем"
        ]
    },
    "T038": {
        "name": "Уравнения: иррациональные",
        "subtopics": [
            "Иррациональные уравнения с одним корнем",
            "Иррациональные уравнения с несколькими корнями",
            "Метод замены в иррациональных уравнениях"
        ]
    },
    "T039": {
        "name": "Уравнения: показательные и логарифмические",
        "subtopics": [
            "Логарифмические уравнения",
            "Показательные уравнения",
            "Системы показательных и логарифмических уравнений"
        ]
    },
    "T040": {
        "name": "Уравнения: тригонометрические системы",
        "subtopics": [
            "Системы тригонометрических уравнений",
            "Тригонометрические уравнения с параметром",
            "Тригонометрические уравнения с отбором корней"
        ]
    },
    "T041": {
        "name": "Числа, индукция, алгоритмы",
        "subtopics": [
            "Алгоритмы и вычисления",
            "Комплексные числа",
            "Метод математической индукции"
        ]
    },
    # --- Добавленные темы из Section 3 (сокращены до 3 подтем) ---
    "T042": {
        "name": "Функции и графики",
        "subtopics": [
            "Графики функций: преобразования и сдвиги",
            "Область определения и область значений",
            "Построение графиков сложных функций"
        ]
    },
    "T043": {
        "name": "Стереометрия: объёмы и сечения",
        "subtopics": [
            "Объём многогранников",
            "Объём тел вращения",
            "Сечения многогранников"
        ]
    }
}

# ============================================================================
# 2. РАСПРЕДЕЛЕНИЕ ПО КЛАССАМ (РОВНО ОДНА ТЕМА = ОДИН КЛАСС)
# ============================================================================
# Распределение от пользователя, переведённое в T-ID:
#   5 класс (6): T002, T022, T008, T004, T024, T005
#   6 класс (6): T006, T007, T032, T033, T016, T018
#   7 класс (6): T026, T025, T023, T027, T019, T003
#   8 класс (6): T042, T011, T012, T037, T009, T017
#   9 класс (6): T038, T020, T010, T015, T036, T035
#  10 класс (6): T039, T013, T014, T028, T029, T030
#  11 класс (7): T021, T040, T034, T043, T031, T041, T001

GRADE_THEMES = {
    5:  ["T002", "T022", "T008", "T004", "T024", "T005"],
    6:  ["T006", "T007", "T032", "T033", "T016", "T018"],
    7:  ["T026", "T025", "T023", "T027", "T019", "T003"],
    8:  ["T042", "T011", "T012", "T037", "T009", "T017"],
    9:  ["T038", "T020", "T010", "T015", "T036", "T035"],
    10: ["T039", "T013", "T014", "T028", "T029", "T030"],
    11: ["T021", "T040", "T034", "T043", "T031", "T041", "T001"]
}

# ============================================================================
# 3. НАСТРОЙКИ ГЕНЕРАЦИИ
# ============================================================================

TASKS_PER_CELL = 5          # Сколько задач нужно для полной ячейки
MAX_WORKERS = 5             # 5 параллельных потоков
MAX_RETRIES = 3             # Попыток на одну задачу
CELL_TIMEOUT = 120          # Таймаут на генерацию одной задачи (сек)

# Только L1, L2, L3 (L4, L5 — не трогать)
ACTIVE_LEVELS = [1, 2, 3]

LEVEL_LABELS = {
    1: "L1",
    2: "L2",
    3: "L3"
}

LEVEL_DESCRIPTIONS = {
    1: (
        "Обычная школьная задача. НЕ ПИШИ примитивные примеры вроде 'сложить 43+25' — "
        "такого в ячейниках нет. Задача должна быть содержательной, но доступной для "
        "обычного школьника этого класса."
    ),
    2: (
        "Олимпиадная задача уровня ШКОЛЬНОГО ЭТАПА ВСОШ. Требует нестандартного "
        "мышления, но вписывается в программу класса. Не слишком сложная."
    ),
    3: (
        "Задача уровня МУНИЦИПАЛЬНОГО ЭТАПА ВСОШ. Заметно сложнее уровня 2. "
        "Требует глубокого понимания темы и умения комбинировать разные подходы."
    )
}

# ============================================================================
# 4. DEEPSEEK CLIENT
# ============================================================================

class DeepSeekClient:
    """Minimal DeepSeek API client for task generation."""

    def __init__(self):
        self.api_key = os.environ.get('DEEPSEEK_API_KEY')
        if not self.api_key:
            raise ValueError("DEEPSEEK_API_KEY not set in environment")
        self.base_url = "https://api.deepseek.com/v1/chat/completions"
        self.model = "deepseek-chat"

    def generate(self, prompt: str, system_prompt: str = "",
                 temperature: float = 0.7, max_tokens: int = 4000) -> Optional[str]:
        """Send request to DeepSeek API and return response text."""
        import requests

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        try:
            resp = requests.post(
                self.base_url, headers=headers, json=payload, timeout=CELL_TIMEOUT
            )
            if resp.status_code != 200:
                logger.warning(f"API error {resp.status_code}: {resp.text[:200]}")
                return None
            data = resp.json()
            content = data.get('choices', [{}])[0].get('message', {}).get('content', '')
            return content.strip() if content else None
        except Exception as e:
            logger.warning(f"API request failed: {e}")
            return None


# ============================================================================
# 5. ПРОМПТЫ
# ============================================================================

SYSTEM_PROMPT = """Ты — генератор математических задач для олимпиадной системы обучения.
Твоя задача — создавать задачи строго по указанным параметрам.

Формат ответа — ТОЛЬКО валидный JSON (без markdown-обёртки):
{
  "statement": "Условие задачи на русском языке",
  "answer": "Краткий ответ",
  "solution": "Полное решение задачи"
}

Правила:
- Условие должно быть чётким и однозначным.
- Решение — пошаговое, с пояснениями.
- Задача должна быть оригинальной (не из учебников).
- Не используй эмодзи и спецсимволы в ответе.
- Все числовые значения реалистичны."""


def build_prompt(grade: int, theme_name: str, subtopic: str,
                 level: int, existing_texts: list) -> str:
    """Build a prompt for generating one task."""
    level_desc = LEVEL_DESCRIPTIONS[level]
    level_label = LEVEL_LABELS[level]

    prompt = f"""Сгенерируй одну математическую задачу для {grade} класса.

Тема: {theme_name}
Подтема: {subtopic}
Уровень: {level_label}

Описание уровня: {level_desc}

"""
    if existing_texts:
        prompt += "Ранее сгенерированные задачи этой ячейки (создай ДРУГУЮ):\n"
        for i, txt in enumerate(existing_texts, 1):
            prompt += f"  {i}. {txt[:150]}\n"
        prompt += "\n"

    prompt += (
        "Ответ дай ТОЛЬКО в виде JSON-объекта с ключами: "
        '"statement", "answer", "solution".\n'
        "Без markdown-обёртки, без пояснений."
    )
    return prompt


# ============================================================================
# 6. ПАРСИНГ JSON
# ============================================================================

import re

def extract_json(text: str) -> Optional[dict]:
    """Try to extract a JSON object from text (handles markdown fences)."""
    if not text:
        return None

    # Try direct parse
    text = text.strip()
    if text.startswith('{') and text.endswith('}'):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

    # Try to find JSON in markdown code blocks
    match = re.search(r'```(?:json)?\s*\n?({.*?})\n?\s*```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Try to find any {...} object
    match = re.search(r'({[^{}]*"statement"[^{}]*"answer"[^{}]*"solution"[^{}]*})', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    return None


def safe_parse(text: str) -> Optional[dict]:
    """Parse JSON, handling escape issues."""
    parsed = extract_json(text)
    if parsed is None:
        return None

    # Validate required fields
    if not isinstance(parsed.get('statement'), str) or len(parsed['statement'].strip()) < 10:
        return None
    if not isinstance(parsed.get('answer'), str) or len(parsed['answer'].strip()) < 1:
        return None
    if not isinstance(parsed.get('solution'), str) or len(parsed['solution'].strip()) < 10:
        return None

    return parsed


# ============================================================================
# 7. ОСНОВНАЯ ЛОГИКА ГЕНЕРАЦИИ
# ============================================================================

def build_cell_plan() -> list:
    """Build list of all cells to fill: (grade, theme_id, level, subtopics)."""
    cells = []
    for grade in sorted(GRADE_THEMES.keys()):
        for tid in GRADE_THEMES[grade]:
            theme = THEMES[tid]
            for level in ACTIVE_LEVELS:
                cells.append({
                    'grade': grade,
                    'theme_id': tid,
                    'theme_name': theme['name'],
                    'subtopics': theme['subtopics'],
                    'level': level,
                    'level_label': LEVEL_LABELS[level],
                    'key': f"G{grade}|{tid}|L{level}"
                })
    return cells


def generate_one_task(client: DeepSeekClient, cell: dict,
                      subtopic: str, existing: list) -> Optional[dict]:
    """Generate a single task for a cell+subtopic."""
    prompt = build_prompt(
        grade=cell['grade'],
        theme_name=cell['theme_name'],
        subtopic=subtopic,
        level=cell['level'],
        existing_texts=existing
    )

    for attempt in range(MAX_RETRIES):
        raw = client.generate(prompt=prompt, system_prompt=SYSTEM_PROMPT)
        if not raw:
            logger.debug(f"  [{cell['key']}/{subtopic[:30]}...] attempt {attempt+1}: empty response")
            time.sleep(1)
            continue

        task = safe_parse(raw)
        if task:
            # Add metadata
            task['level'] = cell['level']
            task['grade'] = cell['grade']
            task['theme_id'] = cell['theme_id']
            task['theme_name'] = cell['theme_name']
            task['subtopic'] = subtopic
            task['source'] = 'VICTOR2.0'
            task['generated_at'] = datetime.now(timezone.utc).isoformat()
            return task

        logger.debug(f"  [{cell['key']}] attempt {attempt+1}: JSON parse failed")
        time.sleep(1)

    return None


def fill_cell(client: DeepSeekClient, cell: dict,
              all_existing: dict) -> list:
    """Fill one cell (grade×theme×level) to TASKS_PER_CELL tasks."""
    cell_key = cell['key']
    existing = all_existing.get(cell_key, [])
    existing_texts = [t.get('statement', '')[:150] for t in existing]

    tasks = list(existing)  # start with existing tasks
    needed = TASKS_PER_CELL - len(tasks)

    if needed <= 0:
        return tasks  # already full

    # Rotate through subtopics for variety
    subtopics = cell['subtopics']
    subtopic_idx = len(tasks) % len(subtopics)

    for i in range(needed):
        subtopic = subtopics[subtopic_idx % len(subtopics)]
        subtopic_idx += 1

        logger.info(f"  Generating task {len(tasks)+1}/{TASKS_PER_CELL} [{cell_key}] [{subtopic[:40]}...]")

        task = generate_one_task(client, cell, subtopic, existing_texts)
        if task:
            tasks.append(task)
            existing_texts.append(task.get('statement', '')[:150])
            logger.info(f"    [OK] Task {len(tasks)}/{TASKS_PER_CELL}")
        else:
            logger.warning(f"    [FAIL] Failed to generate task for {cell_key}")

    return tasks


def process_cell(client: DeepSeekClient, cell: dict,
                 all_existing: dict) -> dict:
    """Process a single cell and return status."""
    cell_key = cell['key']
    logger.info(f"\n{'='*60}")
    logger.info(f"Cell: {cell_key} | {cell['theme_name']}")
    logger.info(f"{'='*60}")

    tasks = fill_cell(client, cell, all_existing)
    is_full = len(tasks) >= TASKS_PER_CELL

    result = {
        'key': cell_key,
        'grade': cell['grade'],
        'theme_id': cell['theme_id'],
        'theme_name': cell['theme_name'],
        'level': cell['level'],
        'level_label': cell['level_label'],
        'tasks_count': len(tasks),
        'target': TASKS_PER_CELL,
        'is_full': is_full,
        'tasks': tasks
    }

    status_icon = "FULL" if is_full else f"{len(tasks)}/{TASKS_PER_CELL}"
    logger.info(f"  [{status_icon}] {cell_key} — {len(tasks)} tasks")
    return result


# ============================================================================
# 8. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================================

def load_existing_tasks(path: str = None) -> dict:
    """Load existing tasks and group by cell key."""
    if path and os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list):
                existing = {}
                for t in data:
                    grade = t.get('grade')
                    theme_id = t.get('theme_id')
                    level = t.get('level')
                    if grade and theme_id and level:
                        key = f"G{grade}|{theme_id}|L{level}"
                        existing.setdefault(key, []).append(t)
                logger.info(f"Loaded {len(data)} existing tasks from {path}")
                return existing
        except Exception as e:
            logger.warning(f"Could not load existing tasks: {e}")

    logger.info("No existing tasks loaded, starting fresh")
    return {}


def print_report(results: list, elapsed: float):
    """Print generation report."""
    total_cells = len(results)
    full_cells = sum(1 for r in results if r['is_full'])
    total_tasks = sum(r['tasks_count'] for r in results)

    print(f"\n{'='*70}")
    print(f"  VICTOR2.0 — ОТЧЁТ О ГЕНЕРАЦИИ")
    print(f"{'='*70}")
    print(f"  Время выполнения: {elapsed:.1f} сек ({elapsed/60:.1f} мин)")
    print(f"  Всего ячеек:      {total_cells}")
    print(f"  Полностью filled:  {full_cells} / {total_cells}")
    print(f"  Всего задач:       {total_tasks}")
    print(f"  Среднее на ячейку: {total_tasks/total_cells:.1f}" if total_cells else "")
    print(f"{'='*70}\n")

    # By grade
    print("По классам:")
    print(f"  {'Класс':<8} {'Ячеек':<8} {'Full':<8} {'Задач':<8} {'% заполн':<10}")
    print(f"  {'-'*42}")
    by_grade = {}
    for r in results:
        by_grade.setdefault(r['grade'], []).append(r)
    for g in sorted(by_grade.keys()):
        grp = by_grade[g]
        n_cells = len(grp)
        n_full = sum(1 for r in grp if r['is_full'])
        n_tasks = sum(r['tasks_count'] for r in grp)
        pct = n_full / n_cells * 100 if n_cells else 0
        print(f"  {g:<8} {n_cells:<8} {n_full:<8} {n_tasks:<8} {pct:>6.1f}%")

    # By level
    print("\nПо уровням:")
    print(f"  {'Уровень':<10} {'Ячеек':<8} {'Full':<8} {'Задач':<8}")
    print(f"  {'-'*34}")
    by_level = {}
    for r in results:
        by_level.setdefault(r['level'], []).append(r)
    for lv in sorted(by_level.keys()):
        grp = by_level[lv]
        n_cells = len(grp)
        n_full = sum(1 for r in grp if r['is_full'])
        n_tasks = sum(r['tasks_count'] for r in grp)
        print(f"  L{lv:<9} {n_cells:<8} {n_full:<8} {n_tasks:<8}")

    # Not full cells
    not_full = [r for r in results if not r['is_full']]
    if not_full:
        print(f"\nЯчейки, требующие доработки ({len(not_full)}):")
        for r in sorted(not_full, key=lambda x: x['key']):
            print(f"  {r['key']:<25} {r['tasks_count']}/{TASKS_PER_CELL} — {r['theme_name']}")


def save_results(results: list, output_path: str):
    """Save all generated tasks to JSON file."""
    all_tasks = []
    for r in results:
        for t in r['tasks']:
            # Check if task already has an ID from existing data
            if 'id' not in t:
                t['id'] = f"V2-{r['grade']}-{r['theme_id']}-L{r['level']}-{len(all_tasks)}"
            all_tasks.append(t)

    # Save tasks
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(all_tasks, f, ensure_ascii=False, indent=2)

    # Save report
    report_path = output_path.replace('.json', '_REPORT.md')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("# VICTOR2.0 — Отчёт о генерации\n\n")
        f.write(f"Сгенерировано: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n\n")

        total_cells = len(results)
        full_cells = sum(1 for r in results if r['is_full'])
        total_tasks = sum(r['tasks_count'] for r in results)

        f.write("## Сводка\n\n")
        f.write(f"| Метрика | Значение |\n")
        f.write(f"|---------|----------|\n")
        f.write(f"| Всего ячеек | {total_cells} |\n")
        f.write(f"| Полностью заполнено | {full_cells} |\n")
        f.write(f"| Всего задач | {total_tasks} |\n")
        f.write(f"| Цель на ячейку | {TASKS_PER_CELL} |\n\n")

        f.write("## По классам\n\n")
        f.write("| Класс | Ячеек | Full | Задач | % |\n")
        f.write("|-------|-------|------|-------|---|\n")
        by_grade = {}
        for r in results:
            by_grade.setdefault(r['grade'], []).append(r)
        for g in sorted(by_grade.keys()):
            grp = by_grade[g]
            n_cells = len(grp)
            n_full = sum(1 for r in grp if r['is_full'])
            n_tasks = sum(r['tasks_count'] for r in grp)
            pct = n_full / n_cells * 100 if n_cells else 0
            f.write(f"| {g} | {n_cells} | {n_full} | {n_tasks} | {pct:.1f}% |\n")

        f.write("\n## По уровням\n\n")
        f.write("| Уровень | Ячеек | Full | Задач |\n")
        f.write("|---------|-------|------|-------|\n")
        by_level = {}
        for r in results:
            by_level.setdefault(r['level'], []).append(r)
        for lv in sorted(by_level.keys()):
            grp = by_level[lv]
            n_cells = len(grp)
            n_full = sum(1 for r in grp if r['is_full'])
            n_tasks = sum(r['tasks_count'] for r in grp)
            f.write(f"| L{lv} | {n_cells} | {n_full} | {n_tasks} |\n")

        not_full = [r for r in results if not r['is_full']]
        if not_full:
            f.write("\n## Недозаполненные ячейки\n\n")
            f.write("| Ячейка | Задач | Тема |\n")
            f.write("|--------|-------|------|\n")
            for r in sorted(not_full, key=lambda x: x['key']):
                f.write(f"| {r['key']} | {r['tasks_count']}/{TASKS_PER_CELL} | {r['theme_name']} |\n")

    logger.info(f"Saved {total_tasks} tasks to {output_path}")
    logger.info(f"Saved report to {report_path}")
    return output_path, report_path


# ============================================================================
# 9. MAIN
# ============================================================================

def main():
    global TASKS_PER_CELL, MAX_WORKERS

    import argparse

    parser = argparse.ArgumentParser(description='VICTOR2.0 — генерация задач')
    parser.add_argument('--output', default='victor2_generated.json',
                        help='Output file path')
    parser.add_argument('--existing', default=None,
                        help='Path to existing tasks JSON to continue from')
    parser.add_argument('--workers', type=int, default=5,
                        help='Number of parallel workers (default: 5)')
    parser.add_argument('--target', type=int, default=5,
                        help='Tasks per cell (default: 5)')
    args = parser.parse_args()

    TASKS_PER_CELL = args.target
    MAX_WORKERS = args.workers

    logger.info("=" * 60)
    logger.info("VICTOR2.0 — STARTING GENERATION")
    logger.info("=" * 60)
    logger.info(f"Workers: {MAX_WORKERS}")
    logger.info(f"Target: {TASKS_PER_CELL} tasks per cell")
    logger.info(f"Active levels: L1, L2, L3")

    # Validate
    all_assigned = set()
    for g, ids in GRADE_THEMES.items():
        for tid in ids:
            assert tid in THEMES, f"Unknown theme {tid} in grade {g}"
            assert tid not in all_assigned, f"Theme {tid} ({THEMES[tid]['name']}) assigned to MULTIPLE grades!"
            all_assigned.add(tid)

    unassigned = set(THEMES.keys()) - all_assigned
    if unassigned:
        logger.warning(f"Themes not assigned to any grade: {unassigned}")

    logger.info(f"Total unique themes: {len(all_assigned)}")
    logger.info(f"Total themes in system: {len(THEMES)}")

    # Build cell plan
    all_cells = build_cell_plan()
    total_target_tasks = len(all_cells) * TASKS_PER_CELL
    logger.info(f"Cells to fill: {len(all_cells)}")
    logger.info(f"Target total tasks: {total_target_tasks}")

    # Load existing
    existing_map = load_existing_tasks(args.existing)

    # Init client
    try:
        client = DeepSeekClient()
        logger.info("DeepSeek client initialized")
    except ValueError as e:
        logger.error(f"Failed to initialize DeepSeek client: {e}")
        logger.error("Set DEEPSEEK_API_KEY environment variable")
        sys.exit(1)

    # Process cells in parallel
    start_time = time.time()
    results = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(process_cell, client, cell, existing_map): cell
            for cell in all_cells
        }

        for future in as_completed(futures):
            cell = futures[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                logger.error(f"Cell {cell['key']} failed: {e}")
                results.append({
                    'key': cell['key'],
                    'grade': cell['grade'],
                    'theme_id': cell['theme_id'],
                    'theme_name': cell['theme_name'],
                    'level': cell['level'],
                    'level_label': cell['level_label'],
                    'tasks_count': 0,
                    'target': TASKS_PER_CELL,
                    'is_full': False,
                    'tasks': []
                })

    elapsed = time.time() - start_time

    # Report
    print_report(results, elapsed)

    # Save
    output_path, report_path = save_results(results, args.output)

    logger.info("=" * 60)
    logger.info("VICTOR2.0 — GENERATION COMPLETE")
    logger.info("=" * 60)


if __name__ == '__main__':
    main()
