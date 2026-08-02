"""
FORMYLA L4-L5: ФИНАЛЬНЫЙ РИЗОНЕР
=================================
Берёт только проблемные задачи (33% = ~432 шт) и доводит их до идеала:
1. Жёсткий аудит каждой задачи через reasoner (thinking=enabled)
2. Если WRONG — перегенерирует ответ+решение через reasoner
3. Переаудит через reasoner
4. Повторяет пока OK или max 3 цикла

Только DeepSeek. Файл FORMYLA_L1_L5_TOP5.jsonl рядом.
"""

import json, time, re, threading, os
from collections import Counter
from queue import Queue

API_KEY = "������"
API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-v4-pro"
INPUT_FILE = "FORMYLA_L1_L5_TOP5.jsonl"
N_THREADS = 5  # меньше потоков = стабильнее для reasoner
MAX_RETRIES = 5

lock = threading.Lock()

def api_call(messages, max_tokens=8000, thinking="enabled", timeout=280):
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
                print(f"\n  Rate limit, ждём {5*(attempt+1)}с...")
                time.sleep(5 * (attempt + 1))
                continue
        except Exception as e:
            s = str(e)
            if "prematurely" in s or "SSLEOF" in s or "SSL" in s:
                time.sleep(2)
                continue
            if "timed out" in s.lower() or "timeout" in s.lower():
                time.sleep(3)
                continue
            if "Connection" in s or "Remote" in s or "Reset" in s:
                time.sleep(3)
                continue
            print(f"\n  Error: {s[:80]}")
            time.sleep(2 * (attempt + 1))
    return None

def parse_json(text):
    if not text:
        return None
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r'^```(json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
    s = text.find('{')
    e = text.rfind('}')
    if s >= 0 and e > s:
        try:
            return json.loads(text[s:e+1])
        except:
            return None
    return None

def load_tasks():
    with open(INPUT_FILE, encoding='utf-8') as f:
        return [json.loads(l) for l in f if l.strip()]

def save_tasks(tasks):
    with open(INPUT_FILE, 'w', encoding='utf-8') as f:
        for t in tasks:
            f.write(json.dumps(t, ensure_ascii=False, default=str) + '\n')

# ============ АУДИТ (РИЗОНЕР) ============

AUDIT_SYS = """Ты — эксперт по олимпиадной математике. Реши задачу САМ и сравни с решением автора.

Проверь:
1. answer_correct — правильный ли ответ?
2. solution_correct — нет ли ошибок в логике?
3. solution_complete — решение полное?
4. problem_valid — корректно ли условие?

JSON: {"answer_correct":true/false,"solution_correct":true/false,"solution_complete":true/false,"problem_valid":true/false,"correct_answer":"...","explanation":"..."}"""

def audit_worker(q, tasks_by_uid, results, done_flag):
    while not done_flag[0]:
        try:
            uid = q.get(timeout=1)
        except:
            continue
        if uid is None:
            q.task_done()
            break
        t = tasks_by_uid[uid]
        user = (f'Класс: {t["grade"]}\nУровень: L{t["level"]}\nТема: {t.get("theme","")}\n\n'
                f'Задача:\n{(t.get("statement","") or "")[:600]}\n\n'
                f'Ответ автора:\n{(t.get("answer","") or "")[:150]}\n\n'
                f'Решение автора:\n{(t.get("solution","") or "")[:2000]}')
        resp = api_call([
            {"role": "system", "content": AUDIT_SYS},
            {"role": "user", "content": user},
        ], max_tokens=8000, thinking="enabled", timeout=280)
        v = parse_json(resp) if resp else None
        if v and v.get('answer_correct') is not None:
            with lock:
                results[uid] = v
        time.sleep(0.5)
        q.task_done()

def run_audit(tasks_by_uid, uids, label='audit'):
    results = {}
    q = Queue()
    for uid in uids:
        q.put(uid)
    done_flag = [False]
    threads = []
    for _ in range(N_THREADS):
        th = threading.Thread(target=audit_worker, args=(q, tasks_by_uid, results, done_flag))
        th.start()
        threads.append(th)
    while not q.empty():
        time.sleep(15)
        n = len(results)
        ok = sum(1 for r in results.values() if r.get('answer_correct') == True)
        wrong = sum(1 for r in results.values() if r.get('answer_correct') == False)
        print(f'\r  [{label}] {n}/{len(uids)} (OK={ok}, Wrong={wrong})', end='', flush=True)
    done_flag[0] = True
    for _ in range(N_THREADS):
        q.put(None)
    for th in threads:
        th.join(timeout=60)
    print()
    return results

# ============ ФИКС (РИЗОНЕР) ============

FIX_SYS = """Ты — эксперт по олимпиадной математике. Реши задачу и выдай ВЕРНЫЙ ответ и ПОЛНОЕ решение.

JSON: {"answer":"...","solution":"..."}"""

def fix_worker(q, tasks_by_uid, fixes, done_flag):
    while not done_flag[0]:
        try:
            uid = q.get(timeout=1)
        except:
            continue
        if uid is None:
            q.task_done()
            break
        t = tasks_by_uid[uid]
        user = (f'Класс: {t["grade"]}\nУровень: L{t["level"]}\nТема: {t.get("theme","")}\n\n'
                f'Задача:\n{(t.get("statement","") or "")[:800]}\n\n'
                f'Реши задачу. Дай верный ответ и полное решение.')
        resp = api_call([
            {"role": "system", "content": FIX_SYS},
            {"role": "user", "content": user},
        ], max_tokens=8000, thinking="enabled", timeout=280)
        result = parse_json(resp) if resp else None
        if result and result.get('answer') and result.get('solution'):
            with lock:
                fixes[uid] = {'answer': result['answer'], 'solution': result['solution']}
        time.sleep(0.5)
        q.task_done()

def run_fix(tasks_by_uid, bad_uids, label='fix'):
    fixes = {}
    q = Queue()
    for uid in bad_uids:
        q.put(uid)
    done_flag = [False]
    threads = []
    for _ in range(N_THREADS):
        th = threading.Thread(target=fix_worker, args=(q, tasks_by_uid, fixes, done_flag))
        th.start()
        threads.append(th)
    while not q.empty():
        time.sleep(15)
        print(f'\r  [{label}] {len(fixes)}/{len(bad_uids)}', end='', flush=True)
    done_flag[0] = True
    for _ in range(N_THREADS):
        q.put(None)
    for th in threads:
        th.join(timeout=60)
    print()
    return fixes

# ============ ГЛАВНОЕ ============

def main():
    print('=' * 60)
    print('FORMYLA L4-L5: ФИНАЛЬНЫЙ РИЗОНЕР')
    print('Только проблемные задачи. Thinking=enabled.')
    print('=' * 60)

    if API_KEY == "ВСТАВЬ_СВОЙ_DEEPSEEK_API_КЛЮЧ_СЮДА":
        print('\nОШИБКА: Вставь API ключ!')
        return

    try:
        import requests
    except ImportError:
        os.system('pip install requests')
        import requests

    tasks = load_tasks()
    l4l5 = [t for t in tasks if t.get('level') in (4, 5)]
    tasks_by_uid = {t['task_uid']: t for t in tasks}
    l4l5_uids = [t['task_uid'] for t in l4l5]

    # Найти проблемные: не помечены как хорошие предыдущим скриптом
    # Проблемные = нет флага 'fixed_smart' или есть флаг но не проверены
    # Берём ВСЕ L4-L5 и проверяем ризонером
    print(f'\nL4-L5 задач: {len(l4l5)}')
    print(f'Режим: reasoner (thinking=enabled)')
    print(f'Потоков: {N_THREADS}')
    print(f'Циклов: до 3')
    print()

    for cycle in range(1, 4):
        print(f'===== ЦИКЛ {cycle} =====')

        # 1. Аудит
        print('--- Аудит (ризонер) ---')
        results = run_audit(tasks_by_uid, l4l5_uids, label=f'cycle{cycle}-audit')

        ok = [uid for uid, r in results.items() if r.get('answer_correct') == True]
        wrong = [uid for uid, r in results.items() if r.get('answer_correct') == False]
        broken = [uid for uid, r in results.items()
                   if r.get('answer_correct') == False and r.get('problem_valid') == False]

        print(f'Результат: OK={len(ok)} ({len(ok)*100//max(1,len(results))}%), '
              f'Wrong={len(wrong)}, Битых условий={len(broken)}')

        if not wrong:
            print('Все задачи OK!')
            break

        # 2. Фикс
        print(f'\n--- Фикс {len(wrong)} задач (ризонер) ---')
        fixes = run_fix(tasks_by_uid, wrong, label=f'cycle{cycle}-fix')
        print(f'Исправлено: {len(fixes)}/{len(wrong)}')

        # 3. Применить
        for uid, fix in fixes.items():
            if uid in tasks_by_uid:
                tasks_by_uid[uid]['answer'] = fix['answer']
                tasks_by_uid[uid]['solution'] = fix['solution']
                tasks_by_uid[uid]['fixed_reasoner'] = True

        save_tasks(list(tasks_by_uid.values()))
        print(f'Сохранено.')
        print()

    # ИТОГ
    print('=' * 60)
    print('ИТОГ')
    print('=' * 60)
    ok_final = sum(1 for uid, r in results.items() if r.get('answer_correct') == True)
    wrong_final = sum(1 for uid, r in results.items() if r.get('answer_correct') == False)
    total = len(results)
    print(f'  OK:     {ok_final} ({ok_final*100//max(1,total)}%)')
    print(f'  Wrong:  {wrong_final} ({wrong_final*100//max(1,total)}%)')
    print(f'  Всего:  {total}')
    print('=' * 60)

if __name__ == '__main__':
    main()
