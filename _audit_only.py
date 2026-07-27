#!/usr/bin/env python3
"""Audit existing tasks and taxonomy - write to file"""
import json, os, hashlib

REPORT_PATH = r"c:\Users\Redmi\Desktop\Новая папка (2)\_FINAL_AUDIT_REPORT.txt"

def sha256_file(path):
    if not os.path.exists(path):
        return "NOT_FOUND"
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()

lines = []
def log(s):
    lines.append(s)
    print(s)

log("=" * 70)
log("АУДИТ ЗАДАЧ L1-L3 — существующий банк и таксономия")
log("=" * 70)

# 1. Taxonomy
log("\n1. ТАКСОНОМИЯ: taxonomy_by_grade.json")
log(f"   SHA-256: {sha256_file('taxonomy_by_grade.json')}")
with open('taxonomy_by_grade.json', 'rb') as f:
    tax = json.loads(f.read())

gt = tax.get('grade_theme_map', {})
log(f"   Классы в таксономии: {sorted(gt.keys(), key=int)}")

theme_ids_used = set()
subtotal_by_grade = {}
for g_str in sorted(gt.keys(), key=int):
    g = int(g_str)
    info = gt[g_str]
    themes = info.get('themes', [])
    theme_ids_used.update(themes)
    
    sub_count = 0
    for tid in themes:
        td = tax.get('theme_definitions', {}).get(tid, {})
        subs = td.get('subtopics', [])
        sub_count += len(subs)
    subtotal_by_grade[g] = sub_count
    
    log(f"   {g} класс:")
    log(f"        раздел: {info.get('section_name', 'N/A')}")
    log(f"        тем: {len(themes)}")
    log(f"        ID тем: {themes}")
    log(f"        подтем (S0/S1/S2): {sub_count}")

total_subtopics = sum(subtotal_by_grade.values())
total_themes = len(theme_ids_used)
log(f"\n   ВСЕГО уникальных theme_id: {total_themes}")
log(f"   ВСЕГО подтем: {total_subtopics}")
log(f"   ЦЕЛЬ ячеек (подтема x 3 уровня): {total_subtopics * 3}")
log(f"   ЦЕЛЬ задач (5 на ячейку): {total_subtopics * 3 * 5}")

# 2. Existing bank
log("\n2. СУЩЕСТВУЮЩИЙ БАНК: victor2_generated.json")
log(f"   SHA-256: {sha256_file('victor2_generated.json')}")
with open('victor2_generated.json', 'rb') as f:
    bank = json.loads(f.read())

log(f"   Всего записей: {len(bank)}")

# Categorize
cells = {}
no_stmt = 0
by_level = {1:0, 2:0, 3:0}
by_grade = {5:0,6:0,7:0,8:0,9:0,10:0,11:0}
cell_by_level = {1:set(), 2:set(), 3:set()}

for d in bank:
    stmt = d.get('statement', '') or ''
    if not stmt.strip():
        no_stmt += 1
        continue
    
    lv = d.get('level', 0)
    if isinstance(lv, str) and lv.startswith('L'):
        lv = int(lv[1])
    lv = int(lv or 0)
    grade = d.get('grade', 0)
    tid = d.get('theme_id', '')
    
    if 1 <= lv <= 3 and grade in (5,6,7,8,9,10,11):
        key = f"G{grade}|{tid}|L{lv}"
        cells[key] = cells.get(key, 0) + 1
        by_level[lv] = by_level.get(lv, 0) + 1
        by_grade[grade] = by_grade.get(grade, 0) + 1
        cell_by_level[lv].add(key)

log(f"   Без условия: {no_stmt}")
log(f"   Ячеек L1-L3: {len(cells)}")
for lv in [1, 2, 3]:
    log(f"     L{lv}: {by_level.get(lv, 0)} задач, {len(cell_by_level[lv])} ячеек")
log(f"   По классам:")
for g in sorted(by_grade.keys()):
    log(f"     {g} класс: {by_grade.get(g, 0)} задач")

# Count tasks per cell
empty5 = 0
low = 0
partial = 0
ready = 0
overfull = 0
total_tasks_in_cells = 0
for key, cnt in sorted(cells.items()):
    if cnt == 0: empty5 += 1
    elif cnt <= 2: low += 1
    elif cnt <= 4: partial += 1
    elif cnt == 5: ready += 1
    else: overfull += 1
    total_tasks_in_cells += cnt

log(f"\n   Состояние ячеек:")
log(f"     EMPTY (0): {empty5}")
log(f"     LOW (1-2): {low}")
log(f"     PARTIAL (3-4): {partial}")
log(f"     READY (5): {ready}")
log(f"     OVERFULL (>5): {overfull}")
log(f"   Всего задач в ячейках: {total_tasks_in_cells}")

# 3. Shortage
target_cells = total_subtopics * 3
shortage = target_cells * 5 - total_tasks_in_cells
log(f"\n3. ДЕФИЦИТ")
log(f"   Ячейки по таксономии: {target_cells}")
log(f"   Ячейки с задачами: {len(cells)}")
log(f"   Пустых ячеек: {target_cells - len(cells)}")
log(f"   Исходный shortage: {shortage}")
log(f"   (если все существующие задачи APPROVE качества)")

# 4. Pipeline status
log("\n4. ПАЙПЛАЙН")
outdir = "l1_l3_generation/max_fill_20260722_111737"
if os.path.isdir(outdir):
    files = os.listdir(outdir)
    log(f"   max_fill_20260722_111737 содержит {len(files)} файлов: {files}")
    for fn in sorted(files):
        fp = os.path.join(outdir, fn)
        size = os.path.getsize(fp)
        log(f"     {fn}: {size} bytes, SHA256={sha256_file(fp)[:16]}...")
else:
    log(f"   max_fill_20260722_111737: НЕ НАЙДЕН (пусто)")

# 5. Checkpoint
cp = "l1_l3_generation/l1_l3_generation_checkpoint.json"
if os.path.exists(cp):
    with open(cp, 'rb') as f:
        ck = json.loads(f.read())
    log(f"\n   Checkpoint: найден, keys={list(ck.keys())[:8]}")
else:
    log(f"\n   Checkpoint: НЕ НАЙДЕН")

# 6. Target grid
tg = "l1_l3_generation/target_grid.json"
if os.path.exists(tg):
    with open(tg, 'rb') as f:
        gd = json.loads(f.read())
    log(f"\n   target_grid.json: найден, cells={len(gd) if isinstance(gd, list) else 'dict'}")
else:
    log(f"\n   target_grid.json: НЕ НАЙДЕН")

log("\n" + "=" * 70)
log("ИТОГО:")
log(f"  Таксономия: {total_themes} тем, {total_subtopics} подтем")
log(f"  Цель: {target_cells} ячеек, {target_cells * 5} задач")
log(f"  Есть (с условием): ~{total_tasks_in_cells} задач в {len(cells)} ячейках")
log(f"  Дефицит задач: ~{shortage}")
log(f"  Пайплайн: {'НЕ ЗАПУЩЕН' if not os.path.isdir(outdir) or not os.listdir(outdir) else 'ЗАПУЩЕН'}")
log("=" * 70)

with open(REPORT_PATH, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))

print(f"\n\nReport saved to {REPORT_PATH}")
print(f"SHA256: {sha256_file(REPORT_PATH)[:16]}...")
