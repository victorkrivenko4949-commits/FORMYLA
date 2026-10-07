#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Investigate mapping between classification task_ids and bank import_keys.
The classification files use task_id (e.g., 'c5307bfa5ccd'), while the bank
uses import_key (e.g., '933db08a1255f136'). This script builds the mapping
by matching on (cell_key + normalized statement) between stage3 audit
results and bank entries.
"""

import json
import hashlib
import re
import os
from typing import Dict, List, Optional, Tuple, Set

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BANK_PATH = os.path.join(BASE_DIR, "..", "l4_l5_fill_output", "curated_bank_L4_L5_filled.json")
STAGE3_PATH = os.path.join(BASE_DIR, "stage3_audit_results.json")
STAGE4_PATH = os.path.join(BASE_DIR, "stage4_classification.json")
STAGE45_PATH = os.path.join(BASE_DIR, "stage45_reclassification.json")
STAGE5_PATH = os.path.join(BASE_DIR, "stage5_fix_results.json")

def load_json(path: str, desc: str = "file") -> any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def normalize_text(text: str) -> str:
    """Normalize text for comparison: strip whitespace, normalize LaTeX."""
    if not text:
        return ""
    text = text.strip()
    # Normalize LaTeX: remove redundant spaces within \( \)
    text = re.sub(r'\\\(\s+', r'\(', text)
    text = re.sub(r'\s+\\\)', r'\)', text)
    text = re.sub(r'\\\[\s+', r'\[', text)
    text = re.sub(r'\s+\\\]', r'\]', text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def normalize_statement_for_hash(text: str) -> str:
    """Normalize statement for hash matching (further collapse)."""
    text = normalize_text(text)
    # Remove LaTeX markers for more robust matching
    text = text.replace('\\(', '').replace('\\)', '')
    text = text.replace('\\[', '').replace('\\]', '')
    # Remove extra spaces after punctuation
    text = re.sub(r'\s+([.,;:!?])', r'\1', text)
    text = re.sub(r'(\d)\s+(\d)', r'\1 \2', text)
    # Lowercase
    text = text.lower().strip()
    return text

def compute_fingerprint(text: str) -> str:
    """Compute a short fingerprint hash of normalized text."""
    norm = normalize_statement_for_hash(text)
    return hashlib.md5(norm.encode('utf-8')).hexdigest()[:12]

def extract_classification_ids(stage4: Dict, stage45: Dict, stage5: Dict) -> Dict[str, str]:
    """Extract the final classification for each task_id across all 3 files.
    Returns {task_id: final_category} where final_category is one of KEEP, FIXED, REPLACE.
    """
    # Stage 4: initial classification
    task_cat: Dict[str, str] = {}
    for item in stage4.get("classifications", []):
        tid = item.get("task_id", "")
        cat = item.get("category", "")
        if tid:
            task_cat[tid] = cat  # stage4 category
    
    # Stage 45: reclassification overrides stage4
    for item in stage45.get("reclassifications", []):
        tid = item.get("task_id", "")
        new_cat = item.get("new_category", "")
        if tid and new_cat:
            task_cat[tid] = new_cat  # stage45 overrides
    
    # Stage 5: fix outcomes - if "replace", then REPLACE; if "fixed", then FIXED
    for item in stage5.get("results", []):
        tid = item.get("task_id", "")
        outcome = item.get("outcome", "")
        if tid:
            if outcome == "replace":
                task_cat[tid] = "REPLACE"
            elif outcome == "fixed":
                task_cat[tid] = "FIXED"
    
    return task_cat

def build_stage3_index(stage3: List[Dict]) -> Dict[str, Dict]:
    """Build index of stage3 entries by task_id."""
    idx: Dict[str, Dict] = {}
    for entry in stage3:
        tid = entry.get("task_id", "")
        if tid:
            idx[tid] = entry
    return idx

def build_bank_index_by_cell_statement(bank: List[Dict]) -> Dict[str, List[Dict]]:
    """Build index of bank entries by cell_key, for matching."""
    idx: Dict[str, List[Dict]] = {}
    for task in bank:
        ck = task.get("cell_key", "")
        if ck:
            idx.setdefault(ck, []).append(task)
    return idx

def match_task_to_bank(stage3_entry: Dict, bank_by_cell: Dict[str, List[Dict]]) -> Optional[Dict]:
    """Match a stage3 audit entry to a bank entry by (cell_key + statement)."""
    cell_key = stage3_entry.get("cell_key", "")
    statement = stage3_entry.get("statement", "")
    
    if not cell_key or not statement:
        return None
    
    bank_tasks = bank_by_cell.get(cell_key, [])
    if not bank_tasks:
        return None
    
    # Compute fingerprint of stage3 statement
    stage3_fp = compute_fingerprint(statement)
    
    # Find matching bank task by fingerprint
    for bt in bank_tasks:
        bt_stmt = bt.get("statement", "")
        bt_fp = compute_fingerprint(bt_stmt)
        if bt_fp == stage3_fp:
            return bt
    
    # If fingerprint fails, try normalized text exact match
    stage3_norm = normalize_statement_for_hash(statement)
    for bt in bank_tasks:
        bt_stmt = bt.get("statement", "")
        bt_norm = normalize_statement_for_hash(bt_stmt)
        if bt_norm == stage3_norm:
            return bt
    
    # If still no match, try substring (first 100 chars)
    stage3_prefix = normalize_statement_for_hash(statement)[:100]
    for bt in bank_tasks:
        bt_stmt = bt.get("statement", "")
        bt_prefix = normalize_statement_for_hash(bt_stmt)[:100]
        if bt_prefix and stage3_prefix and bt_prefix == stage3_prefix:
            return bt
    
    return None

def main():
    print("=" * 70)
    print("INVESTIGATION: task_id -> import_key MAPPING")
    print("=" * 70)
    
    # Load all data
    print("\n[1] Loading data files...")
    bank = load_json(BANK_PATH, "bank")
    stage3 = load_json(STAGE3_PATH, "stage3 audit")
    stage4 = load_json(STAGE4_PATH, "stage4 classification")
    stage45 = load_json(STAGE45_PATH, "stage45 reclassification")
    stage5 = load_json(STAGE5_PATH, "stage5 fix results")
    
    print(f"    Bank entries: {len(bank)}")
    print(f"    Stage3 audits: {len(stage3)}")
    print(f"    Stage4 classifications: {len(stage4.get('classifications', []))}")
    print(f"    Stage45 reclassifications: {len(stage45.get('reclassifications', []))}")
    print(f"    Stage5 fix results: {len(stage5.get('results', []))}")
    
    # Build classification mapping
    print("\n[2] Extracting final classifications...")
    task_cats = extract_classification_ids(stage4, stage45, stage5)
    print(f"    Total unique classified task_ids: {len(task_cats)}")
    
    keep_ids = {tid for tid, cat in task_cats.items() if cat == "KEEP"}
    fixed_ids = {tid for tid, cat in task_cats.items() if cat == "FIXED"}
    replace_ids = {tid for tid, cat in task_cats.items() if cat == "REPLACE"}
    print(f"    KEEP: {len(keep_ids)}, FIXED: {len(fixed_ids)}, REPLACE: {len(replace_ids)}")
    print(f"    Sum: {len(keep_ids)+len(fixed_ids)+len(replace_ids)} (expect 63)")
    
    # Build stage3 index
    print("\n[3] Building stage3 index...")
    stage3_idx = build_stage3_index(stage3)
    print(f"    Stage3 entries indexed: {len(stage3_idx)}")
    
    # Build bank index by cell_key
    print("\n[4] Building bank index by cell_key...")
    bank_by_cell = build_bank_index_by_cell_statement(bank)
    print(f"    Unique cell_keys in bank: {len(bank_by_cell)}")
    
    # Match each classified task_id to bank entry
    print("\n[5] Matching classified tasks to bank entries...")
    task_to_import: Dict[str, str] = {}
    unmatched: List[str] = []
    match_methods: Dict[str, int] = {"fingerprint": 0, "normalized_exact": 0, "prefix_100": 0, "failed": 0}
    
    for tid, cat in sorted(task_cats.items()):
        stage3_entry = stage3_idx.get(tid)
        if not stage3_entry:
            unmatched.append(f"{tid} ({cat}): NOT FOUND in stage3 audit")
            match_methods["failed"] += 1
            continue
        
        matched_bank = match_task_to_bank(stage3_entry, bank_by_cell)
        if matched_bank:
            import_key = matched_bank.get("import_key", "")
            if import_key:
                task_to_import[tid] = import_key
                # Determine which method worked
                cell_key = stage3_entry.get("cell_key", "")
                statement = stage3_entry.get("statement", "")
                fp = compute_fingerprint(statement)
                for bt in bank_by_cell.get(cell_key, []):
                    bt_fp = compute_fingerprint(bt.get("statement", ""))
                    if bt.get("import_key") == import_key:
                        if bt_fp == fp:
                            match_methods["fingerprint"] += 1
                        else:
                            match_methods["normalized_exact"] += 1
                        break
            else:
                unmatched.append(f"{tid} ({cat}): matched bank entry but no import_key")
                match_methods["failed"] += 1
        else:
            unmatched.append(f"{tid} ({cat}): NO bank match found")
            match_methods["failed"] += 1
    
    print(f"    Successfully mapped: {len(task_to_import)} / {len(task_cats)}")
    print(f"    Match methods: {match_methods}")
    
    if unmatched:
        print(f"\n    UNMATCHED ({len(unmatched)}):")
        for u in unmatched[:10]:
            print(f"      - {u}")
        if len(unmatched) > 10:
            print(f"      ... and {len(unmatched)-10} more")
    
    # Now analyze per-cell replacement slots with CORRECT mapping
    print("\n[6] Per-cell replacement slot analysis (with correct mapping)...")
    
    # Get cell_key for each task from stage3
    replace_cells: Dict[str, List[str]] = {}  # cell_key -> [import_keys]
    fixed_cells: Dict[str, List[str]] = {}
    
    for tid in replace_ids:
        import_key = task_to_import.get(tid)
        stage3_entry = stage3_idx.get(tid)
        cell_key = stage3_entry.get("cell_key", "") if stage3_entry else ""
        if import_key and cell_key:
            replace_cells.setdefault(cell_key, []).append(import_key)
    
    for tid in fixed_ids:
        import_key = task_to_import.get(tid)
        stage3_entry = stage3_idx.get(tid)
        cell_key = stage3_entry.get("cell_key", "") if stage3_entry else ""
        if import_key and cell_key:
            fixed_cells.setdefault(cell_key, []).append(import_key)
    
    print(f"\n    Cells with REPLACE tasks: {len(replace_cells)}")
    for ck in sorted(replace_cells.keys()):
        imp_keys = replace_cells[ck]
        fixed_in_cell = fixed_cells.get(ck, [])
        print(f"      {ck}: {len(imp_keys)} REPLACE, {len(fixed_in_cell)} FIXED")
    
    # Count bank tasks per cell
    print("\n[7] Computing correct slot counts per cell...")
    total_replacement_slots = 0
    slots_by_cell: Dict[str, dict] = {}
    
    for cell_key in sorted(set(list(replace_cells.keys()) + list(bank_by_cell.keys()))):
        bank_tasks = bank_by_cell.get(cell_key, [])
        bank_count = len(bank_tasks)
        replace_keys = replace_cells.get(cell_key, [])
        fixed_keys = fixed_cells.get(cell_key, [])
        
        # Valid existing = total bank tasks - REPLACE tasks
        valid_existing = bank_count - len(replace_keys)
        
        # Needed slots = max(0, 5 - valid_existing)
        needed_slots = max(0, 5 - valid_existing)
        
        # Replacement slots = min(replace_count, needed_slots)
        replacement_slots = min(len(replace_keys), needed_slots)
        
        total_replacement_slots += replacement_slots
        
        slots_by_cell[cell_key] = {
            "bank_count": bank_count,
            "replace_in_bank": len(replace_keys),
            "fixed_in_bank": len(fixed_keys),
            "valid_existing": valid_existing,
            "needed_slots": needed_slots,
            "replacement_slots": replacement_slots
        }
        
        if replacement_slots > 0:
            print(f"    {cell_key}: bank={bank_count}, replace={len(replace_keys)}, "
                  f"valid={valid_existing}, need={needed_slots}, slots={replacement_slots}")
    
    print(f"\n    TOTAL replacement slots: {total_replacement_slots}")
    
    # Also count cells with < 5 tasks that are NOT in the REPLACE set
    print("\n[8] All cells with < 5 tasks (potential refill candidates)...")
    underfilled = []
    for cell_key, bank_tasks in sorted(bank_by_cell.items()):
        if len(bank_tasks) < 5:
            underfilled.append((cell_key, len(bank_tasks)))
            print(f"    {cell_key}: {len(bank_tasks)} tasks")
    print(f"    Total underfilled cells: {len(underfilled)}")
    
    # Save mapping
    print("\n[9] Saving mapping files...")
    mapping_path = os.path.join(BASE_DIR, "task_id_to_import_key_mapping.json")
    mapping_data = {
        "mapping": task_to_import,
        "summary": {
            "total_classified": len(task_cats),
            "mapped_successfully": len(task_to_import),
            "unmatched": len(unmatched),
            "match_methods": match_methods
        },
        "unmatched": unmatched
    }
    with open(mapping_path, "w", encoding="utf-8") as f:
        json.dump(mapping_data, f, ensure_ascii=False, indent=2)
    print(f"    Saved task_id -> import_key mapping to {mapping_path}")
    
    # Save corrected slot report
    report_path = os.path.join(BASE_DIR, "corrected_slot_report.json")
    report_data = {
        "task_counts": {
            "KEEP": len(keep_ids),
            "FIXED": len(fixed_ids),
            "REPLACE": len(replace_ids),
            "total": len(task_cats)
        },
        "total_replacement_slots": total_replacement_slots,
        "per_cell_slots": slots_by_cell,
        "underfilled_cells": underfilled,
        "total_underfilled": len(underfilled)
    }
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)
    print(f"    Saved corrected slot report to {report_path}")
    
    print("\n" + "=" * 70)
    print("INVESTIGATION COMPLETE")
    print("=" * 70)

if __name__ == "__main__":
    main()
