import json, re, csv
from pathlib import Path
from collections import Counter

p = Path("formyla_final_rebuilt.json")
data = json.loads(p.read_text(encoding="utf-8"))

def level(t):
    for k in ["difficulty","level","difficulty_level"]:
        if k in t:
            try:
                return int(t[k])
            except Exception:
                pass
    m = re.search(r"-L(\d+)", str(t.get("id","")))
    return int(m.group(1)) if m else None

def grade(t):
    for k in ["grade","class","class_level"]:
        if k in t:
            try:
                return int(t[k])
            except Exception:
                pass
    m = re.match(r"^(\d+)-", str(t.get("id","")))
    return int(m.group(1)) if m else None

def topic(t):
    return str(t.get("theme") or t.get("topic") or t.get("method_code") or t.get("method") or "?")

rows = []
for t in data:
    l = level(t)
    sol = str(t.get("solution","") or "")
    if l and l >= 6 and len(sol.strip()) < 700:
        rows.append({
            "id": t.get("id"),
            "grade": grade(t),
            "level": l,
            "solution_len": len(sol.strip()),
            "topic": topic(t),
            "task_text": str(t.get("task_text",""))[:240]
        })

rows.sort(key=lambda r: (r["level"], r["solution_len"], str(r["id"])))
Path("FINAL_RELEASE/checks").mkdir(parents=True, exist_ok=True)
Path("FINAL_RELEASE/checks/short_L6_L8_sorted.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

with open("FINAL_RELEASE/checks/short_L6_L8_sorted.csv","w",encoding="utf-8",newline="") as f:
    w = csv.DictWriter(f, fieldnames=["id","grade","level","solution_len","topic","task_text"])
    w.writeheader()
    w.writerows(rows)

cnt = Counter((r["grade"], r["level"]) for r in rows)
print("SHORT_L6_L8", len(rows))
print("TOP_CELLS")
for (g,l),c in cnt.most_common(20):
    print(g, l, c)
print("FILES")
print("FINAL_RELEASE/checks/short_L6_L8_sorted.json")
print("FINAL_RELEASE/checks/short_L6_L8_sorted.csv")
