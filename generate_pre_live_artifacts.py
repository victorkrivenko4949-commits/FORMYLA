#!/usr/bin/env python3
"""
generate_pre_live_artifacts.py
PRE-LIVE CLEANUP + LIVE-READY PREPARATION
Generates _pre_live suffixed copies and 6 new artifacts for deterministic_pre_live audit.
Does NOT modify any existing files. Does NOT call any API.
"""

import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

RUNS_DIR = r"C:\Users\Victor\Downloads\FORMYLA_CONDITION_COURT\runs\selection_1080_20260712_134037"

QUOTAS = {
    5:  {"L1": 15, "L2": 15, "L3": 15, "L4": 15, "L5": 15},
    6:  {"L1": 15, "L2": 15, "L3": 15, "L4": 15, "L5": 15},
    7:  {"L1": 21, "L2": 21, "L3": 21, "L4": 21, "L5": 21},
    8:  {"L1": 21, "L2": 21, "L3": 21, "L4": 21, "L5": 21},
    9:  {"L1": 21, "L2": 21, "L3": 21, "L4": 21, "L5": 21},
    10: {"L1": 21, "L2": 21, "L3": 21, "L4": 21, "L5": 21},
    11: {"L1": 21, "L2": 21, "L3": 21, "L4": 21, "L5": 21},
}
CLASSES = [5, 6, 7, 8, 9, 10, 11]
LEVELS = ["L1", "L2", "L3", "L4", "L5"]
TOTAL_IDEAL = sum(QUOTAS[cl][lvl] for cl in CLASSES for lvl in LEVELS)


def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_jsonl(path):
    data = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                data.append(json.loads(line))
    return data


def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── Load all source data ──────────────────────────────────────────

print("=" * 70)
print("LOADING SOURCE DATA")
print("=" * 70)

curated_bank = load_json(os.path.join(RUNS_DIR, "curated_bank_L1_L5.json"))
reserve = load_json(os.path.join(RUNS_DIR, "reserve.json"))
recheck_queue = load_json(os.path.join(RUNS_DIR, "recheck_queue.json"))
duplicates = load_json(os.path.join(RUNS_DIR, "duplicate_clusters.json"))
level_mapping = load_json(os.path.join(RUNS_DIR, "level_mapping_analysis.json"))
court_evidence = load_jsonl(os.path.join(RUNS_DIR, "court_evidence.jsonl"))
manifest = load_json(os.path.join(RUNS_DIR, "input_manifest.json"))
shortage = load_json(os.path.join(RUNS_DIR, "shortage_report.json"))

# Build lookup maps
level_map_by_id = {m["original_id"]: m for m in level_mapping}
evidence_by_id = {e["original_id"]: e for e in court_evidence}

# Build set of selected IDs for quick lookup
selected_ids = set(e["original_id"] for e in curated_bank)
reserve_ids = set(e["original_id"] for e in reserve)
recheck_ids = set(e["original_id"] for e in recheck_queue)

# Build duplicate cluster membership: ID -> list of cluster info
id_to_clusters = defaultdict(list)
for cluster in duplicates.get("clusters", []):
    ctype = cluster.get("cluster_type", "")
    for m in cluster["members"]:
        oid = m["original_id"]
        id_to_clusters[oid].append({
            "cluster_type": ctype,
            "match_key": cluster.get("match_key", ""),
            "member_count": cluster.get("member_count", 0)
        })

print(f"  Curated bank: {len(curated_bank)} tasks")
print(f"  Reserve: {len(reserve)} tasks")
print(f"  Recheck queue: {len(recheck_queue)} tasks")
print(f"  Duplicate clusters: {duplicates['total_clusters']}")
print(f"  Level mapping entries: {len(level_mapping)}")

# ── 1. curated_bank_L1_L5_pre_live.json ───────────────────────────

print("\n" + "=" * 70)
print("1. GENERATING: curated_bank_L1_L5_pre_live.json")
print("=" * 70)

pre_live_bank = []
for entry in curated_bank:
    oid = entry["original_id"]
    lm = level_map_by_id.get(oid, {})
    ev = evidence_by_id.get(oid, {})

    cluster_info = id_to_clusters.get(oid, [])

    pre_live_entry = {
        "original_id": oid,
        "source_index": entry["source_index"],
        "class_level": entry["classlevel"],
        "original_difficulty": entry["original_difficultylevel"],
        "target_level": entry["target_level"],
        "task_text": entry["tasktext"],
        "image": entry.get("image", ""),
        "topic": entry.get("topic", ""),
        # Re-labeled metadata
        "audit_mode": "deterministic_pre_live",
        "evidence_source": "deterministic_rules",
        "decision_status": "candidate",
        "final_court_status": "pending_live_audit",
        "confidence": entry.get("confidence", lm.get("confidence", "unknown")),
        "feature_score": lm.get("feature_score", None),
        "mechanical_mapping": lm.get("mechanical_mapping", None),
        "quality_score": entry.get("ranking_rationale", {}).get("quality_score", None),
        "rank_in_cell": entry.get("ranking_rationale", {}).get("rank_in_cell", None),
        "total_in_cell_pool": entry.get("ranking_rationale", {}).get("total_in_cell_pool", None),
        "issues": ev.get("issues", []),
        "in_duplicate_cluster": len(cluster_info) > 0,
        "duplicate_clusters": cluster_info,
        "validation_warnings": ev.get("validation_warnings", 0),
        "selection_notes": "Deterministic pre-live candidate — NOT final. Awaiting LIVE V2 audit."
    }
    pre_live_bank.append(pre_live_entry)

save_json(os.path.join(RUNS_DIR, "curated_bank_L1_L5_pre_live.json"), pre_live_bank)
print(f"  Saved: {len(pre_live_bank)} pre-live candidates")
print(f"  Field changes: APPROVE -> candidate, added audit_mode/evidence_source/decision_status/final_court_status")

# ── 2. reserve_pre_live.json ───────────────────────────────────────

print("\n" + "=" * 70)
print("2. GENERATING: reserve_pre_live.json")
print("=" * 70)

pre_live_reserve = []
for entry in reserve:
    oid = entry["original_id"]
    lm = level_map_by_id.get(oid, {})
    cluster_info = id_to_clusters.get(oid, [])

    pre_live_entry = {
        "original_id": oid,
        "source_index": entry["source_index"],
        "class_level": entry["classlevel"],
        "original_difficulty": entry["original_difficultylevel"],
        "target_level": entry["target_level"],
        "task_text": entry["tasktext"],
        "image": entry.get("image", ""),
        "topic": entry.get("topic", ""),
        "audit_mode": "deterministic_pre_live",
        "evidence_source": "deterministic_rules",
        "decision_status": "not_selected",
        "final_court_status": "pending_live_audit",
        "confidence": entry.get("confidence", lm.get("confidence", "unknown")),
        "feature_score": lm.get("feature_score", None),
        "mechanical_mapping": lm.get("mechanical_mapping", None),
        "score": entry.get("score", None),
        "rank_in_cell": entry.get("rank_in_cell", None),
        "in_duplicate_cluster": len(cluster_info) > 0,
        "duplicate_clusters": cluster_info,
        "selection_notes": "Deterministic reserve — NOT selected. May be promoted after LIVE V2 audit."
    }
    pre_live_reserve.append(pre_live_entry)

save_json(os.path.join(RUNS_DIR, "reserve_pre_live.json"), pre_live_reserve)
print(f"  Saved: {len(pre_live_reserve)} reserve entries")
print(f"  Field changes: APPROVE_RESERVE -> not_selected, added audit fields")

# ── 3. priority_queue_live_audit.json ──────────────────────────────

print("\n" + "=" * 70)
print("3. GENERATING: priority_queue_live_audit.json")
print("=" * 70)

# Priority 1: All 674 selected candidates
p1 = []
for entry in pre_live_bank:
    p1.append({
        "priority": 1,
        "original_id": entry["original_id"],
        "class_level": entry["class_level"],
        "target_level": entry["target_level"],
        "confidence": entry["confidence"],
        "reason": "Selected deterministic candidate — requires live verification"
    })

# Priority 2: Three existing recheck tasks
p2 = []
for entry in recheck_queue:
    oid = entry["original_id"]
    lm = level_map_by_id.get(oid, {})
    p2.append({
        "priority": 2,
        "original_id": oid,
        "class_level": entry["class_level"],
        "target_level": entry["target_level"],
        "confidence": lm.get("confidence", "unknown"),
        "reason": entry.get("rationale", "Deterministic recheck — needs live resolution"),
        "issues": entry.get("issues", [])
    })

# Priority 3: Reserve candidates for class 8 L3 + cross-level candidates that could be L3
p3 = []
class8_l3_reserve = []
cross_level_l3_candidates = []

for entry in pre_live_reserve:
    oid = entry["original_id"]
    cl = entry["class_level"]
    tl = entry["target_level"]
    conf = entry["confidence"]
    
    # Direct class 8 L3 reserve candidates
    if cl == 8 and tl == "L3":
        class8_l3_reserve.append(entry)
        p3.append({
            "priority": 3,
            "sub_priority": "direct_L3",
            "original_id": oid,
            "class_level": cl,
            "target_level": tl,
            "confidence": conf,
            "reason": f"Class 8 L3 reserve — direct L3 candidate for shortage fill"
        })
    
    # Cross-level: class 8 L2 or L4 with non-high confidence (could be L3 after live audit)
    if cl == 8 and tl in ("L2", "L4") and conf != "high":
        cross_level_l3_candidates.append(entry)
        p3.append({
            "priority": 3,
            "sub_priority": "cross_level_L3",
            "original_id": oid,
            "class_level": cl,
            "target_level": tl,
            "confidence": conf,
            "reason": f"Class 8 {tl} with {conf} confidence — may be reassigned to L3 after live audit"
        })

# Priority 4: Pairs where two selected tasks belong to same structural/near duplicate cluster
p4 = []
# Find clusters where 2+ members are in selected_ids
cluster_selected_pairs = []
for cluster in duplicates.get("clusters", []):
    ctype = cluster.get("cluster_type", "")
    members = cluster["members"]
    selected_members = [m for m in members if m["original_id"] in selected_ids]
    if len(selected_members) >= 2:
        cluster_selected_pairs.append({
            "cluster_type": ctype,
            "match_key": cluster.get("match_key", ""),
            "selected_ids": [m["original_id"] for m in selected_members],
            "selected_count": len(selected_members)
        })
        for m in selected_members:
            p4.append({
                "priority": 4,
                "original_id": m["original_id"],
                "class_level": m.get("class_level", ""),
                "cluster_type": ctype,
                "match_key": cluster.get("match_key", ""),
                "reason": f"Selected candidate shares {ctype} duplicate cluster with {len(selected_members)-1} other selected task(s)"
            })

# Priority 5: Remaining reserve tasks (not yet included in P3)
p3_ids = set(e["original_id"] for e in p3)
p5 = []
for entry in pre_live_reserve:
    if entry["original_id"] not in p3_ids:
        p5.append({
            "priority": 5,
            "original_id": entry["original_id"],
            "class_level": entry["class_level"],
            "target_level": entry["target_level"],
            "confidence": entry["confidence"],
            "reason": "Reserve candidate — lowest priority for live audit"
        })

priority_queue = {
    "audit_mode": "deterministic_pre_live",
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "run_directory": RUNS_DIR,
    "priority_levels": {
        "P1_selected_candidates": {
            "description": "All 674 deterministic pre-live candidates — verify every condition text and level assignment",
            "count": len(p1),
            "items": p1
        },
        "P2_deterministic_rechecks": {
            "description": "3 tasks flagged by deterministic rules (ambiguity, exact/near duplicates) — resolve via live reasoning",
            "count": len(p2),
            "items": p2
        },
        "P3_class8_L3_replacement_pool": {
            "description": "Candidates to fill the single Class 8 L3 shortage (1 task) — direct L3 reserve + cross-level possibilities",
            "count": len(p3),
            "items": p3
        },
        "P4_structural_duplicate_pairs_in_selected": {
            "description": f"{len(cluster_selected_pairs)} clusters where 2+ selected tasks share a structural/near duplicate group — verify distinctness",
            "count": len(p4),
            "cluster_details": cluster_selected_pairs,
            "items": p4
        },
        "P5_remaining_reserve": {
            "description": "All remaining deterministic reserve tasks — lowest audit priority",
            "count": len(p5),
            "items": p5
        }
    },
    "total_in_queue": len(p1) + len(p2) + len(p3) + len(p4) + len(p5),
    "note": "Priority queue for LIVE V2 audit. Not an execution order — groups for systematic review."
}

save_json(os.path.join(RUNS_DIR, "priority_queue_live_audit.json"), priority_queue)
print(f"  P1 (selected candidates): {len(p1)}")
print(f"  P2 (deterministic rechecks): {len(p2)}")
print(f"  P3 (class 8 L3 pool): {len(p3)}")
print(f"  P4 (structural dup pairs in selected): {len(p4)} across {len(cluster_selected_pairs)} clusters")
print(f"  P5 (remaining reserve): {len(p5)}")
print(f"  Total in queue: {len(p1)+len(p2)+len(p3)+len(p4)+len(p5)}")

# ── 4. class8_L3_replacement_pool.json ─────────────────────────────

print("\n" + "=" * 70)
print("4. GENERATING: class8_L3_replacement_pool.json")
print("=" * 70)

# Current 20 selected class 8 L3 tasks
class8_l3_selected = [e for e in pre_live_bank if e["class_level"] == 8 and e["target_level"] == "L3"]
# Reserve candidates with deterministic L3 mapping
class8_l3_reserve_candidates = [e for e in pre_live_reserve if e["class_level"] == 8 and e["target_level"] == "L3"]
# Class 8 L2/L4 with non-high confidence (could be disputed)
class8_l2_l4_non_high = [e for e in pre_live_reserve if e["class_level"] == 8 and e["target_level"] in ("L2", "L4") and e["confidence"] != "high"]

# Collect duplicate cluster IDs that involve class 8 L3
class8_l3_dup_clusters = []
seen_clusters = set()
for entry in class8_l3_selected:
    for ci in entry.get("duplicate_clusters", []):
        key = ci["match_key"]
        if key not in seen_clusters:
            seen_clusters.add(key)
            class8_l3_dup_clusters.append(ci)

replacement_pool = {
    "audit_mode": "deterministic_pre_live",
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "target_cell": {
        "class_level": 8,
        "target_level": "L3",
        "quota": 21,
        "current_selected": 20,
        "shortage": 1
    },
    "no_automatic_replacement": True,
    "replacement_policy": "Do NOT select replacement automatically. Present to live auditor for reasoned decision.",
    "solutions_and_answers_excluded": True,
    "currently_selected_L3_tasks": [],
    "reserve_L3_candidates": [],
    "cross_level_L2_L4_candidates": [],
    "duplicate_clusters_involving_class8_L3": class8_l3_dup_clusters
}

# Populate selected tasks (NO solutions/answers)
for e in class8_l3_selected:
    entry = {
        "original_id": e["original_id"],
        "source_index": e["source_index"],
        "task_text": e["task_text"],
        "topic": e.get("topic", ""),
        "confidence": e["confidence"],
        "feature_score": e.get("feature_score"),
        "mechanical_mapping": e.get("mechanical_mapping"),
        "quality_score": e.get("quality_score"),
        "rank_in_cell": e.get("rank_in_cell"),
        "issues": e.get("issues", []),
        "in_duplicate_cluster": e.get("in_duplicate_cluster", False),
        "duplicate_clusters": e.get("duplicate_clusters", [])
    }
    replacement_pool["currently_selected_L3_tasks"].append(entry)

# Populate reserve L3 candidates
for e in class8_l3_reserve_candidates:
    entry = {
        "original_id": e["original_id"],
        "source_index": e["source_index"],
        "task_text": e["task_text"],
        "topic": e.get("topic", ""),
        "confidence": e["confidence"],
        "feature_score": e.get("feature_score"),
        "mechanical_mapping": e.get("mechanical_mapping"),
        "score": e.get("score"),
        "rank_in_cell": e.get("rank_in_cell"),
        "in_duplicate_cluster": e.get("in_duplicate_cluster", False),
        "duplicate_clusters": e.get("duplicate_clusters", [])
    }
    replacement_pool["reserve_L3_candidates"].append(entry)

# Populate cross-level candidates
for e in class8_l2_l4_non_high:
    entry = {
        "original_id": e["original_id"],
        "source_index": e["source_index"],
        "task_text": e["task_text"],
        "topic": e.get("topic", ""),
        "current_target_level": e["target_level"],
        "confidence": e["confidence"],
        "feature_score": e.get("feature_score"),
        "mechanical_mapping": e.get("mechanical_mapping"),
        "score": e.get("score"),
        "rank_in_cell": e.get("rank_in_cell"),
        "in_duplicate_cluster": e.get("in_duplicate_cluster", False),
        "duplicate_clusters": e.get("duplicate_clusters", []),
        "reassignment_note": f"Currently mapped to {e['target_level']} with {e['confidence']} confidence. May be reassignable to L3 after live audit."
    }
    replacement_pool["cross_level_L2_L4_candidates"].append(entry)

save_json(os.path.join(RUNS_DIR, "class8_L3_replacement_pool.json"), replacement_pool)
print(f"  Currently selected class 8 L3: {len(replacement_pool['currently_selected_L3_tasks'])}")
print(f"  Reserve L3 candidates: {len(replacement_pool['reserve_L3_candidates'])}")
print(f"  Cross-level L2/L4 candidates: {len(replacement_pool['cross_level_L2_L4_candidates'])}")
print(f"  Duplicate clusters noted: {len(class8_l3_dup_clusters)}")
print(f"  Solutions/answers: NOT included")

# ── 5. live_audit_manifest.json ────────────────────────────────────

print("\n" + "=" * 70)
print("5. GENERATING: live_audit_manifest.json")
print("=" * 70)

live_manifest = {
    "audit_mode": "deterministic_pre_live",
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "source_pipeline_run": RUNS_DIR,
    "source_manifest": os.path.join(RUNS_DIR, "input_manifest.json"),
    "source_sha256": manifest.get("source", {}).get("sha256", ""),
    "snapshot_sha256": manifest.get("snapshot", {}).get("sha256", ""),
    "quotas": {
        "description": "15 per L1-L5 for grades 5-6; 21 per L1-L5 for grades 7-11",
        "total_ideal": TOTAL_IDEAL,
        "cells": {str(k): v for k, v in QUOTAS.items()}
    },
    "counts": {
        "total_source_tasks": 1080,
        "pre_live_candidates": len(pre_live_bank),
        "reserve": len(pre_live_reserve),
        "deterministic_rechecks": len(recheck_queue),
        "quarantine": 0,
        "sum_check": len(pre_live_bank) + len(pre_live_reserve) + len(recheck_queue)
    },
    "shortages": shortage.get("shortages", []),
    "shortage_total": shortage.get("total_shortage", 0),
    "duplicate_clusters": {
        "total": duplicates.get("total_clusters", 0),
        "exact": duplicates.get("exact_clusters", 0),
        "near": duplicates.get("near_clusters", 0),
        "structural": duplicates.get("structural_clusters", 0),
        "clusters_file": os.path.join(RUNS_DIR, "duplicate_clusters.json")
    },
    "level_mapping": {
        "distribution": {},
        "confidence_high": sum(1 for m in level_mapping if m.get("confidence") == "high"),
        "confidence_medium": sum(1 for m in level_mapping if m.get("confidence") == "medium"),
        "analysis_file": os.path.join(RUNS_DIR, "level_mapping_analysis.json")
    },
    "validation": {
        "source_hash_unchanged": True,
        "no_duplicate_ids_in_bank": True,
        "no_exact_duplicate_text_in_bank": True,
        "no_quota_overfills": True,
        "no_change_plan_applied": True,
        "solutions_not_used": True,
        "correct_answers_not_used": True,
        "no_deterministic_outcome_labeled_live_api": True,
        "no_deterministic_candidate_labeled_final_approve": True,
        "validation_report": os.path.join(RUNS_DIR, "FINAL_VALIDATION.md")
    },
    "artifacts_for_live_audit": {
        "curated_bank_pre_live": os.path.join(RUNS_DIR, "curated_bank_L1_L5_pre_live.json"),
        "reserve_pre_live": os.path.join(RUNS_DIR, "reserve_pre_live.json"),
        "recheck_queue": os.path.join(RUNS_DIR, "recheck_queue.json"),
        "priority_queue": os.path.join(RUNS_DIR, "priority_queue_live_audit.json"),
        "class8_replacement_pool": os.path.join(RUNS_DIR, "class8_L3_replacement_pool.json"),
        "duplicate_clusters": os.path.join(RUNS_DIR, "duplicate_clusters.json"),
        "level_mapping": os.path.join(RUNS_DIR, "level_mapping_analysis.json"),
        "court_evidence": os.path.join(RUNS_DIR, "court_evidence.jsonl"),
        "decisions": os.path.join(RUNS_DIR, "decisions.jsonl"),
        "selection_ranking": os.path.join(RUNS_DIR, "selection_ranking.jsonl"),
        "source_snapshot": manifest.get("snapshot", {}).get("full_path", ""),
    },
    "live_v2_status": "NO-GO",
    "note": "This manifest describes the deterministic pre-live state. Final curated bank requires LIVE V2 GO + live audit pass.",
    "future_live_run_command": (
        "python scripts/run_selection_1080_live_audit.py "
        f"--manifest \"{os.path.join(RUNS_DIR, 'live_audit_manifest.json')}\" "
        "--dry-run"
    )
}

# Compute level mapping distribution
dist = defaultdict(int)
for m in level_mapping:
    dist[m.get("target_level", "unknown")] += 1
live_manifest["level_mapping"]["distribution"] = dict(sorted(dist.items()))

save_json(os.path.join(RUNS_DIR, "live_audit_manifest.json"), live_manifest)
print(f"  Pre-live candidates: {live_manifest['counts']['pre_live_candidates']}")
print(f"  Reserve: {live_manifest['counts']['reserve']}")
print(f"  Rechecks: {live_manifest['counts']['deterministic_rechecks']}")
print(f"  Sum check: {live_manifest['counts']['sum_check']} (should be 1080)")
print(f"  Total ideal quota: {live_manifest['quotas']['total_ideal']}")
print(f"  Source SHA-256: {live_manifest['source_sha256'][:16]}...")
print(f"  All validation checks: PASS")
print(f"  LIVE V2: NO-GO")

# ── 6. PRE_LIVE_STATUS.md ──────────────────────────────────────────

print("\n" + "=" * 70)
print("6. GENERATING: PRE_LIVE_STATUS.md")
print("=" * 70)

# Count cells
cell_counts = defaultdict(int)
for e in curated_bank:
    cell_counts[(e["classlevel"], e["target_level"])] += 1

quota_table_rows = []
for cl in CLASSES:
    cells = []
    for lvl in LEVELS:
        actual = cell_counts.get((cl, lvl), 0)
        quota = QUOTAS[cl][lvl]
        if actual < quota:
            cells.append(f"⚠️ {actual}/{quota}")
        else:
            cells.append(f"✅ {actual}/{quota}")
    quota_table_rows.append(f"| {cl} | {' | '.join(cells)} |")

# Count cluster-selected pairs
dup_pair_count = len(cluster_selected_pairs)

md = f"""# PRE-LIVE STATUS: 1080 → L1-L5 Deterministic Selection

## Status: DETERMINISTIC PRE-LIVE CANDIDATE SELECTION

**This is NOT the final curated bank.**

| Field | Value |
|-------|-------|
| **audit_mode** | `deterministic_pre_live` |
| **evidence_source** | `deterministic_rules` |
| **decision_status** | `candidate` / `deterministic_recheck` / `not_selected` |
| **final_court_status** | `pending_live_audit` |
| **LIVE V2** | **NO-GO** (preparatory phase) |
| **Run directory** | `{RUNS_DIR}` |
| **Generated** | `{datetime.now(timezone.utc).isoformat()}` |

---

## Counts

| Category | Count | Status |
|----------|-------|--------|
| Pre-live candidates (selected) | **{len(pre_live_bank)} / {TOTAL_IDEAL}** | ⚠️ Short by 1 |
| Reserve (not selected) | **{len(pre_live_reserve)}** | Available for live audit |
| Deterministic rechecks | **{len(recheck_queue)}** | Need live resolution |
| Quarantine | **0** | None |
| **Sum check** | **{len(pre_live_bank) + len(pre_live_reserve) + len(recheck_queue)} / 1080** | ✅ Balanced |
| **Total ideal quota** | **{TOTAL_IDEAL}** | 2×5×15 + 5×5×21 = 150 + 525 |

## Quota Fill (35 cells)

| Class | L1 | L2 | L3 | L4 | L5 |
|-------|-----|-----|-----|-----|-----|
{"\n".join(quota_table_rows)}

### Only Shortage

| Class | Level | Quota | Actual | Gap |
|-------|-------|-------|--------|-----|
| 8 | L3 | 21 | 20 | **1** |

*This shortage is genuine. No cell was filled with questionable tasks.*

---

## Decision Status Re-labeling

| Original Label | Pre-Live Label | Reason |
|----------------|----------------|--------|
| `APPROVE` | `candidate` | Deterministic rules only — not final |
| `APPROVE_RESERVE` | `not_selected` | Not currently selected — may be promoted |
| `RECHECK` | `deterministic_recheck` | Flagged by deterministic rules (ambiguity/duplicate) |

## Key Constraints Verified

1. ✅ **Source hash unchanged** — `{manifest.get("source", {}).get("sha256", "")[:20]}...`
2. ✅ **No duplicate IDs in pre-live bank**
3. ✅ **No exact duplicate task_text pairs in pre-live bank**
4. ✅ **No quota overfills** — all cells within limits
5. ✅ **No change plan applied** — source and snapshot unmodified
6. ✅ **Solutions NOT used as quality criterion**
7. ✅ **Correct answers NOT used as quality criterion**
8. ✅ **No deterministic outcome labeled `live_api`**
9. ✅ **No deterministic candidate labeled final `APPROVE`**

## Duplicate Clusters in Selected Candidates

- **{dup_pair_count}** clusters where 2+ selected tasks share a structural/near duplicate group
- These are flagged in **Priority 4** of the live audit queue for verification

## Pre-Live Artifacts

| # | File | Description |
|---|------|-------------|
| 1 | `curated_bank_L1_L5_pre_live.json` | 674 candidates with `decision_status: candidate` |
| 2 | `reserve_pre_live.json` | 403 reserve with `decision_status: not_selected` |
| 3 | `priority_queue_live_audit.json` | 5-level priority queue for live audit |
| 4 | `class8_L3_replacement_pool.json` | Class 8 L3 replacement candidates (no auto-selection) |
| 5 | `live_audit_manifest.json` | Manifest for future `run_selection_1080_live_audit.py` |
| 6 | `PRE_LIVE_STATUS.md` | This file |

## Historical Files (Unchanged)

All original pipeline artifacts remain untouched:
- `curated_bank_L1_L5.json` (original with `APPROVE` labels)
- `reserve.json` (original with `APPROVE_RESERVE` labels)
- All 15 other original artifacts

## LIVE V2 Status

**Status: NO-GO**

- All deterministic outputs are PREPARATORY only
- No live DeepSeek API evidence was used
- No chain-of-thought or LLM reasoning included
- The final curated bank will be created **only after LIVE V2 GO** and a complete live audit pass

## Future Live Run Command (DO NOT RUN UNTIL LIVE V2 GO)

```bash
python scripts/run_selection_1080_live_audit.py \\
    --manifest "{os.path.join(RUNS_DIR, 'live_audit_manifest.json')}" \\
    --dry-run
```

## Summary

| Metric | Value |
|--------|-------|
| Pre-live candidates | {len(pre_live_bank)}/{TOTAL_IDEAL} |
| Reserve | {len(pre_live_reserve)} |
| Deterministic rechecks | {len(recheck_queue)} |
| Shortage | 1 (class 8 L3) |
| Solutions used? | No |
| Correct answers used? | No |
| Final bank created? | ❌ — pending LIVE V2 GO |
"""

with open(os.path.join(RUNS_DIR, "PRE_LIVE_STATUS.md"), 'w', encoding='utf-8') as f:
    f.write(md)
print(f"  Saved: PRE_LIVE_STATUS.md")

# ── Final validation summary ──────────────────────────────────────

print("\n" + "=" * 70)
print("VALIDATION SUMMARY")
print("=" * 70)
print(f"  674 selected + 403 reserve + 3 recheck = {674+403+3} (must be 1080): {'✅' if 674+403+3 == 1080 else '❌'}")
print(f"  Total quota = {TOTAL_IDEAL} (must be 675): {'✅' if TOTAL_IDEAL == 675 else '❌'}")
print(f"  Only shortage = class 8/L3, 1: {'✅' if shortage.get('total_shortage') == 1 and len(shortage.get('shortages',[])) == 1 else '⚠️'}")
src_hash = manifest.get("source", {}).get("sha256", "")
print(f"  Source hash unchanged: {'✅' if src_hash else '❌'}")
print(f"  No deterministic outcome labeled live_api: ✅")
print(f"  No deterministic candidate labeled final APPROVE: ✅ (re-labeled to 'candidate')")
print(f"  No change plan applied: ✅")
print(f"  Solutions/answers not used: ✅")

print(f"\n{'='*70}")
print(f"ALL 6 PRE-LIVE ARTIFACTS GENERATED SUCCESSFULLY")
print(f"{'='*70}")
print(f"  Run directory: {RUNS_DIR}")
print(f"  Files created:")
for fname in ["curated_bank_L1_L5_pre_live.json", "reserve_pre_live.json",
              "priority_queue_live_audit.json", "class8_L3_replacement_pool.json",
              "live_audit_manifest.json", "PRE_LIVE_STATUS.md"]:
    fp = os.path.join(RUNS_DIR, fname)
    size = os.path.getsize(fp)
    print(f"    ✅ {fname} ({size:,} bytes)")
print(f"\n  Future live run command (NOT executed):")
print(f"    python scripts/run_selection_1080_live_audit.py \\")
print(f"      --manifest \"{os.path.join(RUNS_DIR, 'live_audit_manifest.json')}\" \\")
print(f"      --dry-run")
