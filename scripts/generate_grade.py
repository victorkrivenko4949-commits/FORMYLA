#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Universal generator for adaptive test tasks. Usage: python scripts/generate_grade.py <grade>
Uses HTTP push to Render (bypasses external DB connection issues)."""
import json, time, os, sys, requests, re
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load .env file for API keys
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

from prompts.adaptive_gen_prompt import ADAPTIVE_GEN_SYSTEM, ADAPTIVE_GEN_USER

# Config
RENDER_URL = 'https://formyla-com.onrender.com'
MIGRATE_SECRET = 'formyla-migrate-2026'
API_KEY = os.environ.get('DEEPSEEK_API_KEY')
API_URL = "https://api.deepseek.com/v1/chat/completions"

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_paths(grade):
    audit_dir = os.path.join(BASE_DIR, 'data', 'audit')
    log_dir = os.path.join(BASE_DIR, 'data', 'logs')
    os.makedirs(log_dir, exist_ok=True)
    return {
        'plan': os.path.join(audit_dir, f'grade{grade}_gen_plan.json'),
        'checkpoint': os.path.join(audit_dir, f'gen_progress_grade{grade}.json'),
        'log': os.path.join(log_dir, f'gen_grade{grade}_{datetime.now():%Y%m%d_%H%M}.log'),
    }


def log(msg, log_file):
    ts = datetime.now().strftime('%H:%M:%S')
    line = f'{ts} {msg}'
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(line + '\n')
    try:
        print(line, flush=True)
    except:
        pass


def call_api(grade, topic, difficulty):
    """Direct API call to DeepSeek."""
    user_msg = ADAPTIVE_GEN_USER.format(grade=grade, topic=topic, difficulty=difficulty)

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": ADAPTIVE_GEN_SYSTEM},
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

    resp = requests.post(
        f'{RENDER_URL}/api/migrate/push',
        json=payload,
        timeout=30
    )
    return resp.status_code == 200


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/generate_grade.py <grade>")
        print("Example: python scripts/generate_grade.py 8")
        sys.exit(1)

    grade = int(sys.argv[1])
    paths = get_paths(grade)

    if not os.path.exists(paths['plan']):
        print(f"Plan file not found: {paths['plan']}")
        print(f"Run: python scripts/gen_plan_any_grade.py {grade} first")
        sys.exit(1)

    plan = json.load(open(paths['plan'], encoding='utf-8'))
    plan_easy = [p for p in plan if p['difficulty'] <= 5]

    # Load checkpoint
    done = {}
    if os.path.exists(paths['checkpoint']):
        done = json.load(open(paths['checkpoint'], encoding='utf-8'))

    total_target = sum(p['count'] for p in plan_easy)
    total_done = sum(done.values())
    log(f'API key: {API_KEY[:10]}...' if API_KEY else 'NO API KEY!', paths['log'])
    log(f'Using HTTP push to {RENDER_URL}', paths['log'])
    log(f'START grade {grade}. Target: {total_target}, already done: {total_done}', paths['log'])

    errors_in_row = 0
    generated = 0

    for item in plan_easy:
        key = f"{item['topic']}|{item['difficulty']}"
        already = done.get(key, 0)
        need = item['count'] - already
        if need <= 0:
            continue

        log(f">>> {item['topic']} L{item['difficulty']} need {need}", paths['log'])

        for i in range(need):
            raw = call_api(grade, item['topic'], item['difficulty'])
            task = parse_json(raw)

            if task is None:
                errors_in_row += 1
                log(f'  X {i+1}/{need} parse error', paths['log'])
                if errors_in_row >= 3:
                    log('!!! 3 errors in a row, pause 60s', paths['log'])
                    time.sleep(60)
                    errors_in_row = 0
                time.sleep(2)
                continue

            try:
                ok = push_task(grade, task, item['topic'], item['difficulty'])
                if ok:
                    errors_in_row = 0
                    done[key] = done.get(key, 0) + 1
                    generated += 1
                    cond = task.get('condition', '')[:60]
                    log(f'  OK {i+1}/{need} [{generated}] {cond}...', paths['log'])
                else:
                    errors_in_row += 1
                    log(f'  X {i+1}/{need} push failed', paths['log'])
            except Exception as e:
                log(f'  X Push exception: {e}', paths['log'])
                errors_in_row += 1

            if done.get(key, 0) % 10 == 0:
                json.dump(done, open(paths['checkpoint'], 'w', encoding='utf-8'),
                          indent=2, ensure_ascii=False)

            time.sleep(1.5)

        json.dump(done, open(paths['checkpoint'], 'w', encoding='utf-8'),
                  indent=2, ensure_ascii=False)
        time.sleep(3)

    log(f'=== DONE grade {grade}. Total generated: {sum(done.values())} ===', paths['log'])


if __name__ == '__main__':
    main()
