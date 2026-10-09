import os
#!/usr/bin/env python3
"""Fix remaining 10 methods with missing Ответ/Что было главным in various tasks.
Uses DeepSeek to complete each incomplete task."""
import json, re, time, sys, requests, urllib3

urllib3.disable_warnings()
API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
API_URL = 'https://api.deepseek.com/chat/completions'
MODEL = 'deepseek-v4-pro'

METHODS_FILE = 'all_methods_real_final.json'
OUTPUT = 'all_methods_real_final.json'

# Remaining methods from validation
REMAINING = {
    'A2a': ['T2','T3','T4'],  # no_main
    'B3': ['T2','T3','T4'],    # no_main
    'B7': ['T2','T3','T4'],    # no_main
    'C7': ['T4'],              # no_answer,no_main
    'C12': ['T2','T3','T4'],   # no_main
    'D3': ['T2','T3','T4'],    # no_main
    'E1': ['T2','T3','T4'],    # no_main
    'E4': ['T2','T3','T4'],    # no_main
    'E17': ['T1','T2','T3','T4'], # T1:no_answer+no_main, T2-4:no_main
    'F8': ['T4'],              # no_answer,no_main
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
        except Exception as e:
            time.sleep(min(60, 10*(attempt+1)))
    return '', {}

with open(METHODS_FILE, 'r', encoding='utf-8') as f:
    methods = json.load(f)

SYS_COMPLETE = """Ты — эксперт по олимпиадной математике и методист.
Тебе дан текст задачи из разбора метода. В тексте не хватает секций **Ответ:** и/или **Что было главным:**.
Твоя задача — дописать недостающие секции, основываясь на тексте условия и решения.
Формат ответа:

Если не хватает обеих секций:
**Ответ:** [правильный ответ, LaTeX в $...$]
**Что было главным:** [ключевой вывод метода, 1-2 предложения]

Если не хватает только **Что было главным:**:
**Что было главным:** [ключевой вывод метода, 1-2 предложения]

НЕ повторяй весь текст задачи. Только недостающие секции."""

def complete_task(code, name, task_text, missing_answer=True, missing_main=True):
    """Call DeepSeek to fill in missing sections."""
    context = task_text[-3500:]
    
    if missing_answer and missing_main:
        instruction = "Напиши **Ответ:** и **Что было главным:**"
    elif missing_answer:
        instruction = "Напиши **Ответ:** (Что было главным уже есть, не повторяй его)"
    else:
        instruction = "Напиши **Что было главным:** (Ответ уже есть, не повторяй его)"
    
    payload = {
        'model': MODEL, 'max_tokens': 2000, 'temperature': 0.3,
        'messages': [
            {'role': 'system', 'content': SYS_COMPLETE},
            {'role': 'user', 'content': f'Метод {code}: {name}\n{instruction}\n\nТекст задачи:\n{context}'}
        ]
    }
    result, _ = call_api(payload, label=f'{code}-complete')
    return result.strip() if result else None

for code, task_indices in REMAINING.items():
    for m in methods:
        if m['method_code'] == code:
            break
    else:
        continue
    
    name = m['method_name']
    we = m.get('worked_example_md','')
    parts = we.split('### Задача')
    print(f'\n[{code}] {name[:50]} — fixing {task_indices}', flush=True)
    
    fixed_any = False
    for ti_str in task_indices:
        idx = int(ti_str[1])  # T2 -> 2
        t = parts[idx]
        
        has_a = '**Ответ:**' in t
        has_m = '**Что было главным:**' in t
        
        if has_a and has_m:
            print(f'  Task {idx}: already complete, skipping', flush=True)
            continue
        
        need_a = not has_a
        need_m = not has_m
        
        desc = []
        if need_a: desc.append('Ответ')
        if need_m: desc.append('Что было главным')
        print(f'  Task {idx}: missing {"+".join(desc)} — calling DeepSeek...', flush=True)
        
        full_task = '### Задача' + t
        completion = complete_task(code, name, full_task, need_a, need_m)
        
        if completion:
            # Clean trailing partial sections
            clean_t = t
            # Cut at last **Ответ:** or **Что было главным:**
            ans_pos = clean_t.rfind('\n**Ответ:**')
            main_pos = clean_t.rfind('\n**Что было главным:**')
            cut = max(ans_pos, main_pos)
            if cut > 0:
                clean_t = clean_t[:cut]
            clean_t = clean_t.rstrip()
            
            # Append completion
            parts[idx] = clean_t + '\n\n' + completion
            print(f'    => COMPLETED ({len(completion)} chars)', flush=True)
            fixed_any = True
        else:
            print(f'    => FAILED (empty response after all retries)', flush=True)
    
    if fixed_any:
        m['worked_example_md'] = '### Задача'.join(parts)
        with open(OUTPUT, 'w', encoding='utf-8') as f:
            json.dump(methods, f, ensure_ascii=False, indent=2)
        print(f'  => SAVED', flush=True)

print('\nALL REMAINING FIXES DONE!')
