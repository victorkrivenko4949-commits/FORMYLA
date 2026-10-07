#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fix problems in olympiads.py where condition (text) contains solution/answer.
Uses repr() for safe Python serialization.
"""
import sys, io, os, ast

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

SRC = 'olympiads.py'
BACKUP = 'olympiads_backup.py'

with open(SRC, 'r', encoding='utf-8') as f:
    content = f.read()

marker = 'OLYMPIADS_DB = '
idx = content.find(marker)
if idx == -1:
    print('ERROR: OLYMPIADS_DB not found')
    sys.exit(1)

header = content[:idx + len(marker)]
list_literal = content[idx + len(marker):].strip()

db = ast.literal_eval(list_literal)
print(f'Loaded {len(db)} olympiads')

def find_olympiad(oid):
    for d in db:
        if d['id'] == oid:
            return d
    return None

def find_problem(o, num):
    for p in o['problems']:
        if p['num'] == num:
            return p
    return None

# ── FIXES ──

# ID 82 prob#5 - strip from "Ответ:"
d = find_olympiad(82)
if d:
    p = find_problem(d, 5)
    if p and 'Ответ:' in p['text']:
        old = p['text']
        p['text'] = old[:old.find('Ответ:')].rstrip()
        print(f'ID82p5: stripped {len(old)-len(p["text"])} chars')

# ID 85 prob#2 - strip from "Ответ:"
d = find_olympiad(85)
if d:
    p = find_problem(d, 2)
    if p and 'Ответ:' in p['text']:
        old = p['text']
        p['text'] = old[:old.find('Ответ:')].rstrip()
        print(f'ID85p2: stripped {len(old)-len(p["text"])} chars')

# ID 540 prob#2 - strip "Ответ: 99 · 98." (or with $\\cdot$)
# The text ends with '…. Ответ: 99 $\\cdot$ 98.'
d = find_olympiad(540)
if d:
    p = find_problem(d, 2)
    if p:
        old = p['text']
        # Try to find "Ответ:" in the text
        idx_ans = old.rfind('Ответ:')
        if idx_ans != -1:
            p['text'] = old[:idx_ans].rstrip()
            print(f'ID540p2: stripped {len(old)-len(p["text"])} chars')
        else:
            print(f'ID540p2: no "Ответ:" found, text ends: {old[-50:]!r}')

# ID 556 prob#4 - strip trailing answer text
d = find_olympiad(556)
if d:
    p = find_problem(d, 4)
    if p:
        old = p['text']
        idx_cond = old.find('(Условие по тексту.)')
        if idx_cond != -1:
            p['text'] = old[:idx_cond].rstrip()
            print(f'ID556p4: stripped {len(old)-len(p["text"])} chars')
        else:
            print(f'ID556p4: "(Условие по тексту.)" not found')

# ID 607 prob#2 - strip from "Решение:"
d = find_olympiad(607)
if d:
    p = find_problem(d, 2)
    if p:
        old = p['text']
        idx_sol = old.find('Решение:')
        if idx_sol != -1:
            p['text'] = old[:idx_sol].rstrip()
            print(f'ID607p2: stripped {len(old)-len(p["text"])} chars')
        else:
            print(f'ID607p2: "Решение:" not found')
    
    # ID 607 prob#3 - truncated text
    p3 = find_problem(d, 3)
    if p3 and len(p3['text'].strip()) < 30:
        new_text = (
            'На доске написано положительное число, с которым разрешается '
            'делать следующие операции: 1) умножать на два; 2) прибавлять один. '
            'Каждый из трёх школьников один раз применил к имеющемуся числу '
            'первую операцию и два раза вторую операцию в некотором порядке. '
            'При этом все три числа оказались различными. '
            'Докажите, что число, полученное третьим школьником, превосходит '
            'число, полученное вторым школьником, более чем на 30%.'
        )
        old = p3['text']
        p3['text'] = new_text
        print(f'ID607p3: replaced ({len(old)}ch -> {len(new_text)}ch)')

# ── WRITE BACK ──
print(f'\nCreating backup: {BACKUP}')
with open(BACKUP, 'w', encoding='utf-8') as f:
    f.write(content)
print('Backup created.')

print('Serializing with repr()...')
new_list_str = repr(db)
new_content = header + new_list_str

# Verify
try:
    compile(new_content + '\n', SRC, 'exec')
    print('Syntax check: OK')
except SyntaxError as e:
    print(f'Syntax check FAILED: {e}')
    with open('olympiads_fixed.py', 'w', encoding='utf-8') as f:
        f.write(new_content)
    sys.exit(1)

# Check file size is reasonable
print(f'New file size: {len(new_content)} bytes (original: {len(content)} bytes)')

with open(SRC, 'w', encoding='utf-8') as f:
    f.write(new_content)
print('Written to olympiads.py')

# ── VERIFY ──
print('\n── Verification ──')
exec(open(SRC, 'r', encoding='utf-8').read())
for tid in [82, 85, 540, 556, 607]:
    for d in OLYMPIADS_DB:
        if d['id'] == tid:
            print(f'\nID {tid} ({d["olympiad"]} {d["year"]} g{d["grade"]}):')
            for p in d['problems']:
                kw_found = False
                for kw in ['Ответ:', 'Решение:', 'Критерии']:
                    if kw in p['text']:
                        print(f'  [!] prob#{p["num"]}: STILL contains "{kw}" ({len(p["text"])}ch)')
                        kw_found = True
                if not kw_found:
                    print(f'  [OK] prob#{p["num"]}: clean ({len(p["text"])} chars)')
            break
