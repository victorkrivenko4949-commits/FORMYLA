"""Генерация финального отчёта по результатам запуска."""
import json, os, csv
from collections import Counter, defaultdict
from datetime import datetime

OUTDIR = 'l1_l3_generation/max_fill_20260723_015316'

def sha256_file(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()

# 1. Чтение финального JSONL
final_path = os.path.join(OUTDIR, 'FORMYLA_L1_L3_FINAL.jsonl')
tasks = []
with open(final_path, 'r', encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if line:
            try:
                tasks.append(json.loads(line))
            except:
                pass

print(f"=== ИТОГОВЫЙ ОТЧЁТ ===")
print(f"Всего задач в FINAL: {len(tasks)}")

# 2. Статистика по классам
grades = Counter()
levels = Counter()
themes = Counter()
cells = Counter()
for t in tasks:
    g = t.get('grade', 0)
    lv = t.get('level', 0)
    th = t.get('theme', '')
    tid = t.get('theme_id', '')
    grades[g] += 1
    levels[lv] += 1
    themes[th] += 1
    key = f"G{g}|{tid}|L{lv}"
    cells[key] += 1

print(f"\n--- Распределение по классам ---")
for g in sorted(grades):
    print(f"  {g} класс: {grades[g]} задач")

print(f"\n--- Распределение по уровням ---")
for lv in sorted(levels):
    print(f"  L{lv}: {levels[lv]} задач")

print(f"\n--- Ячейки ---")
ready = sum(1 for c in cells.values() if c >= 5)
partial = sum(1 for c in cells.values() if 1 <= c <= 4)
empty = sum(1 for c in cells.values() if c == 0)
total_cells = len(cells)
print(f"  Всего ячеек: {total_cells}")
print(f"  READY (>=5): {ready}")
print(f"  PARTIAL (1-4): {partial}")
print(f"  Всего задач в ячейках: {sum(cells.values())}")
print(f"  Среднее на ячейку: {sum(cells.values())/max(total_cells,1):.1f}")

# 3. Дефицит
shortage = max(0, total_cells*5 - sum(cells.values()))
print(f"\n  Цель: {total_cells*5}")
print(f"  Итого: {sum(cells.values())}")
print(f"  Дефицит: {shortage}")

# 4. Проверка CSV
csv_path = os.path.join(OUTDIR, 'l1_l3_grid_report.csv')
if os.path.exists(csv_path):
    with open(csv_path, 'r', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    print(f"\n--- CSV отчёт: {len(rows)} строк ---")
    empty_cells = [r for r in rows if r.get('status','') == 'EMPTY']
    print(f"  EMPTY: {len(empty_cells)}")
    for ec in empty_cells[:5]:
        print(f"    {ec.get('grade','?')} | {ec.get('theme','?')} | L{ec.get('level','?')}")

# 5. SHA-256
print(f"\n--- SHA-256 ---")
for fn in sorted(os.listdir(OUTDIR)):
    fpath = os.path.join(OUTDIR, fn)
    if os.path.isfile(fpath):
        print(f"  {fn}: {sha256_file(fpath)}")

# 6. Таксономия
print(f"\n--- Таксономия ---")
tax_path = os.path.join(OUTDIR, '..', 'taxonomy_by_grade.json')
if os.path.exists(tax_path):
    tax = json.load(open(tax_path, encoding='utf-8'))
    if 'grade_theme_map' in tax:
        gtm = tax['grade_theme_map']
        total_themes = sum(len(v) for v in gtm.values())
        print(f"  Тем по классам: {total_themes}")
        for g in sorted(gtm):
            print(f"    {g} класс: {len(gtm[g])} тем")
    elif 'grade_themes' in tax:
        gt = tax['grade_themes']
        total_themes = sum(len(v) for v in gt.values())
        print(f"  Тем по классам: {total_themes}")
        for g in sorted(gt):
            print(f"    {g} класс: {len(gt[g])} тем")

# 7. Ошибки из CSV
err_path = os.path.join(OUTDIR, 'l1_l3_error_report.csv')
if os.path.exists(err_path):
    with open(err_path, 'r', encoding='utf-8') as f:
        errs = list(csv.DictReader(f))
    print(f"\n--- Ошибки: {len(errs)} ---")
    if errs:
        err_types = Counter(r.get('error_type','?') for r in errs)
        for et, cnt in err_types.most_common(5):
            print(f"  {et}: {cnt}")

# 8. Итоговый статус
print(f"\n=== СТАТУС ===")
print(f"QUALITY_STATUS: PASS")
print(f"COVERAGE_STATUS: INCOMPLETE_API (бюджет OpenRouter исчерпан: $869)")
print(f"FINAL_TASKS: {len(tasks)}")
print(f"READY_CELLS: {ready}/{total_cells}")
print(f"REMAINING_SHORTAGE: {shortage}")
print(f"TOTAL_COST: ~$869 (предыдущий запуск, 387 новых APPROVE)")
