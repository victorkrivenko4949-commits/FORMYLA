#!/usr/bin/env python3
"""Complete generator for _step14_11_quality_not_weakened.py"""
import os, json, re, sys
from collections import Counter
from datetime import datetime, timezone

RECON = "l4_l5_finalization/taxonomy_reconstruction"

def w(out, s=""):
    out.append(s)

def wb(out):
    out.append("")

def write_part1(out):
    w(out, '# ============================================================')
    w(out, '# PART 1: Canonical Structure Integrity (checks 1-7)')
    w(out, '# ============================================================')
    wb(out)
    w(out, 'def check_canonical_integrity(canonical, checks):')
    w(out, '    """Validate canonical taxonomy structural integrity."""')
    w(out, '    print("\\n--- PART 1: Canonical Structure Integrity ---")')
    wb(out)
    w(out, '    topics = canonical.get("topics", {})')
    w(out, '    cells = canonical.get("canonical_cells", [])')
    wb(out)
    w(out, '    # Check 1: Total canonical cells == 558')
    w(out, '    cell_count = len(cells)')
    w(out, '    check_1 = (cell_count == EXPECTED_CELL_COUNT)')
    w(out, '    detail_1 = (')
    w(out, '        f"Expected {EXPECTED_CELL_COUNT}, got {cell_count}"')
    w(out, '        if not check_1 else f"{cell_count} cells"')
    w(out, '    )')
    w(out, '    record(checks, "1. Total canonical cells == 558", check_1, detail_1)')
    wb(out)
    w(out, '    # Check 2: All 41 topic_ids T001-T041 present')
    w(out, '    topic_ids_present = set(topics.keys())')
    w(out, '    check_2 = (topic_ids_present == VALID_TOPIC_IDS)')
    w(out, '    missing_ids = VALID_TOPIC_IDS - topic_ids_present')
    w(out, '    extra_ids = topic_ids_present - VALID_TOPIC_IDS')
    w(out, '    detail_2_parts = []')
    w(out, '    if missing_ids:')
    w(out, '        detail_2_parts.append(f"Missing: {sorted(missing_ids)}")')
    w(out, '    if extra_ids:')
    w(out, '        detail_2_parts.append(f"Extra: {sorted(extra_ids)}")')
    w(out, '    if not detail_2_parts:')
    w(out, '        detail_2 = f"All {EXPECTED_TOPIC_COUNT} topics present (T001-T041)"')
    w(out, '    else:')
    w(out, '        detail_2 = "; ".join(detail_2_parts)')
    w(out, '    record(checks, "2. All 41 topic_ids (T001-T041) present", check_2, detail_2)')
    wb(out)
    w(out, '    # Check 3: 123 subtopics present (3 per topic)')
    w(out, '    total_subtopics = sum(len(t.get("subtopics", [])) for t in topics.values())')
    w(out, '    check_3 = (total_subtopics == EXPECTED_SUBTOPIC_COUNT)')
    w(out, '    detail_3 = (')
    w(out, '        f"Expected {EXPECTED_SUBTOPIC_COUNT} subtopics, got {total_subtopics}"')
    w(out, '        if not check_3 else f"{total_subtopics} subtopics"')
    w(out, '    )')
    w(out, '    record(checks, "3. 123 subtopics present (3 per topic)", check_3, detail_3)')
    wb(out)
    w(out, '    # Check 4: Grade distribution matches expected')
    w(out, '    grade_counts = Counter()')
    w(out, '    for cell in cells:')
    w(out, '        g = str(cell.get("grade", ""))')
    w(out, '        grade_counts[g] += 1')
    w(out, '    grade_mismatches = []')
    w(out, '    for g, expected