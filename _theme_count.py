import json
with open('data/theme_to_section.json','r',encoding='utf-8') as f:
    ts_data = json.load(f)

by_g = {}
for tid in ts_data:
    if not tid.startswith('G'): continue
    parts = tid.split('_')
    if len(parts) < 2: continue
    try: g = int(parts[0][1:])
    except: continue
    by_g.setdefault(g, set()).add(tid)

total = 0
print("=== Unique theme IDs per grade ===")
for g in sorted(by_g):
    n = len(by_g[g])
    total += n
    print(f"Grade {g}: {n}")
print(f"TOTAL: {total}")

by_g_sec = {}
for tid, sec in ts_data.items():
    if not tid.startswith('G'): continue
    parts = tid.split('_')
    if len(parts) < 2: continue
    try: g = int(parts[0][1:])
    except: continue
    by_g_sec.setdefault(g, set()).add(sec)
print()
for g in sorted(by_g_sec):
    print(f"Grade {g}: {len(by_g_sec[g])} sections")
