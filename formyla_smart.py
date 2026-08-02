"""
FORMYLA L4-L5: Умный 3-уровневый аудит
=========================================
Стратегия:
  Цикл 1: Быстрый аудит (v4-pro, thinking=disabled) — все 1320 задач
  Цикл 2: Быстрый аудит (v4-pro, thinking=disabled) — все 1320 задач
  
  Результаты:
  - 2/2 OK → Оставляем (хорошая задача)
  - 2/2 WRONG → Помечаем "BROKEN" (возможно условие некорректно)
  - 1 OK + 1 WRONG → Жёсткий аудит (v4-pro, thinking=enabled) — финальный вердикт

  Затем: фиксим все WRONG (кроме BROKEN), переаудит, повторяем.

Запуск: python formyla_smart.py
Нужен: pip install requests
Файл FORMYLA_L1_L5_TOP5.jsonl должен лежать рядом.
"""

import json, time, re, threading, os
from collections import Counter
from queue import Queue

# ============ НАСТРОЙКИ ============
API_KEY = "������"
API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-v4-pro"
INPUT_FILE = "FORMYLA_L1_L5_TOP5.jsonl"
N_THREADS = 6
MAX_RETRIES = 5
# ====================================

lock = threading.Lock()

def api_call(messages, max_tokens=6000, thinking="disabled", timeout=60):
    """Вызов DeepSeek API. thinking: 'disabled' (быстро) или 'enabled' (точно)."""
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
                print(f"  Rate limit, ждём {5*(attempt+1)}с...")
                time.sleep(5 * (attempt + 1))
                continue
            print(f"  API error: {err[:80]}")
        except Exception as e:
            err_name = type(e).__name__
            if "prematurely" in str(e) or "SSLError" in str(e) or "SSLEOF" in str(e):
                # Adaptive думает слишком долго, ответ обрывается
                time.sleep(2)
                continue
            if "timed out" in str(e).lower() or "timeout" in str(e).lower():
                time.sleep(3)
                continue
            print(f"  {err_name}: {str(e)[:80]}")
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

# ============ АУДИТ ============

AUDIT_SYS_FAST = """Ты — эксперт по математике. Быстро проверь решение.

JSON: {"answer_correct":true/false,"solution_complete":true/false}"""

AUDIT_SYS_HARD = """Ты — эксперт по олимпиадной математике высшего уровня.
Внимательно реши задачу САМ и сравни с решением автора.

Проверь:
1. answer_correct — правильный ли ответ автора?
2. solution_correct — нет ли ошибок в логике?
3. solution_complete — решение полное, без обрывов?
4. problem_valid — корректно ли условие задачи (можно ли её решить)?

JSON: {"answer_correct":true/false,"solution_correct":true/false,"solution_complete":true/false,"problem_valid":true/false,"correct_answer":"...","explanation":"..."}"""

def audit_worker(q, tasks_by_uid, results, done_flag, mode):
    """mode: 'fast' or 'hard'"""
    while not done_flag[0]:
        try:
            uid = q.get(timeout=1)
        except:
            continue
        if uid is None:
            q.task_done()
            break
        t = tasks_by_uid[uid]
        stmt = (t.get('statement', '') or '')[:500]
        ans = (t.get('answer', '') or '')[:150]
        sol = (t.get('solution', '') or '')[:1500]

        if mode == 'fast':
            sys_msg = AUDIT_SYS_FAST
            user = f'Класс:{t["grade"]} L{t["level"]}\n\nЗадача:\n{stmt}\n\nОтвет:\n{ans}\n\nРешение:\n{sol}'
            resp = api_call([{"role": "system", "content": sys_msg},
                             {"role": "user", "content": user}],
                            max_tokens=1500, thinking="disabled", timeout=60)
            v = parse_json(resp) if resp else None
            if v and v.get('answer_correct') is not None:
                with lock:
                    results[uid] = {
                        'answer_correct': v['answer_correct'],
                        'solution_complete': v.get('solution_complete'),
                    }
        else:
            # Hard mode: full reasoning
            sys_msg = AUDIT_SYS_HARD
            user = f'Класс:{t["grade"]} L{t["level"]} Тема:{t.get("theme","")}\n\nЗадача:\n{stmt}\n\nОтвет автора:\n{ans}\n\nРешение автора:\n{sol}'
            resp = api_call([{"role": "system", "content": sys_msg},
                             {"role": "user", "content": user}],
                            max_tokens=8000, thinking="enabled", timeout=280)
            v = parse_json(resp) if resp else None
            if v and v.get('answer_correct') is not None:
                with lock:
                    results[uid] = {
                        'answer_correct': v['answer_correct'],
                        'solution_correct': v.get('solution_correct'),
                        'solution_complete': v.get('solution_complete'),
                        'problem_valid': v.get('problem_valid', True),
                        'correct_answer': v.get('correct_answer', ''),
                        'explanation': v.get('explanation', '')[:300],
                    }
        time.sleep(0.3)
        q.task_done()

def run_audit(tasks_by_uid, uids, mode='fast', label='audit'):
    results = {}
    q = Queue()
    for uid in uids:
        q.put(uid)
    done_flag = [False]
    threads = []
    for _ in range(N_THREADS):
        th = threading.Thread(target=audit_worker, args=(q, tasks_by_uid, results, done_flag, mode))
        th.start()
        threads.append(th)
    while not q.empty():
        time.sleep(10 if mode == 'hard' else 5)
        n = len(results)
        ok = sum(1 for r in results.values() if r.get('answer_correct') == True)
        wrong = sum(1 for r in results.values() if r.get('answer_correct') == False)
        speed = "жёсткий" if mode == 'hard' else "быстрый"
        print(f'\r  [{label}] {speed}: {n}/{len(uids)} (OK={ok}, Wrong={wrong})', end='', flush=True)
    done_flag[0] = True
    for _ in range(N_THREADS):
        q.put(None)
    for th in threads:
        th.join(timeout=30)
    print()
    return results

# ============ ФИКС ============

FIX_SYS = """Реши задачу. Ответ ВЕРНЫЙ, перепроверь. Решение КРАТКОЕ (до 100 слов), ПОЛНОЕ.

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
        user = f'Класс: {t["grade"]}\nУровень: L{t["level"]}\nТема: {t.get("theme","")}\n\nЗадача:\n{(t.get("statement","") or "")[:800]}\n\nРеши.'
        resp = api_call([{"role": "system", "content": FIX_SYS},
                         {"role": "user", "content": user}],
                        max_tokens=3000, thinking="disabled", timeout=60)
        result = parse_json(resp) if resp else None
        if result and result.get('answer') and result.get('solution'):
            with lock:
                fixes[uid] = {'answer': result['answer'], 'solution': result['solution']}
        time.sleep(0.3)
        q.task_done()

def run_fix(tasks_by_uid, bad_uids):
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
        time.sleep(5)
        print(f'\r  Фикс: {len(fixes)}/{len(bad_uids)}', end='', flush=True)
    done_flag[0] = True
    for _ in range(N_THREADS):
        q.put(None)
    for th in threads:
        th.join(timeout=30)
    print()
    return fixes

# ============ ГЛАВНЫЙ ЦИКЛ ============

def main():
    print('=' * 60)
    print('FORMYLA L4-L5: УМНЫЙ 3-УРОВНЕВЫЙ АУДИТ')
    print('=' * 60)

    if API_KEY == "ВСТАВЬ_СВОЙ_DEEPSEEK_API_КЛЮЧ_СЮДА":
        print('\nОШИБКА: Вставь свой DeepSeek API ключ в переменную API_KEY!')
        return

    try:
        import requests
    except ImportError:
        print('Устанавливаю requests...')
        os.system('pip install requests')
        import requests

    tasks = load_tasks()
    l4l5 = [t for t in tasks if t.get('level') in (4, 5)]
    tasks_by_uid = {t['task_uid']: t for t in tasks}
    l4l5_uids = [t['task_uid'] for t in l4l5]

    print(f'L4-L5 задач: {len(l4l5)}')
    print(f'Потоков: {N_THREADS}')
    print()

    # ====== ФАЗА 1: Два быстрых аудита ======
    print('====== ФАЗА 1: Два быстрых аудита ======\n')

    print('--- Аудит #1 (быстрый) ---')
    audit1 = run_audit(tasks_by_uid, l4l5_uids, mode='fast', label='audit1')

    print('\n--- Аудит #2 (быстрый) ---')
    audit2 = run_audit(tasks_by_uid, l4l5_uids, mode='fast', label='audit2')

    # ====== Классификация ======
    both_ok = []        # 2/2 OK → хорошая задача
    both_wrong = []      # 2/2 WRONG → возможно условие некорректно
    disputed = []        # 1 OK + 1 WRONG → нужен жёсткий аудит

    for uid in l4l5_uids:
        r1 = audit1.get(uid, {})
        r2 = audit2.get(uid, {})
        a1 = r1.get('answer_correct')
        a2 = r2.get('answer_correct')
        if a1 is None or a2 is None:
            disputed.append(uid)  # ошибка = пересчитать
        elif a1 == True and a2 == True:
            both_ok.append(uid)
        elif a1 == False and a2 == False:
            both_wrong.append(uid)
        else:
            disputed.append(uid)

    print(f'\n====== КЛАССИФИКАЦИЯ ======')
    print(f'  2/2 OK (хорошие):     {len(both_ok)}')
    print(f'  2/2 WRONG (битые):    {len(both_wrong)}')
    print(f'  Спорные (1+1):        {len(disputed)}')
    print(f'  Итого:                {len(both_ok) + len(both_wrong) + len(disputed)}')

    # ====== ФАЗА 2: Жёсткий аудит спорных ======
    if disputed:
        print(f'\n====== ФАЗА 2: Жёсткий аудит {len(disputed)} спорных задач ======\n')
        hard_results = run_audit(tasks_by_uid, disputed, mode='hard', label='hard')

        # Разбираем спорные
        hard_ok = [uid for uid, r in hard_results.items() if r.get('answer_correct') == True]
        hard_wrong = [uid for uid, r in hard_results.items() if r.get('answer_correct') == False]
        hard_broken = [uid for uid, r in hard_results.items()
                       if r.get('answer_correct') == False and r.get('problem_valid') == False]

        print(f'\n  Жёсткий аудит: OK={len(hard_ok)}, Wrong={len(hard_wrong)}, '
              f'Битые условия={len(hard_broken)}')

        both_wrong.extend(hard_wrong)
        both_ok.extend(hard_ok)

    # ====== ФАЗА 3: Фикс всех WRONG ======
    all_wrong = both_wrong
    if all_wrong:
        print(f'\n====== ФАЗА 3: Фикс {len(all_wrong)} задач ======\n')
        fixes = run_fix(tasks_by_uid, all_wrong)
        print(f'Исправлено: {len(fixes)}/{len(all_wrong)}')

        # Применить
        for uid, fix in fixes.items():
            if uid in tasks_by_uid:
                tasks_by_uid[uid]['answer'] = fix['answer']
                tasks_by_uid[uid]['solution'] = fix['solution']
                tasks_by_uid[uid]['fixed_smart'] = True

        save_tasks(list(tasks_by_uid.values()))
        print(f'Сохранено в {INPUT_FILE}')

    # ====== ФАЗА 4: Финальный аудит исправленных ======
    if all_wrong:
        print(f'\n====== ФАЗА 4: Переаудит исправленных ======\n')
        fixed_uids = [uid for uid in all_wrong if uid in tasks_by_uid]
        reaudit = run_audit(tasks_by_uid, fixed_uids, mode='fast', label='reaudit')

        ok = sum(1 for r in reaudit.values() if r.get('answer_correct') == True)
        wrong = sum(1 for r in reaudit.values() if r.get('answer_correct') == False)
        print(f'\n  После фикса: OK={ok} ({ok*100//max(1,len(reaudit))}%), Wrong={wrong}')

        # Если ещё есть wrong — ещё один фикс
        still_wrong = [uid for uid, r in reaudit.items() if r.get('answer_correct') == False]
        if still_wrong:
            print(f'\n--- Доп. фикс {len(still_wrong)} задач ---')
            fixes2 = run_fix(tasks_by_uid, still_wrong)
            for uid, fix in fixes2.items():
                if uid in tasks_by_uid:
                    tasks_by_uid[uid]['answer'] = fix['answer']
                    tasks_by_uid[uid]['solution'] = fix['solution']
                    tasks_by_uid[uid]['fixed_smart'] = True
            save_tasks(list(tasks_by_uid.values()))
            print(f'Сохранено.')

    # ====== ИТОГ ======
    print('\n' + '=' * 60)
    print('ИТОГ')
    print('=' * 60)
    total_ok = len(both_ok)
    total_wrong = len(both_wrong)
    total = total_ok + total_wrong
    print(f'  Хорошие задачи:   {total_ok} ({total_ok*100//max(1,total)}%)')
    print(f'  Проблемные:        {total_wrong} ({total_wrong*100//max(1,total)}%)')
    print(f'  Всего L4-L5:       {total}')
    cells = Counter((t['grade'], t['theme_id'], t['level']) for t in tasks)
    print(f'  Всего в базе:      {len(tasks)} задач, {len(cells)} ячеек')
    print(f'  Все по 5:          {all(v == 5 for v in cells.values())}')
    print('=' * 60)

if __name__ == '__main__':
    main()
