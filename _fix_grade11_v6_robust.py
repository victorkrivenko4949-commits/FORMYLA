#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Robust fix for grade 11 vsosh 2020 regional Day 2 problems.
Uses manual brace-balanced extraction to avoid JSON parsing issues.
"""
import ast
import json
import os
import sys
import time
import requests
import shutil
import re

os.chdir(r'C:\Users\Victor\Desktop\Новая папка (2)')

DEEPSEEK_KEY = os.environ.get('DEEPSEEK_API_KEY', '')
if not DEEPSEEK_KEY:
    print("ERROR: DEEPSEEK_API_KEY not set!")
    sys.exit(1)

API_URL = "https://api.deepseek.com/v1/chat/completions"
MODEL = "deepseek-chat"
GRADE_11_INDEX = 1046


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
            r = requests.post(API_URL, json=payload, headers=headers, timeout=600)
            r.raise_for_status()
            data = r.json()
            content = data["choices"][0]["message"]["content"]
            print(f"  Response length: {len(content)} chars", flush=True)
            return content
        except Exception as e:
            print(f"  Attempt {attempt+1} failed: {e}", flush=True)
            if attempt < 2:
                time.sleep(5 * (2 ** attempt))
    return None


def fix_json_escapes(text):
    """Fix invalid backslash escapes in JSON string content."""
    VALID_ESCAPES = set('"\\/bfnrtu')
    result = []
    i = 0
    while i < len(text):
        c = text[i]
        if c == '\\' and i + 1 < len(text):
            nextc = text[i + 1]
            if nextc in VALID_ESCAPES:
                result.append(c)
                result.append(nextc)
                i += 2
            else:
                result.append('\\\\')
                result.append(nextc)
                i += 2
        else:
            result.append(c)
            i += 1
    return ''.join(result)


def extract_problems_robust(text):
    """
    Extract problem objects from DeepSeek JSON response.
    
    Strategy:
    1. Try direct JSON.parse (with fix_json_escapes for backslashes)
    2. If that fails, use manual brace-balanced extraction per problem
    """
    # Strip markdown fences
    if '```json' in text:
        text = text.split('```json', 1)[1]
        if '```' in text:
            text = text.split('```', 1)[0]
    elif '```' in text:
        text = text.split('```', 1)[1]
        if '```' in text:
            text = text.split('```', 1)[0]
    
    text = text.strip()
    
    # Strategy 1: fix backslashes and try direct parse
    fixed = fix_json_escapes(text)
    try:
        data = json.loads(fixed)
        if isinstance(data, list):
            print(f"  Direct JSON parse succeeded: {len(data)} problems", flush=True)
            return data
        elif isinstance(data, dict):
            # Maybe wrapped in a dict
            for key in ['problems', 'tasks', 'day2', 'data']:
                if key in data and isinstance(data[key], list):
                    print(f"  Direct JSON parse (wrapped in '{key}'): {len(data[key])} problems", flush=True)
                    return data[key]
            return [data]
    except json.JSONDecodeError:
        pass
    
    # Strategy 2: Try parsing just the array between [ and ]
    start = text.find('[')
    end = text.rfind(']')
    if start >= 0 and end > start:
        snippet = text[start:end+1]
        fixed_snippet = fix_json_escapes(snippet)
        try:
            data = json.loads(fixed_snippet)
            if isinstance(data, list):
                print(f"  Bracket-extracted JSON parse: {len(data)} problems", flush=True)
                return data
        except json.JSONDecodeError:
            pass
    
    # Strategy 3: Manual brace extraction
    print(f"  Using manual brace extraction...", flush=True)
    problems = []
    
    i = start if start >= 0 else 0
    while i < len(text):
        # Find next '{'
        brace_start = text.find('{', i)
        if brace_start == -1:
            break
        
        # Find matching '}' with quote awareness
        depth = 0
        brace_end = -1
        in_str = False
        j = brace_start
        while j < len(text):
            c = text[j]
            if c == '\\':
                j += 2
                continue
            if c == '"':
                in_str = not in_str
            if not in_str:
                if c == '{':
                    depth += 1
                elif c == '}':
                    depth -= 1
                    if depth == 0:
                        brace_end = j
                        break
            j += 1
        
        if brace_end > brace_start:
            obj_text = text[brace_start:brace_end + 1]
            
            # Fix backslashes in this object
            fixed_obj = fix_json_escapes(obj_text)
            
            # Try to parse this object
            try:
                obj = json.loads(fixed_obj)
                if isinstance(obj, dict) and ('num' in obj or 'text' in obj):
                    problems.append(obj)
            except json.JSONDecodeError:
                # Manual field extraction
                obj_data = {}
                for key in ['num', 'text', 'answer', 'solution', 'number']:
                    pattern = rf'"{re.escape(key)}"\s*:\s*'
                    match = re.search(pattern, fixed_obj)
                    if match:
                        val_start = match.end()
                        if val_start < len(fixed_obj) and fixed_obj[val_start] == '"':
                            # String value - find closing quote with escape awareness
                            qpos = val_start + 1
                            while qpos < len(fixed_obj):
                                if fixed_obj[qpos] == '\\':
                                    qpos += 2
                                elif fixed_obj[qpos] == '"':
                                    break
                                else:
                                    qpos += 1
                            obj_data[key] = fixed_obj[val_start + 1:qpos]
                        else:
                            # Non-string value (number) - read until comma, brace, or bracket
                            qpos = val_start
                            while qpos < len(fixed_obj) and fixed_obj[qpos] not in ',}]\n':
                                qpos += 1
                            val = fixed_obj[val_start:qpos].strip()
                            try:
                                obj_data[key] = int(val)
                            except ValueError:
                                obj_data[key] = val
                
                if 'num' in obj_data or 'text' in obj_data:
                    # Renumber if needed
                    if 'number' in obj_data and 'num' not in obj_data:
                        obj_data['num'] = obj_data['number']
                    problems.append(obj_data)
            
            i = brace_end + 1
        else:
            i = brace_start + 1
    
    print(f"  Manual extraction: {len(problems)} problems", flush=True)
    return problems


# ============================================================
def load_olympiads_db():
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
    print("ERROR: Could not find OLYMPIADS_DB!", flush=True)
    sys.exit(1)


def ast_to_dict(ast_node):
    if isinstance(ast_node, ast.Dict):
        result = {}
        for k, v in zip(ast_node.keys, ast_node.values):
            key = ast_to_dict(k)
            result[key] = ast_to_dict(v)
        return result
    elif isinstance(ast_node, ast.List):
        return [ast_to_dict(elem) for elem in ast_node.elts]
    elif isinstance(ast_node, ast.Constant):
        return ast_node.value
    elif isinstance(ast_node, ast.Str):
        return ast_node.s
    elif isinstance(ast_node, ast.Num):
        return ast_node.n
    elif isinstance(ast_node, ast.NameConstant):
        return ast_node.value
    elif isinstance(ast_node, ast.UnaryOp) and isinstance(ast_node.op, ast.USub):
        return -ast_to_dict(ast_node.operand)
    else:
        return None


def save_olympiads_db(db_list):
    print("Saving olympiads.py...", flush=True)
    content = 'OLYMPIADS_DB = ' + json.dumps(db_list, ensure_ascii=False, indent=2)
    content += '\n'
    if os.path.exists('olympiads.py'):
        shutil.copy2('olympiads.py', 'olympiads_backup_grade11_v6.py')
        print("  Backup: olympiads_backup_grade11_v6.py", flush=True)
    with open('olympiads.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"  Written {len(content)} bytes", flush=True)


def validate_problems(problems, expected_nums=None):
    """Validate and renumber problems. Returns list of valid problems."""
    valid = []
    for p in problems:
        if not isinstance(p, dict):
            continue
        if not p.get('text', '').strip():
            continue
        num = p.get('num', 0) or p.get('number', 0)
        if isinstance(num, str) and num.isdigit():
            num = int(num)
        if not isinstance(num, int):
            num = 0
        if expected_nums and num in expected_nums:
            valid.append(p)
        elif not expected_nums:
            valid.append(p)
    
    # Renumber
    for i, p in enumerate(valid):
        if expected_nums:
            p['num'] = expected_nums[i] if i < len(expected_nums) else expected_nums[-1] + (i - len(expected_nums) + 1)
        else:
            p['num'] = 6 + i
    
    return valid


def main():
    content, ast_entries = load_olympiads_db()
    
    print("Converting AST entries to dicts...", flush=True)
    all_entries = []
    for i, entry in enumerate(ast_entries):
        d = ast_to_dict(entry)
        all_entries.append(d)
    print(f"  Total entries: {len(all_entries)}", flush=True)
    
    idx = GRADE_11_INDEX
    entry = all_entries[idx]
    existing_problems = entry.get('problems', [])
    
    print(f"\n{'='*60}")
    print(f"Entry index {idx}: grade={entry.get('grade','?')}, id={entry.get('id','')}")
    print(f"  Existing problems: {len(existing_problems)}")
    
    has_day = any('day' in p for p in existing_problems)
    print(f"  Has 'day' field: {has_day}")
    
    if has_day:
        day2_count = sum(1 for p in existing_problems if p.get('day') == 2)
        if day2_count >= 5:
            print(f"  Already has {day2_count} Day 2 problems. Nothing to do.")
            return
    
    existing_text = "\n".join([
        f"Задача {p.get('num')}: {p.get('text', '')[:200]}"
        for p in existing_problems
    ])
    
    all_day2 = []
    
    # ===== CALL 1: Problems 6-7 =====
    print(f"\n{'='*60}")
    print(f"CALL 1: Problems 6-7")
    print(f"{'='*60}")
    
    sys_prompt = """Ты — эксперт по Всероссийской олимпиаде школьников (ВсОШ) по математике.
Верни ТОЛЬКО валидный JSON-массив из 2 задач 2-го дня регионального этапа ВсОШ 2020-2021 для 11 класса.
Каждый объект: {"num": число, "text": "полный текст", "answer": "ответ", "solution": "решение"}.
НЕ используй кавычки внутри строк JSON.
Заверши массив ]."""

    user_prompt = f"""ВсОШ 2020-2021, 11 класс, Региональный этап.

Задачи 1-го дня (НЕ повторяй):
{existing_text}

Верни ТОЛЬКО задачи 6 и 7 второго дня в JSON."""
    
    resp = call_deepseek(sys_prompt, user_prompt, max_tokens=16000)
    if resp is None:
        print("  CALL 1 FAILED!"); sys.exit(1)
    
    with open('_last_11_call1_v6.txt', 'w', encoding='utf-8') as f:
        f.write(resp)
    print(f"  Saved ({len(resp)} chars)", flush=True)
    
    probs = extract_problems_robust(resp)
    if not probs:
        print("  CALL 1: No problems extracted!"); sys.exit(1)
    
    valid = validate_problems(probs, expected_nums=[6, 7])
    print(f"  Valid: {len(valid)} problems")
    for p in valid:
        print(f"    Problem {p.get('num')}: {(p.get('text','') or '')[:60]}...")
    all_day2.extend(valid)
    
    # ===== CALL 2: Problems 8-10 =====
    print(f"\n{'='*60}")
    print(f"CALL 2: Problems 8-10")
    print(f"{'='*60}")
    
    sys_prompt2 = """Ты — эксперт по Всероссийской олимпиаде школьников (ВсОШ) по математике.
Верни ТОЛЬКО валидный JSON-массив из 3 задач 2-го дня регионального этапа ВсОШ 2020-2021 для 11 класса.
Каждый объект: {"num": число, "text": "полный текст", "answer": "ответ", "solution": "решение"}.
НЕ используй кавычки внутри строк JSON.
Заверши массив ]."""

    user_prompt2 = f"""ВсОШ 2020-2021, 11 класс, Региональный этап.

Задачи 1-го дня (НЕ повторяй):
{existing_text}

Верни ТОЛЬКО задачи 8, 9 и 10 второго дня в JSON."""
    
    resp2 = call_deepseek(sys_prompt2, user_prompt2, max_tokens=16000)
    if resp2 is None:
        print("  CALL 2 FAILED!"); sys.exit(1)
    
    with open('_last_11_call2_v6.txt', 'w', encoding='utf-8') as f:
        f.write(resp2)
    print(f"  Saved ({len(resp2)} chars)", flush=True)
    
    probs2 = extract_problems_robust(resp2)
    
    # If new call fails, try old response
    if not probs2 and os.path.exists('_last_response_11_v4_call2.txt'):
        print("  Trying old Call 2 response...", flush=True)
        with open('_last_response_11_v4_call2.txt', 'r', encoding='utf-8') as f:
            old_resp = f.read()
        probs2 = extract_problems_robust(old_resp)
    
    if not probs2:
        print("  CALL 2: No problems extracted!"); sys.exit(1)
    
    valid2 = validate_problems(probs2, expected_nums=[8, 9, 10])
    print(f"  Valid: {len(valid2)} problems")
    for p in valid2:
        print(f"    Problem {p.get('num')}: {(p.get('text','') or '')[:60]}...")
    all_day2.extend(valid2)
    
    # ===== Combine =====
    print(f"\n{'='*60}")
    print(f"Total: {len(all_day2)} problems")
    
    # Renumber sequentially
    for i, p in enumerate(all_day2):
        p['num'] = 6 + i
    
    print(f"  Using {len(all_day2)} problems for Day 2:")
    for p in all_day2:
        print(f"    Problem {p['num']}: {(p.get('text','') or '')[:80]}...")
    
    if len(all_day2) < 3:
        print(f"  ERROR: Too few problems ({len(all_day2)}). Aborting.")
        sys.exit(1)
    
    # Add day fields
    for p in all_day2:
        p['day'] = 2
        p.setdefault('answer', '')
        p.setdefault('solution', '')
        p.setdefault('solution_status', '')
    
    for p in existing_problems:
        p['day'] = 1
    
    existing_problems.extend(all_day2)
    
    print(f"\n  Total problems now: {len(existing_problems)}")
    print(f"  Day 1: {sum(1 for p in existing_problems if p.get('day')==1)}")
    print(f"  Day 2: {sum(1 for p in existing_problems if p.get('day')==2)}")
    
    save_olympiads_db(all_entries)
    
    # Update data/olympiads_db.py
    db_py_path = 'data/olympiads_db.py'
    if os.path.exists(db_py_path):
        print(f"\nUpdating {db_py_path}...", flush=True)
        db_content = '# -*- coding: utf-8 -*-\n'
        db_content += '# Extracted from routes/olympiad.py for reuse by the olympiad Blueprint.\n'
        db_content += '# This file contains only the OLYMPIADS_DB data dictionary.\n\n'
        db_content += 'OLYMPIADS_DB = ' + json.dumps(all_entries, ensure_ascii=False, indent=2)
        db_content += '\n'
        shutil.copy2(db_py_path, db_py_path + '.bak6')
        with open(db_py_path, 'w', encoding='utf-8') as f:
            f.write(db_content)
        print(f"  Updated {db_py_path} ({len(db_content)} bytes)", flush=True)
    
    print("\n[OK] Grade 11 Day 2 problems added successfully!")


if __name__ == '__main__':
    main()
