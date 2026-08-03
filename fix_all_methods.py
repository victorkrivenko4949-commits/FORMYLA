#!/usr/bin/env python3
"""Diagnostic + Fix script for:
Problem 1: E8, E12, E14, E15, F3 — truncated last task (missing Ответ/Что было главным)
Problem 2: G1,G2,G3,G4,G5,G7,H3,H5,E5a,F14,F15,F16,F17 — тренировочная first task
"""

import json
import re
import sys
import time
import requests
import urllib3
import traceback

urllib3.disable_warnings()

API_KEY = 'sk-ad477f779a1045cba3cc09100e908370'
API_URL = 'https://api.deepseek.com/chat/completions'
MODEL = 'deepseek-v4-pro'

METHODS_FILE = 'all_methods_real_final.json'
OUTPUT_FILE = 'all_methods_real_final.json'

PROBLEM1_CODES = ['E8', 'E12', 'E14', 'E15', 'F3']
PROBLEM2_CODES = ['G1', 'G2', 'G3', 'G4', 'G5', 'G7', 'H3', 'H5', 'E5a', 'F14', 'F15', 'F16', 'F17']

with open(METHODS_FILE, 'r', encoding='utf-8') as f:
    methods = json.load(f)

print(f'Loaded {len(methods)} methods', flush=True)

# ============================================================================
# STEP 0: FULL DIAGNOSTIC
# ============================================================================

print("\n" + "=" * 80)
print("FULL DIAGNOSTIC")
print("=" * 80)

all_ok = True

for m in methods:
    code = m['method_code']
    we = m.get('worked_example_md', '')
    tasks = we.split('### Задача')
    num_tasks = len(tasks) - 1
    if num_tasks == 0:
        print(f"[{code}] ERROR: No tasks found!")
        all_ok = False
        continue

    issues = []
    for i in range(1, len(tasks)):
        task_text = tasks[i]
        has_answer = '**Ответ:**' in task_text
        has_main = '**Что было главным:**' in task_text
        if not has_answer:
            issues.append(f'Task {i} missing Ответ')
        if not has_main:
            issues.append(f'Task {i} missing Что было главным')

    # Check first task for тренировочная
    task1_text = tasks[1] if len(tasks) > 1 else ''
    src_match = re.search(r'\*\*Источник:\*\*\s*(.*?)(?:\n|$)', task1_text)
    src_line = src_match.group(1) if src_match else ''
    is_training = 'тренировочная' in src_line.lower() or 'классическая задача' in src_line.lower()

    if issues or is_training:
        all_ok = False
        print(f"[{code}] ISSUES: issues={issues}, training_first={is_training}")
    else:
        print(f"[{code}] OK ({num_tasks} tasks)")

if all_ok:
    print("\nALL 102 METHODS ARE ALREADY OK! No fixes needed.")
    sys.exit(0)

# ============================================================================
# STEP 1: FIX PROBLEM 1 — truncated last tasks
# ============================================================================

print("\n" + "=" * 80)
print("STEP 1: FIXING TRUNCATED LAST TASKS (Problem 1)")
print("=" * 80)

SYSTEM_PROMPT_FIX_TRUNCATED = """Ты — эксперт по олимпиадной математике и методист.
Тебе дан текст последней задачи из разбора метода. Задача обрезана — нет секций **Ответ:** и **Что было главным:**.
Твоя задача: написать **Ответ:** и **Что было главным:** основываясь на тексте задачи и решении.
Верни ТОЛЬКО эти две секции в формате:

**Ответ:** [правильный ответ, LaTeX в $...$]

**Что было главным:** [ключевой вывод метода, 1-2 предложения]

НЕ повторяй весь текст задачи. Только эти две секции."""


def fix_truncated_task(code, name, last_task_text):
    """Call DeepSeek to complete the truncated last task."""
    # Take last 2000 chars as context
    context = last_task_text[-2000:]

    payload = {
        'model': MODEL,
        'messages': [
            {'role': 'system', 'content': SYSTEM_PROMPT_FIX_TRUNCATED},
            {'role': 'user', 'content': f'Метод {code}: {name}\n\nТекст последней задачи (обрезан):\n{context}'}
        ],
        'max_tokens': 2000,
        'temperature': 0.3,
    }

    session = requests.Session()
    session.verify = False
    headers = {
        'Authorization': f'Bearer {API_KEY}',
        'Content-Type': 'application/json'
    }

    for attempt in range(10):
        try:
            r = session.post(API_URL, json=payload, headers=headers, timeout=120)
            if r.status_code == 429:
                wait = min(60, 10 * (attempt + 1))
                print(f'      Rate limit (429), waiting {wait}s...', flush=True)
                time.sleep(wait)
                continue
            if r.status_code >= 500:
                wait = min(60, 5 * (attempt + 1))
                print(f'      Server error {r.status_code}, waiting {wait}s...', flush=True)
                time.sleep(wait)
                continue
            if r.status_code != 200:
                print(f'      HTTP {r.status_code}, retrying...', flush=True)
                time.sleep(5)
                continue

            d = r.json()
            content = d['choices'][0]['message'].get('content', '') or ''
            if not content:
                print(f'      Empty response, retrying...', flush=True)
                time.sleep(5)
                continue

            return content

        except Exception as e:
            print(f'      Error: {str(e)[:80]}, retrying...', flush=True)
            time.sleep(10)

    return None


PROBLEM1_MAP = {m['method_code']: m for m in methods if m['method_code'] in PROBLEM1_CODES}

for code, m in PROBLEM1_MAP.items():
    we = m.get('worked_example_md', '')
    tasks = we.split('### Задача')

    last_idx = len(tasks) - 1
    last_task = tasks[last_idx]
    has_answer = '**Ответ:**' in last_task
    has_main = '**Что было главным:**' in last_task

    if has_answer and has_main:
        print(f"[{code}] Last task already complete, skipping", flush=True)
        continue

    print(f"\n[{code}] Fixing truncated last task...", flush=True)
    print(f"  Last 200 chars: {last_task[-200:]}", flush=True)

    completion = fix_truncated_task(code, m['method_name'], last_task)

    if completion:
        # Append to the last task
        we = we.rstrip()
        we += '\n\n' + completion.strip()
        m['worked_example_md'] = we
        print(f"[{code}] COMPLETED: {completion[:150]}...", flush=True)
    else:
        print(f"[{code}] FAILED to get completion from DeepSeek", flush=True)

# Save after Problem 1
with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
    json.dump(methods, f, ensure_ascii=False, indent=2)
print(f"\nSaved after Problem 1 fixes to {OUTPUT_FILE}", flush=True)

print("\n" + "=" * 80)
print("STEP 1 DONE")
print("=" * 80)
