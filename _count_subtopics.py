# -*- coding: utf-8 -*-
import sqlite3, json, re

db = sqlite3.connect('instance/formyla.db')

# 1. From gen_conveyor (what we already have)
subs = db.execute('SELECT DISTINCT curator_subtopic FROM gen_conveyor ORDER BY curator_subtopic').fetchall()
print(f'\n=== GEN CONVEYOR: {len(subs)} unique subtopics ===')
by_grade = {}
for s in subs:
    slug = s[0]
    g = slug[1:slug.index('_')] if '_' in slug else '?'
    g = g.lstrip('0123456789') or slug[1] if len(slug)>1 else '?'
    try:
        g = int(slug[1:].split('_')[0]) if '_' in slug else int(slug[1:3]) if len(slug)>2 else 0
    except: g = 0
    by_grade.setdefault(g, []).append(slug)

for g in sorted(by_grade):
    print(f'  Grade {g}: {len(by_grade[g])} subtopics')
    for s in by_grade[g][:10]: print(f'    - {s}')
    if len(by_grade[g]) > 10: print(f'    ... +{len(by_grade[g])-10} more')

# 2. From adaptive_tasks
print(f'\n=== ADAPTIVE TASKS subtopics per grade ===')
for g in [5,6,7,8,9,10,11]:
    subs2 = db.execute(
        'SELECT DISTINCT subtopic FROM adaptive_tasks WHERE grade=? AND subtopic IS NOT NULL AND subtopic!=""',
        (g,)
    ).fetchall()
    print(f'  Grade {g}: {len(subs2)} unique subtopics')

# 3. From curator/monthly_cycle.py — themes_of_section
print(f'\n=== CURATOR CYCLE themes (from monthly_cycle.py) ===')
with open('curator/monthly_cycle.py','r',encoding='utf-8') as f:
    mc = f.read()

# Find themes_of_section function patterns
for g in [5,6,7,8,9,10,11]:
    themes = set(re.findall(rf'G{g}_T\d+', mc))
    if themes:
        print(f'  Grade {g}: {len(themes)} themes referenced in code')

# 4. From all_210_subtopics.txt
print(f'\n=== ALL 210 SUBTOPICS file ===')
try:
    with open('all_210_subtopics.txt','r',encoding='utf-8') as f:
        lines = f.readlines()
    total = len([l for l in lines if l.strip()])
    print(f'  Total lines: {total}')
    by_g = {}
    for l in lines:
        for g in [5,6,7,8,9,10,11]:
            if l.strip().startswith(f'G{g}_'):
                by_g[g] = by_g.get(g, 0) + 1
    for g in sorted(by_g): print(f'  Grade {g}: {by_g[g]} subtopics')
except: print('  File not found')

db.close()

# ── FINAL CALC ──
total_unique = len(subs)
subtopics_per_grade = max(by_g.values()) if by_g else 7
print(f'\n{"="*60}')
print(f'FINAL: {total_unique} unique subtopics across all grades')
print(f'35 tasks/subtopic x 5 levels x {total_unique} subtopics')
total_tasks = total_unique * 35
total_gens = total_tasks / 10  # 10 tasks per generation
print(f'Total tasks needed: {total_tasks}')
print(f'Total generations: {total_gens:.0f}')
print(f'Time (3 concurrent): {total_gens/3*5/60:.1f} hours')
print(f'Cost: ${total_gens*0.04:.2f}')
