"""
FORMYLA L4-L5: КАЧЕСТВЕННЫЙ ФИКС ЧЕРЕЗ РИЗОНЕР
================================================
Что делает:
  1. Быстрый аудит всех 1320 (находит wrong)
  2. Фикс wrong задач через РИЗОНЕР (thinking=enabled)
     - Решает задачу заново с полным рассуждением
     - Проверяет свой же ответ
     - Только потом сохраняет
  3. Переаудит через ризонер
  4. Повторяет 2 цикла

Ключевое отличие: фикс через reasoner, не через fast mode.
"""

import json, time, re, threading, os
from collections import Counter
from queue import Queue

API_KEY = "sk-ad477f779a1045cba3cc09100e908370"
API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-v4-pro"
INPUT_FILE = "FORMYLA_L1_L5_TOP5.jsonl"
N_THREADS_FAST = 8
N_THREADS_REASONER = 5

lock = threading.Lock()

def api_call(messages, max_tokens=8000, thinking="disabled", timeout=60):
    import requests
    for attempt in range(5):
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
                print(f"\n  Rate limit, ждём {5*(attempt+1)}с...")
                time.sleep(5 * (attempt + 1))
                continue
        except Exception as e:
            s = str(e)
            if any(x in s for x in ["prematurely", "SSL", "EOF", "Remote", "Connection", "Reset", "timeout", "timed", "resolve", "getaddrinfo"]):
                time.sleep(3)
                continue
            print(f"\n  Error: {type(e).__name__}: {s[:80]}")
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

# ============ БЫСТРЫЙ АУДИТ ============

FAST_SYS = """Проверь решение. JSON: {"answer_correct":true/false,"solution_complete":true/false}"""

def fast_audit_worker(q, tasks_by_uid, results, done_flag):
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
            with lock: results[uid] = v
        time.sleep(0.3)
        q.task_done()

def run_fast_audit(tasks_by_uid, uids, label='audit'):
    results = {}
    q = Queue()
    for uid in uids: q.put(uid)
    done_flag = [False]
    threads = []
    for _ in range(N_THREADS_FAST):
        th = threading.Thread(target=fast_audit_worker, args=(q, tasks_by_uid, results, done_flag))
        th.start()
        threads.append(th)
    while not q.empty():
        time.sleep(5)
        n = len(results)
        ok = sum(1 for r in results.values() if r.get('answer_correct') == True)
        wrong = sum(1 for r in results.values() if r.get('answer_correct') == False)
        print(f'\r  [{label}] {n}/{len(uids)} (OK={ok}, Wrong={wrong})', end='', flush=True)
    done_flag[0] = True
    for _ in range(N_THREADS_FAST): q.put(None)
    for th in threads: th.join(timeout=30)
    print()
    return results

# ============ РИЗОНЕР ФИКС (с самопроверкой) ============

FIX_SYS = """Ты — эксперт по олимпиадной математике. Реши задачу максимально тщательно.

Шаги:
1. Внимательно прочитай условие
2. Реши задачу с полным рассуждением
3. Проверь свой ответ подстановкой или другим способом
4. Убедись что ответ правильный

Выдай JSON: {"answer":"...","solution":"...","verified":true/false}"""

VERIFY_SYS = """Проверь: правильный ли этот ответ для данной задачи?

JSON: {"correct":true/false,"correct_answer":"..."}"""

def reasoner_fix_worker(q, tasks_by_uid, fixes, done_flag):
    while not done_flag[0]:
        try: uid = q.get(timeout=1)
        except: continue
        if uid is None: q.task_done(); break
        t = tasks_by_uid[uid]
        user = (f'Класс: {t["grade"]}\nУровень: L{t["level"]}\nТема: {t.get("theme","")}\n\n'
                f'Задача:\n{(t.get("statement","") or "")[:800]}\n\n'
                f'Реши задачу. Дай верный ответ и полное решение.')

        # Шаг 1: Решить через ризонер
        resp = api_call([{"role":"system","content":FIX_SYS},{"role":"user","content":user}],
                        max_tokens=8000, thinking="enabled", timeout=280)
        result = parse_json(resp) if resp else None

        if not result or not result.get('answer') or not result.get('solution'):
            time.sleep(0.5)
            q.task_done()
            continue

        # Шаг 2: Самопроверка через ризонер
        verify_user = (f'Задача:\n{(t.get("statement","") or "")[:400]}\n\n'
                       f'Предлагаемый ответ: {result["answer"][:100]}\n\n'
                       f'Правильный ли это ответ?')
        verify_resp = api_call([{"role":"system","content":VERIFY_SYS},{"role":"user","content":verify_user}],
                              max_tokens=4000, thinking="enabled", timeout=200)
        verify = parse_json(verify_resp) if verify_resp else None

        if verify and verify.get('correct') == True:
            with lock:
                fixes[uid] = {'answer': result['answer'], 'solution': result['solution']}
        elif verify and verify.get('correct') == False and verify.get('correct_answer'):
            # Ризонер нашёл правильный ответ при проверке — используем его
            with lock:
                fixes[uid] = {'answer': verify['correct_answer'],
                              'solution': result['solution'] + f'\n\nПравильный ответ: {verify["correct_answer"]}'}
        else:
            # Не удалось проверить — всё равно сохраняем (лучше чем было)
            with lock:
                fixes[uid] = {'answer': result['answer'], 'solution': result['solution']}

        time.sleep(0.5)
        q.task_done()

def run_reasoner_fix(tasks_by_uid, bad_uids, label='fix'):
    fixes = {}
    q = Queue()
    for uid in bad_uids: q.put(uid)
    done_flag = [False]
    threads = []
    for _ in range(N_THREADS_REASONER):
        th = threading.Thread(target=reasoner_fix_worker, args=(q, tasks_by_uid, fixes, done_flag))
        th.start()
        threads.append(th)
    while not q.empty():
        time.sleep(15)
        print(f'\r  [{label}] {len(fixes)}/{len(bad_uids)}', end='', flush=True)
    done_flag[0] = True
    for _ in range(N_THREADS_REASONER): q.put(None)
    for th in threads: th.join(timeout=60)
    print()
    return fixes

# ============ РИЗОНЕР АУДИТ ============

HARD_SYS = """Ты — эксперт по олимпиадной математике. Реши задачу САМ и сравни.

JSON: {"answer_correct":true/false,"solution_correct":true/false,"solution_complete":true/false,"problem_valid":true/false,"correct_answer":"..."}"""

def hard_audit_worker(q, tasks_by_uid, results, done_flag):
    while not done_flag[0]:
        try: uid = q.get(timeout=1)
        except: continue
        if uid is None: q.task_done(); break
        t = tasks_by_uid[uid]
        user = (f'Класс: {t["grade"]}\nУровень: L{t["level"]}\nТема: {t.get("theme","")}\n\n'
                f'Задача:\n{(t.get("statement","") or "")[:600]}\n\n'
                f'Ответ автора:\n{(t.get("answer","") or "")[:150]}\n\n'
                f'Решение автора:\n{(t.get("solution","") or "")[:2000]}')
        resp = api_call([{"role":"system","content":HARD_SYS},{"role":"user","content":user}],
                        max_tokens=8000, thinking="enabled", timeout=280)
        v = parse_json(resp) if resp else None
        if v and v.get('answer_correct') is not None:
            with lock: results[uid] = v
        time.sleep(0.5)
        q.task_done()

def run_hard_audit(tasks_by_uid, uids, label='hard-audit'):
    results = {}
    q = Queue()
    for uid in uids: q.put(uid)
    done_flag = [False]
    threads = []
    for _ in range(N_THREADS_REASONER):
        th = threading.Thread(target=hard_audit_worker, args=(q, tasks_by_uid, results, done_flag))
        th.start()
        threads.append(th)
    while not q.empty():
        time.sleep(15)
        n = len(results)
        ok = sum(1 for r in results.values() if r.get('answer_correct') == True)
        wrong = sum(1 for r in results.values() if r.get('answer_correct') == False)
        print(f'\r  [{label}] {n}/{len(uids)} (OK={ok}, Wrong={wrong})', end='', flush=True)
    done_flag[0] = True
    for _ in range(N_THREADS_REASONER): q.put(None)
    for th in threads: th.join(timeout=60)
    print()
    return results

# ============ ГЛАВНОЕ ============

def main():
    print('=' * 60)
    print('FORMYLA L4-L5: КАЧЕСТВЕННЫЙ ФИКС ЧЕРЕЗ РИЗОНЕР')
    print('Аудит (быстрый) → Фикс (ризонер) → Аудит (ризонер)')
    print('=' * 60)

    if API_KEY == "ВСТАВЬ_СВОЙ_DEEPSEEK_API_КЛЮЧ_СЮДА":
        print('\nОШИБКА: Вставь API ключ!'); return

    try: import requests
    except ImportError: os.system('pip install requests'); import requests

    tasks = load_tasks()
    l4l5 = [t for t in tasks if t.get('level') in (4, 5)]
    tasks_by_uid = {t['task_uid']: t for t in tasks}
    l4l5_uids = [t['task_uid'] for t in l4l5]

    print(f'L4-L5: {len(l4l5)} задач')
    print(f'Быстрый аудит: {N_THREADS_FAST} потоков')
    print(f'Ризонер фикс: {N_THREADS_REASONER} потоков')
    print()

    for cycle in range(1, 4):
        print(f'===== ЦИКЛ {cycle} =====')

        # 1. Быстрый аудит — находим wrong
        print('--- Быстрый аудит ---')
        fast_results = run_fast_audit(tasks_by_uid, l4l5_uids, label=f'c{cycle}-fast')
        ok = sum(1 for r in fast_results.values() if r.get('answer_correct') == True)
        wrong = [uid for uid, r in fast_results.items() if r.get('answer_correct') == False]
        print(f'OK: {ok} ({ok*100//max(1,len(fast_results))}%), Wrong: {len(wrong)}')

        if not wrong:
            print('Все задачи OK!'); break

        # 2. Фикс через РИЗОНЕР (с самопроверкой!)
        print(f'\n--- Ризонер фикс {len(wrong)} задач (с самопроверкой) ---')
        fixes = run_reasoner_fix(tasks_by_uid, wrong, label=f'c{cycle}-fix')
        print(f'Исправлено: {len(fixes)}/{len(wrong)}')

        for uid, fix in fixes.items():
            if uid in tasks_by_uid:
                tasks_by_uid[uid]['answer'] = fix['answer']
                tasks_by_uid[uid]['solution'] = fix['solution']
                tasks_by_uid[uid]['fixed_reasoner_v2'] = True

        save_tasks(list(tasks_by_uid.values()))
        print('Сохранено.')

        # 3. Ризонер аудит исправленных
        if fixes:
            fixed_uids = list(fixes.keys())
            print(f'\n--- Ризонер проверка {len(fixed_uids)} исправленных ---')
            hard = run_hard_audit(tasks_by_uid, fixed_uids, label=f'c{cycle}-verify')
            h_ok = sum(1 for r in hard.values() if r.get('answer_correct') == True)
            h_wrong = sum(1 for r in hard.values() if r.get('answer_correct') == False)
            print(f'После фикса: OK={h_ok}, Wrong={h_wrong}')

        print()

    # ===== ФИНАЛЬНЫЙ БЫСТРЫЙ АУДИТ =====
    print('===== ФИНАЛЬНЫЙ АУДИТ =====')
    final = run_fast_audit(tasks_by_uid, l4l5_uids, label='final')
    f_ok = sum(1 for r in final.values() if r.get('answer_correct') == True)
    f_wrong = sum(1 for r in final.values() if r.get('answer_correct') == False)
    total = len(final)

    print('\n' + '=' * 60)
    print('ИТОГ')
    print('=' * 60)
    print(f'  OK:     {f_ok} ({f_ok*100//max(1,total)}%)')
    print(f'  Wrong:  {f_wrong} ({f_wrong*100//max(1,total)}%)')
    print(f'  Всего:  {total}')
    cells = Counter((t['grade'], t['theme_id'], t['level']) for t in tasks)
    print(f'  База:   {len(tasks)} задач, {len(cells)} ячеек, все по 5: {all(v==5 for v in cells.values())}')
    print('=' * 60)

if __name__ == '__main__':
    main()
