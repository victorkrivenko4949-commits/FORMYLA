#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fix grade 10 variant 2 (idx 1042) - missing problems 9 and 10 only.
Previous call truncated because problems 6 and 7 had very long solutions.
Calls DeepSeek asking ONLY for problems 9 and 10 with higher max_tokens.
"""
import ast
import json
import os
import sys
import time
import re
import shutil
import requests

sys.stdout.reconfigure(encoding='utf-8')
os.environ['PYTHONIOENCODING'] = 'utf-8'
os.chdir(r'C:\Users\Victor\Desktop\Новая папка (2)')

DEEPSEEK_KEY = os.environ.get('DEEPSEEK_API_KEY', '')
if not DEEPSEEK_KEY:
    print("ERROR: DEEPSEEK_API_KEY not set!")
    sys.exit(1)

API_URL = "https://api.deepseek.com/v1/chat/completions"
MODEL = "deepseek-chat"

def fix_json_escapes(text):
    VALID_ESCAPES = set('"\\/bfnrtu')
    result = []
    i = 0
    while i < len(text):
        c = text[i]
        if c == '\\' and i + 1 < len(text):
            nextc = text[i + 1]
            if nextc in VALID_ESCAPES:
                result.append(c); result.append(nextc); i += 2
            else:
                result.append('\\\\'); result.append(nextc); i += 2
        else:
            result.append(c); i += 1
    return ''.join(result)

def extract_field_value(text, key, start_pos=0):
    pattern = rf'"{re.escape(key)}"\s*:\s*'
    m = re.search(pattern, text[start_pos:])
    if not m:
        return None, start_pos
    key_end = start_pos + m.end()
    if key_end >= len(text):
        return None, key_end
    if text[key_end] == '"':
        result_chars = []
        i = key_end + 1
        while i < len(text):
            c = text[i]
            if c == '\\':
                result_chars.append(c); i += 1
                if i < len(text):
                    result_chars.append(text[i]); i += 1
            elif c == '"':
                j = i + 1
                while j < len(text) and text[j] in ' \t\n\r':
                    j += 1
                if j < len(text) and text[j] in ',}]':
                    return ''.join(result_chars), j
                else:
                    result_chars.append(c); i += 1
            else:
                result_chars.append(c); i += 1
        return ''.join(result_chars), len(text)
    else:
        j = key_end
        while j < len(text) and text[j] not in ',}\n\r]':
            j += 1
        raw = text[key_end:j].strip()
        try:
            return int(raw), j
        except ValueError:
            return raw, j

def extract_problems_anchor(text, expected_nums=(9, 10)):
    """Extract problems by anchoring on 'num': N patterns."""
    if '```json' in text:
        text = text.split('```json', 1)[1]
        if '```' in text:
            text = text.split('```', 1)[0]
    elif '```' in text:
        text = text.split('```', 1)[1]
        if '```' in text:
            text = text.split('```', 1)[0]
    text = text.strip()
    text = fix_json_escapes(text)
    
    # Try direct json.loads first
    try:
        data = json.loads(text)
        if isinstance(data, list):
            print(f"  Direct JSON parse: {len(data)} problems", flush=True)
            return data
        elif isinstance(data, dict):
            for key in ['problems', 'tasks', 'day2', 'data']:
                if key in data and isinstance(data[key], list):
                    print(f"  Direct JSON parse (wrapped in '{key}'): {len(data[key])} problems", flush=True)
                    return data[key]
    except json.JSONDecodeError:
        pass
    
    print(f"  Using anchor-based extraction for nums {expected_nums}...", flush=True)
    problems = []
    for num in expected_nums:
        pattern = rf'"num"\s*:\s*{num}(?:\s*[,}}\s]|\s*\n)'
        m = re.search(pattern, text)
        if not m:
            print(f"  WARNING: 'num': {num} not found!", flush=True)
            continue
        match_end = m.end()
        obj_start = -1
        brace_depth = 0
        for pos in range(match_end - 1, -1, -1):
            c = text[pos]
            if c == '}':
                brace_depth += 1
            elif c == '{':
                if brace_depth == 0:
                    obj_start = pos
                    break
                brace_depth -= 1
        if obj_start < 0:
            print(f"  WARNING: Could not find opening '{{' for num={num}!", flush=True)
            continue
        obj = {}
        pos = obj_start
        val, pos = extract_field_value(text, 'num', pos)
        if val is not None: obj['num'] = val
        val, pos = extract_field_value(text, 'text', pos)
        if val is not None: obj['text'] = val
        val, pos = extract_field_value(text, 'answer', pos)
        if val is not None: obj['answer'] = val
        val, pos = extract_field_value(text, 'solution', pos)
        if val is not None: obj['solution'] = val
        if 'num' in obj or 'text' in obj:
            problems.append(obj)
            txt_preview = (str(obj.get('text', '')) or '')[:80]
            print(f"  Extracted problem {obj.get('num', '?')}: {txt_preview}", flush=True)
        else:
            print(f"  WARNING: No useful fields extracted for num={num}!", flush=True)
    print(f"  Anchor extraction: {len(problems)} problems", flush=True)
    return problems

def call_deepseek(system_prompt, user_prompt, temperature=0.2, max_tokens=16000):
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_KEY}",
        "Content-Type": "application/json",
    }
    for attempt in range(3):
        try:
            print(f"  API call attempt {attempt+1}...", flush=True)
            r = requests.post(API_URL, json=payload, headers=headers, timeout=180)
            r.raise_for_status()
            data = r.json()
            content = data["choices"][0]["message"]["content"]
            print(f"  Response: {len(content)} chars", flush=True)
            return content
        except Exception as e:
            print(f"  Attempt {attempt+1} failed: {e}", flush=True)
            if attempt < 2:
                wait = 5 * (2 ** attempt)
                print(f"  Waiting {wait}s...", flush=True)
                time.sleep(wait)
    return None

def load_olympiads_db():
    print("Loading olympiads.py via AST...", flush=True)
    with open('olympiads.py', 'r', encoding='utf-8') as f:
        content = f.read()
    tree = ast.parse(content)
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == 'OLYMPIADS_DB' for t in node.targets
        ):
            entries = node.value.elts
            print(f"  Found OLYMPIADS_DB with {len(entries)} entries", flush=True)
            return content, entries
    print("ERROR: Could not find OLYMPIADS_DB assignment!", flush=True)
    sys.exit(1)

def convert_ast_to_dict(ast_node):
    if isinstance(ast_node, ast.Dict):
        result = {}
        for k, v in zip(ast_node.keys, ast_node.values):
            key = convert_ast_to_dict(k)
            result[key] = convert_ast_to_dict(v)
        return result
    elif isinstance(ast_node, ast.List):
        return [convert_ast_to_dict(elem) for elem in ast_node.elts]
    elif isinstance(ast_node, ast.Constant):
        return ast_node.value
    elif isinstance(ast_node, ast.Str):
        return ast_node.s
    elif isinstance(ast_node, ast.Num):
        return ast_node.n
    elif isinstance(ast_node, ast.NameConstant):
        return ast_node.value
    elif isinstance(ast_node, ast.UnaryOp) and isinstance(ast_node.op, ast.USub):
        return -convert_ast_to_dict(ast_node.operand)
    else:
        return None

def main():
    # Step 1: Load current state
    content, ast_entries = load_olympiads_db()
    
    print("Converting AST entries to dicts...", flush=True)
    all_entries = []
    for i, entry in enumerate(ast_entries):
        d = convert_ast_to_dict(entry)
        all_entries.append(d)
    print(f"  Total entries: {len(all_entries)}", flush=True)
    
    idx = 1042
    entry = all_entries[idx]
    existing_problems = entry.get('problems', [])
    
    print(f"\n{'='*60}", flush=True)
    print(f"Entry index {idx}: grade {entry['grade']} {entry.get('subject','')}", flush=True)
    print(f"  Existing problems: {len(existing_problems)}", flush=True)
    
    day1 = [p for p in existing_problems if p.get('day') == 1]
    day2 = [p for p in existing_problems if p.get('day') == 2]
    print(f"  Day 1: {len(day1)} problems", flush=True)
    print(f"  Day 2: {len(day2)} problems", flush=True)
    
    # Check which Day 2 problems we already have
    day2_nums = set(p.get('num') for p in day2)
    missing_nums = [n for n in [9, 10] if n not in day2_nums]
    print(f"  Already have Day 2 nums: {sorted(day2_nums)}", flush=True)
    print(f"  Missing: {missing_nums}", flush=True)
    
    if not missing_nums:
        print("  Nothing to fix! All Day 2 problems present.", flush=True)
        return
    
    # Build Day 1 context for the prompt
    day1_text = "\n".join([
        f"Задача {p.get('num')}: {str(p.get('text', ''))[:300]}"
        for p in day1
    ])
    
    # Also provide already-extracted problems 6-8 as context
    day2_existing_text = "\n".join([
        f"Задача {p.get('num')}: {str(p.get('text', ''))[:200]}"
        for p in day2
    ])
    
    sys_prompt = """Ты — эксперт по Всероссийской олимпиаде школьников (ВсОШ) по математике.
Твоя задача — вспомнить РЕАЛЬНЫЕ задачи 2-го дня регионального этапа ВсОШ 2020-2021 учебного года для 10 класса.

Ты должен опираться на свои знания реальных задач ВсОШ.

ВАЖНО: Верни ТОЛЬКО валидный JSON-массив из объектов. Каждый объект должен иметь поля:
  - "num": номер задачи (9, 10)
  - "text": полный текст задачи
  - "answer": краткий ответ
  - "solution": полное решение с LaTeX

Формулы используй в формате $...$ для инлайн и $$...$$ для выключенных формул."""

    user_prompt = f"""ВсОШ, 2020-2021 учебный год, 10 класс, Региональный этап (ВАРИАНТ 2).

ЗАДАЧИ 1-го ДНЯ (уже есть):
{day1_text}

ЗАДАЧИ 2-го ДНЯ (уже есть, НЕ ПОВТОРЯЙ):
{day2_existing_text}

Твоя задача: ВСПОМНИ и верни ТОЛЬКО задачи 9 и 10 (номера 9 и 10) второго дня для 10 класса регионального этапа ВсОШ 2020-2021 (вариант 2).

Верни строго JSON-массив из 2 объектов:
[
  {{
    "num": 9,
    "text": "полный текст задачи 9",
    "answer": "ответ",
    "solution": "полное решение"
  }},
  {{
    "num": 10,
    "text": "полный текст задачи 10",
    "answer": "ответ",
    "solution": "полное решение"
  }}
]"""

    print(f"\n  Calling DeepSeek for problems 9 and 10...", flush=True)
    response = call_deepseek(sys_prompt, user_prompt, temperature=0.2, max_tokens=16000)
    
    if response is None:
        print("  FAILED to get response!", flush=True)
        return
    
    # Save raw response
    raw_file = '_raw_response_g10_idx1042_v2.txt'
    with open(raw_file, 'w', encoding='utf-8') as f:
        f.write(response)
    print(f"  Raw response saved to {raw_file} ({len(response)} chars)", flush=True)
    
    # Parse
    day2_new = extract_problems_anchor(response, expected_nums=(9, 10))
    
    if not day2_new:
        print("  FAILED to extract any problems!", flush=True)
        return
    
    # Validate
    valid = []
    for p in day2_new:
        num = p.get('num', 0)
        if isinstance(num, str):
            try:
                num = int(num)
            except (ValueError, TypeError):
                num = 0
        if num in (9, 10):
            valid.append(p)
    
    print(f"  Valid problems (9, 10): {len(valid)}", flush=True)
    
    if not valid:
        print("  No valid problems 9 or 10 found!", flush=True)
        return
    
    # Add day=2 and defaults
    for p in valid:
        p['day'] = 2
        p.setdefault('answer', '')
        p.setdefault('solution', '')
        p.setdefault('solution_status', '')
    
    # Append to existing problems
    existing_problems.extend(valid)
    
    print(f"\n  Total problems now: {len(existing_problems)}", flush=True)
    print(f"  Day 1: {sum(1 for p in existing_problems if p.get('day')==1)}", flush=True)
    print(f"  Day 2: {sum(1 for p in existing_problems if p.get('day')==2)}", flush=True)
    print(f"  Day 2 nums: {sorted([p.get('num') for p in existing_problems if p.get('day')==2])}", flush=True)
    
    # Save
    print("\nSaving olympiads.py...", flush=True)
    output = 'OLYMPIADS_DB = ' + json.dumps(all_entries, ensure_ascii=False, indent=2) + '\n'
    
    import shutil
    shutil.copy2('olympiads.py', 'olympiads_backup_g10v2_fix.py')
    print("  Backup saved as olympiads_backup_g10v2_fix.py", flush=True)
    
    with open('olympiads.py', 'w', encoding='utf-8') as f:
        f.write(output)
    print(f"  Written {len(output)} bytes to olympiads.py", flush=True)
    
    # Also update data/olympiads_db.py
    db_path = 'data/olympiads_db.py'
    if os.path.exists(db_path):
        print(f"\nUpdating {db_path}...", flush=True)
        shutil.copy2(db_path, db_path + '.bak_g10v2')
        db_content = '# -*- coding: utf-8 -*-\n'
        db_content += '# Extracted from routes/olympiad.py for reuse by the olympiad Blueprint.\n'
        db_content += '# This file contains only the OLYMPIADS_DB data dictionary.\n\n'
        db_content += 'OLYMPIADS_DB = ' + json.dumps(all_entries, ensure_ascii=False, indent=2) + '\n'
        with open(db_path, 'w', encoding='utf-8') as f:
            f.write(db_content)
        print(f"  Updated {db_path} ({len(db_content)} bytes)", flush=True)
    
    print(f"\n[OK] Done! Added {len(valid)} problems to idx {idx}", flush=True)
    for p in valid:
        print(f"  - Problem {p['num']}: {str(p.get('text',''))[:80]}", flush=True)

if __name__ == '__main__':
    main()