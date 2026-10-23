#!/usr/bin/env python3
"""
FORMYLA Methods Local Runner
============================

Улучшает все 102 метода через DeepSeek API v4-pro.
Запускается ЛОКАЛЬНО у Victor на его машине.

USAGE:
    # 1. Установить переменную окружения (Windows PowerShell):
    $env:DEEPSEEK_API_KEY = "sk-..."

    # или Linux/Mac:
    export DEEPSEEK_API_KEY="sk-..."

    # 2. Положить рядом файл paste.txt со 102 методами

    # 3. Запуск:
    python formyla_local_runner.py

    # По умолчанию: 6 workers, модель deepseek-v4-pro, output = all_methods_improved.json
    # Можно указать флаги:
    python formyla_local_runner.py --workers 8 --input paste.txt --output improved.json

ФИЧИ:
    - Инкрементальное сохранение: после КАЖДОГО метода записывает результат
    - Пропускает уже улучшенные (при перезапуске продолжит с места остановки)
    - Retry-логика: 3 попытки с увеличением max_tokens при обрыве
    - Постпроцессинг LaTeX: \\(...\\) -> $...$
    - Многопоточность: 6+ методов параллельно

ОЖИДАЕМОЕ ВРЕМЯ: 30-60 минут для всех 102 методов на 6 потоках.
ОЖИДАЕМАЯ СТОИМОСТЬ: ~2.5-3M токенов DeepSeek v4-pro.
"""

import json
import os
import re
import sys
import time
import argparse
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# Ключ встроен по твоей просьбе. ОТЗОВИ ЕГО после запуска на
# https://platform.deepseek.com/api_keys — он утёк в чат и в этом файле.
API_KEY = os.environ.get("DEEPSEEK_API_KEY", "").strip()

DEEPSEEK_BASE = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-v4-pro"

session = requests.Session()

print_lock = threading.Lock()
def safe_print(*args, **kwargs):
    with print_lock:
        print(*args, **kwargs, flush=True)

def normalize_latex(text):
    r"""Convert \(...\) -> $...$ and \[...\] -> $$...$$"""
    if not text:
        return text
    text = re.sub(r'\\\[(.+?)\\\]', r'$$\1$$', text, flags=re.DOTALL)
    text = re.sub(r'\\\((.+?)\\\)', r'$\1$', text, flags=re.DOTALL)
    return text

def call_deepseek(system_msg, user_msg, max_tokens=16000, timeout=300, retries=3):
    """Call DeepSeek with retry logic. Returns (content, usage, error)."""
    headers = {
        'Authorization': f'Bearer {API_KEY}',
        'Content-Type': 'application/json',
    }
    
    for attempt in range(retries):
        payload = {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg}
            ],
            "max_tokens": max_tokens,
            "temperature": 0.3,
        }
        try:
            r = session.post(DEEPSEEK_BASE, json=payload, headers=headers, timeout=timeout)
            if r.status_code != 200:
                if attempt < retries - 1:
                    time.sleep(2 * (attempt + 1))
                    continue
                return '', {}, f"HTTP {r.status_code}: {r.text[:200]}"
            
            data = r.json()
            msg = data['choices'][0]['message']
            content = msg.get('content') or ''
            finish_reason = data['choices'][0].get('finish_reason', '')
            usage = data.get('usage', {})
            
            if not content and finish_reason == 'length':
                new_max = int(max_tokens * 1.5)
                if attempt < retries - 1 and new_max <= 32000:
                    max_tokens = new_max
                    time.sleep(1)
                    continue
                return '', usage, f"Empty (finish=length)"
            
            if not content:
                if attempt < retries - 1:
                    time.sleep(2 * (attempt + 1))
                    continue
                return '', usage, "Empty content"
            
            return content, usage, None
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            return '', {}, str(e)
    return '', {}, "Max retries"

SYS = "Ты эксперт по олимпиадной математике и методист. Улучшай статьи о методах. Весь LaTeX: $...$ и $$...$$ (НЕ \\(...\\)). Проверяй всю математику."

def process_method(method):
    code = method['method_code']
    name = method['method_name']
    difficulty = method.get('difficulty_level', '?')
    grades = method.get('grades', [])
    competitions = method.get('recommended_competitions', [])
    
    improved = dict(method)
    total_tokens = 0
    errors = []
    
    # 1. definition
    c, u, e = call_deepseek(SYS,
        f"Улучши определение (definition_md) метода {code}: {name}. 2-3 абзаца, доступных новичку и математически точных, много формул $...$. Текущее:\n{method.get('definition_md','')[:3000]}\nВерни ТОЛЬКО текст.",
        max_tokens=6000)
    if e: errors.append(f"def:{e}")
    else: improved['definition_md'] = normalize_latex(c); total_tokens += u.get('total_tokens',0)
    
    # 2. theorems
    c, u, e = call_deepseek(SYS,
        f"Улучши теоремы (main_theorems_md) метода {code}: {name}. Формулы $...$ и $$...$$, условия применимости. Формат: **Название:** формула. *Условие:* ... *Когда использовать:* ... Текущее:\n{method.get('main_theorems_md','')[:5000]}\nВерни ТОЛЬКО текст.",
        max_tokens=8000)
    if e: errors.append(f"thm:{e}")
    else: improved['main_theorems_md'] = normalize_latex(c); total_tokens += u.get('total_tokens',0)
    
    # 3. techniques
    c, u, e = call_deepseek(SYS,
        f"Улучши приёмы (typical_techniques_md) метода {code}: {name}. 5-7 конкретных пошаговых приёмов с формулами $...$. Текущее:\n{method.get('typical_techniques_md','')[:4000]}\nВерни ТОЛЬКО текст.",
        max_tokens=8000)
    if e: errors.append(f"tec:{e}")
    else: improved['typical_techniques_md'] = normalize_latex(c); total_tokens += u.get('total_tokens',0)
    
    # 4. worked_example (главное поле)
    cur_ex = method.get('worked_example_md','')[:20000]
    c, u, e = call_deepseek(SYS,
        f"""Улучши раздел примеров (worked_example_md) метода {code}: {name} (сложность {difficulty}/5).

ТРЕБОВАНИЯ:
1. Ровно 3 примера РАЗНОЙ сложности:
   - Пример 1 (лёгкий): для новичка, базовое применение
   - Пример 2 (средний): типовая олимпиадная задача уровня ВсОШ
   - Пример 3 (сложный): красивая/усиленная задача

2. Формат каждого примера:
### Задача N. [условие задачи]
**Источник:** [тренировочная или указать олимпиаду]
**Как думать (рассуждение ученика):**
1. *Что я вижу?*
2. *Какой триггер сработал?*
3. *Первый ход?*
4. *Ключевая идея?*
**Решение:**
[полное решение с формулами]
**Ответ:** [краткий]
**Что было главным:** [ключевой вывод]

3. ВЕСЬ LaTeX: $...$ и $$...$$ (запрещено \\(...\\) и \\[...\\])
4. Проверь КАЖДОЕ вычисление и формулу на правильность
5. Формул должно быть много, но без избыточности

Определение (контекст): {method.get('definition_md','')[:800]}
Теоремы (контекст): {method.get('main_theorems_md','')[:800]}

Текущий worked_example_md:
{cur_ex}

Верни ТОЛЬКО улучшенный текст worked_example_md.""",
        max_tokens=16000, timeout=600)
    if e: errors.append(f"ex:{e}")
    else: improved['worked_example_md'] = normalize_latex(c); total_tokens += u.get('total_tokens',0)
    
    # 5. pitfalls
    c, u, e = call_deepseek(SYS,
        f"Улучши ловушки (pitfalls_md) метода {code}: {name}. 4-6 типичных ошибок в формате: **Ошибка: [название]** -> Почему неверно: [объяснение] -> Как избежать: [совет]. Формулы $...$. Текущее:\n{method.get('pitfalls_md','')[:4000]}\nВерни ТОЛЬКО текст.",
        max_tokens=8000)
    if e: errors.append(f"pit:{e}")
    else: improved['pitfalls_md'] = normalize_latex(c); total_tokens += u.get('total_tokens',0)
    
    # 6. why_it_works
    c, u, e = call_deepseek(SYS,
        f"Улучши why_it_works_md метода {code}: {name}. 1 абзац (3-5 предложений), математически точный, формулы $...$. Текущее:\n{method.get('why_it_works_md','')[:2000]}\nВерни ТОЛЬКО текст.",
        max_tokens=4000)
    if e: errors.append(f"why:{e}")
    else: improved['why_it_works_md'] = normalize_latex(c); total_tokens += u.get('total_tokens',0)
    
    fields_done = 6 - len(errors)
    safe_print(f"[{code}] DONE: {fields_done}/6 fields, {total_tokens} tokens, errors={len(errors)}")
    return improved, fields_done, total_tokens, errors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', '-i', default='paste.txt', help='Input JSON file')
    parser.add_argument('--output', '-o', default='all_methods_improved.json', help='Output JSON')
    parser.add_argument('--workers', '-w', type=int, default=6, help='Parallel workers')
    parser.add_argument('--methods', '-m', help='Comma-separated codes (optional)')
    args = parser.parse_args()
    
    with open(args.input, 'r', encoding='utf-8') as f:
        all_methods = json.load(f)
    safe_print(f"Loaded {len(all_methods)} methods from {args.input}")
    
    # Load existing output if present
    existing = {}
    if os.path.exists(args.output):
        with open(args.output, 'r', encoding='utf-8') as f:
            existing_data = json.load(f)
            existing = {m['method_code']: m for m in existing_data}
        safe_print(f"Loaded {len(existing)} existing entries from {args.output}")
    
    # Determine what to process
    filter_codes = set(args.methods.split(',')) if args.methods else None
    to_process = []
    for m in all_methods:
        code = m['method_code']
        if filter_codes and code not in filter_codes:
            continue
        if code in existing:
            orig = next(o for o in all_methods if o['method_code'] == code)
            changed = sum(1 for f in ['definition_md','main_theorems_md','typical_techniques_md','worked_example_md','pitfalls_md','why_it_works_md'] if orig.get(f,'') != existing[code].get(f,''))
            if changed == 6:
                safe_print(f"[{code}] already improved, skip")
                continue
        to_process.append(m)
    
    safe_print(f"To process: {len(to_process)} methods with {args.workers} workers, model={MODEL}\n")
    
    save_lock = threading.Lock()
    
    def save():
        output = []
        for m in all_methods:
            output.append(existing.get(m['method_code'], m))
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
    
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(process_method, m): m['method_code'] for m in to_process}
        completed = 0
        for future in as_completed(futures):
            code = futures[future]
            try:
                improved, fields_done, tokens, errors = future.result()
                with save_lock:
                    existing[code] = improved
                    completed += 1
                    save()
                    safe_print(f"    ({completed}/{len(to_process)} saved)")
            except Exception as e:
                safe_print(f"[{code}] EXCEPTION: {e}")
    
    save()
    safe_print(f"\nDONE. Total improved: {sum(1 for c in existing if existing[c])}/102")

if __name__ == '__main__':
    main()
