import os
#!/usr/bin/env python3
"""
FORMYLA L4-L5: РИЗОНЕР (исправленный)
======================================
max_tokens=32000 (место для ответа после рассуждений)
Отладка: печатает что получил если не парсится
"""
import json, time, re, os, requests
from collections import Counter

API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-v4-pro"
INPUT_FILE = "FORMYLA_L1_L5_TOP5.jsonl"
FIXES_FILE = "L4L5_REASONER_FIXES.jsonl"
MAX_RETRIES = 3

session = requests.Session()
session.headers.update({
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
})

def api_call(messages, max_tokens=32000, timeout=300):
    payload = {
        "model": MODEL, "messages": messages, "max_tokens": max_tokens,
        "temperature": 0.1, "thinking": {"type": "enabled"},
    }
    for attempt in range(MAX_RETRIES):
        try:
            r = session.post(API_URL, json=payload, timeout=timeout)
            d = r.json()
            if "error" not in d:
                msg = d["choices"][0]["message"]
                content = msg.get("content", "")
                finish = d["choices"][0].get("finish_reason", "")
                if finish == "length" and not content:
                    print(f"    (обрезано на рассуждениях, не хватило токенов)")
                    return None
                return content
            err = str(d.get("error", {}).get("message", ""))
            if "429" in err:
                time.sleep(5 * (attempt + 1))
                continue
            print(f"  API error: {err[:60]}")
        except Exception as e:
            s = str(e)
            print(f"  Ошибка (попытка {attempt+1}): {s[:80]}")
            time.sleep(3)
    return None

def parse_json(text):
    if not text: return None
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r'^```(json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
    # Ищем последний JSON в тексте (ризонер может написать несколько)
    s = text.rfind('{')
    e = text.rfind('}')
    if s >= 0 and e > s:
        # Берём от последней { к последней }
        # Но JSON может быть вложенный — попробуем с конца
        while s >= 0:
            try:
                return json.loads(text[s:e+1])
            except:
                # Пробуем предыдущую {
                s = text.rfind('{', 0, s)
        # Если не получилось — пробуем первую {
        s = text.find('{')
        e = text.rfind('}')
        if s >= 0 and e > s:
            try: return json.loads(text[s:e+1])
            except: pass
    return None

def load_tasks():
    with open(INPUT_FILE, encoding='utf-8') as f:
        return [json.loads(l) for l in f if l.strip()]

def save_tasks(tasks):
    with open(INPUT_FILE, 'w', encoding='utf-8') as f:
        for t in tasks:
            f.write(json.dumps(t, ensure_ascii=False, default=str) + '\n')

def load_fixes():
    fixes = {}
    try:
        for l in open(FIXES_FILE, encoding='utf-8'):
            l = l.strip()
            if l:
                d = json.loads(l)
                if d.get('answer'): fixes[d['task_uid']] = d
    except: pass
    return fixes

def save_fix(uid, answer, solution):
    with open(FIXES_FILE, 'a', encoding='utf-8') as f:
        f.write(json.dumps({'task_uid': uid, 'answer': answer, 'solution': solution},
            ensure_ascii=False) + '\n')

FIX_SYS = 'Реши задачу. Ответ ВЕРНЫЙ. После всех рассуждений ОБЯЗАТЕЛЬНО заверши коротким JSON (решение до 100 слов): {"answer":"...","solution":"..."}\n\nВАЖНО: не пиши очень длинные рассуждения, будь краток. Обязательно закончи JSONом в конце.'

def main():
    print('=' * 60)
    print('FORMYLA L4-L5: РИЗОНЕР (max_tokens=32000, отладка)')
    print('=' * 60)

    tasks = load_tasks()
    l4l5 = [t for t in tasks if t.get('level') in (4, 5)]
    tasks_by_uid = {t['task_uid']: t for t in tasks}

    prev_wrong = set()
    try:
        for l in open('L4L5_AUDIT_RESULTS.jsonl', encoding='utf-8'):
            l = l.strip()
            if l:
                r = json.loads(l)
                if r.get('answer_correct') == False:
                    prev_wrong.add(r['task_uid'])
    except: pass

    already = load_fixes()
    to_fix = [uid for uid in prev_wrong if uid in tasks_by_uid and uid not in already]

    print(f'Задач для фикса: {len(to_fix)}')
    print(f'max_tokens=32000, thinking=enabled, 1 поток')
    print()

    fixed = 0
    for i, uid in enumerate(to_fix):
        t = tasks_by_uid[uid]
        stmt = (t.get("statement","") or "")[:800]
        user = (f'Класс: {t["grade"]}\nУровень: L{t["level"]}\nТема: {t.get("theme","")}\n\n'
                f'Задача:\n{stmt}\n\nРеши. Выдай JSON с answer и solution.')

        t0 = time.time()
        resp = api_call([{"role":"system","content":FIX_SYS},{"role":"user","content":user}],
                        max_tokens=32000, timeout=300)
        elapsed = time.time() - t0

        if not resp:
            print(f'  [{i+1}/{len(to_fix)}] FAIL — пустой ответ ({elapsed:.0f}с)')
            continue

        result = parse_json(resp)

        if result and result.get('answer') and result.get('solution'):
            save_fix(uid, result['answer'], result['solution'])
            tasks_by_uid[uid]['answer'] = result['answer']
            tasks_by_uid[uid]['solution'] = result['solution']
            tasks_by_uid[uid]['fixed_reasoner'] = True
            fixed += 1
            print(f'  [{i+1}/{len(to_fix)}] OK ({elapsed:.0f}с) — {result["answer"][:50]}')
        else:
            # Отладка — покажи что получили
            print(f'  [{i+1}/{len(to_fix)}] PARSE FAIL ({elapsed:.0f}с)')
            print(f'    Ответ ({len(resp)} симв): {resp[:200]}')
            print()

        if fixed % 10 == 0 and fixed > 0:
            save_tasks(list(tasks_by_uid.values()))
        time.sleep(1)

    save_tasks(list(tasks_by_uid.values()))
    print(f'\nИтого: исправлено {fixed}/{len(to_fix)}')

if __name__ == '__main__':
    main()
