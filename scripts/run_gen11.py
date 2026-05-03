#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Grade 11 generator - uses HTTP API to push tasks (bypasses external DB block)."""
import json, time, os, sys, requests, re
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

# Config
RENDER_URL = 'https://formyla-com.onrender.com'
MIGRATE_SECRET = 'formyla-migrate-2026'
API_KEY = os.environ.get('DEEPSEEK_API_KEY')
API_URL = "https://api.deepseek.com/v1/chat/completions"

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLAN_FILE = os.path.join(BASE_DIR, 'data', 'audit', 'grade11_gen_plan.json')
CHECKPOINT = os.path.join(BASE_DIR, 'data', 'audit', 'gen_progress_grade11.json')
LOG_FILE = os.path.join(BASE_DIR, 'data', 'logs', f'gen_grade11_{datetime.now():%Y%m%d_%H%M}.log')

GRADE = 11

SYSTEM_PROMPT = """Ты методист, составляющий задачи для адаптивного теста по математике для российских школьников 5-11 классов.

ВАЖНО: используй ТОЛЬКО математический аппарат, доступный в указанном классе.

ШКАЛА СЛОЖНОСТИ:
L1 - Школьная программа. Стандартная задача из учебника, 1-2 шага.
L2 - Повышенная сложность. Доп. главы учебника, 2-3 шага.
L3 - Муниципальный этап ВсОШ (нижняя половина). Одна нестандартная идея, 3-4 шага.
L4 - Муниципальный этап ВсОШ (верхняя половина). Две идеи, 4-5 шагов.
L5 - Региональный этап ВсОШ. Серьезная олимпиадная задача с доказательством.

ОГРАНИЧЕНИЯ ПО АППАРАТУ (КРИТИЧНО!):
9-11: вся школьная программа включая производные, интегралы, комплексные числа, стереометрию.

ТРЕБОВАНИЯ К ЗАДАЧЕ:
1. Условие на русском, четкое, однозначное.
2. Математика в LaTeX: $x^2$, $\\frac{a}{b}$.
3. Числа реалистичные.
4. Решение 3-7 шагов с обоснованием.
5. Краткий итоговый ответ.
6. Не копировать классику дословно - переформулировать.

ФОРМАТ ОТВЕТА - СТРОГО JSON:
{
  "condition": "<условие>",
  "solution": "<пошаговое решение>",
  "answer": "<краткий ответ>",
  "tags": ["<тег>"],
  "estimated_time_min": <число>,
  "uses_only_grade_program": true,
  "difficulty_justification": "<1-предложение>"
}
Никакого текста вне JSON.
"""


def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    line = f'{ts} {msg}'
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(line + '\n')
    try:
        print(line, flush=True)
    except:
        pass


def call_api(topic, difficulty):
    """Direct API call to DeepSeek."""
    user_msg = f"Сгенерируй задачу:\nКласс: {GRADE}\nТема: {topic}\nУровень сложности: {difficulty}\n\nВерни строго JSON."

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
        "temperature": 0.7,
        "max_tokens": 1500
    }

    try:
        resp = requests.post(API_URL, json=payload, headers=headers, timeout=90)
        resp.raise_for_status()
        data = resp.json()
        return data['choices'][0]['message']['content']
    except Exception as e:
        log(f'  API error: {e}')
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


def push_task(task, topic, difficulty):
    """Push task to Render via HTTP API."""
    row = {
        'class_level': GRADE,
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

    resp = requests.post(
        f'{RENDER_URL}/api/migrate/push',
        json=payload,
        timeout=30
    )
    if resp.status_code == 200:
        return True
    else:
        log(f'  Push error: {resp.status_code} {resp.text[:100]}')
        return False


def main():
    log(f'API key: {API_KEY[:10]}...' if API_KEY else 'NO API KEY!')
    log(f'Using HTTP push to {RENDER_URL}')

    plan = json.load(open(PLAN_FILE, encoding='utf-8'))
    plan = [p for p in plan if p['difficulty'] <= 5]

    # Load checkpoint
    done = {}
    if os.path.exists(CHECKPOINT):
        done = json.load(open(CHECKPOINT, encoding='utf-8'))

    total_target = sum(p['count'] for p in plan)
    total_done = sum(done.values())
    log(f'START grade {GRADE}. Target: {total_target}, already done: {total_done}')

    errors_in_row = 0
    generated = 0

    for item in plan:
        key = f"{item['topic']}|{item['difficulty']}"
        already = done.get(key, 0)
        need = item['count'] - already
        if need <= 0:
            continue

        log(f">>> {item['topic']} L{item['difficulty']} need {need}")

        for i in range(need):
            raw = call_api(item['topic'], item['difficulty'])
            task = parse_json(raw)

            if task is None:
                errors_in_row += 1
                log(f'  X {i+1}/{need} parse error')
                if errors_in_row >= 3:
                    log('!!! 3 errors in a row, pause 60s')
                    time.sleep(60)
                    errors_in_row = 0
                time.sleep(2)
                continue

            try:
                ok = push_task(task, item['topic'], item['difficulty'])
                if ok:
                    errors_in_row = 0
                    done[key] = done.get(key, 0) + 1
                    generated += 1
                    cond = task.get('condition', '')[:60]
                    log(f'  OK {i+1}/{need} [{generated}] {cond}...')
                else:
                    errors_in_row += 1
            except Exception as e:
                log(f'  X Push exception: {e}')
                errors_in_row += 1

            # Save checkpoint every 10 tasks
            if done.get(key, 0) % 10 == 0:
                json.dump(done, open(CHECKPOINT, 'w', encoding='utf-8'),
                          indent=2, ensure_ascii=False)

            time.sleep(1.5)  # Rate limit: ~40 tasks/min

        json.dump(done, open(CHECKPOINT, 'w', encoding='utf-8'),
                  indent=2, ensure_ascii=False)
        time.sleep(3)

    log(f'=== DONE grade {GRADE}. Total generated: {sum(done.values())} ===')


if __name__ == '__main__':
    main()
