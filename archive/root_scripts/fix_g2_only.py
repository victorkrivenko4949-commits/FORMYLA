import os
#!/usr/bin/env python3
"""Fix ONLY G2 — training first task replacement."""
import json, re, time, random, requests, urllib3

urllib3.disable_warnings()
API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
API_URL = 'https://api.deepseek.com/chat/completions'
MODEL = 'deepseek-v4-pro'

METHODS_FILE = 'all_methods_real_final.json'
TASKS_FILE = 'olympiad_tasks_PERFECT (3).json'
OUTPUT = 'all_methods_real_final.json'

def call_api(payload, label='', max_retries=20):
    session = requests.Session()
    session.verify = False
    headers = {'Authorization': f'Bearer {API_KEY}', 'Content-Type': 'application/json'}
    for attempt in range(max_retries):
        try:
            r = session.post(API_URL, json=payload, headers=headers, timeout=180)
            if r.status_code == 429:
                wait = min(60, 15*(attempt+1))
                print(f'  [{label}] 429, wait {wait}s...', flush=True)
                time.sleep(wait); continue
            if r.status_code >= 500:
                wait = min(60, 10*(attempt+1))
                print(f'  [{label}] {r.status_code}, wait {wait}s...', flush=True)
                time.sleep(wait); continue
            if r.status_code != 200:
                print(f'  [{label}] HTTP {r.status_code}, retry...', flush=True)
                time.sleep(10); continue
            d = r.json()
            c = d['choices'][0]['message'].get('content','') or ''
            if not c:
                print(f'  [{label}] Empty, retry...', flush=True)
                time.sleep(10); continue
            return c, d.get('usage',{})
        except Exception as e:
            wait = min(60, 10*(attempt+1))
            print(f'  [{label}] {str(e)[:80]}, wait {wait}s...', flush=True)
            time.sleep(wait)
    return '', {}

with open(METHODS_FILE, 'r', encoding='utf-8') as f:
    methods = json.load(f)
with open(TASKS_FILE, 'r', encoding='utf-8') as f:
    olympiad_tasks = json.load(f)
tasks_by_uid = {t['task_uid']: t for t in olympiad_tasks}

SECTION_FILTERS = {
    'G': ['неравенств','коши','йенсен','среднее','выпукл','оценк','максимум','минимум',
          'докажите','больше','меньш','наименьш','наибольш','доказат','выполняет'],
}

def filter_tasks(all_tasks, section, method_text):
    kws = SECTION_FILTERS.get(section, [])
    name_words = re.findall(r'[а-яё]{4,}', method_text.lower())
    scored = []
    for t in all_tasks:
        text = (t.get('text','') + ' ' + str(t.get('solution','') or '')[:200]).lower()
        ss = sum(1 for kw in kws if kw in text)
        ns = sum(2 for w in name_words if len(w) > 4 and w in text)
        gs = 1 if t.get('grade',0) in [7,8,9] else 0
        total = ss + ns + gs
        if total > 0:
            scored.append((total, t))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [t for _, t in scored[:30]]

def norm_ltx(t):
    if not t: return t
    t = re.sub(r'\\\[(.+?)\\\]', r'$$\1$$', t, flags=re.DOTALL)
    t = re.sub(r'\\\((.+?)\\\)', r'$\1$', t, flags=re.DOTALL)
    return t

m = next(x for x in methods if x['method_code'] == 'G2')
code = 'G2'; name = m['method_name']; section = 'G'
print(f'Fixing [{code}] {name}', flush=True)

# Step 1: Select
mt = name + ' ' + m.get('definition_md','')[:300]
candidates = filter_tasks(olympiad_tasks, section, mt)
if not candidates:
    candidates = random.sample(olympiad_tasks, min(30, len(olympiad_tasks)))

cand_lines = []
for i, t in enumerate(candidates[:20]):
    cand_lines.append(f"[{i+1}] task_uid: {t.get('task_uid','?')}")
    cand_lines.append(f"    source: {t.get('source_name','?')}")
    cand_lines.append(f"    grade: {t.get('grade','?')}")
    cand_lines.append(f"    text: {t.get('text','')[:300]}")
    cand_lines.append("")

sel_prompt = f"""Метод: {code}: {name}
Раздел: {section}. Сложность: {m.get('difficulty_level','?')}/5.

Описание: {m.get('definition_md','')[:600]}

Приёмы: {m.get('typical_techniques_md','')[:300]}

Кандидаты:
{chr(10).join(cand_lines)}

Выбери ОДНУ ЛУЧШУЮ задачу, которая иллюстрирует метод {code}.
Верни: task_uid: <uid>
почему: <1 предложение>"""

print('Step 1: Selecting task...', flush=True)
sel, _ = call_api({'model': MODEL, 'max_tokens': 2000, 'temperature': 0.3,
    'messages': [{'role':'system','content':'Ты — эксперт по олимпиадной математике. Выбери лучшую задачу.'},
                 {'role':'user','content': sel_prompt}]}, label='G2-select')

if not sel:
    print('FAILED: no selection', flush=True)
else:
    uid_m = re.search(r'task_uid:\s*(\S+)', sel)
    if not uid_m:
        print(f'FAILED: no uid in: {sel[:200]}', flush=True)
    else:
        uid = uid_m.group(1).strip()
        print(f'Selected: {uid[:40]}...', flush=True)
        st = tasks_by_uid.get(uid)
        if not st:
            print(f'FAILED: uid not in DB', flush=True)
        else:
            src = st.get('source_name','?')
            print(f'Source: {src}', flush=True)

            # Step 2: Analysis
            ap = f"""Метод: {code}: {name}

Определение: {m.get('definition_md','')[:400]}

Задача (РЕАЛЬНАЯ, из базы):
{st.get('text','')}

Официальное решение:
{str(st.get('solution','') or '')[:3000]}

Ответ: {str(st.get('answer','') or '')}

Напиши разбор:

### Задача 1. [точная формулировка]

**Источник:** {src}

**Как думать (рассуждение ученика):**
1. *Что я вижу?* ...
2. *Какой триггер сработал?* (свяжи с методом {code}) ...
3. *Первый ход?* ...
4. *Ключевая идея?* ...

**Решение:**
[решение с формулами $...$]

**Ответ:** [ответ]

**Что было главным:** [ключевой вывод метода]

Верни ТОЛЬКО текст разбора."""

            print('Step 2: Writing analysis...', flush=True)
            analysis, _ = call_api({'model': MODEL, 'max_tokens': 12000, 'temperature': 0.3,
                'messages': [{'role':'system','content':'Ты — эксперт по олимпиадной математике и методист. LaTeX: $...$ и $$...$$.'},
                             {'role':'user','content': ap}]}, label='G2-analysis')

            if not analysis:
                print('FAILED: no analysis', flush=True)
            else:
                analysis = norm_ltx(analysis)
                req = ['### Задача 1','**Источник:**','**Как думать:**','**Решение:**','**Ответ:**','**Что было главным:**']
                miss = [r for r in req if r not in analysis]
                if miss:
                    print(f'WARNING: missing: {miss}', flush=True)

                # Keep existing tasks 2+ (skip training task 1)
                existing = m.get('worked_example_md','')
                parts = existing.split('### Задача')
                kept = parts[2:]
                if kept:
                    m['worked_example_md'] = analysis.strip() + '\n\n### Задача' + '### Задача'.join(kept)
                else:
                    m['worked_example_md'] = analysis.strip()

                print(f'New WE length: {len(m["worked_example_md"])}', flush=True)
                with open(OUTPUT, 'w', encoding='utf-8') as f:
                    json.dump(methods, f, ensure_ascii=False, indent=2)
                print('SAVED!', flush=True)
