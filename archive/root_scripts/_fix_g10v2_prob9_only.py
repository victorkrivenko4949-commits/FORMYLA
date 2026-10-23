#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Targeted fix: Get problem 9 ONLY for grade 10 var 2 (idx 1042).

Current state: 9 problems (1-8 + misnumbered 9 which is actually 10). Need problem 9.
The script inserts problem 9 between 8 and 10 without disturbing existing data.

STRATEGY:
1. Load current olympiads.py state (9 problems, problem 9 is misnumbered x²+y²+x+y)
2. First, renumber the mislabeled problem 9 -> 10
3. Call DeepSeek asking for ONLY problem 9
4. Explicitly list existing topics (including problem 10's topic) to avoid repeats
5. Explicitly list FORBIDDEN problem types
6. Suggest ALLOWED problem types
7. After getting problem 9, validate it's not a duplicate
8. Insert into the correct position (after problem 8, before problem 10)
9. Save to both olympiads.py and data/olympiads_db.py
"""
import ast
import json
import os
import sys
import time
import re
import requests
import shutil

sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None
os.environ['PYTHONIOENCODING'] = 'utf-8'

os.chdir(r'C:\Users\Victor\Desktop\Новая папка (2)')

DEEPSEEK_KEY = os.environ.get('DEEPSEEK_API_KEY', '')
if not DEEPSEEK_KEY:
    print("ERROR: DEEPSEEK_API_KEY not set!")
    sys.exit(1)

API_URL = "https://api.deepseek.com/v1/chat/completions"
MODEL = "deepseek-chat"
OUTPUT_FILE = "_raw_response_g10v2_prob9.txt"
TARGET_INDEX = 1042

# Existing Day 2 problems that we CANNOT duplicate
EXISTING_DAY2_TOPICS = """
Задача 6 (уже есть): факториальное уравнение a! + b! = c! — найти все тройки натуральных чисел
Задача 7 (уже есть): геометрия — треугольник ABC, AD — биссектриса, M — середина BC, угол BAD = CAD = MAD. Найти углы треугольника.
Задача 8 (уже есть): теория чисел — делимость (m² + n² + m + n) на (mn). Доказать, что m=n.
Задача 10 (уже есть): теория чисел — делимость (x² + y² + x + y) на (xy). Найти все пары натуральных чисел.
"""


def call_deepseek(system_prompt, user_prompt, temperature=0.2, max_tokens=8000):
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
    """Extract value of JSON key starting from start_pos."""
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


def extract_problem_anchor(text, expected_num=9):
    """Extract a single problem by anchoring on 'num': N pattern."""
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
    
    # Try direct json.loads
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
    except json.JSONDecodeError:
        pass
    
    # Also try to find if it's a single object
    try:
        # Wrap in array if it's a single object
        if text.strip().startswith('{') and text.strip().endswith('}'):
            data = json.loads(f'[{text}]')
            return data
    except json.JSONDecodeError:
        pass
    
    # Anchor-based extraction
    print(f"  Using anchor-based extraction for num={expected_num}...", flush=True)
    pattern = rf'"num"\s*:\s*{expected_num}(?:\s*[,}}\s]|\s*\n)'
    m = re.search(pattern, text)
    if not m:
        print(f"  WARNING: 'num': {expected_num} not found!", flush=True)
        return []
    
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
        print(f"  WARNING: Could not find opening '{{'!", flush=True)
        return []
    
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
    
    if obj:
        txt_preview = (str(obj.get('text', '')) or '')[:80]
        print(f"  Extracted problem {obj.get('num', '?')}: {txt_preview}", flush=True)
        return [obj]
    return []


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


def save_olympiads_db(db_list):
    """Save OLYMPIADS_DB back to olympiads.py as JSON."""
    print("\nSaving olympiads.py...", flush=True)
    content = 'OLYMPIADS_DB = ' + json.dumps(db_list, ensure_ascii=False, indent=2)
    content += '\n'
    backup_name = 'olympiads_backup_before_prob9.py'
    if os.path.exists('olympiads.py'):
        shutil.copy2('olympiads.py', backup_name)
        print(f"  Backup saved as {backup_name}", flush=True)
    with open('olympiads.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"  Written {len(content)} bytes to olympiads.py", flush=True)
    print(f"  Total entries: {len(db_list)}", flush=True)
    db_py_path = 'data/olympiads_db.py'
    if os.path.exists(db_py_path):
        print(f"\nUpdating {db_py_path}...", flush=True)
        shutil.copy2(db_py_path, db_py_path + '.bak_before_prob9')
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
    new_text_clean = re.sub(r'\\+', '\\\\', new_text)
    new_text_clean = re.sub(r'\s+', ' ', new_text_clean)
    for ep in existing_problems:
        ep_text = (ep.get('text', '') or '').strip()
        ep_text_clean = re.sub(r'\\+', '\\\\', ep_text)
        ep_text_clean = re.sub(r'\s+', ' ', ep_text_clean)
        if len(new_text_clean) > 0 and len(ep_text_clean) > 0:
            overlap = len(set(new_text_clean.split()) & set(ep_text_clean.split()))
            min_len = min(len(new_text_clean.split()), len(ep_text_clean.split()))
            if min_len > 0 and overlap / min_len > 0.55:
                print(f"  DUPLICATE DETECTED with problem {ep.get('num')}!", flush=True)
                print(f"    New: {new_text_clean[:80]}...", flush=True)
                print(f"    Existing: {ep_text_clean[:80]}...", flush=True)
                return True
    return False


def get_prompt():
    """Create prompt asking DeepSeek for problem 9 ONLY."""
    sys_prompt = """Ты — эксперт по Всероссийской олимпиаде школьников (ВсОШ) по математике.
Твоя задача — вспомнить РЕАЛЬНУЮ задачу из регионального этапа ВсОШ для 10 класса.

Верни ТОЛЬКО валидный JSON-объект для задачи 9:
{
  "num": 9,
  "text": "полный текст задачи на русском языке",
  "answer": "краткий ответ",
  "solution": "полное решение с LaTeX"
}

Формулы используй в формате $...$ для инлайн и $$...$$ для выключенных."""
    
    user_prompt = f"""ВсОШ, 2020-2021 учебный год, 10 класс, Региональный этап, ВАРИАНТ 2.

Во 2-м дне этого варианта УЖЕ ЕСТЬ задачи 6, 7, 8 и 10 на следующие темы (НЕ ПОВТОРЯЙ ИХ):
{EXISTING_DAY2_TOPICS}

Твоя задача — вспомнить и вернуть РЕАЛЬНУЮ задачу 9 для этого же варианта.

ЗАПРЕЩЕННЫЕ ТЕМЫ (НЕЛЬЗЯ давать задачи на эти темы):
1. Факториальные уравнения (a! + b! = c!, a! + b! + c! = что-то, деление факториалов)
2. Геометрия с биссектрисой (AD — биссектриса, любые вариации)
3. Делимость (m² + n² + m + n) на (mn)
4. Делимость (x² + y² + x + y) на (xy)
5. Любые другие задачи на делимость m² + n² + m + n или x² + y² + x + y

РАЗРЕШЕННЫЕ ТЕМЫ (выбери ОДНУ из них):
1. Неравенства (докажите неравенство, найдите наибольшее/наименьшее значение)
2. Комбинаторика (раскраски, подсчет количества способов, алгоритмы)
3. Функциональные уравнения
4. Теория чисел (НОД, НОК, простые числа, делимость — НО НЕ факториалы и не m²+n²+m+n)
5. Геометрия (площади, окружности, подобие — НО НЕ биссектриса AD)
6. Последовательности и прогрессии
7. Многочлены и уравнения

Верни строго JSON-объект для задачи с номером 9. Это должна быть РЕАЛЬНАЯ задача из ВсОШ, а не выдуманная."""
    
    return sys_prompt, user_prompt


def main():
    # Step 1: Load current DB
    content, ast_entries = load_olympiads_db()
    print("Converting AST entries to dicts...", flush=True)
    all_entries = []
    for i, entry in enumerate(ast_entries):
        d = convert_ast_to_dict(entry)
        all_entries.append(d)
    print(f"  Total entries: {len(all_entries)}", flush=True)
    
    if TARGET_INDEX >= len(all_entries):
        print(f"ERROR: Index {TARGET_INDEX} out of range!", flush=True)
        sys.exit(1)
    
    entry = all_entries[TARGET_INDEX]
    print(f"\n{'='*70}", flush=True)
    print(f"Entry index {TARGET_INDEX}: id={entry.get('id')}, grade={entry.get('grade')}", flush=True)
    
    current_problems = entry.get('problems', [])
    print(f"  Current problems: {len(current_problems)}")
    for p in current_problems:
        print(f"    Problem {p.get('num')} (day {p.get('day')}): {str(p.get('text',''))[:60]}")
    
    # === FIX MISNUMBERING: Check if problem 9 exists but is the misnumbered x²+y²+x+y problem ===
    nums = [p.get('num') for p in current_problems]
    renumbered = False
    if 9 in nums:
        prob9 = None
        for p in current_problems:
            if p.get('num') == 9:
                prob9 = p
                break
        prob9_text = (prob9.get('text', '') or '') if prob9 else ''
        # Check if problem 9 is actually the x²+y²+x+y problem (should be problem 10)
        clean_text = prob9_text.replace('\\', '').replace(' ', '').lower()
        if 'x^2' in clean_text or 'x²' in clean_text or 'x+y' in clean_text:
            print(f"\n  *** Problem 9 found but it's the MISNUMBERED x²+y²+x+y problem ***")
            print(f"  Renumbering problem 9 -> 10, then proceeding to generate real problem 9.")
            prob9['num'] = 10
            renumbered = True
        else:
            print(f"  Problem 9 already exists! Stopping.")
            sys.exit(0)
    
    # Verify state after possible renumbering
    nums_after = [p.get('num') for p in current_problems]
    if 9 in nums_after:
        print(f"  ERROR: Problem 9 still exists after attempted renumbering!")
        sys.exit(1)
    print(f"  Confirmed: problem 9 is missing, need to add it.")
    print(f"  Current problem numbers: {sorted(nums_after)}")
    if renumbered:
        print(f"  Problem 10 now contains: {str(prob9_text)[:80]}...")
    
    # Step 2: Call DeepSeek for problem 9 only
    print(f"\n  Calling DeepSeek for problem 9...", flush=True)
    sys_prompt, user_prompt = get_prompt()
    
    # First attempt
    response = call_deepseek(sys_prompt, user_prompt, temperature=0.15, max_tokens=8000)
    
    if response is None:
        print(f"  FAILED to get response from DeepSeek!", flush=True)
        sys.exit(1)
    
    # Save raw response
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(response)
    print(f"  Raw response saved to {OUTPUT_FILE} ({len(response)} chars)", flush=True)
    
    # Parse
    new_problems = extract_problem_anchor(response, expected_num=9)
    if not new_problems:
        print(f"  First attempt failed to extract problem. Trying again...", flush=True)
        response = call_deepseek(sys_prompt, user_prompt, temperature=0.3, max_tokens=8000)
        if response:
            with open(OUTPUT_FILE.replace('.txt', '_v2.txt'), 'w', encoding='utf-8') as f:
                f.write(response)
            new_problems = extract_problem_anchor(response, expected_num=9)
    
    if not new_problems:
        print(f"  FAILED to extract problem 9!", flush=True)
        sys.exit(1)
    
    problem_9 = new_problems[0]
    if not isinstance(problem_9, dict) or not problem_9.get('text', '').strip():
        print(f"  Invalid problem 9 extracted!", flush=True)
        sys.exit(1)
    
    # Set fields
    problem_9['num'] = 9
    problem_9['day'] = 2
    problem_9.setdefault('answer', '')
    problem_9.setdefault('solution', '')
    problem_9.setdefault('solution_status', '')
    
    print(f"\n  Problem 9 extracted:", flush=True)
    print(f"    Text: {str(problem_9.get('text',''))[:120]}", flush=True)
    
    # Step 3: Check for duplicates
    print(f"\n  Checking for duplicates...", flush=True)
    if is_duplicate(problem_9, current_problems):
        print(f"\n  ERROR: Problem 9 is a DUPLICATE!", flush=True)
        print(f"  Trying again with even stricter prompt...", flush=True)
        
        # Second attempt with even stricter prompt
        strict_prompt = sys_prompt
        strict_user = f"""ВсОШ, 2020-2021, 10 класс, Региональный этап, ВАРИАНТ 2.

УЖЕ ЕСТЬ задачи:
{EXISTING_DAY2_TOPICS}

ПРЕДЫДУЩАЯ ПОПЫТКА дала задачу, которая повторяет одну из этих тем.
ЭТО КАТЕГОРИЧЕСКИ НЕДОПУСТИМО.

НУЖНА ЗАДАЧА НА ДРУГУЮ ТЕМУ:
- Неравенство (докажите, что ... ≥ ...)
- Комбинаторика (раскраска, игры, подсчет способов)
- Функциональное уравнение
- Последовательность, предел
- Геометрия (НО НЕ про биссектрису AD, НЕ про медиану BC)
- Теория чисел НО НЕ факториалы и НЕ делимость m²+n²+m+n

НЕЛЬЗЯ:
- a! + b! = c! или похожие
- AD — биссектриса, ∠BAD = ∠CAD
- m² + n² + m + n делится на mn
- x² + y² + x + y делится на xy

Верни JSON с num=9."""
        
        response2 = call_deepseek(strict_prompt, strict_user, temperature=0.25, max_tokens=8000)
        if response2:
            with open(OUTPUT_FILE.replace('.txt', '_v3.txt'), 'w', encoding='utf-8') as f:
                f.write(response2)
            new_problems2 = extract_problem_anchor(response2, expected_num=9)
            if new_problems2:
                problem_9 = new_problems2[0]
                problem_9['num'] = 9
                problem_9['day'] = 2
                problem_9.setdefault('answer', '')
                problem_9.setdefault('solution', '')
                problem_9.setdefault('solution_status', '')
                
                if not is_duplicate(problem_9, current_problems):
                    print(f"  Second attempt: problem 9 is UNIQUE!", flush=True)
                else:
                    print(f"  Second attempt also returned a DUPLICATE!", flush=True)
                    sys.exit(1)
    
    # Step 4: Insert problem 9 at the right position (after problem 8, before problem 10)
    print(f"\n  Inserting problem 9...", flush=True)
    
    # Find position where problem 8 ends (need to insert 9 before 10)
    insert_pos = len(current_problems)
    for i, p in enumerate(current_problems):
        n = p.get('num', 0)
        if isinstance(n, str):
            try: n = int(n)
            except: pass
        if n >= 10:
            insert_pos = i
            break
    
    current_problems.insert(insert_pos, problem_9)
    print(f"  Inserted at position {insert_pos} (before problem 10)")

    # Step 5: Update entry and save
    all_entries[TARGET_INDEX]['problems'] = current_problems
    
    print(f"\n  Final state:", flush=True)
    for p in current_problems:
        print(f"    Problem {p.get('num')} (day {p.get('day')}): {str(p.get('text',''))[:60]}", flush=True)
    print(f"  Total: {len(current_problems)} problems", flush=True)
    print(f"  Day 1: {sum(1 for p in current_problems if p.get('day')==1)}", flush=True)
    print(f"  Day 2: {sum(1 for p in current_problems if p.get('day')==2)}", flush=True)
    
    save_olympiads_db(all_entries)
    
    print(f"\n{'='*70}", flush=True)
    print("SUCCESS! Grade 10 var 2 (idx 1042) now has 10 problems.", flush=True)


if __name__ == '__main__':
    main()
