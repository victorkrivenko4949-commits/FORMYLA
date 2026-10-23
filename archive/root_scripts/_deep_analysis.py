#!/usr/bin/env python3
"""
Глубокий анализ: таксономия, существующие задачи, shortage.
Ищет актуальную таксономию и определяет точное состояние.
"""
import json, os, hashlib
from collections import defaultdict

def sha256f(path):
    if not os.path.exists(path):
        return "NOT_FOUND"
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()

def load_jsonl(path):
    items = []
    if not os.path.exists(path):
        return items
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError as e:
                    print(f"  JSON error: {e}")
    return items

# ============== 1. Поиск актуальной таксономии ==============
print("=" * 70)
print("1. ПОИСК АКТУАЛЬНОЙ ТАКСОНОМИИ")
print("=" * 70)

# Проверяем все возможные источники
tax_candidates = [
    "l1_l3_generation/taxonomy_by_grade.json",
    "taxonomy_by_grade.json",
    "l1_l3_generation/canonical_taxonomy.json",
    "l1_l3_generation/target_grid.json",
    "l1_l3_generation/l1_l3_generated_audit.json",
]

for cand in tax_candidates:
    if os.path.exists(cand):
        sz = os.path.getsize(cand)
        sh = sha256f(cand)
        print(f"[{sz:>8} bytes] {cand}")
        print(f"          SHA256: {sh}")
        if cand.endswith('.json'):
            with open(cand, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict):
                print(f"          Keys: {list(data.keys())}")
                if 'grades' in data:
                    print(f"          grades levels: {list(data['grades'].keys())}")
                    for gk in sorted(data['grades'].keys()):
                        items = data['grades'][gk]
                        print(f"            Grade {gk}: {len(items)} items")
                        if items and isinstance(items[0], str):
                            print(f"              strings, first: {items[0][:60]}")
                        elif items and isinstance(items[0], dict):
                            print(f"              dict, keys: {list(items[0].keys())}")
                elif 'topics' in data:
                    print(f"          topics count: {len(data['topics'])}")
                elif not any(k.startswith('G') for k in data.keys()):
                    print(f"          Grade keys: {[k for k in data.keys() if k.isdigit()]}")
            elif isinstance(data, list):
                print(f"          List of {len(data)} items")
        print()

# ============== 2. Проверка taxonomy_by_grade.json ==============
print("=" * 70)
print("2. ТЕКУЩАЯ taxonomy_by_grade.json")
print("=" * 70)

with open("taxonomy_by_grade.json", "r", encoding="utf-8") as f:
    tax = json.load(f)

if 'meta' in tax:
    meta = tax['meta']
    print(f"meta.total_themes: {meta.get('total_themes')}")
    print(f"meta.total_subtopics: {meta.get('total_subtopics')}")
    summary = meta.get('grade_summary', {})
    for g in sorted(summary.keys()):
        print(f"  Grade {g}: {summary[g].get('themes')} themes, {summary[g].get('subtopics')} subtopics")

if 'grades' in tax:
    g_total = 0
    all_ids = set()
    for g_str in sorted(tax['grades'].keys()):
        items = tax['grades'][g_str]
        print(f"\nGrade {g_str}: {len(items)} items")
        for item in items:
            if isinstance(item, str):
                print(f"  STR: {item[:80]}")
                g_total += 1
            elif isinstance(item, dict):
                tid = item.get('theme_id', item.get('id', '?'))
                theme = item.get('theme', item.get('name', item.get('subtopic', '?')))
                section = item.get('section', '')
                all_ids.add(tid)
                print(f"  {tid}: {str(theme)[:60]} [{str(section)[:20]}]")
                g_total += 1
    print(f"\nTotal items in grades: {g_total}")
    print(f"Unique IDs: {len(all_ids)}")

# ============== 3. Поиск подходящей таксономии для 135 тем ==============
print("\n" + "=" * 70)
print("3. ПОИСК ТАКСОНОМИИ НА 135 ТЕМ")
print("=" * 70)

# Check l1_l3_generation/generated files - maybe the target grid has it
if os.path.exists("l1_l3_generation/target_grid.json"):
    with open("l1_l3_generation/target_grid.json", "r", encoding="utf-8") as f:
        tg = json.load(f)
    print(f"target_grid.json type: {type(tg).__name__}")
    if isinstance(tg, list):
        print(f"  Items: {len(tg)}")
        if tg:
            print(f"  First item keys: {list(tg[0].keys()) if isinstance(tg[0], dict) else 'not dict'}")
        # Check for cell keys
        grade_tids = defaultdict(set)
        for item in tg:
            if isinstance(item, dict):
                g = item.get('grade')
                tid = item.get('theme_id')
                if g and tid:
                    grade_tids[g].add(tid)
        for g in sorted(grade_tids.keys()):
            print(f"  Grade {g}: {len(grade_tids[g])} theme_ids")

# Check l1_l3_generated_audit
if os.path.exists("l1_l3_generation/l1_l3_generated_audit.json"):
    with open("l1_l3_generation/l1_l3_generated_audit.json", "r", encoding="utf-8") as f:
        aud = json.load(f)
    print(f"\nl1_l3_generated_audit.json type: {type(aud).__name__}")
    if isinstance(aud, list):
        print(f"  Items: {len(aud)}")
        if aud and isinstance(aud[0], dict):
            print(f"  First keys: {list(aud[0].keys())[:10]}")
            # Check theme_ids
            tids = set()
            for a in aud:
                tid = a.get('theme_id')
                if tid:
                    tids.add(tid)
            print(f"  Unique theme_ids: {len(tids)}")
    elif isinstance(aud, dict):
        print(f"  Keys: {list(aud.keys())[:10]}")

# ============== 4. Анализ FINAL JSONL ==============
print("\n" + "=" * 70)
print("4. АНАЛИЗ FINAL JSONL")
print("=" * 70)

final_path = "l1_l3_generation/max_fill_20260723_015316/FORMYLA_L1_L3_FINAL.jsonl"
if os.path.exists(final_path):
    tasks = load_jsonl(final_path)
    print(f"Всего задач: {len(tasks)}")
    
    # Статистика
    statuses = defaultdict(int)
    grades = defaultdict(int)
    levels = defaultdict(int)
    cells_by_id = defaultdict(int)
    
    for t in tasks:
        statuses[t.get('quality_status', 'NONE')] += 1
        grades[t.get('grade', 0)] += 1
        levels[t.get('level', 0)] += 1
        g = t.get('grade', 0)
        tid = t.get('theme_id', '?')
        l = t.get('level', 0)
        cell = f"G{g}|{tid}|L{l}"
        cells_by_id[cell] += 1
    
    print(f"Статусы: {dict(statuses)}")
    print(f"Классы: {dict(sorted(grades.items()))}")
    print(f"Уровни: {dict(sorted(levels.items()))}")
    
    # Анализ ячеек APPROVE
    approved = [t for t in tasks if t.get('quality_status') == 'APPROVE']
    print(f"\nAPPROVE: {len(approved)}")
    
    if approved:
        approve_cells = defaultdict(int)
        approve_grade_tids = defaultdict(set)
        for t in approved:
            g = t.get('grade', 0)
            tid = t.get('theme_id', '?')
            l = t.get('level', 0)
            cell = f"G{g}|{tid}|L{l}"
            approve_cells[cell] += 1
            approve_grade_tids[g].add(tid)
        
        print(f"Ячеек с APPROVE: {len(approve_cells)}")
        for g in sorted(approve_grade_tids.keys()):
            print(f"  Grade {g}: {len(approve_grade_tids[g])} themes в APPROVE")
        
        ready = sum(1 for v in approve_cells.values() if v == 5)
        partial = sum(1 for v in approve_cells.values() if 1 <= v <= 4)
        overfull = sum(1 for v in approve_cells.values() if v > 5)
        shortage = sum(max(0, 5 - v) for v in approve_cells.values())
        
        print(f"\nREADY (5): {ready}")
        print(f"PARTIAL (1-4): {partial}")
        print(f"OVERFULL: {overfull}")
        print(f"SHORTAGE: {shortage}")
        
        # Выводим PARTIAL ячейки
        print("\nPARTIAL ячейки (< 5 APPROVE):")
        partial_cells = {k: v for k, v in sorted(approve_cells.items()) if 1 <= v <= 4}
        for cell, cnt in sorted(partial_cells.items()):
            print(f"  {cell}: {cnt}/5")
        
        # Выводим EMPTY ячейки (нужно вычислить из полной сетки)
        print("\nEMPTY ячеек (нет APPROVE): нужно вычислить по полной таксономии")
    
    # Проверка дубликатов
    uids = [t.get('task_uid', '') for t in tasks]
    uid_dups = [u for u in uids if u and uids.count(u) > 1]
    if uid_dups:
        print(f"\nДубликаты task_uid: {set(uid_dups)}")

# ============== 5. Все файлы в max_fill_20260723_015316 ==============
print("\n" + "=" * 70)
print("5. ФАЙЛЫ РЕЗУЛЬТАТА")
print("=" * 70)

outdir = "l1_l3_generation/max_fill_20260723_015316"
if os.path.exists(outdir):
    for fname in sorted(os.listdir(outdir)):
        fpath = os.path.join(outdir, fname)
        if os.path.isfile(fpath):
            sz = os.path.getsize(fpath)
            sh = sha256f(fpath)
            print(f"  {fname:40s} {sz:>8} bytes  {sh}")

# ============== 6. Промты ==============
print("\n" + "=" * 70)
print("6. ПРОМТЫ")
print("=" * 70)

prompt_dir = "l1_l3_generation/prompts"
if os.path.exists(prompt_dir):
    for fname in sorted(os.listdir(prompt_dir)):
        fpath = os.path.join(prompt_dir, fname)
        if os.path.isfile(fpath):
            with open(fpath, 'r', encoding='utf-8') as f:
                content = f.read()
            sh = sha256f(fpath)
            print(f"  {fname:40s} {len(content):>6} chars  {sh}")

# ============== 7. Checkpoint ==============
print("\n" + "=" * 70)
print("7. CHECKPOINT")
print("=" * 70)

for cp in ["l1_l3_generation/l1_l3_generation_checkpoint.json", 
           "l1_l3_generation/l1_l3_checkpoint_20260723_015316.json",
           "fill_cell_holes_checkpoint.json"]:
    if os.path.exists(cp):
        sz = os.path.getsize(cp)
        print(f"{cp}: {sz} bytes, {sha256f(cp)}")

# ============== 8. README / manifest ==============
print("\n" + "=" * 70)
print("8. MANIFEST/REPORT")
print("=" * 70)

report = "l1_l3_generation/max_fill_20260723_015316/L1_L3_MAX_FILL_FINAL_REPORT.md"
if os.path.exists(report):
    with open(report, 'r', encoding='utf-8') as f:
        content = f.read()
    print(f"Report ({len(content)} chars):")
    print(content[:2000])

print("\n" + "=" * 70)
print("ДИАГНОСТИКА ЗАВЕРШЕНА")
print("=" * 70)
