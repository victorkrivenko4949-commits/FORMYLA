#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Multi-threaded generator to fill topic gaps across all grades.
Target: 175 tasks per topic per grade (6 topics × 175 = 1050).
Uses 30 concurrent threads with DeepSeek API + HTTP push to Render.

Usage: python scripts/_gen_fill_gaps.py
"""

import json, time, os, sys, re, threading, queue
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

# ─── Config ───
RENDER_URL = 'https://formyla-com.onrender.com'
MIGRATE_SECRET = 'formyla-migrate-2026'
API_KEY = os.environ.get('DEEPSEEK_API_KEY')
API_URL = "https://api.deepseek.com/v1/chat/completions"
MAX_THREADS = 30
TARGET_PER_TOPIC = 175  # per grade per topic

# ─── 6 canonical topics with their DB-level names ───
TOPIC_NAMES = {
    'algebra': {
        5: 'Дроби, доли и пропорции',
        6: 'Дроби, доли и пропорции',
        7: 'Алгебраические тождества и преобразования',
        8: 'Алгебраические тождества и преобразования',
        9: 'Алгебраические тождества и преобразования',
        10: 'Алгебра (уравнения, неравенства, системы)',
        11: 'Алгебра (полиномы, системы, параметры)',
    },
    'geometry': {
        5: 'Геометрия (периметры и площади)',
        6: 'Геометрия (периметры и площади)',
        7: 'Начала геометрии',
        8: 'Начала геометрии',
        9: 'Начала геометрии',
        10: 'Геометрия (планиметрия, окружности)',
        11: 'Планиметрия (окружности, подобие, площади)',
    },
    'number_theory': {
        5: 'Делимость, остатки и последняя цифра',
        6: 'НОД, НОК и основная теорема арифметики',
        7: 'Теория чисел',
        8: 'Теория чисел',
        9: 'Теория чисел',
        10: 'Теория чисел',
        11: 'Теория чисел (делимость, сравнения, диофантовы)',
    },
    'combinatorics': {
        5: 'Комбинаторика (правило суммы и произведения)',
        6: 'Комбинаторика (правило суммы и произведения)',
        7: 'Комбинаторика (правило суммы и произведения)',
        8: 'Комбинаторика (правило суммы и произведения)',
        9: 'Комбинаторика (правило суммы и произведения)',
        10: 'Комбинаторика',
        11: 'Комбинаторика и вероятность',
    },
    'movement': {
        5: 'Задачи на движение',
        6: 'Задачи на движение',
        7: 'Задачи на движение',
        8: 'Задачи на движение',
        9: 'Задачи на движение',
        10: 'Задачи на движение',
        11: 'Задачи на движение',
    },
    'logic': {
        5: 'Логика (рыцари и лжецы, логические таблицы)',
        6: 'Логика (рыцари и лжецы, логические таблицы)',
        7: 'Логика (рыцари и лжецы, логические таблицы)',
        8: 'Логика и инварианты',
        9: 'Логика и инварианты',
        10: 'Логика и инварианты',
        11: 'Логика и инварианты',
    },
}

# Current counts from audit - UPDATED after round 5
CURRENT = {
    5:  {'algebra': 290, 'geometry': 197, 'number_theory': 175, 'combinatorics': 575, 'movement': 175, 'logic': 175},
    6:  {'algebra': 175, 'geometry': 198, 'number_theory': 198, 'combinatorics': 378, 'movement': 175, 'logic': 175},
    7:  {'algebra': 272, 'geometry': 201, 'number_theory': 175, 'combinatorics': 330, 'movement': 175, 'logic': 174},
    8:  {'algebra': 284, 'geometry': 218, 'number_theory': 211, 'combinatorics': 272, 'movement': 175, 'logic': 175},
    9:  {'algebra': 372, 'geometry': 249, 'number_theory': 175, 'combinatorics': 205, 'movement': 175, 'logic': 175},
    10: {'algebra': 436, 'geometry': 243, 'number_theory': 175, 'combinatorics': 175, 'movement': 175, 'logic': 175},
    11: {'algebra': 481, 'geometry': 312, 'number_theory': 175, 'combinatorics': 175, 'movement': 175, 'logic': 175},
}

# ─── Prompt ───
SYSTEM_PROMPT = """Ты методист, составляющий задачи для адаптивного теста по математике для российских школьников 5-11 классов.

ВАЖНО: используй ТОЛЬКО математический аппарат, доступный в указанном классе.

ШКАЛА СЛОЖНОСТИ:
L1 - Школьная программа. Стандартная задача из учебника, 1-2 шага.
L2 - Повышенная сложность. Доп. главы учебника, 2-3 шага.
L3 - Муниципальный этап ВсОШ (нижняя половина). Одна нестандартная идея, 3-4 шага.
L4 - Муниципальный этап ВсОШ (верхняя половина). Две идеи, 4-5 шагов.
L5 - Региональный этап ВсОШ. Серьезная олимпиадная задача с доказательством.

ОГРАНИЧЕНИЯ ПО АППАРАТУ (КРИТИЧНО!):
5 класс: натуральные числа, дроби, простая геометрия. НЕТ: уравнений с x, степеней >2, отрицательных чисел.
6 класс: + отрицательные числа, простейшие уравнения, пропорции, проценты.
7 класс: многочлены, формулы сокр. умножения, признаки равенства треугольников.
8 класс: квадратные уравнения, теорема Пифагора, подобие, окружность.
9-11: вся школьная программа.

ТРЕБОВАНИЯ К ЗАДАЧЕ:
1. Условие на русском, четкое, однозначное.
2. Математика в LaTeX: $x^2$, $\\frac{a}{b}$.
3. Числа реалистичные.
4. Решение 3-7 шагов с обоснованием.
5. Краткий итоговый ответ.
6. Не копировать классику дословно - переформулировать.
7. Каждая задача должна быть УНИКАЛЬНОЙ - не повторять сюжеты и числа.

ФОРМАТ ОТВЕТА - СТРОГО JSON:
{{
  "condition": "<условие>",
  "solution": "<пошаговое решение>",
  "answer": "<краткий ответ>",
  "tags": ["<тег>"],
  "estimated_time_min": <число>,
  "uses_only_grade_program": true,
  "difficulty_justification": "<1-предложение>"
}}
Никакого текста вне JSON."""

USER_PROMPT = """Сгенерируй задачу:
Класс: {grade}
Тема: {topic}
Уровень сложности: {difficulty}

Верни строго JSON."""

# ─── Globals ───
lock = threading.Lock()
stats = {'generated': 0, 'errors': 0, 'pushed': 0}
LOG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'data', 'logs', f'gen_fill_gaps_{datetime.now():%Y%m%d_%H%M}.log')
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)


def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    line = f'{ts} {msg}'
    with lock:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    try:
        print(line, flush=True)
    except:
        pass


def call_api(grade, topic, difficulty):
    """Call DeepSeek API."""
    user_msg = USER_PROMPT.format(grade=grade, topic=topic, difficulty=difficulty)
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg}
        ],
        "temperature": 0.8,
        "max_tokens": 1500
    }
    try:
        resp = requests.post(API_URL, json=payload, headers=headers, timeout=90)
        resp.raise_for_status()
        return resp.json()['choices'][0]['message']['content']
    except Exception as e:
        return None


def parse_json(raw):
    """Parse JSON from LLM response."""
    if not raw:
        return None
    raw = re.sub(r'^```(?:json)?\s*', '', raw.strip())
    raw = re.sub(r'\s*```$', '', raw.strip())
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r'\{[\s\S]*\}', raw)
        if match:
            try:
                return json.loads(match.group())
            except:
                pass
    return None


def push_task(grade, task, topic, difficulty):
    """Push task to Render via HTTP API."""
    row = {
        'class_level': grade,
        'difficulty_level': difficulty,
        'topic': topic,
        'task_text': task.get('condition', ''),
        'solution': task.get('solution', ''),
        'criteria_1_point': f'L{difficulty}: ' + task.get('answer', ''),
        'criteria_2_points': task.get('solution', '')[:200],
        'correct_answer': task.get('answer', ''),
    }
    payload = {
        'secret': MIGRATE_SECRET,
        'table': 'adaptive_tasks',
        'rows': [row]
    }
    try:
        resp = requests.post(f'{RENDER_URL}/api/migrate/push', json=payload, timeout=30)
        return resp.status_code == 200
    except:
        return False


def generate_one(grade, topic_key, topic_name, difficulty):
    """Generate and push one task. Returns True on success."""
    raw = call_api(grade, topic_name, difficulty)
    task = parse_json(raw)
    if task is None:
        with lock:
            stats['errors'] += 1
        return False

    cond = task.get('condition', '')
    if len(cond) < 20:
        with lock:
            stats['errors'] += 1
        return False

    ok = push_task(grade, task, topic_name, difficulty)
    if ok:
        with lock:
            stats['generated'] += 1
            stats['pushed'] += 1
        return True
    else:
        with lock:
            stats['errors'] += 1
        return False


def build_task_queue():
    """Build list of (grade, topic_key, topic_name, difficulty, count) to generate."""
    tasks = []
    total_needed = 0

    for grade in range(5, 12):
        for topic_key in ['algebra', 'geometry', 'number_theory', 'combinatorics', 'movement', 'logic']:
            current = CURRENT[grade][topic_key]
            need = max(0, TARGET_PER_TOPIC - current)
            if need > 0:
                topic_name = TOPIC_NAMES[topic_key][grade]
                # Distribute across difficulty levels 1-5
                per_level = need // 5
                remainder = need % 5
                for diff in range(1, 6):
                    count = per_level + (1 if diff <= remainder else 0)
                    if count > 0:
                        tasks.append((grade, topic_key, topic_name, diff, count))
                        total_needed += count

    return tasks, total_needed


def main():
    log('=' * 70)
    log('FILL GAPS GENERATOR - 30 threads')
    log(f'Target: {TARGET_PER_TOPIC} tasks per topic per grade')
    log(f'API key: {API_KEY[:10]}...' if API_KEY else 'NO API KEY!')
    log(f'Push to: {RENDER_URL}')
    log('=' * 70)

    task_queue, total_needed = build_task_queue()

    # Print plan
    log(f'\nTotal tasks to generate: {total_needed}')
    log(f'Task batches: {len(task_queue)}')
    log('')

    # Show gaps per grade
    for grade in range(5, 12):
        gaps = []
        for tk in ['algebra', 'geometry', 'number_theory', 'combinatorics', 'movement', 'logic']:
            need = max(0, TARGET_PER_TOPIC - CURRENT[grade][tk])
            if need > 0:
                gaps.append(f'{tk}:+{need}')
        if gaps:
            log(f'  Grade {grade}: {", ".join(gaps)}')

    log('')

    if total_needed == 0:
        log('Nothing to generate! All topics at target.')
        return

    # Build flat list of individual tasks
    individual_tasks = []
    for grade, topic_key, topic_name, diff, count in task_queue:
        for _ in range(count):
            individual_tasks.append((grade, topic_key, topic_name, diff))

    log(f'Starting {MAX_THREADS} threads for {len(individual_tasks)} tasks...')
    log('')

    start_time = time.time()
    completed = 0
    failed = 0

    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        futures = {}
        for i, (grade, topic_key, topic_name, diff) in enumerate(individual_tasks):
            future = executor.submit(generate_one, grade, topic_key, topic_name, diff)
            futures[future] = (i, grade, topic_key, diff)

        for future in as_completed(futures):
            i, grade, topic_key, diff = futures[future]
            try:
                success = future.result()
                if success:
                    completed += 1
                else:
                    failed += 1
            except Exception as e:
                failed += 1
                log(f'  Exception: {e}')

            total_done = completed + failed
            if total_done % 50 == 0 or total_done == len(individual_tasks):
                elapsed = time.time() - start_time
                rate = completed / elapsed * 60 if elapsed > 0 else 0
                log(f'  Progress: {total_done}/{len(individual_tasks)} '
                    f'(OK: {completed}, FAIL: {failed}, '
                    f'rate: {rate:.1f}/min, '
                    f'elapsed: {elapsed/60:.1f}min)')

    elapsed = time.time() - start_time
    log('')
    log('=' * 70)
    log(f'DONE! Generated: {completed}, Failed: {failed}')
    log(f'Time: {elapsed/60:.1f} minutes')
    log(f'Rate: {completed/elapsed*60:.1f} tasks/min')
    log('=' * 70)


if __name__ == '__main__':
    main()
