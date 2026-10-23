#!/usr/bin/env python
"""Diagnose audit status fields in the curated bank after trimming."""
import json
from collections import Counter
from pathlib import Path

BANK_PATH = "curated_bank_L1_L5_fixed.json"
OUT_PATH = "_diag_audit_status.txt"

def main():
    with open(BANK_PATH, "r", encoding="utf-8") as f:
        bank = json.load(f)

    lines = []
    lines.append(f"Total tasks in bank: {len(bank)}")
    lines.append("")

    # Audit-related fields to analyze
    fields = ["audit_mode", "decision_status", "final_court_status",
              "evidence_source", "confidence", "feature_score",
              "mechanical_mapping", "quality_score",
              "pending_live_audit", "in_duplicate_cluster"]

    for field in fields:
        c = Counter()
        has_field = 0
        no_field = 0
        for t in bank:
            if field in t:
                has_field += 1
                val = t[field]
                if isinstance(val, str):
                    c[val] += 1
                elif val is None:
                    c["<None>"] += 1
                elif isinstance(val, bool):
                    c[f"<{val}>"] += 1
                elif isinstance(val, (int, float)):
                    c[f"<{val}>"] += 1
                else:
                    c[f"<{type(val).__name__}:{val}>"] += 1
            else:
                no_field += 1

        lines.append(f"--- {field} ---")
        lines.append(f"  Has field: {has_field}")
        lines.append(f"  Missing field: {no_field}")
        if c:
            lines.append(f"  Distribution:")
            for val, cnt in c.most_common():
                pct = 100 * cnt / has_field if has_field else 0
                lines.append(f"    {repr(val)}: {cnt} ({pct:.1f}%)")
        lines.append("")

    # L1-L3 vs L4-L5 breakdown
    l1l3 = [t for t in bank if t.get("level") in (1, 2, 3) and t.get("grade") is not None]
    l4l5 = [t for t in bank if t not in l1l3]
    lines.append(f"--- Level breakdown ---")
    lines.append(f"  L1-L3 tasks: {len(l1l3)}")
    lines.append(f"  L4-L5 tasks: {len(l4l5)}")
    lines.append("")

    # Grade distribution in L1-L3
    grade_counter = Counter()
    level_counter = Counter()
    for t in l1l3:
        g = t.get("grade")
        lv = t.get("level")
        if g is not None:
            grade_counter[g] += 1
        if lv is not None:
            level_counter[lv] += 1
    lines.append("--- Grade distribution (L1-L3) ---")
    for g in sorted(grade_counter):
        lines.append(f"  Grade {g}: {grade_counter[g]} tasks")
    lines.append("")
    lines.append("--- Level distribution (L1-L3) ---")
    for lv in sorted(level_counter):
        lines.append(f"  Level {lv}: {level_counter[lv]} tasks")
    lines.append("")

    # Check for tasks that might need live audit:
    # - audit_mode == "pending" or similar
    # - decision_status suggesting review needed
    # - tasks without decision_status at all
    lines.append("--- Tasks potentially needing audit attention ---")
    needs_attention = []
    for t in bank:
        reasons = []
        ds = t.get("decision_status")
        fc = t.get("final_court_status")
        am = t.get("audit_mode")
        ev = t.get("evidence_source")

        if am is None or am == "":
            reasons.append("no audit_mode")
        if ds is None or ds == "":
            reasons.append("no decision_status")
        elif ds in ("pending", "uncertain", "needs_review", "undecided"):
            reasons.append(f"decision_status={ds}")
        if fc is None or fc == "":
            reasons.append("no final_court_status")
        elif fc in ("pending", "uncertain", "needs_review"):
            reasons.append(f"final_court_status={fc}")
        if ev is None or ev == "":
            reasons.append("no evidence_source")

        if reasons:
            needs_attention.append((t.get("original_id", "???"), reasons, t.get("grade"), t.get("level")))

    if needs_attention:
        lines.append(f"  Total: {len(needs_attention)} tasks")
        for tid, reasons, g, lv in needs_attention:
            lines.append(f"    {tid}  grade={g} level={lv}  reasons: {', '.join(reasons)}")
    else:
        lines.append("  None found - all tasks have complete audit fields")
    lines.append("")

    # Cell distribution after trim
    from collections import defaultdict
    cells = defaultdict(list)
    for t in l1l3:
        key = f"G{t['grade']}|L{t['level']}"
        cells[key].append(t)

    lines.append("--- Cell distribution after trim ---")
    for key in sorted(cells, key=lambda k: (int(k.split("|L")[1]), k)):
        tasks = cells[key]
        lines.append(f"  {key}: {len(tasks)} tasks")
        for t in tasks:
            lines.append(f"    {t.get('original_id','???')}  qs={t.get('quality_score','?')}  rank={t.get('rank_in_cell','?')}")
    lines.append("")

    # Write output
    out_path = Path(OUT_PATH)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Diagnostic report written to {OUT_PATH}")
    print(f"Total lines: {len(lines)}")
    print(f"L1-L3 tasks: {len(l1l3)}")
    print(f"Tasks needing attention: {len(needs_attention)}")

if __name__ == "__main__":
    main()
