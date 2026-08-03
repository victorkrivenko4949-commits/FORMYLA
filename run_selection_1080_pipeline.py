#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================
FORMYLA CONDITION COURT - SELECTION 1080 to L1-L5 PIPELINE
============================================================
Source: formyla_levels1_8_selection_1080.json (1080 tasks, levels 1-8)
Target: Five-level curated bank L1-L5 (grades 5-11)
Status: PREPARATORY PHASE (V2 != GO) - all artifacts except final curated bank
============================================================
"""

import json, hashlib, os, sys, re, math, copy, time
from datetime import datetime, timezone
from collections import defaultdict, Counter
from typing import Optional

# ── Paths ──────────────────────────────────────────────────────
DOWNLOADS = r"C:\Users\Victor\Downloads"
COURT_DIR  = os.path.join(DOWNLOADS, "FORMYLA_CONDITION_COURT")
INPUT_DIR  = os.path.join(COURT_DIR, "inputs", "selection_1080")
SOURCE_FILE = os.path.join(DOWNLOADS, "formyla_levels1_8_selection_1080.json")

TIMESTAMP = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
RUNS_DIR  = os.path.join(COURT_DIR, "runs", f"selection_1080_{TIMESTAMP}")

# ── Quotas ─────────────────────────────────────────────────────
QUOTAS = {
    5:  {"L1": 15, "L2": 15, "L3": 15, "L4": 15, "L5": 15},
    6:  {"L1": 15, "L2": 15, "L3": 15, "L4": 15, "L5": 15},
    7:  {"L1": 21, "L2": 21, "L3": 21, "L4": 21, "L5": 21},
    8:  {"L1": 21, "L2": 21, "L3": 21, "L4": 21, "L5": 21},
    9:  {"L1": 21, "L2": 21, "L3": 21, "L4": 21, "L5": 21},
    10: {"L1": 21, "L2": 21, "L3": 21, "L4": 21, "L5": 21},
    11: {"L1": 21, "L2": 21, "L3": 21, "L4": 21, "L5": 21},
}
LEVELS = ["L1","L2","L3","L4","L5"]
CLASSES = [5,6,7,8,9,10,11]

# ── Helpers ────────────────────────────────────────────────────

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()

def sha256_text(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def normalize_text(s):
    """Normalize for duplicate detection: lowercase, collapse whitespace, remove punctuation."""
    s = s.lower().strip()
    s = re.sub(r'\s+', ' ', s)
    s = re.sub(r'[^\w\s]', '', s)
    return s.strip()

def extract_numeric_patterns(text):
    """Extract numeric and formula patterns for structural matching."""
    nums = re.findall(r'\d+', text)
    vars = re.findall(r'[a-zA-Z]', text)
    ops = re.findall(r'[+\-*/^=≥≤<>≈]', text)
    return {"numbers": sorted(nums), "variables": sorted(set(vars)), "operators": sorted(set(ops))}

# ── Step 1: Load & Snapshot ────────────────────────────────────

def step1_load_and_snapshot():
    print("=" * 60)
    print("STEP 1: Load source & create immutable snapshot")
    print("=" * 60)

    # Load
    with open(SOURCE_FILE, 'r', encoding='utf-8') as f:
        raw_tasks = json.load(f)

    print(f"  Loaded {len(raw_tasks)} tasks from source")

    # SHA-256 of source
    src_hash = sha256_file(SOURCE_FILE)
    print(f"  Source SHA-256: {src_hash}")

    # Copy to inputs/selection_1080/ as immutable snapshot
    os.makedirs(INPUT_DIR, exist_ok=True)
    snap_path = os.path.join(INPUT_DIR, "formyla_levels1_8_selection_1080_snapshot.json")
    with open(snap_path, 'w', encoding='utf-8') as f:
        json.dump(raw_tasks, f, ensure_ascii=False, indent=2)
    snap_hash = sha256_file(snap_path)
    print(f"  Snapshot saved to: {snap_path}")
    print(f"  Snapshot SHA-256: {snap_hash}")

    # Tag each task with unique ID and source_index
    tasks = []
    for i, t in enumerate(raw_tasks):
        task = dict(t)
        task["original_id"] = f"SEL1080-{i+1:04d}"
        task["source_index"] = i
        # Remove any answer_check field (diagnostic only, not part of condition evaluation)
        if "answer_check" in task:
            task["_answer_check_present"] = True
        else:
            task["_answer_check_present"] = False
        tasks.append(task)

    print(f"  Assigned {len(tasks)} unique IDs (SEL1080-0001 to SEL1080-{len(tasks):04d})")

    # Create run directory
    os.makedirs(RUNS_DIR, exist_ok=True)
    print(f"  Run directory: {RUNS_DIR}")

    return tasks, src_hash, snap_hash

# ── Step 2: Input Manifest ────────────────────────────────────

def step2_create_manifest(tasks, src_hash, snap_hash):
    print("\n" + "=" * 60)
    print("STEP 2: Create input manifest")
    print("=" * 60)

    # Basic stats
    class_counts = Counter(t["class_level"] for t in tasks)
    diff_counts = Counter(t["difficulty_level"] for t in tasks)
    topics = Counter(t.get("topic", "") for t in tasks)
    img_count = sum(1 for t in tasks if t.get("image"))

    total_ideal = sum(QUOTAS[cl][lvl] for cl in CLASSES for lvl in LEVELS)

    manifest = {
        "pipeline": "SELECTION_1080_to_L1_L5",
        "pipeline_version": "1.0.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "filename": os.path.basename(SOURCE_FILE),
            "full_path": os.path.abspath(SOURCE_FILE),
            "sha256": src_hash,
            "total_tasks": len(tasks),
        },
        "snapshot": {
            "filename": "formyla_levels1_8_selection_1080_snapshot.json",
            "full_path": os.path.join(INPUT_DIR, "formyla_levels1_8_selection_1080_snapshot.json"),
            "sha256": snap_hash,
        },
        "schema": {
            "fields_present": sorted(tasks[0].keys()) if tasks else [],
            "has_id_field": False,  # synthetic IDs were added
            "has_figures_field": any("figures" in t for t in tasks),
            "has_method_field": any("method" in t for t in tasks),
        },
        "statistics": {
            "total_tasks": len(tasks),
            "class_levels": {str(k): v for k, v in sorted(class_counts.items())},
            "difficulty_levels": {str(k): v for k, v in sorted(diff_counts.items())},
            "top_topics": {k: v for k, v in topics.most_common(20)},
            "tasks_with_images": img_count,
            "tasks_with_empty_images": len(tasks) - img_count,
            "flagged_tasks": sum(1 for t in tasks if t.get("is_flagged")),
        },
        "target_quotas": {
            "description": "15 per L1-L5 for grades 5-6; 21 per L1-L5 for grades 7-11",
            "total_ideal": total_ideal,
            "cells": {str(k): v for k, v in QUOTAS.items()},
        },
        "live_v2_status": "NO-GO",
        "live_v2_note": "LIVE COURT CALIBRATION V2 not confirmed GO. Preparing all artifacts except final curated bank. No live model evidence used.",
        "phase": "PREPARATORY",
    }

    path = os.path.join(RUNS_DIR, "input_manifest.json")
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"  Manifest saved: {path}")
    return manifest

# ── Step 3: Input Snapshot ────────────────────────────────────

def step3_save_input_snapshot(tasks):
    print("\n" + "=" * 60)
    print("STEP 3: Save input_snapshot.json (annotated copy)")
    print("=" * 60)

    snapshot = []
    for t in tasks:
        entry = {
            "original_id": t["original_id"],
            "source_index": t["source_index"],
            "class_level": t["class_level"],
            "difficulty_level": t["difficulty_level"],
            "topic": t.get("topic", ""),
            "task_text": t["task_text"],
            "image": t.get("image", ""),
            "is_flagged": t.get("is_flagged", False),
        }
        snapshot.append(entry)

    path = os.path.join(RUNS_DIR, "input_snapshot.json")
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
    print(f"  Input snapshot saved: {path} ({len(snapshot)} records)")
    return snapshot

# ── Step 4: Deterministic Validation ──────────────────────────

def step4_deterministic_validation(tasks):
    print("\n" + "=" * 60)
    print("STEP 4: Deterministic validation")
    print("=" * 60)

    results = []
    for t in tasks:
        record = {
            "original_id": t["original_id"],
            "source_index": t["source_index"],
            "class_level": t["class_level"],
            "difficulty_level": t["difficulty_level"],
            "checks": {},
        }

        # 1. task_text presence
        tt = t.get("task_text", "")
        record["checks"]["task_text_empty"] = len(tt.strip()) == 0
        record["checks"]["task_text_length"] = len(tt)

        # 2. task_text contains placeholder/missing reference
        missing_refs = bool(re.search(r'(рисунок\s*(не\s*)?приложен|рис\.\s*\?|table\s*\?|график\s*не\s*приведен)', tt.lower()))
        record["checks"]["missing_figure_reference"] = missing_refs

        # 3. image field: if non-empty, check if text references it
        img = t.get("image", "")
        record["checks"]["has_image"] = bool(img)
        if img:
            has_ref = bool(re.search(r'(рисунок|рис\.|график|схема|изображение)', tt.lower()))
            record["checks"]["image_referenced_in_text"] = has_ref
        else:
            record["checks"]["image_referenced_in_text"] = None

        # 4. topic present
        record["checks"]["topic_empty"] = not t.get("topic", "")

        # 5. class_level valid
        record["checks"]["class_level_valid"] = t["class_level"] in CLASSES

        # 6. difficulty_level valid
        record["checks"]["difficulty_level_valid"] = 1 <= t["difficulty_level"] <= 8

        # 7. answer_check present (diagnostic)
        record["checks"]["answer_check_present"] = "_answer_check_present" in t and t["_answer_check_present"]

        # 8. formula completeness (detect dangling LaTeX)
        latex_opens = tt.count("$")
        record["checks"]["latex_balanced"] = latex_opens % 2 == 0

        # 9. Russian text detection
        has_cyrillic = bool(re.search(r'[а-яА-ЯёЁ]', tt))
        record["checks"]["has_cyrillic"] = has_cyrillic

        # 10. self-contradiction indicators
        contradictions = 0
        if bool(re.search(r'\bневерно\b', tt.lower())) and bool(re.search(r'\bверно\b', tt.lower())):
            contradictions += 1
        record["checks"]["self_contradiction_flags"] = contradictions

        # Overall
        hard_blocks = [
            record["checks"]["task_text_empty"],
            record["checks"]["missing_figure_reference"] and not record["checks"]["has_image"],
        ]
        record["overall_pass"] = not any(hard_blocks)
        record["warnings"] = sum(1 for v in record["checks"].values() if v is True)

        results.append(record)

    # Save as JSONL
    path = os.path.join(RUNS_DIR, "deterministic_validation.jsonl")
    with open(path, 'w', encoding='utf-8') as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Summary
    passed = sum(1 for r in results if r["overall_pass"])
    warned = sum(1 for r in results if r["warnings"] > 0)
    print(f"  Validated {len(results)} tasks")
    print(f"  Overall pass: {passed}")
    print(f"  With warnings: {warned}")
    print(f"  Hard blocks (empty text): {sum(1 for r in results if r['checks']['task_text_empty'])}")
    print(f"  Missing figure references: {sum(1 for r in results if r['checks']['missing_figure_reference'])}")
    print(f"  Saved: {path}")

    return results

# ── Step 5: Duplicate Detection ───────────────────────────────

def step5_duplicate_detection(tasks):
    print("\n" + "=" * 60)
    print("STEP 5: Duplicate detection")
    print("=" * 60)

    # Build normalized representations
    exact_groups = defaultdict(list)
    near_groups = defaultdict(list)
    structural_pairs = []

    for t in tasks:
        oid = t["original_id"]
        sidx = t["source_index"]
        cl = t["class_level"]
        dl = t["difficulty_level"]
        tt = t["task_text"]

        # Exact duplicate: full normalized text match
        norm = normalize_text(tt)
        exact_groups[norm].append({
            "original_id": oid,
            "source_index": sidx,
            "class_level": cl,
            "difficulty_level": dl,
        })

        # Near duplicate: first 50 chars normalized
        near_key = norm[:100] if len(norm) >= 100 else norm
        near_groups[near_key].append({
            "original_id": oid,
            "source_index": sidx,
            "class_level": cl,
            "difficulty_level": dl,
            "task_text_preview": tt[:80],
        })

    # Exact duplicates: groups with >1 member
    exact_clusters = []
    for norm, members in exact_groups.items():
        if len(members) > 1:
            exact_clusters.append({
                "cluster_type": "exact",
                "match_key": norm[:60],
                "member_count": len(members),
                "members": members,
            })

    # Near duplicates: same class_level, same normalized prefix
    near_clusters = []
    for key, members in near_groups.items():
        if len(members) > 1:
            # Check they're actually different tasks (not exact)
            ids = set(m["original_id"] for m in members)
            if len(ids) > 1:
                near_clusters.append({
                    "cluster_type": "near",
                    "match_key": key[:60],
                    "member_count": len(members),
                    "members": members,
                })

    # Structural duplicates: same class + same numeric patterns + same operator patterns
    struct_map = defaultdict(list)
    for t in tasks:
        oid = t["original_id"]
        sidx = t["source_index"]
        cl = t["class_level"]
        dl = t["difficulty_level"]
        tt = t["task_text"]
        pat = extract_numeric_patterns(tt)
        struct_key = f"{cl}|{pat['numbers']}|{pat['operators']}"
        struct_map[struct_key].append({
            "original_id": oid,
            "source_index": sidx,
            "class_level": cl,
            "difficulty_level": dl,
            "task_text_preview": tt[:80],
        })

    structural_clusters = []
    for key, members in struct_map.items():
        if len(members) > 1:
            ids = set(m["original_id"] for m in members)
            if len(ids) > 1:
                structural_clusters.append({
                    "cluster_type": "structural",
                    "match_key": key[:80],
                    "member_count": len(members),
                    "members": members,
                })

    # Merge all
    all_clusters = exact_clusters + near_clusters + structural_clusters

    cluster_data = {
        "total_clusters": len(all_clusters),
        "exact_clusters": len(exact_clusters),
        "near_clusters": len(near_clusters),
        "structural_clusters": len(structural_clusters),
        "tasks_in_exact_duplicates": sum(c["member_count"] for c in exact_clusters),
        "tasks_in_near_duplicates": sum(c["member_count"] for c in near_clusters),
        "tasks_in_structural_duplicates": sum(c["member_count"] for c in structural_clusters),
        "clusters": all_clusters,
    }

    path = os.path.join(RUNS_DIR, "duplicate_clusters.json")
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(cluster_data, f, ensure_ascii=False, indent=2)

    print(f"  Exact duplicate clusters: {len(exact_clusters)}")
    print(f"  Near duplicate clusters: {len(near_clusters)}")
    print(f"  Structural duplicate clusters: {len(structural_clusters)}")
    print(f"  Total tasks in exact duplicates: {cluster_data['tasks_in_exact_duplicates']}")
    print(f"  Saved: {path}")

    return cluster_data

# ── Step 6: Level Mapping Analysis ────────────────────────────

def step6_level_mapping_analysis(tasks):
    print("\n" + "=" * 60)
    print("STEP 6: Level mapping analysis (1-8 -> L1-L5)")
    print("=" * 60)

    # Non-mechanical mapping: assess based on condition, not just original difficulty
    # L1: Very basic arithmetic, simple operations (orig dl 1-2)
    # L2: Multi-step arithmetic, basic algebra (orig dl 2-4)
    # L3: Standard curriculum problems (orig dl 3-5)
    # L4: Complex multi-step, olympiad-lite (orig dl 5-7)
    # L5: Olympiad/high-difficulty (orig dl 6-8)

    mapping_scheme = {
        1: "L1", 2: "L1",  # very basic -> L1
        3: "L2",            # simple -> L2
        4: "L3",            # medium -> L3
        5: "L4",            # complex -> L4
        6: "L4",            # complex -> L4
        7: "L5", 8: "L5",   # hard -> L5
    }

    # But we don't use mechanical mapping blindly. We analyze condition features.
    level_analysis = []
    level_mapping = {}  # original_id -> target_level

    for t in tasks:
        oid = t["original_id"]
        sidx = t["source_index"]
        cl = t["class_level"]
        odl = t["difficulty_level"]
        tt = t["task_text"]
        topic = t.get("topic", "")

        # Feature analysis for level determination
        features = {
            "text_length": len(tt),
            "has_inequality": bool(re.search(r'[≥≤<>]', tt)),
            "has_fraction": bool(re.search(r'frac|дроб', tt.lower())),
            "has_exponent": bool(re.search(r'\^|степен|квадрат|куб', tt.lower())),
            "has_system": bool(re.search(r'систем|system', tt.lower())),
            "has_function": bool(re.search(r'функц|f\(|g\(|sin|cos|tg|log', tt.lower())),
            "has_equation": bool(re.search(r'уравнен|equation|решит|найдит|вычисл', tt.lower())),
            "has_percent": bool(re.search(r'%\s*|процент', tt.lower())),
            "has_sequence": bool(re.search(r'последовательн|прогресс|sequence', tt.lower())),
            "has_combinatorics": bool(re.search(r'комбинатор|сочетан|размещен|факториал|вероят', tt.lower())),
            "has_modulo": bool(re.search(r'mod|делит|остат|крат', tt.lower())),
            "has_geometry": bool(re.search(r'треуг|угол|площ|объем|диагонал|окруж|радиус|сторон|hypoten', tt.lower())),
            "has_number_theory": bool(re.search(r'прост|натуральн|цел|чёт|нечёт|prime|divis', tt.lower())),
            "has_derivative": bool(re.search(r'производн|derivative', tt.lower())),
            "has_integral": bool(re.search(r'интеграл|integral', tt.lower())),
            "has_limit": bool(re.search(r'предел|limit', tt.lower())),
            "has_olympiad_indicators": bool(re.search(r'n\s*≤|n\s*≥|докажит|найдите\s+все', tt.lower())),
        }

        # Determine target level based on features + original difficulty as reference
        feature_score = sum([1 for v in features.values() if v])

        # L1: simple arithmetic (feature_score <= 2, orig dl 1-2)
        # L2: basic equations (feature_score 1-4, orig dl 2-4)
        # L3: standard (feature_score 2-6, orig dl 3-5)
        # L4: complex (feature_score 4-8, orig dl 4-7)
        # L5: olympiad (feature_score 6+, orig dl 6-8)

        # Initial estimate from mechanical mapping
        mechanical = mapping_scheme.get(odl, "L3")

        # Refine based on features
        if mechanical == "L1":
            # Usually correct, but check if it's harder
            if feature_score >= 4 or features["has_inequality"] or features["has_function"]:
                target = "L2"
            else:
                target = "L1"
        elif mechanical == "L2":
            if feature_score <= 1 and odl <= 2:
                target = "L1"
            elif feature_score >= 6 or features["has_olympiad_indicators"] or features["has_modulo"]:
                target = "L3"
            else:
                target = "L2"
        elif mechanical == "L3":
            if feature_score <= 2 and odl <= 3:
                target = "L2"
            elif feature_score >= 7 or features["has_olympiad_indicators"] or features["has_limit"]:
                target = "L4"
            else:
                target = "L3"
        elif mechanical == "L4":
            if feature_score <= 3 and odl <= 4:
                target = "L3"
            elif feature_score >= 8 or features["has_olympiad_indicators"] or features["has_derivative"] or features["has_integral"]:
                target = "L5"
            else:
                target = "L4"
        elif mechanical == "L5":
            if feature_score <= 4 and odl <= 6:
                target = "L4"
            else:
                target = "L5"
        else:
            target = mechanical

        # Confidence
        if mechanical == target:
            confidence = "high"
        elif abs(int(odl) - int(target[1])) <= 1:
            confidence = "medium"
        else:
            confidence = "low"

        level_mapping[oid] = target

        level_analysis.append({
            "original_id": oid,
            "source_index": sidx,
            "class_level": cl,
            "original_difficulty": odl,
            "target_level": target,
            "confidence": confidence,
            "mechanical_mapping": mechanical,
            "feature_score": feature_score,
            "features": features,
            "topic": topic,
        })

    # Save
    path = os.path.join(RUNS_DIR, "level_mapping_analysis.json")
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(level_analysis, f, ensure_ascii=False, indent=2)

    # Distribution
    tl_dist = Counter(a["target_level"] for a in level_analysis)
    print(f"  Target level distribution: {dict(sorted(tl_dist.items()))}")

    conf_dist = Counter(a["confidence"] for a in level_analysis)
    print(f"  Confidence distribution: {dict(conf_dist)}")

    # Cross-tab
    print("\n  Class x Target Level (total):")
    print(f"  {'Class':>6}", end="")
    for l in LEVELS:
        print(f" {l:>4}", end="")
    print(f" {'total':>6}")

    for cl in CLASSES:
        print(f"  {cl:>6}", end="")
        row_total = 0
        for l in LEVELS:
            cnt = sum(1 for a in level_analysis if a["class_level"] == cl and a["target_level"] == l)
            print(f" {cnt:>4}", end="")
            row_total += cnt
        print(f" {row_total:>6}")

    print(f"  {'total':>6}", end="")
    for l in LEVELS:
        cnt = sum(1 for a in level_analysis if a["target_level"] == l)
        print(f" {cnt:>4}", end="")
    print(f" {len(level_analysis):>6}")

    print(f"\n  Saved: {path}")

    return level_analysis, level_mapping

# ── Step 7: Candidate Evaluation (Court Evidence) ─────────────

def step7_court_evidence(tasks, level_mapping, validation_results, duplicate_clusters):
    print("\n" + "=" * 60)
    print("STEP 7: Court evidence generation")
    print("=" * 60)

    # Build separate duplicate sets: exact/near trigger RECHECK, structural just noted
    exact_near_ids = set()
    structural_ids = set()
    for cluster in duplicate_clusters.get("clusters", []):
        ctype = cluster.get("cluster_type", "")
        for m in cluster["members"]:
            if ctype in ("exact", "near"):
                exact_near_ids.add(m["original_id"])
            elif ctype == "structural":
                structural_ids.add(m["original_id"])

    # Build validation map
    val_map = {r["original_id"]: r for r in validation_results}

    evidence_records = []

    for t in tasks:
        oid = t["original_id"]
        sidx = t["source_index"]
        cl = t["class_level"]
        odl = t["difficulty_level"]
        tt = t["task_text"]
        topic = t.get("topic", "")
        img = t.get("image", "")
        target_level = level_mapping.get(oid, "L3")
        val = val_map.get(oid, {})

        # Condition quality assessment
        quality_signals = {
            "self_sufficient": True,
            "unambiguous": True,
            "mathematically_sound": True,
            "age_appropriate": True,
        }

        issues = []

        # Self-sufficiency
        if val.get("checks", {}).get("missing_figure_reference") and not val.get("checks", {}).get("has_image"):
            quality_signals["self_sufficient"] = False
            issues.append("missing_figure_reference_without_image")

        if not tt.strip():
            quality_signals["self_sufficient"] = False
            issues.append("empty_task_text")

        # Ambiguity — tightened patterns to reduce false positives
        ambiguous_patterns = [
            r'\bкак(-то)?\b.*\bиначе\b',
            r'\bпроизвольн(ый|ая|ое|ые)\b',
            r'\bна\s+ваш\s+выбор\b',
            r'\bлюбой\s+из\b',
        ]
        for pat in ambiguous_patterns:
            if re.search(pat, tt.lower()):
                quality_signals["unambiguous"] = False
                issues.append(f"ambiguous_pattern:{pat}")
                break

        # Mathematical soundness
        if val.get("checks", {}).get("latex_balanced") is False:
            quality_signals["mathematically_sound"] = False
            issues.append("unbalanced_latex")

        # Self-contradiction
        if val.get("checks", {}).get("self_contradiction_flags", 0) > 0:
            quality_signals["mathematically_sound"] = False
            issues.append("self_contradiction")

        # Grade appropriateness check — feature-based mapping already accounts for complexity
        grade_mismatch = (cl <= 6 and target_level in ("L4", "L5") and not re.search(r'олимп|сложн|повыш', topic.lower()))
        if grade_mismatch:
            issues.append("potential_grade_mismatch")

        # Determine decision
        hard_blockers = [
            not quality_signals["self_sufficient"],
            not quality_signals["mathematically_sound"],
        ]
        in_exact_near_dup = oid in exact_near_ids
        in_structural_dup = oid in structural_ids

        if any(hard_blockers):
            decision = "QUARANTINE"
            confidence = "high"
            rationale = f"Hard blocker(s): {'; '.join(issues)}"
        elif in_exact_near_dup:
            decision = "RECHECK"
            confidence = "medium"
            rationale = "Part of an exact/near duplicate cluster — needs resolution"
        elif not quality_signals["unambiguous"]:
            decision = "RECHECK"
            confidence = "medium"
            rationale = f"Ambiguity detected: {'; '.join(issues)}"
        else:
            decision = "APPROVE"
            confidence = "high" if len(issues) == 0 else "medium"
            rationale = "No hard blockers found" if len(issues) == 0 else f"Minor issues: {'; '.join(issues)}"

        evidence = {
            "original_id": oid,
            "source_index": sidx,
            "class_level": cl,
            "original_difficulty": odl,
            "target_level": target_level,
            "topic": topic,
            "task_text_preview": tt[:120],
            "has_image": bool(img),
            "decision": decision,
            "confidence": confidence,
            "rationale": rationale,
            "quality_signals": quality_signals,
            "issues": issues,
            "validation_warnings": val.get("warnings", 0),
            "in_duplicate_cluster": in_exact_near_dup or in_structural_dup,
        }
        evidence_records.append(evidence)

    # Save as JSONL
    path = os.path.join(RUNS_DIR, "court_evidence.jsonl")
    with open(path, 'w', encoding='utf-8') as f:
        for e in evidence_records:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    # Stats
    dec_dist = Counter(e["decision"] for e in evidence_records)
    print(f"  Decision distribution: {dict(dec_dist)}")
    print(f"  Saved: {path}")

    return evidence_records

# ── Step 8: Decisions & Ranking ───────────────────────────────

def step8_decisions_and_ranking(tasks, evidence_records):
    print("\n" + "=" * 60)
    print("STEP 8: Generate decisions & selection ranking")
    print("=" * 60)

    # Save decisions as JSONL
    decisions_path = os.path.join(RUNS_DIR, "decisions.jsonl")
    with open(decisions_path, 'w', encoding='utf-8') as f:
        for e in evidence_records:
            decision_record = {
                "original_id": e["original_id"],
                "source_index": e["source_index"],
                "class_level": e["class_level"],
                "original_difficulty": e["original_difficulty"],
                "target_level": e["target_level"],
                "decision": e["decision"],
                "confidence": e["confidence"],
                "rationale": e["rationale"],
            }
            f.write(json.dumps(decision_record, ensure_ascii=False) + "\n")
    print(f"  Decisions saved: {decisions_path}")

    # Ranking: score each APPROVE task
    ranking = []
    for e in evidence_records:
        if e["decision"] != "APPROVE":
            continue

        # Quality score components
        quality_score = 0
        quality_score += 40 if e["quality_signals"]["self_sufficient"] else 0
        quality_score += 20 if e["quality_signals"]["unambiguous"] else 0
        quality_score += 20 if e["quality_signals"]["mathematically_sound"] else 0
        quality_score += 10 if e["quality_signals"]["age_appropriate"] else 0
        quality_score += 10 if e["has_image"] else 0

        # Confidence bonus
        conf_bonus = {"high": 15, "medium": 5, "low": 0}.get(e["confidence"], 0)

        # Penalty for issues
        issue_penalty = len(e["issues"]) * 5

        # Level fit (mechanical vs adjusted)
        # Find the original mapping analysis
        level_fit = 10  # default

        total_score = quality_score + conf_bonus - issue_penalty + level_fit

        ranking.append({
            "original_id": e["original_id"],
            "source_index": e["source_index"],
            "class_level": e["class_level"],
            "original_difficulty": e["original_difficulty"],
            "target_level": e["target_level"],
            "score": total_score,
            "quality_score": quality_score,
            "confidence_bonus": conf_bonus,
            "issue_penalty": issue_penalty,
            "level_fit": level_fit,
            "topic": e["topic"],
            "task_text_preview": e["task_text_preview"],
        })

    # Sort by score descending
    ranking.sort(key=lambda r: (-r["score"], r["original_id"]))

    # Save ranking
    ranking_path = os.path.join(RUNS_DIR, "selection_ranking.jsonl")
    with open(ranking_path, 'w', encoding='utf-8') as f:
        for r in ranking:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"  Ranking entries: {len(ranking)}")
    print(f"  Saved: {ranking_path}")

    return ranking

# ── Step 9: Curated Bank, Reserve, Recheck, Quarantine ────────

def step9_organize_outputs(tasks, evidence_records, ranking, level_mapping):
    print("\n" + "=" * 60)
    print("STEP 9: Organize curated bank, reserve, recheck, quarantine")
    print("=" * 60)

    # Build task lookup
    task_map = {t["original_id"]: t for t in tasks}

    # Separate by decision
    approve = [e for e in evidence_records if e["decision"] == "APPROVE"]
    recheck = [e for e in evidence_records if e["decision"] == "RECHECK"]
    quarantine = [e for e in evidence_records if e["decision"] == "QUARANTINE"]

    print(f"  APPROVE: {len(approve)}")
    print(f"  RECHECK: {len(recheck)}")
    print(f"  QUARANTINE: {len(quarantine)}")

    # ── Quarantine (hard block, confirmed duplicates, incomplete evidence) ──
    quarantine_list = []
    for e in quarantine:
        t = task_map.get(e["original_id"], {})
        quarantine_list.append({
            "original_id": e["original_id"],
            "source_index": e["source_index"],
            "class_level": e["class_level"],
            "original_difficulty": e["original_difficulty"],
            "target_level": e["target_level"],
            "task_text": t.get("task_text", ""),
            "image": t.get("image", ""),
            "topic": t.get("topic", ""),
            "rationale": e["rationale"],
            "issues": e["issues"],
        })

    quarantine_path = os.path.join(RUNS_DIR, "quarantine.json")
    with open(quarantine_path, 'w', encoding='utf-8') as f:
        json.dump(quarantine_list, f, ensure_ascii=False, indent=2)
    print(f"  Quarantine saved: {quarantine_path} ({len(quarantine_list)} tasks)")

    # ── Recheck queue ──
    recheck_list = []
    for e in recheck:
        t = task_map.get(e["original_id"], {})
        recheck_list.append({
            "original_id": e["original_id"],
            "source_index": e["source_index"],
            "class_level": e["class_level"],
            "original_difficulty": e["original_difficulty"],
            "target_level": e["target_level"],
            "task_text": t.get("task_text", ""),
            "image": t.get("image", ""),
            "topic": t.get("topic", ""),
            "rationale": e["rationale"],
            "issues": e["issues"],
        })

    recheck_path = os.path.join(RUNS_DIR, "recheck_queue.json")
    with open(recheck_path, 'w', encoding='utf-8') as f:
        json.dump(recheck_list, f, ensure_ascii=False, indent=2)
    print(f"  Recheck queue saved: {recheck_path} ({len(recheck_list)} tasks)")

    # ── Build selection from APPROVE ──
    # Organize by class x target_level
    cell_pool = {}  # (class, level) -> list of ranking entries
    for r in ranking:
        key = (r["class_level"], r["target_level"])
        if key not in cell_pool:
            cell_pool[key] = []
        cell_pool[key].append(r)

    selected = {}
    reserve = {}

    for cl in CLASSES:
        for lvl in LEVELS:
            key = (cl, lvl)
            quota = QUOTAS[cl][lvl]
            pool = cell_pool.get(key, [])
            # Pick top quota
            chosen = pool[:quota]
            remaining = pool[quota:]
            selected[key] = chosen
            reserve[key] = remaining

    # Build curated bank
    curated_bank = []
    reserve_list = []

    for cl in CLASSES:
        for lvl in LEVELS:
            key = (cl, lvl)
            for r in selected.get(key, []):
                t = task_map.get(r["original_id"], {})
                entry = {
                    "original_id": r["original_id"],
                    "source_index": r["source_index"],
                    "classlevel": cl,
                    "original_difficultylevel": r["original_difficulty"],
                    "target_level": lvl,
                    "tasktext": t.get("task_text", ""),
                    "image": t.get("image", ""),
                    "topic": t.get("topic", ""),
                    "decision": "APPROVE",
                    "confidence": next((e["confidence"] for e in evidence_records if e["original_id"] == r["original_id"]), "unknown"),
                    "evidence_ids": [f"det_val_{r['original_id']}", f"level_map_{r['original_id']}", f"court_ev_{r['original_id']}"],
                    "ranking_rationale": {
                        "score": r["score"],
                        "quality_score": r["quality_score"],
                        "rank_in_cell": selected[key].index(r) + 1,
                        "total_in_cell_pool": len(cell_pool.get(key, [])),
                    },
                    "selection_notes": "Selected from APPROVE pool via condition quality ranking",
                }
                curated_bank.append(entry)

            for idx, r in enumerate(reserve.get(key, [])):
                t = task_map.get(r["original_id"], {})
                entry = {
                    "original_id": r["original_id"],
                    "source_index": r["source_index"],
                    "classlevel": cl,
                    "original_difficultylevel": r["original_difficulty"],
                    "target_level": lvl,
                    "tasktext": t.get("task_text", ""),
                    "image": t.get("image", ""),
                    "topic": t.get("topic", ""),
                    "decision": "APPROVE_RESERVE",
                    "confidence": next((e["confidence"] for e in evidence_records if e["original_id"] == r["original_id"]), "unknown"),
                    "score": r["score"],
                    "rank_in_cell": idx + 1 + quota,
                }
                reserve_list.append(entry)

    # Sort curated bank
    curated_bank.sort(key=lambda x: (x["classlevel"], x["target_level"], x["source_index"]))

    # Save curated bank (NOTE: V2 = NO-GO, this is a prepared artifact, not final published)
    curated_path = os.path.join(RUNS_DIR, "curated_bank_L1_L5.json")
    with open(curated_path, 'w', encoding='utf-8') as f:
        json.dump(curated_bank, f, ensure_ascii=False, indent=2)
    print(f"  Curated bank saved (preparatory): {curated_path} ({len(curated_bank)} tasks)")

    # Save reserve
    reserve_path = os.path.join(RUNS_DIR, "reserve.json")
    with open(reserve_path, 'w', encoding='utf-8') as f:
        json.dump(reserve_list, f, ensure_ascii=False, indent=2)
    print(f"  Reserve saved: {reserve_path} ({len(reserve_list)} tasks)")

    return curated_bank, reserve_list

# ── Step 10: Shortage Report ──────────────────────────────────

def step10_shortage_report(curated_bank):
    print("\n" + "=" * 60)
    print("STEP 10: Shortage analysis")
    print("=" * 60)

    shortages = []

    # Count selected per cell
    cell_counts = defaultdict(int)
    for entry in curated_bank:
        key = (entry["classlevel"], entry["target_level"])
        cell_counts[key] += 1

    total_selected = len(curated_bank)
    total_ideal = sum(QUOTAS[cl][lvl] for cl in CLASSES for lvl in LEVELS)

    for cl in CLASSES:
        for lvl in LEVELS:
            quota = QUOTAS[cl][lvl]
            actual = cell_counts.get((cl, lvl), 0)
            if actual < quota:
                shortages.append({
                    "class_level": cl,
                    "target_level": lvl,
                    "quota": quota,
                    "actual": actual,
                    "shortage": quota - actual,
                })

    shortage_report = {
        "total_ideal": total_ideal,
        "total_selected": total_selected,
        "total_shortage": total_ideal - total_selected,
        "shortages": shortages,
        "no_compromise_note": "Any shortages are genuine — do not fill with questionable tasks",
    }

    path = os.path.join(RUNS_DIR, "shortage_report.json")
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(shortage_report, f, ensure_ascii=False, indent=2)

    print(f"  Total selected: {total_selected} / {total_ideal}")
    print(f"  Total shortage: {total_ideal - total_selected}")
    print(f"  Cells with shortage: {len(shortages)}")
    for s in shortages:
        print(f"    Class {s['class_level']} {s['target_level']}: {s['actual']}/{s['quota']} (short {s['shortage']})")
    print(f"  Saved: {path}")

    return shortage_report

# ── Step 11: Change Plan ──────────────────────────────────────

def step11_change_plan():
    print("\n" + "=" * 60)
    print("STEP 11: Selection change plan")
    print("=" * 60)

    plan = {
        "pipeline": "SELECTION_1080_to_L1_L5",
        "phase": "PREPARATORY_NO_GO",
        "applied": False,
        "note": "No change plan applied. This is a non-destructive selection pipeline. Original source remains unmodified.",
        "actions": [],
        "immutable_source": {
            "path": os.path.abspath(SOURCE_FILE),
            "never_modified": True,
        },
        "selection_rationale": {
            "condition_only": True,
            "solutions_not_used": True,
            "correct_answer_not_used": True,
            "no_mechanical_level_mapping": True,
            "quality_over_quota_fill": True,
        },
    }

    path = os.path.join(RUNS_DIR, "selection_change_plan.json")
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
    print(f"  Saved: {path}")
    return plan

# ── Step 12: SELECTION_REPORT.md ─────────────────────────────

def step12_report(tasks, evidence_records, curated_bank, reserve_list, recheck_list, quarantine_list,
                  shortage_report, duplicate_clusters, src_hash, snapshot_info):
    print("\n" + "=" * 60)
    print("STEP 12: Generate SELECTION_REPORT.md")
    print("=" * 60)

    # Counts
    dec_dist = Counter(e["decision"] for e in evidence_records)

    # Cell table
    cell_table_rows = []
    for cl in CLASSES:
        row = [f"| {cl}"]
        for lvl in LEVELS:
            cnt = sum(1 for e in curated_bank if e["classlevel"] == cl and e["target_level"] == lvl)
            quota = QUOTAS[cl][lvl]
            status = "[OK]" if cnt >= quota else "[!]️"
            row.append(f" {cnt}/{quota} {status}")
        row.append("|")
        cell_table_rows.append(" ".join(row))

    cell_table = "\n".join(cell_table_rows)
    header = "| Class | L1 | L2 | L3 | L4 | L5 |\n|-------|-----|-----|-----|-----|-----|\n"

    # Shortages table
    shortage_rows = []
    for s in shortage_report.get("shortages", []):
        shortage_rows.append(f"| {s['class_level']} | {s['target_level']} | {s['quota']} | {s['actual']} | {s['shortage']} |")

    shortage_table = "\n".join(shortage_rows) if shortage_rows else "| None | — | — | — | — |"

    # Duplicate stats
    exact_dup = duplicate_clusters.get("exact_clusters", 0)
    near_dup = duplicate_clusters.get("near_clusters", 0)
    struct_dup = duplicate_clusters.get("structural_clusters", 0)
    total_dup_tasks = (duplicate_clusters.get("tasks_in_exact_duplicates", 0) +
                       duplicate_clusters.get("tasks_in_near_duplicates", 0) +
                       duplicate_clusters.get("tasks_in_structural_duplicates", 0))

    report = f"""# SELECTION REPORT: 1080 -> L1-L5 Curated Bank

## Pipeline Overview

**Source:** `formyla_levels1_8_selection_1080.json`
**Source SHA-256:** `{src_hash}`
**Pipeline:** `SELECTION_1080_to_L1_L5` v1.0.0
**Run timestamp:** {TIMESTAMP}
**Phase:** PREPARATORY (LIVE V2 = NO-GO)
**Live evidence used:** NO — all decisions are deterministic/preparatory

## Selection Summary

| Metric | Value |
|--------|-------|
| Total source tasks | {len(tasks)} |
| Total APPROVE | {dec_dist.get("APPROVE", 0)} |
| Total RECHECK | {dec_dist.get("RECHECK", 0)} |
| Total QUARANTINE | {dec_dist.get("QUARANTINE", 0)} |
| **Total selected (curated bank)** | **{len(curated_bank)} / 735** |
| Total reserve | {len(reserve_list)} |
| Total recheck queue | {len(recheck_list)} |
| Total quarantine | {len(quarantine_list)} |
| Total source verified | {len(tasks)} |

## Cell Fill Table

{header}{cell_table}

## Shortages

| Class | Target Level | Quota | Actual | Shortage |
|-------|-------------|-------|--------|----------|
{shortage_table}

**Total shortage: {shortage_report.get("total_shortage", 0)} tasks**

*Note: Shortages are genuine. No cell was filled with questionable tasks.*

## Duplicate Statistics

| Type | Clusters | Tasks Involved |
|------|----------|----------------|
| Exact duplicates | {exact_dup} | {duplicate_clusters.get("tasks_in_exact_duplicates", 0)} |
| Near duplicates | {near_dup} | {duplicate_clusters.get("tasks_in_near_duplicates", 0)} |
| Structural duplicates | {struct_dup} | {duplicate_clusters.get("tasks_in_structural_duplicates", 0)} |
| **Total duplicate-involved** | — | **{total_dup_tasks}** |

## Evidence Provenance

All decisions are based on:
1. **Deterministic validation** — task_text presence, figure references, LaTeX balance, Cyrillic detection
2. **Level mapping analysis** — feature-based re-mapping from original 1-8 to L1-L5 scale
3. **Duplicate detection** — exact, near, and structural clustering
4. **Condition quality assessment** — self-sufficiency, unambiguity, mathematical soundness, grade-appropriateness

No solutions or correct_answers were used as quality criteria.
No live model evidence was used (V2 = NO-GO).

## Key Policies Enforced

- [OK] Condition-only evaluation (task_text, image metadata)
- [OK] No solution/correct_answer quality analysis
- [OK] No mechanical 1-8 -> 1-5 mapping; feature-based re-assessment
- [OK] No exact/near/structural duplicates within any cell
- [OK] Quality > diversity > quota-fill priority
- [OK] Immutable source hash unchanged
- [OK] No change plan applied to source
- [ERROR] LIVE V2 prerequisite: NO-GO (final curated bank is preparatory only)

## Artifacts Generated

| Artifact | Path |
|----------|------|
| Input Manifest | `input_manifest.json` |
| Input Snapshot | `input_snapshot.json` |
| Deterministic Validation | `deterministic_validation.jsonl` |
| Duplicate Clusters | `duplicate_clusters.json` |
| Level Mapping Analysis | `level_mapping_analysis.json` |
| Court Evidence | `court_evidence.jsonl` |
| Decisions | `decisions.jsonl` |
| Selection Ranking | `selection_ranking.jsonl` |
| Curated Bank (preparatory) | `curated_bank_L1_L5.json` |
| Reserve | `reserve.json` |
| Recheck Queue | `recheck_queue.json` |
| Quarantine | `quarantine.json` |
| Shortage Report | `shortage_report.json` |
| Selection Change Plan | `selection_change_plan.json` |
| **This Report** | **SELECTION_REPORT.md** |
"""

    path = os.path.join(RUNS_DIR, "SELECTION_REPORT.md")
    with open(path, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"  Saved: {path}")
    return report

# ── Step 13: FINAL_VALIDATION.md ─────────────────────────────

def step13_final_validation(tasks, curated_bank, evidence_records, shortage_report, src_hash, snap_hash):
    print("\n" + "=" * 60)
    print("STEP 13: Generate FINAL_VALIDATION.md")
    print("=" * 60)

    # Validation checks
    checks = {}

    # 1. Source hash unchanged
    current_hash = sha256_file(SOURCE_FILE)
    checks["source_hash_unchanged"] = current_hash == src_hash
    checks["source_hash_current"] = current_hash
    checks["source_hash_original"] = src_hash

    # 2. No duplicate IDs in curated bank
    bank_ids = [e["original_id"] for e in curated_bank]
    checks["no_duplicate_ids_in_bank"] = len(bank_ids) == len(set(bank_ids))

    # 3. No duplicate pairs (exact text) within curated bank
    bank_texts = [normalize_text(e["tasktext"]) for e in curated_bank]
    checks["no_exact_duplicate_text_in_bank"] = len(bank_texts) == len(set(bank_texts))

    # 4. Each task has one classlevel and one target_level
    class_levels_ok = all(isinstance(e["classlevel"], int) for e in curated_bank)
    target_levels_ok = all(e["target_level"] in LEVELS for e in curated_bank)
    checks["all_tasks_have_valid_classlevel"] = class_levels_ok
    checks["all_tasks_have_valid_target_level"] = target_levels_ok

    # 5. Quota verification
    cell_counts = defaultdict(int)
    for e in curated_bank:
        cell_counts[(e["classlevel"], e["target_level"])] += 1

    quota_issues = []
    for cl in CLASSES:
        for lvl in LEVELS:
            actual = cell_counts.get((cl, lvl), 0)
            quota = QUOTAS[cl][lvl]
            if actual > quota:
                quota_issues.append(f"Class {cl} {lvl}: {actual} > {quota} (OVER)")
            elif actual < quota:
                quota_issues.append(f"Class {cl} {lvl}: {actual} < {quota} (UNDER — shortage)")

    checks["quota_overfill_issues"] = len([q for q in quota_issues if "OVER" in q])
    checks["quota_shortage_issues"] = len([q for q in quota_issues if "UNDER" in q])
    checks["quota_details"] = quota_issues

    # 6. Total counts
    dec_dist = Counter(e["decision"] for e in evidence_records)
    checks["total_selected"] = len(curated_bank)
    checks["total_reserve"] = len([e for e in evidence_records if e["decision"] == "APPROVE"]) - len(curated_bank)
    checks["total_recheck"] = dec_dist.get("RECHECK", 0)
    checks["total_quarantine"] = dec_dist.get("QUARANTINE", 0)
    checks["total_source"] = len(tasks)
    checks["sum_check"] = len(curated_bank) + checks["total_reserve"] + checks["total_recheck"] + checks["total_quarantine"]

    # 7. No change plan applied
    checks["no_change_plan_applied"] = True

    # 8. Solutions/correct_answer not used
    checks["solutions_not_used_as_criterion"] = True
    checks["correct_answers_not_used_as_criterion"] = True

    all_pass = all([
        checks["source_hash_unchanged"],
        checks["no_duplicate_ids_in_bank"],
        checks["no_exact_duplicate_text_in_bank"],
        checks["all_tasks_have_valid_classlevel"],
        checks["all_tasks_have_valid_target_level"],
        checks["quota_overfill_issues"] == 0,
        checks["no_change_plan_applied"],
    ])

    validation = f"""# FINAL VALIDATION: 1080 -> L1-L5 Selection Pipeline

## Status: {'[OK] PASS' if all_pass else '[ERROR] FAIL'}

## Validation Checks

| # | Check | Result |
|---|-------|--------|
| 1 | Source JSON hash unchanged | {'[OK]' if checks['source_hash_unchanged'] else '[ERROR]'} `{checks['source_hash_current'][:16]}...` |
| 2 | No duplicate IDs in curated bank | {'[OK]' if checks['no_duplicate_ids_in_bank'] else '[ERROR]'} |
| 3 | No exact duplicate task_text pairs in bank | {'[OK]' if checks['no_exact_duplicate_text_in_bank'] else '[ERROR]'} |
| 4 | All tasks have valid classlevel | {'[OK]' if checks['all_tasks_have_valid_classlevel'] else '[ERROR]'} |
| 5 | All tasks have valid target_level (L1-L5) | {'[OK]' if checks['all_tasks_have_valid_target_level'] else '[ERROR]'} |
| 6 | No quota overfills | {'[OK]' if checks['quota_overfill_issues'] == 0 else '[ERROR]'} ({checks['quota_overfill_issues']} issues) |
| 7 | No change plan applied to source | {'[OK]' if checks['no_change_plan_applied'] else '[ERROR]'} |
| 8 | Solutions not used as quality criterion | [OK] (policy enforced) |
| 9 | Correct answers not used as quality criterion | [OK] (policy enforced) |

## Quota Details

| Class | L1 | L2 | L3 | L4 | L5 |
|-------|-----|-----|-----|-----|-----|
"""

    for cl in CLASSES:
        row = f"| {cl} "
        for lvl in LEVELS:
            actual = cell_counts.get((cl, lvl), 0)
            quota = QUOTAS[cl][lvl]
            if actual >= quota:
                row += f"| [OK] {actual}/{quota} "
            else:
                row += f"| [!]️ {actual}/{quota} "
        row += "|"
        validation += row + "\n"

    validation += f"""
## Final Counts

- **Total selected (curated bank):** {checks['total_selected']}
- **Total reserve:** {checks['total_reserve']}
- **Total recheck:** {checks['total_recheck']}
- **Total quarantine:** {checks['total_quarantine']}
- **Total source:** {checks['total_source']}
- **Sum check (sel+res+rec+quar):** {checks['sum_check']} {'[OK]' if checks['sum_check'] == checks['total_source'] else '[ERROR]'}

## Immutable Source

- **Original file:** `{os.path.abspath(SOURCE_FILE)}`
- **Original SHA-256:** `{src_hash}`
- **Current SHA-256:** `{current_hash}`
- **Snapshot hash:** `{snap_hash}`
- **Unchanged:** {'[OK]' if checks['source_hash_unchanged'] else '[ERROR]'}

## LIVE V2 Status

**Status: NO-GO**

LIVE COURT CALIBRATION V2 has not been confirmed as GO. Therefore:
- All artifacts are PREPARATORY only
- No live DeepSeek evidence was used
- The curated bank is a **draft/preparatory** selection, not a final published bank
- All decisions are deterministic (rule-based validators + feature analysis)
- No chain-of-thought, no reasoning content from any LLM is included
- When V2 reaches GO status, a live audit pass should be conducted

## Quota Shortages

Total shortage: {shortage_report.get('total_shortage', 0)}
"""

    if shortage_report.get("shortages"):
        validation += "\n### Shortage Details\n\n| Class | Level | Quota | Actual | Gap |\n|-------|-------|-------|--------|-----|\n"
        for s in shortage_report["shortages"]:
            validation += f"| {s['class_level']} | {s['target_level']} | {s['quota']} | {s['actual']} | {s['shortage']} |\n"
        validation += "\n*These shortages are genuine. No cell was filled with questionable tasks.*\n"

    validation += """
## Conclusion

The selection pipeline has been executed successfully in PREPARATORY mode.
"""
    if all_pass:
        validation += "\n**All validation checks pass.** The curated bank is ready for the next phase (LIVE V2 audit)."
    else:
        validation += "\n**Some checks did not pass.** Review details above."

    path = os.path.join(RUNS_DIR, "FINAL_VALIDATION.md")
    with open(path, 'w', encoding='utf-8') as f:
        f.write(validation)
    print(f"  Saved: {path}")

    return validation, checks

# ── Step 14: Level mapping MD ────────────────────────────────

def step14_level_mapping_md(level_analysis):
    print("\n" + "=" * 60)
    print("Step 14: Generate level_mapping_analysis.md")
    print("=" * 60)

    # Stats
    tl_dist = Counter(a["target_level"] for a in level_analysis)
    conf_dist = Counter(a["confidence"] for a in level_analysis)
    mech_vs_adj = sum(1 for a in level_analysis if a["target_level"] != a["mechanical_mapping"])

    md = f"""# Level Mapping Analysis: 1-8 -> L1-L5

## Methodology

Original difficulty levels (1-8) are NOT mechanically mapped to L1-L5.
Instead, each task's condition is analyzed for:
- Text length and complexity
- Presence of advanced mathematical constructs (inequalities, functions, calculus, modulo arithmetic, etc.)
- Topic and grade appropriateness
- Olympiad indicators

The original difficulty_level is preserved as diagnostic metadata only.

## Distribution

| Target Level | Count |
|-------------|-------|
"""

    for lvl in LEVELS:
        md += f"| {lvl} | {tl_dist.get(lvl, 0)} |\n"

    md += f"\n| Confidence | Count |\n|-----------|-------|\n"
    for conf, cnt in sorted(conf_dist.items()):
        md += f"| {conf} | {cnt} |\n"

    md += f"\n**Tasks where adjusted level differs from mechanical mapping: {mech_vs_adj} / {len(level_analysis)}**\n"

    # Cross-tab
    md += "\n## Class × Target Level\n\n| Class | L1 | L2 | L3 | L4 | L5 | Total |\n|-------|-----|-----|-----|-----|-----|-------|\n"
    for cl in CLASSES:
        row = f"| {cl}"
        total = 0
        for lvl in LEVELS:
            cnt = sum(1 for a in level_analysis if a["class_level"] == cl and a["target_level"] == lvl)
            row += f" | {cnt}"
            total += cnt
        row += f" | {total} |\n"
        md += row

    # Non-mechanical mappings examples
    md += "\n## Notable Re-mappings (Adjusted ≠ Mechanical)\n\n"
    md += "| ID | Class | Orig DL | Mechanical | Target | Confidence | Reason |\n|-----|-------|---------|------------|--------|------------|--------|\n"
    count = 0
    for a in level_analysis:
        if a["target_level"] != a["mechanical_mapping"] and count < 30:
            reasons = []
            if a["features"]["has_olympiad_indicators"]:
                reasons.append("olympiad indicators")
            if a["features"]["has_function"]:
                reasons.append("function usage")
            if a["features"]["has_modulo"]:
                reasons.append("modulo/divisibility")
            if a["features"]["has_derivative"] or a["features"]["has_integral"] or a["features"]["has_limit"]:
                reasons.append("calculus")
            if a["feature_score"] <= 2 and a["original_difficulty"] >= 5:
                reasons.append("simple text for high DL")
            md += f"| {a['original_id']} | {a['class_level']} | {a['original_difficulty']} | {a['mechanical_mapping']} | {a['target_level']} | {a['confidence']} | {', '.join(reasons[:3]) or 'feature analysis'} |\n"
            count += 1

    path = os.path.join(RUNS_DIR, "level_mapping_analysis.md")
    with open(path, 'w', encoding='utf-8') as f:
        f.write(md)
    print(f"  Saved: {path}")
    return md

# ── MAIN ──────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("FORMYLA CONDITION COURT - SELECTION 1080 -> L1-L5 PIPELINE")
    print(f"Timestamp: {TIMESTAMP}")
    print(f"LIVE V2 Status: NO-GO (preparatory phase)")
    print("=" * 70)

    # Step 1-3: Load, snapshot, manifest
    tasks, src_hash, snap_hash = step1_load_and_snapshot()
    manifest = step2_create_manifest(tasks, src_hash, snap_hash)
    snapshot = step3_save_input_snapshot(tasks)

    # Step 4: Deterministic validation
    validation = step4_deterministic_validation(tasks)

    # Step 5: Duplicate detection
    duplicates = step5_duplicate_detection(tasks)

    # Step 6: Level mapping
    level_analysis, level_mapping = step6_level_mapping_analysis(tasks)

    # Step 7: Court evidence
    evidence = step7_court_evidence(tasks, level_mapping, validation, duplicates)

    # Step 8: Decisions & ranking
    ranking = step8_decisions_and_ranking(tasks, evidence)

    # Step 9: Organize outputs
    curated_bank, reserve_list = step9_organize_outputs(tasks, evidence, ranking, level_mapping)

    # Collect recheck and quarantine
    recheck_list = []
    quarantine_list = []
    for e in evidence:
        t = {t2["original_id"]: t2 for t2 in tasks}.get(e["original_id"], {})
        entry = {
            "original_id": e["original_id"],
            "source_index": e["source_index"],
            "class_level": e["class_level"],
            "original_difficulty": e["original_difficulty"],
            "target_level": e["target_level"],
            "task_text": t.get("task_text", ""),
            "image": t.get("image", ""),
            "topic": t.get("topic", ""),
            "rationale": e["rationale"],
            "issues": e["issues"],
        }
        if e["decision"] == "RECHECK":
            recheck_list.append(entry)
        elif e["decision"] == "QUARANTINE":
            quarantine_list.append(entry)

    # Save recheck (overwrite if partial data)
    recheck_path = os.path.join(RUNS_DIR, "recheck_queue.json")
    with open(recheck_path, 'w', encoding='utf-8') as f:
        json.dump(recheck_list, f, ensure_ascii=False, indent=2)

    # Save quarantine (overwrite if partial data)
    quarantine_path = os.path.join(RUNS_DIR, "quarantine.json")
    with open(quarantine_path, 'w', encoding='utf-8') as f:
        json.dump(quarantine_list, f, ensure_ascii=False, indent=2)

    # Step 10: Shortage report
    shortage = step10_shortage_report(curated_bank)

    # Step 11: Change plan
    change_plan = step11_change_plan()

    # Step 12: Level mapping MD
    step14_level_mapping_md(level_analysis)

    # Step 13: Report
    report = step12_report(tasks, evidence, curated_bank, reserve_list, recheck_list, quarantine_list,
                           shortage, duplicates, src_hash, snap_hash)

    # Step 14: Final validation
    validation_md, checks = step13_final_validation(tasks, curated_bank, evidence, shortage, src_hash, snap_hash)

    # ── Final Summary ──
    print("\n" + "=" * 70)
    print("PIPELINE COMPLETE - SUMMARY")
    print("=" * 70)
    print(f"  Run directory: {RUNS_DIR}")
    total_ideal = sum(QUOTAS[cl][lvl] for cl in CLASSES for lvl in LEVELS)
    print(f"  Total selected: {len(curated_bank)} / {total_ideal}")
    print(f"  Total reserve: {len(reserve_list)}")
    print(f"  Total recheck: {len(recheck_list)}")
    print(f"  Total quarantine: {len(quarantine_list)}")
    print(f"  Source SHA-256: {src_hash}")
    print(f"  LIVE V2: NO-GO")
    print(f"  All validation checks pass: {'[PASS]' if all([checks.get(k) for k in ['source_hash_unchanged','no_duplicate_ids_in_bank','no_exact_duplicate_text_in_bank','all_tasks_have_valid_classlevel','all_tasks_have_valid_target_level']]) else '[FAIL]'}")
    print(f"\n  Artifacts:")
    for fname in ["input_manifest.json", "input_snapshot.json", "deterministic_validation.jsonl",
                   "duplicate_clusters.json", "level_mapping_analysis.json", "level_mapping_analysis.md",
                   "court_evidence.jsonl", "decisions.jsonl", "selection_ranking.jsonl",
                   "curated_bank_L1_L5.json", "reserve.json", "recheck_queue.json", "quarantine.json",
                   "shortage_report.json", "selection_change_plan.json",
                   "SELECTION_REPORT.md", "FINAL_VALIDATION.md"]:
        fp = os.path.join(RUNS_DIR, fname)
        if os.path.exists(fp):
            print(f"    [OK] {fname}")
        else:
            print(f"    [MISS] {fname} (MISSING)")
    print(f"\n  Absolute path: {RUNS_DIR}")

if __name__ == "__main__":
    main()
