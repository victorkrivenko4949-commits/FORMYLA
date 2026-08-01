"""
FORMYLA L4-L5: ОПТИМАЛЬНЫЙ СКРИПТ
==================================
Стратегия:
  1. БЫСТРЫЙ аудит всех 1320 (thinking=disabled, 8 потоков) — за ~10 мин
  2. БЫСТРЫЙ фикс всех wrong (thinking=disabled) — за ~5 мин
  3. БЫСТРЫЙ переаудит — за ~10 мин
  4. РИЗОНЕР только на оставшихся wrong (~50-80 шт) — за ~30 мин
  5. РИЗОНЕР фикс только тех что ризонер пометил wrong
  6. Финальная проверка

Итого: ~1 час вместо 5+ часов
"""

import json, time, re, threading, os
from collections import Counter
from queue import Queue

API_KEY = "sk-ad477f779a1045cba3cc09100e908370"
API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-v4-pro"
INPUT_FILE = "FORMYLA_L1_L5_TOP5.jsonl"
N_THREADS_FAST = 8
N_THREADS_HARD = 4

lock = threading.Lock()

def api_call(messages, max_tokens=6000, thinking="disabled", timeout=60):
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
                time.sleep(5 * (attempt + 1))
                continue
        except Exception as e:
            s = str(e)
            if any(x in s for x in ["prematurely", "SSL", "EOF", "Remote", "Connection", "Reset", "timeout", "timed"]):
                time.sleep(2)
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

# ============ БЫСТРЫЙ АУДИТ ============

FAST_AUDIT_SYS = """Проверь решение. JSON: {"answer_correct":true/false,"solution_complete":true/false}"""

def audit_worker_fast(q, tasks_by_uid, results, done_flag):
    while not done_flag[0]:
        try: uid = q.get(timeout=1)
        except: continue
        if uid is None: q.task_done(); break
        t = tasks_by_uid[uid]
        user = (f'Класс:{t["grade"]} L{t["level"]}\n'
                f'Задача:\n{(t.get("statement","") or "")[:400]}\n\n'
                f'Ответ:\n{(t.get("answer","") or "")[:100]}\n\n'
                f'Решение:\n{(t.get("solution","") or "")[:1000]}')
        resp = api_call([{"role":"system","content":FAST_AUDIT_SYS},{"role":"user","content":user}],
                        max_tokens=1500, thinking="disabled", timeout=50)
        v = parse_json(resp) if resp else None
        if v and v.get('answer_correct') is not None:
            with lock: results[uid] = v
        time.sleep(0.3)
        q.task_done()

# ============ ЖЁСТКИЙ АУДИТ (РИЗОНЕР) ============

HARD_AUDIT_SYS = """Ты — эксперт по олимпиадной математике. Реши задачу САМ и сравни с решением автора.

JSON: {"answer_correct":true/false,"solution_correct":true/false,"solution_complete":true/false,"problem_valid":true/false,"correct_answer":"..."}"""

def audit_worker_hard(q, tasks_by_uid, results, done_flag):
    while not done_flag[0]:
        try: uid = q.get(timeout=1)
        except: continue
        if uid is None: q.task_done(); break
        t = tasks_by_uid[uid]
        user = (f'Класс: {t["grade"]} L{t["level"]} Тема: {t.get("theme","")}\n\n'
                f'Задача:\n{(t.get("statement","") or "")[:600]}\n\n'
                f'Ответ автора:\n{(t.get("answer","") or "")[:150]}\n\n'
                f'Решение автора:\n{(t.get("solution","") or "")[:2000]}')
        resp = api_call([{"role":"system","content":HARD_AUDIT_SYS},{"role":"user","content":user}],
                        max_tokens=8000, thinking="enabled", timeout=280)
        v = parse_json(resp) if resp else None
        if v and v.get('answer_correct') is not None:
            with lock: results[uid] = v
        time.sleep(0.5)
        q.task_done()

def run_audit(tasks_by_uid, uids, mode='fast', label='audit'):
    results = {}
    q = Queue()
    for uid in uids: q.put(uid)
    done_flag = [False]
    n_threads = N_THREADS_FAST if mode == 'fast' else N_THREADS_HARD
    worker = audit_worker_fast if mode == 'fast' else audit_worker_hard
    threads = []
    for _ in range(n_threads):
        th = threading.Thread(target=worker, args=(q, tasks_by_uid, results, done_flag))
        th.start()
        threads.append(th)
    while not q.empty():
        time.sleep(5 if mode == 'fast' else 15)
        n = len(results)
        ok = sum(1 for r in results.values() if r.get('answer_correct') == True)
        wrong = sum(1 for r in results.values() if r.get('answer_correct') == False)
        print(f'\r  [{label}] {n}/{len(uids)} (OK={ok}, Wrong={wrong})', end='', flush=True)
    done_flag[0] = True
    for _ in range(n_threads): q.put(None)
    for th in threads: th.join(timeout=30)
    print()
    return results

# ============ ФИКС ============

FIX_SYS = """Реши задачу. Ответ ВЕРНЫЙ. Решение КРАТКОЕ (до 100 слов), ПОЛНОЕ.

JSON: {"answer":"...","solution":"..."}"""

def fix_worker(q, tasks_by_uid, fixes, done_flag, mode='fast'):
    while not done_flag[0]:
        try: uid = q.get(timeout=1)
        except: continue
        if uid is None: q.task_done(); break
        t = tasks_by_uid[uid]
        user = (f'Класс: {t["grade"]}\nУровень: L{t["level"]}\nТема: {t.get("theme","")}\n\n'
                f'Задача:\n{(t.get("statement","") or "")[:800]}\n\nРеши.')
        thinking = "disabled" if mode == 'fast' else "enabled"
        max_tok = 3000 if mode == 'fast' else 8000
        timeout = 50 if mode == 'fast' else 280
        resp = api_call([{"role":"system","content":FIX_SYS},{"role":"user","content":user}],
                        max_tokens=max_tok, thinking=thinking, timeout=timeout)
        result = parse_json(resp) if resp else None
        if result and result.get('answer') and result.get('solution'):
            with lock: fixes[uid] = {'answer': result['answer'], 'solution': result['solution']}
        time.sleep(0.3 if mode == 'fast' else 0.5)
        q.task_done()

def run_fix(tasks_by_uid, bad_uids, mode='fast', label='fix'):
    fixes = {}
    q = Queue()
    for uid in bad_uids: q.put(uid)
    done_flag = [False]
    n_threads = N_THREADS_FAST if mode == 'fast' else N_THREADS_HARD
    threads = []
    for _ in range(n_threads):
        th = threading.Thread(target=fix_worker, args=(q, tasks_by_uid, fixes, done_flag, mode))
        th.start()
        threads.append(th)
    while not q.empty():
        time.sleep(5 if mode == 'fast' else 15)
        print(f'\r  [{label}] {len(fixes)}/{len(bad_uids)}', end='', flush=True)
    done_flag[0] = True
    for _ in range(n_threads): q.put(None)
    for th in threads: th.join(timeout=30)
    print()
    return fixes

# ============ ГЛАВНОЕ ============

def main():
    print('=' * 60)
    print('FORMYLA L4-L5: ОПТИМАЛЬНЫЙ СКРИПТ')
    print('Быстро → Фикс → Переаудит → Ризонер на остаток')
    print('=' * 60)

    if API_KEY == "ВСТАВЬ_СВОЙ_DEEPSEEK_API_КЛЮЧ_СЮДА":
        print('\nОШИБКА: Вставь API ключ!'); return

    try: import requests
    except ImportError: os.system('pip install requests'); import requests

    tasks = load_tasks()
    l4l5 = [t for t in tasks if t.get('level') in (4, 5)]
    tasks_by_uid = {t['task_uid']: t for t in tasks}
    l4l5_uids = [t['task_uid'] for t in l4l5]

    print(f'L4-L5: {len(l4l5)} задач\n')

    # ===== ФАЗА 1: Быстрый аудит =====
    print('===== ФАЗА 1: Быстрый аудит (thinking=disabled) =====')
    results1 = run_audit(tasks_by_uid, l4l5_uids, mode='fast', label='fast-audit-1')
    ok1 = sum(1 for r in results1.values() if r.get('answer_correct') == True)
    wrong1 = [uid for uid, r in results1.items() if r.get('answer_correct') == False]
    print(f'OK: {ok1} ({ok1*100//max(1,len(results1))}%), Wrong: {len(wrong1)}')

    # ===== ФАЗА 2: Быстрый фикс =====
    if wrong1:
        print(f'\n===== ФАЗА 2: Быстрый фикс {len(wrong1)} задач =====')
        fixes1 = run_fix(tasks_by_uid, wrong1, mode='fast', label='fast-fix')
        for uid, fix in fixes1.items():
            if uid in tasks_by_uid:
                tasks_by_uid[uid]['answer'] = fix['answer']
                tasks_by_uid[uid]['solution'] = fix['solution']
                tasks_by_uid[uid]['fixed_fast'] = True
        save_tasks(list(tasks_by_uid.values()))
        print(f'Исправлено: {len(fixes1)}/{len(wrong1)}')

    # ===== ФАЗА 3: Быстрый переаудит =====
    print(f'\n===== ФАЗА 3: Быстрый переаудит =====')
    results2 = run_audit(tasks_by_uid, l4l5_uids, mode='fast', label='fast-audit-2')
    ok2 = sum(1 for r in results2.values() if r.get('answer_correct') == True)
    wrong2 = [uid for uid, r in results2.items() if r.get('answer_correct') == False]
    print(f'OK: {ok2} ({ok2*100//max(1,len(results2))}%), Wrong: {len(wrong2)}')

    # ===== ФАЗА 4: Ризонер на оставшиеся wrong =====
    if wrong2:
        print(f'\n===== ФАЗА 4: Ризонер на {len(wrong2)} спорных задач =====')
        hard_results = run_audit(tasks_by_uid, wrong2, mode='hard', label='reasoner-audit')
        hard_ok = [uid for uid, r in hard_results.items() if r.get('answer_correct') == True]
        hard_wrong = [uid for uid, r in hard_results.items() if r.get('answer_correct') == False]
        broken = [uid for uid, r in hard_results.items()
                  if r.get('answer_correct') == False and r.get('problem_valid') == False]
        print(f'Ризонер: OK={len(hard_ok)}, Wrong={len(hard_wrong)}, Битых={len(broken)}')

        # ===== ФАЗА 5: Ризонер фикс =====
        if hard_wrong:
            print(f'\n===== ФАЗА 5: Ризонер фикс {len(hard_wrong)} задач =====')
            fixes2 = run_fix(tasks_by_uid, hard_wrong, mode='hard', label='reasoner-fix')
            for uid, fix in fixes2.items():
                if uid in tasks_by_uid:
                    tasks_by_uid[uid]['answer'] = fix['answer']
                    tasks_by_uid[uid]['solution'] = fix['solution']
                    tasks_by_uid[uid]['fixed_reasoner'] = True
            save_tasks(list(tasks_by_uid.values()))
            print(f'Исправлено: {len(fixes2)}/{len(hard_wrong)}')

            # ===== ФАЗА 6: Финальная проверка исправленных =====
            print(f'\n===== ФАЗА 6: Финальная проверка =====')
            fixed_uids = list(fixes2.keys())
            final = run_audit(tasks_by_uid, fixed_uids, mode='hard', label='final-check')
            final_ok = sum(1 for r in final.values() if r.get('answer_correct') == True)
            final_wrong = sum(1 for r in final.values() if r.get('answer_correct') == False)
            print(f'Финал: OK={final_ok}, Wrong={final_wrong}')

    # ===== ИТОГ =====
    print('\n' + '=' * 60)
    print('ИТОГ')
    print('=' * 60)
    total_ok = ok2 + len(hard_ok) if wrong2 else ok2
    total_wrong = len(hard_wrong) if wrong2 else 0
    total = len(l4l5)
    print(f'  OK:      {total_ok} ({total_ok*100//max(1,total)}%)')
    print(f'  Wrong:   {total_wrong}')
    if wrong2:
        print(f'  Битых:   {len(broken)} (возможно некорректное условие)')
    cells = Counter((t['grade'], t['theme_id'], t['level']) for t in tasks)
    print(f'  База:    {len(tasks)} задач, {len(cells)} ячеек, все по 5: {all(v==5 for v in cells.values())}')
    print('=' * 60)

if __name__ == '__main__':
    main()
