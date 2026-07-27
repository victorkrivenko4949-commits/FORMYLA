#!/usr/bin/env python
"""Analyze audit results from audit_675_full_results.json."""
import json

with open("audit_675_full_results.json", "r", encoding="utf-8") as f:
    data = json.load(f)

print("Top-level keys:", list(data.keys()))
print()

results = data.get("results", None)
tasks = data.get("tasks", None)

if results is None and isinstance(data, list):
    # maybe it's a flat list
    items = list(enumerate(data))
elif isinstance(results, list):
    items = list(enumerate(results))
elif isinstance(results, dict):
    items = list(results.items())
elif isinstance(tasks, list):
    items = list(enumerate(tasks))
else:
    items = []

print(f"Total items: {len(items)}")
print()

overall_counts = {"PASS": 0, "FAIL": 0, "MINOR": 0, "N/A": 0}
failed_indices = []
minor_indices = []

for idx, item in items:
    if isinstance(item, dict):
        verdict = item.get("overall", item.get("verdict", ""))
        if not verdict:
            verdict = item.get("result", item.get("status", "N/A"))
        if verdict in overall_counts:
            overall_counts[verdict] = overall_counts[verdict] + 1
        else:
            overall_counts[verdict] = 1
        if verdict == "FAIL":
            failed_indices.append(item.get("task_index", idx))
        elif verdict == "MINOR":
            minor_indices.append(item.get("task_index", idx))

print("=" * 60)
print("OVERALL AUDIT RESULTS")
print("=" * 60)
for k, v in sorted(overall_counts.items()):
    pct = 100.0 * v / len(items) if len(items) > 0 else 0
    print(f"  {k:8s}: {v:4d} ({pct:.1f}%)")

print()
print(f"Failed tasks ({len(failed_indices)}): {failed_indices}")
print(f"Minor tasks ({len(minor_indices)}): {minor_indices}")

# Also try to get per-criterion breakdown
print()
print("=" * 60)
print("PER-LEVEL BREAKDOWN")
print("=" * 60)
level_counts = {}
for idx, item in items:
    if isinstance(item, dict):
        level = item.get("level", None)
        if not level and isinstance(item, dict):
            for k in ["expected_level", "rubric_level", "task_level"]:
                level = item.get(k, level)
        verdict = item.get("overall", item.get("verdict", ""))
        if level:
            level_counts.setdefault(level, {"PASS": 0, "FAIL": 0, "MINOR": 0})
            if verdict in level_counts[level]:
                level_counts[level][verdict] += 1

for level in sorted(level_counts.keys()):
    counts = level_counts[level]
    print(f"  Level {level}: PASS={counts['PASS']} FAIL={counts['FAIL']} MINOR={counts['MINOR']}")

# Show a sample failed task
if failed_indices:
    print()
    print("=" * 60)
    print("SAMPLE FAILED TASK DETAIL")
    print("=" * 60)
    for idx, item in items:
        item_idx = item.get("task_index", idx) if isinstance(item, dict) else idx
        if item_idx == failed_indices[0]:
            if isinstance(item, dict):
                print(json.dumps(item, ensure_ascii=False, indent=2)[:3000])
            break
