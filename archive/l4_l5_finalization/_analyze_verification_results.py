#!/usr/bin/env python
"""Analyze Stage 7 verification results from checkpoint to understand rejection patterns."""
import json
import sys
from collections import Counter, defaultdict

CHECKPOINT_PATH = "l4_l5_finalization/stage7_checkpoint.json"
CANDIDATES_PATH = "l4_l5_finalization/stage6_candidates.json"

def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def analyze():
    checkpoint = load_json(CHECKPOINT_PATH)
    candidates = load_json(CANDIDATES_PATH)

    rejected = checkpoint.get("rejected", {})
    verified = checkpoint.get("verified", {})

    print(f"Verified candidates: {len(verified)}")
    print(f"Rejected candidates: {len(rejected)}")
    print(f"Total in candidates file: {len(candidates.get('candidates', {}))}")
    print()

    # Rejection reason breakdown
    math_rejected = 0
    topic_rejected = 0
    level_rejected = 0
    dup_rejected = 0
    error_rejected = 0
    math_accepted_but_classifier_failed = 0

    # Detailed stats
    solver_a_statuses = Counter()
    solver_b_called = 0
    solver_b_confirmed = 0
    arbiter_statuses = Counter()
    topic_statuses = Counter()
    topic_match_count = 0
    subtopic_match_count = 0
    level_statuses = Counter()
    level_match_count = 0
    dup_statuses = Counter()
    dup_confirmed = 0
    math_accepted_count = 0

    # Per-slot analysis
    slot_details = []

    for slot_key, data in sorted(rejected.items(), key=lambda x: int(x[0].split("_")[1])):
        verifiers = data.get("verifiers", {})

        # Check if error-based rejection
        if "error" in data:
            error_rejected += 1
            slot_details.append({
                "slot": slot_key,
                "reason": "ERROR",
                "error": data["error"]
            })
            continue

        # Get verifier statuses
        sa = verifiers.get("solver_a", {})
        sb = verifiers.get("solver_b", {})
        arb = verifiers.get("arbiter", {})
        topic = verifiers.get("topic", {})
        level_v = verifiers.get("level", {})
        dup = verifiers.get("duplicate", {})

        sa_status = sa.get("solver_a_status", "unknown")
        solver_a_statuses[sa_status] += 1

        if sb:
            solver_b_called += 1
            sb_status = sb.get("solver_b_status", "unknown")
            if sb_status == "confirmed":
                solver_b_confirmed += 1

        arb_status = arb.get("arbiter_status", "unknown")
        if arb_status != "unknown":
            arbiter_statuses[arb_status] += 1

        math_accepted = data.get("math_accepted", False)
        if math_accepted:
            math_accepted_count += 1

        topic_status = topic.get("topic_status", "unknown")
        topic_statuses[topic_status] += 1
        topic_match = topic.get("topic_match", False)
        subtopic_match = topic.get("subtopic_match", False)
        if topic_match:
            topic_match_count += 1
        if subtopic_match:
            subtopic_match_count += 1

        level_status = level_v.get("level_status", "unknown")
        level_statuses[level_status] += 1
        level_match = level_v.get("level_match", False)
        if level_match:
            level_match_count += 1

        dup_status = dup.get("dup_status", "unknown")
        dup_statuses[dup_status] += 1
        if dup_status == "confirmed":
            dup_confirmed += 1

        # Determine rejection category
        if not math_accepted:
            math_rejected += 1
            reason_detail = "math"
        elif topic_status == "disputed":
            topic_rejected += 1
            reason_detail = "topic"
            math_accepted_but_classifier_failed += 1
        elif level_status == "disputed":
            level_rejected += 1
            reason_detail = "level"
            math_accepted_but_classifier_failed += 1
        elif dup_status != "confirmed":
            dup_rejected += 1
            reason_detail = "dup"
            math_accepted_but_classifier_failed += 1
        else:
            reason_detail = "unknown"

        slot_details.append({
            "slot": slot_key,
            "reason": reason_detail,
            "math_accepted": math_accepted,
            "sa_status": sa_status,
            "arb_status": arb_status,
            "topic_status": topic_status,
            "topic_match": topic_match,
            "subtopic_match": subtopic_match,
            "subtopic_confidence": topic.get("subtopic_confidence", 0),
            "level_status": level_status,
            "level_match": level_match,
            "level_confidence": level_v.get("level_confidence", 0),
            "estimated_level": level_v.get("estimated_level", "?"),
            "dup_status": dup_status,
            "max_similarity": dup.get("max_similarity", 0),
        })

    # Print summary
    print("=" * 70)
    print("REJECTION BREAKDOWN")
    print("=" * 70)
    print(f"  Math rejected (SOLVER A/ARBITER disagree):      {math_rejected}")
    print(f"  Topic rejected (subtopic mismatch):              {topic_rejected}")
    print(f"  Level rejected (level mismatch):                 {level_rejected}")
    print(f"  Duplicate rejected:                              {dup_rejected}")
    print(f"  Error-based rejection:                           {error_rejected}")
    print(f"  Math accepted but failed classifiers:            {math_accepted_but_classifier_failed}")
    print()

    print("=" * 70)
    print("VERIFIER STATUS COUNTS")
    print("=" * 70)
    print(f"  SOLVER A statuses:          {dict(solver_a_statuses)}")
    print(f"  SOLVER B called:            {solver_b_called}")
    print(f"  SOLVER B confirmed:         {solver_b_confirmed}")
    print(f"  ARBITER statuses:           {dict(arbiter_statuses)}")
    print(f"  Math accepted:              {math_accepted_count}")
    print(f"  TOPIC statuses:             {dict(topic_statuses)}")
    print(f"  TOPIC match:                {topic_match_count}")
    print(f"  SUBTOPIC match:             {subtopic_match_count}")
    print(f"  LEVEL statuses:             {dict(level_statuses)}")
    print(f"  LEVEL match:                {level_match_count}")
    print(f"  DUP statuses:               {dict(dup_statuses)}")
    print(f"  DUP confirmed:              {dup_confirmed}")
    print()

    # Per-slot details table
    print("=" * 140)
    print(f"{'Slot':>8} | {'Reason':>10} | {'Math':>5} | {'SA':>12} | {'ARB':>12} | {'Topic':>8} | {'SubT':>6} | {'ST_Cnf':>7} | {'Level':>7} | {'LvlMt':>7} | {'LvCnf':>7} | {'EstLv':>6} | {'Dup':>6}")
    print("-" * 140)
    for d in slot_details:
        print(f"{d['slot']:>8} | {d['reason']:>10} | {str(d['math_accepted']):>5} | {d['sa_status']:>12} | {d['arb_status']:>12} | {d['topic_status']:>8} | {str(d['subtopic_match']):>6} | {d['subtopic_confidence']:>7.2f} | {d['level_status']:>7} | {str(d['level_match']):>7} | {d['level_confidence']:>7.2f} | {d['estimated_level']:>6} | {d['dup_status']:>6}")
    print()

    # Most common failure patterns
    print("=" * 70)
    print("COMMON FAILURE PATTERNS")
    print("=" * 70)

    # Pattern: math_rejected - what does SOLVER A say?
    if math_rejected > 0:
        print(f"\n1. Math-rejected candidates ({math_rejected} slots):")
        for d in slot_details:
            if d['reason'] == 'math':
                try:
                    slot_data = rejected[d['slot']]
                    sa = slot_data.get('verifiers', {}).get('solver_a', {})
                    sa_answer = sa.get('solver_answer', '?')[:80]
                    sa_conf = sa.get('solver_confidence', '?')
                    # Get candidate answer from candidates file
                    cand = candidates.get('candidates', {}).get(d['slot'], {})
                    cand_answer = cand.get('answer', '?')[:80]
                    print(f"    {d['slot']}: SA={sa_answer} (conf={sa_conf}) | Candidate={cand_answer}")
                except Exception as e:
                    print(f"    {d['slot']}: error reading data: {e}")

    # Pattern: level mismatch
    level_mismatches = [d for d in slot_details if d['reason'] == 'level']
    if level_mismatches:
        print(f"\n2. Level-rejected candidates ({len(level_mismatches)} slots):")
        for d in level_mismatches:
            print(f"    {d['slot']}: estimated={d['estimated_level']}, confidence={d['level_confidence']:.2f}")

    # Pattern: topic mismatch
    topic_mismatches = [d for d in slot_details if d['reason'] == 'topic']
    if topic_mismatches:
        print(f"\n3. Topic-rejected candidates ({len(topic_mismatches)} slots):")
        for d in topic_mismatches:
            print(f"    {d['slot']}: topic_match={d['topic_match']}, subtopic_match={d['subtopic_match']}, subtopic_confidence={d['subtopic_confidence']:.2f}")

    # Save detailed report
    report_path = "l4_l5_finalization/stage7_rejection_analysis.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({
            "total_verified": len(verified),
            "total_rejected": len(rejected),
            "math_rejected": math_rejected,
            "topic_rejected": topic_rejected,
            "level_rejected": level_rejected,
            "dup_rejected": dup_rejected,
            "error_rejected": error_rejected,
            "math_accepted_but_classifier_failed": math_accepted_but_classifier_failed,
            "slot_details": slot_details
        }, f, indent=2, ensure_ascii=False)
    print(f"\nDetailed report saved to {report_path}")

if __name__ == "__main__":
    analyze()
