#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""STEP 3: Resolve 3 RECHECK tasks - determine exact cause and convert to APPROVE or REJECT"""

import json
import sys

RUN_DIR = r"../../Downloads/FORMYLA_CONDITION_COURT/runs/selection_1080_20260718_175442"

def main():
    # 1. Read recheck queue
    with open(f"{RUN_DIR}/recheck_queue.json", "r", encoding="utf-8") as f:
        recheck = json.load(f)
    
    # 2. Read duplicate clusters (it's a dict with "clusters" key)
    with open(f"{RUN_DIR}/duplicate_clusters.json", "r", encoding="utf-8") as f:
        clusters_data = json.load(f)
    clusters = clusters_data.get("clusters", [])
    
    # 3. Read evidence records
    with open(f"{RUN_DIR}/court_evidence.jsonl", "r", encoding="utf-8") as f:
        evidence = [json.loads(line) for line in f]
    
    # 4. Read decisions
    with open(f"{RUN_DIR}/decisions.jsonl", "r", encoding="utf-8") as f:
        decisions = {d["original_id"]: d for d in [json.loads(line) for line in f]}
    
    # 5. Read curated bank
    with open(f"{RUN_DIR}/curated_bank_L1_L5.json", "r", encoding="utf-8") as f:
        bank = json.load(f)
    
    bank_by_id = {t["original_id"]: t for t in bank}
    
    print("=" * 70)
    print("STEP 3: RESOLVE 3 RECHECK TASKS")
    print("=" * 70)
    
    # Find evidence for RECHECK tasks
    ev_by_id = {}
    for e in evidence:
        oid = e.get("original_id")
        if oid:
            if oid not in ev_by_id:
                ev_by_id[oid] = []
            ev_by_id[oid].append(e)
    
    resolutions = []
    
    for r in recheck:
        oid = r["original_id"]
        print(f"\n--- {oid} ---")
        print(f"  Class: {r['class_level']}, Level: {r['target_level']}")
        print(f"  Topic: {r['topic']}")
        print(f"  Rationale: {r['rationale']}")
        print(f"  Issues: {r.get('issues', [])}")
        print(f"  Text: {r['task_text'][:120]}...")
        
        dec = decisions.get(oid, {})
        print(f"  Decision: {dec.get('decision', 'N/A')}")
        
        ev_list = ev_by_id.get(oid, [])
        print(f"  Evidence records: {len(ev_list)}")
        
        # Check if in duplicate clusters
        in_cluster = False
        for c in clusters:
            members = c.get("members", [])
            ids = [m.get("original_id", m.get("id", "")) for m in members]
            if oid in ids:
                in_cluster = True
                print(f"  DUPLICATE CLUSTER ({c.get('cluster_type', 'unknown')}): match_key='{c.get('match_key','')[:60]}...'")
                for m in members:
                    mid = m.get("original_id", m.get("id", ""))
                    if mid != oid:
                        print(f"    Related: {mid} (class {m.get('class_level','?')}, diff {m.get('difficulty_level','?')})")
        
        in_bank = oid in bank_by_id
        print(f"  In curated bank: {in_bank}")
    
    # 6. Detailed analysis
    print("\n" + "=" * 70)
    print("DETAILED ANALYSIS")
    print("=" * 70)
    
    for r in recheck:
        oid = r["original_id"]
        print(f"\n{'#'*60}")
        print(f"# {oid}")
        print(f"{'#'*60}")
        
        if oid == "SEL1080-0963":
            print(f"  ISSUE 1: 'произвольный' pattern triggered ambiguity detector")
            print(f"  ANALYSIS: The word 'произвольный' (arbitrary) is used correctly here.")
            print(f"  This is the STANDARD formulation of the classic 8x8 L-tromino problem.")
            print(f"  'произвольный' means 'any/arbitrary' - the key point is the")
            print(f"  tiling must work regardless of which cell is removed.")
            print(f"  CONCLUSION: False positive by ambiguity detector. APPROVE.")
            
            print(f"\n  ISSUE 2: potential_grade_mismatch")
            print(f"  ANALYSIS: 8x8 board tiling with L-trominoes is a standard")
            print(f"  6th-7th grade Olympiad problem (chessboard coloring).")
            print(f"  Appropriate for class 6, difficulty 8 (L5). APPROVE.")
            
            resolutions.append({
                "original_id": oid,
                "resolution": "APPROVE",
                "rationale": "False positive by pattern detector. 'произвольный' is used correctly in the standard formulation of the classic 8x8 L-tromino tiling problem. Grade 6 is appropriate for this difficulty 8 problem.",
                "issues_resolved": [
                    "ambiguous_pattern:произвольный - correctly used in context",
                    "potential_grade_mismatch - class 6 appropriate for this problem"
                ]
            })
        
        elif oid == "SEL1080-0976":
            print(f"  ISSUE: Near-duplicate cluster with SEL1080-1011")
            print(f"  ANALYSIS: These are DIFFERENT problems with different constraints.")
            print(f"  SEL1080-0976 (class 7): restricts rows, columns, and 45° diagonals only")
            print(f"  SEL1080-1011 (class 8): restricts ALL lines (any slope)")
            print(f"  1011 is strictly more restrictive (any slope vs only 45°).")
            print(f"  CONCLUSION: Not duplicates. APPROVE.")
            
            resolutions.append({
                "original_id": oid,
                "resolution": "APPROVE",
                "rationale": "Not a true duplicate. SEL1080-0976 restricts only rows, columns, and 45° diagonals. SEL1080-1011 restricts ALL lines (any slope). Different constraints, different solutions, different class levels. False positive by duplicate detector.",
                "issues_resolved": [
                    "duplicate_cluster - constraints differ (45° only vs any slope)"
                ]
            })
        
        elif oid == "SEL1080-1011":
            print(f"  ISSUE: Near-duplicate cluster with SEL1080-0976")
            print(f"  ANALYSIS: This is a HARDER problem (class 8, L5).")
            print(f"  5x5 board, no three collinear on ANY line (any slope).")
            print(f"  More complex combinatorial geometry argument than 0976.")
            print(f"  CONCLUSION: Not a duplicate. APPROVE.")
            
            resolutions.append({
                "original_id": oid,
                "resolution": "APPROVE",
                "rationale": "Not a true duplicate. SEL1080-1011 restricts ALL lines (any slope) which is a harder combinatorial geometry problem than SEL1080-0976 (rows/columns/45° only). Different constraints, different class level. False positive by duplicate detector.",
                "issues_resolved": [
                    "duplicate_cluster - constraints differ (any slope vs 45° only)"
                ]
            })
    
    # 7. Write resolution artifact
    output = {
        "analysis_timestamp": "2026-07-18T22:47:00+03:00",
        "total_recheck": len(recheck),
        "resolved": len(resolutions),
        "resolutions": resolutions,
        "summary": {
            "total": 3,
            "approved": 3,
            "rejected": 0,
            "note": "All 3 RECHECK tasks are false positives - ambiguity detector and duplicate detector flagged them incorrectly. All are valid, distinct tasks."
        }
    }
    
    with open("l4_l5_finalization/recheck_final_resolution.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*70}")
    print(f"RESOLUTION SUMMARY:")
    print(f"  Total RECHECK: {len(recheck)}")
    print(f"  APPROVED: {len(resolutions)}")
    print(f"  REJECTED: 0")
    print(f"  Written to: l4_l5_finalization/recheck_final_resolution.json")
    print(f"{'='*70}")

if __name__ == "__main__":
    main()
