#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Add Day 2 problems for vsosh 2020 regional grades 9 and 10 (2 variants).
Uses DeepSeek API with anchor-based extraction to handle unescaped quotes.

Target entries:
  idx 1037: grade 9
  idx 1041: grade 10 variant 1 (id=516)
  idx 1042: grade 10 variant 2 (id=517)
"""
import ast
import json
import os
import sys
import time
import re
import shutil
import requests

# Fix encoding
sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None
os.environ['PYTHONIOENCODING'] = 'utf-8'

os.chdir(r'C:\Users\Victor\Desktop\Новая папка (2)')

DEEPSEEK_KEY = os.environ.get('DEEPSEEK_API_KEY', '')
if not DEEPSEEK_KEY:
    print("ERROR: DEEPSEEK_API_KEY not set!")
    sys.exit(1)

API_URL = "https://api.deepseek.com/v1/chat/completions"
MODEL = "deepseek-chat"

TARGET_ENTRIES = [
    {'index': 1037, 'grade': 9, 'desc': 'grade 9'},
    {'index': 1041, 'grade': 10, 'desc': 'grade 10 variant 1 (id=516)'},
    {'index': 1042, 'grade': 10, 'desc': 'grade 10 variant 2 (id=517)'},
]


def call_deepseek(system_prompt, user_prompt, temperature=0.2, max_tokens=12000):
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


def fix_json_escapes(text):
    """Fix invalid backslash escapes."""
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
    """Extract value of JSON key starting from start_pos.
    Handles unescaped quotes inside string values."""
    pattern = rf'"{re.escape(key)}"\s*:\s*'
    m = re.search(pattern, text[start_pos:])
    if not m:
        return None, start_pos
    key_end = start_pos + m.end()
    
    if key_end >= len(text):
        return None, key_end
    
    if text[key_end] == '"':
        # String value
        result_chars = []
        i = key_end + 1
        while i < len(text):
            c = text[i]
            if c == '\\':
                result_chars.append(c); i += 1
                if i < len(text):
                    result_chars.append(text[i]); i += 1
            elif c == '"':
                # Look ahead to check if this is real closing quote
                j = i + 1
                while j < len(text) and text[j] in ' \t\n\r':
                    j += 1
                if j < len(text) and text[j] in ',}]':
                    return ''.join(result_chars), j
                else:
                    # Unescaped quote inside value
                    result_chars.append(c); i += 1
            else:
                result_chars.append(c); i += 1
        return ''.join(result_chars), len(text)
    else:
        # Number value
        j = key_end
        while j < len(text) and text[j] not in ',}\n\r]':
            j += 1
        raw = text[key_end:j].strip()
        try:
            return int(raw), j
        except ValueError:
            return raw, j


def extract_problems_anchor(text, expected_nums=(6, 7, 8, 9, 10)):
    """Extract problems by anchoring on 'num': N patterns.
    Uses the same robust approach as v8 which handles unescaped quotes."""
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
    
    # Fix backslash escapes first
    text = fix_json_escapes(text)
    
    # Strategy 1: Try direct json.loads (quick win if no unescaped quotes)
    try:
        data = json.loads(text)
        if isinstance(data, list):
            print(f"  Direct JSON parse succeeded: {len(data)} problems", flush=True)
            return data
        elif isinstance(data, dict):
            for key in ['problems', 'tasks', 'day2', 'data']:
                if key in data and isinstance(data[key], list):
                    print(f"  Direct JSON parse (wrapped in '{key}'): {len(data[key])} problems", flush=True)
                    return data[key]
    except json.JSONDecodeError:
        pass
    
    # Strategy 2: Anchor-based extraction
    print(f"  Using anchor-based extraction for nums {expected_nums}...", flush=True)
    problems = []
    
    for num in expected_nums:
        # Find "num": NUM (not followed by another digit)
        pattern = rf'"num"\s*:\s*{num}(?:\s*[,}}\s]|\s*\n)'
        m = re.search(pattern, text)
        if not m:
            print(f"  WARNING: 'num': {num} not found!", flush=True)
            continue
        
        match_end = m.end()
        
        # Walk backward from the match to find the opening '{'
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
        
        # Now extract all fields from obj_start using extract_field_value
        obj = {}
        pos = obj_start
        
        # Extract num
        val, pos = extract_field_value(text, 'num', pos)
        if val is not None:
            obj['num'] = val
        
        # Extract text
        val, pos = extract_field_value(text, 'text', pos)
        if val is not None:
            obj['text'] = val
        
        # Extract answer
        val, pos = extract_field_value(text, 'answer', pos)
        if val is not None:
            obj['answer'] = val
        
        # Extract solution
        val, pos = extract_field_value(text, 'solution', pos)
        if val is not None:
            obj['solution'] = val
        
        if 'num' in obj or 'text' in obj:
            problems.append(obj)
            txt_preview = (str(obj.get('text', '')) or '')[:80]
            print(f"  Extracted problem {obj.get('num', '?')}: {txt_preview}", flush=True)
        else:
            print(f"  WARNING: No useful fields extracted for num={num}!", flush=True)
    
    print(f"  Anchor extraction: {len(problems)} problems", flush=True)
    return problems


def get_day2_prompt(grade, existing_problems):
    """Create prompt asking DeepSeek to provide Day 2 problems."""
    sys_prompt = """Ты — эксперт по Всероссийской олимпиаде школьников (ВсОШ) по математике. 
Твоя задача — вспомнить РЕАЛЬНЫЕ задачи 2-го дня регионального этапа ВсОШ 2020-2021 учебного года для указанного класса.

Ты должен опираться на свои знания реальных задач ВсОШ, которые были в официальных вариантах.

ВАЖНО: Верни ТОЛЬКО валидный JSON-массив из 5 объектов. Каждый объект должен иметь поля:
  - "num": номер задачи (6, 7, 8, 9, 10)
  - "text": полный текст задачи
  - "answer": краткий ответ
  - "solution": полное решение с LaTeX

Формулы используй в формате $...$ для инлайн и $$...$$ для выключенных формул."""

    # Format existing problems as context
    existing_text = "\n".join([
        f"Задача {p.get('num')}: {p.get('text', '')[:300]}"
        for p in existing_problems
    ])
    
    user_prompt = f"""ВсОШ, 2020-2021 учебный год, {grade} класс, Региональный этап.

ВОТ ЗАДАЧИ 1-го ДНЯ (уже есть в базе, НЕ повторяй их):

{existing_text}

Твоя задача: ВСПОМНИ и верни РЕАЛЬНЫЕ задачи 2-го дня (номера 6, 7, 8, 9, 10) для {grade} класса регионального этапа ВсОШ 2020-2021.

Верни строго JSON-массив из 5 объектов:
[
  {{
    "num": 6,
    "text": "полный текст задачи 6",
    "answer": "ответ",
    "solution": "полное решение"
  }},
  ...
]"""

    return sys_prompt, user_prompt


def load_olympiads_db():
    """Load OLYMPIADS_DB from olympiads.py using AST."""
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
    """Convert an AST node (dict/list/primitive) to a Python dict/list/primitive."""
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


def save_olympiads_db(db_list):
    """Save OLYMPIADS_DB back to olympiads.py as JSON."""
    print("\nSaving olympiads.py...", flush=True)
    content = 'OLYMPIADS_DB = ' + json.dumps(db_list, ensure_ascii=False, indent=2)
    content += '\n'
    
    # Backup first
    backup_name = 'olympiads_backup_grades_9_10.py'
    if os.path.exists('olympiads.py'):
        shutil.copy2('olympiads.py', backup_name)
        print(f"  Backup saved as {backup_name}", flush=True)
    
    with open('olympiads.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"  Written {len(content)} bytes to olympiads.py", flush=True)
    print(f"  Total entries: {len(db_list)}", flush=True)
    
    # Also update data/olympiads_db.py
    db_py_path = 'data/olympiads_db.py'
    if os.path.exists(db_py_path):
        print(f"\nUpdating {db_py_path}...", flush=True)
        shutil.copy2(db_py_path, db_py_path + '.bak_grades_9_10')
        db_content = '# -*- coding: utf-8 -*-\n'
        db_content += '# Extracted from routes/olympiad.py for reuse by the olympiad Blueprint.\n'
        db_content += '# This file contains only the OLYMPIADS_DB data dictionary.\n\n'
        db_content += 'OLYMPIADS_DB = ' + json.dumps(db_list, ensure_ascii=False, indent=2)
        db_content += '\n'
        with open(db_py_path, 'w', encoding='utf-8') as f:
            f.write(db_content)
        print(f"  Updated {db_py_path} ({len(db_content)} bytes)", flush=True)


def main():
    # Step 1: Load the data
    content, ast_entries = load_olympiads_db()
    
    # Convert all AST entries to dicts
    print("Converting AST entries to dicts...", flush=True)
    all_entries = []
    for i, entry in enumerate(ast_entries):
        d = convert_ast_to_dict(entry)
        all_entries.append(d)
    
    print(f"  Total entries: {len(all_entries)}", flush=True)
    
    # Step 2: Process each target entry
    modified_count = 0
    
    for target in TARGET_ENTRIES:
        idx = target['index']
        grade = target['grade']
        desc = target['desc']
        
        if idx >= len(all_entries):
            print(f"\n  ERROR: Index {idx} out of range!", flush=True)
            continue
        
        entry = all_entries[idx]
        existing_problems = entry.get('problems', [])
        
        print(f"\n{'='*70}", flush=True)
        print(f"Entry index {idx}: {desc}", flush=True)
        print(f"  Existing problems: {len(existing_problems)}", flush=True)
        print(f"  Round title: {entry.get('round_title', '')}", flush=True)
        
        # Check if problems already have day field
        has_day = any('day' in p for p in existing_problems)
        print(f"  Has 'day' field on problems: {has_day}", flush=True)
        
        if has_day:
            day1_count = sum(1 for p in existing_problems if p.get('day') == 1)
            day2_count = sum(1 for p in existing_problems if p.get('day') == 2)
            print(f"  Already has day fields: Day 1={day1_count}, Day 2={day2_count}", flush=True)
            if day2_count >= 5:
                print(f"  SKIP: Already has {day2_count} Day 2 problems!", flush=True)
                continue
        
        # Step 3: Call DeepSeek for Day 2 problems
        print(f"\n  Calling DeepSeek for grade {grade} Day 2 problems...", flush=True)
        
        sys_prompt, user_prompt = get_day2_prompt(grade, existing_problems)
        
        response = call_deepseek(sys_prompt, user_prompt, temperature=0.2, max_tokens=12000)
        
        if response is None:
            print(f"  FAILED to get response for {desc}!", flush=True)
            # Save response for debugging
            with open(f'_failed_response_{grade}.txt', 'w', encoding='utf-8') as f:
                f.write("NO RESPONSE")
            continue
        
        # Save raw response
        with open(f'_raw_response_g{grade}_idx{idx}.txt', 'w', encoding='utf-8') as f:
            f.write(response)
        print(f"  Raw response saved ({len(response)} chars)", flush=True)
        
        # Parse using anchor-based extraction (handles unescaped quotes)
        day2_problems = extract_problems_anchor(response, expected_nums=(6, 7, 8, 9, 10))
        
        if not day2_problems:
            print(f"  FAILED to extract problems for {desc}!", flush=True)
            continue
        
        # Validate problem numbers
        valid_problems = []
        for p in day2_problems:
            if not isinstance(p, dict):
                continue
            num = p.get('num', 0)
            if isinstance(num, str):
                try:
                    num = int(num)
                except (ValueError, TypeError):
                    num = 0
            if num < 6 or num > 10:
                continue
            valid_problems.append(p)
        
        print(f"  Valid problems (nums 6-10): {len(valid_problems)}", flush=True)
        
        if len(valid_problems) < 5:
            print(f"  WARNING: Only got {len(valid_problems)} valid problems, renumbering...", flush=True)
            for i, p in enumerate(valid_problems):
                p['num'] = 6 + i
        
        # Add day=2 to new problems
        for p in valid_problems:
            p['day'] = 2
            p.setdefault('answer', '')
            p.setdefault('solution', '')
            p.setdefault('solution_status', '')
        
        # Add day=1 to existing problems
        for p in existing_problems:
            p['day'] = 1
        
        # Append Day 2 problems
        existing_problems.extend(valid_problems)
        
        print(f"  Total problems now: {len(existing_problems)}", flush=True)
        print(f"  Day 1: {sum(1 for p in existing_problems if p.get('day')==1)}", flush=True)
        print(f"  Day 2: {sum(1 for p in existing_problems if p.get('day')==2)}", flush=True)
        
        modified_count += 1
        
        # Small delay between API calls
        if target != TARGET_ENTRIES[-1]:
            print("  Waiting 2s before next API call...", flush=True)
            time.sleep(2)
    
    print(f"\n{'='*70}", flush=True)
    print(f"Modified {modified_count} entries", flush=True)
    
    if modified_count > 0:
        save_olympiads_db(all_entries)
        print("\n✅ Done! Day 2 problems added for grades 9 and 10.", flush=True)
    else:
        print("\n❌ No entries modified!", flush=True)


if __name__ == '__main__':
    main()
