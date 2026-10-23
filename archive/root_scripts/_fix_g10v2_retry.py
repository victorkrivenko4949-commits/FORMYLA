#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Retry: Get REAL problems 9 and 10 for grade 10 var 2 (idx 1042) of vsosh 2020 regional.

Key insight from previous failure:
  The previous script showed DeepSeek the FULL text of existing Day 2 problems (6, 7, 8)
  with "NE POVTORJAY" instruction. DeepSeek still returned semantically identical problems.

NEW STRATEGY:
  1. Restore clean backup (8 problems: 5 Day 1 + 3 Day 2) from olympiads_backup_g10v2_fix.py
  2. Call DeepSeek with ONLY Day 1 problems (1-5) as context - NO Day 2 text at all
  3. List FORBIDDEN topics without revealing the full problem text
  4. Ask for real problems 9 and 10
  5. Verify they are NOT duplicates before appending
  6. Save to both olympiads.py and data/olympiads_db.py
"""
import ast
import json
import os
import sys
import time
import re
import requests
import shutil

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

OUTPUT_FILE = "_raw_response_g10v2_retry.txt"
TARGET_INDEX = 1042  # idx 1042 = id 517 = grade 10 var 2

# Day 1 problems (1-5) for context - these are the REAL problems
DAY1_PROBLEMS = [
    {
        "num": 1,
        "text": "На доске написано выражение $\cos x$. Разрешается вместо любого выражения $E$ (или вместо его части, являющейся выражением) написать выражение $E'$, полученное из $E$ применением какой-нибудь формулы тригонометрии (формулы можно использовать только в одну сторону, например, из $\sin 2x$ нельзя получить $2\\sin x\\cos x$, а наоборот — можно). Какое наименьшее количество шагов потребуется, чтобы получить из $\cos x$ выражение $\cos x\\cos 2x\\cos 4x\\ldots\\cos 512x$?",
    },
    {
        "num": 2,
        "text": "На сторонах выпуклого четырёхугольника $ABCD$ во внешнюю сторону построены равносторонние треугольники $ABM$, $BCN$, $CPD$ и $DAQ$. Оказалось, что отрезки $MN$ и $PQ$ равны и перпендикулярны. Докажите, что $ABCD$ — квадрат.",
    },
    {
        "num": 3,
        "text": "На доске пишут $n$ квадратных трёхчленов так, чтобы любые два имели общий корень. При каком наибольшем $n$ это возможно, если все трёхчлены различны, имеют старший коэффициент 1 и вещественные корни?",
    },
    {
        "num": 4,
        "text": "Назовём многоугольник хорошим, если его можно разрезать на две равные части (совпадающие при наложении) по прямой, не проходящей через вершины. Какое наибольшее количество сторон может иметь хороший многоугольник?",
    },
    {
        "num": 5,
        "text": "Петя задумал два многочлена $f(x)$ и $g(x)$ с целыми неотрицательными коэффициентами. Вася может за один вопрос назвать пару чисел $(a,b)$ и узнать значение $af(b)+bg(a)$. За какое наименьшее количество вопросов Вася сможет гарантированно определить оба многочлена?",
    },
]


def call_deepseek(system_prompt, user_prompt, temperature=0.3, max_tokens=12000):
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


def extract_problems_anchor(text, expected_nums=(9, 10)):
    """Extract problems by anchoring on 'num': N patterns."""
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
        pattern = rf'"num"\s*:\s*{num}(?:\s*[,}}\s]|\s*\n)'
        m = re.search(pattern, text)
        if not m:
            print(f"  WARNING: 'num': {num} not found!", flush=True)
            continue
        
        match_end = m.end()
        
        # Walk backward to find opening '{'
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
        
        # Now extract all fields
        obj = {}
        pos = obj_start
        
        val, pos = extract_field_value(text, 'num', pos)
        if val is not None:
            obj['num'] = val
        
        val, pos = extract_field_value(text, 'text', pos)
        if val is not None:
            obj['text'] = val
        
        val, pos = extract_field_value(text, 'answer', pos)
        if val is not None:
            obj['answer'] = val
        
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
    """Convert an AST node to a Python dict/list/primitive."""
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


def load_backup_entry(backup_file, target_id=517):
    """Load a specific entry from backup file by id."""
    print(f"Loading backup from {backup_file}...", flush=True)
    with open(backup_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    tree = ast.parse(content)
    
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == 'OLYMPIADS_DB' for t in node.targets
        ):
            entries = node.value.elts
            for i, entry in enumerate(entries):
                d = convert_ast_to_dict(entry)
                if d.get('id') == target_id:
                    print(f"  Found backup entry at position {i} with id={target_id}", flush=True)
                    return d
    
    print(f"ERROR: Could not find entry with id={target_id} in backup!", flush=True)
    return None


def save_olympiads_db(db_list):
    """Save OLYMPIADS_DB back to olympiads.py as JSON."""
    print("\nSaving olympiads.py...", flush=True)
    content = 'OLYMPIADS_DB = ' + json.dumps(db_list, ensure_ascii=False, indent=2)
    content += '\n'
    
    # Backup first
    backup_name = 'olympiads_backup_before_retry.py'
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
        shutil.copy2(db_py_path, db_py_path + '.bak_before_retry')
        db_content = '# -*- coding: utf-8 -*-\n'
        db_content += '# Extracted from routes/olympiad.py for reuse by the olympiad Blueprint.\n'
        db_content += '# This file contains only the OLYMPIADS_DB data dictionary.\n\n'
        db_content += 'OLYMPIADS_DB = ' + json.dumps(db_list, ensure_ascii=False, indent=2)
        db_content += '\n'
        with open(db_py_path, 'w', encoding='utf-8') as f:
            f.write(db_content)
        print(f"  Updated {db_py_path} ({len(db_content)} bytes)", flush=True)


def is_duplicate(new_problem, existing_problems):
    """Check if new_problem is semantically a duplicate of any existing problem."""
    new_text = (new_problem.get('text', '') or '').strip()
    new_text_clean = re.sub(r'\\+', '\\\\', new_text)  # normalize LaTeX escaping
    new_text_clean = re.sub(r'\s+', ' ', new_text_clean)
    
    for ep in existing_problems:
        ep_text = (ep.get('text', '') or '').strip()
        ep_text_clean = re.sub(r'\\+', '\\\\', ep_text)
        ep_text_clean = re.sub(r'\s+', ' ', ep_text_clean)
        
        # Check if texts are very similar
        if len(new_text_clean) > 0 and len(ep_text_clean) > 0:
            # Simple overlap check
            overlap = len(set(new_text_clean.split()) & set(ep_text_clean.split()))
            min_len = min(len(new_text_clean.split()), len(ep_text_clean.split()))
            if min_len > 0 and overlap / min_len > 0.6:
                print(f"  DUPLICATE DETECTED with problem {ep.get('num')}!", flush=True)
                print(f"    New: {new_text_clean[:80]}...", flush=True)
                print(f"    Existing: {ep_text_clean[:80]}...", flush=True)
                return True
    
    return False


def get_prompt():
    """Create prompt asking DeepSeek for REAL problems 9 and 10.
    CRITICAL: Do NOT reveal existing Day 2 problems to avoid contamination."""
    sys_prompt = """Ты — эксперт по Всероссийской олимпиаде школьников (ВсОШ) по математике. 
Твоя задача — вспомнить РЕАЛЬНЫЕ задачи 2-го дня регионального этапа ВсОШ 2020-2021 учебного года для 10 класса.

ВАЖНО: Ты должен опираться ТОЛЬКО на свои знания реальных задач ВсОШ из официальных вариантов.
НЕ придумывай задачи — вспомни реальные.

Верни ТОЛЬКО валидный JSON-массив из 2 объектов для задач 9 и 10:
[
  {
    "num": 9,
    "text": "полный текст задачи",
    "answer": "краткий ответ",
    "solution": "полное решение с LaTeX"
  },
  {
    "num": 10,
    "text": "полный текст задачи",
    "answer": "краткий ответ",
    "solution": "полное решение с LaTeX"
  }
]

Формулы используй в формате $...$ для инлайн и $$...$$ для выключенных формул."""

    # Format Day 1 problems as context (only problems 1-5, NOT day 2)
    day1_text = "\n".join([
        f"Задача {p['num']}: {p['text']}"
        for p in DAY1_PROBLEMS
    ])
    
    user_prompt = f"""ВсОШ, 2020-2021 учебный год, 10 класс, Региональный этап, ВАРИАНТ 2.

ВОТ ЗАДАЧИ 1-го ДНЯ (уже есть в базе, НЕ повторяй их):

{day1_text}

Во 2-м дне этого варианта уже есть задачи 6, 7, 8 на следующие темы:
- Задача 6: факториальные уравнения (a! + b! = c!)
- Задача 7: геометрия с биссектрисой и медианой (треугольник ABC, AD — биссектриса, M — середина BC)
- Задача 8: теория чисел (делимость m^2 + n^2 + m + n на mn)

Твоя задача: ВСПОМНИ и верни РЕАЛЬНЫЕ задачи 9 и 10 для этого же варианта 10 класса.
ЭТО ДОЛЖНЫ БЫТЬ ДРУГИЕ ЗАДАЧИ, НЕ НА ТЕ ЖЕ ТЕМЫ!

ЗАПРЕЩЕНО давать задачи на темы:
1. Факториальные уравнения (a! + b! = c!)
2. Геометрия с биссектрисой и медианой
3. Делимость m² + n² + m + n на mn
4. Любые другие задачи, повторяющие уже данные выше

Верни строго JSON-массив из 2 объектов (номера 9 и 10)."""

    return sys_prompt, user_prompt


def main():
    # Step 1: Load current olympiads DB
    content, ast_entries = load_olympiads_db()
    
    print("Converting AST entries to dicts...", flush=True)
    all_entries = []
    for i, entry in enumerate(ast_entries):
        d = convert_ast_to_dict(entry)
        all_entries.append(d)
    
    print(f"  Total entries: {len(all_entries)}", flush=True)
    
    # Step 2: Verify entry at TARGET_INDEX
    if TARGET_INDEX >= len(all_entries):
        print(f"ERROR: Index {TARGET_INDEX} out of range!", flush=True)
        sys.exit(1)
    
    entry = all_entries[TARGET_INDEX]
    print(f"\n{'='*70}", flush=True)
    print(f"Entry index {TARGET_INDEX}: id={entry.get('id')}, grade={entry.get('grade')}", flush=True)
    print(f"  Current problems: {len(entry.get('problems', []))}", flush=True)
    
    if entry.get('id') != 517:
        print(f"WARNING: Expected id=517 but got id={entry.get('id')}!", flush=True)
        print("Continuing anyway...", flush=True)
    
    existing_problems = entry.get('problems', [])
    
    # Check current state
    has_day = any('day' in p for p in existing_problems)
    print(f"  Has 'day' field: {has_day}", flush=True)
    
    day1_count = sum(1 for p in existing_problems if p.get('day') == 1)
    day2_count = sum(1 for p in existing_problems if p.get('day') == 2)
    print(f"  Day 1: {day1_count}, Day 2: {day2_count}", flush=True)
    
    # Step 3: Restore clean 8-problem state from backup
    print(f"\n  Restoring clean 8-problem state from backup...", flush=True)
    backup_entry = load_backup_entry('olympiads_backup_g10v2_fix.py', target_id=517)
    
    if backup_entry is None:
        print("ERROR: Could not restore from backup!", flush=True)
        sys.exit(1)
    
    backup_problems = backup_entry.get('problems', [])
    print(f"  Backup has {len(backup_problems)} problems", flush=True)
    for bp in backup_problems:
        print(f"    Problem {bp.get('num')}: day={bp.get('day')}, text={str(bp.get('text',''))[:60]}", flush=True)
    
    # Replace the entry's problems with backup's problems
    all_entries[TARGET_INDEX]['problems'] = backup_problems
    
    # Step 4: Call DeepSeek for problems 9 and 10
    print(f"\n  Calling DeepSeek for problems 9 and 10...", flush=True)
    
    sys_prompt, user_prompt = get_prompt()
    
    response = call_deepseek(sys_prompt, user_prompt, temperature=0.3, max_tokens=12000)
    
    if response is None:
        print(f"  FAILED to get response from DeepSeek!", flush=True)
        # Save current state (with restored backup) before exiting
        print("Saving current state (with restored backup but no new problems)...", flush=True)
        save_olympiads_db(all_entries)
        sys.exit(1)
    
    # Save raw response
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(response)
    print(f"  Raw response saved to {OUTPUT_FILE} ({len(response)} chars)", flush=True)
    
    # Parse using anchor-based extraction
    new_problems = extract_problems_anchor(response, expected_nums=(9, 10))
    
    if not new_problems:
        print(f"  FAILED to extract any problems from response!", flush=True)
        print("Saving current state (with restored backup only)...", flush=True)
        save_olympiads_db(all_entries)
        sys.exit(1)
    
    # Step 5: Validate problem numbers
    valid_problems = []
    for p in new_problems:
        if not isinstance(p, dict):
            continue
        num = p.get('num', 0)
        if isinstance(num, str):
            try:
                num = int(num)
            except (ValueError, TypeError):
                num = 0
        if num not in (9, 10):
            # Renumber
            num = 9 if len(valid_problems) == 0 else 10
        p['num'] = num
        valid_problems.append(p)
    
    print(f"\n  Extracted {len(valid_problems)} problems from response", flush=True)
    
    # Step 6: Verify they are NOT duplicates of problems 6, 7, 8
    day2_existing = [p for p in backup_problems if p.get('day') == 2]
    
    print(f"\n  Checking for duplicates against {len(day2_existing)} existing Day 2 problems...", flush=True)
    final_problems_to_add = []
    for np in valid_problems:
        if is_duplicate(np, day2_existing):
            print(f"  Problem {np.get('num')} is a DUPLICATE - skipping!", flush=True)
        else:
            print(f"  Problem {np.get('num')} is UNIQUE - adding!", flush=True)
            final_problems_to_add.append(np)
    
    if not final_problems_to_add:
        print(f"\n  ERROR: All problems were duplicates! Need at least 2 unique problems.", flush=True)
        print("Trying again with lower temperature...", flush=True)
        
        # Retry once with lower temperature
        response2 = call_deepseek(sys_prompt, user_prompt, temperature=0.1, max_tokens=12000)
        if response2:
            with open(OUTPUT_FILE.replace('.txt', '_retry2.txt'), 'w', encoding='utf-8') as f:
                f.write(response2)
            new_problems2 = extract_problems_anchor(response2, expected_nums=(9, 10))
            for np in new_problems2:
                if isinstance(np, dict) and not is_duplicate(np, day2_existing):
                    num = np.get('num', 9 if len(final_problems_to_add) == 0 else 10)
                    np['num'] = 9 if len(final_problems_to_add) == 0 else 10
                    final_problems_to_add.append(np)
        
        if not final_problems_to_add:
            print("  Still couldn't get non-duplicate problems. Saving backup state only.", flush=True)
            save_olympiads_db(all_entries)
            sys.exit(1)
    
    # Need exactly 9 and 10
    # Renumber
    for i, p in enumerate(final_problems_to_add):
        p['num'] = 9 + i
    
    # Add day=2 and default fields
    for p in final_problems_to_add:
        p['day'] = 2
        p.setdefault('answer', '')
        p.setdefault('solution', '')
        p.setdefault('solution_status', '')
    
    print(f"\n  Problems to add:", flush=True)
    for p in final_problems_to_add:
        print(f"    Problem {p['num']}: {str(p.get('text',''))[:80]}", flush=True)
    
    # Step 7: Append to existing problems
    current_problems = all_entries[TARGET_INDEX].get('problems', [])
    
    # Ensure day fields on all problems
    for p in current_problems:
        if 'day' not in p:
            p['day'] = 1 if p.get('num', 0) <= 5 else 2
    
    current_problems.extend(final_problems_to_add)
    
    print(f"\n  Total problems now: {len(current_problems)}", flush=True)
    print(f"  Day 1: {sum(1 for p in current_problems if p.get('day')==1)}", flush=True)
    print(f"  Day 2: {sum(1 for p in current_problems if p.get('day')==2)}", flush=True)
    
    # Step 8: Save
    save_olympiads_db(all_entries)
    
    print(f"\n{'='*70}", flush=True)
    print("Done! Grade 10 var 2 (idx 1042) now has clean problems:", flush=True)
    for p in all_entries[TARGET_INDEX].get('problems', []):
        print(f"  Prob {p.get('num')} (day {p.get('day')}): {str(p.get('text',''))[:80]}", flush=True)


if __name__ == '__main__':
    main()
