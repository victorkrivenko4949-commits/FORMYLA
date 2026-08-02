"""
FORMYLA L4-L5: КАЧЕСТВЕННЫЙ ФИКС (с сохранением прогресса)
=========================================================
Улучшения:
  - Сохраняет результаты аудита в файл
  - При перезапуске продолжает с места остановки
  - Проверяет только то что ещё не проверено
  - Больше ретраев при ошибках
  - Если интернет упал — просто перезапусти, продолжит

Запуск: python formyla_quality_fix2.py
"""

import json, time, re, threading, os
from collections import Counter
from queue import Queue

API_KEY = "sk-ad477f779a1045cba3cc09100e908370"
API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-v4-pro"
INPUT_FILE = "FORMYLA_L1_L5_TOP5.jsonl"
AUDIT_FILE = "L4L5_AUDIT_RESULTS.jsonl"    # результаты аудита
FIXES_FILE = "L4L5_FIXES_DONE.jsonl"       # выполненные фиксы
N_THREADS_FAST = 8
N_THREADS_REASONER = 5
MAX_RETRIES = 8  # больше ретраев

lock = threading.Lock()

def api_call(messages, max_tokens=8000, thinking="disabled", timeout=60):
    import requests
    for attempt in range(MAX_RETRIES):
        try:
            r = requests.post(API_URL, json={
                "model": MODEL,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": 0.1,
                "thinking": {"type": thinking},
            }, headers={"Authorization": f"Bearer {API_KEY}"}, timeout=timeout)
            d = r.json()
            if "error" not in d:
                return d["choices"][0]["message"]["content"]
            err = str(d.get("error", {}).get("message", ""))
            if "429" in err:
                time.sleep(5 * (attempt + 1))
                continue
        except Exception as e:
            s = str(e)
            if any(x in s for x in ["prematurely", "SSL", "EOF", "Remote", "Connection",
                                     "Reset", "timeout", "timed", "resolve", "getaddrinfo",
                                     "Max retries", "SSLEOF"]):
                time.sleep(3 * (attempt + 1))
                continue
            time.sleep(2 * (attempt + 1))
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

def load_audit_results():
    """Загружает предыдущие результаты аудита."""
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

def save_audit_result(result):
    with lock:
        with open(AUDIT_FILE, 'a', encoding='utf-8') as f:
            f.write(json.dumps(result, ensure_ascii=False) + '\n')

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
            f.write(json.dumps({'task_uid': uid, 'answer': answer, 'solution': solution}, ensure_ascii=False) + '\n')

# ============ БЫСТРЫЙ АУДИТ (только непроверенные) ============

FAST_SYS = """Проверь решение. JSON: {"answer_correct":true/false,"solution_complete":true/false}"""

def fast_audit_worker(q, tasks_by_uid, done_flag):
    while not done_flag[0]:
        try: uid = q.get(timeout=1)
        except: continue
        if uid is None: q.task_done(); break
        t = tasks_by_uid[uid]
        user = (f'Класс:{t["grade"]} L{t["level"]}\n'
                f'Задача:\n{(t.get("statement","") or "")[:400]}\n\n'
                f'Ответ:\n{(t.get("answer","") or "")[:100]}\n\n'
                f'Решение:\n{(t.get("solution","") or "")[:1000]}')
        resp = api_call([{"role":"system","content":FAST_SYS},{"role":"user","content":user}],
                        max_tokens=1500, thinking="disabled", timeout=50)
        v = parse_json(resp) if resp else None
        if v and v.get('answer_correct') is not None:
            save_audit_result({
                'task_uid': uid, 'level': t['level'], 'grade': t['grade'],
                'answer_correct': v['answer_correct'],
                'solution_complete': v.get('solution_complete'),
            })
        time.sleep(0.3)
        q.task_done()

def run_fast_audit(tasks_by_uid, l4l5_uids, label='audit'):
    """Аудит только непроверенных задач."""
    existing = load_audit_results()
    to_audit = [uid for uid in l4l5_uids if uid not in existing]
    print(f'  Уже проверено: {len(existing)}, осталось: {len(to_audit)}')

    if not to_audit:
        return existing

    q = Queue()
    for uid in to_audit: q.put(uid)
    done_flag = [False]
    threads = []
    for _ in range(N_THREADS_FAST):
        th = threading.Thread(target=fast_audit_worker, args=(q, tasks_by_uid, done_flag))
        th.start()
        threads.append(th)
    while not q.empty():
        time.sleep(5)
        n = len(load_audit_results())
        ok = sum(1 for r in load_audit_results().values() if r.get('answer_correct') == True)
        wrong = sum(1 for r in load_audit_results().values() if r.get('answer_correct') == False)
        print(f'\r  [{label}] {n}/{len(l4l5_uids)} (OK={ok}, Wrong={wrong})', end='', flush=True)
    done_flag[0] = True
    for _ in range(N_THREADS_FAST): q.put(None)
    for th in threads: th.join(timeout=30)
    print()
    return load_audit_results()

# ============ ЭКСПЕРТ ФИКС (только неисправленные) ============

FIX_SYS = """Ты — эксперт по олимпиадной математике. Реши задачу тщательно.

JSON: {"answer":"...","solution":"..."}"""

def reasoner_fix_worker(q, tasks_by_uid, done_flag):
    while not done_flag[0]:
        try: uid = q.get(timeout=1)
        except: continue
        if uid is None: q.task_done(); break
        t = tasks_by_uid[uid]
        user = (f'Класс: {t["grade"]}\nУровень: L{t["level"]}\nТема: {t.get("theme","")}\n\n'
                f'Задача:\n{(t.get("statement","") or "")[:800]}\n\nРеши.')
        resp = api_call([{"role":"system","content":FIX_SYS},{"role":"user","content":user}],
                        max_tokens=8000, thinking="adaptive", timeout=280)
        result = parse_json(resp) if resp else None
        if result and result.get('answer') and result.get('solution'):
            save_fix(uid, result['answer'], result['solution'])
        time.sleep(0.5)
        q.task_done()

def run_reasoner_fix(tasks_by_uid, bad_uids, label='fix'):
    existing_fixes = load_fixes()
    to_fix = [uid for uid in bad_uids if uid not in existing_fixes]
    print(f'  Уже исправлено: {len(existing_fixes & set(bad_uids))}, осталось: {len(to_fix)}')

    if not to_fix:
        return existing_fixes

    q = Queue()
    for uid in to_fix: q.put(uid)
    done_flag = [False]
    threads = []
    for _ in range(N_THREADS_REASONER):
        th = threading.Thread(target=reasoner_fix_worker, args=(q, tasks_by_uid, done_flag))
        th.start()
        threads.append(th)
    while not q.empty():
        time.sleep(15)
        n = len(load_fixes())
        print(f'\r  [{label}] {n}/{len(bad_uids)}', end='', flush=True)
    done_flag[0] = True
    for _ in range(N_THREADS_REASONER): q.put(None)
    for th in threads: th.join(timeout=60)
    print()
    return load_fixes()

# ============ ГЛАВНОЕ ============

def main():
    print('=' * 60)
    print('FORMYLA L4-L5: КАЧЕСТВЕННЫЙ ФИКС v2')
    print('Сохраняет прогресс. Можно перезапускать.')
    print('=' * 60)

    try: import requests
    except ImportError: os.system('pip install requests'); import requests

    tasks = load_tasks()
    l4l5 = [t for t in tasks if t.get('level') in (4, 5)]
    tasks_by_uid = {t['task_uid']: t for t in tasks}
    l4l5_uids = [t['task_uid'] for t in l4l5]

    print(f'L4-L5: {len(l4l5)} задач\n')

    for cycle in range(1, 5):
        print(f'===== ЦИКЛ {cycle} =====')

        # 1. Быстрый аудит (только непроверенные)
        print('--- Быстрый аудит (только новые) ---')
        results = run_fast_audit(tasks_by_uid, l4l5_uids, label=f'c{cycle}-audit')

        ok = sum(1 for r in results.values() if r.get('answer_correct') == True)
        wrong = [uid for uid, r in results.items() if r.get('answer_correct') == False]
        print(f'OK: {ok} ({ok*100//max(1,len(results))}%), Wrong: {len(wrong)}')

        if not wrong:
            print('Все проверенные задачи OK!'); break

        # 2. Фикс через ризонер (только неисправленные)
        print(f'\n--- Эксперт фикс {len(wrong)} задач ---')
        fixes = run_reasoner_fix(tasks_by_uid, wrong, label=f'c{cycle}-fix')
        print(f'Исправлено: {len(fixes & set(wrong))}/{len(wrong)}')

        # 3. Применить фиксы к базе
        for uid, fix in fixes.items():
            if uid in tasks_by_uid:
                tasks_by_uid[uid]['answer'] = fix['answer']
                tasks_by_uid[uid]['solution'] = fix['solution']
                tasks_by_uid[uid]['fixed_reasoner_v2'] = True
        save_tasks(list(tasks_by_uid.values()))
        print('Сохранено в базу.')

        # 4. Очистить аудит для исправленных (чтобы перепроверить)
        all_results = load_audit_results()
        for uid in fixes:
            if uid in all_results:
                del all_results[uid]
        with open(AUDIT_FILE, 'w', encoding='utf-8') as f:
            for r in all_results.values():
                f.write(json.dumps(r, ensure_ascii=False) + '\n')
        print(f'Очищен аудит для {len(fixes)} исправленных (будут перепроверены).')
        print()

    # ===== ИТОГ =====
    results = load_audit_results()
    ok = sum(1 for r in results.values() if r.get('answer_correct') == True)
    wrong = sum(1 for r in results.values() if r.get('answer_correct') == False)
    total = len(results)

    print('=' * 60)
    print('ИТОГ')
    print('=' * 60)
    print(f'  Проверено: {total}/{len(l4l5)}')
    print(f'  OK:        {ok} ({ok*100//max(1,total)}%)')
    print(f'  Wrong:     {wrong} ({wrong*100//max(1,total)}%)')
    cells = Counter((t['grade'], t['theme_id'], t['level']) for t in tasks)
    print(f'  База:      {len(tasks)} задач, {len(cells)} ячеек, все по 5: {all(v==5 for v in cells.values())}')
    print('=' * 60)
    print('\nЕсли осталось много Wrong — запусти скрипт ещё раз.')
    print('Если интернет упал — просто перезапусти, продолжит с места.')

if __name__ == '__main__':
    main()
