import json, re
from pathlib import Path
from collections import defaultdict

p = Path("formyla_final_rebuilt.json")
data = json.loads(p.read_text(encoding="utf-8"))

def norm(s):
    s = str(s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s

def level(t):
    for k in ["difficulty", "level", "difficulty_level"]:
        if k in t:
            try:
                return int(t[k])
            except Exception:
                pass
    m = re.search(r"-L(\d+)", str(t.get("id","")))
    return int(m.group(1)) if m else 99

def grade(t):
    for k in ["grade", "class", "class_level"]:
        if k in t:
            try:
                return int(t[k])
            except Exception:
                pass
    m = re.match(r"^(\d+)-", str(t.get("id","")))
    return int(m.group(1)) if m else 99

def is_fill(t):
    return "-fill-" in str(t.get("id",""))

def keep_score(t):
    tid = str(t.get("id",""))
    return (
        level(t),
        1 if is_fill(t) else 0,
        grade(t),
        len(str(t.get("solution","") or "")) * -1,
        tid
    )

groups = defaultdict(list)
for idx, t in enumerate(data):
    key = (norm(t.get("task_text")), norm(t.get("answer") or t.get("correct_answer")))
    if key[0]:
        groups[key].append((idx, t))
    else:
        groups[(f"__empty__{idx}", "")].append((idx, t))

keep_idx = set()
removed = []
dup_groups = []

for key, arr in groups.items():
    if len(arr) == 1:
        keep_idx.add(arr[0][0])
        continue

    chosen_idx, chosen_task = sorted(arr, key=lambda it: keep_score(it[1]))[0]
    keep_idx.add(chosen_idx)

    group = {
        "kept_id": chosen_task.get("id"),
        "removed_ids": [],
        "all_ids": [x.get("id") for _, x in arr],
        "answer": key[1],
        "task_text": key[0][:500]
    }

    for idx, t in arr:
        if idx != chosen_idx:
            removed.append({
                "id": t.get("id"),
                "grade": grade(t),
                "level": level(t),
                "kept_id": chosen_task.get("id"),
                "task_text": key[0][:300],
                "answer": key[1][:200]
            })
            group["removed_ids"].append(t.get("id"))

    dup_groups.append(group)

clean = [t for i, t in enumerate(data) if i in keep_idx]

Path("FINAL_RELEASE/checks").mkdir(parents=True, exist_ok=True)
Path("FINAL_RELEASE/checks/removed_exact_duplicate_ids.json").write_text(
    json.dumps(removed, ensure_ascii=False, indent=2),
    encoding="utf-8"
)
Path("FINAL_RELEASE/checks/duplicate_groups_kept_removed.json").write_text(
    json.dumps(dup_groups, ensure_ascii=False, indent=2),
    encoding="utf-8"
)

p.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")

print("BEFORE", len(data))
print("AFTER", len(clean))
print("REMOVED", len(removed))
print("DUP_GROUPS", len(dup_groups))
print("REMOVED_FILE", "FINAL_RELEASE/checks/removed_exact_duplicate_ids.json")
print("GROUPS_FILE", "FINAL_RELEASE/checks/duplicate_groups_kept_removed.json")
