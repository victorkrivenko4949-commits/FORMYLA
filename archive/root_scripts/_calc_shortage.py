#!/usr/bin/env python3
"""Calculate exact shortage per cell and write report"""
import json, os
from collections import Counter, defaultdict

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_SHORTAGE_REPORT.txt')
out_lines = []

def log(s=""):
    out_lines.append(s)
    print(s)

# 1. Load taxonomy
log("=" * 70)
log("ДЕФИЦИТ L1-L3: ПОЛНЫЙ АНАЛИЗ")
log("=" * 70)

with open('taxonomy_by_grade.json', 'r', encoding='utf-8') as f:
    tax = json.load(f)

grades_data = tax['grades']

# Build mapping: theme_id -> {grade, name, subtopics}
themes = {}
for g_str, g_info in grades_data.items():
    grade = int(g_str)
    for t in g_info['themes']:
        tid = t['id']
        themes[tid] = {
            'grade': grade,
            'name': t['name'],
            'subtopics': t.get('subtopics', [])
        }

log(f"\nТаксономия:")
log(f"  Классы: {sorted([int(k) for k in grades_data.keys()])}")
total_themes = len(themes)
for g in sorted([int(k) for k in grades_data.keys()]):
    g_themes = {tid: v for tid, v in themes.items() if v['grade'] == g}
    g_sub = sum(len(v['subtopics']) for v in g_themes.values())
    log(f"  {g} класс: {len(g_themes)} тем, {g_sub} подтем")
    for tid in sorted(g_themes):
        log(f"    {tid}: {g_themes[tid]['name']} - {len(g_themes[tid]['subtopics'])} подтем")

total_subtopics = sum(len(v['subtopics']) for v in themes.values())
log(f"\n  ВСЕГО тем: {total_themes}")
log(f"  ВСЕГО подтем: {total_subtopics}")
log(f"  ЯЧЕЕК (тема x 3 уровня): {total_themes * 3}")

# 2. Load bank
with open('victor2_generated.json', 'r', encoding='utf-8') as f:
    bank = json.load(f)

log(f"\nБанк задач: victor2_generated.json")
log(f"  Записей: {len(bank)}")

# Count per cell (current taxonomy)
cells = Counter()
themes_in_bank = set()
themes_not_in_taxonomy = set()
grade_mismatch = 0
no_statement = 0

for d in bank:
    stmt = (d.get('statement') or '').strip()
    if not stmt:
        no_statement += 1
        continue
    
    lv = d.get('level', 0)
    if isinstance(lv, str) and lv.startswith('L'):
        lv = int(lv[1])
    lv = int(lv or 0)
    grade = d.get('grade', 0)
    tid = d.get('theme_id', '')
    
    themes_in_bank.add(tid)
    
    if tid not in themes:
        themes_not_in_taxonomy.add(tid)
        continue
    
    expected_grade = themes[tid]['grade']
    if grade != expected_grade:
        grade_mismatch += 1
        continue
    
    if 1 <= lv <= 3:
        key = f"G{grade}|{tid}|L{lv}"
        cells[key] += 1

log(f"  Без условия: {no_statement}")
log(f"  Тема не в таксономии: {len(themes_not_in_taxonomy)} ({themes_not_in_taxonomy})")
log(f"  Несовпадение класс-тема: {grade_mismatch}")
log(f"  Задач в ячейках: {sum(cells.values())}")

# 3. Build full grid
log(f"\n" + "=" * 70)
log("ПОЛНАЯ СЕТКА И ДЕФИЦИТ")
log("=" * 70)

EMPTY, LOW, PARTIAL, READY, OVERFULL = 0, 0, 0, 0, 0
total_shortage = 0
by_class_shortage = defaultdict(int)
by_level_shortage = defaultdict(int)
all_data = []

for g in sorted([int(k) for k in grades_data.keys()]):
    log(f"\n--- {g} КЛАСС ---")
    for tid in sorted(themes):
        if themes[tid]['grade'] != g:
            continue
        theme_name = themes[tid]['name']
        for lv in [1, 2, 3]:
            key = f"G{g}|{tid}|L{lv}"
            cnt = cells.get(key, 0)
            shortage = max(0, 5 - cnt)
            total_shortage += shortage
            by_class_shortage[g] += shortage
            by_level_shortage[lv] += shortage
            
            if cnt == 0: EMPTY += 1
            elif cnt <= 2: LOW += 1
            elif cnt <= 4: PARTIAL += 1
            elif cnt == 5: READY += 1
            else: OVERFULL += 1
            
            status = ("EMPTY" if cnt == 0 else 
                     "LOW" if cnt <= 2 else 
                     "PARTIAL" if cnt <= 4 else 
                     "READY" if cnt == 5 else "OVERFULL")
            
            all_data.append((key, cnt, shortage, status))
            
            if cnt < 5:
                log(f"  {key} ({theme_name[:40]}): {cnt}/5 задач, дефицит {shortage} [{status}]")

log(f"\n" + "=" * 70)
log("СВОДКА")
log("=" * 70)
log(f"  Всего ячеек: {total_themes * 3}")
log(f"  EMPTY (0): {EMPTY}")
log(f"  LOW (1-2): {LOW}")
log(f"  PARTIAL (3-4): {PARTIAL}")
log(f"  READY (5): {READY}")
log(f"  OVERFULL (>5): {OVERFULL}")
log(f"  READY+OVERFULL: {READY + OVERFULL} (не требуют генерации)")
log(f"")
log(f"  ОБЩИЙ ДЕФИЦИТ: {total_shortage} задач")
log(f"")
log(f"  По классам:")
for g in sorted(by_class_shortage):
    g_themes = len([t for t in themes.values() if t['grade'] == g])
    g_cells = sum(1 for k, c, s, st in all_data if k.startswith(f"G{g}|"))
    g_filled = sum(1 for k, c, s, st in all_data if k.startswith(f"G{g}|") and c > 0)
    log(f"    {g} класс: {g_cells} ячеек, {g_filled} заполнено, дефицит {by_class_shortage[g]}")
log(f"")
log(f"  По уровням:")
for lv in [1, 2, 3]:
    lv_cells = sum(1 for k, c, s, st in all_data if f"L{lv}" in k)
    lv_filled = sum(1 for k, c, s, st in all_data if f"L{lv}" in k and c > 0)
    log(f"    L{lv}: {lv_filled}/{lv_cells} ячеек, дефицит {by_level_shortage[lv]}")

log(f"\n  ЦЕЛЬ: {total_themes * 3 * 5} задач ({total_themes * 3} ячеек x 5)")
log(f"  ЕСТЬ: {sum(cells.values())} задач в {len([1 for c in cells.values() if c > 0])} ячейках")

# Write report
with open(OUT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(out_lines))

print(f"\n\nОтчёт сохранён: {OUT}")
