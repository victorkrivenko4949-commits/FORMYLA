import json

# Проверка таксономии
with open('l1_l3_generation/taxonomy_by_grade.json', 'r', encoding='utf-8') as f:
    d = json.load(f)

print("Классы:", list(d.keys()))
total = 0
for k, v in d.items():
    print(f"  {k}: {len(v)} тем")
    total += len(v)
print(f"Всего тем: {total}")
print()

# Проверка результатов
import os
outdir = 'l1_l3_generation/max_fill_20260723_015316'
for fn in sorted(os.listdir(outdir)):
    fpath = os.path.join(outdir, fn)
    size = os.path.getsize(fpath)
    print(f"  {fn}: {size} bytes")
