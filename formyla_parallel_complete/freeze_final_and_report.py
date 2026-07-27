import json, csv, re, glob, subprocess, sys
from pathlib import Path
from collections import Counter, defaultdict

FINAL = Path("formyla_final_rebuilt.json")
data = json.loads(FINAL.read_text(encoding="utf-8"))

def get_grade(t):
    for k in ["grade", "class", "class_level"]:
        if k in t:
            try:
                return int(t[k])
            except Exception:
                pass
    m = re.match(r"^(\d+)-", str(t.get("id","")))
    return int(m.group(1)) if m else None

def get_level(t):
    for k in ["difficulty", "level", "difficulty_level"]:
        if k in t:
            try:
                return int(t[k])
            except Exception:
                pass
    m = re.search(r"-L(\d+)", str(t.get("id","")))
    return int(m.group(1)) if m else None

def text_len(x):
    return len(str(x or "").strip())

rows = []
cnt = Counter()
short = []
empty = []
bad_encoding = []
dups = defaultdict(list)

for i,t in enumerate(data):
    tid = str(t.get("id",""))
    g = get_grade(t)
    l = get_level(t)
    cnt[(g,l)] += 1
    key = (str(t.get("task_text","")).strip(), str(t.get("answer","")).strip())
    dups[key].append(tid)
    if text_len(t.get("task_text")) < 20 or text_len(t.get("solution")) < 80:
        short.append(tid)
    if not str(t.get("task_text","")).strip() or not str(t.get("solution","")).strip():
        empty.append(tid)
    s = json.dumps(t, ensure_ascii=False)
    if any(x in s for x in ["╨", "╤", "Рџ", "Р°", "СЃ", "С‚"]):
        bad_encoding.append(tid)

Path("FINAL_RELEASE/checks").mkdir(parents=True, exist_ok=True)

with open("FINAL_RELEASE/checks/coverage_by_grade_level.csv","w",encoding="utf-8",newline="") as f:
    w = csv.writer(f)
    w.writerow(["grade","level","count"])
    for (g,l),c in sorted(cnt.items(), key=lambda x: (x[0][0] is None, x[0][0], x[0][1] is None, x[0][1])):
        w.writerow([g,l,c])

dup_rows = [(k,v) for k,v in dups.items() if len(v) > 1 and k[0]]
with open("FINAL_RELEASE/checks/quality_quick_report.json","w",encoding="utf-8") as f:
    json.dump({
        "total": len(data),
        "grade_level_cells": len(cnt),
        "short_or_tiny_solution": len(short),
        "empty_required": len(empty),
        "bad_encoding_markers": len(bad_encoding),
        "duplicate_text_answer_pairs": len(dup_rows),
        "sample_short_ids": short[:50],
        "sample_empty_ids": empty[:50],
        "sample_bad_encoding_ids": bad_encoding[:50],
        "sample_duplicate_groups": [{"ids": v[:10], "count": len(v)} for k,v in dup_rows[:30]]
    }, f, ensure_ascii=False, indent=2)

print("FINAL_TOTAL", len(data))
print("CELLS", len(cnt))
print("SHORT_OR_TINY", len(short))
print("EMPTY_REQUIRED", len(empty))
print("BAD_ENCODING", len(bad_encoding))
print("DUP_TEXT_ANSWER", len(dup_rows))
print("REPORT", "FINAL_RELEASE/checks/quality_quick_report.json")
print("COVERAGE", "FINAL_RELEASE/checks/coverage_by_grade_level.csv")
