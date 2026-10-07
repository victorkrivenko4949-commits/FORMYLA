#!/usr/bin/env python
"""Diagnose why topic mapping returns zero matches."""
import json, os, sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BANK_PATH = os.path.join(SCRIPT_DIR, "..", "curated_bank_L1_L5_fixed.json")
TAXONOMY_PATH = os.path.join(SCRIPT_DIR, "..", "taxonomy_by_grade.json")
OUT_PATH = os.path.join(SCRIPT_DIR, "_topic_mapping_diag.json")

# Load bank
with open(BANK_PATH, 'r', encoding='utf-8-sig') as f:
    bank = json.load(f)

# Load taxonomy
with open(TAXONOMY_PATH, 'r', encoding='utf-8-sig') as f:
    taxonomy = json.load(f)

# Build topic_name_to_id map (same as _analyze_bank_schema.py)
topic_name_to_id = {}
for grade_str, grade_data in taxonomy.get("grades", {}).items():
    grade = int(grade_str)
    for theme in grade_data.get("themes", []):
        tid = theme["id"]
        tname = theme["name"]
        topic_name_to_id[(grade, tname)] = tid

# Check first 5 bank records
results = []
for i, r in enumerate(bank[:5]):
    g = r.get('grade')
    t = r.get('topic')
    match = topic_name_to_id.get((g, t))
    results.append({
        'index': i,
        'original_id': r.get('original_id'),
        'grade': g,
        'grade_type': type(g).__name__,
        'topic': t,
        'topic_type': type(t).__name__,
        'topic_repr': repr(t),
        'topic_codepoints': [ord(c) for c in (t or '')