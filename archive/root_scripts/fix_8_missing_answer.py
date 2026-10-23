import os
#!/usr/bin/env python3
"""Fix 8 methods where previous fix accidentally removed Ответ from T2,T3,T4.
These tasks only need Что было главным added back. Ответ exists earlier in the text."""
import json, re, time, requests, urllib3

urllib3.disable_warnings()
API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
API_URL = 'https://api.deepseek.com/chat/completions'
MODEL = 'deepseek-v4-pro'

METHODS_FILE = 'all_methods_real_final.json'
OUTPUT = 'all_methods_real_final.json'

FIX_ME = ['A2a', 'B3', 'B7', 'C12', 'D3', 'E1', 'E4', 'E17']

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
                time.sleep(10); continue
            return c, d.get('usage',{})
        except:
            time.sleep(min(60, 10*(attempt+1)))
    return '', {}

with open(METHODS_FILE, 'r', encoding='utf-8') as f:
    methods = json.load(f)

SYS_COMPLETE = """Ты — эксперт по олимпиадной математике и методист.
Тебе дан текст задачи с решением, но без секции **Что было главным:**.
Напиши ТОЛЬКО одну строку **Что было главным:** с ключевым выводом метода (1-2 предложения на русском).
Не повторяй условие или решение. Только:

**Что было главным:** [вывод]"""

for m in methods:
    code = m['method_code']
    if code not in FIX_ME:
        continue
    name = m['method_name']
    we = m.get('worked_example_md','')
    parts = we.split('### Задача')
    print(f'\n[{code}] {name[:50]}', flush=True)
    
    fixed_any = False
    # Fix T2, T3, T4 — add missing Ответ + Что было главным
    for idx in [2, 3, 4]:
        if idx >= len(parts):
            continue
        t = parts[idx]
        has_a = '**Ответ:**' in t
        has_m = '**Что было главным:**' in t
        
        if has_a and has_m:
            print(f'  Task {idx}: OK', flush=True)
            continue
        
        desc = []
        if not has_a: desc.append('Ответ')
        if not has_m: desc.append('Что было главным')
        print(f'  Task {idx}: missing {"+".join(desc)} — DeepSeek...', flush=True)
        
        full_task = '### Задача' + t
        completion, _ = call_api(
            {'model': MODEL, 'max_tokens': 2000, 'temperature': 0.3,
             'messages': [{'role':'system','content': SYS_COMPLETE},
                          {'role':'user','content': f'Метод {code}: {name}\n\nНапиши {"**Ответ:** и **Что было главным:**" if not has_a else "**Что было главным:**"} для задачи:\n{full_task[-3500:]}'}]},
            label=f'{code}-T{idx}')
        
        if completion:
            # Just append, don't cut anything this time
            clean_t = t.rstrip()
            parts[idx] = clean_t + '\n\n' + completion.strip()
            print(f'    => COMPLETED ({len(completion)} chars)', flush=True)
            fixed_any = True
        else:
            print(f'    => FAILED', flush=True)
    
    if fixed_any:
        m['worked_example_md'] = '### Задача'.join(parts)
        with open(OUTPUT, 'w', encoding='utf-8') as f:
            json.dump(methods, f, ensure_ascii=False, indent=2)
        print(f'  => SAVED', flush=True)

print('\nDONE!')
