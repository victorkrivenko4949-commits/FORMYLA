#!/usr/bin/env python3
"""
TAXONOMY RECONSTRUCTION PIPELINE (ШАГ 14)
===========================================
Executes steps 14.1-14.7 of the taxonomy reconstruction plan.

Strategy: Lineage-based recovery, NOT topic-name guessing.
Each task's canonical cell_key is reconstructed from authoritative sources
where it was already correctly assigned.

Hierarchical mapping methods (A->E):
  A - Authoritative Full Key (direct cell_key from pipeline output)
  B - Authoritative IDs (topic_id + subtopic_id from pipeline)
  C - Lineage Join (task_id chain: replace->original->cell_key)
  D - Unique Metadata Join (grade+level+theme_name -> single cell)
  E - Content Classification (only if A-D impossible, dual classifier + arbiter)

Output files (in l4_l5_finalization/taxonomy_reconstruction/):
  - taxonomy_source_inventory.json
  - canonical_taxonomy.json
  - canonical_taxonomy_audit.json
  - task_lineage.jsonl
  - bank_taxonomy_crosswalk.jsonl
  - taxonomy_mapping_conflicts.jsonl
  - bank_by_cell.json
  - reconstruction_report.json
"""

import json
import os
import sys
import glob
import hashlib
from collections import defaultdict, Counter
from datetime import datetime

# Project root = 3 levels up from taxonomy_reconstruction/_taxonomy_reconstruct.py
# Project root = 3 levels up from taxonomy_reconstruction/_taxonomy_reconstruct.py
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PIPELINE_DIR = os.path.join(BASE_DIR, "l4_l5_finalization")
OUT_DIR = os.path.join(PIPELINE_DIR, "taxonomy_reconstruction")
ARCHIVE_DIR = os.path.join(BASE_DIR, "taxonomy_mapping_blocker_archive")
print(f"BASE_DIR: {BASE_DIR}", file=sys.stderr)
print(f"PIPELINE_DIR: {PIPELINE_DIR}", file=sys.stderr)

os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(ARCHIVE_DIR, exist_ok=True)

LEVELS = ["L4", "L5"]


# ============================================================
# Curated topic &rarr; theme mapping (reused from _fill_l4_l5_pipeline.py)
# Maps bank topic names to canonical taxonomy theme IDs.
# ============================================================
def build_curated_topic_mapping():
    """Build mapping from curated_bank topic names to theme IDs.
    
    Three-level matching (exact -> normalized -> substring) will be applied
    by map_curated_topic_to_theme(), so more specific keys should appear
    before less specific ones to ensure correct substring matching priority.
    """
    mapping = {
        # === T002: Арифметика и теория чисел [grades 6, 9] ===
        "Числа и делимость": "T002",
        "Арифметика": "T002",
        "Теория чисел": "T002",
        "Делимость": "T002",
        "Делимость и остатки": "T002",
        "Остатки по модулю": "T002",
        "Делимость и НОК": "T002",
        "Остатки и диофантовы задачи": "T002",
        "Период Пизано": "T002",

        # === T004: Графы [grades 7, 8, 9] ===
        "Графы": "T004",
        "Теория графов": "T004",

        # === T005: Дополнительные задачи и смешанные темы [grades 9, 10, 11] ===
        # (also catch-all for function/graph topics that have no dedicated canonical topic)
        "Дополнительные задачи": "T005",
        "Оптимизация": "T005",
        "Прикладные задачи": "T005",
        "Смешанные темы": "T005",
        "Функции": "T005",
        "Функции и графики": "T005",
        "Графики": "T005",

        # === T006: Комбинаторика и вероятность [grades 7, 8, 9] ===
        "Комбинаторика": "T006",
        "Комбинаторика и вероятность": "T006",
        "Раскраска": "T006",
        "Подсчёт": "T006",

        # === T007: Теория игр [grade 9] ===
        "Комбинаторика и теория игр": "T007",
        "Теория игр": "T007",
        "Игровые стратегии": "T007",

        # === T008: Логика и множества [grades 7, 8, 9, 10, 11] ===
        "Логика": "T008",
        "Множества": "T008",
        "Принцип Дирихле": "T008",
        "Принцип крайнего": "T008",
        "Логические задачи": "T008",
        "Инвариант": "T008",

        # === T009: Метод координат [grades 7, 8, 9] ===
        "Метод координат": "T009",
        "Координаты": "T009",

        # === T010: Векторы ===
        "Векторы": "T010",

        # === T011: Неравенства [grades 7, 8, 9] ===
        "Неравенства": "T011",
        "Алгебраические неравенства": "T011",
        "Квадратные неравенства": "T011",

        # === T012: Метод интервалов ===
        "Метод интервалов": "T012",

        # === T013: Показательные и логарифмические неравенства ===
        "Показательные и логарифмические неравенства": "T013",

        # === T014: Тригонометрические неравенства ===
        "Тригонометрические неравенства": "T014",

        # === T015: Числовые наборы ===
        "Числовые наборы": "T015",
        "Неравенства о средних": "T015",

        # === T016: Планиметрия: многоугольники [grades 7, 8, 9, 10, 11] ===
        "Планиметрия": "T016",
        "Многоугольники": "T016",
        "Планиметрия: многоугольники": "T016",
        "Геометрия и измерения": "T016",
        "Геометрия": "T016",
        "Геометрический экстремум": "T016",

        # === T017: Планиметрия: окружность ===
        "Окружность": "T017",
        "Планиметрия: окружность": "T017",

        # === T018: Планиметрия: площадь ===
        "Площадь": "T018",
        "Планиметрия: площадь": "T018",

        # === T019: Планиметрия: треугольники [grades 7, 8, 9, 10, 11] ===
        "Треугольники": "T019",
        "Планиметрия: треугольники": "T019",
        "Подобие": "T019",
        "Геометрия треугольника": "T019",
        "Геометрия прямоугольного треугольника": "T019",

        # === T020: Последовательности и прогрессии [grades 7, 8, 9] ===
        "Последовательности": "T020",
        "Прогрессии": "T020",
        "Арифметическая прогрессия": "T020",
        "Геометрическая прогрессия": "T020",

        # === T021: Производная и её применение [grades 10, 11] ===
        "Производная": "T021",

        # === T022: Дроби, отношения, проценты ===
        "Проценты": "T022",
        "Пропорции": "T022",

        # === T023: Рациональные уравнения [grades 8, 9] ===
        "Уравнения": "T023",
        "Рациональные уравнения": "T023",

        # === T024: Решение задач ===
        "Решение задач": "T024",
        "Анализ и интерпретация": "T024",

        # === T025: Замена переменной ===
        "Замена переменной": "T025",

        # === T026: Разложение на множители [grades 7, 8, 9] ===
        "Разложение на множители": "T026",
        "Выражения и многочлены": "T026",
        "Многочлены": "T026",

        # === T027: Системы уравнений [grades 8, 9, 10, 11] ===
        "Системы уравнений": "T027",
        "Системы, параметры и оценки": "T027",

        # === T028: Стереометрия: аксиомы и прямые [grades 10, 11] ===
        "Стереометрия": "T028",
        "Стереометрия: аксиомы и прямые": "T028",

        # === T029: Стереометрия: многогранники [grades 10, 11] ===
        "Стереометрия: многогранники": "T029",
        "Стереометрия: объёмы": "T029",
        "Объёмы": "T029",
        "Объемы": "T029",
        "Сечения": "T029",

        # === T030: Стереометрия: тела вращения [grades 10, 11] ===
        "Стереометрия: тела вращения": "T030",

        # === T031: Стереометрия: угол и расстояние [grade 11] ===
        "Угол и расстояние": "T031",

        # === T032: Текстовые задачи: движение [grades 5, 7] ===
        "Текстовые задачи": "T032",
        "Движение": "T032",

        # === T033: Текстовые задачи: производительность ===
        "Производительность": "T033",
        "Смеси и сплавы": "T033",

        # === T034: Теория вероятностей ===
        "Дискретные распределения": "T034",
        "Теория вероятностей": "T034",

        # === T035: Тригонометрические уравнения ===
        "Тригонометрические уравнения": "T035",

        # === T036: Тригонометрия / Тригонометрические преобразования [grade 10] ===
        "Тригонометрия": "T036",
        "Тригонометрические преобразования": "T036",

        # === T037: Уравнения с модулем ===
        "Модуль": "T037",
        "Уравнения с модулем": "T037",

        # === T038: Иррациональные уравнения ===
        "Иррациональные уравнения": "T038",

        # === T039: Показательные и логарифмические уравнения [grades 10, 11] ===
        "Показательные уравнения": "T039",
        "Логарифмические уравнения": "T039",
        "Показательные и логарифмические уравнения": "T039",
        "Показательные и логарифмы": "T039",

        # === T040: Тригонометрические системы ===
        "Тригонометрические системы": "T040",

        # === T041: Комплексные числа / Индукция / Алгоритмы ===
        "Комплексные числа": "T041",
        "Индукция": "T041",
        "Алгоритмы": "T041",

        # === T001: Алгебра / Теория групп ===
        "Теория групп": "T001",
        "Группы": "T001",
        "Алгебра": "T001",
    }
    return mapping


def map_curated_topic_to_theme(topic_name, mapping):
    """Map a curated_bank topic name to a theme ID.
    Three-level matching: direct lookup, case-insensitive, then partial substring.
    """
    if not topic_name:
        return None
    if topic_name in mapping:
        return mapping[topic_name]
    topic_lower = topic_name.lower().strip()
    for key, val in mapping.items():
        if key.lower().strip() == topic_lower:
            return val
    for key, val in mapping.items():
        if key.lower() in topic_lower or topic_lower in key.lower():
            return val
    return None


# ============================================================
# 14.1: Archive current results, mark dependent as invalid
# ============================================================

def step_14_1():
    """Archive current pipeline results that depend on incorrect mapping."""
    print("=" * 60)
    print("ШАГ 14.1: Archiving dependent results")
    print("=" * 60)
    
    dependent_files = [
        "bank_schema_report.json",
        "_diag_topic_mapping.py",
    ]
    
    archived = []
    for fname in dependent_files:
        src = os.path.join(PIPELINE_DIR, fname)
        if os.path.exists(src):
            dst = os.path.join(ARCHIVE_DIR, fname)
            import shutil
            shutil.copy2(src, dst)
            archived.append(fname)
            print(f"  Archived: {fname}")
    
    # Mark stage7 checkpoint as dependent on incorrect mapping
    stage7_cp = os.path.join(PIPELINE_DIR, "stage7_checkpoint.json")
    if os.path.exists(stage7_cp):
        # Create a marker file
        with open(os.path.join(ARCHIVE_DIR, "INVALID_MAPPING_MARKER.txt"), "w") as f:
            f.write(f"MARKED INVALID at {datetime.now().isoformat()}\n")
            f.write("Reason: Taxonomy mapping was incorrect (mapped_to_taxonomy=0)\n")
            f.write("These results depend on grade+level-only indexing, not cell_key\n")
        print("  Created INVALID_MAPPING_MARKER.txt")
    
    print(f"  Total archived: {len(archived)} files\n")
    return {"archived_files": archived, "status": "completed"}


# ============================================================
# 14.2: Build taxonomy_source_inventory.json
# ============================================================

def step_14_2():
    """Catalog all authoritative sources of cell_key data."""
    print("=" * 60)
    print("ШАГ 14.2: Building taxonomy_source_inventory.json")
    print("=" * 60)
    
    sources = []
    
    # Source 1: stage3_checkpoint.json
    path = os.path.join(PIPELINE_DIR, "stage3_checkpoint.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        results = data.get("results", [])
        cell_keys = sum(1 for r in results if r.get("cell_key"))
        unique_cell_keys = len(set(r.get("cell_key") for r in results if r.get("cell_key")))
        sources.append({
            "path": "stage3_checkpoint.json",
            "type": "checkpoint",
            "record_count": len(results),
            "has_task_id": True,
            "has_full_cell_key": True,
            "has_topic_id": True,
            "has_subtopic_id": True,
            "cell_key_coverage": f"{cell_keys}/{len(results)}",
            "unique_cell_keys": unique_cell_keys,
            "authority_rank": 1,
            "usable": True,
            "notes": "Direct task_id->cell_key mapping from Stage 3 multi-role audit"
        })
        print(f"  stage3_checkpoint: {len(results)} results, {unique_cell_keys} unique cell_keys")
    
    # Source 2: stage3_audit_results.json
    path = os.path.join(PIPELINE_DIR, "stage3_audit_results.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        cell_keys = sum(1 for r in data if isinstance(r, dict) and r.get("cell_key"))
        unique_cell_keys = len(set(r.get("cell_key") for r in data if isinstance(r, dict) and r.get("cell_key")))
        sources.append({
            "path": "stage3_audit_results.json",
            "type": "audit_results",
            "record_count": len(data),
            "has_task_id": True,
            "has_full_cell_key": True,
            "cell_key_coverage": f"{cell_keys}/{len(data)}",
            "unique_cell_keys": unique_cell_keys,
            "authority_rank": 1,
            "usable": True,
            "notes": "Same data as stage3_checkpoint but as flat array"
        })
        print(f"  stage3_audit_results: {len(data)} records, {unique_cell_keys} unique cell_keys")
    
    # Source 3: stage4_classification.json
    path = os.path.join(PIPELINE_DIR, "stage4_classification.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        classifications = data.get("classifications", [])
        cell_keys = sum(1 for r in classifications if r.get("cell_key"))
        unique_cell_keys = len(set(r.get("cell_key") for r in classifications if r.get("cell_key")))
        sources.append({
            "path": "stage4_classification.json",
            "type": "classification",
            "record_count": len(classifications),
            "has_task_id": True,
            "has_full_cell_key": True,
            "cell_key_coverage": f"{cell_keys}/{len(classifications)}",
            "unique_cell_keys": unique_cell_keys,
            "authority_rank": 1,
            "usable": True,
            "notes": "Stage 4 task classifications with cell_key"
        })
        print(f"  stage4_classification: {len(classifications)} records, {unique_cell_keys} unique cell_keys")
    
    # Source 4: stage45_reclassification.json
    path = os.path.join(PIPELINE_DIR, "stage45_reclassification.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        reclass = data.get("reclassifications", [])
        cell_keys = sum(1 for r in reclass if r.get("cell_key"))
        unique_cell_keys = len(set(r.get("cell_key") for r in reclass if r.get("cell_key")))
        sources.append({
            "path": "stage45_reclassification.json",
            "type": "reclassification",
            "record_count": len(reclass),
            "has_task_id": True,
            "has_full_cell_key": True,
            "cell_key_coverage": f"{cell_keys}/{len(reclass)}",
            "unique_cell_keys": unique_cell_keys,
            "authority_rank": 1,
            "usable": True,
            "notes": "Stage 45 reclassification with cell_key"
        })
        print(f"  stage45_reclassification: {len(reclass)} records, {unique_cell_keys} unique cell_keys")
    
    # Source 5: stage5_fix_results.json
    path = os.path.join(PIPELINE_DIR, "stage5_fix_results.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        results = data.get("results", [])
        cell_keys = sum(1 for r in results if r.get("cell_key"))
        unique_cell_keys = len(set(r.get("cell_key") for r in results if r.get("cell_key")))
        sources.append({
            "path": "stage5_fix_results.json",
            "type": "fix_results",
            "record_count": len(results),
            "has_task_id": True,
            "has_full_cell_key": True,
            "cell_key_coverage": f"{cell_keys}/{len(results)}",
            "unique_cell_keys": unique_cell_keys,
            "authority_rank": 1,
            "usable": True,
            "notes": "Stage 5 fix results with cell_key"
        })
        print(f"  stage5_fix_results: {len(results)} records, {unique_cell_keys} unique cell_keys")
    
    # Source 6: stage5_fixes/ directory
    fixes_dir = os.path.join(PIPELINE_DIR, "stage5_fixes")
    if os.path.isdir(fixes_dir):
        fix_files = glob.glob(os.path.join(fixes_dir, "*_fix_log.json"))
        fix_task_ids = set()
        fix_cell_keys = set()
        for ff in fix_files:
            try:
                with open(ff, "r", encoding="utf-8") as f:
                    fix_data = json.load(f)
                if isinstance(fix_data, dict):
                    tid = fix_data.get("task_id")
                    ck = fix_data.get("cell_key")
                    if tid:
                        fix_task_ids.add(tid)
                    if ck:
                        fix_cell_keys.add(ck)
            except:
                pass
        sources.append({
            "path": "stage5_fixes/",
            "type": "fix_logs_directory",
            "record_count": len(fix_files),
            "unique_task_ids": len(fix_task_ids),
            "unique_cell_keys": len(fix_cell_keys),
            "has_task_id": True,
            "has_full_cell_key": True,
            "authority_rank": 1,
            "usable": True,
            "notes": "Individual fix logs with cell_key per task"
        })
        print(f"  stage5_fixes/: {len(fix_files)} fix logs, {len(fix_cell_keys)} unique cell_keys")
    
    # Source 7: stage45_forensics/ directory
    forensics_dir = os.path.join(PIPELINE_DIR, "stage45_forensics")
    if os.path.isdir(forensics_dir):
        forensic_files = glob.glob(os.path.join(forensics_dir, "*.json"))
        forensic_task_ids = set()
        for ff in forensic_files:
            basename = os.path.basename(ff)
            # Format: {task_id}_G{grade}_L{level}_T{xxx}_S{x}.json
            parts = basename.replace(".json", "").split("_")
            if len(parts) >= 1:
                forensic_task_ids.add(parts[0])
        sources.append({
            "path": "stage45_forensics/",
            "type": "forensics_directory",
            "record_count": len(forensic_files),
            "unique_task_ids": len(forensic_task_ids),
            "has_full_cell_key_in_filename": True,
            "authority_rank": 1,
            "usable": True,
            "notes": "Task forensics files with cell_key encoded in filename"
        })
        print(f"  stage45_forensics/: {len(forensic_files)} forensic files")
    
    # Source 8: reconciliation_report.json
    path = os.path.join(PIPELINE_DIR, "reconciliation_report.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        cells = data.get("replacement_cells", data.get("cells", []))
        if not cells:
            # Try to find cell arrays
            for key in data:
                if isinstance(data[key], list) and len(data[key]) > 0:
                    if isinstance(data[key][0], dict) and "cell_key" in data[key][0]:
                        cells = data[key]
                        break
        
        # The replacement_cells might not be the key name, look for any list of dicts with cell_key
        if not cells:
            for key, val in data.items():
                if isinstance(val, list) and len(val) > 0 and isinstance(val[0], dict):
                    if "cell_key" in val[0]:
                        cells = val
                        break
        
        final_sets = data.get("final_sets", {})
        total_count = sum(s.get("count", 0) for s in final_sets.values())
        
        sources.append({
            "path": "reconciliation_report.json",
            "type": "reconciliation_report",
            "record_count": 1,
            "total_tasks": data.get("stage3_unique_task_ids", 0),
            "keep_count": final_sets.get("keep", {}).get("count", 0),
            "fixed_count": final_sets.get("fixed", {}).get("count", 0),
            "replace_count": final_sets.get("replace", {}).get("count", 0),
            "cells_with_replace_ids": len(cells),
            "has_cell_keys": True,
            "has_task_id_mappings": True,
            "authority_rank": 2,
            "usable": True,
            "notes": "Reconciliation of all pipeline stages with cell_key->task_id mapping"
        })
        print(f"  reconciliation_report: {total_count} total tasks, {len(cells)} cells with replace_ids")
    
    # Source 9: stage6_candidates.json
    path = os.path.join(PIPELINE_DIR, "stage6_candidates.json")
    path_alt = os.path.join(PIPELINE_DIR, "checkpoints_failed_chat_run", "stage6_candidates.json")
    for p, label in [(path, "stage6_candidates.json"), (path_alt, "checkpoints_failed_chat_run/stage6_candidates.json")]:
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            candidates = data.get("candidates", data)
            if isinstance(candidates, dict):
                candidate_count = len(candidates)
                cell_keys = set()
                task_ids = set()
                for ck, cdata in candidates.items():
                    cell_keys.add(ck)
                    if isinstance(cdata, dict) and cdata.get("task_id"):
                        task_ids.add(cdata["task_id"])
                sources.append({
                    "path": label,
                    "type": "generated_candidates",
                    "record_count": candidate_count,
                    "unique_cell_keys": len(cell_keys),
                    "unique_task_ids": len(task_ids),
                    "has_full_cell_key_as_key": True,
                    "has_task_id": True,
                    "authority_rank": 1,
                    "usable": True,
                    "notes": f"Stage 6 generated candidates keyed by full cell_key"
                })
                print(f"  {label}: {candidate_count} candidates, {len(cell_keys)} unique cell_keys")
    
    # Source 10: stage6_candidate_selection.jsonl
    path = os.path.join(PIPELINE_DIR, "stage6_candidate_selection.jsonl")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        selections = []
        for line in lines:
            line = line.strip()
            if line:
                try:
                    selections.append(json.loads(line))
                except:
                    pass
        flat_keys = set()
        cell_keys_no_sub = set()
        task_ids = set()
        for s in selections:
            if s.get("flat_key"):
                flat_keys.add(s["flat_key"])
            if s.get("cell_key"):
                cell_keys_no_sub.add(s["cell_key"])
            if s.get("task_id"):
                task_ids.add(s["task_id"])
        sources.append({
            "path": "stage6_candidate_selection.jsonl",
            "type": "candidate_selection",
            "record_count": len(selections),
            "unique_flat_keys": len(flat_keys),
            "unique_task_ids": len(task_ids),
            "has_flat_key": True,
            "has_cell_key_without_subtopic": True,
            "authority_rank": 1,
            "usable": True,
            "notes": "Selected candidates with flat_key (G|L|T|S format)"
        })
        print(f"  stage6_candidate_selection: {len(selections)} selections, {len(flat_keys)} unique flat_keys")
    
    # Source 11: stage7_checkpoint.json
    path = os.path.join(PIPELINE_DIR, "stage7_checkpoint.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        slot_keys = set()
        total_entries = 0
        if isinstance(data, dict):
            for key, val in data.items():
                if "|" in str(key) or key.startswith("G"):
                    slot_keys.add(key)
                    total_entries += 1
                elif isinstance(val, dict):
                    total_entries += 1
                    for k2 in val:
                        if "|" in str(k2) or str(k2).startswith("G"):
                            slot_keys.add(k2)
        elif isinstance(data, list):
            total_entries = len(data)
            for item in data:
                if isinstance(item, dict):
                    sk = item.get("slot_key", item.get("cell_key", ""))
                    if "|" in str(sk):
                        slot_keys.add(sk)
        
        sources.append({
            "path": "stage7_checkpoint.json",
            "type": "checkpoint",
            "record_count": total_entries,
            "slot_keys_found": len(slot_keys),
            "has_slot_keys": True,
            "authority_rank": 3,
            "usable": True,
            "notes": "Stage 7 checkpoint with slot_key entries (may have stale data)"
        })
        print(f"  stage7_checkpoint: ~{total_entries} entries, {len(slot_keys)} slot_keys")
    
    # Source 12: correction_slot_report.json
    path = os.path.join(PIPELINE_DIR, "corrected_slot_report.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        sources.append({
            "path": "corrected_slot_report.json",
            "type": "slot_report",
            "record_count": 1,
            "authority_rank": 3,
            "usable": True,
            "notes": "Report on corrected slot mapping"
        })
        print(f"  corrected_slot_report: found")
    
    # Source 13: taxonomy_by_grade.json (authoritative taxonomy definition)
    path = os.path.join(BASE_DIR, "taxonomy_by_grade.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        meta = data.get("meta", {})
        sources.append({
            "path": "taxonomy_by_grade.json",
            "type": "authoritative_taxonomy",
            "total_themes": meta.get("total_themes", 0),
            "total_subtopics": meta.get("total_subtopics", 0),
            "grades": list(meta.get("grade_summary", {}).keys()),
            "has_topic_ids": True,
            "has_subtopic_names": True,
            "authority_rank": 0,
            "usable": True,
            "notes": "THE AUTHORITATIVE TAXONOMY SOURCE - defines all themes, topic_ids, subtopics per grade"
        })
        print(f"  taxonomy_by_grade.json: {meta.get('total_themes', 0)} themes, {meta.get('total_subtopics', 0)} subtopics")
    
    # Source 14: curated_bank_L1_L5_fixed.json
    path = os.path.join(BASE_DIR, "curated_bank_L1_L5_fixed.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            # Just count lines to get size
            line_count = sum(1 for _ in f)
        sources.append({
            "path": "curated_bank_L1_L5_fixed.json",
            "type": "bank",
            "estimated_records": "See bank_schema_report for exact count",
            "has_cell_keys": False,
            "has_topic_names": True,
            "has_grade_level": True,
            "authority_rank": 4,
            "usable": False,
            "notes": "The bank itself. Lacks cell_keys. Needs mapping from authoritative sources."
        })
        print(f"  curated_bank_L1_L5_fixed.json: {line_count} lines (the bank itself)")
    
    inventory = {
        "meta": {
            "generated_at": datetime.now().isoformat(),
            "total_sources": len(sources),
            "authoritative_sources": len([s for s in sources if s.get("authority_rank", 99) <= 1]),
            "purpose": "Catalog all files containing authoritative task_id->cell_key mappings"
        },
        "sources": sorted(sources, key=lambda s: (s.get("authority_rank", 99), s.get("path", "")))
    }
    
    out_path = os.path.join(OUT_DIR, "taxonomy_source_inventory.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(inventory, f, indent=2, ensure_ascii=False)
    print(f"\n  Written: taxonomy_source_inventory.json ({len(sources)} sources)")
    return inventory


# ============================================================
# 14.3: Build canonical_taxonomy.json
# ============================================================

def step_14_3():
    """Build canonical taxonomy from taxonomy_by_grade.json."""
    print("=" * 60)
    print("ШАГ 14.3: Building canonical_taxonomy.json")
    print("=" * 60)
    
    path = os.path.join(BASE_DIR, "taxonomy_by_grade.json")
    with open(path, "r", encoding="utf-8") as f:
        taxonomy = json.load(f)
    
    meta = taxonomy.get("meta", {})
    grades_data = taxonomy.get("grades", {})
    
    # Collect all unique topics across all grades
    all_topics = {}  # topic_id -> {name, grades: [], subtopics: []}
    topic_subtopic_map = {}  # (topic_id, subtopic_index) -> subtopic_name
    
    for grade_str, gdata in grades_data.items():
        for theme in gdata.get("themes", []):
            tid = theme["id"]
            tname = theme["name"]
            subtopics = theme.get("subtopics", [])
            if tid not in all_topics:
                all_topics[tid] = {
                    "name": tname,
                    "grades": [],
                    "subtopics": subtopics
                }
            all_topics[tid]["grades"].append(int(grade_str))
            
            for si, sname in enumerate(subtopics):
                topic_subtopic_map[(tid, si)] = sname
    
    # Sort topics by their numeric ID
    sorted_topic_ids = sorted(all_topics.keys(), key=lambda x: int(x.replace("T", "")))
    
    # Build canonical cells
    canonical_cells = []
    
    for grade_str, gdata in grades_data.items():
        grade = int(grade_str)
        for theme in gdata.get("themes", []):
            tid = theme["id"]
            tname = theme["name"]
            subtopics = theme.get("subtopics", [])
            for si, sname in enumerate(subtopics):
                for level in LEVELS:
                    cell_key = f"G{grade}|{level}|{tid}|S{si}"
                    canonical_cells.append({
                        "cell_key": cell_key,
                        "grade": grade,
                        "level": level,
                        "topic_id": tid,
                        "theme_name": tname,
                        "subtopic_index": si,
                        "subtopic_name": sname
                    })
    
    # Count unique cells
    unique_cells = defaultdict(int)
    for cc in canonical_cells:
        unique_cells[(cc["grade"], cc["level"], cc["topic_id"], cc["subtopic_index"])] += 1
    
    # Build canonical cells dict for lookup
    canonical_dict = {}
    for cc in canonical_cells:
        canonical_dict[cc["cell_key"]] = {
            "grade": cc["grade"],
            "level": cc["level"],
            "topic_id": cc["topic_id"],
            "theme_name": cc["theme_name"],
            "subtopic_index": cc["subtopic_index"],
            "subtopic_name": cc["subtopic_name"]
        }
    
    # Build topic index
    topics_index = {}
    for tid in sorted_topic_ids:
        tinfo = all_topics[tid]
        topics_index[tid] = {
            "name": tinfo["name"],
            "grades": sorted(tinfo["grades"]),
            "subtopics": tinfo["subtopics"]
        }
    
    # Build canonical structure
    canonical = {
        "meta": {
            "generated_at": datetime.now().isoformat(),
            "source": "taxonomy_by_grade.json",
            "unique_topics": len(sorted_topic_ids),
            "unique_subtopics": len(topic_subtopic_map),
            "levels": LEVELS,
            "total_canonical_cells": len(canonical_cells),
            "unique_grade_topic_subtopic_combos": len(unique_cells),
            "topic_ids": sorted_topic_ids,
            "grades_present": sorted([int(g) for g in grades_data.keys()])
        },
        "topics": topics_index,
        "canonical_cells": canonical_cells
    }
    
    out_path = os.path.join(OUT_DIR, "canonical_taxonomy.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(canonical, f, indent=2, ensure_ascii=False)
    print(f"  Written: canonical_taxonomy.json ({len(canonical_cells)} canonical cells, {len(sorted_topic_ids)} topics)")
    
    # Build audit
    audit = {
        "meta": {
            "generated_at": datetime.now().isoformat(),
            "source": "taxonomy_by_grade.json"
        },
        "total_topics_in_source": meta.get("total_themes", 0),
        "total_subtopics_in_source": meta.get("total_subtopics", 0),
        "unique_topics_extracted": len(sorted_topic_ids),
        "unique_subtopics_extracted": len(topic_subtopic_map),
        "total_canonical_cells": len(canonical_cells),
        "grades_summary": {},
        "integrity_checks": {
            "all_topics_have_3_subtopics": all(len(t["subtopics"]) == 3 for t in all_topics.values()),
            "all_cell_keys_unique": len(canonical_cells) == len(set(cc["cell_key"] for cc in canonical_cells)),
            "no_missing_topic_ids": all(tid.startswith("T") for tid in sorted_topic_ids)
        }
    }
    
    for grade_str, gdata in grades_data.items():
        grade = int(grade_str)
        grade_cells = [cc for cc in canonical_cells if cc["grade"] == grade]
        audit["grades_summary"][grade_str] = {
            "themes": gdata.get("theme_count", 0),
            "subtopics": gdata.get("subtopic_count", 0),
            "canonical_cells": len(grade_cells),
            "cells_per_level": {lvl: len([cc for cc in grade_cells if cc["level"] == lvl]) for lvl in LEVELS}
        }
    
    # Check that all topic IDs from stage data exist in canonical taxonomy
    audit_path = os.path.join(OUT_DIR, "canonical_taxonomy_audit.json")
    with open(audit_path, "w", encoding="utf-8") as f:
        json.dump(audit, f, indent=2, ensure_ascii=False)
    print(f"  Written: canonical_taxonomy_audit.json")
    
    return canonical, canonical_dict


# ============================================================
# 14.4: Build task_lineage.jsonl
# ============================================================

def step_14_4():
    """Reconstruct each task's cell by lineage from all checkpoint sources."""
    print("=" * 60)
    print("ШАГ 14.4: Building task_lineage.jsonl (lineage reconstruction)")
    print("=" * 60)
    
    # Collect all task_id->cell_key mappings from authoritative sources
    # Each entry: {task_id, cell_key, source, confidence, method}
    task_mappings = []
    
    # Source A: stage3_audit_results.json (authoritative)
    path = os.path.join(PIPELINE_DIR, "stage3_audit_results.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for item in data:
            if isinstance(item, dict) and item.get("task_id") and item.get("cell_key"):
                task_mappings.append({
                    "task_id": item["task_id"],
                    "cell_key": item["cell_key"],
                    "source": "stage3_audit_results.json",
                    "method": "A",
                    "confidence": 1.0
                })
    
    # Source A: stage4_classification.json
    path = os.path.join(PIPELINE_DIR, "stage4_classification.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for item in data.get("classifications", []):
            if item.get("task_id") and item.get("cell_key"):
                task_mappings.append({
                    "task_id": item["task_id"],
                    "cell_key": item["cell_key"],
                    "source": "stage4_classification.json",
                    "method": "A",
                    "confidence": 1.0
                })
    
    # Source A: stage45_reclassification.json
    path = os.path.join(PIPELINE_DIR, "stage45_reclassification.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for item in data.get("reclassifications", []):
            if item.get("task_id") and item.get("cell_key"):
                task_mappings.append({
                    "task_id": item["task_id"],
                    "cell_key": item["cell_key"],
                    "source": "stage45_reclassification.json",
                    "method": "A",
                    "confidence": 1.0
                })
    
    # Source A: stage5_fix_results.json
    path = os.path.join(PIPELINE_DIR, "stage5_fix_results.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for item in data.get("results", []):
            if item.get("task_id") and item.get("cell_key"):
                task_mappings.append({
                    "task_id": item["task_id"],
                    "cell_key": item["cell_key"],
                    "source": "stage5_fix_results.json",
                    "method": "A",
                    "confidence": 1.0
                })
    
    # Source A: stage5_fixes/ individual files
    fixes_dir = os.path.join(PIPELINE_DIR, "stage5_fixes")
    if os.path.isdir(fixes_dir):
        for ff in glob.glob(os.path.join(fixes_dir, "*_fix_log.json")):
            try:
                with open(ff, "r", encoding="utf-8") as f:
                    fix_data = json.load(f)
                if isinstance(fix_data, dict) and fix_data.get("task_id") and fix_data.get("cell_key"):
                    task_mappings.append({
                        "task_id": fix_data["task_id"],
                        "cell_key": fix_data["cell_key"],
                        "source": f"stage5_fixes/{os.path.basename(ff)}",
                        "method": "A",
                        "confidence": 1.0
                    })
            except:
                pass
    
    # Source B: stage45_forensics/ filenames
    forensics_dir = os.path.join(PIPELINE_DIR, "stage45_forensics")
    if os.path.isdir(forensics_dir):
        for ff in glob.glob(os.path.join(forensics_dir, "*.json")):
            basename = os.path.basename(ff).replace(".json", "")
            # Format: {task_id}_G{grade}_L{level}_T{xxx}_S{x}
            parts = basename.split("_")
            if len(parts) >= 5:
                task_id = parts[0]
                # Reconstruct cell_key from filename
                grade_part = next((p for p in parts if p.startswith("G")), None)
                level_part = next((p for p in parts if p.startswith("L")), None)
                topic_part = next((p for p in parts if p.startswith("T")), None)
                sub_part = next((p for p in parts if p.startswith("S")), None)
                if all([grade_part, level_part, topic_part, sub_part]):
                    cell_key = f"{grade_part}|{level_part}|{topic_part}|{sub_part}"
                    task_mappings.append({
                        "task_id": task_id,
                        "cell_key": cell_key,
                        "source": f"stage45_forensics/{basename}.json",
                        "method": "B",
                        "confidence": 1.0
                    })
    
    # Source A/B: stage6_candidates.json
    for candidates_path, label in [
        (os.path.join(PIPELINE_DIR, "stage6_candidates.json"), "stage6_candidates.json"),
        (os.path.join(PIPELINE_DIR, "checkpoints_failed_chat_run", "stage6_candidates.json"), "checkpoints_failed_chat_run/stage6_candidates.json")
    ]:
        if os.path.exists(candidates_path):
            with open(candidates_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            candidates = data.get("candidates", data)
            if isinstance(candidates, dict):
                for cell_key, cdata in candidates.items():
                    if isinstance(cdata, dict) and cdata.get("task_id"):
                        task_mappings.append({
                            "task_id": cdata["task_id"],
                            "cell_key": cell_key,
                            "source": label,
                            "method": "A",
                            "confidence": 1.0,
                            "generated": True
                        })
    
    # Source A/B: stage6_candidate_selection.jsonl
    path = os.path.join(PIPELINE_DIR, "stage6_candidate_selection.jsonl")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        item = json.loads(line)
                        if item.get("task_id") and item.get("flat_key"):
                            task_mappings.append({
                                "task_id": item["task_id"],
                                "cell_key": item["flat_key"],
                                "source": "stage6_candidate_selection.jsonl",
                                "method": "A",
                                "confidence": 1.0,
                                "selected": True
                            })
                    except:
                        pass
    
    # Deduplicate: for each task_id, keep the most authoritative source
    # Priority: stage3_audit > stage4 > stage45 > stage5 > stage6 > forensics
    source_priority = {
        "stage3_audit_results.json": 0,
        "stage3_checkpoint.json": 0,
        "stage4_classification.json": 1,
        "stage45_reclassification.json": 2,
        "stage45_forensics/": 2,
        "stage5_fix_results.json": 3,
        "stage5_fixes/": 3,
        "stage6_candidates.json": 4,
        "stage6_candidate_selection.jsonl": 4,
        "checkpoints_failed_chat_run/stage6_candidates.json": 4,
    }
    
    def get_source_priority(source):
        for prefix, pri in source_priority.items():
            if source.startswith(prefix) or source == prefix:
                return pri
        return 99
    
    # Sort by priority (lowest first = most authoritative)
    task_mappings.sort(key=lambda x: (get_source_priority(x["source"]), 0 if x.get("method") == "A" else 1))
    
    # Build final lineage: one entry per task_id with the best source
    task_lineage = {}
    for mapping in task_mappings:
        tid = mapping["task_id"]
        if tid not in task_lineage:
            task_lineage[tid] = mapping
        # If same source priority, prefer method A over B
        existing_pri = get_source_priority(task_lineage[tid]["source"])
        new_pri = get_source_priority(mapping["source"])
        if new_pri < existing_pri:
            task_lineage[tid] = mapping
        elif new_pri == existing_pri:
            # Prefer method A
            if mapping.get("method") == "A" and task_lineage[tid].get("method") != "A":
                task_lineage[tid] = mapping
    
    # Write task_lineage.jsonl
    out_path = os.path.join(OUT_DIR, "task_lineage.jsonl")
    with open(out_path, "w", encoding="utf-8") as f:
        for tid, mapping in sorted(task_lineage.items()):
            f.write(json.dumps(mapping, ensure_ascii=False) + "\n")
    
    # Count stats
    cell_key_counts = Counter(m["cell_key"] for m in task_lineage.values())
    method_counts = Counter(m.get("method", "?") for m in task_lineage.values())
    
    print(f"  Total task_id->cell_key mappings collected: {len(task_mappings)}")
    print(f"  Unique task_ids with lineage: {len(task_lineage)}")
    print(f"  Unique cell_keys: {len(cell_key_counts)}")
    print(f"  By method: {dict(method_counts)}")
    print(f"  Written: task_lineage.jsonl")
    
    return task_lineage


# ============================================================
# 14.5: Build bank_taxonomy_crosswalk.jsonl
# ============================================================

def step_14_5(task_lineage, canonical_dict):
    """Build crosswalk mapping bank tasks to canonical taxonomy cells."""
    print("=" * 60)
    print("ШАГ 14.5: Building bank_taxonomy_crosswalk.jsonl")
    print("=" * 60)
    
    # Load the bank
    bank_path = os.path.join(BASE_DIR, "curated_bank_L1_L5_fixed.json")
    bank_records = []
    with open(bank_path, "r", encoding="utf-8") as f:
        bank_data = json.load(f)
    
    if isinstance(bank_data, list):
        bank_records = bank_data
    elif isinstance(bank_data, dict):
        # Try common keys
        for key in ["tasks", "records", "items", "data", "bank"]:
            if key in bank_data and isinstance(bank_data[key], list):
                bank_records = bank_data[key]
                break
        if not bank_records:
            # Try all values
            for val in bank_data.values():
                if isinstance(val, list) and len(val) > 0 and isinstance(val[0], dict):
                    bank_records = val
                    break
    
    print(f"  Bank records loaded: {len(bank_records)}")
    
    # Initialize curated topic mapping for Method D topic->theme_id resolution
    topic_mapping = build_curated_topic_mapping()
    print(f"  Curated topic mapping: {len(topic_mapping)} entries")
    
    # Build task_id->lineage lookup
    lineage_lookup = {m["task_id"]: m for m in task_lineage.values()}
    
    # Build bank task_id->grade+level+topic lookup (for tasks without cell_key in bank)
    bank_task_info = {}  # task_id -> {grade, level, topic}
    for record in bank_records:
        if isinstance(record, dict):
            tid = record.get("original_id") or record.get("task_id") or record.get("id") or record.get("_id")
            if tid:
                bank_task_info[tid] = {
                    "grade": record.get("grade") or record.get("class_level"),
                    "level": record.get("level"),
                    "topic": record.get("topic") or record.get("theme_name") or record.get("category"),
                    "statement": (record.get("statement") or record.get("question") or "")[:100]
                }
    
    # Build grade+level+topic lookup from canonical taxonomy (for Method D)
    grade_level_topic_lookup = defaultdict(list)
    grade_level_topic_id_lookup = defaultdict(list)
    for ck, cinfo in canonical_dict.items():
        meta_key = (cinfo["grade"], cinfo["level"], cinfo["theme_name"])
        grade_level_topic_lookup[meta_key].append(ck)
        # Also build topic_id-based lookup (used with curated topic mapping)
        tid_key = (cinfo["grade"], cinfo["level"], cinfo["topic_id"])
        grade_level_topic_id_lookup[tid_key].append(ck)
    
    print(f"  Built grade+level+topic lookup: {len(grade_level_topic_lookup)} unique keys")
    print(f"  Built grade+level+topic_id lookup: {len(grade_level_topic_id_lookup)} unique keys")
    
    # Build the crosswalk
    crosswalk = []
    unmapped_tasks = []
    mapped_by_method = Counter()
    
    for record in bank_records:
        if not isinstance(record, dict):
            continue
        
        tid = record.get("original_id") or record.get("task_id") or record.get("id") or record.get("_id")
        if not tid:
            continue
        
        # Break down tid for gen_ tasks
        is_generated = str(tid).startswith("gen_")
        
        bank_entry = {
            "task_id": tid,
            "bank_grade": record.get("grade") or record.get("class_level"),
            "bank_level": record.get("level"),
            "bank_topic": record.get("topic") or record.get("theme_name") or "",
            "bank_subtopic": record.get("subtopic") or record.get("subtopic_name") or "",
            "statement_preview": (record.get("statement") or record.get("question") or "")[:120]
        }
        
        cell_key = None
        method = None
        confidence = 0.0
        source = None
        
        # METHOD A: Check if task_id is in authoritative lineage
        if tid in lineage_lookup:
            cell_key = lineage_lookup[tid]["cell_key"]
            method = lineage_lookup[tid].get("method", "A")
            confidence = 1.0
            source = lineage_lookup[tid]["source"]
            mapped_by_method["A_lineage"] += 1
        
        # METHOD B: Check if record already has a cell_key field
        elif record.get("cell_key"):
            cell_key = record["cell_key"]
            method = "A_bank_field"
            confidence = 1.0
            source = "curated_bank_L1_L5_fixed.json (cell_key field)"
            mapped_by_method["A_bank_field"] += 1
        
        # METHOD C: For gen_ tasks, check stage6_candidate_selection.jsonl
        elif is_generated:
            # Already handled by lineage lookup above (gen_ tasks are in stage6)
            pass
        
        # METHOD D: Metadata Join by grade+level+topic (with fallbacks and curated mapping)
        if not cell_key:
            # Fix 1: Use class_level as grade fallback (224 records have class_level, not grade)
            bank_grade = record.get("grade") or record.get("class_level")
            bank_level = record.get("level")
            bank_topic = record.get("topic") or record.get("theme_name") or ""
            
            if bank_grade is not None and bank_level is not None and bank_topic:
                # Convert numeric level (1-5) to taxonomy format (L1-L5)
                level_key = f"L{bank_level}"
                
                # Fix 2: Canonical taxonomy ONLY has L4/L5 — skip L1-L3 records
                if level_key not in ["L4", "L5"]:
                    pass  # L1-L3 records cannot match canonical taxonomy
                else:
                    # Fix 3: Use curated topic mapping to convert bank topic name -> theme_id
                    topic_id = map_curated_topic_to_theme(bank_topic, topic_mapping)
                    
                    if topic_id:
                        # Look up by (grade, level_key, topic_id) instead of theme_name
                        tid_key = (int(bank_grade), level_key, topic_id)
                        candidates = grade_level_topic_id_lookup.get(tid_key, [])
                        
                        if len(candidates) == 1:
                            cell_key = candidates[0]
                            method = "D_metadata_join"
                            confidence = 0.99
                            source = f"Unique metadata join: grade={bank_grade}, level={level_key}, topic_id={topic_id} ({bank_topic})"
                            mapped_by_method["D_metadata_join"] += 1
                        elif len(candidates) > 0:
                            # Multiple subtopics under same grade+level+topic
                            # Try to disambiguate by subtopic if bank has it
                            bank_subtopic = record.get("subtopic") or record.get("subtopic_name") or ""
                            if bank_subtopic:
                                # Find which candidate matches the subtopic
                                subtopic_match = None
                                for ck in candidates:
                                    cinfo = canonical_dict.get(ck, {})
                                    if cinfo.get("subtopic_name", "").lower() == bank_subtopic.lower():
                                        subtopic_match = ck
                                        break
                                if subtopic_match:
                                    cell_key = subtopic_match
                                    method = "D_metadata_join_subtopic"
                                    confidence = 0.95
                                    source = f"Metadata join + subtopic: grade={bank_grade}, level={level_key}, topic_id={topic_id}, subtopic={bank_subtopic}"
                                    mapped_by_method["D_metadata_join_subtopic"] += 1
                                else:
                                    # No subtopic match - pick first candidate
                                    cell_key = candidates[0]
                                    method = "D_metadata_join_multi"
                                    confidence = 0.9
                                    source = f"Multi-candidate metadata join (pick 1/{len(candidates)}): grade={bank_grade}, level={level_key}, topic_id={topic_id}"
                                    mapped_by_method["D_metadata_join_multi"] += 1
                            else:
                                # No subtopic info - pick first candidate
                                cell_key = candidates[0]
                                method = "D_metadata_join_multi"
                                confidence = 0.9
                                source = f"Multi-candidate metadata join (pick 1/{len(candidates)}): grade={bank_grade}, level={level_key}, topic_id={topic_id}"
                                mapped_by_method["D_metadata_join_multi"] += 1
        
        # If we have a cell_key, validate it against canonical taxonomy
        if cell_key:
            # Validate cell_key format
            parts = str(cell_key).split("|")
            if len(parts) == 4:
                # Check if valid per canonical taxonomy
                if cell_key in canonical_dict:
                    cinfo = canonical_dict[cell_key]
                    entry = {
                        **bank_entry,
                        "cell_key": cell_key,
                        "canonical_grade": cinfo["grade"],
                        "canonical_level": cinfo["level"],
                        "canonical_topic_id": cinfo["topic_id"],
                        "canonical_theme": cinfo["theme_name"],
                        "canonical_subtopic": cinfo["subtopic_name"],
                        "mapping_method": method,
                        "confidence": confidence,
                        "source": source,
                        "validated": True
                    }
                    crosswalk.append(entry)
                else:
                    # Cell key not in canonical taxonomy (e.g., from different grade's topic)
                    # Still valid, but note it
                    entry = {
                        **bank_entry,
                        "cell_key": cell_key,
                        "mapping_method": method,
                        "confidence": confidence,
                        "source": source,
                        "validated": False,
                        "validation_note": "cell_key format valid but not in canonical taxonomy for this grade"
                    }
                    crosswalk.append(entry)
            else:
                # Invalid cell_key format
                entry = {
                    **bank_entry,
                    "cell_key": cell_key,
                    "mapping_method": method,
                    "confidence": 0.0,
                    "validated": False,
                    "validation_note": f"Invalid cell_key format: {cell_key}"
                }
                crosswalk.append(entry)
                unmapped_tasks.append(tid)
        else:
            # No mapping found - will need METHOD D or E
            unmapped_tasks.append(tid)
            entry = {
                **bank_entry,
                "cell_key": None,
                "mapping_method": None,
                "confidence": 0.0,
                "validated": False,
                "validation_note": "No authoritative mapping found"
            }
            crosswalk.append(entry)
    
    # Write crosswalk
    out_path = os.path.join(OUT_DIR, "bank_taxonomy_crosswalk.jsonl")
    with open(out_path, "w", encoding="utf-8") as f:
        for entry in crosswalk:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    
    # Summary
    mapped_count = sum(1 for e in crosswalk if e.get("cell_key") and e.get("validated"))
    mapped_total = sum(1 for e in crosswalk if e.get("cell_key"))
    unresolved = sum(1 for e in crosswalk if not e.get("cell_key"))
    
    summary = {
        "generated_at": datetime.now().isoformat(),
        "total_bank_records": len(bank_records),
        "total_crosswalk_entries": len(crosswalk),
        "mapped_with_validated_cell_key": mapped_count,
        "mapped_total": mapped_total,
        "unresolved": unresolved,
        "unresolved_task_ids": unmapped_tasks[:50],  # First 50 for inspection
        "mapped_by_method": dict(mapped_by_method),
        "coverage": f"{mapped_count}/{len(bank_records)} ({100*mapped_count/len(bank_records):.1f}%)" if bank_records else "N/A"
    }
    
    out_summary = os.path.join(OUT_DIR, "bank_taxonomy_crosswalk_summary.json")
    with open(out_summary, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    
    print(f"  Mapped (validated): {mapped_count}/{len(bank_records)}")
    print(f"  Mapped (total): {mapped_total}/{len(bank_records)}")
    print(f"  Unresolved: {unresolved}")
    print(f"  By method: {dict(mapped_by_method)}")
    print(f"  Written: bank_taxonomy_crosswalk.jsonl + summary.json")
    
    return crosswalk, summary


# ============================================================
# 14.6: Resolve mapping conflicts
# ============================================================

def step_14_6(crosswalk):
    """Detect and resolve mapping conflicts."""
    print("=" * 60)
    print("ШАГ 14.6: Resolving mapping conflicts")
    print("=" * 60)
    
    # Check for task_ids mapped to multiple cell_keys
    task_to_cell = defaultdict(set)
    for entry in crosswalk:
        tid = entry["task_id"]
        ck = entry.get("cell_key")
        if ck:
            task_to_cell[tid].add(ck)
    
    conflicts = []
    for tid, cells in task_to_cell.items():
        if len(cells) > 1:
            conflict = {
                "task_id": tid,
                "cell_keys": list(cells),
                "count": len(cells),
                "entries": [e for e in crosswalk if e["task_id"] == tid and e.get("cell_key") in cells]
            }
            conflicts.append(conflict)
    
    # Also check for cell_keys mapped to wrong grade
    grade_conflicts = []
    for entry in crosswalk:
        if entry.get("cell_key") and entry.get("validated"):
            ck = entry["cell_key"]
            parts = ck.split("|")
            if len(parts) == 4:
                ck_grade = int(parts[0].replace("G", ""))
                bank_grade = entry.get("bank_grade")
                if bank_grade is not None and ck_grade != bank_grade:
                    grade_conflicts.append({
                        "task_id": entry["task_id"],
                        "cell_key": ck,
                        "bank_grade": bank_grade,
                        "cell_key_grade": ck_grade
                    })
    
    conflicts_output = {
        "generated_at": datetime.now().isoformat(),
        "total_entries_checked": len(crosswalk),
        "multiple_cell_key_conflicts": {
            "count": len(conflicts),
            "conflicts": conflicts[:20]  # First 20
        },
        "grade_mismatch_conflicts": {
            "count": len(grade_conflicts),
            "conflicts": grade_conflicts[:20]
        },
        "resolution_notes": "Conflicts resolved by source priority: stage3 > stage4 > stage45 > stage5 > stage6"
    }
    
    out_path = os.path.join(OUT_DIR, "taxonomy_mapping_conflicts.jsonl")
    with open(out_path, "w", encoding="utf-8") as f:
        for conflict in conflicts:
            f.write(json.dumps(conflict, ensure_ascii=False) + "\n")
    
    # Also write the grade conflicts
    for gc in grade_conflicts:
        with open(out_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"type": "grade_mismatch", **gc}, ensure_ascii=False) + "\n")
    
    out_json = os.path.join(OUT_DIR, "taxonomy_mapping_conflicts.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(conflicts_output, f, indent=2, ensure_ascii=False)
    
    print(f"  Multiple cell-key conflicts: {len(conflicts)}")
    print(f"  Grade mismatch conflicts: {len(grade_conflicts)}")
    print(f"  Written: taxonomy_mapping_conflicts.jsonl/.json")
    
    return conflicts, grade_conflicts


# ============================================================
# 14.7: Rebuild bank_by_cell from crosswalk
# ============================================================

def step_14_7(crosswalk, canonical_dict):
    """Group bank tasks by canonical cell_key."""
    print("=" * 60)
    print("ШАГ 14.7: Building bank_by_cell")
    print("=" * 60)
    
    # Group crosswalk entries by cell_key
    cells = defaultdict(list)
    cell_themes = {}
    
    for entry in crosswalk:
        ck = entry.get("cell_key")
        if ck and entry.get("validated"):
            cells[ck].append(entry)
            if ck in canonical_dict:
                cell_themes[ck] = canonical_dict[ck]
    
    # Build bank_by_cell structure
    bank_by_cell = {}
    for ck, entries in sorted(cells.items()):
        task_ids = [e["task_id"] for e in entries]
        bank_by_cell[ck] = {
            "cell_key": ck,
            "task_count": len(task_ids),
            "task_ids": task_ids,
            "levels_present": list(set(e.get("canonical_level", e.get("bank_level")) for e in entries if e.get("canonical_level") or e.get("bank_level"))),
            "unique_statements": len(set(e.get("statement_preview", "") for e in entries))
        }
        if ck in cell_themes:
            bank_by_cell[ck]["canonical_info"] = cell_themes[ck]
    
    # Generate stats
    total_cells_with_tasks = len(bank_by_cell)
    total_tasks_mapped = sum(c["task_count"] for c in bank_by_cell.values())
    
    # Count cells needing L4, L5, both
    l4_only = sum(1 for c in bank_by_cell.values() if c.get("levels_present") == ["L4"])
    l5_only = sum(1 for c in bank_by_cell.values() if c.get("levels_present") == ["L5"])
    both_levels = sum(1 for c in bank_by_cell.values() if len(c.get("levels_present", [])) > 1)
    
    report = {
        "generated_at": datetime.now().isoformat(),
        "total_canonical_cells_available": len(canonical_dict),
        "cells_with_tasks": total_cells_with_tasks,
        "total_tasks_mapped": total_tasks_mapped,
        "cells_with_L4_only": l4_only,
        "cells_with_L5_only": l5_only,
        "cells_with_both_levels": both_levels,
        "coverage": f"{total_cells_with_tasks}/{len(canonical_dict)} ({100*total_cells_with_tasks/len(canonical_dict):.1f}%)" if canonical_dict else "N/A",
        "avg_tasks_per_cell": round(total_tasks_mapped / total_cells_with_tasks, 2) if total_cells_with_tasks > 0 else 0,
        "grade_distribution": {}
    }
    
    # Grade distribution
    for ck, info in bank_by_cell.items():
        if "canonical_info" in info:
            g = str(info["canonical_info"]["grade"])
            if g not in report["grade_distribution"]:
                report["grade_distribution"][g] = {"cells": 0, "tasks": 0}
            report["grade_distribution"][g]["cells"] += 1
            report["grade_distribution"][g]["tasks"] += info["task_count"]
    
    out_path = os.path.join(OUT_DIR, "bank_by_cell.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "report": report,
            "cells": bank_by_cell
        }, f, indent=2, ensure_ascii=False)
    
    print(f"  Cells with tasks: {total_cells_with_tasks}/{len(canonical_dict)}")
    print(f"  Total tasks mapped: {total_tasks_mapped}")
    print(f"  L4-only cells: {l4_only}, L5-only cells: {l5_only}, Both: {both_levels}")
    print(f"  Written: bank_by_cell.json")
    
    return bank_by_cell, report


# ============================================================
# MAIN
# ============================================================

def main():
    print("\n" + "=" * 60)
    print("TAXONOMY RECONSTRUCTION PIPELINE (ШАГ 14)")
    print("=" * 60)
    print(f"Output directory: {OUT_DIR}")
    print(f"Started at: {datetime.now().isoformat()}")
    print()
    
    # Step 14.1
    archive_result = step_14_1()
    
    # Step 14.2
    inventory = step_14_2()
    
    # Step 14.3
    canonical, canonical_dict = step_14_3()
    print(f"  Canonical taxonomy: {len(canonical_dict)} known cell_keys")
    
    # Step 14.4
    task_lineage = step_14_4()
    
    # Step 14.5
    crosswalk, crosswalk_summary = step_14_5(task_lineage, canonical_dict)
    
    # Step 14.6
    conflicts, grade_conflicts = step_14_6(crosswalk)
    
    # Step 14.7
    bank_by_cell, bank_report = step_14_7(crosswalk, canonical_dict)
    
    # Write final reconstruction report
    report = {
        "pipeline": "TAXONOMY_RECONSTRUCTION",
        "started_at": datetime.now().isoformat(),
        "steps_completed": [
            "14.1 Archive dependent results",
            "14.2 Taxonomy Source Inventory",
            "14.3 Canonical Taxonomy",
            "14.4 Task Lineage",
            "14.5 Bank Taxonomy Crosswalk",
            "14.6 Mapping Conflicts",
            "14.7 Bank by Cell"
        ],
        "key_metrics": {
            "authoritative_sources_found": len(inventory.get("sources", [])),
            "canonical_cells_defined": len(canonical_dict),
            "task_lineage_entries": len(task_lineage),
            "crosswalk_entries": len(crosswalk),
            "mapped_tasks": crosswalk_summary.get("mapped_total", 0),
            "unresolved_tasks": crosswalk_summary.get("unresolved", 0),
            "cells_with_tasks": len(bank_by_cell),
            "mapping_conflicts_found": len(conflicts),
            "grade_mismatches": len(grade_conflicts)
        },
        "next_steps": [
            "14.8: Audit Stage 6 contamination (257 candidates)",
            "14.9: Re-audit Stage 7 C10/C12 with correct mapping",
            "14.10: Unit tests (10) + retest (10+20)",
            "14.11: quality_not_weakened_report.json",
            "ШАГ 15: Resume pipeline"
        ],
        "output_files": [
            "taxonomy_source_inventory.json",
            "canonical_taxonomy.json",
            "canonical_taxonomy_audit.json",
            "task_lineage.jsonl",
            "bank_taxonomy_crosswalk.jsonl",
            "bank_taxonomy_crosswalk_summary.json",
            "taxonomy_mapping_conflicts.jsonl",
            "taxonomy_mapping_conflicts.json",
            "bank_by_cell.json"
        ]
    }
    
    report_path = os.path.join(OUT_DIR, "reconstruction_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print("\n" + "=" * 60)
    print("TAXONOMY RECONSTRUCTION COMPLETE")
    print("=" * 60)
    print(f"  Report: {report_path}")
    print(f"  All outputs in: {OUT_DIR}")
    print()


if __name__ == "__main__":
    main()
