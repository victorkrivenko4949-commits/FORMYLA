#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ФАЗА 1: Генерация задач для 7 класса — заполнение дефицитов.
Цель: 25 задач на каждую ячейку (тема × difficulty 1-5).
Приоритет: полные дыры (0 задач) → наибольший дефицит.

Запуск: python scripts/generate_grade7_fill_gaps.py
Флаги:
  --dry-run   только показать план, не генерировать
  --limit N   сгенерировать не более N задач (по умолчанию все)
  --topic T   только для конкретной темы
"""

import sys
import io
import os
import json
import time
import sqlite3
import requests
import re
import argparse
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# ─── Настройки ────────────────────────────────────────────────────────────────
DB_PATH = "instance/formyla.db"
TARGET = 25          # целевое количество задач на ячейку
GRADE = 7
BATCH_SIZE = 10      # коммит каждые N задач
SLEEP_BETWEEN = 3    # секунд между запросами к API

from dotenv import load_dotenv
load_dotenv()
API_KEY = os.environ.get('DEEPSEEK_API_KEY', '')
API_URL = "https://api.deepseek.com/v1/chat/completions"
MODEL = "deepseek-chat"

# ─── Темы 7 класса (из БД) ────────────────────────────────────────────────────
TOPICS_7 = [
    "Алгебраические тождества и преобразования",
    "Взвешивания, переливания и алгоритмы",
    "Геометрические доказательства",
    "Геометрия на клетчатой бумаге и разрезания",
    "Графы (знакомства, турниры, маршруты)",
    "Делимость, остатки и последняя цифра",
    "Инварианты, четность и чередование",
    "Комбинаторика",
    "Комбинаторика (правило суммы и произведения)",
    "Комбинаторика (правилы суммы/произведения, деревья)",
    "Линейные уравнения и системы",
    "Логика (рыцари и лжецы, логические таблицы)",
    "Логика и инварианты",
    "НОД, НОК и основная теорема арифметики",
    "Начала геометрии",
    "Неравенства",
    "Принцип Дирихле",
    "Текстовые задачи (совместная работа, обратный ход)",
    "Теория чисел",
    "Треугольники",
    "Функции и графики",
    "Числовые ребусы и крипторифмы",
]

DIFFICULTY_DESC = {
    1: "очень лёгкая олимпиадная задача (школьный этап, первые задачи)",
    2: "лёгкая олимпиадная задача (школьный этап, средние задачи)",
    3: "средняя олимпиадная задача (муниципальный этап)",
    4: "сложная олимпиадная задача (региональный этап)",
    5: "очень сложная олимпиадная задача (всероссийский/международный уровень)",
}

# ─── Программа 7 класса ───────────────────────────────────────────────────────
GRADE7_CURRICULUM = """
7 КЛАСС — олимпиадная математика:
- Алгебра: линейные уравнения и системы, алгебраические тождества (a²-b², (a+b)²), неравенства
- Теория чисел: делимость, НОД/НОК, остатки, последняя цифра степени, диофантовы уравнения
- Комбинаторика: правило суммы/произведения, перестановки, размещения, сочетания
- Логика: рыцари и лжецы, инварианты, чётность, раскраски
- Геометрия: признаки равенства треугольников, углы, параллельные прямые, площади
- Графы: основы теории графов, задачи на маршруты
- Принцип Дирихле, взвешивания, числовые ребусы
"""


def get_deficit_plan(conn):
    """Возвращает список (topic, difficulty, current_count, deficit) отсортированный по приоритету."""
    cur = conn.cursor()
    plan = []
    for topic in TOPICS_7:
        cur.execute("""
            SELECT difficulty_level, COUNT(*) as cnt
            FROM adaptive_tasks
            WHERE class_level=? AND topic=?
            GROUP BY difficulty_level
        """, (GRADE, topic))
        counts = {row[0]: row[1] for row in cur.fetchall()}
        for d in range(1, 6):
            cnt = counts.get(d, 0)
            deficit = max(0, TARGET - cnt)
            if deficit > 0:
                plan.append((topic, d, cnt, deficit))
    # Сортируем: сначала полные дыры (cnt=0), потом по дефициту убывающему
    plan.sort(key=lambda x: (-1 if x[2] == 0 else 0, -x[3]))
    return plan


def build_prompt(topic, difficulty, existing_count):
    """Строит промпт для генерации задачи."""
    diff_desc = DIFFICULTY_DESC[difficulty]
    return f"""Ты — эксперт по олимпиадной математике для школьников.

Сгенерируй ОДНУ оригинальную олимпиадную задачу для 7 класса.

ТЕМА: {topic}
СЛОЖНОСТЬ: {difficulty}/5 — {diff_desc}
ПРОГРАММА: {GRADE7_CURRICULUM}

ТРЕБОВАНИЯ:
1. Задача должна точно соответствовать теме "{topic}"
2. Сложность {difficulty}/5: {diff_desc}
3. Задача должна быть ОРИГИНАЛЬНОЙ (не из известных олимпиад)
4. Условие чёткое, однозначное, с числовым ответом
5. Используй LaTeX для формул: $\\frac{{a}}{{b}}$, $x^2$, $\\sqrt{{n}}$
6. Решение должно быть полным и понятным для 7-классника

Верни ТОЛЬКО JSON (без markdown, без ```):
{{
  "task_text": "Полный текст задачи с LaTeX формулами",
  "correct_answer": "Числовой ответ (только число или простое выражение)",
  "solution": "Полное решение с объяснением каждого шага",
  "difficulty_check": {difficulty}
}}"""


def call_api(prompt):
    """Вызывает DeepSeek API."""
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.8,
        "max_tokens": 2000,
    }
    resp = requests.post(API_URL, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()['choices'][0]['message']['content']


def parse_response(raw):
    """Парсит JSON из ответа LLM."""
    # Убираем управляющие символы
    raw = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', raw)
    # Ищем JSON
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if not match:
        raise ValueError(f"JSON не найден в ответе: {raw[:200]}")
    return json.loads(match.group())


def insert_task(conn, topic, difficulty, task_text, correct_answer, solution):
    """Вставляет задачу в БД."""
    cur = conn.cursor()
    # criteria_1_point и criteria_2_points — обязательные поля NOT NULL
    criteria_1 = f"Правильный ответ: {correct_answer}"
    criteria_2 = f"Полное решение с обоснованием"
    cur.execute("""
        INSERT INTO adaptive_tasks
        (class_level, topic, difficulty_level, task_text, correct_answer, solution,
         criteria_1_point, criteria_2_points, is_flagged, attempts_count, solves_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0)
    """, (GRADE, topic, difficulty, task_text, correct_answer, solution, criteria_1, criteria_2))
    return cur.lastrowid


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', help='Только показать план')
    parser.add_argument('--limit', type=int, default=0, help='Максимум задач для генерации')
    parser.add_argument('--topic', type=str, default='', help='Только для конкретной темы')
    args = parser.parse_args()

    if not API_KEY and not args.dry_run:
        print("ОШИБКА: DEEPSEEK_API_KEY не задан!")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)

    print("=" * 70)
    print(f"ГЕНЕРАЦИЯ ЗАДАЧ ДЛЯ {GRADE} КЛАССА — ЗАПОЛНЕНИЕ ДЕФИЦИТОВ")
    print(f"Цель: {TARGET} задач на каждую ячейку (тема × difficulty)")
    print("=" * 70)

    plan = get_deficit_plan(conn)

    # Фильтр по теме
    if args.topic:
        plan = [p for p in plan if args.topic.lower() in p[0].lower()]

    total_deficit = sum(p[3] for p in plan)
    zero_cells = sum(1 for p in plan if p[2] == 0)

    print(f"\nПлан генерации:")
    print(f"  Ячеек с дефицитом: {len(plan)}")
    print(f"  Полных дыр (0 задач): {zero_cells}")
    print(f"  Всего нужно сгенерировать: {total_deficit} задач")

    if args.limit:
        print(f"  Лимит: {args.limit} задач")

    print(f"\nТОП-20 приоритетных ячеек:")
    print(f"{'Тема':<45} {'D':>3} {'Есть':>6} {'Нужно':>6}")
    print("-" * 65)
    for topic, d, cnt, deficit in plan[:20]:
        marker = " ← ДЫРА" if cnt == 0 else ""
        print(f"{topic:<45} {d:>3} {cnt:>6} {deficit:>6}{marker}")

    if args.dry_run:
        print("\n[DRY RUN] Генерация не запущена.")
        conn.close()
        return

    # Генерация
    generated = 0
    errors = 0
    batch_buffer = []

    print(f"\n{'='*70}")
    print("НАЧИНАЕМ ГЕНЕРАЦИЮ...")
    print(f"{'='*70}\n")

    for topic, difficulty, current_count, deficit in plan:
        if args.limit and generated >= args.limit:
            print(f"\nДостигнут лимит {args.limit} задач.")
            break

        # Сколько нужно сгенерировать для этой ячейки
        need = min(deficit, (args.limit - generated) if args.limit else deficit)

        for i in range(need):
            if args.limit and generated >= args.limit:
                break

            print(f"[{generated+1}] {topic[:40]} | D={difficulty} | ({current_count+i+1}/{TARGET})")

            try:
                prompt = build_prompt(topic, difficulty, current_count + i)
                raw = call_api(prompt)
                data = parse_response(raw)

                task_text = data.get('task_text', '').strip()
                correct_answer = str(data.get('correct_answer', '')).strip()
                solution = data.get('solution', '').strip()

                if not task_text or not correct_answer:
                    print(f"  ⚠️  Пустой ответ, пропускаем")
                    errors += 1
                    continue

                task_id = insert_task(conn, topic, difficulty, task_text, correct_answer, solution)
                generated += 1
                batch_buffer.append(task_id)

                print(f"  ✅ ID={task_id} | Ответ: {correct_answer[:30]}")

                # Коммит каждые BATCH_SIZE задач
                if len(batch_buffer) >= BATCH_SIZE:
                    conn.commit()
                    print(f"  💾 Batch commit ({len(batch_buffer)} задач)")
                    batch_buffer = []

                time.sleep(SLEEP_BETWEEN)

            except Exception as e:
                print(f"  ❌ Ошибка: {e}")
                errors += 1
                time.sleep(5)
                continue

    # Финальный коммит
    if batch_buffer:
        conn.commit()
        print(f"\n💾 Финальный commit ({len(batch_buffer)} задач)")

    print(f"\n{'='*70}")
    print(f"ГЕНЕРАЦИЯ ЗАВЕРШЕНА")
    print(f"  Сгенерировано: {generated} задач")
    print(f"  Ошибок: {errors}")
    print(f"{'='*70}")

    conn.close()


if __name__ == '__main__':
    main()
