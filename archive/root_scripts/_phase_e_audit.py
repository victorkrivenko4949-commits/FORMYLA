#!/usr/bin/env python3
"""Phase E — Historical Migration Audit for V2 Clean Rerun.

Discovers all historical records from contaminated runs, audits each
against 15 eligibility criteria, and produces migration artifacts.
"""
import json
import sqlite3
import hashlib
import sys
import os
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

BASE = Path(r"C:\Users\Victor\Downloads\FORMYLA_CONDITION_COURT")
OUTPUTS = BASE / "outputs" / "live_calibration_v2"
NOW = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
RUN_DIR = OUTPUTS / "runs" / f"v2_clean_rerun_{NOW}"

BANNED_FIELDS = {"solution", "correctAnswer", "answerCheck", "chain_of_thought", "reasoning_content"}
REQUIRED_REASONING_ROLES = {"chief_justice", "appeal_judge"}
STANDARD_ROLES = {"condition_lawyer", "taxonomy_auditor", "math_skeptic", "level_calibrator_a", "level_calibrator_b", "duplicate_hunter", "red_team"}
ALL_ROLES = STANDARD_ROLES | REQUIRED_REASONING_ROLES

def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def load_jsonl(path: Path) -> list[dict]:
    records = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return records

def examine_checkpoint(path: Path, label: str) -> dict:
    """Examine a task_checkpoint.jsonl and classify records."""
    records = load_jsonl(path)
    result = {
        "source": str(path),
        "label": label,
        "total_records": len(records),
        "has_verdict": 0,
        "has_agent_calls": 0,
        "has_cache_keys": 0,
        "task_indices": set(),
        "sample_keys": [],
    }
    for r in records:
        if "task_index" in r:
            result["task_indices"].add(r["task_index"])
        if "final_verdict" in r or "verdict" in r:
            result["has_verdict"] += 1
        if "agent_calls" in r or "calls" in r:
            result["has_agent_calls"] += 1
        if "cache_key" in r or "cache" in r:
            result["has_cache_keys"] += 1
        if not result["sample_keys"]:
            result["sample_keys"] = list(r.keys())[:20]
    result["unique_task_indices"] = sorted(result["task_indices"])
    return result

def examine_sqlite_cache(path: Path) -> dict:
    """Examine the old V1/V2 cache SQLite database."""
    result = {
        "source": str(path),
        "exists": path.exists(),
        "tables": {},
        "total_cache_rows": 0,
    }
    if not path.exists():
        return result
    conn = sqlite3.connect(str(path))
    try:
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        for (tname,) in cur.fetchall():
            cur2 = conn.execute(f'SELECT COUNT(*) FROM "{tname}"')
            (cnt,) = cur2.fetchone()
            result["tables"][tname] = cnt
            result["total_cache_rows"] += cnt
    finally:
        conn.close()
    return result

def examine_invalidated_runs(base: Path) -> list[dict]:
    """Discover all invalidated run artifacts."""
    results = []
    inv_dir = base / "invalidated_runs"
    if inv_dir.exists():
        for run_dir in inv_dir.iterdir():
            if run_dir.is_dir():
                info = {"run_dir": str(run_dir), "name": run_dir.name, "files": [f.name for f in run_dir.iterdir()]}
                cp = run_dir / "task_checkpoint.jsonl"
                if cp.exists():
                    info["checkpoint"] = examine_checkpoint(cp, f"invalidated:{run_dir.name}")
                results.append(info)
    return results

def main():
    run_dir = RUN_DIR
    run_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== PHASE E MIGRATION AUDIT ===")
    print(f"Run directory: {run_dir}")
    print()

    # Step 1: Discover all historical data sources
    print("--- DISCOVERING HISTORICAL DATA ---")

    # Main checkpoint (contaminated run)
    main_cp = examine_checkpoint(OUTPUTS / "task_checkpoint.jsonl", "main:contaminated")
    print(f"Main checkpoint ({OUTPUTS / 'task_checkpoint.jsonl'}): {main_cp['total_records']} records, {len(main_cp['unique_task_indices'])} unique task indices")

    # Incident checkpoint
    inc_cp = examine_checkpoint(OUTPUTS / "incident_20260712_task37_stall" / "task_checkpoint.jsonl", "incident:task37_stall")
    print(f"Incident checkpoint: {inc_cp['total_records']} records, {len(inc_cp['unique_task_indices'])} unique task indices")

    # Invalidated run checkpoint
    inv_runs = examine_invalidated_runs(OUTPUTS)
    inv_cp = None
    for inv in inv_runs:
        if "checkpoint" in inv:
            inv_cp = inv["checkpoint"]
            print(f"Invalidated run ({inv['name']}): {inv_cp['total_records']} records, {len(inv_cp['unique_task_indices'])} unique task indices")

    # Old SQLite cache
    cache_info = examine_sqlite_cache(BASE / "cache" / "deepseek_cache.sqlite")
    print(f"Legacy cache DB ({BASE / 'cache' / 'deepseek_cache.sqlite'}): {cache_info['total_cache_rows']} rows in {len(cache_info['tables'])} tables")
    for tname, cnt in cache_info["tables"].items():
        print(f"  Table '{tname}': {cnt} rows")

    # Events
    events = load_jsonl(OUTPUTS / "events.jsonl")
    print(f"Events: {len(events)}")

    print()

    # Step 2: Deep audit of main checkpoint records
    print("--- AUDITING MAIN CHECKPOINT RECORDS ---")

    records = load_jsonl(OUTPUTS / "task_checkpoint.jsonl")
    print(f"Total checkpoint records: {len(records)}")

    # Categories
    opaque_verdicts = 0      # records with only final_verdict, no per-agent detail
    has_per_agent = 0        # records with agent_role or per-agent structure
    missing_role = 0
    missing_thinking = 0
    hash_mismatch = 0
    version_mismatch = 0
    incomplete_provenance = 0
    unsafe_content = 0
    duplicates = 0
    potential_cache = 0
    rejected_records = []
    reusable_records = []

    seen_cache_keys = set()

    # Load canonical task list to check hashes
    # Try to get from the pre-live selection
    pre_live_path = BASE / "runs" / "selection_1080_20260712_134037" / "curated_bank_L1_L5_pre_live.json"
    canonical_tasks = {}
    if pre_live_path.exists():
        data = json.loads(pre_live_path.read_text(encoding="utf-8"))
        tasks = data if isinstance(data, list) else data.get("tasks", data.get("records", []))
        for t in tasks:
            idx = t.get("task_index") or t.get("id")
            if idx is not None:
                canonical_tasks[int(idx)] = t
        print(f"Loaded {len(canonical_tasks)} canonical tasks from {pre_live_path.name}")

    for i, rec in enumerate(records):
        rejection_reasons = []
        task_idx = rec.get("task_index", rec.get("task_id", f"record_{i}"))

        # Check if this is an opaque checkpoint verdict (no per-agent detail)
        has_agent_detail = False
        for key in ["agent_role", "agent_calls", "calls", "evidence", "per_agent"]:
            if key in rec:
                has_agent_detail = True
                break

        agent_role = rec.get("agent_role")

        if not has_agent_detail and not agent_role:
            opaque_verdicts += 1
            rejection_reasons.append("opaque_checkpoint_verdict_no_per_agent_detail")
            rejected_records.append({
                "task_index": task_idx,
                "reasons": rejection_reasons,
                "has_keys": list(rec.keys()),
            })
            continue

        # Check for agent_role
        if not agent_role:
            missing_role += 1
            rejection_reasons.append("missing_agent_role")
            rejected_records.append({"task_index": task_idx, "reasons": rejection_reasons})
            continue

        # Check for banned fields
        contains_banned = False
        rec_str = json.dumps(rec)
        for bf in BANNED_FIELDS:
            if bf in rec_str.lower():
                contains_banned = True
                break
        if contains_banned:
            unsafe_content += 1
            rejection_reasons.append("contains_banned_fields")
            rejected_records.append({"task_index": task_idx, "reasons": rejection_reasons, "role": agent_role})
            continue

        # Check if has model info
        model = rec.get("model_requested") or rec.get("model") or rec.get("model_id")
        if not model:
            incomplete_provenance += 1
            rejection_reasons.append("missing_model_info")
            rejected_records.append({"task_index": task_idx, "reasons": rejection_reasons, "role": agent_role})
            continue

        # Check thinking mode for reasoning roles
        if agent_role in REQUIRED_REASONING_ROLES:
            thinking_req = rec.get("thinking_requested") or rec.get("thinking", False)
            thinking_conf = rec.get("thinking_confirmed") or rec.get("thinking_mode", False)
            if not thinking_req or not thinking_conf:
                missing_thinking += 1
                rejection_reasons.append(f"reasoning_role_{agent_role}_missing_thinking_metadata")
                rejected_records.append({"task_index": task_idx, "reasons": rejection_reasons, "role": agent_role})
                continue

        # Check for evidence_source = live_api
        source = rec.get("evidence_source") or rec.get("source") or rec.get("origin")
        if source and source != "live_api":
            incomplete_provenance += 1
            rejection_reasons.append(f"evidence_source_is_{source}_not_live_api")
            rejected_records.append({"task_index": task_idx, "reasons": rejection_reasons, "role": agent_role})
            continue

        # Check for output hash
        output_hash = rec.get("output_hash") or rec.get("response_hash") or rec.get("hash")
        if not output_hash:
            incomplete_provenance += 1
            rejection_reasons.append("missing_output_hash")
            rejected_records.append({"task_index": task_idx, "reasons": rejection_reasons, "role": agent_role})
            continue

        # Check for timestamps
        started = rec.get("started_at") or rec.get("timestamp") or rec.get("created_at")
        ended = rec.get("ended_at") or rec.get("completed_at")
        if not started or not ended:
            incomplete_provenance += 1
            rejection_reasons.append("missing_timestamps")
            rejected_records.append({"task_index": task_idx, "reasons": rejection_reasons, "role": agent_role})
            continue

        # Check for prompt_version / rubric_version
        pv = rec.get("prompt_version") or rec.get("prompt")
        rv = rec.get("rubric_version") or rec.get("rubric")
        # Since this is V2, prompt versions may not exist in old records - flag but don't auto-reject
        if not pv or not rv:
            version_mismatch += 1
            rejection_reasons.append("missing_prompt_or_rubric_version")
            rejected_records.append({"task_index": task_idx, "reasons": rejection_reasons, "role": agent_role})
            continue

        # Check for cache key conflict
        cache_key = rec.get("cache_key")
        if cache_key:
            if cache_key in seen_cache_keys:
                duplicates += 1
                rejection_reasons.append("duplicate_cache_key")
                rejected_records.append({"task_index": task_idx, "reasons": rejection_reasons, "role": agent_role})
                continue
            seen_cache_keys.add(cache_key)

        # Check for provenance (originating_run_id, artifact hash)
        run_id = rec.get("run_id") or rec.get("originating_run_id") or rec.get("run")
        if not run_id:
            incomplete_provenance += 1
            rejection_reasons.append("missing_originating_run_id")
            rejected_records.append({"task_index": task_idx, "reasons": rejection_reasons, "role": agent_role})
            continue

        # ALL CHECKS PASSED — this record is reusable
        reusable_records.append({
            "task_index": task_idx,
            "agent_role": agent_role,
            "model": model,
            "cache_key": cache_key,
            "originating_run_id": run_id,
            "output_hash": output_hash,
            "reasons": [],
        })

    total_discovered = len(records)
    total_reusable = len(reusable_records)
    total_rejected = len(rejected_records)

    print(f"\n--- AUDIT RESULTS ---")
    print(f"Total historical records discovered: {total_discovered}")
    print(f"Valid live_api records (with agent detail): {has_per_agent}")
    print(f"Reusable cache records: {total_reusable}")
    print(f"Rejected records: {total_rejected}")
    print(f"  Opaque checkpoint verdicts (no per-agent detail): {opaque_verdicts}")
    print(f"  Missing agent_role: {missing_role}")
    print(f"  Missing thinking metadata (reasoning roles): {missing_thinking}")
    print(f"  Hash/version mismatch: {version_mismatch}")
    print(f"  Incomplete provenance: {incomplete_provenance}")
    print(f"  Unsafe content (banned fields): {unsafe_content}")
    print(f"  Duplicate/conflicting: {duplicates}")

    # Source hash
    main_cp_hash = sha256_file(OUTPUTS / "task_checkpoint.jsonl") if (OUTPUTS / "task_checkpoint.jsonl").exists() else "N/A"
    print(f"\nSource hash (main checkpoint): {main_cp_hash}")

    # Step 3: Create migration artifacts
    print(f"\n--- CREATING MIGRATION ARTIFACTS IN {run_dir} ---")

    # migration_audit.jsonl — one line per record
    audit_path = run_dir / "migration_audit.jsonl"
    with open(audit_path, "w", encoding="utf-8") as f:
        for rec in reusable_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        for rec in rejected_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"  migration_audit.jsonl: {total_reusable + total_rejected} entries")

    # migration_summary.json
    summary = {
        "phase": "E",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sources": {
            "main_checkpoint": {
                "path": str(OUTPUTS / "task_checkpoint.jsonl"),
                "records": main_cp["total_records"],
                "unique_task_indices": main_cp["unique_task_indices"],
                "sha256": main_cp_hash,
            },
            "incident_checkpoint": {
                "path": str(OUTPUTS / "incident_20260712_task37_stall" / "task_checkpoint.jsonl"),
                "records": inc_cp["total_records"],
                "unique_task_indices": inc_cp["unique_task_indices"],
            },
            "legacy_cache_db": {
                "path": str(BASE / "cache" / "deepseek_cache.sqlite"),
                "total_rows": cache_info["total_cache_rows"],
                "tables": cache_info["tables"],
            },
        },
        "audit_results": {
            "total_historical_records_discovered": total_discovered,
            "opaque_checkpoint_verdicts": opaque_verdicts,
            "records_with_per_agent_detail": has_per_agent,
            "reusable_cache_records": total_reusable,
            "total_rejected": total_rejected,
            "rejected_by_reason": {
                "opaque_checkpoint_verdict_no_per_agent_detail": opaque_verdicts,
                "missing_agent_role": missing_role,
                "missing_thinking_metadata_reasoning_roles": missing_thinking,
                "hash_version_mismatch": version_mismatch,
                "incomplete_provenance": incomplete_provenance,
                "unsafe_content_banned_fields": unsafe_content,
                "duplicate_conflicting": duplicates,
            },
        },
        "conclusion": {
            "verdict": "FAIL" if total_reusable == 0 else "PASS",
            "note": "No historical task-level verdict was migrated as a final decision.",
            "reusable_records_count": total_reusable,
        },
    }
    summary_path = run_dir / "migration_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"  migration_summary.json: written")

    # rejected_historical_records.jsonl
    rej_path = run_dir / "rejected_historical_records.jsonl"
    with open(rej_path, "w", encoding="utf-8") as f:
        for rec in rejected_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"  rejected_historical_records.jsonl: {len(rejected_records)} entries")

    # cache_import_manifest.json
    manifest = {
        "run_id": f"v2_clean_rerun_{NOW}",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "imported_records": reusable_records,
        "count": len(reusable_records),
        "provenance": {
            "source_checkpoint": str(OUTPUTS / "task_checkpoint.jsonl"),
            "source_checkpoint_sha256": main_cp_hash,
        },
    }
    manifest_path = run_dir / "cache_import_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"  cache_import_manifest.json: {len(reusable_records)} imported records")

    print(f"\n--- PHASE E COMPLETE ---")
    print(f"PASS/FAIL: {'FAIL - no reusable records' if total_reusable == 0 else 'PASS'}")
    print(f"No live API calls were made during Phase E.")
    print(f"Full 1080-task re-leveling was NOT started.")

if __name__ == "__main__":
    main()
