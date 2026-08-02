#!/usr/bin/env python3
"""
FORMYLA L4-L5: РИЗОНЕР ФИКС + ПОЛНЫЙ АУДИТ (стабильная версия)
================================================================
3 потока, adaptive режим, 120с таймаут, 2с задержка.
Не заедает. Сохраняет прогресс. Можно перезапускать.
"""
import json, time, re, threading, os
from collections import Counter
from queue import Queue

API_KEY = "sk-ad477f779a1045cba3cc09100e908370"
API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-v4-pro"
INPUT_FILE = "FORMYLA_L1_L5_TOP5.jsonl"
AUDIT_FILE = "L4L5_REASONER_AUDIT.jsonl"
FIXES_FILE = "L4L5_REASONER_FIXES.jsonl"
N_THREADS = 3       # 3 потока — стабильно для ризонера
MAX_RETRIES = 10    # 10 попыток на задачу
DELAY = 2           # 2с задержка между запросами

lock = threading.Lock()

def api_call(messages, max_tokens=4000, thinking="adaptive", timeout=120):
    try:
        import requests
    except ImportError:
        os.system('pip install requests')
        import requests

    payload = {
        "model": MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.1,
        "thinking": {"type": thinking},
    }
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

    for attempt in range(MAX_RETRIES):
        try:
            r = requests.post(API_URL, json=payload, headers=headers, timeout=timeout)
            d = r.json()
            if "error" not in d:
                return d["choices"][0]["message"]["content"]
            err = str(d.get("error", {}).get("message", ""))
            if "429" in err:
                print(f"\n  Rate limit, ждём {5*(attempt+1)}с...")
                time.sleep(5 * (attempt + 1))
                continue
        except Exception as e:
            s = str(e)
            if any(x in s for x in ["prematurely", "SSL", "EOF", "Remote", "Connection",
                                     "Reset", "timeout", "timed", "resolve", "getaddrinfo",
                                     "Max retries", "SSLEOF"]):
                # Нет связи — ждём 5с и пробуем снова
                time.sleep(5)
                continue
            time.sleep(3)
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
    results = {}
    try:
        for l in open(AUDIT_FILE, encoding='utf-8'):
            l = l.strip()
            if l:
                r = json.loads(l)
                if r.get('answer_correct') is not None:
                    results[r['task_uid']] = r
    except: pass
    return results

def save_audit(uid, level, grade, ac, sc, ca, pv):
    with lock:
        with open(AUDIT_FILE, 'a', encoding='utf-8') as f:
            f.write(json.dumps({'task_uid': uid, 'level': level, 'grade': grade,
                'answer_correct': ac, 'solution_complete': sc,
                'correct_answer': ca, 'problem_valid': pv}, ensure_ascii=False) + '\n')

def load_fixes():
    fixes = {}
    try:
        for l in open(FIXES_FILE, encoding='utf-8'):
            l = l.strip()
            if l:
                r = json.loads(l)
                if r.get('answer'):
                    fixes[r['task_uid']] = r
    except: pass
    return fixes

def save_fix(uid, answer, solution):
    with lock:
        with open(FIXES_FILE, 'a', encoding='utf-8') as f:
            f.write(json.dumps({'task_uid': uid, 'answer': answer, 'solution': solution},
                ensure_ascii=False) + '\n')

# ============ ФИКС ============

FIX_SYS = """Ты — эксперт по олимпиадной математике. Реши задачу.

JSON: {"answer":"...","solution":"..."}"""

def fix_worker(q, tasks_by_uid, done_flag):
    while not done_flag[0]:
        try: uid = q.get(timeout=1)
        except: continue
        if uid is None: q.task_done(); break
        t = tasks_by_uid[uid]
        user = (f'Класс: {t["grade"]}\nУровень: L{t["level"]}\nТема: {t.get("theme","")}\n\n'
                f'Задача:\n{(t.get("statement","") or "")[:800]}\n\nРеши.')
        for attempt in range(MAX_RETRIES):
            resp = api_call([{"role":"system","content":FIX_SYS},{"role":"user","content":user}],
                            max_tokens=4000, thinking="adaptive", timeout=120)
            result = parse_json(resp) if resp else None
            if result and result.get('answer') and result.get('solution'):
                save_fix(uid, result['answer'], result['solution'])
                break
        time.sleep(DELAY)
        q.task_done()

# ============ АУДИТ ============

AUDIT_SYS = """Ты — эксперт по олимпиадной математике. Реши задачу и сравни с решением автора.

JSON: {"answer_correct":true/false,"solution_correct":true/false,"solution_complete":true/false,"problem_valid":true/false,"correct_answer":"..."}"""

def audit_worker(q, tasks_by_uid, done_flag):
    while not done_flag[0]:
        try: uid = q.get(timeout=1)
        except: continue
        if uid is None: q.task_done(); break
        t = tasks_by_uid[uid]
        user = (f'Класс: {t["grade"]}\nУровень: L{t["level"]}\nТема: {t.get("theme","")}\n\n'
                f'Задача:\n{(t.get("statement","") or "")[:600]}\n\n'
                f'Ответ автора:\n{(t.get("answer","") or "")[:150]}\n\n'
                f'Решение автора:\n{(t.get("solution","") or "")[:2000]}')
        for attempt in range(MAX_RETRIES):
            resp = api_call([{"role":"system","content":AUDIT_SYS},{"role":"user","content":user}],
                            max_tokens=4000, thinking="adaptive", timeout=120)
            v = parse_json(resp) if resp else None
            if v and v.get('answer_correct') is not None:
                save_audit(uid, t['level'], t['grade'],
                          v['answer_correct'], v.get('solution_complete'),
                          v.get('correct_answer', ''), v.get('problem_valid', True))
                break
        time.sleep(DELAY)
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
        th.start()
        threads.append(th)
    while not q.empty():
        time.sleep(15)
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
    print('FORMYLA L4-L5: РИЗОНЕР (стабильная версия)')
    print(f'3 потока, adaptive, 120с таймаут, {DELAY}с задержка')
    print('=' * 60)

    try: import requests
    except ImportError: os.system('pip install requests'); import requests

    tasks = load_tasks()
    l4l5 = [t for t in tasks if t.get('level') in (4, 5)]
    tasks_by_uid = {t['task_uid']: t for t in tasks}
    l4l5_uids = [t['task_uid'] for t in l4l5]
    print(f'L4-L5: {len(l4l5)} задач\n')

    # ===== ФАЗА 1: ФИКС =====
    print('===== ФАЗА 1: Фикс =====')
    prev_audit = {}
    try:
        for l in open('L4L5_AUDIT_RESULTS.jsonl', encoding='utf-8'):
            l = l.strip()
            if l:
                r = json.loads(l)
                if r.get('answer_correct') == False:
                    prev_audit[r['task_uid']] = r
    except: pass

    already_fixed = load_fixes()
    if prev_audit:
        to_fix = [uid for uid in prev_audit.keys() if uid in tasks_by_uid and uid not in already_fixed]
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
                tasks_by_uid[uid]['fixed_reasoner_final'] = True
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
