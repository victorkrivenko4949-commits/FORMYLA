import os
#!/usr/bin/env python3
"""Fix 8 methods: properly add BOTH Ответ and Что было главным to T2,T3,T4.
The original Ответ was accidentally cut by fix_remaining_10.py's cleaning logic."""
import json, re, time, requests, urllib3

urllib3.disable_warnings()
API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
API_URL = 'https://api.deepseek.com/chat/completions'
MODEL = 'deepseek-v4-pro'

METHODS_FILE = 'all_methods_real_final.json'
OUTPUT = 'all_methods_real_final.json'

FIX_ME = {
    'A2a': [2,3,4], 'B3': [2,3,4], 'B7': [2,3,4],
    'C12': [2,3,4], 'D3': [2,3,4], 'E1': [3,4],  # E1 T2 was fixed
    'E4': [2,3,4], 'E17': [2,3,4]
}

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

SYS = """Ты — эксперт по олимпиадной математике и методист.
Тебе дан текст задачи с решением. Напиши ТОЛЬКО две строки:
**Ответ:** [правильный ответ, формулы в $...$]
**Что было главным:** [ключевой вывод метода, 1-2 предложения]
НЕ повторяй условие или решение."""

for m in methods:
    code = m['method_code']
    if code not in FIX_ME:
        continue
    name = m['method_name']
    we = m.get('worked_example_md','')
    parts = we.split('### Задача')
    print(f'\n[{code}] {name[:50]}', flush=True)
    
    fixed = False
    for idx in FIX_ME[code]:
        if idx >= len(parts):
            continue
        t = parts[idx]
        if '**Ответ:**' in t and '**Что было главным:**' in t:
            print(f'  Task {idx}: already OK', flush=True)
            continue
        
        # Even if Что было главным exists, we need to also re-add Ответ
        # Strip trailing Что было главным (the one we added that was wrong)
        # Keep the original content before any fix
        # Actually: the original Ответ was cut. The Что was added by fix_8.
        # We need to remove the trailing Что and add fresh Ответ+Что
        
        # Remove trailing Что было главным that was added by fix_8
        main_pos = t.rfind('\n**Что было главным:**')
        if main_pos > 0:
            clean_t = t[:main_pos].rstrip()
        else:
            clean_t = t.rstrip()
        
        print(f'  Task {idx}: fixing BOTH Ответ+Что...', flush=True)
        
        completion, _ = call_api(
            {'model': MODEL, 'max_tokens': 2000, 'temperature': 0.3,
             'messages': [{'role':'system','content': SYS},
                          {'role':'user','content': f'Метод {code}: {name}\n\nЗадача:\n### Задача{clean_t[-3500:]}'}]},
            label=f'{code}-T{idx}')
        
        if completion:
            parts[idx] = clean_t + '\n\n' + completion.strip()
            print(f'    => COMPLETED ({len(completion)} chars)', flush=True)
            fixed = True
        else:
            print(f'    => FAILED', flush=True)
    
    if fixed:
        m['worked_example_md'] = '### Задача'.join(parts)
        with open(OUTPUT, 'w', encoding='utf-8') as f:
            json.dump(methods, f, ensure_ascii=False, indent=2)
        print(f'  => SAVED', flush=True)

print('\nDONE!')
