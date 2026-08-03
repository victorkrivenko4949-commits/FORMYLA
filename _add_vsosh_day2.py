#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Add Day 2 problems for vsosh 2020 regional (grades 9, 10, 11) to olympiads.py.

Uses DeepSeek API to find/recall the real Day 2 problems from internet training data.
The existing data only has 5 problems per entry (all Day 1). We need 5 more for Day 2.

Strategy:
1. Load olympiads.py via AST
2. Find vsosh 2020 regional entries
3. For each grade, call DeepSeek with the existing Day 1 problems as context
4. Ask DeepSeek to provide the 5 Day 2 problems (tasks 6-10)
5. Parse JSON response
6. Add day=1 to existing problems, day=2 to new problems
7. Write back to olympiads.py
"""

import ast
import json
import os
import sys
import time
import requests

os.chdir(r'C:\Users\Victor\Desktop\Новая папка (2)')

DEEPSEEK_KEY = os.environ.get('DEEPSEEK_API_KEY', '')
if not DEEPSEEK_KEY:
    print("ERROR: DEEPSEEK_API_KEY not set!")
    sys.exit(1)

# The vsosh 2020 regional entries we identified
# These are the AST indices (0-based position in OLYMPIADS_DB list)
TARGET_ENTRIES = [
    {'index': 1037, 'grade': 9, 'id': '', 'variants': 1},
    {'index': 1041, 'grade': 10, 'id': 516, 'variants': 1},
    {'index': 1042, 'grade': 10, 'id': 517, 'variants': 2},  # variant 2
    {'index': 1046, 'grade': 11, 'id': 519, 'variants': 1},
]

API_URL = "https://api.deepseek.com/v1/chat/completions"
MODEL = "deepseek-chat"


def call_deepseek(system_prompt, user_prompt, temperature=0.3, max_tokens=8000):
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
            r = requests.post(API_URL, json=payload, headers=headers, timeout=180)
            r.raise_for_status()
            data = r.json()
            content = data["choices"][0]["message"]["content"]
            return content
        except Exception as e:
            print(f"  Attempt {attempt+1} failed: {e}")
            if attempt < 2:
                time.sleep(5 * (2 ** attempt))
    
    return None


def extract_json_from_response(text):
    """Extract JSON object from DeepSeek response (handles markdown fences)."""
    # Try to find JSON between ```json and ``` markers
    if '```json' in text:
        text = text.split('```json', 1)[1]
        if '```' in text:
            text = text.split('```', 1)[0]
    elif '```' in text:
        text = text.split('```', 1)[1]
        if '```' in text:
            text = text.split('```', 1)[0]
    
    text = text.strip()
    
    # Try to parse as JSON
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # Try to find {...} or [...] in the text
    for start_char, end_char in [('{', '}'), ('[', ']')]:
        start = text.find(start_char)
        if start >= 0:
            end = text.rfind(end_char)
            if end > start:
                try:
                    return json.loads(text[start:end+1])
                except json.JSONDecodeError:
                    pass
    
    return None


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
    elif isinstance(ast_node, ast.Str):  # Python < 3.8
        return ast_node.s
    elif isinstance(ast_node, ast.Num):  # Python < 3.8
        return ast_node.n
    elif isinstance(ast_node, ast.NameConstant):  # Python < 3.8
        return ast_node.value
    elif isinstance(ast_node, ast.UnaryOp) and isinstance(ast_node.op, ast.USub):
        return -convert_ast_to_dict(ast_node.operand)
    else:
        return None


def save_olympiads_db(db_list):
    """Save OLYMPIADS_DB back to olympiads.py as JSON."""
    print("Saving olympiads.py...", flush=True)
    content = 'OLYMPIADS_DB = ' + json.dumps(db_list, ensure_ascii=False, indent=2)
    content += '\n'
    
    # Backup first
    import shutil
    if os.path.exists('olympiads.py'):
        shutil.copy2('olympiads.py', 'olympiads_backup_day2.py')
        print("  Backup saved as olympiads_backup_day2.py", flush=True)
    
    with open('olympiads.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"  Written {len(content)} bytes", flush=True)
    print(f"  Total entries: {len(db_list)}", flush=True)


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
        f"Задача {p.get('num')}: {p.get('text', '')[:200]}"
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


def get_test_prompt(grade):
    """Alternative: ask DeepSeek to just list the topics/descriptions of Day 2 problems."""
    sys_prompt = "Ты — эксперт по Всероссийской олимпиаде школьников. Перечисли РЕАЛЬНЫЕ задачи 2-го дня."
    
    user_prompt = f"""Какие были задачи 6, 7, 8, 9, 10 во 2-м дне регионального этапа ВсОШ 2020-2021 по математике для {grade} класса?

Перечисли каждую задачу с её полным условием. Верни строго JSON-массив."""

    return sys_prompt, user_prompt


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
    
    # Step 2: Find vsosh 2020 regional entries and add Day 2 problems
    modified_count = 0
    
    for target in TARGET_ENTRIES:
        idx = target['index']
        grade = target['grade']
        
        if idx >= len(all_entries):
            print(f"  ERROR: Index {idx} out of range!", flush=True)
            continue
        
        entry = all_entries[idx]
        existing_problems = entry.get('problems', [])
        
        print(f"\n{'='*60}", flush=True)
        print(f"Entry index {idx}: grade={grade}, id={entry.get('id','')}", flush=True)
        print(f"  Existing problems: {len(existing_problems)}", flush=True)
        print(f"  Round title: {entry.get('round_title', '')}", flush=True)
        
        # Check if problems already have day field
        has_day = any('day' in p for p in existing_problems)
        print(f"  Has 'day' field on problems: {has_day}", flush=True)
        
        # Step 3: Call DeepSeek for Day 2 problems
        print(f"\n  Calling DeepSeek for grade {grade} Day 2 problems...", flush=True)
        
        sys_prompt, user_prompt = get_day2_prompt(grade, existing_problems)
        
        response = call_deepseek(sys_prompt, user_prompt, temperature=0.2, max_tokens=10000)
        
        if response is None:
            print(f"  FAILED to get response for grade {grade}!", flush=True)
            continue
        
        print(f"  DeepSeek response length: {len(response)} chars", flush=True)
        print(f"  Response preview: {response[:300]}...", flush=True)
        
        # Parse JSON from response
        day2_problems = extract_json_from_response(response)
        
        if day2_problems is None:
            print(f"  FAILED to parse JSON for grade {grade}!", flush=True)
            print(f"  Raw response saved to _last_response_{grade}.txt", flush=True)
            with open(f'_last_response_{grade}.txt', 'w', encoding='utf-8') as f:
                f.write(response)
            continue
        
        if isinstance(day2_problems, dict):
            # Maybe wrapped in a container
            for key in ['problems', 'tasks', 'day2', 'data']:
                if key in day2_problems:
                    day2_problems = day2_problems[key]
                    break
        
        if not isinstance(day2_problems, list):
            print(f"  Unexpected response type: {type(day2_problems).__name__}", flush=True)
            print(f"  Content: {json.dumps(day2_problems, ensure_ascii=False)[:500]}", flush=True)
            continue
        
        print(f"  Got {len(day2_problems)} problems from DeepSeek", flush=True)
        
        # Validate and fix problem numbers
        valid_problems = []
        for p in day2_problems:
            if not isinstance(p, dict):
                continue
            num = p.get('num', 0)
            if num < 6 or num > 10:
                # Renumber starting from 6
                continue
            valid_problems.append(p)
        
        # If we got less than 5 problems, renumber what we have
        if len(valid_problems) < 5:
            print(f"  WARNING: Only got {len(valid_problems)} valid problems (nums 6-10)", flush=True)
            # Accept what we have, renumber
            for i, p in enumerate(valid_problems):
                p['num'] = 6 + i
        
        # Add day=2 to new problems
        for p in valid_problems:
            p['day'] = 2
            # Ensure all required fields
            p.setdefault('answer', '')
            p.setdefault('solution', '')
            p.setdefault('solution_status', '')
            p.setdefault('text', '')
        
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
        time.sleep(1)
    
    print(f"\n{'='*60}", flush=True)
    print(f"Modified {modified_count} entries", flush=True)
    
    if modified_count > 0:
        # Step 4: Save back to olympiads.py
        save_olympiads_db(all_entries)
        
        # Also update data/olympiads_db.py if it exists
        db_py_path = 'data/olympiads_db.py'
        if os.path.exists(db_py_path):
            print(f"\nUpdating {db_py_path}...", flush=True)
            db_content = '# -*- coding: utf-8 -*-\n'
            db_content += '# Extracted from routes/olympiad.py for reuse by the olympiad Blueprint.\n'
            db_content += '# This file contains only the OLYMPIADS_DB data dictionary.\n\n'
            db_content += 'OLYMPIADS_DB = ' + json.dumps(all_entries, ensure_ascii=False, indent=2)
            db_content += '\n'
            
            import shutil
            shutil.copy2(db_py_path, db_py_path + '.bak')
            with open(db_py_path, 'w', encoding='utf-8') as f:
                f.write(db_content)
            print(f"  Updated {db_py_path} ({len(db_content)} bytes)", flush=True)
        
        print("\n[OK] Done! Day 2 problems added.", flush=True)
        print("\nNext steps:", flush=True)
        print("  1. Verify the data: python _verify_vsosh_days.py", flush=True)
        print("  2. Restart the app to see changes", flush=True)
    else:
        print("\n[ERROR] No entries modified!", flush=True)


if __name__ == '__main__':
    main()
