#!/usr/bin/env python3
"""Fix all BASE_DIR -> PIPELINE_DIR references for pipeline files."""

import os, re

SCRIPT = r"l4_l5_finalization\taxonomy_reconstruction\_taxonomy_reconstruct.py"

with open(SCRIPT, "r", encoding="utf-8") as f:
    content = f.read()

# Replace pipeline file BASE_DIR refs with PIPELINE_DIR
pipeline_patterns = [
    ('os.path.join(BASE_DIR, "stage3_checkpoint.json")', 'os.path.join(PIPELINE_DIR, "stage3_checkpoint.json")'),
    ('os.path.join(BASE_DIR, "stage3_audit_results.json")', 'os.path.join(PIPELINE_DIR, "stage3_audit_results.json")'),
    ('os.path.join(BASE_DIR, "stage4_classification.json")', 'os.path.join(PIPELINE_DIR, "stage4_classification.json")'),
    ('os.path.join(BASE_DIR, "stage45_reclassification.json")', 'os.path.join(PIPELINE_DIR, "stage45_reclassification.json")'),
    ('os.path.join(BASE_DIR, "stage5_fix_results.json")', 'os.path.join(PIPELINE_DIR, "stage5_fix_results.json")'),
    ('os.path.join(BASE_DIR, "stage5_fixes")', 'os.path.join(PIPELINE_DIR, "stage5_fixes")'),
    ('os.path.join(BASE_DIR, "stage45_forensics")', 'os.path.join(PIPELINE_DIR, "stage45_forensics")'),
    ('os.path.join(BASE_DIR, "reconciliation_report.json")', 'os.path.join(PIPELINE_DIR, "reconciliation_report.json")'),
    ('os.path.join(BASE_DIR, "stage6_candidates.json")', 'os.path.join(PIPELINE_DIR, "stage6_candidates.json")'),
    ('os.path.join(BASE_DIR, "checkpoints_failed_chat_run"', 'os.path.join(PIPELINE_DIR, "checkpoints_failed_chat_run"'),
    ('os.path.join(BASE_DIR, "stage6_candidate_selection.jsonl")', 'os.path.join(PIPELINE_DIR, "stage6_candidate_selection.jsonl")'),
    ('os.path.join(BASE_DIR, "stage7_checkpoint.json")', 'os.path.join(PIPELINE_DIR, "stage7_checkpoint.json")'),
    ('os.path.join(BASE_DIR, "corrected_slot_report.json")', 'os.path.join(PIPELINE_DIR, "corrected_slot_report.json")'),
    ('src = os.path.join(BASE_DIR, fname)', 'src = os.path.join(PIPELINE_DIR, fname)'),
]

count = 0
for old, new in pipeline_patterns:
    occ = content.count(old)
    if occ > 0:
        content = content.replace(old, new)
        count += occ
        print(f"  Replaced {occ}x: {old}")

print(f"\nTotal BASE_DIR->PIPELINE_DIR replacements: {count}")

# Fix Unicode arrow in print statement
old_arrow = "\u2192"  # ->
new_arrow = "->"
if old_arrow in content:
    content = content.replace(old_arrow, new_arrow)
    print(f"  Replaced Unicode arrow with ->")

# Verify remaining are only root-level
remaining = re.findall(r'os\.path\.join\(BASE_DIR,\s*[^)]+\)', content)
print(f"\nRemaining BASE_DIR refs (should be root-level only):")
for ref in remaining:
    print(f"  {ref}")

with open(SCRIPT, "w", encoding="utf-8") as f:
    f.write(content)

print(f"\nDone! File written.")
