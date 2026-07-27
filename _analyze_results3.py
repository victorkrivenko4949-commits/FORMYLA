#!/usr/bin/env python
"""Detailed analysis of audit results for regeneration planning."""
import json

with open("audit_675_full_results.json", "r", encoding="utf-8") as f:
    data = json.load(f)

results = data["results"]
summary = data["summary"]

print("=" * 70)
print("AUDIT SUMMARY")
print("=" * 70)
print(f"  Total tasks:       {summary['total']}")
print(f"  PASSED:            {summary['passed']} ({100*summary['passed']/summary['total']:.1f}%)")
print(f"  MINOR:             {summary['minor']} ({100*summary['minor']/summary['total']:.1f}%)")
print(f"  FAILED:            {summary['failed_audit']} ({100*summary['failed_audit']/summary['total']:.1f}%)")
print(f"  API failures:      {summary['api_failures']}")
print()
print(f"  Level mismatches:  {summary['level_mismatches']}")
print(f"  Class mismatches:  {summary['class_mismatches']}")
print(f"  Topic mismatches:  {summary['topic_mismatches']}")
print(f"  Condition issues:  {summary['condition_issues']}")

# Breakdown by pipeline_verdict
print()
print("=" * 70)
print("PIPELINE VERDICT BREAKDOWN")
print("=" * 70)
pv_counts = {}
for r in results:
    pv = r.get("pipeline_verdict") or "UNKNOWN"
    pv_counts[pv] = pv_counts.get(pv, 0) + 1
for pv, count in sorted(pv_counts.items(), key=lambda x: str(x[0])):
    print(f"  {pv:20s}: {count:4d} ({100*count/len(results):.1f}%)")

# Cross-tab: pipeline_verdict vs audit overall
print()
print("=" * 70)
print("PIPELINE VERDICT vs AUDIT OVERALL")
print("=" * 70)
cross = {}
for r in results:
    pv = r.get("pipeline_verdict", "UNKNOWN")
    ao = r.get("audit_result", {}).get("overall", "N/A")
    cross.setdefault(pv, {}).setdefault(ao, 0)
    cross[pv][ao] += 1

for pv in sorted(cross.keys()):
    print(f"  {pv}:")
    for ao in sorted(cross[pv].keys()):
        print(f"      audit={ao:6s}: {cross[pv][ao]:4d}")

# List all failed task indices
print()
print("=" * 70)
print("FAILED TASK INDICES (need regeneration)")
print("=" * 70)
failed_indices = []
for r in results:
    if r.get("audit_result", {}).get("overall") == "FAIL":
        failed_indices.append(r["task_index"])

print(f"Total failed: {len(failed_indices)}")
print(f"Indices: {failed_indices}")

# Show failed tasks by type of issue
print()
print("=" * 70)
print("FAILED TASKS - ISSUE BREAKDOWN")
print("=" * 70)
issue_counts = {"level_only": 0, "class_only": 0, "topic_only": 0, "condition_only": 0,
                "level+class": 0, "level+topic": 0, "class+topic": 0,
                "level+class+topic": 0, "other": 0}

for idx in failed_indices:
    r = next(x for x in results if x["task_index"] == idx)
    ar = r.get("audit_result", {})
    issues = []
    if ar.get("level_match", {}).get("verdict") in ("MAJOR", "FAIL"):
        issues.append("level")
    if ar.get("class_match", {}).get("verdict") in ("MAJOR", "FAIL"):
        issues.append("class")
    if ar.get("topic_match", {}).get("verdict") in ("MAJOR", "FAIL"):
        issues.append("topic")
    if ar.get("condition_correctness", {}).get("verdict") in ("MAJOR", "FAIL"):
        issues.append("condition")
    
    key = "+".join(sorted(issues)) if issues else "other"
    if key not in issue_counts:
        issue_counts[key] = 0
    issue_counts[key] += 1

for k, v in sorted(issue_counts.items(), key=lambda x: -x[1]):
    if v > 0:
        print(f"  {k:30s}: {v:4d}")

# Save failed task indices to a file for regeneration
with open("_failed_audit_indices.json", "w", encoding="utf-8") as f:
    json.dump({"failed_indices": failed_indices, "count": len(failed_indices), 
               "summary": summary}, f, ensure_ascii=False, indent=2)
print(f"\nFailed indices saved to _failed_audit_indices.json")
