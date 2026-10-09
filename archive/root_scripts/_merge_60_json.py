#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Merge 60 solutions from tasks_solutions_out.json INTO olympiads.py.

Uses JSON serialization to avoid Python source-code formatting bugs.
"""
import json, os, sys

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

# 5. Save olympiads.py using JSON
print("Saving olympiads.py...", flush=True)
with open('olympiads.py', 'w', encoding='utf-8') as f:
    f.write('OLYMPIADS_DB = ')
    json.dump(db, f, ensure_ascii=False, indent=2)
    f.write('\n')

# 6. Verify
print("Verifying saved file...", flush=True)
with open('olympiads.py', 'r', encoding='utf-8') as f:
    verify_src = f.read()
try:
    exec(verify_src)
    new_db = OLYMPIADS_DB
    gen_count = sum(1 for o in new_db for p in o['problems'] if p.get('solution_status') == 'generated')
    print(f"Verified: {len(new_db)} olympiads, {gen_count} generated solutions", flush=True)
except SyntaxError as e:
    print(f"SYNTAX ERROR after save: {e}", flush=True)
    sys.exit(1)

print("Done!", flush=True)
