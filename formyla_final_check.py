"""
FORMYLA L4-L5: ФИНАЛЬНАЯ ПРОВЕРКА (2 аудита ризонером)
======================================================
Запускать ПОСЛЕ formyla_optimal.py

Что делает:
  1. Аудит #1 всех L4-L5 через ризонер
  2. Аудит #2 всех L4-L5 через ризонер
  3. Сравнение:
     - 2/2 OK → задача идеальна
     - 2/2 WRONG → задача битая (некорректное условие)
     - 1 OK + 1 WRONG → спорная (нужен ручной разбор)
  4. Сохраняет отчёт

Только DeepSeek. Файл FORMYLA_L1_L5_TOP5.jsonl рядом.
"""

import json, time, re, threading, os
from collections import Counter
from queue import Queue

API_KEY = "ВСТАВЬ_СВОЙ_DEEPSEEK_API_КЛЮЧ_СЮДА"
API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-v4-pro"
INPUT_FILE = "FORMYLA_L1_L5_TOP5.jsonl"
REPORT_FILE = "FORMYLA_L4_L5_FINAL_REPORT.txt"
N_THREADS = 5

lock = threading.Lock()

def api_call(messages, max_tokens=8000, timeout=280):
    import requests
    for attempt in range(5):
        try:
            r = requests.post(API_URL, json={
                "model": MODEL,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": 0.1,
                "thinking": {"type": "enabled"},
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

AUDIT_SYS = """Ты — эксперт по олимпиадной математике. Реши задачу САМ и сравни с решением автора.

JSON: {"answer_correct":true/false,"solution_correct":true/false,"solution_complete":true/false,"problem_valid":true/false,"correct_answer":"...","explanation":"кратко"}"""

def audit_worker(q, tasks_by_uid, results, done_flag):
    while not done_flag[0]:
        try: uid = q.get(timeout=1)
        except: continue
        if uid is None: q.task_done(); break
        t = tasks_by_uid[uid]
        user = (f'Класс: {t["grade"]}\nУровень: L{t["level"]}\nТема: {t.get("theme","")}\n\n'
                f'Задача:\n{(t.get("statement","") or "")[:600]}\n\n'
                f'Ответ автора:\n{(t.get("answer","") or "")[:150]}\n\n'
                f'Решение автора:\n{(t.get("solution","") or "")[:2000]}')
        resp = api_call([{"role":"system","content":AUDIT_SYS},{"role":"user","content":user}],
                        max_tokens=8000, timeout=280)
        v = parse_json(resp) if resp else None
        if v and v.get('answer_correct') is not None:
            with lock: results[uid] = v
        time.sleep(0.5)
        q.task_done()

def run_audit(tasks_by_uid, uids, label='audit'):
    results = {}
    q = Queue()
    for uid in uids: q.put(uid)
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
    for _ in range(N_THREADS): q.put(None)
    for th in threads: th.join(timeout=60)
    print()
    return results

def main():
    print('=' * 60)
    print('FORMYLA L4-L5: ФИНАЛЬНАЯ ПРОВЕРКА')
    print('2 независимых аудита ризонером')
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
    print(f'Режим: reasoner (thinking=enabled)')
    print(f'Потоков: {N_THREADS}')
    print()

    # ===== АУДИТ #1 =====
    print('===== АУДИТ #1 (ризонер) =====')
    audit1 = run_audit(tasks_by_uid, l4l5_uids, label='audit-1')

    # ===== АУДИТ #2 =====
    print('\n===== АУДИТ #2 (ризонер) =====')
    audit2 = run_audit(tasks_by_uid, l4l5_uids, label='audit-2')

    # ===== СРАВНЕНИЕ =====
    both_ok = []
    both_wrong = []
    disputed = []
    errors = []

    for uid in l4l5_uids:
        r1 = audit1.get(uid)
        r2 = audit2.get(uid)
        if not r1 or not r2:
            errors.append(uid)
            continue
        a1 = r1.get('answer_correct')
        a2 = r2.get('answer_correct')
        if a1 == True and a2 == True:
            both_ok.append(uid)
        elif a1 == False and a2 == False:
            both_wrong.append(uid)
        else:
            disputed.append(uid)

    # ===== ОТЧЁТ =====
    total = len(l4l5)
    print('\n' + '=' * 60)
    print('ОТЧЁТ ФИНАЛЬНОЙ ПРОВЕРКИ')
    print('=' * 60)
    print(f'  2/2 OK (идеальные):     {len(both_ok)} ({len(both_ok)*100//max(1,total)}%)')
    print(f'  2/2 WRONG (битые):       {len(both_wrong)} ({len(both_wrong)*100//max(1,total)}%)')
    print(f'  Спорные (1 OK + 1 WRONG): {len(disputed)} ({len(disputed)*100//max(1,total)}%)')
    print(f'  Ошибки аудита:           {len(errors)}')
    print(f'  Всего:                    {total}')

    # Битые задачи (некорректное условие)
    broken = []
    for uid in both_wrong:
        r = audit1.get(uid) or audit2.get(uid)
        if r and r.get('problem_valid') == False:
            broken.append(uid)

    print(f'\n  Из {len(both_wrong)} битых:')
    print(f'    Некорректное условие:   {len(broken)}')
    print(f'    Ошибка в решении:       {len(both_wrong) - len(broken)}')

    # Спорные — детали
    if disputed:
        print(f'\n  Спорные задачи ({len(disputed)}):')
        for uid in disputed[:10]:
            t = tasks_by_uid.get(uid, {})
            r1 = audit1.get(uid, {})
            r2 = audit2.get(uid, {})
            print(f'    g{t.get("grade","?")} L{t.get("level","?")} {t.get("theme","")[:40]}')
            print(f'      #1: {"OK" if r1.get("answer_correct") else "WRONG"} | '
                  f'#2: {"OK" if r2.get("answer_correct") else "WRONG"}')
            if r1.get('correct_answer'):
                print(f'      Правильный ответ: {r1.get("correct_answer","")[:60]}')

    # Сохранить отчёт
    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        f.write('FORMYLA L4-L5 — ФИНАЛЬНЫЙ ОТЧЁТ\n')
        f.write(f'Дата: {time.strftime("%Y-%m-%d %H:%M")}\n')
        f.write(f'Модель: {MODEL} (reasoner)\n')
        f.write(f'Аудитов: 2\n\n')
        f.write(f'2/2 OK (идеальные):      {len(both_ok)} ({len(both_ok)*100//max(1,total)}%)\n')
        f.write(f'2/2 WRONG (битые):       {len(both_wrong)} ({len(both_wrong)*100//max(1,total)}%)\n')
        f.write(f'Спорные (1 OK + 1 WRONG): {len(disputed)} ({len(disputed)*100//max(1,total)}%)\n')
        f.write(f'Ошибки аудита:           {len(errors)}\n')
        f.write(f'Всего:                   {total}\n\n')

        f.write(f'Битые задачи (некорректное условие): {len(broken)}\n')
        for uid in both_wrong:
            t = tasks_by_uid.get(uid, {})
            r = audit1.get(uid, {})
            f.write(f'  {uid} g{t.get("grade","?")} L{t.get("level","?")} {t.get("theme","")[:40]}\n')
            f.write(f'    Условие: {t.get("statement","")[:100]}\n')
            f.write(f'    Ответ: {t.get("answer","")[:50]}\n')
            if r.get('correct_answer'):
                f.write(f'    Правильный: {r.get("correct_answer","")[:50]}\n')
            f.write('\n')

        if disputed:
            f.write(f'\nСпорные задачи: {len(disputed)}\n')
            for uid in disputed:
                t = tasks_by_uid.get(uid, {})
                r1 = audit1.get(uid, {})
                r2 = audit2.get(uid, {})
                f.write(f'  {uid} g{t.get("grade","?")} L{t.get("level","?")} {t.get("theme","")[:40]}\n')
                f.write(f'    #1: {"OK" if r1.get("answer_correct") else "WRONG"} | '
                        f'#2: {"OK" if r2.get("answer_correct") else "WRONG"}\n')
                f.write(f'    Условие: {t.get("statement","")[:100]}\n\n')

    print(f'\nОтчёт сохранён: {REPORT_FILE}')
    print('=' * 60)

if __name__ == '__main__':
    main()
