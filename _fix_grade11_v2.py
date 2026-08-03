#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Re-call DeepSeek for grade 11 vsosh 2020 regional Day 2 problems.
The previous call was truncated at max_tokens=10000.
Now use max_tokens=16000 to get all 5 problems.
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
            r = requests.post(API_URL, json=payload, headers=headers, timeout=300)
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


def extract_json(text):
    """Extract JSON array from DeepSeek response."""
    # Handle markdown fences
    if '```json' in text:
        text = text.split('```json', 1)[1]
        if '```' in text:
            text = text.split('```', 1)[0]
    elif '```' in text:
        text = text.split('```', 1)[1]
        if '```' in text:
            text = text.split('```', 1)[0]
    
    text = text.strip()
    
    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # Try find [...] bounds
    start = text.find('[')
    if start >= 0:
        # Count brackets to find matching close
        depth = 0
        for i in range(start, len(text)):
            if text[i] == '[':
                depth += 1
            elif text[i] == ']':
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i+1])
                    except json.JSONDecodeError:
                        pass
    
    return None


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
    
    import shutil
    if os.path.exists('olympiads.py'):
        shutil.copy2('olympiads.py', 'olympiads_backup_grade11.py')
        print("  Backup: olympiads_backup_grade11.py", flush=True)
    
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
    
    # Format existing problems as context
    existing_text = "\n".join([
        f"Задача {p.get('num')}: {p.get('text', '')[:300]}"
        for p in existing_problems
    ])
    
    # Create prompt for Day 2 problems
    sys_prompt = """Ты — эксперт по Всероссийской олимпиаде школьников (ВсОШ) по математике. 
Твоя задача — вспомнить РЕАЛЬНЫЕ задачи 2-го дня регионального этапа ВсОШ 2020-2021 учебного года для 11 класса.

Ты должен опираться на свои знания реальных задач ВсОШ.

ВАЖНО: Верни ТОЛЬКО валидный JSON-массив из 5 объектов. Каждый объект должен иметь поля:
  - "num": номер задачи (6, 7, 8, 9, 10)
  - "text": полный текст задачи на русском языке
  - "answer": краткий ответ
  - "solution": полное решение с LaTeX

Формулы используй в формате $...$ для инлайн и $$...$$ для выключенных формул."""

    user_prompt = f"""ВсОШ, 2020-2021 учебный год, 11 класс, Региональный этап.

ВОТ ЗАДАЧИ 1-го ДНЯ (уже есть в базе, НЕ повторяй их):

{existing_text}

Твоя задача: ВСПОМНИ и верни РЕАЛЬНЫЕ задачи 2-го дня (номера 6, 7, 8, 9, 10) для 11 класса регионального этапа ВсОШ 2020-2021.

Очень важно: дай ПОЛНЫЙ текст каждой задачи и ПОЛНОЕ решение с обоснованием.
Не сокращай условия задач.

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

    # Call DeepSeek
    print(f"\n  Calling DeepSeek for grade 11 Day 2 problems (max_tokens=16000)...", flush=True)
    response = call_deepseek(sys_prompt, user_prompt, temperature=0.2, max_tokens=16000)
    
    if response is None:
        print("  FAILED to get response from DeepSeek!")
        sys.exit(1)
    
    # Save raw response
    with open('_last_response_11_v2.txt', 'w', encoding='utf-8') as f:
        f.write(response)
    print(f"  Raw response saved to _last_response_11_v2.txt ({len(response)} chars)", flush=True)
    
    # Preview
    print(f"  Preview: {response[:300]}...", flush=True)
    
    # Parse JSON
    print("  Parsing JSON...", flush=True)
    day2_problems = extract_json(response)
    
    if day2_problems is None:
        print("  FAILED to parse JSON from response!")
        print("  Trying alternative extraction methods...", flush=True)
        
        # Try more lenient extraction
        if '[' in response:
            start = response.find('[')
            # Try with bracket counting
            depth = 0
            best_end = -1
            for i in range(start, len(response)):
                if response[i] == '[':
                    depth += 1
                elif response[i] == ']':
                    depth -= 1
                    if depth == 0:
                        best_end = i
                        break
            
            if best_end > start:
                snippet = response[start:best_end+1]
                print(f"  Extracted JSON snippet length: {len(snippet)} chars", flush=True)
                try:
                    day2_problems = json.loads(snippet)
                    print("  JSON parsed successfully with bracket counting!", flush=True)
                except json.JSONDecodeError as e:
                    print(f"  Still failed: {e}", flush=True)
                    # Try to salvage partial data - find complete objects
                    print("  Trying to salvage partial data...", flush=True)
                    # Find all complete {...} objects
                    objects = []
                    i = snippet.find('{')
                    while i >= 0:
                        obj_depth = 0
                        for j in range(i, len(snippet)):
                            if snippet[j] == '{':
                                obj_depth += 1
                            elif snippet[j] == '}':
                                obj_depth -= 1
                                if obj_depth == 0:
                                    try:
                                        obj = json.loads(snippet[i:j+1])
                                        objects.append(obj)
                                        print(f"    Found complete object at {i}-{j+1}", flush=True)
                                    except json.JSONDecodeError:
                                        pass
                                    i = j + 1
                                    break
                        else:
                            break
                        i = snippet.find('{', i)
                    
                    if objects:
                        print(f"  Found {len(objects)} complete objects via salvage!", flush=True)
                        day2_problems = objects
    
    if day2_problems is None:
        print("  All extraction methods failed!")
        sys.exit(1)
    
    if isinstance(day2_problems, dict):
        for key in ['problems', 'tasks', 'day2', 'data']:
            if key in day2_problems:
                day2_problems = day2_problems[key]
                break
    
    if not isinstance(day2_problems, list):
        print(f"  Unexpected type: {type(day2_problems).__name__}")
        sys.exit(1)
    
    print(f"  Got {len(day2_problems)} problems", flush=True)
    
    # Validate
    valid = []
    for p in day2_problems:
        if not isinstance(p, dict):
            continue
        # Try to get num from various fields
        num = p.get('num', 0) or p.get('number', 0) or p.get('id', 0) or p.get('task', 0)
        if isinstance(num, str) and num.isdigit():
            num = int(num)
        if not isinstance(num, int):
            num = 0
        if num < 6 or num > 10:
            continue
        valid.append(p)
    
    # If not enough valid, renumber what we have
    if len(valid) < 5:
        print(f"  WARNING: Only {len(valid)} valid problems with nums 6-10", flush=True)
        # Accept all as valid and renumber
        valid = []
        for p in day2_problems:
            if isinstance(p, dict) and p.get('text'):
                valid.append(p)
        for i, p in enumerate(valid):
            p['num'] = 6 + i
    
    if len(valid) < 3:
        print(f"  ERROR: Too few problems ({len(valid)}), cannot proceed")
        sys.exit(1)
    
    print(f"  Using {len(valid)} problems", flush=True)
    for p in valid:
        print(f"    Problem {p.get('num')}: text={p.get('text','')[:80]}...", flush=True)
    
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
    
    # Append Day 2
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
        
        import shutil
        shutil.copy2(db_py_path, db_py_path + '.bak')
        with open(db_py_path, 'w', encoding='utf-8') as f:
            f.write(db_content)
        print(f"  Updated {db_py_path} ({len(db_content)} bytes)", flush=True)
    
    print("\n[OK] Grade 11 Day 2 problems added successfully!")


if __name__ == '__main__':
    main()
