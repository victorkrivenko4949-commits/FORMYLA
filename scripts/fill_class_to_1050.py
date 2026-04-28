#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
УНИВЕРСАЛЬНЫЙ ГЕНЕРАТОР задач для адаптивного теста.
Заполняет класс до целевого количества (по умолчанию 1050),
равномерно распределяя по ячейкам (тема x сложность).

Запуск:
  python scripts/fill_class_to_1050.py --grade 5 --dry-run
  python scripts/fill_class_to_1050.py --grade 5
  python scripts/fill_class_to_1050.py --grade 8 --target 1050 --batch-size 50

Флаги:
  --grade N        Класс (обязательный)
  --target N       Целевое количество задач (по умолчанию 1050)
  --dry-run        Только показать план, не генерировать
  --batch-size N   Размер порции для коммита (по умолчанию 50)
"""

import sys, io, os, json, time, sqlite3, requests, re, argparse, hashlib
from datetime import datetime
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DB_PATH = "instance/formyla.db"
SLEEP_BETWEEN = 2
MAX_RETRIES_PER_CELL = 3
MIN_PER_CELL = 4

from dotenv import load_dotenv
load_dotenv()
API_KEY = os.environ.get('DEEPSEEK_API_KEY', '')
API_URL = "https://api.deepseek.com/v1/chat/completions"
MODEL = "deepseek-chat"

# ─── Программы по классам ─────────────────────────────────────────────────────
CURRICULUM = {
    5: """5 КЛАСС: арифметика (делимость, остатки, дроби), логика (рыцари/лжецы),
комбинаторика (правило суммы/произведения), геометрия (клетчатая бумага, разрезания),
числовые ребусы, принцип Дирихле, инварианты, взвешивания/переливания, текстовые задачи, графы.""",

    6: """6 КЛАСС: дроби/пропорции, делимость (признаки, НОД/НОК), геометрия (периметры/площади,
разрезания/замощения), комбинаторика, логика (рыцари/лжецы), инварианты (четность, раскраски),
принцип Дирихле, графы, текстовые задачи, числовые ребусы.""",

    7: """7 КЛАСС: алгебра (линейные уравнения/системы, тождества, неравенства),
теория чисел (делимость, НОД/НОК, остатки, диофантовы уравнения),
комбинаторика (перестановки, размещения, сочетания), логика (инварианты, четность),
геометрия (равенство треугольников, углы, площади), графы, функции и графики.""",

    8: """8 КЛАСС: алгебра (квадратные уравнения, системы, тождества),
геометрия (подобие, теорема Пифагора, окружности), теория чисел (сравнения по модулю),
комбинаторика (биномиальные коэффициенты, включения-исключения),
неравенства (AM-GM), графы, функции и графики, геометрические доказательства.""",

    9: """9 КЛАСС: алгебра (многочлены, параметры), геометрия (тригонометрия, теоремы синусов/косинусов),
теория чисел (функция Эйлера, теорема Ферма), комбинаторика (рекуррентности),
неравенства (AM-GM, Коши-Шварца), логика и инварианты, функции и графики.""",

    10: """10 КЛАСС: функциональные уравнения, последовательности, стереометрия,
теория чисел (p-адические оценки), экстремальная комбинаторика,
неравенства (Шура, Мюрхеда), сложные функциональные уравнения.""",
}

DIFFICULTY_DESC = {
    1: "очень легкая олимпиадная (школьный этап, первые задачи)",
    2: "легкая олимпиадная (школьный этап, средние задачи)",
    3: "средняя олимпиадная (муниципальный этап)",
    4: "сложная олимпиадная (региональный этап)",
    5: "очень сложная олимпиадная (всероссийский/международный)",
}

COST_PER_1K_INPUT = 0.00014
COST_PER_1K_OUTPUT = 0.00028
AVG_INPUT_TOKENS = 500
AVG_OUTPUT_TOKENS = 800


def normalize_text(text):
    if not text:
        return ""
    t = text.lower().strip()
    t = re.sub(r'\s+', '', t)
    t = re.sub(r'\\[a-zA-Z]+', '', t)
    t = re.sub(r'[{}\[\]()$\\]', '', t)
    t = re.sub(r'[.,;:!?\xab\xbb\u201c\u201d\'\u2014\u2013\-]', '', t)
    return t


def text_hash(text):
    return hashlib.md5(normalize_text(text).encode('utf-8')).hexdigest()


def check_latex(text):
    if text.count('$') % 2 != 0:
        return "непарные $"
    if re.search(r'\$ *rac\{', text):
        return "$ rac{ (потерянный \\f)"
    if re.search(r'\\\\[a-z]', text):
        return "двойной бэкслэш"
    ob = text.count('{')
    cb = text.count('}')
    if ob != cb and (ob > 0 or cb > 0):
        return "непарные {}"
    return None


def validate_task(task_text, answer, existing_hashes):
    if not task_text or len(task_text.strip()) < 30:
        return False, "условие < 30 символов"
    if not answer or not answer.strip():
        return False, "пустой ответ"
    if len(task_text) > 1500:
        return False, "условие > 1500 символов"
    issue = check_latex(task_text)
    if issue:
        return False, "LaTeX: " + issue
    if text_hash(task_text) in existing_hashes:
        return False, "дубликат"
    return True, "ok"


def build_prompt(grade, topic, difficulty):
    cur = CURRICULUM.get(grade, "")
    dd = DIFFICULTY_DESC[difficulty]
    return (
        f"Ты - эксперт по олимпиадной математике для школьников.\n\n"
        f"Сгенерируй ОДНУ оригинальную олимпиадную задачу для {grade} класса.\n\n"
        f"ТЕМА: {topic}\n"
        f"СЛОЖНОСТЬ: {difficulty}/5 - {dd}\n"
        f"ПРОГРАММА: {cur}\n\n"
        f"ТРЕБОВАНИЯ:\n"
        f"1. Задача точно соответствует теме \"{topic}\" и уровню {grade} класса\n"
        f"2. Сложность {difficulty}/5: {dd}\n"
        f"3. Задача ОРИГИНАЛЬНАЯ (не из известных олимпиад)\n"
        f"4. Условие четкое, однозначное, с числовым ответом\n"
        f"5. ВСЕ формулы в $...$: $\\frac{{a}}{{b}}$, $x^2$, $\\sqrt{{n}}$\n"
        f"6. НЕ используй \\frac, \\sqrt ВНЕ долларов $\n"
        f"7. Решение полное и понятное для {grade}-классника\n"
        f"8. Условие от 50 до 500 символов\n\n"
        f"Верни ТОЛЬКО валидный JSON (без markdown, без ```):\n"
        f'{{"condition": "текст задачи", "answer": "числовой ответ", "solution": "решение"}}'
    )


def call_api(prompt):
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.85,
        "max_tokens": 3000,
    }
    resp = requests.post(API_URL, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()['choices'][0]['message']['content']


def parse_response(raw):
    raw = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', raw)
    raw = re.sub(r'^```json\s*', '', raw.strip())
    raw = re.sub(r'\s*```$', '', raw.strip())
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if not match:
        raise ValueError(f"JSON не найден: {raw[:200]}")
    return json.loads(match.group())


def insert_task(conn, grade, topic, difficulty, task_text, answer, solution):
    cur = conn.cursor()
    c1 = f"Правильный ответ: {answer}"
    c2 = "Полное решение с обоснованием"
    cur.execute("""
        INSERT INTO adaptive_tasks
        (class_level, topic, difficulty_level, task_text, correct_answer, solution,
         criteria_1_point, criteria_2_points, is_flagged, attempts_count, solves_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0)
    """, (grade, topic, difficulty, task_text, answer, solution, c1, c2))
    return cur.lastrowid


def get_topics(conn, grade):
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT topic FROM adaptive_tasks WHERE class_level=? ORDER BY topic", (grade,))
    return [r[0] for r in cur.fetchall()]


def get_matrix(conn, grade):
    cur = conn.cursor()
    cur.execute("""
        SELECT topic, difficulty_level, COUNT(*) FROM adaptive_tasks
        WHERE class_level=? GROUP BY topic, difficulty_level
    """, (grade,))
    return {(r[0], r[1]): r[2] for r in cur.fetchall()}


def build_hashes(conn, grade):
    cur = conn.cursor()
    cur.execute("SELECT task_text FROM adaptive_tasks WHERE class_level=?", (grade,))
    return {text_hash(r[0]) for r in cur.fetchall() if r[0]}


def build_plan(matrix, topics, target):
    current_total = sum(matrix.values())
    global_need = max(0, target - current_total)
    if global_need == 0:
        return [], current_total, global_need

    num_cells = len(topics) * 5
    tpc = max(MIN_PER_CELL, target // max(num_cells, 1))

    plan = []
    for topic in topics:
        for d in range(1, 6):
            cur_count = matrix.get((topic, d), 0)
            cell_need = max(0, tpc - cur_count)
            if cell_need > 0:
                plan.append({'topic': topic, 'difficulty': d, 'current': cur_count, 'need': cell_need})

    plan.sort(key=lambda x: (-1 if x['current'] == 0 else 0, -x['need']))

    total_planned = sum(p['need'] for p in plan)
    if total_planned > global_need:
        ratio = global_need / total_planned
        remaining = global_need
        for p in plan:
            p['need'] = max(1, int(p['need'] * ratio))
            remaining -= p['need']
        i = 0
        while remaining > 0 and i < len(plan):
            plan[i]['need'] += 1
            remaining -= 1
            i += 1
        total_now = sum(p['need'] for p in plan)
        while total_now > global_need:
            for p in reversed(plan):
                if p['need'] > 1 and total_now > global_need:
                    p['need'] -= 1
                    total_now -= 1

    plan = [p for p in plan if p['need'] > 0]
    return plan, current_total, global_need


def estimate_cost(n):
    ic = n * AVG_INPUT_TOKENS / 1000 * COST_PER_1K_INPUT
    oc = n * AVG_OUTPUT_TOKENS / 1000 * COST_PER_1K_OUTPUT
    return (ic + oc) * 1.15


def print_matrix(matrix_data, topics_list, title):
    all_diffs = sorted(set(d for _, d in matrix_data.keys()))
    if not all_diffs:
        all_diffs = [1, 2, 3, 4, 5]
    header = f"  {'Тема':<40}"
    for d in all_diffs:
        header += f" d={d:>2}"
    header += "  ИТОГО"
    print(header)
    print(f"  {'─'*40}" + "─────" * len(all_diffs) + "───────")
    for topic in topics_list:
        row = f"  {topic[:40]:<40}"
        rt = 0
        for d in all_diffs:
            c = matrix_data.get((topic, d), 0)
            row += f" {c:>4}"
            rt += c
        row += f"  {rt:>5}"
        print(row)
    total_row = f"  {'ИТОГО':<40}"
    grand = 0
    for d in all_diffs:
        ct = sum(matrix_data.get((t, d), 0) for t in topics_list)
        total_row += f" {ct:>4}"
        grand += ct
    total_row += f"  {grand:>5}"
    print(f"  {'─'*40}" + "─────" * len(all_diffs) + "───────")
    print(total_row)


def main():
    parser = argparse.ArgumentParser(description='Универсальный генератор задач')
    parser.add_argument('--grade', type=int, required=True, help='Класс (5-10)')
    parser.add_argument('--target', type=int, default=1050, help='Целевое кол-во (по умолчанию 1050)')
    parser.add_argument('--dry-run', action='store_true', help='Только план')
    parser.add_argument('--batch-size', type=int, default=50, help='Размер порции (по умолчанию 50)')
    args = parser.parse_args()

    grade = args.grade
    target = args.target
    batch_size = args.batch_size

    if grade not in CURRICULUM:
        print(f"ОШИБКА: класс {grade} не поддерживается. Доступны: {list(CURRICULUM.keys())}")
        sys.exit(1)

    if not API_KEY and not args.dry_run:
        print("ОШИБКА: DEEPSEEK_API_KEY не задан!")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)

    print("=" * 70)
    print(f"ГЕНЕРАТОР ЗАДАЧ — {grade} КЛАСС")
    print(f"Цель: {target} задач | Режим: {'DRY-RUN' if args.dry_run else 'ГЕНЕРАЦИЯ'}")
    print("=" * 70)

    topics = get_topics(conn, grade)
    matrix = get_matrix(conn, grade)
    current_total = sum(matrix.values())

    print(f"\nТекущее состояние: {current_total} задач, {len(topics)} тем")

    if current_total >= target:
        print(f"\n Уже >= {target} задач. Генерация не нужна.")
        conn.close()
        sys.exit(0)

    plan, current_total, global_need = build_plan(matrix, topics, target)
    total_planned = sum(p['need'] for p in plan)
    holes = sum(1 for p in plan if p['current'] == 0)

    print(f"\n{'─'*70}")
    print(f"ПЛАН ГЕНЕРАЦИИ")
    print(f"{'─'*70}")
    print(f"  Нужно: {global_need} задач (глобальный CAP)")
    print(f"  Запланировано: {total_planned} задач")
    print(f"  Ячеек с дефицитом: {len(plan)}, полных дыр: {holes}")

    cost = estimate_cost(total_planned)
    est_min = total_planned * (SLEEP_BETWEEN + 3) / 60
    print(f"  Стоимость API: ~${cost:.2f}")
    print(f"  Время: ~{est_min:.0f} мин ({est_min/60:.1f} ч)")

    if cost > 5.0:
        print(f"  ВНИМАНИЕ: стоимость > $5!")

    print(f"\n  {'Тема':<45} {'D':>3} {'Есть':>6} {'Нужно':>6}")
    print(f"  {'-'*65}")
    for p in plan[:30]:
        mk = " <- ДЫРА" if p['current'] == 0 else ""
        print(f"  {p['topic'][:45]:<45} {p['difficulty']:>3} {p['current']:>6} {p['need']:>6}{mk}")
    if len(plan) > 30:
        print(f"  ... и ещё {len(plan) - 30} ячеек")

    # Прогноз
    print(f"\n{'─'*70}")
    print(f"ПРОГНОЗ ПОСЛЕ ГЕНЕРАЦИИ")
    print(f"{'─'*70}")
    projected = dict(matrix)
    for p in plan:
        key = (p['topic'], p['difficulty'])
        projected[key] = projected.get(key, 0) + p['need']
    all_topics_proj = sorted(set(t for t, _ in projected.keys()))
    print_matrix(projected, all_topics_proj, "Прогноз")

    if args.dry_run:
        print(f"\n{'='*70}")
        print(f"DRY-RUN: генерация не запущена.")
        print(f"Для запуска: python scripts/fill_class_to_1050.py --grade {grade}")
        print(f"{'='*70}")
        conn.close()
        return

    # ─── ГЕНЕРАЦИЯ ─────────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"НАЧИНАЕМ ГЕНЕРАЦИЮ ({total_planned} задач)")
    print(f"{'='*70}\n")

    existing_hashes = build_hashes(conn, grade)
    generated = 0
    rejected = 0
    api_calls = 0
    batch_buffer = []
    start_time = time.time()

    for p in plan:
        topic = p['topic']
        difficulty = p['difficulty']
        need = p['need']
        consecutive_failures = 0

        for i in range(need):
            if generated >= global_need:
                print(f"\n  Достигнут глобальный CAP: {global_need} задач!")
                break

            if consecutive_failures >= MAX_RETRIES_PER_CELL:
                skipped = need - i
                print(f"  Пропускаем ячейку ({topic[:30]}, d={difficulty}): "
                      f"{MAX_RETRIES_PER_CELL} неудач, пропущено {skipped}")
                rejected += skipped
                break

            attempt = 0
            success = False

            while attempt < MAX_RETRIES_PER_CELL and not success:
                attempt += 1
                try:
                    prompt = build_prompt(grade, topic, difficulty)
                    raw = call_api(prompt)
                    api_calls += 1
                    data = parse_response(raw)

                    task_text = (data.get('condition') or data.get('task_text', '')).strip()
                    answer = str(data.get('answer') or data.get('correct_answer', '')).strip()
                    solution = data.get('solution', '').strip()

                    ok, reason = validate_task(task_text, answer, existing_hashes)
                    if not ok:
                        print(f"  [отклонено, попытка {attempt}] {reason}")
                        rejected += 1
                        consecutive_failures += 1
                        time.sleep(1)
                        continue

                    task_id = insert_task(conn, grade, topic, difficulty, task_text, answer, solution)
                    generated += 1
                    consecutive_failures = 0
                    batch_buffer.append(task_id)
                    existing_hashes.add(text_hash(task_text))

                    print(f"  [{grade} класс] +{generated}/{global_need} | "
                          f"{topic[:30]} d={difficulty} | ID={task_id}")

                    if len(batch_buffer) >= batch_size:
                        conn.commit()
                        elapsed = time.time() - start_time
                        rate = generated / elapsed * 60 if elapsed > 0 else 0
                        print(f"\n  Batch commit ({len(batch_buffer)} задач) | "
                              f"{rate:.1f} задач/мин | {elapsed/60:.1f} мин\n")
                        batch_buffer = []

                    success = True
                    time.sleep(SLEEP_BETWEEN)

                except json.JSONDecodeError as e:
                    print(f"  JSON ошибка (попытка {attempt}): {e}")
                    rejected += 1
                    consecutive_failures += 1
                    api_calls += 1
                    time.sleep(2)

                except requests.exceptions.RequestException as e:
                    print(f"  API ошибка (попытка {attempt}): {e}")
                    consecutive_failures += 1
                    api_calls += 1
                    time.sleep(10)

                except Exception as e:
                    print(f"  Ошибка (попытка {attempt}): {e}")
                    rejected += 1
                    consecutive_failures += 1
                    api_calls += 1
                    time.sleep(3)

        if generated >= global_need:
            break

    # Финальный коммит
    if batch_buffer:
        conn.commit()
        print(f"\n  Финальный commit ({len(batch_buffer)} задач)")

    elapsed = time.time() - start_time

    # ─── ОТЧЁТ ─────────────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"ОТЧЁТ О ГЕНЕРАЦИИ — {grade} КЛАСС")
    print(f"{'='*70}")
    print(f"  Было задач:        {current_total}")
    print(f"  Сгенерировано:     {generated}")
    print(f"  Отклонено:         {rejected}")
    print(f"  API вызовов:       {api_calls}")
    print(f"  Время:             {elapsed/60:.1f} мин")
    if elapsed > 0:
        print(f"  Скорость:          {generated/elapsed*60:.1f} задач/мин")

    # Финальная матрица
    final_matrix = get_matrix(conn, grade)
    final_total = sum(final_matrix.values())
    final_topics = sorted(set(t for t, _ in final_matrix.keys()))
    print(f"\n  Итого задач:       {final_total}")
    print(f"\n{'─'*70}")
    print(f"ФИНАЛЬНАЯ МАТРИЦА")
    print(f"{'─'*70}")
    print_matrix(final_matrix, final_topics, "Финал")

    conn.close()
    print(f"\n{'='*70}")
    print("Готово!")


if __name__ == '__main__':
    main()
