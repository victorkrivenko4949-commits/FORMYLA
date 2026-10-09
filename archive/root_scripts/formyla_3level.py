import os
#!/usr/bin/env python3
"""
FORMYLA L4-L5: PULSE SYSTEM (фикс от заеданий)
==============================================
Изменения от оригинала:
  1. q.join() вместо while not q.empty() — ждёт реальные задачи
  2. Нет выхода "нет прогресса 2 мин" — крутит раунды до конца
  3. Пропуск зависших задач после 3 раундов — идёт дальше на след. шаг
  4. Потоки 3→5, таймаут 30→45
Всё остальное БЕЗ ИЗМЕНЕНИЙ: thinking, max_tokens, save_result, prompts.
"""
import json, time, re, os, sys, requests, threading
from queue import Queue, Empty

API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-v4-pro"
INPUT_FILE = "FORMYLA_L4_L5_FINAL.jsonl"
AUDIT1_FILE = "AUDIT1.jsonl"
AUDIT2_FILE = "AUDIT2.jsonl"
EXPERT_AUDIT_FILE = "EXPERT_AUDIT.jsonl"
FIXES_FILE = "FINAL_FIXES.jsonl"
BROKEN_FILE = "BROKEN_TASKS.jsonl"
DISPUTED_FILE = "DISPUTED_TASKS.jsonl"
SKIPPED_FILE = "SKIPPED_TASKS.jsonl"
N_THREADS = 5
TIMEOUT = 45
MAX_RETRIES = 3
MAX_ROUNDS = 3  # потом пропускаем зависшие

lock = threading.Lock()
session = requests.Session()
session.headers.update({"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"})

err_counter = {}
err_lock = threading.Lock()

def note_error(kind):
    with err_lock:
        err_counter[kind] = err_counter.get(kind, 0) + 1

def api_call(messages, max_tokens=1500, thinking="disabled", timeout=45):
    payload = {"model": MODEL, "messages": messages, "max_tokens": max_tokens,
        "temperature": 0.1, "thinking": {"type": thinking}}
    for attempt in range(MAX_RETRIES):
        try:
            r = session.post(API_URL, json=payload, timeout=timeout)
            d = r.json()
            if "error" not in d:
                return d["choices"][0]["message"]["content"]
            note_error(f"api_error:{str(d.get('error',''))[:80]}")
            if "429" in str(d.get("error", {})):
                time.sleep(3)
                continue
        except requests.exceptions.Timeout:
            note_error("timeout")
        except requests.exceptions.ConnectionError:
            note_error("connection")
        except Exception as e:
            note_error(f"other:{type(e).__name__}")
        time.sleep(2)
    return None

def parse_json(text):
    if not text: return None
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r'^```(json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
    s = text.rfind('{'); e = text.rfind('}')
    if s >= 0 and e > s:
        while s >= 0:
            try: return json.loads(text[s:e+1])
            except: s = text.rfind('{', 0, s)
    return None

def load_tasks():
    with open(INPUT_FILE, encoding='utf-8') as f:
        return [json.loads(l) for l in f if l.strip()]

def save_tasks(tasks):
    with open(INPUT_FILE, 'w', encoding='utf-8') as f:
        for t in tasks:
            f.write(json.dumps(t, ensure_ascii=False, default=str) + '\n')

def load_results(filepath):
    r = {}
    try:
        for l in open(filepath, encoding='utf-8'):
            l = l.strip()
            if l:
                d = json.loads(l)
                if d.get('answer_correct') is not None: r[d['task_uid']] = d
    except: pass
    return r

def save_result(filepath, data):
    with lock:
        with open(filepath, 'a', encoding='utf-8') as f:
            f.write(json.dumps(data, ensure_ascii=False) + '\n')
            f.flush()

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
            f.flush()

AUDIT_SYS = 'Проверь решение. JSON: {"answer_correct":true/false,"solution_complete":true/false}'
EXPERT_AUDIT_SYS = ('Ты — эксперт по олимпиадной математике. Реши и сравни. '
    'JSON: {"answer_correct":true/false,"solution_correct":true/false,"solution_complete":true/false,'
    '"problem_valid":true/false,"correct_answer":"..."}')
FIX_SYS = 'Реши задачу. Ответ ВЕРНЫЙ. Решение КРАТКОЕ (до 100 слов). JSON: {"answer":"...","solution":"..."}'

def audit_worker(q, tbu, outfile, sys_msg, thinking, max_tok):
    while True:
        try: uid = q.get(timeout=5)
        except Empty: return
        if uid is None: q.task_done(); return
        try:
            t = tbu[uid]
            user = (f'Класс:{t["grade"]} L{t["level"]}\n'
                    f'Задача:\n{(t.get("statement","") or "")[:400]}\n\n'
                    f'Ответ:\n{(t.get("answer","") or "")[:100]}\n\n'
                    f'Решение:\n{(t.get("solution","") or "")[:1000]}')
            resp = api_call([{"role":"system","content":sys_msg},{"role":"user","content":user}],
                            max_tokens=max_tok, thinking=thinking, timeout=TIMEOUT)
            v = parse_json(resp) if resp else None
            if v and v.get('answer_correct') is not None:
                save_result(outfile, {'task_uid': uid, 'answer_correct': v['answer_correct'],
                    'solution_complete': v.get('solution_complete'),
                    'correct_answer': v.get('correct_answer',''),
                    'problem_valid': v.get('problem_valid', True)})
            elif resp:
                note_error("bad_json")
        except Exception as e:
            note_error(f"worker:{type(e).__name__}")
        finally:
            q.task_done()

def fix_worker(q, tbu, outfile=None, sys_msg=None, thinking=None, max_tok=None):
    while True:
        try: uid = q.get(timeout=5)
        except Empty: return
        if uid is None: q.task_done(); return
        try:
            t = tbu[uid]
            user = (f'Класс: {t["grade"]}\nУровень: L{t["level"]}\nТема: {t.get("theme","")}\n\n'
                    f'Задача:\n{(t.get("statement","") or "")[:800]}\n\nРеши.')
            resp = api_call([{"role":"system","content":FIX_SYS},{"role":"user","content":user}],
                            max_tokens=3000, thinking="adaptive", timeout=60)
            result = parse_json(resp) if resp else None
            if result and result.get('answer') and result.get('solution'):
                save_fix(uid, result['answer'], result['solution'])
            elif resp:
                note_error("bad_json")
        except Exception as e:
            note_error(f"worker:{type(e).__name__}")
        finally:
            q.task_done()

def run_phase(tbu, uids, worker_fn, outfile, label, is_audit=True, sys_msg=AUDIT_SYS,
              thinking="disabled", max_tok=1500):
    loader = lambda: load_results(outfile) if is_audit else load_fixes()
    total = len(uids)

    for rnd in range(1, MAX_ROUNDS + 1):
        already = loader()
        to_do = [uid for uid in uids if uid not in already]
        print(f'  {label}: {len(already)}/{total}, осталось {len(to_do)}'
              + (f' [раунд {rnd}]' if rnd > 1 else ''), flush=True)
        if not to_do:
            return already

        q = Queue()
        for uid in to_do: q.put(uid)
        threads = []
        args = (q, tbu, outfile, sys_msg, thinking, max_tok) if is_audit else (q, tbu)
        for _ in range(N_THREADS):
            th = threading.Thread(target=worker_fn, args=args)
            th.start(); threads.append(th)

        # Монитор прогресса
        stop = threading.Event()
        def monitor():
            while not stop.wait(15):
                cur = loader()
                n = len(cur)
                if is_audit:
                    ok = sum(1 for r in cur.values() if r.get('answer_correct')==True)
                    wrong = sum(1 for r in cur.values() if r.get('answer_correct')==False)
                    print(f'\r  [{label}] {n}/{total} (OK={ok}, Wrong={wrong}) очередь={q.unfinished_tasks}   ', end='', flush=True)
                else:
                    print(f'\r  [{label}] {n}/{total} очередь={q.unfinished_tasks}   ', end='', flush=True)
        mon = threading.Thread(target=monitor, daemon=True)
        mon.start()

        q.join()  # Ждём ВСЕ задачи
        for _ in range(N_THREADS): q.put(None)
        for th in threads: th.join(timeout=10)
        stop.set()
        mon.join(timeout=2)
        print()

        done = loader()
        left = [uid for uid in uids if uid not in done]
        if not left:
            print(f'  {label}: ГОТОВО {total}/{total}', flush=True)
            return done

        # Пропуск зависших
        if rnd == MAX_ROUNDS:
            print(f'  {label}: пропускаю {len(left)} зависших → {SKIPPED_FILE}', flush=True)
            with open(SKIPPED_FILE, 'a', encoding='utf-8') as f:
                for uid in left:
                    f.write(json.dumps(tbu[uid], ensure_ascii=False) + '\n')
            # Убираем пропущенные из uids
            skipped = set(left)
            uids[:] = [u for u in uids if u not in skipped]
            return done

        with err_lock:
            top = sorted(err_counter.items(), key=lambda kv: -kv[1])[:5]
        print(f'  {label}: не добито {len(left)}. Причины: '
              + (', '.join(f'{k}×{v}' for k, v in top) if top else 'н/д'), flush=True)
        pause = min(60, 15 * rnd)
        print(f'  Пауза {pause}с...', flush=True)
        time.sleep(pause)

    return loader()

def apply_fixes(tbu):
    fixes = load_fixes()
    applied = 0
    for uid, fix in fixes.items():
        if uid in tbu:
            tbu[uid]['answer'] = fix['answer']
            tbu[uid]['solution'] = fix['solution']
            tbu[uid]['fixed_final'] = True
            applied += 1
    if applied > 0:
        save_tasks(list(tbu.values()))
    return applied

def main():
    print('=' * 50)
    print('FORMYLA L4-L5: PULSE (3 шага, пропуск зависших)')
    print('=' * 50)

    tasks = load_tasks()
    tbu = {t['task_uid']: t for t in tasks}
    uids = [t['task_uid'] for t in tasks]
    print(f'L4-L5: {len(tasks)} задач\n')

    # ШАГ 1: Два аудита
    print('===== ШАГ 1: Два аудита =====\n')
    print('--- Аудит #1 ---')
    a1 = run_phase(tbu, uids, audit_worker, AUDIT1_FILE, 'audit1', True)
    print('--- Аудит #2 ---')
    a2 = run_phase(tbu, uids, audit_worker, AUDIT2_FILE, 'audit2', True)

    print(f'\n>>> ШАГ 1 ЗАВЕРШЁН: {len(uids)} задач в работе\n')

    # КЛАССИФИКАЦИЯ
    both_ok = []
    both_wrong = []
    disputed = []
    for uid in uids:
        r1 = a1.get(uid); r2 = a2.get(uid)
        if not r1 or not r2:
            disputed.append(uid); continue
        ac1 = r1.get('answer_correct'); ac2 = r2.get('answer_correct')
        if ac1 == True and ac2 == True: both_ok.append(uid)
        elif ac1 == False and ac2 == False: both_wrong.append(uid)
        else: disputed.append(uid)

    print(f'2/2 OK: {len(both_ok)}, 2/2 WRONG: {len(both_wrong)}, Спорные: {len(disputed)}')

    # ШАГ 2: Эксперт-аудит спорных
    if disputed:
        print(f'\n===== ШАГ 2: Эксперт-аудит {len(disputed)} спорных =====\n')
        ea = run_phase(tbu, disputed, audit_worker, EXPERT_AUDIT_FILE, 'expert-1', True,
                      EXPERT_AUDIT_SYS, "adaptive", 4000)
        expert_ok = [uid for uid in disputed if ea.get(uid, {}).get('answer_correct') == True]
        expert_wrong = [uid for uid in disputed if ea.get(uid, {}).get('answer_correct') == False]
        expert_unknown = [uid for uid in disputed if uid not in ea]
        print(f'Эксперт: OK={len(expert_ok)}, WRONG={len(expert_wrong)}, ?={len(expert_unknown)}')

        # 2-й эксперт-аудит для wrong
        recheck = expert_wrong + expert_unknown
        if recheck:
            keep = {k: v for k, v in ea.items() if k not in set(recheck)}
            with open(EXPERT_AUDIT_FILE, 'w', encoding='utf-8') as f:
                for r in keep.values(): f.write(json.dumps(r, ensure_ascii=False) + '\n')
            ea2 = run_phase(tbu, recheck, audit_worker,
                           EXPERT_AUDIT_FILE, 'expert-2', True, EXPERT_AUDIT_SYS, "adaptive", 4000)
            still_disputed = []
            for uid in recheck:
                r2 = ea2.get(uid)
                if not r2: still_disputed.append(uid)
                elif r2.get('answer_correct') == True: both_ok.append(uid)
                else: both_wrong.append(uid)

            both_ok.extend(expert_ok)
            if still_disputed:
                with open(DISPUTED_FILE, 'w', encoding='utf-8') as f:
                    for uid in still_disputed:
                        f.write(json.dumps(tbu[uid], ensure_ascii=False) + '\n')
                print(f'Спорных осталось: {len(still_disputed)} → {DISPUTED_FILE}')
        else:
            both_ok.extend(expert_ok)

        print('\n>>> ШАГ 2 ЗАВЕРШЁН\n')

    # ШАГ 3: Фикс wrong (3 круга)
    if both_wrong:
        print(f'\n===== ШАГ 3: Фикс {len(both_wrong)} задач (3 круга) =====\n')
        for circle in range(1, 4):
            print(f'--- Круг {circle} ---')
            fixes = run_phase(tbu, both_wrong, fix_worker, FIXES_FILE, f'fix-c{circle}', False)
            print(f'  Исправлено: {len(fixes)}')
            apply_fixes(tbu)

            with open(EXPERT_AUDIT_FILE, 'w', encoding='utf-8') as f: pass
            ea = run_phase(tbu, both_wrong, audit_worker, EXPERT_AUDIT_FILE,
                          f'verify-c{circle}', True, EXPERT_AUDIT_SYS, "adaptive", 4000)
            still = [uid for uid in both_wrong if ea.get(uid, {}).get('answer_correct') == False]
            unknown = [uid for uid in both_wrong if uid not in ea]
            fixed_now = len(both_wrong) - len(still) - len(unknown)
            print(f'  OK после круга {circle}: {fixed_now}')
            both_wrong = still + unknown
            if not both_wrong: print('  Все исправлены!'); break
            all_f = load_fixes()
            for uid in both_wrong:
                all_f.pop(uid, None)
            with open(FIXES_FILE, 'w', encoding='utf-8') as f:
                for r in all_f.values(): f.write(json.dumps(r, ensure_ascii=False) + '\n')

        if both_wrong:
            print(f'\n  {len(both_wrong)} не прошли → {BROKEN_FILE}')
            with open(BROKEN_FILE, 'w', encoding='utf-8') as f:
                for uid in both_wrong:
                    f.write(json.dumps(tbu[uid], ensure_ascii=False) + '\n')
        print('\n>>> ШАГ 3 ЗАВЕРШЁН\n')

    # ИТОГ
    print(f'\n{"="*50}')
    print(f'OK: {len(both_ok)}, WRONG: {len(both_wrong)}/{len(tasks)}')
    with err_lock:
        if err_counter:
            top = sorted(err_counter.items(), key=lambda kv: -kv[1])[:8]
            print('Ошибки: ' + ', '.join(f'{k}×{v}' for k, v in top))
    print(f'{"="*50}')

if __name__ == '__main__':
    main()
