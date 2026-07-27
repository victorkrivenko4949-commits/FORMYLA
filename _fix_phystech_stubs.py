# -*- coding: utf-8 -*-
"""
Fix 15 stub problems in olympiads.py for phystech (id=691, 692, 693).

Strategy:
  1. Import olympiads module → locate 3 stub olympiad sets
  2. For each stub problem, extract the problem statement from the solution field
     using OpenRouter AI (5 parallel workers)
  3. Apply targeted text replacements to olympiads.py

The solution fields contain the full problem statement embedded within them.
We ask the AI to extract just the problem condition text.

Usage:
    python _fix_phystech_stubs.py

Requires:
    OPENROUTER_API_KEY in .env or environment
"""

import asyncio
import json
import os
import re
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# ── load .env ──────────────────────────────────────────────────────────────
from dotenv import load_dotenv

load_dotenv()

# ── stub set identifiers ───────────────────────────────────────────────────
STUB_IDS = [691, 692, 693]

# Pattern to detect stub text fields
STUB_TEXT_PATTERNS = [
    r'^Задача\s+\d+\s*\([^)]+\)\s*\.\s*$',          # "Задача 1 (вариант 9)."
    r'^Задача\s+про\s+.+\([^)]+\)\s*\.\s*$',          # "Задача про квадратные трёхчлены (вариант 13)."
    r'^[А-Яа-яA-Za-z].*\bзадача\b.*\([^)]+\)\s*\.\s*$',  # "Геометрическая задача на хорды (вариант 13)."
]

OUTPUT_DIR = Path("pipeline/output")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
EXTRACTED_PATH = OUTPUT_DIR / "phystech_stub_extractions.json"


def is_stub_text(text: str) -> bool:
    """Check if a text field looks like a stub (short placeholder)."""
    text = text.strip()
    if len(text) > 120:
        return False  # long text → probably real problem
    for pat in STUB_TEXT_PATTERNS:
        if re.match(pat, text):
            return True
    # Also catch very short (< 60 chars) generic stubs
    if len(text) < 60 and ('вариант' in text.lower() or 'задача' in text.lower()):
        return True
    return False


def find_stub_problems():
    """Import olympiads.py and find all stub problems in the 3 target sets."""
    # Import olympiads (may need path manipulation)
    sys.path.insert(0, '.')
    # Clear any cached import
    for key in list(sys.modules.keys()):
        if 'olympiads' in key:
            del sys.modules[key]
    from olympiads import OLYMPIADS_DB

    stubs = []
    for idx, entry in enumerate(OLYMPIADS_DB):
        eid = entry.get('id', '')
        if eid not in STUB_IDS:
            continue
        for prob in entry.get('problems', []):
            text = prob.get('text', '')
            if is_stub_text(text):
                stubs.append({
                    'db_index': idx,
                    'set_id': eid,
                    'year': entry.get('year'),
                    'grade': entry.get('grade'),
                    'round': entry.get('round'),
                    'problem_num': prob.get('num'),
                    'old_text': text,
                    'solution': prob.get('solution', ''),
                    'answer': prob.get('answer', ''),
                })

    _safe_print(f"Found {len(stubs)} stub problems in sets {STUB_IDS}")
    for s in stubs:
        _safe_print(f"  [{s['set_id']}] gr.{s['grade']} {s['round']} prob#{s['problem_num']}: "
              f"\"{s['old_text'][:60]}\"")
    return stubs, OLYMPIADS_DB


# ── AI response sanitization ───────────────────────────────────────────────

def _clean_ai_response(text: str) -> str:
    """
    Sanitize AI response: strip markdown code blocks, extract from embedded JSON.

    The AI sometimes wraps JSON in ```json ... ``` blocks despite instruction
    to return raw JSON. This function handles that.
    """
    if not text:
        return text

    # Pattern 1: ```json\n{ "extracted_text": "..." }\n```
    m = re.search(r'```json\s*\n?(\{.*?\})\s*\n?```', text, re.DOTALL)
    if m:
        try:
            j = json.loads(m.group(1))
            extracted = j.get('extracted_text', '').strip()
            if extracted and len(extracted) > 20:
                return extracted
        except (json.JSONDecodeError, Exception):
            pass

    # Pattern 2: standalone ```json prefix / ``` suffix
    text = re.sub(r'^```json\s*', '', text)
    text = re.sub(r'\s*```$', '', text)

    # Pattern 3: try to parse whole text as JSON object
    try:
        j = json.loads(text)
        if isinstance(j, dict):
            extracted = j.get('extracted_text', '').strip()
            if extracted and len(extracted) > 20:
                return extracted
            # If no extracted_text but has other keys, return the longest string value
            string_vals = [v for v in j.values() if isinstance(v, str) and len(v) > 20]
            if string_vals:
                return max(string_vals, key=len)
    except (json.JSONDecodeError, Exception):
        pass

    # Pattern 4: Try to find any JSON with extracted_text in the text
    m = re.search(r'\{[^{}]*"extracted_text"[^{}]*\}', text, re.DOTALL)
    if m:
        try:
            j = json.loads(m.group())
            extracted = j.get('extracted_text', '').strip()
            if extracted and len(extracted) > 20:
                return extracted
        except (json.JSONDecodeError, Exception):
            pass

    return text.strip()


def _is_answer_only(text: str) -> bool:
    """Check if extracted text looks like an answer rather than a problem condition."""
    if not text:
        return False
    # Answer starts with "Ответ:" or "**Ответ:**"
    if re.match(r'^\s*(\*\*)?Ответ\s*:?\s*', text):
        return True
    # Answer starts with $\text{Ответ: }$
    if text.startswith('$\\text{Ответ:') or text.startswith('$\\text{Ответ}'):
        return True
    # Very short text that is clearly an answer formula (no problem keywords)
    if len(text) < 50 and ('=' in text) and not any(kw in text for kw in
            ['Найдите', 'Решите', 'Пусть', 'Дано', 'Вычислите', 'Сколько',
             'Может', 'Существует', 'Докажите', 'Известно', 'При']):
        return True
    return False


def _strip_trailing_answer(text: str) -> str:
    """Remove trailing **Ответ:** ... from the end of extracted text."""
    text = re.sub(r'\n*\*\*Ответ:\*\*\s*.*$', '', text, flags=re.DOTALL)
    text = re.sub(r'\n*Ответ:\s*.*$', '', text, flags=re.DOTALL)
    return text.strip()


# ── AI extraction ──────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Ты — ассистент по извлечению условий математических задач.

Тебе дано решение олимпиадной задачи. В начале решения (до слова «Решение:» или «**Решение**»)
часто записано УСЛОВИЕ задачи. Твоя задача — извлечь только условие задачи (текст задачи),
убрав всё, что относится к решению, ответу или пояснениям.

Правила:
1. Извлеки ТОЛЬКО условие задачи (как оно записано в начале текста).
2. Если в начале текста нет явного условия, реконструируй его из решения.
3. Сохрани LaTeX-разметку ($...$, $$...$$, \\[ \\] и т.д.).
4. Не добавляй слова «Решение», «Ответ», «Задача N».
5. Если задача начинается с «**Задача N.**» или «**Задача N (вариант M).**» — убери этот заголовок,
   но сохрани сам текст условия.
6. Если в условии есть система уравнений, сохрани её в LaTeX.
7. НЕ используй JSON — верни просто текст условия задачи, чистый текст. Никаких обёрток, никаких {"extracted_text": "..."}. Просто текст."""


def extract_problem_text_ai(solution: str, old_text: str, problem_info: dict) -> str:
    """
    Call OpenRouter AI to extract problem text from the solution field.
    Falls back to programmatic extraction if AI fails.
    Also sanitizes the AI response (strips code blocks, handles answer-only responses).
    """
    # First try programmatic extraction (for cases where it's clean)
    prog_result = _try_programmatic_extract(solution)
    if prog_result:
        return prog_result

    # Otherwise use AI
    result = _call_ai_extract(solution, old_text, problem_info)

    # Sanitize the result
    result = _clean_ai_response(result)

    # Check if we got answer-only text
    if _is_answer_only(result):
        _safe_print(f"  [WARN] AI returned answer-only for {problem_info}, re-trying with stronger prompt")
        # Retry with even stronger emphasis on extracting the problem condition
        result = _call_ai_extract_retry(solution, old_text, problem_info)
        result = _clean_ai_response(result)

    # Strip any trailing answer from the result
    result = _strip_trailing_answer(result)

    return result


def _try_programmatic_extract(solution: str) -> str | None:
    """
    Try to extract problem text programmatically using known patterns.
    """
    s = solution.strip()

    # Pattern 1: "**Задача N (вариант M).** [problem text] **Решение.**"
    m = re.match(
        r'\*\*Задача\s+\d+.*?\*\*\s*\n*(.*?)(?:\n\n\*\*Решение|\n\*\*Решение|^[ \t]*\*\*Решение)',
        s, re.DOTALL
    )
    if m:
        txt = m.group(1).strip()
        if len(txt) > 30:
            return txt

    # Pattern 2: "**Задача N.** [problem text] **Решение.**"
    m = re.match(
        r'\*\*Задача\s+\d+\.\*\*\s*(.*?)(?:\n\n\*\*Решение|\n\*\*Решение)',
        s, re.DOTALL
    )
    if m:
        txt = m.group(1).strip()
        if len(txt) > 30:
            return txt

    # Pattern 3: Problem text right at start before "**Решение.**"
    # e.g. "Решите систему уравнений:\n$$\begin{cases}...\end{cases}$$\n\n**Решение.**"
    m = re.match(
        r'(.+?)(?:\n\n\*\*Решение\.?\*\*|\n\*\*Решение\.?\*\*)',
        s, re.DOTALL
    )
    if m:
        txt = m.group(1).strip()
        # Make sure it looks like a problem (has math or is long enough)
        if len(txt) > 40 and ('$' in txt or '\\' in txt or '?' in txt or 'Найдите' in txt
                              or 'Решите' in txt or 'Пусть' in txt):
            return txt

    # Pattern 4: Problem starts with "**Ответ:**" — the solution has answer-first format.
    # We need AI for this case.

    return None


def _call_ai_extract(solution: str, old_text: str, problem_info: dict) -> str:
    """
    Call OpenRouter AI to extract problem text.
    Uses synchronous httpx call within a thread pool.
    """
    import httpx

    api_key = os.getenv('OPENROUTER_API_KEY')
    if not api_key:
        _safe_print(f"  [WARN] No OPENROUTER_API_KEY, using placeholder for {problem_info}")
        return _make_placeholder_text(solution, old_text, problem_info)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost",
        "X-Title": "PhystechStubFixer",
    }

    payload = {
        "model": "deepseek/deepseek-chat",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Извлеки условие задачи из этого решения. "
                                        f"Если условие не указано явно в начале, восстанови его по решению.\n\n"
                                        f"СТАРОЕ НАЗВАНИЕ: {old_text}\n\n"
                                        f"РЕШЕНИЕ:\n{solution}"}
        ],
        "temperature": 0.1,
        "max_tokens": 2048,
    }

    try:
        resp = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=120.0,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data['choices'][0]['message']['content'].strip()

        # Just return the raw text (no JSON parsing - LaTeX backslashes break JSON)
        if len(content) > 20:
            return content

    except Exception as e:
        _safe_print(f"  [WARN] AI call failed: {e}")

    # Last resort: make a placeholder
    return _make_placeholder_text(solution, old_text, problem_info)


def _call_ai_extract_retry(solution: str, old_text: str, problem_info: dict) -> str:
    """
    Retry AI extraction with a stronger prompt when the first attempt
    returned answer-only text instead of the problem condition.
    """
    import httpx

    api_key = os.getenv('OPENROUTER_API_KEY')
    if not api_key:
        return _make_placeholder_text(solution, old_text, problem_info)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost",
        "X-Title": "PhystechStubFixer",
    }

    retry_prompt = (
        "ВАЖНО: Ты в прошлый раз вернул ответ задачи вместо условия!\n\n"
        "Тебе нужно извлечь именно УСЛОВИЕ задачи (текст самой задачи), а не ответ или решение.\n"
        "Условие задачи обычно находится в самом начале текста, до слов **Решение**.\n"
        "Если условие не указано явно, восстанови его по решению — что дано, что нужно найти.\n\n"
        "НЕ возвращай ответ (Ответ: ...) — верни только условие задачи.\n\n"
        f"СТАРОЕ НАЗВАНИЕ: {old_text}\n\n"
        f"РЕШЕНИЕ:\n{solution}"
    )

    payload = {
        "model": "deepseek/deepseek-chat",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": retry_prompt}
        ],
        "temperature": 0.2,
        "max_tokens": 2048,
    }

    try:
        resp = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=120.0,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data['choices'][0]['message']['content'].strip()

        # Return raw text directly
        if len(content) > 20:
            return content
    except Exception as e:
        _safe_print(f"  [WARN] AI retry call failed: {e}")

    return _make_placeholder_text(solution, old_text, problem_info)


def _make_placeholder_text(solution: str, old_text: str, problem_info: dict) -> str:
    """
    Create a reasonable placeholder when AI extraction fails.
    We reconstruct from the solution content by taking the first meaningful sentence.
    """
    s = solution.strip()
    # Try to get first sentence that looks like a problem statement
    lines = s.split('\n')
    problem_lines = []
    for line in lines:
        line = line.strip()
        # Skip empty lines, solution markers, answer markers
        if not line or line.startswith('**Решение') or line.startswith('**Ответ') \
           or line.startswith('Ответ:') or line.startswith('Решение:'):
            continue
        problem_lines.append(line)
        # If we have enough content and hit a blank line after collecting content
        if len(problem_lines) >= 3 and sum(len(l) for l in problem_lines) > 100:
            break

    if problem_lines:
        candidate = '\n'.join(problem_lines)
        # If the candidate starts with "**Задача", strip the header
        candidate = re.sub(r'^\*\*Задача\s+\d+.*?\*\*\s*\n*', '', candidate).strip()
        if len(candidate) > 30:
            return candidate

    # Ultimate fallback
    return f"Задача {problem_info.get('problem_num', '?')} (вариант из задания)"


# ── file patching ──────────────────────────────────────────────────────────

def _escape_py_string(text: str) -> str:
    """
    Escape text for safe insertion as a Python single-quoted string literal.
    
    LaTeX backslashes like \angle, \sqrt, \triangle contain \a, \t, etc.
    which are Python escape sequences. We must double all backslashes.
    Also handle actual newlines, carriage returns, single quotes, etc.
    """
    result = []
    for ch in text:
        if ch == '\\':
            result.append('\\\\')
        elif ch == "'":
            result.append("\\'")
        elif ch == '\n':
            result.append('\\n')
        elif ch == '\r':
            result.append('\\r')
        elif ch == '\t':
            result.append('\\t')
        elif ord(ch) < 32:
            result.append(f'\\x{ord(ch):02x}')
        else:
            result.append(ch)
    return ''.join(result)


def apply_fixes_to_file(stubs_with_fixes: list[dict]):
    """
    Read olympiads.py as text, apply targeted replacements for the 15 stub text fields,
    write back the modified file.
    """
    olympiad_path = Path("olympiads.py")
    backup_path = olympiad_path.with_suffix(".py.bak_stubs")

    # Create backup first
    shutil.copy2(olympiad_path, backup_path)
    _safe_print(f"\n[BACKUP] Backup saved to {backup_path}")

    # Read the full file
    content = olympiad_path.read_text(encoding='utf-8')

    # Apply each fix: find the old_text in the file and replace it
    for fix in stubs_with_fixes:
        old = fix['old_text']
        new = fix['new_text']
        if old == new:
            continue

        # Escape new_text for Python string literal insertion
        new_escaped = _escape_py_string(new)

        # Escape the old text for regex
        escaped_old = re.escape(old)
        
        # Pattern: match the text field value in single-quoted format
        # Looking for: 'text': 'OLD_TEXT',
        pattern = r"('text'\s*:\s*)'" + escaped_old + r"'(\s*[,\n])"

        def _make_replacer(escaped_text):
            def _replacer(m):
                return m.group(1) + "'" + escaped_text + "'" + m.group(2)
            return _replacer

        new_content, count = re.subn(pattern, _make_replacer(new_escaped), content)
        if count > 0:
            _safe_print(f"  [OK] Replaced text for set#{fix['set_id']} prob#{fix['problem_num']}: "
                  f"\"{old[:40]}...\" -> \"{new[:40]}...\" ({count} replacement(s))")
            content = new_content
        else:
            _safe_print(f"  [WARN] Could not find text in file for set#{fix['set_id']} prob#{fix['problem_num']}: "
                  f"\"{old[:60]}...\"")
            # Try harder: search for the text somewhere in the content
            idx = content.find(old)
            if idx >= 0:
                _safe_print(f"    Found at position {idx}, using direct replacement")
                # For direct replacement, also need to escape
                content = content[:idx] + new_escaped + content[idx + len(old):]
                _safe_print(f"    [OK] Applied direct replacement")
            else:
                _safe_print(f"    [FAIL] Text not found anywhere in file!")

    # Write back
    olympiad_path.write_text(content, encoding='utf-8')
    _safe_print(f"\n[OK] olympiads.py updated successfully!")


# ── safe print for Windows console ──────────────────────────────────────────

def _safe_print(text: str):
    """Print text safely on Windows cp1251 console."""
    try:
        print(text)
    except UnicodeEncodeError:
        # Fall back to ASCII with replacement
        print(text.encode('ascii', 'replace').decode('ascii'))


# ── main ───────────────────────────────────────────────────────────────────

def main():
    _safe_print("=" * 60)
    _safe_print("Phystech Stub Fixer")
    _safe_print("=" * 60)

    # Step 1: Find stub problems
    _safe_print("\n[STEP 1] Finding stub problems...")
    stubs, db = find_stub_problems()
    if not stubs:
        _safe_print("No stub problems found. Nothing to fix.")
        return

    # Step 2: Check if we already have extracted texts
    extracted_map = {}
    if EXTRACTED_PATH.exists():
        try:
            extracted_map = json.loads(EXTRACTED_PATH.read_text(encoding='utf-8'))
            _safe_print(f"\n[CACHE] Loaded {len(extracted_map)} previously extracted texts")
        except Exception as e:
            _safe_print(f"[WARN] Could not load cached extractions: {e}")
            extracted_map = {}

    # Step 3: Extract problem texts (AI with 5 threads)
    _safe_print("\n[STEP 2] Extracting problem texts (5 parallel workers)...")
    to_process = []
    for s in stubs:
        cache_key = f"{s['set_id']}_{s['problem_num']}"
        if cache_key in extracted_map:
            # Still sanitize cached entries (may be from a previous run with malformed data)
            cached_val = extracted_map[cache_key]
            cleaned = _clean_ai_response(cached_val)
            cleaned = _strip_trailing_answer(cleaned)
            if cleaned != cached_val:
                _safe_print(f"  [SANITIZE] [{cache_key}]: cleaned cached entry")
                extracted_map[cache_key] = cleaned
            _safe_print(f"  [CACHED] [{s['set_id']}] prob#{s['problem_num']}")
        else:
            to_process.append(s)

    if to_process:
        results = {}
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_map = {}
            for s in to_process:
                cache_key = f"{s['set_id']}_{s['problem_num']}"
                future = executor.submit(
                    extract_problem_text_ai,
                    s['solution'],
                    s['old_text'],
                    {'set_id': s['set_id'], 'problem_num': s['problem_num'],
                     'grade': s['grade'], 'round': s['round']}
                )
                future_map[future] = cache_key

            for future in as_completed(future_map):
                ck = future_map[future]
                try:
                    result = future.result()
                    results[ck] = result
                    _safe_print(f"  [OK] Extracted [{ck}]: \"{result[:60]}...\"")
                except Exception as e:
                    _safe_print(f"  [FAIL] [{ck}]: {e}")
                    results[ck] = None

        # Update extracted_map
        for k, v in results.items():
            if v:
                # Sanitize before saving
                v = _clean_ai_response(v)
                v = _strip_trailing_answer(v)
                extracted_map[k] = v

        # Save cache
        EXTRACTED_PATH.write_text(
            json.dumps(extracted_map, ensure_ascii=False, indent=2),
            encoding='utf-8'
        )
        _safe_print(f"\n[SAVED] Extractions to {EXTRACTED_PATH}")

    # Step 4: Build fix list
    _safe_print("\n[STEP 3] Preparing fixes...")
    fixes = []
    for s in stubs:
        cache_key = f"{s['set_id']}_{s['problem_num']}"
        new_text = extracted_map.get(cache_key)
        if not new_text or new_text == s['old_text']:
            _safe_print(f"  [WARN] No valid extraction for [{cache_key}], keeping old text")
            continue
        # Extra safety: if the new text is suspiciously short, skip
        if len(new_text) < 20:
            _safe_print(f"  [WARN] Extraction for [{cache_key}] too short ({len(new_text)} chars), skipping")
            continue
        fixes.append({
            **s,
            'new_text': new_text,
        })

    _safe_print(f"  {len(fixes)} fixes to apply")

    # Step 4: Apply fixes to olympiads.py
    _safe_print("\n[STEP 4] Applying fixes to olympiads.py...")
    apply_fixes_to_file(fixes)

    # Step 5: Verify by re-importing
    _safe_print("\n[STEP 5] Verifying olympiads.py loads correctly...")
    try:
        # Clear cache and re-import
        for key in list(sys.modules.keys()):
            if 'olympiads' in key:
                del sys.modules[key]
        from olympiads import OLYMPIADS_DB

        # Check that our fixes are in place
        fixed_count = 0
        for entry in OLYMPIADS_DB:
            if entry.get('id') in STUB_IDS:
                for prob in entry.get('problems', []):
                    text = prob.get('text', '')
                    if not is_stub_text(text) and len(text) > 60:
                        fixed_count += 1

        _safe_print(f"  [OK] olympiads.py loads successfully!")
        _safe_print(f"  [OK] {fixed_count}/15 problems now have proper text fields")
        _safe_print(f"\n[SUMMARY]")
        _safe_print(f"  Backup: olympiads.py.bak_stubs")
        _safe_print(f"  Extractions: {EXTRACTED_PATH}")
    except Exception as e:
        _safe_print(f"  [FAIL] Verification failed: {e}")
        _safe_print(f"  [WARN] Restoring backup...")
        shutil.copy2(Path("olympiads.py.bak_stubs"), Path("olympiads.py"))
        _safe_print(f"  [OK] Backup restored")


if __name__ == '__main__':
    main()
