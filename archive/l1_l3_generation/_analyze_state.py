import json, os

# 1. Проверка taxonomy_by_grade.json (корневой)
print("=== taxonomy_by_grade.json (КОРЕНЬ) ===")
with open('taxonomy_by_grade.json', 'r', encoding='utf-8') as f:
    d = json.load(f)
print("Ключи:", list(d.keys()))
if 'grade_theme_map' in d:
    gtm = d['grade_theme_map']
    total = 0
    for grade, themes in sorted(gtm.items()):
        print(f"  {grade}: {len(themes)} тем")
        total += len(themes)
    print(f"  Всего тем: {total}")
    print(f"  Ожидалось ячеек L1-L3: {total*3}")
elif 'grade_themes' in d:
    gt = d['grade_themes']
    total = sum(len(v) for v in gt.values())
    print(f"  Всего тем: {total}")
elif all(k.isdigit() or k.startswith('grade') for k in d.keys()):
    total = sum(len(v) for v in d.values())
    print(f"  Всего тем: {total}")
else:
    for k, v in d.items():
        if isinstance(v, dict):
            print(f"  {k}: {len(v)} подразделов")
        elif isinstance(v, list):
            print(f"  {k}: {len(v)} элементов")

# 2. Проверка l1_l3_generation/taxonomy_by_grade.json (копии)
print("\n=== l1_l3_generation/taxonomy_by_grade.json ===")
with open('l1_l3_generation/taxonomy_by_grade.json', 'r', encoding='utf-8') as f:
    d2 = json.load(f)
print("Ключи:", list(d2.keys()))
for k, v in d2.items():
    if isinstance(v, list):
        print(f"  {k}: {len(v)}")
    elif isinstance(v, dict):
        print(f"  {k}: {len(v)} ключей")
    else:
        print(f"  {k}: {v}")

# 3. Проверка результатов
print("\n=== max_fill_20260723_015316 ===")
outdir = 'l1_l3_generation/max_fill_20260723_015316'
if os.path.isdir(outdir):
    for fn in sorted(os.listdir(outdir)):
        fpath = os.path.join(outdir, fn)
        size = os.path.getsize(fpath)
        print(f"  {fn}: {size} bytes")
        if fn == 'FORMYLA_L1_L3_FINAL.jsonl':
            with open(fpath, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            print(f"    Строк: {len(lines)}")
        elif fn == 'l1_l3_grid_report.csv':
            with open(fpath, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            print(f"    Строк: {len(lines)}")
            if len(lines) > 1:
                print(f"    Последняя: {lines[-1].strip()}")
else:
    print("  Папка не найдена")

# 4. Проверка curated_bank
print("\n=== curated_bank_L1_L5_taxonomy_v2.json (первые 5 задач) ===")
with open('curated_bank_L1_L5_taxonomy_v2.json', 'r', encoding='utf-8') as f:
    bank = json.load(f)
print(f"  Всего задач: {len(bank)}")
grades = set()
levels = set()
for t in bank[:5]:
    print(f"  grade={t.get('grade','?')} level={t.get('level','?')} theme={t.get('theme','?')}")
