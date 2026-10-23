import os
#!/usr/bin/env python3
"""
FORMYLA L4-L5: РИЗОНЕР ФИКС + ПОЛНЫЙ АУДИТ
============================================
Фаза 1: Фикс всех wrong через РИЗОНЕР (thinking=enabled)
  - Если fail — пробует снова (до 10 раз)
  - Если 10 раз fail — пропускает, идёт дальше
Фаза 2: Полный аудит ВСЕХ 1320 через РИЗОНЕР (6 потоков)
  - Если fail — пробует снова (до 10 раз)
  - НИ ОДНА задача не пропускается без проверки

Сохраняет прогресс. Можно перезапускать.
"""
import json, time, re, threading, os
from collections import Counter
from queue import Queue

API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-v4-pro"
INPUT_FILE = "FORMYLA_L1_L5_TOP5.jsonl"
AUDIT_FILE = "L4L5_REASONER_AUDIT.jsonl"    # новый файл — чистый аудит ризонером
FIXES_FILE = "L4L5_REASONER_FIXES.jsonl"     # новый файл — фиксы ризонером
N_THREADS = 6
MAX_RETRIES = 10  # 10 попыток на каждую задачу!

lock = threading.Lock()

def api_call(messages, max_tokens=8000, thinking="enabled", timeout=280):
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
            print(f"\n  API error: {err[:60]}")
        except Exception as e:
            s = str(e)
            if any(x in s for x in ["prematurely", "SSL", "EOF", "Remote", "Connection",
                                     "Reset", "timeout", "timed", "resolve", "getaddrinfo",
                                     "Max retries", "SSLEOF"]):
                print(f"\n  Нет связи (попытка {attempt+1}/{MAX_RETRIES}), ждём 5с...")
                time.sleep(5)
                continue
            print(f"\n  Ошибка: {s[:60]}")
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

# ============ ФИКС ЧЕРЕЗ РИЗОНЕР ============

FIX_SYS = """Ты — эксперт по олимпиадной математике. Реши задачу максимально тщательно.

Реши, проверь свой ответ, и выдай результат.

JSON: {"answer":"...","solution":"..."}"""

def fix_worker(q, tasks_by_uid, done_flag):
    while not done_flag[0]:
        try: uid = q.get(timeout=1)
        except: continue
        if uid is None: q.task_done(); break
        t = tasks_by_uid[uid]
        user = (f'Класс: {t["grade"]}\nУровень: L{t["level"]}\nТема: {t.get("theme","")}\n\n'
                f'Задача:\n{(t.get("statement","") or "")[:800]}\n\n'
                f'Реши задачу. Дай верный ответ и полное решение.')

        # До 10 попыток — пока не получится
        for attempt in range(MAX_RETRIES):
            resp = api_call([{"role":"system","content":FIX_SYS},{"role":"user","content":user}],
                            max_tokens=8000, thinking="enabled", timeout=280)
            result = parse_json(resp) if resp else None
            if result and result.get('answer') and result.get('solution'):
                save_fix(uid, result['answer'], result['solution'])
                break
            # Если не получилось — пробуем ещё
        time.sleep(0.5)
        q.task_done()

# ============ АУДИТ ЧЕРЕЗ РИЗОНЕР ============

AUDIT_SYS = """Ты — эксперт по олимпиадной математике. Реши задачу САМ и сравни с решением автора.

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

        # До 10 попыток — пока не получится
        for attempt in range(MAX_RETRIES):
            resp = api_call([{"role":"system","content":AUDIT_SYS},{"role":"user","content":user}],
                            max_tokens=8000, thinking="enabled", timeout=280)
            v = parse_json(resp) if resp else None
            if v and v.get('answer_correct') is not None:
                save_audit(uid, t['level'], t['grade'],
                          v['answer_correct'], v.get('solution_complete'),
                          v.get('correct_answer', ''), v.get('problem_valid', True))
                break
        time.sleep(0.5)
        q.task_done()

# ============ ЗАПУСК ============

def run_phase(tasks_by_uid, uids, worker_fn, label, is_audit=True):
    already = load_audit() if is_audit else load_fixes()
    to_do = [uid for uid in uids if uid not in already]
    total = len(uids)
    print(f'  {label}: уже {len(already)}/{total}, осталось {len(to_do)}', flush=True)

    if not to_do:
        return already

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
    for th in threads: th.join(timeout=60)
    print()
    return load_audit() if is_audit else load_fixes()

# ============ ГЛАВНОЕ ============

def main():
    print('=' * 60)
    print('FORMYLA L4-L5: РИЗОНЕР ФИКС + ПОЛНЫЙ АУДИТ')
    print('Фаза 1: Фикс через ризонер (10 попыток на задачу)')
    print('Фаза 2: Полный аудит через ризонер (10 попыток)')
    print('=' * 60)

    try: import requests
    except ImportError: os.system('pip install requests'); import requests

    tasks = load_tasks()
    l4l5 = [t for t in tasks if t.get('level') in (4, 5)]
    tasks_by_uid = {t['task_uid']: t for t in tasks}
    l4l5_uids = [t['task_uid'] for t in l4l5]
    print(f'L4-L5: {len(l4l5)} задач')
    print(f'Потоков: {N_THREADS}')
    print(f'Попыток на задачу: {MAX_RETRIES}')
    print()

    # ===== ФАЗА 1: ФИКС =====
    # Загружаем предыдущий аудит (L4L5_AUDIT_RESULTS.jsonl) чтобы найти wrong
    print('===== ФАЗА 1: Фикс через ризонер =====')
    prev_audit = {}
    try:
        for l in open('L4L5_AUDIT_RESULTS.jsonl', encoding='utf-8'):
            l = l.strip()
            if l:
                r = json.loads(l)
                if r.get('answer_correct') == False:
                    prev_audit[r['task_uid']] = r
    except: pass

    # Также добавляем задачи не из предыдущего аудита
    # Берём все L4-L5 которые ещё не исправлены
    already_fixed = load_fixes()
    to_fix = [uid for uid in l4l5_uids if uid not in already_fixed]

    # Если есть предыдущий аудит — фиксим только wrong
    if prev_audit:
        wrong_from_prev = [uid for uid in prev_audit.keys() if uid in tasks_by_uid and uid not in already_fixed]
        if wrong_from_prev:
            to_fix = wrong_from_prev

    print(f'Задач для фикса: {len(to_fix)}')

    if to_fix:
        fixes = run_phase(tasks_by_uid, to_fix, fix_worker, 'reasoner-fix', is_audit=False)
        print(f'Исправлено: {len(fixes)}')

        # Применить
        for uid, fix in fixes.items():
            if uid in tasks_by_uid:
                tasks_by_uid[uid]['answer'] = fix['answer']
                tasks_by_uid[uid]['solution'] = fix['solution']
                tasks_by_uid[uid]['fixed_reasoner_final'] = True
        save_tasks(list(tasks_by_uid.values()))
        print('Сохранено в базу.')
    else:
        print('Нет задач для фикса (все уже исправлены).')

    # ===== ФАЗА 2: ПОЛНЫЙ АУДИТ =====
    print(f'\n===== ФАЗА 2: Полный аудит через ризонер =====')
    print(f'Проверяем ВСЕ {len(l4l5_uids)} задач (без пропусков).')

    results = run_phase(tasks_by_uid, l4l5_uids, audit_worker, 'reasoner-audit', is_audit=True)

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
    print(f'  Битых:      {broken} (некорректное условие)')
    print(f'{"=" * 60}')

    if total < len(l4l5_uids):
        print(f'\nВнимание: {len(l4l5_uids) - total} задач не проверены (fail после 10 попыток).')
        print('Запусти скрипт ещё раз — они будут проверены.')

if __name__ == '__main__':
    main()
