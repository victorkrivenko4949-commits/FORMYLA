#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Final fix for grade 11 vsosh 2020 regional Day 2 problems.
Uses split API calls (problems 6-7, then 8-10).
Includes enhanced JSON fixing: handles both LaTeX backslash escapes AND unescaped double quotes.
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
    """Call DeepSeek API and return the response text."""
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


def fix_unescaped_quotes(text):
    """
    Fix unescaped double quotes inside JSON string values.
    
    This uses a state machine that tracks JSON structure:
    - When outside a string, " starts a string
    - When inside a string, " ends it ONLY if followed by a structural char (, ] } or whitespace+structural)
    - Otherwise the " is escaped as \"
    
    Also handles the tricky case where string content contains patterns like:
    ...текст: "цитата", продолжение...
    The first " starts a nested quote, the " before , is ambiguous.
    We handle this by looking ahead more carefully.
    """
    # First fix backslash escapes
    text = fix_json_escapes(text)
    
    result = []
    i = 0
    in_string = False
    
    while i < len(text):
        c = text[i]
        
        # Handle escape sequences in string - copy verbatim
        if c == '\\' and in_string and i + 1 < len(text):
            result.append(c)
            result.append(text[i+1])
            i += 2
            continue
        
        if c == '"':
            if not in_string:
                in_string = True
                result.append(c)
            else:
                # We're inside a string. Check if this " closes it.
                # Look ahead past whitespace for a structural character
                j = i + 1
                while j < len(text) and text[j] in ' \t\n\r':
                    j += 1
                
                if j < len(text) and text[j] in ',]}':
                    # Structural character follows - this " closes the string
                    in_string = False
                    result.append(c)
                else:
                    # Not at structural boundary - this is an unescaped quote inside content
                    result.append('\\"')
            i += 1
        else:
            result.append(c)
            i += 1
    
    # Edge case: if we're still "in_string" at the end, the last " was actually content
    # This shouldn't happen with valid-ish JSON, but handle gracefully
    # We'll just append nothing extra - the JSON will be invalid but that's the best we can do
    
    return ''.join(result)


def extract_json(text):
    """Extract JSON array from DeepSeek response, handling various issues."""
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
    
    # CRITICAL: Fix both LaTeX escapes AND unescaped quotes
    print("  Fixing JSON escapes...", flush=True)
    text = fix_unescaped_quotes(text)
    
    # Check if response has both [ and ]
    if '[' not in text:
        print("  ERROR: No '[' in response!", flush=True)
        return None
    if ']' not in text:
        print("  ERROR: No ']' in response - response was truncated!", flush=True)
        return None
    
    # Try direct parse first
    try:
        data = json.loads(text)
        if isinstance(data, (list, dict)):
            print(f"  JSON parsed directly!", flush=True)
            return data
    except json.JSONDecodeError as e:
        print(f"  Direct parse failed: {e}", flush=True)
        print(f"  Around pos {e.pos}: {repr(text[max(0,e.pos-80):e.pos+80])}", flush=True)
    
    # Fallback: extract between outermost [ and ]
    start = text.find('[')
    end = text.rfind(']')
    if end > start:
        snippet = text[start:end+1]
        try:
            data = json.loads(snippet)
            print(f"  JSON parsed via bracket extraction!", flush=True)
            return data
        except json.JSONDecodeError as e:
            print(f"  Bracket extraction failed: {e}", flush=True)
            print(f"  Around pos {e.pos}: {repr(snippet[max(0,e.pos-80):e.pos+80])}", flush=True)
    
    # Fallback: try line-by-line per-problem extraction
    print("  Trying line-by-line extraction...", flush=True)
    try:
        problems = extract_problems_manual(text)
        if problems and len(problems) >= 1:
            print(f"  Manual extraction got {len(problems)} problems", flush=True)
            return problems
    except Exception as e:
        print(f"  Manual extraction failed: {e}", flush=True)
    
    return None


def extract_problems_manual(text):
    """
    Manually extract problems from potentially broken JSON.
    Works by finding each {"num": N, ...} object balanced by braces.
    """
    problems = []
    i = 0
    
    while i < len(text):
        # Find next '{'
        brace_start = text.find('{', i)
        if brace_start == -1:
            break
        
        # Find matching '}' by counting braces
        depth = 0
        brace_end = -1
        j = brace_start
        in_str = False
        
        while j < len(text):
            c = text[j]
            if c == '\\' and in_str and j + 1 < len(text):
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
            # Extract the object text
            obj_text = text[brace_start:brace_end + 1]
            
            # Fix and try to parse this object individually
            fixed_obj = fix_unescaped_quotes(obj_text)
            try:
                obj = json.loads(fixed_obj)
                if isinstance(obj, dict) and 'num' in obj:
                    problems.append(obj)
            except json.JSONDecodeError:
                # Even this failed - try regex extraction of fields
                obj_data = {}
                for key in ['num', 'text', 'answer', 'solution']:
                    # Find "key": value
                    pattern = f'"{key}"\\s*:\\s*'
                    match = re.search(pattern, fixed_obj)
                    if match:
                        val_start = match.end()
                        if val_start < len(fixed_obj) and fixed_obj[val_start] == '"':
                            # String value - find the closing quote
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
                            # Non-string value (num)
                            qpos = val_start
                            while qpos < len(fixed_obj) and fixed_obj[qpos] not in ',}]\n':
                                qpos += 1
                            val = fixed_obj[val_start:qpos].strip()
                            try:
                                obj_data[key] = int(val)
                            except ValueError:
                                obj_data[key] = val
                
                if 'num' in obj_data:
                    problems.append(obj_data)
            
            i = brace_end + 1
        else:
            i = brace_start + 1
    
    return problems


def load_olympiads_db():
    """Load OLYMPIADS_DB from olympiads.py."""
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
    
    print("ERROR: Could not find OLYMPIADS_DB!", flush=True)
    sys.exit(1)


def ast_to_dict(ast_node):
    """Convert AST node to Python dict/list/primitive."""
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
    """Save back to olympiads.py."""
    print("Saving olympiads.py...", flush=True)
    content = 'OLYMPIADS_DB = ' + json.dumps(db_list, ensure_ascii=False, indent=2)
    content += '\n'
    
    if os.path.exists('olympiads.py'):
        shutil.copy2('olympiads.py', 'olympiads_backup_grade11_v5.py')
        print("  Backup: olympiads_backup_grade11_v5.py", flush=True)
    
    with open('olympiads.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"  Written {len(content)} bytes", flush=True)


def main():
    # Load data
    content, ast_entries = load_olympiads_db()
    
    # Convert to dicts
    print("Converting AST entries to dicts...", flush=True)
    all_entries = []
    for i, entry in enumerate(ast_entries):
        d = ast_to_dict(entry)
        all_entries.append(d)
    
    print(f"  Total entries: {len(all_entries)}", flush=True)
    
    # Get grade 11 entry
    idx = GRADE_11_INDEX
    if idx >= len(all_entries):
        print(f"ERROR: Index {idx} out of range!")
        sys.exit(1)
    
    entry = all_entries[idx]
    existing_problems = entry.get('problems', [])
    
    print(f"\n{'='*60}")
    print(f"Entry index {idx}: grade={entry.get('grade','?')}, id={entry.get('id','')}")
    print(f"  Existing problems: {len(existing_problems)}")
    print(f"  Round title: {entry.get('round_title', '')}")
    
    # Check if already has day field
    has_day = any('day' in p for p in existing_problems)
    print(f"  Has 'day' field: {has_day}")
    
    if has_day:
        print("  Entry already has day fields! Checking if Day 2 problems exist...")
        day2_count = sum(1 for p in existing_problems if p.get('day') == 2)
        if day2_count >= 5:
            print(f"  Already has {day2_count} Day 2 problems. Nothing to do.")
            return
    
    # Format existing Day 1 problems as context
    existing_text = "\n".join([
        f"Задача {p.get('num')}: {p.get('text', '')[:200]}"
        for p in existing_problems
    ])
    
    # ============================================================
    # APPROACH: Split into 2 API calls
    # Call 1: problems 6-7 (2 problems)
    # Call 2: problems 8-10 (3 problems)
    # ============================================================
    
    all_day2_problems = []
    
    # --- CALL 1: Problems 6-7 ---
    print(f"\n{'='*60}")
    print(f"CALL 1: Requesting problems 6-7 from DeepSeek...")
    print(f"{'='*60}")
    
    sys_prompt_67 = """Ты — эксперт по Всероссийской олимпиаде школьников (ВсОШ) по математике.
Твоя задача — вспомнить РЕАЛЬНЫЕ задачи 2-го дня регионального этапа ВсОШ 2020-2021 учебного года для 11 класса.

Верни ТОЛЬКО валидный JSON-массив из 2 объектов (задачи 6 и 7). Каждый объект должен иметь поля:
  - "num": номер задачи (6 или 7)
  - "text": полный текст задачи на русском языке
  - "answer": краткий ответ
  - "solution": краткое решение (3-5 предложений)

ВАЖНО: Все кавычки внутри строк JSON должны быть экранированы (\\").
ВАЖНО: Заверши JSON-массив закрывающей скобкой ].
Формулы используй в формате $...$ или $$...$$."""

    user_prompt_67 = f"""ВсОШ, 2020-2021 учебный год, 11 класс, Региональный этап.

ВОТ ЗАДАЧИ 1-го ДНЯ (уже есть в базе, НЕ повторяй их):
{existing_text}

Твоя задача: вспомни и верни ТОЛЬКО задачи 6 и 7 второго дня.
Дай краткие решения (3-5 предложений).

Верни строго JSON-массив из 2 объектов:
[
  {{
    "num": 6,
    "text": "полный текст задачи 6",
    "answer": "ответ",
    "solution": "краткое решение"
  }},
  {{
    "num": 7,
    "text": "полный текст задачи 7",
    "answer": "ответ",
    "solution": "краткое решение"
  }}
]"""

    response_67 = call_deepseek(sys_prompt_67, user_prompt_67, temperature=0.2, max_tokens=16000)
    
    if response_67 is None:
        print("  CALL 1 FAILED!")
        sys.exit(1)
    
    # Save raw response
    with open('_last_response_11_v5_call1.txt', 'w', encoding='utf-8') as f:
        f.write(response_67)
    print(f"  Call 1 response saved to _last_response_11_v5_call1.txt ({len(response_67)} chars)", flush=True)
    print(f"  Has closing ']': {response_67.rstrip().endswith(']')}", flush=True)
    
    # Parse
    print("  Parsing JSON...", flush=True)
    problems_67 = extract_json(response_67)
    
    if problems_67 is None:
        print("  CALL 1: Failed to parse JSON!")
        sys.exit(1)
    
    if isinstance(problems_67, dict):
        for key in ['problems', 'tasks', 'day2', 'data']:
            if key in problems_67:
                problems_67 = problems_67[key]
                break
    
    if not isinstance(problems_67, list):
        print(f"  CALL 1: Unexpected type: {type(problems_67).__name__}")
        sys.exit(1)
    
    print(f"  Call 1 got {len(problems_67)} problems", flush=True)
    for p in problems_67:
        num = p.get('num', '?')
        text_preview = (p.get('text', '') or '')[:80]
        print(f"    Problem {num}: {text_preview}...", flush=True)
    
    all_day2_problems.extend(problems_67)
    
    # --- CALL 2: Problems 8-10 ---
    print(f"\n{'='*60}")
    print(f"CALL 2: Requesting problems 8-10 from DeepSeek...")
    print(f"{'='*60}")
    
    sys_prompt_810 = """Ты — эксперт по Всероссийской олимпиаде школьников (ВсОШ) по математике.
Твоя задача — вспомнить РЕАЛЬНЫЕ задачи 2-го дня регионального этапа ВсОШ 2020-2021 учебного года для 11 класса.

Верни ТОЛЬКО валидный JSON-массив из 3 объектов (задачи 8, 9 и 10). Каждый объект должен иметь поля:
  - "num": номер задачи (8, 9 или 10)
  - "text": полный текст задачи на русском языке
  - "answer": краткий ответ
  - "solution": краткое решение (3-5 предложений)

ВАЖНО: Все кавычки внутри строк JSON должны быть экранированы (\\").
ВАЖНО: Заверши JSON-массив закрывающей скобкой ].
Формулы используй в формате $...$ или $$...$$."""

    user_prompt_810 = f"""ВсОШ, 2020-2021 учебный год, 11 класс, Региональный этап.

ВОТ ЗАДАЧИ 1-го ДНЯ (уже есть в базе, НЕ повторяй их):
{existing_text}

Твоя задача: вспомни и верни ТОЛЬКО задачи 8, 9 и 10 второго дня.
Дай краткие решения (3-5 предложений).

Верни строго JSON-массив из 3 объектов:
[
  {{
    "num": 8,
    "text": "полный текст задачи 8",
    "answer": "ответ",
    "solution": "краткое решение"
  }},
  {{
    "num": 9,
    "text": "полный текст задачи 9",
    "answer": "ответ",
    "solution": "краткое решение"
  }},
  {{
    "num": 10,
    "text": "полный текст задачи 10",
    "answer": "ответ",
    "solution": "краткое решение"
  }}
]"""

    response_810 = call_deepseek(sys_prompt_810, user_prompt_810, temperature=0.2, max_tokens=16000)
    
    if response_810 is None:
        print("  CALL 2 FAILED!")
        sys.exit(1)
    
    # Save raw response
    with open('_last_response_11_v5_call2.txt', 'w', encoding='utf-8') as f:
        f.write(response_810)
    print(f"  Call 2 response saved to _last_response_11_v5_call2.txt ({len(response_810)} chars)", flush=True)
    print(f"  Has closing ']': {response_810.rstrip().endswith(']')}", flush=True)
    
    # Parse - with enhanced quote fixing
    print("  Parsing JSON (with enhanced quote fixing)...", flush=True)
    problems_810 = extract_json(response_810)
    
    if problems_810 is None:
        print("  CALL 2: Failed to parse JSON!")
        print("  Trying fallback: use previously saved data if available...")
        # Check if we can load from the old call2 response
        if os.path.exists('_last_response_11_v4_call2.txt'):
            print("  Attempting to parse previous Call 2 response with enhanced fixer...")
            with open('_last_response_11_v4_call2.txt', 'r', encoding='utf-8') as f:
                old_response = f.read()
            problems_810 = extract_json(old_response)
        
        if problems_810 is None:
            sys.exit(1)
    
    if isinstance(problems_810, dict):
        for key in ['problems', 'tasks', 'day2', 'data']:
            if key in problems_810:
                problems_810 = problems_810[key]
                break
    
    if not isinstance(problems_810, list):
        print(f"  CALL 2: Unexpected type: {type(problems_810).__name__}")
        sys.exit(1)
    
    print(f"  Call 2 got {len(problems_810)} problems", flush=True)
    for p in problems_810:
        num = p.get('num', '?')
        text_preview = (p.get('text', '') or '')[:80]
        print(f"    Problem {num}: {text_preview}...", flush=True)
    
    all_day2_problems.extend(problems_810)
    
    # ============================================================
    # Combine and apply results
    # ============================================================
    print(f"\n{'='*60}")
    print(f"Total Day 2 problems from both calls: {len(all_day2_problems)}")
    
    # Validate and renumber if needed
    valid = []
    for p in all_day2_problems:
        if not isinstance(p, dict):
            continue
        num = p.get('num', 0) or p.get('number', 0)
        if isinstance(num, str) and num.isdigit():
            num = int(num)
        if not isinstance(num, int):
            num = 0
        if 6 <= num <= 10 and p.get('text', '').strip():
            valid.append(p)
    
    print(f"  Valid problems (nums 6-10 with text): {len(valid)}")
    
    if len(valid) < 3:
        print(f"  ERROR: Too few valid problems ({len(valid)}), trying fallback...")
        valid = []
        for p in all_day2_problems:
            if isinstance(p, dict) and p.get('text', '').strip():
                valid.append(p)
        for i, p in enumerate(valid):
            p['num'] = 6 + i
        
        if len(valid) < 3:
            print(f"  Still too few problems ({len(valid)}). Aborting.")
            sys.exit(1)
    
    print(f"  Using {len(valid)} problems for Day 2")
    for p in valid:
        num = p.get('num', '?')
        text_preview = (p.get('text', '') or '')[:80]
        print(f"    Problem {num}: {text_preview}...", flush=True)
    
    # Add day=2 to new problems
    for p in valid:
        p['day'] = 2
        p.setdefault('answer', '')
        p.setdefault('solution', '')
        p.setdefault('solution_status', '')
        p.setdefault('text', '')
    
    # Add day=1 to existing problems
    for p in existing_problems:
        p['day'] = 1
    
    # Append Day 2 problems
    existing_problems.extend(valid)
    
    print(f"\n  Total problems now: {len(existing_problems)}")
    print(f"  Day 1: {sum(1 for p in existing_problems if p.get('day')==1)}")
    print(f"  Day 2: {sum(1 for p in existing_problems if p.get('day')==2)}")
    
    # Save
    save_olympiads_db(all_entries)
    
    # Also update data/olympiads_db.py
    db_py_path = 'data/olympiads_db.py'
    if os.path.exists(db_py_path):
        print(f"\nUpdating {db_py_path}...", flush=True)
        db_content = '# -*- coding: utf-8 -*-\n'
        db_content += '# Extracted from routes/olympiad.py for reuse by the olympiad Blueprint.\n'
        db_content += '# This file contains only the OLYMPIADS_DB data dictionary.\n\n'
        db_content += 'OLYMPIADS_DB = ' + json.dumps(all_entries, ensure_ascii=False, indent=2)
        db_content += '\n'
        
        shutil.copy2(db_py_path, db_py_path + '.bak5')
        with open(db_py_path, 'w', encoding='utf-8') as f:
            f.write(db_content)
        print(f"  Updated {db_py_path} ({len(db_content)} bytes)", flush=True)
    
    print("\n[OK] Grade 11 Day 2 problems added successfully using split approach with enhanced JSON fixing!")


if __name__ == '__main__':
    main()
