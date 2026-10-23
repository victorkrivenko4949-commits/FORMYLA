import json, re, csv
from pathlib import Path
from collections import defaultdict, Counter

p = Path("formyla_final_rebuilt.json")
data = json.loads(p.read_text(encoding="utf-8"))

def grade(t):
    for k in ["grade", "class", "class_level"]:
        if k in t:
            try: return int(t[k])
            except: pass
    m = re.match(r"^(\d+)-", str(t.get("id","")))
    return int(m.group(1)) if m else None

def level(t):
    for k in ["difficulty", "level", "difficulty_level"]:
        if k in t:
            try: return int(t[k])
            except: pass
    m = re.search(r"-L(\d+)", str(t.get("id","")))
    return int(m.group(1)) if m else None

def norm(s):
    s = str(s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s

dups = defaultdict(list)
short_hi = []
by_cell = Counter()

for t in data:
    g, l = grade(t), level(t)
    by_cell[(g,l)] += 1
    key = (norm(t.get("task_text")), norm(t.get("answer") or t.get("correct_answer")))
    if key[0]:
        dups[key].append(t)
    if l and l >= 6 and len(norm(t.get("solution"))) < 700:
        short_hi.append({
            "id": t.get("id"),
            "grade": g,
            "level": l,
            "solution_len": len(norm(t.get("solution"))),
            "task_text": norm(t.get("task_text"))[:220]
        })

dup_groups = []
for (txt, ans), arr in dups.items():
    if len(arr) > 1:
        dup_groups.append({
            "count": len(arr),
            "ids": [x.get("id") for x in arr],
            "grades": [grade(x) for x in arr],
            "levels": [level(x) for x in arr],
            "answer": ans[:120],
            "task_text": txt[:350]
        })

dup_groups.sort(key=lambda x: (-x["count"], x["ids"]))
short_hi.sort(key=lambda x: (x["level"], x["solution_len"], x["id"] or ""))

Path("FINAL_RELEASE/checks").mkdir(parents=True, exist_ok=True)

Path("FINAL_RELEASE/checks/exact_duplicates_full.json").write_text(
    json.dumps(dup_groups, ensure_ascii=False, indent=2),
    encoding="utf-8"
)

Path("FINAL_RELEASE/checks/short_solutions_L6_L8.json").write_text(
    json.dumps(short_hi, ensure_ascii=False, indent=2),
    encoding="utf-8"
)

with open("FINAL_RELEASE/checks/cell_counts.csv","w",encoding="utf-8",newline="") as f:
    w = csv.writer(f)
    w.writerow(["grade","level","count"])
    for (g,l),c in sorted(by_cell.items()):
        w.writerow([g,l,c])

print("TOTAL", len(data))
print("DUP_GROUPS", len(dup_groups))
print("DUP_EXTRA_TASKS", sum(x["count"]-1 for x in dup_groups))
print("SHORT_L6_L8", len(short_hi))
print("FILES:")
print("FINAL_RELEASE/checks/exact_duplicates_full.json")
print("FINAL_RELEASE/checks/short_solutions_L6_L8.json")
print("FINAL_RELEASE/checks/cell_counts.csv")
