import json, os, sys, glob
from collections import defaultdict
base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, base)
print("=" * 60)
print("ADAPTIVE TEST - TASKS BY GRADE")
print("=" * 60)
ad = os.path.join(base, "adaptive_data")
bg = defaultdict(int)
bt = defaultdict(int)
tot = 0
for f in sorted(glob.glob(os.path.join(ad, "*.json"))):
    fn = os.path.basename(f)
    with open(f, "r", encoding="utf-8") as fh:
        tasks = json.load(fh)
    g2 = defaultdict(int)
    for t in tasks:
        g = t.get("grade", "?")
        bg[g] += 1
        g2[g] += 1
        bt[t.get("subject", "?")] += 1
    tot += len(tasks)
    print(f"  {fn}: {len(tasks)} tasks | grades: {dict(sorted(g2.items()))}")
print(f"\nTOTAL adaptive_data: {tot}")
print(f"\nBy grade (adaptive_data):")
for g in sorted(bg.keys()):
    print(f"  Grade {g}: {bg[g]} tasks")
print(f"\nBy topic (adaptive_data):")
for t in sorted(bt.keys()):
    print(f"  {t}: {bt[t]} tasks")
print("\n" + "=" * 60)
print("PROBLEMS_DB (problems.py)")
print("=" * 60)
from problems import PROBLEMS_DB
bg2 = defaultdict(int)
bt2 = defaultdict(int)
for p in PROBLEMS_DB:
    bg2[p.get("grade", "?")] += 1
    bt2[p.get("subject", "?")] += 1
print(f"Total: {len(PROBLEMS_DB)}")
print(f"\nBy grade:")
for g in sorted(bg2.keys()):
    print(f"  Grade {g}: {bg2[g]} tasks")
print(f"\nBy topic:")
for t in sorted(bt2.keys()):
    print(f"  {t}: {bt2[t]} tasks")
