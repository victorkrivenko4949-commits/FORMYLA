#!/usr/bin/env python3
"""Fix G2 — heuristic task selection + DeepSeek analysis only."""
import json, re, time, requests, urllib3

urllib3.disable_warnings()
API_KEY = 'sk-ad477f779a1045cba3cc09100e908370'
API_URL = 'https://api.deepseek.com/chat/completions'
MODEL = 'deepseek-v4-pro'

METHODS_FILE = 'all_methods_real_final.json'
TASKS_FILE = 'olympiad_tasks_PERFECT (3).json'
OUTPUT = 'all_methods_real_final.json'

def call_api(payload, label='', max_retries=15):
    session = requests.Session(); session.verify = False
    headers = {'Authorization': f'Bearer {API_KEY}', 'Content-Type': 'application/json'}
    for attempt in range(max_retries):
        try:
            r = session.post(API_URL, json=payload, headers=headers, timeout=180)
            if r.status_code == 429:
                time.sleep(min(60, 15*(attempt+1))); continue
            if r.status_code >= 500:
                time.sleep(min(60, 10*(attempt+1))); continue
            if r.status_code != 200:
                time.sleep(10); continue
            d = r.json()
            c = d['choices'][0]['message'].get('content','') or ''
            if not c:
                print(f'  [{label}] Empty retry {attempt+1}...', flush=True)
                time.sleep(10); continue
            return c, d.get('usage',{})
        except Exception as e:
            time.sleep(min(60, 10*(attempt+1)))
    return '', {}

with open(METHODS_FILE, 'r', encoding='utf-8') as f:
    methods = json.load(f)
with open(TASKS_FILE, 'r', encoding='utf-8') as f:
    olympiad_tasks = json.load(f)

m = next(x for x in methods if x['method_code'] == 'G2')
code = 'G2'; name = m['method_name']; section = 'G'
print(f'Fixing [{code}] {name}', flush=True)

# Heuristic selection from section G tasks
G_KWS = ['неравенств','коши','йенсен','среднее','выпукл','оценк','максимум','минимум',
         'докажите','больше','меньш','наименьш','наибольш','доказат','выполняет']
method_name_words = re.findall(r'[а-яё]{4,}', name.lower())

scored = []
for t in olympiad_tasks:
    text = (t.get('text','') + ' ' + str(t.get('solution','') or '')[:200]).lower()
    ss = sum(1 for kw in G_KWS if kw in text)
    ns = sum(2 for w in method_name_words if len(w) > 4 and w in text)
    gs = 1 if t.get('grade',0) in [7,8,9] else 0
    total = ss + ns + gs
    if total > 0:
        scored.append((total, t))
scored.sort(key=lambda x: x[0], reverse=True)

# Take top 3, pick one with best grade
top = scored[:3] if scored else []
if not top:
    top = [(0, t) for t in olympiad_tasks[:3]]

# Pick one with grade 7-9 if available
best = None
for _, t in top:
    if t.get('grade',0) in [7,8,9]:
        best = t; break
if not best:
    best = top[0][1]

st = best
src = st.get('source_name','?')
print(f'Heuristic pick: {src} (grade {st.get("grade","?")})', flush=True)

# Normalize LaTeX
def nltx(t):
    if not t: return t
    t = re.sub(r'\\\[(.+?)\\\]', r'$$\1$$', t, flags=re.DOTALL)
    t = re.sub(r'\\\((.+?)\\\)', r'$\1$', t, flags=re.DOTALL)
    return t

# Step: Analysis
ap = f"""Метод: {code}: {name}

Определение: {m.get('definition_md','')[:400]}

Задача (РЕАЛЬНАЯ, из базы):
{st.get('text','')}

Официальное решение:
{str(st.get('solution','') or '')[:3000]}

Ответ: {str(st.get('answer','') or '')}

Напиши разбор в формате:

### Задача 1. [точная формулировка из условия выше]

**Источник:** {src}

**Как думать (рассуждение ученика):**
1. *Что я вижу?* ...
2. *Какой триггер сработал?* (свяжи с методом {code}) ...
3. *Первый ход?* ...
4. *Ключевая идея?* ...

**Решение:**
[перепиши решение с формулами $...$, добавь пояснения]

**Ответ:** [ответ]

**Что было главным:** [ключевой вывод метода]

Верни ТОЛЬКО текст разбора."""

print('Calling DeepSeek for analysis...', flush=True)
analysis, _ = call_api({'model': MODEL, 'max_tokens': 12000, 'temperature': 0.3,
    'messages': [{'role':'system','content':'Ты — эксперт по олимпиадной математике. LaTeX: $...$ и $$...$$. Верни только разбор.'},
                 {'role':'user','content': ap}]}, label='G2-analysis')

if not analysis:
    print('FAILED: no analysis from DeepSeek', flush=True)
else:
    analysis = nltx(analysis)
    req = ['### Задача 1','**Источник:**','**Как думать:**','**Решение:**','**Ответ:**','**Что было главным:**']
    miss = [r for r in req if r not in analysis]
    if miss:
        print(f'WARNING: missing: {miss}', flush=True)

    existing = m.get('worked_example_md','')
    parts = existing.split('### Задача')
    kept = parts[2:]  # skip training task 1
    if kept:
        m['worked_example_md'] = analysis.strip() + '\n\n### Задача' + '### Задача'.join(kept)
    else:
        m['worked_example_md'] = analysis.strip()

    print(f'New length: {len(m["worked_example_md"])} chars', flush=True)
    with open(OUTPUT, 'w', encoding='utf-8') as f:
        json.dump(methods, f, ensure_ascii=False, indent=2)
    print('SAVED!', flush=True)
