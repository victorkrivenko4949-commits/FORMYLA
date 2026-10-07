#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Merge 60 solutions from tasks_solutions_out.json INTO olympiads.py.

Uses exec() to load olympiads.py, modifies data in-memory, saves back
using proper Python repr with line-wrapping for string values.
Converts LaTeX: \(...\) -> $...$, \[...\] -> $$...$$.
"""
import json, os, re, sys

os.chdir(r'C:\Users\Victor\Desktop\Новая папка (2)')

# 1. Load olympiads.py
print("Loading olympiads.py...", flush=True)
with open('olympiads.py', 'r', encoding='utf-8') as f:
    src = f.read()
exec(src)
db = OLYMPIADS_DB

# Build lookup
lookup = {}
for rec in db:
    k = (rec['olympiad'], rec['year'], rec['grade'], rec['round'])
    lookup.setdefault(k, []).append(rec)

# 2. Load solutions
with open(r'C:\Users\Victor\Downloads\tasks_solutions_out.json', 'r', encoding='utf-8') as f:
    solutions = json.load(f)
print(f"Loaded {len(solutions)} solutions.", flush=True)

# 3. LaTeX converter
def convert_latex(text):
    text = text.replace('\\(', '$').replace('\\)', '$')
    text = text.replace('\\[', '$$').replace('\\]', '$$')
    return text

# 4. Merge
matched = 0
not_found = []
for s in solutions:
    k = (s['olympiad'], s['year'], s['grade'], s['round'])
    candidates = lookup.get(k, [])
    found = False
    for rec in candidates:
        for p in rec['problems']:
            if str(p['num']) == str(s['num']):
                p['solution'] = convert_latex(s['solution'])
                p['answer'] = convert_latex(s.get('answer', ''))
                p['solution_status'] = 'generated'
                matched += 1
                found = True
                break
        if found:
            break
    if not found:
        not_found.append(s['key'])

print(f"Merged: {matched}/{len(solutions)}", flush=True)
if not_found:
    print(f"Not found ({len(not_found)}): {not_found[:5]}...", flush=True)

# 5. Save olympiads.py
print("Saving olympiads.py...", flush=True)

def wrap_str(s, indent):
    """Return a Python string literal with olympiads.py-style line wrapping.
    
    indent = number of spaces before the opening quote.
    Returns one or more joined string literals for long strings.
    """
    # Escape for Python single-quoted string
    escaped = s.replace('\\', '\\\\').replace("'", "\\'")
    
    # Split at explicit newlines
    parts = escaped.split('\\n')
    
    if len(parts) <= 1 and len(escaped) <= 80 - indent - 2:
        return "'" + escaped + "'"
    
    if len(parts) > 1:
        # Has \n - produce separate chunks
        chunks = []
        for i, p in enumerate(parts):
            if i < len(parts) - 1:
                chunks.append("'" + p + "\\n'")
            else:
                chunks.append("'" + p + "'")
        # Join with proper indentation
        cont_indent = indent + 28
        joiner = "\n" + " " * cont_indent
        return joiner.join(chunks)
    
    # Long single line - wrap at spaces
    max_line = 80 - indent - 2
    chunks = []
    remaining = escaped
    while remaining:
        if len(remaining) <= max_line:
            chunks.append("'" + remaining + "'")
            break
        chunk = remaining[:max_line]
        # Try to break at space
        last_space = chunk.rfind(' ')
        if last_space > max_line // 2:
            chunks.append("'" + remaining[:last_space] + "'")
            remaining = remaining[last_space:]
        else:
            chunks.append("'" + remaining[:max_line] + "'")
            remaining = remaining[max_line:]
    cont_indent = indent + 28
    joiner = "\n" + " " * cont_indent
    return joiner.join(chunks)


def fmt_val(v, indent):
    """Format a value for olympiads.py with proper indentation."""
    if isinstance(v, bool):
        return 'True' if v else 'False'
    if isinstance(v, int):
        return str(v)
    if v is None:
        return 'None'
    if isinstance(v, str):
        return wrap_str(v, indent)
    if isinstance(v, list):
        return fmt_list(v, indent)
    if isinstance(v, dict):
        return fmt_dict(v, indent)
    return repr(v)


def fmt_dict(d, indent):
    """Format a dict like olympiads.py: {'key': value, 'key2': value2, ...}"""
    if not d:
        return '{}'
    items = list(d.items())
    # Try single line first
    single = '{'
    for i, (k, v) in enumerate(items):
        if i > 0:
            single += ', '
        single += repr(k) + ': ' + fmt_val(v, indent + 2)
    single += '}'
    if len(single) <= 100 - indent:
        return single
    
    # Multi-line
    lines = ['{']
    for i, (k, v) in enumerate(items):
        comma = ',' if i < len(items) - 1 else ''
        val_str = fmt_val(v, indent + 2)
        if '\n' in val_str:
            lines.append(' ' * (indent + 2) + repr(k) + ': ' + val_str + comma)
        else:
            lines.append(' ' * (indent + 2) + repr(k) + ': ' + val_str + comma)
    lines.append(' ' * indent + '}')
    return '\n'.join(lines)


def fmt_list(lst, indent):
    """Format a list like olympiads.py: [item1, item2, ...]"""
    if not lst:
        return '[]'
    # Try single line first
    single = '['
    for i, item in enumerate(lst):
        if i > 0:
            single += ', '
        single += fmt_val(item, indent + 1)
    single += ']'
    if len(single) <= 100 - indent:
        return single
    
    # Multi-line
    lines = ['[']
    for item in lst:
        val_str = fmt_val(item, indent + 1)
        if '\n' in val_str:
            lines.append(' ' * (indent + 1) + val_str + ',')
        else:
            lines.append(' ' * (indent + 1) + val_str + ',')
    lines.append(' ' * indent + ']')
    return '\n'.join(lines)


# Generate olympiads.py content
output = 'OLYMPIADS_DB = ' + fmt_list(db, 0)
output += '\n'

with open('olympiads.py', 'w', encoding='utf-8') as f:
    f.write(output)

print("olympiads.py saved successfully!", flush=True)

# Verify
print("Verifying...", flush=True)
with open('olympiads.py', 'r', encoding='utf-8') as f:
    verify_src = f.read()
exec(verify_src)
verify_db = OLYMPIADS_DB
gen_count = sum(1 for rec in verify_db for p in rec['problems'] if p.get('solution_status') == 'generated')
print(f"Problems with solution_status='generated': {gen_count}", flush=True)
print("Done!", flush=True)
