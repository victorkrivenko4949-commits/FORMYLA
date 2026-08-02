#!/usr/bin/env python3
"""
FORMYLA L4-L5: ДВУХШАГОВЫЙ ФИКС + АУДИТ
=========================================
thinking=disabled (быстро, стабильно), но ДВА шага:
  Шаг 1: Решить задачу
  Шаг 2: Проверить свой ответ
  Если проверка says wrong → берём правильный ответ из проверки

Фаза 1: Фикс всех wrong (быстро + самопроверка)
Фаза 2: Полный аудит всех 1320 (быстро, 8 потоков)
8 потоков, 50с таймаут, 0.5с задержка
"""
import json, time, re, threading, os
from collections import Counter
from queue import Queue

API_KEY = "sk-ad477f779a1045cba3cc09100e908370"
API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-v4-pro"
INPUT_FILE = "FORMYLA_L1_L5_TOP5.jsonl"
AUDIT_FILE = "L4L5_FINAL_AUDIT.jsonl"
FIXES_FILE = "L4L5_FINAL_FIXES.jsonl"
N_THREADS = 8
MAX_RETRIES = 5

lock = threading.Lock()

def api_call(messages, max_tokens=2000, timeout=50):
    try:
        import requests
    except ImportError:
        os.system('pip install requests')
        import requests
    payload = {
        "model": MODEL, "messages": messages, "max_tokens": max_tokens,
        "temperature": 0.1, "thinking": {"type": "disabled"},
    }
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    for attempt in range(MAX_RETRIES):
        try:
            r = requests.post(API_URL, json=payload, headers=headers, timeout=timeout)
            d = r.json()
            if "error" not in d:
                return d["choices"][0]["message"]["content"]
            if "429" in str(d.get("error", {})):
                time.sleep(5 * (attempt + 1))
                continue
        except Exception as e:
            s = str(e)
            if any(x in s for x in ["prematurely", "SSL", "EOF", "Remote", "Connection",
                                     "Reset", "timeout", "timed", "resolve", "getaddrinfo",
                                     "Max retries", "SSLEOF"]):
                time.sleep(2 * (attempt + 1))
                continue
            time.sleep(2)
    return None

def parse_json(text):
    if not text: return None
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r'^```(json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
    s = text.find('{'); e = text.rfind('}')
    if s >= 0 and e > s:
        try: return json.loads(text[s:e+1])
        except: return None
    return None

def load_tasks():
    with open(INPUT_FILE, encoding='utf-8') as f:
        return [json.loads(l) for l in f if l.strip()]

def save_tasks(tasks):
    with open(INPUT_FILE, 'w', encoding='utf-8') as f:
        for t in tasks:
            f.write(json.dumps(t, ensure_ascii=False, default=str) + '\n')

def load_audit():
    r = {}
    try:
        for l in open(AUDIT_FILE, encoding='utf-8'):
            l = l.strip()
            if l:
                d = json.loads(l)
                if d.get('answer_correct') is not None: r[d['task_uid']] = d
    except: pass
    return r

def save_audit(uid, lvl, g, ac, sc, ca, pv):
    with lock:
        with open(AUDIT_FILE, 'a', encoding='utf-8') as f:
            f.write(json.dumps({'task_uid': uid, 'level': lvl, 'grade': g,
                'answer_correct': ac, 'solution_complete': sc,
                'correct_answer': ca, 'problem_valid': pv}, ensure_ascii=False) + '\n')

def load_fixes():
    r = {}
    try:
        for l in open(FIXES_FILE, encoding='utf-8'):
            l = l.strip()
            if l:
                d = json.loads(l)
                if d.get('answer'): r[d['task_uid']] = d
    except: pass
    return r

def save_fix(uid, answer, solution):
    with lock:
        with open(FIXES_FILE, 'a', encoding='utf-8') as f:
            f.write(json.dumps({'task_uid': uid, 'answer': answer, 'solution': solution},
                ensure_ascii=False) + '\n')

# ============ ФИКС (двухшаговый) ============

SOLVE_SYS = 'Реши задачу. Ответ ВЕРНЫЙ. Решение КРАТКОЕ (до 100 слов). JSON: {"answer":"...","solution":"..."}'
VERIFY_SYS = 'Проверь правильный ли ответ для задачи. JSON: {"correct":true/false,"correct_answer":"..."}'

def fix_worker(q, tasks_by_uid, done_flag):
    while not done_flag[0]:
        try: uid = q.get(timeout=1)
        except: continue
        if uid is None: q.task_done(); break
        t = tasks_by_uid[uid]
        stmt = (t.get("statement","") or "")[:600]

        # Шаг 1: Решить
        solve_user = (f'Класс: {t["grade"]}\nУровень: L{t["level"]}\nТема: {t.get("theme","")}\n\n'
                      f'Задача:\n{stmt}\n\nРеши.')
        resp = api_call([{"role":"system","content":SOLVE_SYS},{"role":"user","content":solve_user}],
                        max_tokens=2000, timeout=50)
        result = parse_json(resp) if resp else None

        if not result or not result.get('answer') or not result.get('solution'):
            time.sleep(0.5); q.task_done(); continue

        # Шаг 2: Проверить
        verify_user = (f'Задача:\n{stmt[:300]}\n\n'
                       f'Предлагаемый ответ: {result["answer"][:80]}\n\n'
                       f'Правильный ли это ответ?')
        vresp = api_call([{"role":"system","content":VERIFY_SYS},{"role":"user","content":verify_user}],
                         max_tokens=1000, timeout=50)
        verify = parse_json(vresp) if vresp else None

        if verify:
            if verify.get('correct') == True:
                save_fix(uid, result['answer'], result['solution'])
            elif verify.get('correct') == False and verify.get('correct_answer'):
                # Берём правильный ответ из проверки
                save_fix(uid, verify['correct_answer'], result['solution'])
            else:
                # Не удалось проверить — сохраняем как есть
                save_fix(uid, result['answer'], result['solution'])
        else:
            save_fix(uid, result['answer'], result['solution'])

        time.sleep(0.5)
        q.task_done()

# ============ АУДИТ ============

AUDIT_SYS = 'Проверь решение. JSON: {"answer_correct":true/false,"solution_complete":true/false,"problem_valid":true/false,"correct_answer":"..."}'

def audit_worker(q, tasks_by_uid, done_flag):
    while not done_flag[0]:
        try: uid = q.get(timeout=1)
        except: continue
        if uid is None: q.task_done(); break
        t = tasks_by_uid[uid]
        user = (f'Класс:{t["grade"]} L{t["level"]}\n'
                f'Задача:\n{(t.get("statement","") or "")[:400]}\n\n'
                f'Ответ:\n{(t.get("answer","") or "")[:100]}\n\n'
                f'Решение:\n{(t.get("solution","") or "")[:1000]}')
        resp = api_call([{"role":"system","content":AUDIT_SYS},{"role":"user","content":user}],
                        max_tokens=1500, timeout=50)
        v = parse_json(resp) if resp else None
        if v and v.get('answer_correct') is not None:
            save_audit(uid, t['level'], t['grade'], v['answer_correct'],
                      v.get('solution_complete'), v.get('correct_answer',''),
                      v.get('problem_valid', True))
        time.sleep(0.5)
        q.task_done()

# ============ ЗАПУСК ============

def run_phase(tasks_by_uid, uids, worker_fn, label, is_audit=True):
    already = load_audit() if is_audit else load_fixes()
    to_do = [uid for uid in uids if uid not in already]
    total = len(uids)
    print(f'  {label}: уже {len(already)}/{total}, осталось {len(to_do)}', flush=True)
    if not to_do: return already
    q = Queue()
    for uid in to_do: q.put(uid)
    done_flag = [False]
    threads = []
    for _ in range(N_THREADS):
        th = threading.Thread(target=worker_fn, args=(q, tasks_by_uid, done_flag))
        th.start(); threads.append(th)
    while not q.empty():
        time.sleep(10)
        current = load_audit() if is_audit else load_fixes()
        n = len(current)
        if is_audit:
            ok = sum(1 for r in current.values() if r.get('answer_correct') == True)
            wrong = sum(1 for r in current.values() if r.get('answer_correct') == False)
            print(f'\r  [{label}] {n}/{total} (OK={ok}, Wrong={wrong})', end='', flush=True)
        else:
            print(f'\r  [{label}] {n}/{total}', end='', flush=True)
    done_flag[0] = True
    for _ in range(N_THREADS): q.put(None)
    for th in threads: th.join(timeout=30)
    print()
    return load_audit() if is_audit else load_fixes()

# ============ ГЛАВНОЕ ============

def main():
    print('=' * 60)
    print('FORMYLA L4-L5: ДВУХШАГОВЫЙ ФИКС + АУДИТ')
    print('thinking=disabled (быстро), самопроверка, 8 потоков')
    print('=' * 60)

    try: import requests
    except ImportError: os.system('pip install requests'); import requests

    tasks = load_tasks()
    l4l5 = [t for t in tasks if t.get('level') in (4, 5)]
    tasks_by_uid = {t['task_uid']: t for t in tasks}
    l4l5_uids = [t['task_uid'] for t in l4l5]
    print(f'L4-L5: {len(l4l5)} задач\n')

    # ===== ФАЗА 1: ФИКС =====
    print('===== ФАЗА 1: Фикс (двухшаговый) =====')
    prev_wrong = set()
    try:
        for l in open('L4L5_AUDIT_RESULTS.jsonl', encoding='utf-8'):
            l = l.strip()
            if l:
                r = json.loads(l)
                if r.get('answer_correct') == False:
                    prev_wrong.add(r['task_uid'])
    except: pass

    already_fixed = load_fixes()
    if prev_wrong:
        to_fix = [uid for uid in prev_wrong if uid in tasks_by_uid and uid not in already_fixed]
    else:
        to_fix = [uid for uid in l4l5_uids if uid not in already_fixed]

    print(f'Задач для фикса: {len(to_fix)}')

    if to_fix:
        fixes = run_phase(tasks_by_uid, to_fix, fix_worker, 'fix', is_audit=False)
        print(f'Исправлено: {len(fixes)}')
        for uid, fix in fixes.items():
            if uid in tasks_by_uid:
                tasks_by_uid[uid]['answer'] = fix['answer']
                tasks_by_uid[uid]['solution'] = fix['solution']
                tasks_by_uid[uid]['fixed_dual'] = True
        save_tasks(list(tasks_by_uid.values()))
        print('Сохранено.')
    else:
        print('Нет задач для фикса.')

    # ===== ФАЗА 2: ПОЛНЫЙ АУДИТ =====
    print(f'\n===== ФАЗА 2: Полный аудит =====')
    results = run_phase(tasks_by_uid, l4l5_uids, audit_worker, 'audit', is_audit=True)

    ok = sum(1 for r in results.values() if r.get('answer_correct') == True)
    wrong = sum(1 for r in results.values() if r.get('answer_correct') == False)
    broken = sum(1 for r in results.values() if r.get('problem_valid') == False)
    total = len(results)

    print(f'\n{"=" * 60}')
    print('ИТОГ')
    print(f'{"=" * 60}')
    print(f'  Проверено:  {total}/{len(l4l5_uids)}')
    print(f'  OK:         {ok} ({ok*100//max(1,total)}%)')
    print(f'  Wrong:      {wrong} ({wrong*100//max(1,total)}%)')
    print(f'  Битых:      {broken}')
    print(f'{"=" * 60}')

    if total < len(l4l5_uids):
        print(f'\n{len(l4l5_uids) - total} задач не проверены. Запусти ещё раз.')

if __name__ == '__main__':
    main()
