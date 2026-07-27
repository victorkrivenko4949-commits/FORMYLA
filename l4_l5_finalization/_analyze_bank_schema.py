#!/usr/bin/env python
"""ШАГ 2: Programmatic schema analysis of curated_bank_L1_L5_fixed.json

Creates bank_schema_report.json with full key/type/frequency analysis,
grade/level/topic distributions, nested structure detection, and cell reconstruction planning.
"""
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BANK_PATH = os.path.join(SCRIPT_DIR, "..", "curated_bank_L1_L5_fixed.json")
TAXONOMY_PATH = os.path.join(SCRIPT_DIR, "..", "taxonomy_by_grade.json")
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "bank_schema_report.json")


def load_json(path, label=""):
    print(f"[{datetime.now().isoformat()}] Loading {label or path}...", flush=True)
    with open(path, 'r', encoding='utf-8-sig') as f:
        return json.load(f)


def build_topic_name_to_id_map(taxonomy):
    """Build mapping from topic name (Russian) -> Txxx code, per grade."""
    topic_name_to_id = {}
    topic_id_to_info = {}
    subtopic_name_to_index = {}

    for grade_str, grade_data in taxonomy.get("grades", {}).items():
        grade = int(grade_str)
        for theme in grade_data.get("themes", []):
            tid = theme["id"]
            tname = theme["name"]
            topic_name_to_id[(grade, tname)] = tid
            subtopics = theme.get("subtopics", [])
            topic_id_to_info[tid] = {"name": tname, "subtopics": subtopics, "grade": grade}
            for idx, sname in enumerate(subtopics):
                subtopic_name_to_index[(grade, tid, sname)] = idx

    return topic_name_to_id, topic_id_to_info, subtopic_name_to_index


def analyze_bank_schema(bank, taxonomy):
    """Complete schema analysis of the bank."""
    report = {}
    report["analysis_timestamp"] = datetime.now().isoformat()
    report["total_records"] = len(bank)

    # --- 1. Root type check ---
    report["root_type"] = type(bank).__name__

    # --- 2. All unique keys, types, frequencies, examples ---
    key_stats = defaultdict(lambda: {"count": 0, "types": set(), "null_count": 0, "examples": []})
    for record in bank:
        for k, v in record.items():
            ks = key_stats[k]
            ks["count"] += 1
            ks["types"].add(type(v).__name__)
            if v is None:
                ks["null_count"] += 1
            if len(ks["examples"]) < 3:
                ks["examples"].append(v)

    schema_fields = {}
    for k in sorted(key_stats.keys()):
        ks = key_stats[k]
        schema_fields[k] = {
            "frequency": f"{ks['count']}/{report['total_records']} ({100*ks['count']/report['total_records']:.1f}%)",
            "types": sorted(list(ks["types"])),
            "null_count": ks["null_count"],
            "sample_values": ks["examples"]
        }
    report["schema_fields"] = schema_fields
    report["unique_keys_count"] = len(schema_fields)

    # --- 3. Is record a task or cell container? ---
    # Check if records have nested "tasks" array (cell container) or flat task fields (individual task)
    has_tasks_array = any("tasks" in r for r in bank[:10])
    has_task_text = any("task_text" in r for r in bank[:10])
    has_statement = any("statement" in r for r in bank[:10])

    if has_tasks_array and not has_task_text:
        record_type = "cell_container"
    elif has_task_text or has_statement:
        record_type = "individual_task"
    else:
        record_type = "unknown"

    report["record_type"] = record_type
    report["record_type_evidence"] = {
        "sample_has_tasks_array": has_tasks_array,
        "sample_has_task_text": has_task_text,
        "sample_has_statement": has_statement
    }

    # --- 4. Grade + Level distribution ---
    grade_counter = Counter()
    level_counter = Counter()
    grade_level_counter = Counter()

    for r in bank:
        g = r.get("grade")
        lv = r.get("level")
        if g is not None:
            grade_counter[g] += 1
        if lv is not None:
            level_counter[lv] += 1
        if g is not None and lv is not None:
            grade_level_counter[(g, lv)] += 1

    report["grade_distribution"] = {str(k): v for k, v in sorted(grade_counter.items())}
    report["level_distribution"] = {str(k): v for k, v in sorted(level_counter.items())}
    report["grade_level_distribution"] = {
        f"G{g}|L{lv}": v for (g, lv), v in sorted(grade_level_counter.items())
    }

    # --- 5. Topic distribution ---
    topic_counter = Counter()
    for r in bank:
        t = r.get("topic")
        if t:
            topic_counter[t] += 1

    report["topic_distribution"] = dict(topic_counter.most_common(50))

    # --- 6. Topic -> Txxx mapping via taxonomy ---
    topic_name_to_id, topic_id_to_info, subtopic_name_to_index = build_topic_name_to_id_map(taxonomy)

    mapped_count = 0
    unmapped_topics = set()
    topic_id_counter = Counter()
    for r in bank:
        g = r.get("grade")
        t = r.get("topic")
        if g is not None and t:
            tid = topic_name_to_id.get((g, t))
            if tid:
                mapped_count += 1
                topic_id_counter[tid] += 1
            else:
                unmapped_topics.add((g, t))

    report["topic_mapping"] = {
        "total_records_with_topic": sum(topic_counter.values()),
        "mapped_to_taxonomy": mapped_count,
        "unmapped_count": len(unmapped_topics),
        "unmapped_examples": sorted([f"G{g}|{t}" for g, t in list(unmapped_topics)[:20]]),
        "topic_id_distribution": dict(topic_id_counter.most_common())
    }

    # --- 7. L4 vs L5 separation ---
    l4_records = [r for r in bank if r.get("level") == 4 or r.get("target_level") == "L4"]
    l5_records = [r for r in bank if r.get("level") == 5 or r.get("target_level") == "L5"]

    # Handle case where both L4 and L5 might match same record
    l4_only = [r for r in bank if (r.get("level") == 4 or r.get("target_level") == "L4") and not (r.get("level") == 5 or r.get("target_level") == "L5")]
    l5_only = [r for r in bank if (r.get("level") == 5 or r.get("target_level") == "L5") and not (r.get("level") == 4 or r.get("target_level") == "L4")]

    report["level_separation"] = {
        "L4_count": len(l4_records),
        "L5_count": len(l5_records),
        "L4_only": len(l4_only),
        "L5_only": len(l5_only),
        "both_L4_and_L5": len(bank) - len(l4_only) - len(l5_only)
    }

    # --- 8. Nested objects detection ---
    nested_fields = {}
    for k, ks in key_stats.items():
        if "dict" in ks["types"] or "list" in ks["types"]:
            nested_samples = [r[k] for r in bank[:5] if k in r and isinstance(r[k], (dict, list))]
            nested_fields[k] = {
                "types": sorted(list(ks["types"])),
                "sample_nested_value": nested_samples[:2] if nested_samples else None
            }
    report["nested_fields"] = nested_fields

    # --- 9. Cell reconstruction estimate ---
    unique_cells_estimate = 0
    cell_keys_possible = set()
    for r in bank:
        g = r.get("grade")
        lv = r.get("level")
        t = r.get("topic")
        if g is not None and lv is not None and t:
            tid = topic_name_to_id.get((g, t))
            if tid:
                cell_keys_possible.add((g, lv, tid))

    report["cell_reconstruction_estimate"] = {
        "unique_grade_level_topic_combinations": len(cell_keys_possible),
        "example_cell_keys": sorted([f"G{g}|L{lv}|T{tid}" for g, lv, tid in list(cell_keys_possible)[:20]])
    }

    # --- 10. Original difficulty / target_level distribution ---
    od_counter = Counter()
    tl_counter = Counter()
    for r in bank:
        od = r.get("original_difficulty")
        tl = r.get("target_level")
        if od is not None:
            od_counter[od] += 1
        if tl:
            tl_counter[tl] += 1

    report["difficulty_distribution"] = {
        "original_difficulty": dict(od_counter.most_common()),
        "target_level": dict(tl_counter.most_common())
    }

    # --- 11. Quality / confidence distribution ---
    qs_counter = Counter()
    conf_counter = Counter()
    for r in bank:
        qs = r.get("quality_score")
        conf = r.get("confidence")
        if qs is not None:
            qs_counter[qs] += 1
        if conf:
            conf_counter[conf] += 1

    report["quality_distribution"] = {
        "quality_score": dict(qs_counter.most_common()),
        "confidence": dict(conf_counter.most_common())
    }

    # --- 12. Duplicate clusters info ---
    in_dup = sum(1 for r in bank if r.get("in_duplicate_cluster"))
    dup_clusters = set()
    for r in bank:
        clusters = r.get("duplicate_clusters", [])
        if clusters:
            for c in clusters:
                if isinstance(c, dict) and "cluster_id" in c:
                    dup_clusters.add(c["cluster_id"])
                elif isinstance(c, str):
                    dup_clusters.add(c)

    report["duplicate_info"] = {
        "in_duplicate_cluster_count": in_dup,
        "unique_duplicate_cluster_ids": len(dup_clusters),
        "cluster_ids_sample": sorted(list(dup_clusters))[:10]
    }

    # --- 13. Grade-level distribution summary for report ---
    report["grade_level_summary"] = {}
    for (g, lv), cnt in sorted(grade_level_counter.items()):
        key = f"G{g}|L{lv}"
        # Count unique topics in this grade+level
        unique_topics = set()
        for r in bank:
            if r.get("grade") == g and (r.get("level") == lv or r.get("target_level") == f"L{lv}"):
                t = r.get("topic")
                if t:
                    unique_topics.add(t)
        report["grade_level_summary"][key] = {
            "task_count": cnt,
            "unique_topic_names": len(unique_topics)
        }

    return report


def analyze():
    print(f"[{datetime.now().isoformat()}] ===== BANK SCHEMA ANALYSIS START =====", flush=True)
    print(f"[{datetime.now().isoformat()}] Bank path: {BANK_PATH}", flush=True)
    print(f"[{datetime.now().isoformat()}] Taxonomy path: {TAXONOMY_PATH}", flush=True)
    print(f"[{datetime.now().isoformat()}] Output path: {OUTPUT_PATH}", flush=True)
    print(f"[{datetime.now().isoformat()}] CWD: {os.getcwd()}", flush=True)
    sys.stdout.flush()

    if not os.path.exists(BANK_PATH):
        print(f"[FATAL] Bank file not found: {BANK_PATH}", flush=True)
        sys.exit(1)

    bank = load_json(BANK_PATH, "curated_bank_L1_L5_fixed.json")
    print(f"[{datetime.now().isoformat()}] Bank loaded: {len(bank)} records", flush=True)

    taxonomy = load_json(TAXONOMY_PATH, "taxonomy_by_grade.json")
    print(f"[{datetime.now().isoformat()}] Taxonomy loaded", flush=True)

    report = analyze_bank_schema(bank, taxonomy)
    print(f"[{datetime.now().isoformat()}] Analysis complete. Writing report...", flush=True)

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)

    print(f"[{datetime.now().isoformat()}] Report written to: {OUTPUT_PATH}", flush=True)
    print(f"[{datetime.now().isoformat()}] Total records: {report['total_records']}", flush=True)
    print(f"[{datetime.now().isoformat()}] Unique keys: {report['unique_keys_count']}", flush=True)
    print(f"[{datetime.now().isoformat()}] Record type: {report['record_type']}", flush=True)
    print(f"[{datetime.now().isoformat()}] Grade distribution: {report['grade_distribution']}", flush=True)
    print(f"[{datetime.now().isoformat()}] Level distribution: {report['level_distribution']}", flush=True)
    print(f"[{datetime.now().isoformat()}] Mapped to taxonomy: {report['topic_mapping']['mapped_to_taxonomy']}", flush=True)
    print(f"[{datetime.now().isoformat()}] Cell reconstruction estimate: {report['cell_reconstruction_estimate']['unique_grade_level_topic_combinations']} unique GLT combinations", flush=True)
    print(f"[{datetime.now().isoformat()}] ===== BANK SCHEMA ANALYSIS END =====", flush=True)


if __name__ == "__main__":
    analyze()
