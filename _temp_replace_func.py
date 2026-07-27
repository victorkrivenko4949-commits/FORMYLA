# -*- coding: utf-8 -*-
"""Temporary script: replace _find_simple_text_span with entry_id-based version."""
import re

FILEPATH = '_fix_all_bad_tasks.py'

with open(FILEPATH, 'r', encoding='utf-8') as f:
    content = f.read()

# Find the start of the function
start_marker = 'def _find_simple_text_span(content: str, set_key: str, problem_num: int) -> tuple:'
idx_start = content.find(start_marker)
if idx_start == -1:
    print("ERROR: could not find function start")
    exit(1)

# Find the end: next 'def ' at same indentation level
# After the function, there's a blank line then 'def apply_fixes_to_file'
end_marker = '\n\ndef apply_fixes_to_file'
idx_end = content.find(end_marker, idx_start)
if idx_end == -1:
    print("ERROR: could not find function end (apply_fixes_to_file)")
    exit(1)

old_func = content[idx_start:idx_end]

print(f"Old function: {len(old_func)} chars (lines {content[:idx_start].count(chr(10)) + 2}-{content[:idx_end].count(chr(10)) + 1})")

# Verify the function spans correctly
assert old_func.startswith('def _find_simple_text_span'), "Doesn't start with function def!"
assert 're.escape(set_key)' in old_func, "Old func uses set_key"
assert 're.escape(str(problem_num))' in old_func, "Old func uses problem_num"
assert 'set_start' in old_func, "Old func uses set_start"

new_func = '''def _find_simple_text_span(content: str, entry_id: int, problem_num: int) -> tuple:
    """
    Find the span (start, end) of the 'text' field value for problem
    `problem_num` in entry with id `entry_id`, handling implicit
    string concatenation.

    olympiads.py stores long string values as:
        'text': 'fragment1... '
                'fragment2... '
                'fragment3...',

    This function locates the opening quote of the first fragment and the
    closing quote of the last fragment, returning absolute byte positions.

    Returns: (span_start, span_end) or (-1, -1)
    """
    # Find the entry by 'id' field
    id_pattern = re.compile(
        r"'id'\s*:\s*" + re.escape(str(entry_id)) + r"\s*(?:[,}])"
    )
    id_match = id_pattern.search(content)
    if not id_match:
        return (-1, -1)

    # Scan backward from id_match to find the opening '{' of this dict
    dict_start = id_match.start()
    while dict_start > 0:
        if content[dict_start] == '{':
            break
        dict_start -= 1
    if content[dict_start] != '{':
        return (-1, -1)

    # Scope the dict (track brace depth for Python dict, NOT LaTeX)
    depth = 0
    dict_end = len(content)
    for i in range(dict_start, len(content)):
        c = content[i]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                dict_end = i + 1
                break
    # NOTE: brace depth tracking for DICT SCOPING is safe because we're
    # scanning raw source code and Python dict braces are unambiguous.
    # This is different from tracking braces INSIDE a string value.

    scope = content[dict_start:dict_end]

    # Find 'num': problem_num within this scope
    num_pattern = re.compile(r"'num'\s*:\s*" + re.escape(str(problem_num)) + r"\s*(?:[,}])")
    num_match = num_pattern.search(scope)
    if not num_match:
        return (-1, -1)

    prob_start = num_match.start()

    # Find 'text': after 'num':
    text_key_match = re.search(r"'text'\s*:", scope[prob_start:])
    if not text_key_match:
        return (-1, -1)

    # Start of text value (after 'text': and whitespace)
    val_rel = prob_start + text_key_match.end()
    while val_rel < len(scope) and scope[val_rel] in ' \t\n\r':
        val_rel += 1

    if val_rel >= len(scope) or scope[val_rel] != "'":
        return (-1, -1)

    # Now find the end of the multi-fragment value.
    # We scan character by character within the string value,
    # tracking when we're inside a single-quoted fragment.
    #
    # IMPORTANT: Do NOT track brace depth here -- the text value may
    # contain LaTeX with unbalanced braces like \\begin{cases}...\\end{cases}
    # or single braces. Brace tracking would break.

    pos = val_rel + 1  # skip opening quote of first fragment
    last_close = -1  # position of the closing quote of the last fragment found

    while pos < len(scope):
        ch = scope[pos]

        # Handle escape sequences: skip the escaped char after backslash
        if ch == '\\\\' and pos + 1 < len(scope):
            pos += 2
            continue

        if ch == "'":
            # Possible closing quote of a fragment
            # Check what follows: whitespace + another ' = continuation
            after = pos + 1
            while after < len(scope) and scope[after] in ' \\t\\n\\r':
                after += 1

            if after < len(scope) and scope[after] == "'":
                # This is the end of a fragment, and there's another fragment
                last_close = pos
                pos = after + 1  # skip opening quote of next fragment
                continue
            else:
                # This is the FINAL closing quote of the last fragment
                last_close = pos
                break

        pos += 1

    if last_close == -1:
        return (-1, -1)

    span_start_abs = dict_start + val_rel
    span_end_abs = dict_start + last_close + 1  # +1 to include the closing quote

    return (span_start_abs, span_end_abs)'''

new_content = content[:idx_start] + new_func + content[idx_end:]

# Verify the new function is syntactically valid
try:
    compile(new_content, FILEPATH, 'exec')
    print("Syntax OK!")
except SyntaxError as e:
    print(f"SYNTAX ERROR: {e}")
    # Show context
    lines = new_content.split('\\n')
    if e.lineno:
        start = max(0, e.lineno - 3)
        end = min(len(lines), e.lineno + 2)
        for ln in range(start, end):
            marker = " >>>" if ln == e.lineno - 1 else "    "
            print(f"  {marker} {ln + 1}: {lines[ln]}")
    exit(1)

with open(FILEPATH, 'w', encoding='utf-8') as f:
    f.write(new_content)

# Verify the old function is gone
if new_func in new_content:
    print("New function written successfully!")
else:
    print("ERROR: new function not found in written content!")
    exit(1)

# Verify the old function is gone
if old_func in new_content:
    print("ERROR: old function still present!")
    exit(1)

print(f"Done! Replaced {len(old_func)}-char old function with {len(new_func)}-char new function")
