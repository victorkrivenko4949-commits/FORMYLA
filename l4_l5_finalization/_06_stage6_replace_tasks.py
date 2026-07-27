#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Stage 6: 3-Candidate-Per-Slot Generation for REPLACE tasks (v2 — Reasoner).

For each replacement slot: generate 3 independent candidates per triple,
validate all, pick the best by quality_score. If accepted, add statement,
main_idea, task_type, fingerprint to cell-level context to forbid repetition
in subsequent triples. Max 5 triples (15 candidates) per slot.

Cells are processed sequentially within-slot, parallel across cells.

Uses DeepSeek Reasoner (deepseek-reasoner via generate_with_reasoning).
run_id = stage6_reasoner_v2 to distinguish from the failed chat-model run.

Outputs:
  - stage6_candidates.json                : All accepted candidates for Stage 7
  - stage6_generation_log.jsonl           : Detailed per-slot generation log
  - stage6_checkpoint.json                : Resumable checkpoint
  - stage6_candidate_selection.jsonl      : Per-slot candidate tracking report
"""

import json
import os
import sys
import uuid
import hashlib
import time
import re
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add project root to path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from ai.deepseek_client import DeepSeekClient

# ── Paths ────────────────────────────────────────────────────────────────────
SLOT_REPORT_PATH     = os.path.join(BASE_DIR, "corrected_slot_report.json")
BANK_PATH            = os.path.join(BASE_DIR, "..", "l4_l5_fill_output", "curated_bank_L4_L5_filled.json")
STAGE3_PATH          = os.path.join(BASE_DIR, "stage3_audit_results.json")
ID_MAPPING_PATH      = os.path.join(BASE_DIR, "task_id_to_import_key_mapping.json")

OUTPUT_CANDIDATES   = os.path.join(BASE_DIR, "stage6_candidates.json")
OUTPUT_LOG          = os.path.join(BASE_DIR, "stage6_generation_log.jsonl")
OUTPUT_SELECTION    = os.path.join(BASE_DIR, "stage6_candidate_selection.jsonl")
CHECKPOINT_PATH     = os.path.join(BASE_DIR, "stage6_checkpoint.json")

# ── Constants ────────────────────────────────────────────────────────────────
MAX_TRIPLES_PER_SLOT = 5        # max 5 triples (15 candidates) per slot
PARALLEL_WORKERS     = 10       # parallel threads for independent cells
GENERATION_MAX_TOKENS  = 8192   # Reasoner needs more tokens for CoT + answer JSON
RUN_ID               = "stage6_reasoner_v2"

# ── Helpers ──────────────────────────────────────────────────────────────────

def load_json(path: str, desc: str = "file") -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, data: Any, desc: str = "file") -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def parse_cell_key(cell_key: str) -> Dict[str, str]:
    """Parse cell key like 'G11|L5|T001|S1' into components."""
    parts = cell_key.split("|")
    if len(parts) >= 4:
        return {
            "grade": parts[0].lstrip("G"),
            "level": parts[1].lstrip("L"),
            "theme_id": parts[2],
            "slot": parts[3].lstrip("S"),
            "cell_key": cell_key
        }
    return {"cell_key": cell_key}
def compute_quality_score(candidate: Dict) -> float:
    """Compute quality score for a candidate (higher = better).

    Factors: solution_length, has_verification, structure, answer_clarity.
    Returns 0.0-1.0 score.
    """
    score = 0.5
    sol = candidate.get("solution", "") or ""
    if len(sol) > 200:
        score += 0.10
    if len(sol) > 500:
        score += 0.05
    verification_keywords = ["verification", "check", "test", "substitute", "plug"]
    if any(kw in sol.lower() for kw in verification_keywords):
        score += 0.15
    required = ["statement", "answer", "solution", "main_idea", "task_type", "why_level"]
    if all(candidate.get(f) for f in required):
        score += 0.10
    ans = candidate.get("answer", "") or ""
    if len(ans) < 200 and len(ans) > 0:
        score += 0.05
    return min(score, 1.0)


def generate_task_id() -> str:
    """Generate a unique task ID with timestamp and uuid fragment."""
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return f"gen_{ts}_{uuid.uuid4().hex[:8]}"


def compute_fingerprint(text: str) -> str:
    """Compute a SHA-256 fingerprint for deduplication."""
    cleaned = re.sub(r"\s+", " ", text.strip().lower())
    return hashlib.sha256(cleaned.encode("utf-8")).hexdigest()


def find_balanced_objects(text: str) -> List[str]:
    """Find all brace-balanced JSON-like objects in text.

    Handles nested braces, LaTeX braces \\{ \\}, and string-escaped braces.
    Returns list of balanced brace-delimited substrings.
    """
    results = []
    i = 0
    while i < len(text):
        # Find opening brace
        if text[i] != "{":
            i += 1
            continue
        # Check it's not LaTeX-escaped
        if i > 0 and text[i - 1] == "\\":
            i += 1
            continue
        # Try to find closing brace
        depth = 0
        in_string = False
        string_char = None
        j = i
        while j < len(text):
            ch = text[j]
            # Handle string boundaries
            if in_string:
                if ch == "\\" and j + 1 < len(text):
                    j += 2
                    continue
                if ch == string_char:
                    in_string = False
                j += 1
                continue
            if ch in ("\"", "'"):
                in_string = True
                string_char = ch
                j += 1
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    results.append(text[i:j + 1])
                    i = j + 1
                    break
            j += 1
        else:
            # No matching close found; move past this brace
            i += 1
            continue
        if depth == 0:
            continue
        i += 1
    return results


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Extract JSON object from model response with robust brace balancing.

    Handles 9 edge cases:
    1. Empty / None input → None
    2. No braces found → None
    3. Multiple objects → first valid one
    4. Nested LaTeX braces within strings → handled
    5. Truncated (unclosed) object → None
    6. Valid JSON with markdown fences → stripped
    7. Extra text before/after JSON → stripped
    8. JSON within code blocks → handled
    9. Malformed JSON (parse error) → None
    """
    if not text or not text.strip():
        return None
    # Strip markdown code fences first
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # Extract content between fences
        lines = cleaned.split("\n")
        fence_found = False
        content_lines = []
        for line in lines:
            if line.strip().startswith("```"):
                if fence_found:
                    break
                fence_found = True
                continue
            if fence_found:
                content_lines.append(line)
        if content_lines:
            cleaned = "\n".join(content_lines).strip()
    # Find all balanced objects
    candidates = find_balanced_objects(cleaned)
    if not candidates:
        return None
    # Try each candidate
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, ValueError):
            continue
    return None


def validate_candidate(candidate: Dict, slot_key: str, cell_context: List[str]) -> Dict[str, Any]:
    """Validate a single candidate. Returns validation result dict.

    Required fields: statement, answer, solution, main_idea, task_type, why_level
    Checks:
      - Schema: all 6 fields present and non-empty
      - No placeholder text
      - No duplicate fingerprint with existing cell context
    """
    required_fields = ["statement", "answer", "solution", "main_idea", "task_type", "why_level"]
    missing = [f for f in required_fields if not candidate.get(f)]
    placeholder_patterns = [
        r"^\s*\[.*(?:insert|placeholder|todo|your|provide|add).*\]\s*$",
        r"^\s*$",
    ]
    placeholders = []
    for f in required_fields:
        val = str(candidate.get(f, ""))
        for pat in placeholder_patterns:
            if re.match(pat, val, re.IGNORECASE):
                placeholders.append(f)
                break
    # Compute fingerprint for dedup
    statement = candidate.get("statement", "")
    fp = compute_fingerprint(statement) if statement else ""
    is_duplicate = fp in cell_context if fp else False
    is_valid = (
        len(missing) == 0
        and len(placeholders) == 0
        and not is_duplicate
    )
    return {
        "is_valid": is_valid,
        "missing_fields": missing,
        "has_placeholder": len(placeholders) > 0,
        "placeholder_fields": placeholders,
        "fingerprint": fp,
        "is_duplicate": is_duplicate,
        "rejection_reason": (
            "missing_fields" if missing else
            "placeholder" if placeholders else
            "duplicate" if is_duplicate else
            None
        )
    }


def _generate_single_candidate(
    client: DeepSeekClient,
    cell_info: Dict,
    slot_data: Dict,
    removal_reason: str,
    cell_context: List[str],
    triple_index: int
) -> Optional[Dict]:
    """Generate a single candidate using DeepSeek Reasoner.

    This is a TRUE independent generation: the model receives only the cell
    metadata and the statement to replace. It does NOT see any previously
    generated answer, solution, or main_idea from the generator or the original task.
    """
    try:
        messages = build_generator_prompt(cell_info, slot_data, removal_reason, cell_context, triple_index)
        # Extract system/user prompts from messages list for generate_with_reasoning()
        system_prompt_str = ""
        user_prompt_str = ""
        for msg in messages:
            if msg.get("role") == "system":
                system_prompt_str = msg.get("content", "")
            elif msg.get("role") == "user":
                user_prompt_str = msg.get("content", "")
        response = client.generate_with_reasoning(
            prompt=user_prompt_str,
            system_prompt=system_prompt_str,
            max_tokens=GENERATION_MAX_TOKENS,
        )
        if not response:
            return None
        raw_text = response
        if isinstance(response, dict):
            raw_text = response.get("content", response.get("text", str(response)))

        extracted = _extract_json(raw_text)
        if not extracted:
            return None

        task_id = generate_task_id()
        fingerprint = compute_fingerprint(extracted.get("statement", ""))

        candidate = {
            "task_id": task_id,
            "run_id": RUN_ID,
            **extracted,
            "fingerprint": fingerprint,
            "quality_score": 0.0,
            "validation": {},
            "triple_index": triple_index,
            "generation_time": datetime.utcnow().isoformat() + "Z",
        }
        return candidate
    except Exception as e:
        print(f"  [ERROR] Generation failed: {e}")
        return None


def process_single_slot(
    client: DeepSeekClient,
    cell_key: str,
    cell_info: Dict,
    slot_key: str,
    slot_data: Dict,
    cell_accepted_tasks: List[Dict]
) -> Optional[Dict]:
    """Process a single replacement slot by generating up to 5 triples (15 candidates).

    Cell-level sequential context:
      - cell_accepted_tasks is a shared list across slots within the same cell
      - Each accepted candidate's statement fingerprint, main_idea, and task_type
        are added to the context to prevent repetition
      - The list is mutated IN PLACE so subsequent slots see the accumulated context

    Per triple:
      1. Generate 3 independent candidates in parallel
      2. Validate each (schema, placeholders, dedup)
      3. Score validated candidates by quality_score
      4. Pick the best validated candidate
      5. If accepted, add to cell context and return
      6. If none validated, retry with next triple (max 5)

    Returns the selected candidate dict, or None if all triples exhausted.
    """
    removal_reason = extract_removal_reasons(slot_data)

    for triple_idx in range(MAX_TRIPLES_PER_SLOT):
        print(f"  Triple {triple_idx + 1}/{MAX_TRIPLES_PER_SLOT} for {slot_key}")

        # Build cell context from accepted tasks (fingerprints)
        cell_context = [t.get("fingerprint", "") for t in cell_accepted_tasks if t.get("fingerprint")]

        # Generate 3 candidates in parallel within this triple
        candidates = []
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(
                    _generate_single_candidate,
                    client, cell_info, slot_data, removal_reason,
                    cell_context, triple_idx
                )
                for _ in range(3)
            ]
            for future in as_completed(futures):
                try:
                    result = future.result(timeout=120)
                    if result:
                        candidates.append(result)
                except Exception as e:
                    print(f"    [ERROR] Candidate generation failed: {e}")

        if not candidates:
            print(f"  No candidates generated in triple {triple_idx + 1}")
            continue

        # Validate all candidates
        for cand in candidates:
            validation = validate_candidate(cand, slot_key, cell_context)
            cand["validation"] = validation
            if validation["is_valid"]:
                cand["quality_score"] = compute_quality_score(cand)
            else:
                cand["quality_score"] = 0.0

        # Sort by quality_score descending, pick best VALID one
        valid_sorted = sorted(
            [c for c in candidates if c.get("validation", {}).get("is_valid")],
            key=lambda c: c.get("quality_score", 0.0),
            reverse=True
        )

        if not valid_sorted:
            print(f"  No valid candidates in triple {triple_idx + 1}")
            continue

        selected = valid_sorted[0]
        print(f"  Selected candidate {selected['task_id']} (score={selected['quality_score']:.3f})")

        # Add to cell context (mutate in-place!)
        fp = selected.get("fingerprint", "")
        if fp and fp not in cell_context:
            cell_context.append(fp)
        cell_accepted_tasks.append({
            "task_id": selected["task_id"],
            "slot_key": slot_key,
            "cell_key": cell_key,
            "fingerprint": fp,
            "statement": selected.get("statement", ""),
            "main_idea": selected.get("main_idea", ""),
            "task_type": selected.get("task_type", ""),
        })

        return selected

    print(f"  [FAIL] All {MAX_TRIPLES_PER_SLOT} triples exhausted for {slot_key} - no valid candidate")
    return None


# ── Batch Processing ──────────────────────────────────────────────────────────

def extract_forbidden_constructs(cell_context: List[str]) -> str:
    """Build a 'forbidden' string warning the generator about used statements."""
    if not cell_context:
        return ""
    return "IMPORTANT: The following statement fingerprints are already used in this cell. Do NOT generate a task with a similar statement: " + ", ".join(cell_context[:5])


def extract_removal_reasons(slot_data: Dict) -> str:
    """Extract removal reason from slot data."""
    return slot_data.get("removal_reason", slot_data.get("reason", ""))


def build_generator_prompt(cell_info: Dict, slot_data: Dict, removal_reason: str, cell_context: List[str], triple_index: int) -> List[Dict]:
    """Build a prompt for the generator model.
    
    TRUE independence: model sees only cell metadata + statement to replace.
    NO previous answers, solutions, or main_ideas are leaked.
    """
    grade = cell_info.get("grade", "?")
    level = cell_info.get("level", "?")
    theme = cell_info.get("theme", "")
    subtopic = cell_info.get("subtopic", "")
    topic = cell_info.get("topic", "")
    statement_to_replace = slot_data.get("statement", "")
    forbidden = extract_forbidden_constructs(cell_context)
    removal_str = f"Removal reason: {removal_reason}" if removal_reason else ""
    
    system_prompt = (
        "You are an expert mathematics problem writer. "
        "Generate a replacement problem for a L4/L5 math competition task. "
        "You must output a valid JSON object with these EXACT fields:\n"
        '  "statement":  The problem statement (clear, self-contained)\n'
        '  "answer":     The final answer with explanation\n'
        '  "solution":   A detailed step-by-step solution\n'
        '  "main_idea":  One sentence describing the key insight\n'
        '  "task_type":  One of: "computation", "proof", "construction", "classification"\n'
        '  "why_level":  One of: "l4_olympiad", "l5_olympiad"\n'
        "Return ONLY valid JSON, no extra text."
    )
    
    user_prompt_parts = [
        f"Grade: {grade}  |  Difficulty Level: {level}  |  Theme: {theme}",
        f"Topic: {topic}  |  Subtopic: {subtopic}" if subtopic else f"Topic: {topic}",
        f"Statement to replace: {statement_to_replace}",
        removal_str,
        f"Triple attempt #{triple_index + 1} of {MAX_TRIPLES_PER_SLOT}",
        forbidden,
    ]
    user_prompt = "\n\n".join(p for p in user_prompt_parts if p)
    system = {"role": "system", "content": system_prompt}
    user = {"role": "user", "content": user_prompt}
    return [system, user]


def log_selection(log_path: str, entry: Dict) -> None:
    """Append a selection log entry to the JSONL file."""
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")




def process_batch(
    client: DeepSeekClient,
    slot_report: Dict,
    bank_data: List[Dict],
    stage3_data: List[Dict],
    checkpoint: Optional[Dict] = None
) -> Tuple[Dict, List[Dict]]:
    """Process all replacement slots across cells.

    NOTE: corrected_slot_report.json has FLAT keys under per_cell_slots,
          e.g. "G10|L4|T013|S0" -> {stats_dict}.
          We restructure them into {cell_base: {slot_key: stats_dict}}.

    Architecture:
      - Slots are grouped by cell_key (cell part only, dropping slot suffix)
      - Cells are processed sequentially (for context accumulation)
      - Within each cell, slots share a cell_accepted_tasks list
      - Across cells, processing is parallel via ThreadPoolExecutor

    Returns (candidates_dict, selection_log).
    """
    slot_report_data = slot_report  # main() already extracts per_cell_slots
    
    # ── Restructure flat keys into per-cell grouping ──────────────────
    # Flat keys like "G10|L4|T013|S0" -> cell_part="G10|L4|T013", slot="S0"
    restructured = {}       # {cell_part: {slot_key: stats_dict}}
    flat_key_to_slot = {}   # {cell_part+"|"+slot_key: slot_key} for checkpoint
    for flat_key, stats in slot_report_data.items():
        parts = flat_key.split("|")
        if len(parts) >= 4:
            cell_part = "|".join(parts[:-1])   # e.g. "G10|L4|T013"
            slot_part = parts[-1]              # e.g. "S0"
            if cell_part not in restructured:
                restructured[cell_part] = {}
            restructured[cell_part][slot_part] = stats
            flat_key_to_slot[flat_key] = slot_part
        else:
            # Unusual key format, keep as-is with a synthetic slot
            restructured[flat_key] = {"__data__": stats}

    # ── Checkpoint ────────────────────────────────────────────────────
    completed_slots = set()
    if checkpoint:
        completed_slots = set(checkpoint.get("completed_slots", []))

    # Build work items from restructured data
    per_cell = {}
    for cell_key, cell_slots in restructured.items():
        cell_slot_keys = list(cell_slots.keys())
        remaining = [k for k in cell_slot_keys if k not in completed_slots]
        if remaining:
            # Parse cell_key (e.g. "G10|L4|T013") but parse_cell_key expects
            # 4-part key; we build cell_info manually for 3-part keys.
            c_parts = cell_key.split("|")
            cell_info = {
                "cell_key": cell_key,
                "grade": c_parts[0].lstrip("G") if len(c_parts) >= 1 else "",
                "level": c_parts[1].lstrip("L") if len(c_parts) >= 2 else "",
                "theme_id": c_parts[2] if len(c_parts) >= 3 else "",
            }
            per_cell[cell_key] = {
                "cell_info": cell_info,
                "slot_keys": remaining
            }

    if not per_cell:
        print("All slots already completed per checkpoint.")
        if os.path.exists(OUTPUT_CANDIDATES):
            return load_json(OUTPUT_CANDIDATES), []
        return {}, []

    print(f"Processing {len(per_cell)} cells with remaining slots")

    # Look up cell info from bank
    # NOTE: bank cell_key includes the slot suffix (e.g. "G10|L4|T013|S0").
    # We build a secondary index keyed by cell_part (no slot) for enrichment.
    # Build bank index by grade+level (bank has grade and level fields but no cell_key)
    # Bank entries have grade (int) and level (int) — composite key is G{grade}|L{level}
    # matching the cell_key prefix format (e.g. "G10|L4" from "G10|L4|T013")
    bank_by_cell_part = {}
    for entry in bank_data:
        g = str(entry.get("grade", "")).strip()
        l_val = str(entry.get("level", "")).strip()
        if g and l_val:
            gl_key = f"G{g}|L{l_val}"
            if gl_key not in bank_by_cell_part:
                bank_by_cell_part[gl_key] = entry

    candidates = {}
    selection_log = []

    # Track completed items. We store the full flat key in checkpoint
    # (e.g. "G10|L4|T013|S0") so it uniquely identifies completed slots.
    completed = set(completed_slots)

    def process_cell(cell_key: str, cell_info: Dict, slot_keys: List[str]) -> Dict:
        """Process all slots in a single cell (sequential within cell)."""
        cell_accepted_tasks = []
        cell_candidates = {}

        # Enrich cell info from bank once — match by grade+level
        grade_from_cell = str(cell_info.get("grade", "")).strip()
        level_from_cell = str(cell_info.get("level", "")).strip()
        gl_key = f"G{grade_from_cell}|L{level_from_cell}"
        bank_entry = bank_by_cell_part.get(gl_key, {})
        full_cell_info = {
            **cell_info,
            "grade": bank_entry.get("grade", cell_info.get("grade", "")),
            "level": bank_entry.get("level", cell_info.get("level", "")),
            "theme": bank_entry.get("theme_name", bank_entry.get("theme", "")),
            "subtopic": bank_entry.get("subtopic", ""),
            "topic": bank_entry.get("topic", ""),
        }

        for slot_key in slot_keys:
            flat_key = f"{cell_key}|{slot_key}"
            print(f"\n{'='*60}")
            print(f"Processing slot: {flat_key}")

            slot_data = restructured.get(cell_key, {}).get(slot_key, {})
            if not slot_data:
                print(f"  No slot data found for {flat_key}, skipping")
                continue

            # Call process_single_slot for this slot
            selected = process_single_slot(
                client, flat_key, full_cell_info, slot_key, slot_data, cell_accepted_tasks
            )

            if selected:
                # Add to candidates (keyed by flat_key so bank lookup works downstream)
                cell_candidates[flat_key] = selected
                completed.add(flat_key)

                # Log selection
                log_entry = {
                    "run_id": RUN_ID,
                    "cell_key": cell_key,
                    "slot_key": slot_key,
                    "flat_key": flat_key,
                    "task_id": selected.get("task_id", ""),
                    "quality_score": selected.get("quality_score", 0.0),
                    "fingerprint": selected.get("fingerprint", ""),
                    "timestamp": datetime.utcnow().isoformat(),
                }
                selection_log.append(log_entry)
                log_selection(OUTPUT_SELECTION, log_entry)
                print(f"  [OK] Slot {flat_key} completed - task_id={selected.get('task_id', '?')}")
            else:
                print(f"  [FAIL] Slot {flat_key} - no valid candidate after all triples")

        return cell_candidates

    # Process cells in parallel
    all_results = {}
    cell_items = list(per_cell.items())
    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as executor:
        futures = {}
        for cell_key, cell_data in cell_items:
            future = executor.submit(
                process_cell, cell_key, cell_data["cell_info"], cell_data["slot_keys"]
            )
            futures[future] = cell_key

        for future in as_completed(futures):
            cell_key = futures[future]
            try:
                result = future.result(timeout=600)
                if result:
                    all_results.update(result)
            except Exception as e:
                print(f"  [ERROR] Cell {cell_key} failed: {e}")

            # Save checkpoint after each cell
            checkpoint_data = {
                "completed_slots": sorted(completed),
                "run_id": RUN_ID,
                "timestamp": datetime.utcnow().isoformat(),
            }
            with open(CHECKPOINT_PATH, "w", encoding="utf-8") as f:
                json.dump(checkpoint_data, f, ensure_ascii=False, indent=2)

    print(f"\nProcessed {len(all_results)} slots across {len(per_cell)} cells")
    return all_results, selection_log



# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    """Pipeline entry point: load data → process batch → save candidates."""
    print("=" * 60)
    print(f"Stage 6: 3-Candidate Replacement Generation  (run_id={RUN_ID})")
    print(f"  Slot report : {SLOT_REPORT_PATH}")
    print(f"  Bank data   : {BANK_PATH}")
    print(f"  Stage 3     : {STAGE3_PATH}")
    print(f"  Output      : {OUTPUT_CANDIDATES}")
    print(f"  Selection   : {OUTPUT_SELECTION}")
    print("=" * 60)

    # ── Load data ──────────────────────────────────────────────────────────────
    print("\n[1/4] Loading data...")
    slot_report = load_json(SLOT_REPORT_PATH, "slot report")
    bank_data = load_json(BANK_PATH, "bank data")
    stage3_data = load_json(STAGE3_PATH, "stage3 data")

    # Unpack slot report (corrected_slot_report has 'per_cell_slots' and 'task_counts')
    report_data = slot_report.get("per_cell_slots", slot_report)
    task_counts = slot_report.get("task_counts", {})

    total_slots = len(report_data)
    print(f"  Loaded {len(bank_data)} bank entries, {total_slots} slot entries")

    # ── Checkpoint resume ──────────────────────────────────────────────────────
    checkpoint = None
    if os.path.exists(CHECKPOINT_PATH):
        try:
            checkpoint = load_json(CHECKPOINT_PATH, "checkpoint")
            cp_run_id = checkpoint.get("run_id", "")
            if cp_run_id == RUN_ID:
                completed = checkpoint.get("completed_slots", [])
                print(f"\n[2/4] Resuming from checkpoint: {len(completed)} slots already done")
            else:
                print(f"\n[2/4] Checkpoint run_id mismatch ({cp_run_id} != {RUN_ID}), starting fresh")
                checkpoint = None
        except Exception as e:
            print(f"  Checkpoint load failed: {e}, starting fresh")
            checkpoint = None

    if checkpoint is None:
        print("\n[2/4] Starting fresh — no valid checkpoint found")
        # Clear old checkpoint files for clean run
        for old_cp in [CHECKPOINT_PATH, OUTPUT_CANDIDATES, OUTPUT_LOG, OUTPUT_SELECTION]:
            if os.path.exists(old_cp):
                os.remove(old_cp)
                print(f"  Removed stale file: {old_cp}")

    # ── Initialize client ──────────────────────────────────────────────────────
    print("\n[3/4] Initializing DeepSeek Reasoner client...")
    client = DeepSeekClient()
    print("  Client ready")

    # ── Run batch processing ───────────────────────────────────────────────────
    print("\n[4/4] Running batch generation (parallel cells, sequential slots)...")
    candidates, selection_log = process_batch(
        client=client,
        slot_report=report_data,
        bank_data=bank_data,
        stage3_data=stage3_data,
        checkpoint=checkpoint,
    )

    # ── Save results ───────────────────────────────────────────────────────────
    output = {
        "run_id": RUN_ID,
        "generated_at": datetime.utcnow().isoformat(),
        "candidates": candidates,
        "summary": {
            "total_slots": total_slots,
            "completed_slots": len(candidates),
            "failed_slots": total_slots - len(candidates),
            "total_selection_entries": len(selection_log),
        },
    }
    save_json(OUTPUT_CANDIDATES, output, "candidates output")

    # ── Clean up checkpoint on success ─────────────────────────────────────────
    if os.path.exists(CHECKPOINT_PATH):
        os.remove(CHECKPOINT_PATH)
        print(f"\n  Cleaned up checkpoint file")

    # ── Report ─────────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print(f"Stage 6 COMPLETE — run_id={RUN_ID}")
    print(f"  Total slots in report : {total_slots}")
    print(f"  Completed slots       : {len(candidates)}")
    print(f"  Failed slots          : {total_slots - len(candidates)}")
    print(f"  Selection log entries : {len(selection_log)}")
    print(f"  Output saved to       : {OUTPUT_CANDIDATES}")
    print(f"  Selection report      : {OUTPUT_SELECTION}")
    if selection_log:
        accepted = sum(1 for e in selection_log if e.get("quality_score", 0) > 0)
        print(f"  Accepted candidates   : {accepted}")
    print("=" * 60)


if __name__ == "__main__":
    main()
