#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate L1-L5 tasks for grade 5 adaptive test."""
import json, time, os, sys, psycopg2
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ai.deepseek_client import DeepSeekClient
from utils.safe_json import safe_parse_llm_json
from prompts.adaptive_gen_prompt import ADAPTIVE_GEN_SYSTEM, ADAPTIVE_GEN_USER

DB_URL = (os.environ.get('DATABASE_URL') or
          os.environ.get('EXTERNAL_DATABASE_URL') or
          'postgresql://formyla_user:HwFVHpWWNFZzLvB1m6aXAKfeijKLqtGe'
          '@dpg-d7n8uo0g4nts73b1n9k0-a.ohio-postgres.render.com'
          '/formyla?sslmode=require')

PLAN_FILE = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'data', 'audit', 'grade5_gen_plan.json')
CHECKPOINT = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'data', 'audit', 'gen_progress_grade5.json')

os.makedirs(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'data', 'logs'), exist_ok=True)
LOG = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'data', 'logs',
    f'gen_grade5_{datetime.now():%Y%m%d_%H%M}.log')

client = DeepSeekClient()


def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    line = f'{ts} {msg}'
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(line + '\n')
    print(line)


def gen_one(topic, difficulty):
    user_msg = ADAPTIVE_GEN_USER.format(
        grade=5, topic=topic, difficulty=difficulty)
    raw = client.generate(
        prompt=user_msg,
        system_prompt=ADAPTIVE_GEN_SYSTEM,
        temperature=0.7,
        max_tokens=1500
    )
    parsed = safe_parse_llm_json(raw)
    if parsed and '_parse_error' not in parsed:
        return parsed
    return None


def save_to_staging(task, topic, difficulty):
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO adaptive_tasks
        (class_level, difficulty_level, topic, task_text,
         solution, criteria_1_point, criteria_2_points,
         correct_answer, created_at)
        VALUES (5, %s, %s, %s, %s, %s, %s, %s, NOW())
    """, (
        difficulty,
        topic,
        task.get('condition', ''),
        task.get('solution', ''),
        'L' + str(difficulty) + ': ' + task.get('answer', ''),
        task.get('solution', '')[:200],
        task.get('answer', ''),
    ))
    conn.commit()
    conn.close()


def main():
    plan = json.load(open(PLAN_FILE, encoding='utf-8'))
    plan_easy = [p for p in plan if p['difficulty'] <= 5]

    # Load checkpoint
    done = {}
    if os.path.exists(CHECKPOINT):
        done = json.load(open(CHECKPOINT, encoding='utf-8'))

    total_target = sum(p['count'] for p in plan_easy)
    total_done = sum(done.values())
    log(f'START. Target: {total_target}, already done: {total_done}')

    errors_in_row = 0
    generated = 0
    PAUSE_AT = 500  # Full run approved after first 50 review

    for item in plan_easy:
        key = f"{item['topic']}|{item['difficulty']}"
        already = done.get(key, 0)
        need = item['count'] - already
        if need <= 0:
            continue

        log(f">>> {item['topic']} L{item['difficulty']} need {need}")

        for i in range(need):
            if generated >= PAUSE_AT:
                log(f'=== PAUSED at {generated} tasks for review ===')
                json.dump(done, open(CHECKPOINT, 'w', encoding='utf-8'),
                          indent=2, ensure_ascii=False)
                return

            task = gen_one(item['topic'], item['difficulty'])
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
                save_to_staging(task, item['topic'], item['difficulty'])
                errors_in_row = 0
                done[key] = done.get(key, 0) + 1
                generated += 1
                cond = task.get('condition', '')[:60]
                log(f'  OK {i+1}/{need} [{generated}] {cond}...')
            except Exception as e:
                log(f'  X DB error: {e}')
                errors_in_row += 1

            if done.get(key, 0) % 10 == 0:
                json.dump(done, open(CHECKPOINT, 'w', encoding='utf-8'),
                          indent=2, ensure_ascii=False)

            time.sleep(1)

        json.dump(done, open(CHECKPOINT, 'w', encoding='utf-8'),
                  indent=2, ensure_ascii=False)
        time.sleep(5)

    log(f'=== DONE. Total generated: {sum(done.values())} ===')


if __name__ == '__main__':
    main()
