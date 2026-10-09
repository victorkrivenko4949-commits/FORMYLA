#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Stage 7 Emergency Diagnostic — Complete 15-Step Plan Implementation.
ШАГ 1-12: Snapshot, Failure Matrix, Condition Summary,
Systematic Bug Analysis, Schema Report, Debug Samples.
"""
import json, os, shutil, csv, sys, re, traceback
from datetime import datetime
from collections import Counter, defaultdict

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SNAPSHOT_DIR = os.path.join(BASE_DIR, "stage7_debug_snapshot")
CHECKPOINT_PATH = os.path.join(BASE_DIR, "stage7_checkpoint.json")
CANDIDATES_PATH = os.path.join(BASE_DIR, "stage6_candidates.json")
CONFLICTS_PATH = os.path.join(BASE_DIR, "stage7_solver_conflicts.jsonl")
MAIN_SCRIPT = os.path.join(BASE_DIR, "_07_stage7_verify.py")

FAILURE_MATRIX_CSV = os.path.join(SNAPSHOT_DIR, "stage7_failure_matrix.csv")
FAILURE_SUMMARY_JSON = os.path.join(SNAPSHOT_DIR, "stage7_failure_summary.json")
SCHEMA_REPORT_JSON = os.path.join(SNAPSHOT_DIR, "stage7_schema_report.json")
DEBUG_SAMPLES_MD = os.path.join(SNAPSHOT_DIR, "stage7_debug_samples.md")
RECLASSIFICATION_JSON = os.path.join(SNAPSHOT_DIR, "stage7_reclassification.json")
AND_GATE_REPORT_JSON = os.path.join(SNAPSHOT_DIR, "stage7_and_gate_report.json")
VERIFIED_JSON = os.path.join(SNAPSHOT_DIR, "stage7_verified.json")
REJECTED_CONTENT_JSONL = os.path.join(SNAPSHOT_DIR, "stage7_rejected_content.jsonl")
PENDING_RETRY_JSONL = os.path.join(SNAPSHOT_DIR, "stage7_pending_retry.jsonl")
SOLVER_CONFLICTS_JSONL = os.path.join(SNAPSHOT_DIR, "stage7_solver_conflicts.jsonl")
UNIT_TEST_REPORT = os.path.join(SNAPSHOT_DIR, "stage7_unit_test_report.txt")

COND_NAMES = {
    "c01_solver_a_answer":     "SOLVER_A: answer matches generator",
    "c02_solver_a_solution":   "SOLVER_A: solution is valid",
    "c03_solver_a_leads":      "SOLVER_A: solution leads to answer",
    "c04_solver_a_confidence": "SOLVER_A: confidence >= 0.70",
    "c05_solver_b_answer":     "SOLVER_B: answer matches generator",
    "c06_solver_b_solution":   "SOLVER_B: solution is valid",
    "c07_arbiter_answer":      "ARBITER: answer match verdict",
    "c08_arbiter_solution":    "ARBITER: solution validity",
    "c09_arbiter_proof":       "ARBITER: has mathematical proof",
    "c10_topic_match":         "TOPIC: classification matches",
    "c11_level_match":         "LEVEL: calibration matches target",
    "c12_duplicate_check":     "DUPLICATE: no duplicate found",
}

COND_ORDER = ["c01","c02","c03","c04","c05","c06","c07","c08","c09","c10","c11","c12"]

def p(text):
    now = datetime.now().strftime("%H:%M:%S")
    print(f"[{now}] {text}")

def load_checkpoint():
    if not os.path.exists(CHECKPOINT_PATH):
        p(f"ERROR: checkpoint not found: {CHECKPOINT_PATH}")
        return None, {}, {}
    p(f"Loading checkpoint ({os.path.getsize(CHECKPOINT_PATH)} bytes)...")
    with open(CHECKPOINT_PATH, "r", encoding="utf-8") as f:
        cp = json.load(f)
    verified = cp.get("verified", {})
    rejected = cp.get("rejected", {})
    conflicts = cp.get("conflicts", [])
    p(f"Checkpoint loaded: {len(verified)} verified, {len(rejected)} rejected, {len(conflicts)} conflicts")
    return cp, verified, rejected

# === ШАГ 1: SAVE SNAPSHOT ===
def save_snapshot():
    if os.path.exists(SNAPSHOT_DIR):
        shutil.rmtree(SNAPSHOT_DIR)
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    p(f"Created snapshot directory: {SNAPSHOT_DIR}")

    files_to_copy = [
        (CHECKPOINT_PATH, "stage7_checkpoint.json"),
        (CANDIDATES_PATH, "stage6_candidates.json"),
        (CONFLICTS_PATH, "stage7_solver_conflicts.jsonl"),
        (MAIN_SCRIPT, "_07_stage7_verify.py"),
    ]
    for src, dst in files_to_copy:
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(SNAPSHOT_DIR, dst))
            p(f"  Copied {dst}")
        else:
            p(f"  WARNING: {src} not found, skipped")
    p("ШАГ 1 complete: snapshot saved")

# === ШАГ 2: BUILD FAILURE MATRIX ===
def build_failure_matrix(rejected):
    p("ШАГ 2: Building failure matrix...")
    if not rejected:
        p("  No rejected entries, matrix empty")
        return {}, {}
    rows = []
    cond_fails = Counter()
    cond_total = Counter()
    for slot_key, entry in rejected.items():
        conditions = entry.get("conditions", {})
        row = {"slot_key": slot_key}
        failed_count = 0
        for cid in COND_ORDER:
            cond = conditions.get(cid)
            if cond is not None:
                cond_total[cid] += 1
                passed = cond.get("passed", False)
                if not passed:
                    cond_fails[cid] += 1
                    failed_count += 1
                    row[cid] = "FAIL"
                else:
                    row[cid] = "PASS"
            else:
                row[cid] = "MISSING"
                cond_fails[cid] += 1
                cond_total[cid] += 1
                failed_count += 1
        row["total_failed"] = failed_count
        rows.append(row)
    fieldnames = ["slot_key"] + COND_ORDER + ["total_failed"]
    with open(FAILURE_MATRIX_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    p(f"  Matrix written: {len(rows)} rows -> {FAILURE_MATRIX_CSV}")

    # Per-condition stats
    summary = {}
    for cid in COND_ORDER:
        total = cond_total.get(cid, 0)
        fails = cond_fails.get(cid, 0)
        rate = (fails / total * 100) if total > 0 else 0
        summary[cid] = {
            "condition_name": COND_NAMES.get(cid, cid),
            "total": total,
            "failed": fails,
            "pass_rate_pct": round(100 - rate, 2),
            "fail_rate_pct": round(rate, 2),
        }
        p(f"    {cid} ({COND_NAMES.get(cid,'')}): {fails}/{total} failed ({rate:.1f}%)")
    summary["_meta"] = {
        "total_candidates": len(rejected),
        "total_conditions": len(rejected) * 12,
    }
    with open(FAILURE_SUMMARY_JSON, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    p(f"  Summary written -> {FAILURE_SUMMARY_JSON}")
    return summary, rows

# === ШАГ 3: CHECK AND-GATE SYSTEMATIC ERRORS ===
def check_and_gate(rejected):
    p("ШАГ 3: Checking AND-gate for systematic errors...")
    if not rejected:
        p("  No rejected entries")
        return {}
    and_gate_report = {
        "total_rejected": len(rejected),
        "solver_b_not_called": 0,
        "solver_b_called": 0,
        "c05_missing": 0,
        "c06_missing": 0,
        "all_solver_a_passed": 0,
        "all_solver_a_failed": 0,
        "c01_c04_all_pass_but_rejected": 0,
        "c07_c12_all_pass_but_rejected": 0,
        "samples": [],
    }
    for slot_key, entry in rejected.items():
        conditions = entry.get("conditions", {})
        c01 = conditions.get("c01_solver_a_answer")
        c02 = conditions.get("c02_solver_a_solution")
        c03 = conditions.get("c03_solver_a_leads")
        c04 = conditions.get("c04_solver_a_confidence")
        c05 = conditions.get("c05_solver_b_answer")
        c06 = conditions.get("c06_solver_b_solution")
        c07 = conditions.get("c07_arbiter_answer")
        c08 = conditions.get("c08_arbiter_solution")
        c09 = conditions.get("c09_arbiter_proof")
        c10 = conditions.get("c10_topic_match")
        c11 = conditions.get("c11_level_match")
        c12 = conditions.get("c12_duplicate_check")

        solver_a_conditions = [c for c in [c01, c02, c03, c04] if c is not None]
        solver_a_all_pass = all(c.get("passed") for c in solver_a_conditions) if solver_a_conditions else False
        solver_a_any_fail = any(not c.get("passed") for c in solver_a_conditions) if solver_a_conditions else False

        # Check if SOLVER_B was called
        solver_b_called = c05 is not None
        if solver_b_called:
            and_gate_report["solver_b_called"] += 1
        else:
            and_gate_report["solver_b_not_called"] += 1

        if c05 is None:
            and_gate_report["c05_missing"] += 1
        if c06 is None:
            and_gate_report["c06_missing"] += 1

        if solver_a_all_pass:
            and_gate_report["all_solver_a_passed"] += 1
        if solver_a_any_fail:
            and_gate_report["all_solver_a_failed"] += 1

        # Check if SOLVER_A + ARBITER + TOPIC + LEVEL + DUPLICATE all pass but still rejected
        non_solver_b_conds = [c for c in [c01, c02, c03, c04, c07, c08, c09, c10, c11, c12] if c is not None]
        non_solver_b_all_pass = all(c.get("passed") for c in non_solver_b_conds) if len(non_solver_b_conds) >= 10 else False

        if non_solver_b_all_pass:
            and_gate_report["c01_c04_all_pass_but_rejected"] += 1
            if len(and_gate_report["samples"]) < 5:
                and_gate_report["samples"].append({
                    "slot_key": slot_key,
                    "reason": "All non-SOLVER-B conditions passed but rejected",
                    "solver_b_called": solver_b_called,
                })

        # Check if ARBITER+TOPIC+LEVEL+DUPLICATE all pass but rejected due to SOLVER_A
        post_solver = [c for c in [c07, c08, c09, c10, c11, c12] if c is not None]
        post_solver_all_pass = all(c.get("passed") for c in post_solver) if len(post_solver) >= 6 else False
        if post_solver_all_pass and not solver_a_all_pass:
            and_gate_report["c07_c12_all_pass_but_rejected"] += 1

    # Calculate percentages
    total = len(rejected)
    and_gate_report["solver_b_not_called_pct"] = round(and_gate_report["solver_b_not_called"] / total * 100, 2)
    and_gate_report["solver_b_called_pct"] = round(and_gate_report["solver_b_called"] / total * 100, 2)
    and_gate_report["solver_a_all_pass_pct"] = round(and_gate_report["all_solver_a_passed"] / total * 100, 2)
    and_gate_report["c01_c04_all_pass_but_rejected_pct"] = round(and_gate_report["c01_c04_all_pass_but_rejected"] / total * 100, 2)
    and_gate_report["c07_c12_all_pass_but_rejected_pct"] = round(and_gate_report["c07_c12_all_pass_but_rejected"] / total * 100, 2)

    p(f"  Total rejected: {total}")
    p(f"  SOLVER_B not called: {and_gate_report['solver_b_not_called']} ({and_gate_report['solver_b_not_called_pct']}%)")
    p(f"  SOLVER_B called: {and_gate_report['solver_b_called']} ({and_gate_report['solver_b_called_pct']}%)")
    p(f"  All SOLVER_A passed: {and_gate_report['all_solver_a_passed']}")
    p(f"  All non-SOLVER-B passed but rejected: {and_gate_report['c01_c04_all_pass_but_rejected']}")
    p(f"  All post-SOLVER passed but rejected: {and_gate_report['c07_c12_all_pass_but_rejected']}")

    with open(AND_GATE_REPORT_JSON, "w", encoding="utf-8") as f:
        json.dump(and_gate_report, f, indent=2, ensure_ascii=False)
    p(f"  AND-gate report written -> {AND_GATE_REPORT_JSON}")
    return and_gate_report

# === ШАГ 4: SCHEMA / FIELD NAME MISMATCH CHECK ===
def check_schema(rejected):
    p("ШАГ 4: Checking condition schemas for field name mismatches...")
    if not rejected:
        p("  No rejected entries")
        return {}
    expected_keys = {"condition_id", "condition_name", "passed", "details", "confidence", "data"}
    data_expected_keys = {"solver_a_answer", "solver_a_solution", "solver_a_confidence",
                          "solver_b_answer", "solver_b_solution",
                          "arbiter_answer", "arbiter_solution", "arbiter_proof",
                          "topic", "subtopic", "level", "probabilities", "target_level"}
    schema_issues = defaultdict(list)
    field_stats = Counter()
    total_conditions = 0

    for slot_key, entry in rejected.items():
        conditions = entry.get("conditions", {})
        for cid, cond in conditions.items():
            total_conditions += 1
            if not isinstance(cond, dict):
                schema_issues[f"{slot_key}/{cid}"].append(f"condition is not a dict: {type(cond)}")
                continue
            cond_keys = set(cond.keys())
            missing = expected_keys - cond_keys
            extra = cond_keys - expected_keys
            if missing:
                schema_issues[f"{slot_key}/{cid}"].append(f"missing keys: {missing}")
            if extra:
                schema_issues[f"{slot_key}/{cid}"].append(f"extra keys: {extra}")
            # Check data sub-dict
            data = cond.get("data")
            if isinstance(data, dict):
                data_keys = set(data.keys())
                # Not all data_expected_keys are required - just report unusual ones
                for k in data_keys:
                    field_stats[k] += 1
            # Track confidence type
            conf = cond.get("confidence")
            if conf is not None:
                field_stats[f"confidence_type_{type(conf).__name__}"] += 1
            # Track passed type
            passed = cond.get("passed")
            field_stats[f"passed_type_{type(passed).__name__}"] += 1

    schema_report = {
        "total_slots_checked": len(rejected),
        "total_conditions_checked": total_conditions,
        "slots_with_issues": len(schema_issues),
        "schema_issues": dict(schema_issues),
        "data_field_frequencies": dict(field_stats.most_common(50)),
        "conclusion": "",
    }

    if schema_issues:
        schema_report["conclusion"] = f"Found {len(schema_issues)} slots with schema issues"
        p(f"  WARNING: {len(schema_issues)} slots with schema issues")
    else:
        schema_report["conclusion"] = "All condition schemas appear consistent"
        p("  All condition schemas consistent")

    with open(SCHEMA_REPORT_JSON, "w", encoding="utf-8") as f:
        json.dump(schema_report, f, indent=2, ensure_ascii=False)
    p(f"  Schema report written -> {SCHEMA_REPORT_JSON}")
    return schema_report

# === ШАГ 5-6: ANALYZE ARBITER (including SOLVER_B data fallback bug) ===
def analyze_arbiter(rejected):
    p("ШАГ 5-6: Analyzing ARBITER conditions...")
    if not rejected:
        p("  No rejected entries")
        return {}
    arbiter_report = {
        "total_checked": 0,
        "arbiter_answer_fail": 0,
        "arbiter_solution_fail": 0,
        "arbiter_proof_fail": 0,
        "all_arbiter_pass": 0,
        "solver_b_not_called_arbiter_analyzed": 0,
        "solver_b_not_called_arbiter_data_uses_solver_a": 0,
        "samples": [],
    }
    for slot_key, entry in rejected.items():
        conditions = entry.get("conditions", {})
        c05 = conditions.get("c05_solver_b_answer")
        c07 = conditions.get("c07_arbiter_answer")
        c08 = conditions.get("c08_arbiter_solution")
        c09 = conditions.get("c09_arbiter_proof")

        solver_b_called = c05 is not None
        arbiter_conds = [c for c in [c07, c08, c09] if c is not None]
        if not arbiter_conds:
            continue
        arbiter_report["total_checked"] += 1

        if c07 and not c07.get("passed"):
            arbiter_report["arbiter_answer_fail"] += 1
        if c08 and not c08.get("passed"):
            arbiter_report["arbiter_solution_fail"] += 1
        if c09 and not c09.get("passed"):
            arbiter_report["arbiter_proof_fail"] += 1
        if all(c.get("passed") for c in arbiter_conds):
            arbiter_report["all_arbiter_pass"] += 1

        # Detect SOLVER_B data fallback in ARBITER
        if not solver_b_called and (c07 or c08):
            arbiter_report["solver_b_not_called_arbiter_analyzed"] += 1
            c07_data = c07.get("data", {}) if c07 else {}
            c08_data = c08.get("data", {}) if c08 else {}
            # Check if arbiter data references solver_a fields when solver_b wasn't called
            data_str = json.dumps(c07_data) + json.dumps(c08_data)
            # If we see solver_a_answer twice but no solver_b_answer, that's the fallback bug
            sa_count = data_str.count("solver_a_answer")
            sb_count = data_str.count("solver_b_answer")
            if sa_count >= 2 and sb_count == 0:
                arbiter_report["solver_b_not_called_arbiter_data_uses_solver_a"] += 1
                if len(arbiter_report["samples"]) < 5:
                    arbiter_report["samples"].append({
                        "slot_key": slot_key,
                        "finding": "ARBITER data references SOLVER_A when SOLVER_B not called",
                        "solver_a_refs": sa_count,
                        "solver_b_refs": sb_count,
                    })

    total = arbiter_report["total_checked"]
    if total > 0:
        p(f"  Total with ARBITER: {total}")
        p(f"  ARBITER answer fail: {arbiter_report['arbiter_answer_fail']} ({arbiter_report['arbiter_answer_fail']/total*100:.1f}%)")
        p(f"  ARBITER solution fail: {arbiter_report['arbiter_solution_fail']} ({arbiter_report['arbiter_solution_fail']/total*100:.1f}%)")
        p(f"  ARBITER proof fail: {arbiter_report['arbiter_proof_fail']} ({arbiter_report['arbiter_proof_fail']/total*100:.1f}%)")
        p(f"  All ARBITER pass: {arbiter_report['all_arbiter_pass']} ({arbiter_report['all_arbiter_pass']/total*100:.1f}%)")
        p(f"  SOLVER_B not called & ARBITER data uses SOLVER_A (fallback bug): {arbiter_report['solver_b_not_called_arbiter_data_uses_solver_a']}")

    with open(os.path.join(SNAPSHOT_DIR, "stage7_arbiter_report.json"), "w", encoding="utf-8") as f:
        json.dump(arbiter_report, f, indent=2, ensure_ascii=False)
    p("  ARBITER report written")
    return arbiter_report

# === ШАГ 7: TOPIC/SUBTOPIC MAPPING CHECK ===
def analyze_topic(rejected):
    p("ШАГ 7: Analyzing TOPIC/SUBTOPIC mapping...")
    if not rejected:
        p("  No rejected entries")
        return {}
    topic_report = {
        "total_checked": 0,
        "topic_mismatches": 0,
        "subtopic_mismatches": 0,
        "topic_mismatch_rate_pct": 0,
        "subtopic_mismatch_rate_pct": 0,
        "samples": [],
    }
    for slot_key, entry in rejected.items():
        conditions = entry.get("conditions", {})
        c10 = conditions.get("c10_topic_match")
        if c10 is None:
            continue
        topic_report["total_checked"] += 1
        if not c10.get("passed"):
            topic_report["topic_mismatches"] += 1
            data = c10.get("data", {})
            if len(topic_report["samples"]) < 10:
                topic_report["samples"].append({
                    "slot_key": slot_key,
                    "expected_topic": data.get("expected_topic", data.get("topic", "?")),
                    "detected_topic": data.get("detected_topic", data.get("classified_topic", "?")),
                    "expected_subtopic": data.get("expected_subtopic", data.get("subtopic", "?")),
                    "detected_subtopic": data.get("detected_subtopic", data.get("classified_subtopic", "?")),
                    "details": c10.get("details", ""),
                })

    total = topic_report["total_checked"]
    if total > 0:
        topic_report["topic_mismatch_rate_pct"] = round(topic_report["topic_mismatches"] / total * 100, 2)
        p(f"  TOPIC mismatches: {topic_report['topic_mismatches']}/{total} ({topic_report['topic_mismatch_rate_pct']}%)")

    with open(os.path.join(SNAPSHOT_DIR, "stage7_topic_report.json"), "w", encoding="utf-8") as f:
        json.dump(topic_report, f, indent=2, ensure_ascii=False)
    p("  TOPIC report written")
    return topic_report

# === ШАГ 8: LEVEL MATCH CHECK ===
def analyze_level(rejected):
    p("ШАГ 8: Analyzing LEVEL calibration...")
    if not rejected:
        p("  No rejected entries")
        return {}
    level_report = {
        "total_checked": 0,
        "level_mismatches": 0,
        "level_mismatch_rate_pct": 0,
        "level_distribution": Counter(),
        "samples": [],
    }
    for slot_key, entry in rejected.items():
        conditions = entry.get("conditions", {})
        c11 = conditions.get("c11_level_match")
        if c11 is None:
            continue
        level_report["total_checked"] += 1
        data = c11.get("data", {})
        target = data.get("target_level", data.get("level", "?"))
        level_report["level_distribution"][str(target)] += 1
        if not c11.get("passed"):
            level_report["level_mismatches"] += 1
            if len(level_report["samples"]) < 10:
                probs = data.get("probabilities", {})
                level_report["samples"].append({
                    "slot_key": slot_key,
                    "target_level": target,
                    "probabilities": probs,
                    "details": c11.get("details", ""),
                })

    total = level_report["total_checked"]
    if total > 0:
        level_report["level_mismatch_rate_pct"] = round(level_report["level_mismatches"] / total * 100, 2)
        p(f"  LEVEL mismatches: {level_report['level_mismatches']}/{total} ({level_report['level_mismatch_rate_pct']}%)")
        p(f"  Level distribution: {dict(level_report['level_distribution'])}")

    with open(os.path.join(SNAPSHOT_DIR, "stage7_level_report.json"), "w", encoding="utf-8") as f:
        json.dump(level_report, f, indent=2, ensure_ascii=False)
    p("  LEVEL report written")
    return level_report

# === ШАГ 9: DUPLICATE DETECTION CHECK ===
def analyze_duplicates(rejected):
    p("ШАГ 9: Analyzing duplicate detection...")
    if not rejected:
        p("  No rejected entries")
        return {}
    dup_report = {
        "total_checked": 0,
        "duplicate_found": 0,
        "duplicate_rate_pct": 0,
        "similarity_scores": [],
        "samples": [],
    }
    for slot_key, entry in rejected.items():
        conditions = entry.get("conditions", {})
        c12 = conditions.get("c12_duplicate_check")
        if c12 is None:
            continue
        dup_report["total_checked"] += 1
        data = c12.get("data", {})
        similarity = data.get("max_similarity", data.get("similarity", None))
        if similarity is not None:
            try:
                dup_report["similarity_scores"].append(float(similarity))
            except (ValueError, TypeError):
                pass
        if not c12.get("passed"):
            dup_report["duplicate_found"] += 1
            if len(dup_report["samples"]) < 10:
                dup_report["samples"].append({
                    "slot_key": slot_key,
                    "similarity": similarity,
                    "match_count": data.get("match_count", data.get("duplicate_count", "?")),
                    "details": c12.get("details", ""),
                })

    total = dup_report["total_checked"]
    if total > 0:
        dup_report["duplicate_rate_pct"] = round(dup_report["duplicate_found"] / total * 100, 2)
        scores = dup_report["similarity_scores"]
        if scores:
            dup_report["avg_similarity"] = round(sum(scores) / len(scores), 4)
            dup_report["max_similarity"] = round(max(scores), 4)
            dup_report["min_similarity"] = round(min(scores), 4)
        p(f"  Duplicates found: {dup_report['duplicate_found']}/{total} ({dup_report['duplicate_rate_pct']}%)")
        if scores:
            p(f"  Similarity: avg={dup_report.get('avg_similarity','?')} max={dup_report.get('max_similarity','?')}")

    with open(os.path.join(SNAPSHOT_DIR, "stage7_duplicate_report.json"), "w", encoding="utf-8") as f:
        json.dump(dup_report, f, indent=2, ensure_ascii=False)
    p("  DUPLICATE report written")
    return dup_report

# === ШАГ 10: BUILD DEBUG SAMPLES (Markdown) ===
def build_debug_samples(rejected, failure_rows):
    p("ШАГ 10: Building debug samples...")
    if not rejected:
        p("  No rejected entries, samples empty")
        return
    # Select 10 most representative samples
    # Pick: 2 with SOLVER_B not called, 2 with all SOLVER_A pass, 2 ARBITER-only fails, 4 random
    samples = []
    keys = list(rejected.keys())
    # Sort by failure count descending for diversity
    slot_fail_count = {}
    for row in failure_rows:
        slot_fail_count[row["slot_key"]] = row["total_failed"]

    # Strategy: pick diverse samples
    selected = []
    # Pick top-3 most failed
    sorted_by_fails = sorted(keys, key=lambda k: slot_fail_count.get(k, 0), reverse=True)
    for k in sorted_by_fails:
        if k not in selected:
            selected.append(k)
        if len(selected) >= 10:
            break

    with open(DEBUG_SAMPLES_MD, "w", encoding="utf-8") as f:
        f.write("# Stage 7 Debug Samples\n\n")
        f.write(f"Generated: {datetime.now().isoformat()}\n")
        f.write(f"Total rejected: {len(rejected)}\n\n")
        f.write("## Selected Samples\n\n")
        for slot_key in selected[:10]:
            entry = rejected[slot_key]
            conditions = entry.get("conditions", {})
            fails = [cid for cid in COND_ORDER if conditions.get(cid) and not conditions[cid].get("passed")]
            missing = [cid for cid in COND_ORDER if conditions.get(cid) is None]
            f.write(f"### {slot_key}\n")
            f.write(f"- **task_type**: {entry.get('task_type', '?')}\n")
            f.write(f"- **candidate_id**: {entry.get('candidate_id', '?')}\n")
            f.write(f"- **overall_accepted**: {entry.get('overall_accepted')}\n")
            f.write(f"- **started_at**: {entry.get('started_at', '?')}\n")
            f.write(f"- **completed_at**: {entry.get('completed_at', '?')}\n")
            f.write(f"- **failed conditions ({len(fails)})**: {', '.join(fails)}\n")
            f.write(f"- **missing conditions ({len(missing)})**: {', '.join(missing)}\n")
            f.write("\n#### Condition Details\n\n")
            for cid in COND_ORDER:
                cond = conditions.get(cid)
                if cond is None:
                    f.write(f"- **{cid}**: MISSING\n")
                else:
                    status = "PASS" if cond.get("passed") else "FAIL"
                    conf = cond.get("confidence", "?")
                    details = cond.get("details", "")
                    f.write(f"- **{cid}** ({COND_NAMES.get(cid, cid)}): **{status}** (conf={conf})\n")
                    if details:
                        f.write(f"  - Details: {details[:200]}\n")
            f.write("\n---\n\n")
    p(f"  Debug samples written -> {DEBUG_SAMPLES_MD}")

# === ШАГ 11: GENERATE UNIT TESTS ===
def generate_unit_tests(rejected):
    p("ШАГ 11: Generating unit tests...")
    test_lines = []
    test_lines.append("#!/usr/bin/env python")
    test_lines.append("# -*- coding: utf-8 -*-")
    test_lines.append('"""Auto-generated unit tests for Stage 7 verification pipeline."""')
    test_lines.append("import json, sys, os")
    test_lines.append("sys.path.insert(0, os.path.dirname(__file__))")
    test_lines.append("")
    test_lines.append("")
    test_lines.append("# === GOLDEN FIXTURE: known rejected candidate ===")
    test_lines.append("FIXTURE_CHECKPOINT = r"""")
    # Use first rejected entry as fixture
    if rejected:
        first_key = list(rejected.keys())[0]
        test_lines.append(json.dumps({first_key: rejected[first_key]}, indent=2, ensure_ascii=False))
    test_lines.append(""""")
    test_lines.append("")
    test_lines.append("def test_checkpoint_loads():")
    test_lines.append("    data = json.loads(FIXTURE_CHECKPOINT)")
    test_lines.append('    assert len(data) > 0, "Fixture should have at least one entry"')
    test_lines.append("")
    test_lines.append("def test_all_conditions_present():")
    test_lines.append("    data = json.loads(FIXTURE_CHECKPOINT)")
    test_lines.append("    for slot_key, entry in data.items():")
    test_lines.append("        conditions = entry.get('conditions', {})")
    test_lines.append("        for cid in [%s]:" % ", ".join(f'"{c}"' for c in COND_ORDER))
    test_lines.append("            assert cid in conditions, f'{slot_key} missing condition {cid}'")
    test_lines.append("")
    test_lines.append("def test_condition_schema():")
    test_lines.append("    data = json.loads(FIXTURE_CHECKPOINT)")
    test_lines.append('    expected_keys = {"condition_id", "condition_name", "passed", "details", "confidence", "data"}')
    test_lines.append("    for slot_key, entry in data.items():")
    test_lines.append("        for cid, cond in entry.get('conditions', {}).items():")
    test_lines.append("            assert isinstance(cond, dict), f'{slot_key}/{cid} not a dict'")
    test_lines.append("            cond_keys = set(cond.keys())")
    test_lines.append("            missing = expected_keys - cond_keys")
    test_lines.append("            assert not missing, f'{slot_key}/{cid} missing keys: {missing}'")
    test_lines.append("")
    test_lines.append("def test_solver_b_not_called_no_arbiter_fallback():")
    test_lines.append("    data = json.loads(FIXTURE_CHECKPOINT)")
    test_lines.append("    for slot_key, entry in data.items():")
    test_lines.append("        conditions = entry.get('conditions', {})")
    test_lines.append("        c05 = conditions.get('c05_solver_b_answer')")
    test_lines.append("        c07 = conditions.get('c07_arbiter_answer')")
    test_lines.append("        if c05 is None and c07 is not None:")
    test_lines.append("            c07_data = c07.get('data', {})")
    test_lines.append("            data_str = json.dumps(c07_data)")
    test_lines.append("            sa_count = data_str.count('solver_a_answer')")
    test_lines.append("            sb_count = data_str.count('solver_b_answer')")
    test_lines.append("            if sa_count >= 2 and sb_count == 0:")
    test_lines.append("                print(f'WARN: {slot_key}: ARBITER data uses SOLVER_A when SOLVER_B not called')")
    test_lines.append("")
    test_lines.append("if __name__ == '__main__':")
    test_lines.append("    test_checkpoint_loads()")
    test_lines.append("    test_all_conditions_present()")
    test_lines.append("    test_condition_schema()")
    test_lines.append("    test_solver_b_not_called_no_arbiter_fallback()")
    test_lines.append('    print("All tests passed.")')

    with open(UNIT_TEST_REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(test_lines))
    p(f"  Unit tests written -> {UNIT_TEST_REPORT}")

# === ШАГ 12: BUILD RECLASSIFICATION ===
def build_reclassification(rejected, and_gate_report):
    p("ШАГ 12: Building reclassification...")
    reclass = {
        "verified": {},
        "retry_candidates": {},
        "hard_rejected": {},
        "retry_reasoning": {},
    }
    for slot_key, entry in rejected.items():
        conditions = entry.get("conditions", {})
        c01 = conditions.get("c01_solver_a_answer")
        c02 = conditions.get("c02_solver_a_solution")
        c03 = conditions.get("c03_solver_a_leads")
        c04 = conditions.get("c04_solver_a_confidence")
        c05 = conditions.get("c05_solver_b_answer")
        c06 = conditions.get("c06_solver_b_solution")
        c07 = conditions.get("c07_arbiter_answer")
        c08 = conditions.get("c08_arbiter_solution")
        c09 = conditions.get("c09_arbiter_proof")
        c10 = conditions.get("c10_topic_match")
        c11 = conditions.get("c11_level_match")
        c12 = conditions.get("c12_duplicate_check")

        solver_a_ok = all(c.get("passed") for c in [c01, c02, c03, c04] if c is not None)
        arbiter_ok = all(c.get("passed") for c in [c07, c08, c09] if c is not None)
        topic_ok = c10 is not None and c10.get("passed")
        level_ok = c11 is not None and c11.get("passed")
        dup_ok = c12 is not None and c12.get("passed")

        # Classification logic:
        core_ok = solver_a_ok and arbiter_ok and topic_ok and level_ok and dup_ok

        if core_ok:
            # This should have passed - SOLVER_B only issue
            reclass["verified"][slot_key] = {
                **entry,
                "reclassification_reason": "All core conditions pass (SOLVER_B not required)",
            }
        elif solver_a_ok and arbiter_ok and topic_ok and level_ok:
            # SOLVER_A + ARBITER + TOPIC + LEVEL pass -> likely a dup false positive or SOLVER_B
            reclass["retry_candidates"][slot_key] = {
                **entry,
                "retry_reason": "SOLVER_A/ARBITER/TOPIC/LEVEL all pass; may be duplicate false positive",
            }
        elif not solver_a_ok:
            reclass["hard_rejected"][slot_key] = {
                **entry,
                "hard_reject_reason": "SOLVER_A conditions failed - genuine content issue",
            }
        else:
            reclass["retry_candidates"][slot_key] = {
                **entry,
                "retry_reason": "Mixed failures - retry may resolve",
            }

    # Generate retry reasoning
    reclass["retry_reasoning"] = {
        "verified_count": len(reclass["verified"]),
        "retry_count": len(reclass["retry_candidates"]),
        "hard_rejected_count": len(reclass["hard_rejected"]),
        "note": "Verified candidates can be moved directly. Retry candidates need 1 more verification pass.",
    }

    with open(RECLASSIFICATION_JSON, "w", encoding="utf-8") as f:
        json.dump(reclass, f, indent=2, ensure_ascii=False)
    p(f"  Reclassification written -> {RECLASSIFICATION_JSON}")
    p(f"    Verified (can promote): {len(reclass['verified'])}")
    p(f"    Retry candidates: {len(reclass['retry_candidates'])}")
    p(f"    Hard rejected: {len(reclass['hard_rejected'])}")
    return reclass

# === MAIN: RUN ALL DIAGNOSTIC STEPS ===
def main():
    p("=" * 60)
    p("STAGE 7 DIAGNOSTIC — 15-STEP PLAN")
    p("=" * 60)

    # Load checkpoint
    cp, verified, rejected = load_checkpoint()
    if cp is None:
        p("FATAL: Cannot proceed without checkpoint")
        return 1

    # ШАГ 1: Save snapshot (backup checkpoint, candidates, conflicts, main script)
    save_snapshot()

    # ШАГ 2: Failure matrix
    summary, rows = build_failure_matrix(rejected)

    # ШАГ 3: AND-gate analysis
    and_gate_report = check_and_gate(rejected)

    # ШАГ 4: Schema check
    schema_report = check_schema(rejected)

    # ШАГ 5-6: ARBITER analysis
    arbiter_report = analyze_arbiter(rejected)

    # ШАГ 7: TOPIC analysis
    topic_report = analyze_topic(rejected)

    # ШАГ 8: LEVEL analysis
    level_report = analyze_level(rejected)

    # ШАГ 9: DUPLICATE analysis
    dup_report = analyze_duplicates(rejected)

    # ШАГ 10: Debug samples
    build_debug_samples(rejected, rows)

    # ШАГ 11: Unit tests
    generate_unit_tests(rejected)

    # ШАГ 12: Reclassification
    reclass = build_reclassification(rejected, and_gate_report)

    # Summary
    p("=" * 60)
    p("DIAGNOSTIC COMPLETE")
    p("=" * 60)
    p(f"  Total candidates in checkpoint: {len(verified) + len(rejected)}")
    p(f"  Verified: {len(verified)}")
    p(f"  Rejected: {len(rejected)}")
    if summary:
        worst = min(summary.keys(), key=lambda k: summary[k].get("fail_rate_pct", 100))
        p(f"  Worst condition: {worst} ({summary[worst].get('fail_rate_pct', 0)}% fail rate)")
    if and_gate_report:
        p(f"  SOLVER_B not called: {and_gate_report.get('solver_b_not_called', '?')}")
        p(f"  Non-SOLVER-B all-pass but rejected: {and_gate_report.get('c01_c04_all_pass_but_rejected', '?')}")
    if reclass:
        p(f"  Can promote immediately: {len(reclass.get('verified', {}))}")
        p(f"  Retry candidates: {len(reclass.get('retry_candidates', {}))}")
        p(f"  Hard rejected: {len(reclass.get('hard_rejected', {}))}")

    p("\nAll artifacts written to: " + SNAPSHOT_DIR)
    return 0

if __name__ == "__main__":
    sys.exit(main())
