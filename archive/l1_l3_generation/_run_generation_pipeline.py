#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
L1-L3 Generation Pipeline — Position-Based with 13-Step AND-Gate Verification
================================================================================

Architecture:
    for level_cell in level_cells:
        for position in 1..5:
            generate_candidates_until_accepted()
            atomic checkpoint

Terminology:
    base_cell:      G{grade}|T{xxx}|S{x}           (128 cells)
    level_cell:     G{grade}|L{level}|T{xxx}|S{x}  (384 cells)
    task_position:  1-5                             (5 per level_cell)
    candidate:      Generated task before verification

Key features:
    - Position-based generation: for level_cell, for position 1-5
    - 13-step AND-gate verification (Schema, Uniqueness, Solver A/B, ... Content Arbiter)
    - Task diversity: 5 tasks per cell differ in main_idea/type/structure
    - Atomic checkpoints after every accepted task (.tmp -> atomic rename)
    - Technical errors (timeout, DNS, HTTP 429/5xx) != content rejection
    - Position-based IDs: G{grade}_{topic}_{subtopic}_{level}_{position:02d}
    - Pilot mode: 3 level_cells (L1, L2, L3) -> auto full pipeline on success

Outputs:
    - l1_l3_generated_raw.json            — all accepted tasks (flat list)
    - l1_l3_generated_audit.json          — generation metrics and status
    - l1_l3_generated_by_cell.json        — tasks grouped by level_cell
    - l1_l3_generated_statistics.json     — statistics
    - l1_l3_generated_by_grade.json       — tasks grouped by grade
    - l1_l3_generated_by_level.json       — tasks grouped by level
    - l1_l3_generated_by_topic.json       — tasks grouped by topic
    - l1_l3_verification_report.json      — per-task verification results
    - l1_l3_generation_checkpoint.json    — resumable state
    - l1_l3_generation.progress           — progress tracker
    - FINAL_REPORT.md                     — final report
"""

import os
import sys
import json
import time
import hashlib
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Set, Tuple

# Import 13-step verification pipeline
from _verification_gates import run_verification_pipeline

# ============================================================================
# Configuration
# ============================================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

GRID_PATH = os.path.join(BASE_DIR, "target_grid.json")
TAXONOMY_PATH = os.path.join(BASE_DIR, "canonical_taxonomy.json")
SMOKE_AUDIT_PATH = os.path.join(BASE_DIR, "smoke_test_deepseek_audit.json")
FORMULA_PATH = os.path.join(BASE_DIR, "task_count_formula.json")

OUTPUT_DIR = BASE_DIR  # all outputs go to l1_l3_generation/

OUTPUT_RAW = os.path.join(OUTPUT_DIR, "l1_l3_generated_raw.json")
OUTPUT_AUDIT = os.path.join(OUTPUT_DIR, "l1_l3_generated_audit.json")
OUTPUT_BY_CELL = os.path.join(OUTPUT_DIR, "l1_l3_generated_by_cell.json")
OUTPUT_STATISTICS = os.path.join(OUTPUT_DIR, "l1_l3_generated_statistics.json")
OUTPUT_BY_GRADE = os.path.join(OUTPUT_DIR, "l1_l3_generated_by_grade.json")
OUTPUT_BY_LEVEL = os.path.join(OUTPUT_DIR, "l1_l3_generated_by_level.json")
OUTPUT_BY_TOPIC = os.path.join(OUTPUT_DIR, "l1_l3_generated_by_topic.json")
OUTPUT_VERIFICATION = os.path.join(OUTPUT_DIR, "l1_l3_verification_report.json")
OUTPUT_CHECKPOINT = os.path.join(OUTPUT_DIR, "l1_l3_generation_checkpoint.json")
OUTPUT_PROGRESS = os.path.join(OUTPUT_DIR, "l1_l3_generation.progress")
OUTPUT_FINAL_REPORT = os.path.join(OUTPUT_DIR, "FINAL_REPORT.md")

API_BASE = "https://api.deepseek.com"
MODEL_NAME = "deepseek-reasoner"

TASKS_PER_LEVEL_CELL = 5
CANDIDATES_PER_BATCH = 3
MAX_ATTEMPTS_PER_POSITION = 15
API_TIMEOUT = 120
RATE_LIMIT_DELAY = 1.5
CONSECUTIVE_TECH_ERROR_LIMIT = 10
CIRCUIT_BREAKER_LIMIT = 5

PILOT_CELLS = [
    {"grade": 5, "topic_id": "T002", "subtopic_id": "S0", "level": "L1"},
    {"grade": 7, "topic_id": "T026", "subtopic_id": "S0", "level": "L2"},
    {"grade": 9, "topic_id": "T038", "subtopic_id": "S0", "level": "L3"},
]

LEVEL_DESCRIPTIONS = {
    "L1": (
        "Уровень L1 (обычная школа): задача не требует специальной олимпиадной подготовки, "
        "достаточно знаний школьной программы. Время решения — 5–10 минут. "
        "Подходит для начинающих олимпиадников."
    ),
    "L2": (
        "Уровень L2 (школьный этап ВсОШ): задача требует олимпиадной смекалки и нестандартного "
        "мышления, опирается на школьную программу. Время решения — 10–20 минут. "
        "Соответствует задачам школьного этапа Всероссийской олимпиады."
    ),
    "L3": (
        "Уровень L3 (муниципальный этап ВсОШ): задача повышенной сложности, требует комбинации "
        "нескольких идей и глубокого понимания темы. Время решения — 20–40 минут. "
        "Соответствует задачам муниципального этапа Всероссийской олимпиады."
    ),
}

# Task type diversity hints for prompt engineering
WANTED_TYPES = [
    "вычислительная задача",
    "доказательная задача",
    "задача на построение",
    "задача на оценку + пример",
    "комбинаторная задача",
    "задача с параметром",
    "геометрическая задача",
    "текстовая задача",
    "задача на делимость",
    "задача на инвариант",
    "задача на раскраску",
    "игровая задача",
    "задача на конструкцию",
    "задача на экстремум",
    "задача на принцип Дирихле",
]

# ============================================================================
# Helpers
# ============================================================================

def _load_api_key() -> str:
    """Load DEEPSEEK_API_KEY from .env or environment."""
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if key:
        return key
    env_path = os.path.join(os.path.dirname(BASE_DIR), ".env")
    if not os.path.exists(env_path):
        env_path = os.path.join(BASE_DIR, ".env")
    if os.path.exists(env_path):
        for line in open(env_path, "r", encoding="utf-8").readlines():
            line = line.strip()
            if line.startswith("DEEPSEEK_API_KEY") and "=" in line:
                key = line.split("=", 1)[1].strip().strip("\"'").strip()
                break
    return key


def _timestamp() -> str:
    """ISO 8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def _make_task_id(grade: int, topic_id: str, subtopic_id: str, level: str, position: int) -> str:
    """Generate position-based task ID: G5_T002_S0_L1_01"""
    return f"G{grade}_{topic_id}_{subtopic_id}_{level}_{position:02d}"


def _make_base_cell_key(grade: int, topic_id: str, subtopic_id: str) -> str:
    """Generate base cell key: G5_T002_S0"""
    return f"G{grade}_{topic_id}_{subtopic_id}"


def _make_level_cell_key(grade: int, topic_id: str, subtopic_id: str, level: str) -> str:
    """Generate level cell key: G5_T002_S0_L1"""
    return f"G{grade}_{topic_id}_{subtopic_id}_{level}"


def _atomic_save(data: Any, path: str):
    """Atomically save JSON to path via .tmp + rename."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def _load_json(path: str, label: str) -> dict:
    """Load and return JSON from path, with error handling."""
    if not os.path.exists(path):
        print(f"ERROR: {label} not found at: {path}")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _check_smoke_status():
    """Verify smoke test passed before proceeding."""
    if not os.path.exists(SMOKE_AUDIT_PATH):
        print("ERROR: Smoke test audit not found. Run _run_smoke_test_deepseek.py first.")
        sys.exit(1)
    audit = _load_json(SMOKE_AUDIT_PATH, "Smoke audit")
    if audit.get("status") != "SMOKE_OK":
        print(f"ERROR: Smoke test status is {audit.get('status')}, expected SMOKE_OK. "
              "Run _run_smoke_test_deepseek.py and fix network/API issues first.")
        sys.exit(1)
    print(f"  [OK] Smoke test passed (SMOKE_OK). Proceeding with generation.")


def _is_technical_error(result: Any) -> bool:
    """Check if a verification result is a technical error (not a content rejection)."""
    if isinstance(result, str):
        result_lower = result.lower()
        tech_signals = [
            "timeout", "timed out", "dns", "connection refused",
            "connection reset", "http 429", "http 500", "http 502",
            "http 503", "rate limit", "too many requests",
            "internal server error", "service unavailable",
            "bad gateway", "gateway timeout",
            "empty response", "server error",
            "cannot connect", "name or service not known",
            "temporary failure in name resolution",
        ]
        return any(signal in result_lower for signal in tech_signals)
    return False


def _write_progress(path: str, line: str):
    """Append a progress line to the progress file."""
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ============================================================================
# Build level cells from target_grid.json
# ============================================================================

def build_level_cells(grid: dict) -> list:
    """
    Convert target_grid into a flat list of level_cells.
    Each level_cell = {grade, topic_id, topic_name, subtopic_id,
                       subtopic_name, curriculum_reason, level,
                       base_cell_key, level_cell_key}
    """
    cells = []
    levels = ["L1", "L2", "L3"]

    for grade_str, grade_data in grid.get("grades", {}).items():
        grade = int(grade_str)
        for topic_id, topic_data in grade_data.get("topics", {}).items():
            topic_name = topic_data.get("topic_name", topic_id)
            for subtopic_id, st_data in topic_data.get("subtopics", {}).items():
                if not st_data.get("allowed", True):
                    continue
                subtopic_name = st_data.get("subtopic_name", subtopic_id)
                curriculum_reason = st_data.get("curriculum_reason", "")
                base_key = _make_base_cell_key(grade, topic_id, subtopic_id)

                for level in levels:
                    lc_key = _make_level_cell_key(grade, topic_id, subtopic_id, level)
                    cells.append({
                        "grade": grade,
                        "topic_id": topic_id,
                        "topic_name": topic_name,
                        "subtopic_id": subtopic_id,
                        "subtopic_name": subtopic_name,
                        "curriculum_reason": curriculum_reason,
                        "level": level,
                        "base_cell_key": base_key,
                        "level_cell_key": lc_key,
                    })

    return cells


# ============================================================================
# Build generation prompt for a level cell (with diversity from existing tasks)
# ============================================================================

def build_prompt(cell: dict, existing_cell_tasks: List[dict] = None) -> list:
    """
    Build messages array for DeepSeek API.
    Includes diversity context: lists already-accepted tasks for this cell
    so the model avoids generating similar tasks.
    """
    grade = cell["grade"]
    topic_name = cell["topic_name"]
    subtopic_name = cell["subtopic_name"]
    level = cell["level"]
    level_desc = LEVEL_DESCRIPTIONS.get(level, "")
    curriculum_reason = cell["curriculum_reason"]

    # Diversity context
    diversity_note = ""
    if existing_cell_tasks:
        diversity_note = "\n\nВАЖНО: Для данной ячейки уже приняты следующие задачи. "
        diversity_note += "Новая задача ДОЛЖНА отличаться от них по основной идее, типу и структуре:\n"
        for et in existing_cell_tasks:
            stmt_short = et.get("statement", "")[:120]
            diversity_note += f"- {et.get('task_id', '?')}: {stmt_short}...\n"

    system_msg = (
        "Ты — составитель олимпиадных задач по математике. "
        "Твоя задача — создать оригинальную, качественную олимпиадную задачу "
        "с полным решением и ответом. "
        "Задача должна быть новой, не повторять известные олимпиадные задачи. "
        "Все размышления и ответ пиши на русском языке.\n\n"
        "Отвечай ТОЛЬКО в следующем JSON-формате, без дополнительного текста:\n"
        "```json\n"
        "{\n"
        '  "statement": "Условие задачи",\n'
        '  "answer": "Краткий ответ",\n'
        '  "solution": "Полное решение с объяснением"\n'
        "}\n"
        "```"
    )

    user_msg = (
        f"Составь олимпиадную задачу по математике для {grade}-го класса.\n\n"
        f"Тема: {topic_name}\n"
        f"Подтема: {subtopic_name}\n"
        f"Уровень сложности: {level}\n\n"
        f"{level_desc}\n\n"
        f"Обоснование включения в программу: {curriculum_reason}\n\n"
        "Требования к задаче:\n"
        "1. Задача должна быть оригинальной (не копировать известные олимпиадные задачи).\n"
        "2. Условие должно быть чётким и однозначным.\n"
        "3. Решение должно быть полным, с пошаговым объяснением.\n"
        "4. Ответ должен быть точным (число, выражение, или краткая формулировка).\n"
        "5. Задача должна точно соответствовать указанной теме и подтеме.\n"
        "6. Сложность должна строго соответствовать указанному уровню.\n"
        f"{diversity_note}"
        "\nВерни JSON с полями: statement, answer, solution."
    )

    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]


# ============================================================================
# API call with retry
# ============================================================================

def call_deepseek(
    api_key: str,
    messages: list,
    attempt: int = 1,
) -> tuple:
    """
    Make a chat completion call to deepseek-reasoner.
    Returns (success: bool, result: dict|str, duration_ms: float).
    """
    payload = json.dumps({
        "model": MODEL_NAME,
        "messages": messages,
        "max_tokens": 4096,
    }).encode("utf-8")

    t0 = time.time()
    try:
        req = urllib.request.Request(
            f"{API_BASE}/v1/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=API_TIMEOUT)
        body = resp.read().decode("utf-8")
        data = json.loads(body)
        elapsed = (time.time() - t0) * 1000

        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})
        content = message.get("content", "")
        finish_reason = choice.get("finish_reason", "")
        usage = data.get("usage", {})

        if not content:
            return False, f"Empty content, finish_reason={finish_reason}", elapsed

        return True, {
            "content": content,
            "finish_reason": finish_reason,
            "usage": usage,
        }, elapsed

    except urllib.error.HTTPError as e:
        elapsed = (time.time() - t0) * 1000
        body = e.read().decode("utf-8", errors="replace")[:500]
        return False, f"HTTP {e.code}: {body}", elapsed

    except json.JSONDecodeError as e:
        elapsed = (time.time() - t0) * 1000
        return False, f"JSON parse failure: {e}", elapsed

    except Exception as e:
        elapsed = (time.time() - t0) * 1000
        return False, f"Request failure: {e}", elapsed


# ============================================================================
# Parse task JSON from model output
# ============================================================================

def extract_json_from_content(content: str) -> dict:
    """
    Extract JSON from model output.
    Tries parsing directly, then falls back to extracting code-fenced JSON.
    """
    content = content.strip()
    if content.startswith("```"):
        lines = content.split("\n")
        clean_lines = []
        for line in lines:
            if line.strip().startswith("```"):
                continue
            clean_lines.append(line)
        content = "\n".join(clean_lines).strip()

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # Try balanced-brace extraction
    brace_depth = 0
    start_idx = -1
    for i, ch in enumerate(content):
        if ch == "{":
            if brace_depth == 0:
                start_idx = i
            brace_depth += 1
        elif ch == "}":
            brace_depth -= 1
            if brace_depth == 0 and start_idx >= 0:
                candidate = content[start_idx:i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    continue

    raise ValueError(f"Could not extract JSON from content (len={len(content)})")


def validate_candidate(task: dict) -> tuple:
    """
    Validate a candidate task has required fields and reasonable content.
    Returns (is_valid: bool, errors: list).
    """
    errors = []
    required = ["statement", "answer", "solution"]
    for field in required:
        if field not in task:
            errors.append(f"Missing field: {field}")
        elif not isinstance(task[field], str) or not task[field].strip():
            errors.append(f"Field '{field}' is empty or not a string")

    if not errors:
        statement = task["statement"].strip()
        answer = task["answer"].strip()
        solution = task["solution"].strip()

        if len(statement) < 20:
            errors.append(f"Statement too short ({len(statement)} chars)")
        if len(answer) < 1:
            errors.append("Answer is empty")
        if len(solution) < 50:
            errors.append(f"Solution too short ({len(solution)} chars)")

    return len(errors) == 0, errors


# ============================================================================
# Batch generation: generate CANDIDATES_PER_BATCH candidates in one call
# ============================================================================

def generate_candidates_batch(
    api_key: str,
    cell: dict,
    existing_cell_tasks: List[dict],
    batch_size: int = CANDIDATES_PER_BATCH,
) -> dict:
    """
    Generate a batch of candidates for a level cell.
    Returns {"success": bool, "candidates": list, "error": str, "duration_ms": float}.
    """
    messages = build_prompt(cell, existing_cell_tasks)
    success, result, duration_ms = call_deepseek(api_key, messages)

    if not success:
        return {"success": False, "candidates": [], "error": str(result), "duration_ms": duration_ms}

    content = result["content"]
    try:
        task_data = extract_json_from_content(content)
    except ValueError as e:
        return {"success": False, "candidates": [], "error": f"Parse error: {e}", "duration_ms": duration_ms}

    is_valid, errors = validate_candidate(task_data)
    if not is_valid:
        return {"success": False, "candidates": [], "error": f"Validation errors: {errors}", "duration_ms": duration_ms}

    # Single candidate per call (deepseek-reasoner generates one)
    candidate = {
        "statement": task_data["statement"].strip(),
        "answer": task_data["answer"].strip(),
        "solution": task_data["solution"].strip(),
        "usage": result.get("usage", {}),
        "generated_at": _timestamp(),
        "model": MODEL_NAME,
    }

    return {"success": True, "candidates": [candidate], "error": None, "duration_ms": duration_ms}


# ============================================================================
# Core position-based loop: generate candidates until one passes 13 gates
# ============================================================================

def generate_candidates_until_accepted(
    api_key: str,
    cell: dict,
    position: int,
    existing_cell_tasks: List[dict],
    existing_ids: set,
    existing_statements: List[str],
    verification_report: dict,
) -> dict:
    """
    For a single position, generate up to MAX_ATTEMPTS_PER_POSITION candidates,
    run each through the 13-step AND-gate verification pipeline.
    
    Returns:
        {"accepted": bool, "task": dict|None, "attempts": int,
         "tech_errors": int, "rejections": int, "reason": str}
    """
    grade = cell["grade"]
    topic_id = cell["topic_id"]
    subtopic_id = cell["subtopic_id"]
    level = cell["level"]
    level_cell_key = cell["level_cell_key"]

    task_id = _make_task_id(grade, topic_id, subtopic_id, level, position)

    attempts = 0
    tech_errors = 0
    rejections = 0

    for attempt in range(1, MAX_ATTEMPTS_PER_POSITION + 1):
        attempts += 1

        # --- Generate ---
        batch_result = generate_candidates_batch(api_key, cell, existing_cell_tasks)

        if not batch_result["success"]:
            error_str = batch_result.get("error", "unknown error")
            if _is_technical_error(error_str):
                tech_errors += 1
                print(f"    [TECH] Position {position}, attempt {attempt}: {error_str[:100]}")
                if tech_errors >= CONSECUTIVE_TECH_ERROR_LIMIT:
                    print(f"    [HALT] {CONSECUTIVE_TECH_ERROR_LIMIT} consecutive tech errors. Halting.")
                    return {
                        "accepted": False, "task": None,
                        "attempts": attempts, "tech_errors": tech_errors,
                        "rejections": rejections,
                        "reason": f"CONSECUTIVE_TECH_ERROR_LIMIT ({CONSECUTIVE_TECH_ERROR_LIMIT})",
                    }
                time.sleep(RATE_LIMIT_DELAY)
                continue
            else:
                rejections += 1
                print(f"    [FAIL] Position {position}, attempt {attempt}: {error_str[:100]}")
                time.sleep(RATE_LIMIT_DELAY)
                continue

        candidate = batch_result["candidates"][0]

        # --- 13-step AND-gate verification ---
        print(f"    [VERIFY] Position {position}, attempt {attempt}...")
        v_result = run_verification_pipeline(
            api_key=api_key,
            candidate=candidate,
            task_id=task_id,
            existing_ids=existing_ids,
            expected_topic=cell["topic_name"],
            expected_subtopic=cell["subtopic_name"],
            expected_level=level,
            existing_statements=existing_statements if existing_statements else None,
        )

        # Store verification result
        verification_report[task_id] = v_result

        if v_result["passed"]:
            # --- ACCEPTED ---
            full_task = {
                "task_id": task_id,
                "grade": grade,
                "topic_id": topic_id,
                "topic_name": cell["topic_name"],
                "subtopic_id": subtopic_id,
                "subtopic_name": cell["subtopic_name"],
                "level": level,
                "position": position,
                "base_cell_key": cell["base_cell_key"],
                "level_cell_key": level_cell_key,
                "statement": candidate["statement"],
                "answer": candidate["answer"],
                "solution": candidate["solution"],
                "usage": candidate.get("usage", {}),
                "generated_at": candidate.get("generated_at", _timestamp()),
                "model": MODEL_NAME,
                "verification": v_result.get("detail", "passed"),
            }
            return {
                "accepted": True, "task": full_task,
                "attempts": attempts, "tech_errors": tech_errors,
                "rejections": rejections, "reason": "ACCEPT",
            }
        else:
            # Check gate 13 content_arbiter verdict
            gate_details = v_result.get("gate_details", {})
            content_arbiter = gate_details.get("content_arbiter", {})
            verdict = content_arbiter.get("verdict", "REJECT")

            if verdict == "RETRY":
                tech_errors += 1
                print(f"    [RETRY] Position {position}, attempt {attempt}: {v_result.get('detail', '')[:120]}")
                if tech_errors >= CONSECUTIVE_TECH_ERROR_LIMIT:
                    print(f"    [HALT] {CONSECUTIVE_TECH_ERROR_LIMIT} consecutive tech errors. Halting.")
                    return {
                        "accepted": False, "task": None,
                        "attempts": attempts, "tech_errors": tech_errors,
                        "rejections": rejections,
                        "reason": f"CONSECUTIVE_TECH_ERROR_LIMIT ({CONSECUTIVE_TECH_ERROR_LIMIT})",
                    }
                time.sleep(RATE_LIMIT_DELAY)
                continue
            else:
                rejections += 1
                detail_short = v_result.get("detail", "")[:120]
                print(f"    [REJECT] Position {position}, attempt {attempt}: {detail_short}")
                if rejections >= CIRCUIT_BREAKER_LIMIT:
                    print(f"    [CB] {CIRCUIT_BREAKER_LIMIT} consecutive rejections. Moving on.")
                    return {
                        "accepted": False, "task": None,
                        "attempts": attempts, "tech_errors": tech_errors,
                        "rejections": rejections,
                        "reason": f"CIRCUIT_BREAKER ({CIRCUIT_BREAKER_LIMIT} rejections)",
                    }
                time.sleep(RATE_LIMIT_DELAY)

    # Exhausted attempts
    return {
        "accepted": False, "task": None,
        "attempts": attempts, "tech_errors": tech_errors,
        "rejections": rejections,
        "reason": f"EXHAUSTED ({MAX_ATTEMPTS_PER_POSITION} attempts)",
    }


# ============================================================================
# Process a single level cell: generate all 5 positions
# ============================================================================

def process_level_cell(
    api_key: str,
    cell: dict,
    checkpoint_state: dict,
    verification_report: dict,
) -> dict:
    """
    Process one level cell: for position in 1..5, generate until accepted.
    Saves atomic checkpoint after each accepted task.
    Returns the cell_result dict.
    """
    grade = cell["grade"]
    topic_id = cell["topic_id"]
    subtopic_id = cell["subtopic_id"]
    level = cell["level"]
    level_cell_key = cell["level_cell_key"]

    # Load existing tasks for this cell from checkpoint
    all_tasks = checkpoint_state.get("tasks", [])
    cell_tasks = [t for t in all_tasks if t.get("level_cell_key") == level_cell_key]
    cell_task_ids = {t["task_id"] for t in cell_tasks}
    cell_statements = [t["statement"] for t in cell_tasks]
    completed_positions = {t["position"] for t in cell_tasks}

    # Global existing IDs (for uniqueness gate)
    all_existing_ids = {t["task_id"] for t in all_tasks}

    results = []
    total_attempts = 0
    total_tech_errors = 0
    total_rejections = 0

    for position in range(1, TASKS_PER_LEVEL_CELL + 1):
        if position in completed_positions:
            print(f"  [SKIP] Position {position} already completed")
            existing = [t for t in cell_tasks if t["position"] == position]
            if existing:
                results.append({
                    "position": position,
                    "status": "COMPLETE",
                    "task_id": existing[0]["task_id"],
                    "attempts": 0,
                    "tech_errors": 0,
                    "rejections": 0,
                })
            continue

        print(f"\n  [POS {position}/{TASKS_PER_LEVEL_CELL}] Generating...")
        pos_result = generate_candidates_until_accepted(
            api_key=api_key,
            cell=cell,
            position=position,
            existing_cell_tasks=cell_tasks,
            existing_ids=all_existing_ids,
            existing_statements=cell_statements,
            verification_report=verification_report,
        )

        total_attempts += pos_result["attempts"]
        total_tech_errors += pos_result["tech_errors"]
        total_rejections += pos_result["rejections"]

        if pos_result["accepted"]:
            task = pos_result["task"]
            all_tasks.append(task)
            cell_tasks.append(task)
            cell_task_ids.add(task["task_id"])
            cell_statements.append(task["statement"])
            all_existing_ids.add(task["task_id"])

            results.append({
                "position": position,
                "status": "COMPLETE",
                "task_id": task["task_id"],
                "attempts": pos_result["attempts"],
                "tech_errors": pos_result["tech_errors"],
                "rejections": pos_result["rejections"],
            })

            # Atomic checkpoint after each accepted task
            checkpoint_state["tasks"] = all_tasks
            checkpoint_state["completed_cells"] = list(set(
                list(checkpoint_state.get("completed_cells", [])) + [level_cell_key]
            ))
            checkpoint_state["last_updated"] = _timestamp()
            checkpoint_state["verification_report"] = verification_report
            _atomic_save(checkpoint_state, OUTPUT_CHECKPOINT)

            print(f"    [OK] {task['task_id']} accepted after {pos_result['attempts']} attempts")
        else:
            results.append({
                "position": position,
                "status": "FAILED",
                "task_id": None,
                "attempts": pos_result["attempts"],
                "tech_errors": pos_result["tech_errors"],
                "rejections": pos_result["rejections"],
                "reason": pos_result.get("reason", "unknown"),
            })
            print(f"    [FAIL] Position {position} failed: {pos_result.get('reason', 'unknown')}")

        time.sleep(RATE_LIMIT_DELAY)

    accepted = sum(1 for r in results if r["status"] == "COMPLETE")
    status = "COMPLETE" if accepted == TASKS_PER_LEVEL_CELL else "PARTIAL"

    return {
        "level_cell_key": level_cell_key,
        "grade": grade,
        "topic_id": topic_id,
        "subtopic_id": subtopic_id,
        "level": level,
        "status": status,
        "accepted": accepted,
        "total_positions": TASKS_PER_LEVEL_CELL,
        "results": results,
        "total_attempts": total_attempts,
        "total_tech_errors": total_tech_errors,
        "total_rejections": total_rejections,
    }


# ============================================================================
# Checkpoint management (position-based)
# ============================================================================

def load_checkpoint() -> dict:
    """Load generation state from checkpoint, or return empty state."""
    if not os.path.exists(OUTPUT_CHECKPOINT):
        return {
            "completed_cells": [],
            "tasks": [],
            "cell_results": [],
            "started_at": _timestamp(),
            "last_updated": _timestamp(),
            "verification_report": {},
        }
    with open(OUTPUT_CHECKPOINT, "r", encoding="utf-8") as f:
        return json.load(f)


# ============================================================================
# Output builders
# ============================================================================

def build_grouped_output(all_tasks: List[dict], group_key: str) -> dict:
    """Group tasks by a key (e.g., level_cell_key, grade, level, topic_id)."""
    grouped = {}
    for t in all_tasks:
        key = t.get(group_key, "unknown")
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(t)
    return grouped


def build_statistics(all_tasks: List[dict], cell_results: List[dict]) -> dict:
    """Build generation statistics."""
    level_counts = {"L1": 0, "L2": 0, "L3": 0}
    grade_counts = {}
    topic_counts = {}

    for t in all_tasks:
        lvl = t.get("level", "?")
        level_counts[lvl] = level_counts.get(lvl, 0) + 1
        g = str(t.get("grade", "?"))
        grade_counts[g] = grade_counts.get(g, 0) + 1
        tid = t.get("topic_id", "?")
        topic_counts[tid] = topic_counts.get(tid, 0) + 1

    total_api_calls = sum(r.get("total_attempts", 0) for r in cell_results)
    total_tech_errors = sum(r.get("total_tech_errors", 0) for r in cell_results)
    total_rejections = sum(r.get("total_rejections", 0) for r in cell_results)

    cells_complete = sum(1 for r in cell_results if r["status"] == "COMPLETE")
    cells_partial = sum(1 for r in cell_results if r["status"] == "PARTIAL")

    return {
        "timestamp": _timestamp(),
        "model": MODEL_NAME,
        "total_tasks": len(all_tasks),
        "level_breakdown": level_counts,
        "grade_breakdown": dict(sorted(grade_counts.items())),
        "topic_breakdown": dict(sorted(topic_counts.items())),
        "cells_complete": cells_complete,
        "cells_partial": cells_partial,
        "total_cells": len(cell_results),
        "total_api_calls": total_api_calls,
        "total_tech_errors": total_tech_errors,
        "total_rejections": total_rejections,
    }


def build_audit(
    all_tasks: List[dict],
    cell_results: List[dict],
    total_cells: int,
    started_at: str,
    verification_report: dict,
) -> dict:
    """Build generation audit with metrics and invariants."""
    stats = build_statistics(all_tasks, cell_results)

    # Verification pass rate
    total_verified = len(verification_report)
    passed_verification = sum(1 for v in verification_report.values() if v.get("passed"))

    completed = sum(1 for r in cell_results if r["status"] == "COMPLETE")
    partial = sum(1 for r in cell_results if r["status"] == "PARTIAL")
    failed = sum(1 for r in cell_results if r["status"] not in ("COMPLETE", "PARTIAL"))

    return {
        "pipeline_step": "generation_audit",
        "timestamp": _timestamp(),
        "started_at": started_at,
        "model": MODEL_NAME,
        "tasks_per_cell": TASKS_PER_LEVEL_CELL,
        "total_cells": total_cells,
        "completed_cells": completed,
        "partial_cells": partial,
        "failed_cells": failed,
        "total_tasks_generated": len(all_tasks),
        "level_breakdown": stats["level_breakdown"],
        "grade_breakdown": stats["grade_breakdown"],
        "total_api_calls": stats["total_api_calls"],
        "total_tech_errors": stats["total_tech_errors"],
        "total_rejections": stats["total_rejections"],
        "verification_results": {
            "total_verified": total_verified,
            "passed": passed_verification,
            "failed": total_verified - passed_verification,
        },
        "invariants": {
            "smoke_test_passed": True,
            "grid_loaded": True,
            "all_cells_processed": completed == total_cells,
            "verification_pipeline_used": True,
            "position_based_ids": True,
            "atomic_checkpoints": True,
        },
        "status": "GENERATION_OK" if completed == total_cells else (
            "GENERATION_PARTIAL" if partial > 0 else "GENERATION_FAIL"
        ),
    }


# ============================================================================
# Generate FINAL_REPORT.md
# ============================================================================

def generate_final_report(
    all_tasks: List[dict],
    cell_results: List[dict],
    audit: dict,
    started_at: str,
    total_cells: int,
) -> str:
    """Generate a comprehensive final report in Markdown."""
    lines = []
    lines.append("# L1-L3 Generation Pipeline — Final Report")
    lines.append("")
    lines.append(f"**Generated:** {_timestamp()}")
    lines.append(f"**Started:** {started_at}")
    lines.append(f"**Model:** {MODEL_NAME}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Total level cells | {total_cells} |")
    lines.append(f"| Completed cells | {audit['completed_cells']} |")
    lines.append(f"| Partial cells | {audit['partial_cells']} |")
    lines.append(f"| Failed cells | {audit['failed_cells']} |")
    lines.append(f"| Total tasks | {len(all_tasks)} |")
    lines.append(f"| Total API calls | {audit['total_api_calls']} |")
    lines.append(f"| Tech errors | {audit['total_tech_errors']} |")
    lines.append(f"| Content rejections | {audit['total_rejections']} |")
    lines.append(f"| Status | {audit['status']} |")
    lines.append("")
    lines.append("## Level Breakdown")
    lines.append("")
    lines.append("| Level | Count |")
    lines.append("|-------|-------|")
    for level in ["L1", "L2", "L3"]:
        lines.append(f"| {level} | {audit['level_breakdown'].get(level, 0)} |")
    lines.append("")
    lines.append("## Grade Breakdown")
    lines.append("")
    lines.append("| Grade | Count |")
    lines.append("|-------|-------|")
    for g, cnt in audit["grade_breakdown"].items():
        lines.append(f"| {g} | {cnt} |")
    lines.append("")
    lines.append("## Verification Results")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Tasks verified | {audit['verification_results']['total_verified']} |")
    lines.append(f"| Passed | {audit['verification_results']['passed']} |")
    lines.append(f"| Failed | {audit['verification_results']['failed']} |")
    lines.append("")
    lines.append("## Output Files")
    lines.append("")
    lines.append(f"- `l1_l3_generated_raw.json` — {len(all_tasks)} tasks")
    lines.append(f"- `l1_l3_generated_by_cell.json` — grouped by level_cell")
    lines.append(f"- `l1_l3_generated_by_grade.json` — grouped by grade")
    lines.append(f"- `l1_l3_generated_by_level.json` — grouped by level")
    lines.append(f"- `l1_l3_generated_by_topic.json` — grouped by topic")
    lines.append(f"- `l1_l3_generated_statistics.json` — statistics")
    lines.append(f"- `l1_l3_verification_report.json` — per-task verification")
    lines.append(f"- `l1_l3_generation_checkpoint.json` — state for resume")
    lines.append(f"- `l1_l3_generated_audit.json` — audit metadata")
    lines.append(f"- `FINAL_REPORT.md` — this report")
    lines.append("")
    return "\n".join(lines)


# ============================================================================
# Main pipeline
# ============================================================================

def main():
    print("=" * 70)
    print("L1-L3 Generation Pipeline — Position-Based with 13-Step AND-Gate Verification")
    print(f"Started: {_timestamp()}")
    print("=" * 70)

    # ---- Step 0: Verify smoke test ----
    print("\n[Step 0] Verifying smoke test...")
    _check_smoke_status()

    # ---- Step 1: Load API key ----
    api_key = _load_api_key()
    key_masked = api_key[:8] + "..." + api_key[-4:] if api_key else "(none)"
    if not api_key:
        print("ERROR: No API key found.")
        sys.exit(1)
    print(f"  [OK] API key loaded: {key_masked}")

    # ---- Step 2: Load grid ----
    print("\n[Step 1] Loading target grid...")
    grid = _load_json(GRID_PATH, "Target grid")
    print(f"  [OK] Grid loaded ({len(grid.get('grades', {}))} grades)")

    # ---- Step 3: Build level cells ----
    print("\n[Step 2] Building level cell inventory...")
    all_cells = build_level_cells(grid)
    total_cells = len(all_cells)
    print(f"  [OK] {total_cells} level cells to process")

    expected_cells = 384
    if total_cells != expected_cells:
        print(f"  [WARN] Expected {expected_cells} cells, found {total_cells}")
    else:
        print(f"  [OK] Cell count matches expected ({expected_cells})")

    # ---- Step 4: Pilot mode detection ----
    pilot_mode = False
    cells_to_process = all_cells

    # Check if we should run pilot
    checkpoint_state = load_checkpoint()
    if not checkpoint_state.get("completed_cells"):
        # No checkpoint — check for PILOT_MODE env or ask via progress file
        pilot_mode = os.environ.get("PILOT_MODE", "1") == "1"
        if pilot_mode:
            print("\n[PILOT] Running pilot: 3 level cells (L1, L2, L3)")
            cells_to_process = []
            for pc in PILOT_CELLS:
                matched = [
                    c for c in all_cells
                    if c["grade"] == pc["grade"]
                    and c["topic_id"] == pc["topic_id"]
                    and c["subtopic_id"] == pc["subtopic_id"]
                    and c["level"] == pc["level"]
                ]
                if matched:
                    cells_to_process.append(matched[0])
                else:
                    print(f"  [WARN] Pilot cell not found in grid: {pc}")
            print(f"  [OK] Pilot cells: {len(cells_to_process)}")
        else:
            print("\n[FULL] Running full pipeline (PILOT_MODE=0)")
    else:
        completed_keys = set(checkpoint_state.get("completed_cells", []))
        if len(completed_keys) < len(PILOT_CELLS):
            pilot_mode = True
            print("\n[RESUME] Resuming pilot...")
            cells_to_process = []
            for pc in PILOT_CELLS:
                lc_key = _make_level_cell_key(pc["grade"], pc["topic_id"], pc["subtopic_id"], pc["level"])
                matched = [c for c in all_cells if c["level_cell_key"] == lc_key]
                if matched:
                    cells_to_process.append(matched[0])
        else:
            # Pilot completed — check if we should proceed to full
            pilot_result = all(
                lc_key in completed_keys
                for pc in PILOT_CELLS
                for lc_key in [_make_level_cell_key(pc["grade"], pc["topic_id"], pc["subtopic_id"], pc["level"])]
            )
            if pilot_result:
                print("\n[PILOT] Pilot completed. Proceeding to full pipeline...")
                cells_to_process = all_cells
            else:
                print("\n[RESUME] Resuming full pipeline...")
                cells_to_process = all_cells

    # ---- Step 5: Load checkpoint state ----
    print("\n[Step 3] Loading checkpoint state...")
    if not checkpoint_state.get("tasks"):
        print("  [INFO] Starting fresh generation")
        checkpoint_state["started_at"] = _timestamp()
        checkpoint_state["total_cells"] = total_cells
        checkpoint_state["verification_report"] = {}

    completed_keys = set(checkpoint_state.get("completed_cells", []))
    all_tasks = list(checkpoint_state.get("tasks", []))
    cell_results = list(checkpoint_state.get("cell_results", []))
    verification_report = dict(checkpoint_state.get("verification_report", {}))

    print(f"  [INFO] Already completed: {len(completed_keys)} cells, {len(all_tasks)} tasks")

    # ---- Step 6: Generate tasks per level cell ----
    print("\n[Step 4] Generating tasks...")
    print(f"{'':-^70}")

    circuit_breaker_count = 0
    cells_processed = len(completed_keys)

    for idx, cell in enumerate(cells_to_process):
        level_cell_key = cell["level_cell_key"]

        if level_cell_key in completed_keys:
            continue

        cells_processed += 1

        # Print cell header
        grade = cell["grade"]
        topic_name = cell["topic_name"]
        subtopic_name = cell["subtopic_name"]
        level = cell["level"]
        print(f"\nCell {cells_processed}/{len(cells_to_process)}: "
              f"G{grade} | {topic_name} | {subtopic_name} | {level}")
        print(f"  Key: {level_cell_key}")

        # Process the cell
        cell_result = process_level_cell(
            api_key=api_key,
            cell=cell,
            checkpoint_state=checkpoint_state,
            verification_report=verification_report,
        )

        cell_results.append(cell_result)

        if cell_result["status"] == "COMPLETE":
            completed_keys.add(level_cell_key)
            circuit_breaker_count = 0
            print(f"  [DONE] {cell_result['accepted']}/{TASKS_PER_LEVEL_CELL} tasks accepted")
        else:
            circuit_breaker_count += 1
            print(f"  [PARTIAL] {cell_result['accepted']}/{TASKS_PER_LEVEL_CELL} tasks accepted")
            print(f"  [REPORT] Attempts: {cell_result['total_attempts']}, "
                  f"Tech: {cell_result['total_tech_errors']}, "
                  f"Reject: {cell_result['total_rejections']}")

        # Write progress
        progress_line = (
            f"[{_timestamp()}] Cell {cells_processed}/{len(cells_to_process)}: "
            f"{level_cell_key} | {cell_result['status']} | "
            f"{cell_result['accepted']}/{TASKS_PER_LEVEL_CELL} accepted | "
            f"{cell_result['total_attempts']} attempts"
        )
        _write_progress(OUTPUT_PROGRESS, progress_line)

        # Save partial outputs periodically
        if cells_processed % 10 == 0 or cells_processed == len(cells_to_process):
            all_tasks = checkpoint_state.get("tasks", [])
            _atomic_save(all_tasks, OUTPUT_RAW)
            _atomic_save(build_grouped_output(all_tasks, "level_cell_key"), OUTPUT_BY_CELL)
            print(f"  [OUT] Partial output saved ({len(all_tasks)} tasks)")

    # ---- Step 7: Pilot -> Full pipeline transition ----
    if pilot_mode:
        all_tasks = checkpoint_state.get("tasks", [])
        pilot_passed = all(
            lc_key in completed_keys
            for c in cells_to_process
            for lc_key in [c["level_cell_key"]]
        )
        if pilot_passed and len(all_tasks) >= TASKS_PER_LEVEL_CELL * len(cells_to_process):
            print(f"\n{'':=^70}")
            print("PILOT PASSED — all pilot cells completed successfully!")
            print(f"Tasks generated: {len(all_tasks)}")
            print("Auto-proceeding to full pipeline (384 cells)...")

            # Save pilot outputs
            _atomic_save(all_tasks, OUTPUT_RAW)
            _atomic_save(cell_results, OUTPUT_BY_CELL)
            _atomic_save(verification_report, OUTPUT_VERIFICATION)

            # Re-run main for full pipeline (skip pilot)
            os.environ["PILOT_MODE"] = "0"
            # Save checkpoint with completed_cells cleared to force full processing
            checkpoint_state["completed_cells"] = []
            checkpoint_state["tasks"] = []
            checkpoint_state["cell_results"] = []
            checkpoint_state["started_at"] = _timestamp()
            _atomic_save(checkpoint_state, OUTPUT_CHECKPOINT)

            print("\n" + "=" * 70)
            print("FULL PIPELINE")
            print("=" * 70)
            # Recursive call for full pipeline — uses fresh state
            return main()

    # ---- Step 8: Final save ----
    all_tasks = checkpoint_state.get("tasks", [])
    print(f"\n{'':=^70}")
    print(f"Generation complete. Saving outputs...")

    # Save all output files
    _atomic_save(all_tasks, OUTPUT_RAW)
    _atomic_save(cell_results, OUTPUT_BY_CELL)
    _atomic_save(build_grouped_output(all_tasks, "grade"), OUTPUT_BY_GRADE)
    _atomic_save(build_grouped_output(all_tasks, "level"), OUTPUT_BY_LEVEL)
    _atomic_save(build_grouped_output(all_tasks, "topic_id"), OUTPUT_BY_TOPIC)
    _atomic_save(verification_report, OUTPUT_VERIFICATION)

    # Final checkpoint
    checkpoint_state["completed_cells"] = list(completed_keys)
    checkpoint_state["tasks"] = all_tasks
    checkpoint_state["cell_results"] = cell_results
    checkpoint_state["verification_report"] = verification_report
    checkpoint_state["last_updated"] = _timestamp()
    _atomic_save(checkpoint_state, OUTPUT_CHECKPOINT)

    print(f"  [OUT] {OUTPUT_RAW} ({len(all_tasks)} tasks)")
    print(f"  [OUT] {OUTPUT_BY_CELL}")
    print(f"  [OUT] {OUTPUT_BY_GRADE}")
    print(f"  [OUT] {OUTPUT_BY_LEVEL}")
    print(f"  [OUT] {OUTPUT_BY_TOPIC}")
    print(f"  [OUT] {OUTPUT_VERIFICATION}")
    print(f"  [OUT] {OUTPUT_CHECKPOINT}")

    # ---- Step 9: Build and save audit ----
    print("\n[Step 5] Building generation audit...")
    audit = build_audit(
        all_tasks, cell_results, total_cells,
        checkpoint_state.get("started_at", _timestamp()),
        verification_report,
    )
    _atomic_save(audit, OUTPUT_AUDIT)

    # Statistics
    stats = build_statistics(all_tasks, cell_results)
    _atomic_save(stats, OUTPUT_STATISTICS)

    print(f"  [OUT] {OUTPUT_AUDIT}")
    print(f"  [OUT] {OUTPUT_STATISTICS}")

    # ---- Step 10: Final report ----
    print("\n[Step 6] Generating final report...")
    report = generate_final_report(
        all_tasks, cell_results, audit,
        checkpoint_state.get("started_at", _timestamp()),
        total_cells,
    )
    with open(OUTPUT_FINAL_REPORT, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"  [OUT] {OUTPUT_FINAL_REPORT}")

    # ---- Final summary ----
    print(f"\n{'':=^70}")
    print("PIPELINE SUMMARY")
    print(f"{'':=^70}")
    print(f"  Total cells:     {total_cells}")
    print(f"  Completed:       {audit['completed_cells']}")
    print(f"  Partial:         {audit['partial_cells']}")
    print(f"  Failed:          {audit['failed_cells']}")
    print(f"  Tasks generated: {len(all_tasks)}")
    print(f"  L1: {audit['level_breakdown'].get('L1', 0):>5}")
    print(f"  L2: {audit['level_breakdown'].get('L2', 0):>5}")
    print(f"  L3: {audit['level_breakdown'].get('L3', 0):>5}")
    print(f"  API calls:       {audit['total_api_calls']}")
    print(f"  Tech errors:     {audit['total_tech_errors']}")
    print(f"  Content rej:     {audit['total_rejections']}")
    print(f"  Verified:        {audit['verification_results']['total_verified']}")
    print(f"  Passed verify:   {audit['verification_results']['passed']}")
    print(f"  Status:          {audit['status']}")
    print(f"{'':=^70}")

    return 0 if audit["status"] in ("GENERATION_OK", "GENERATION_PARTIAL") else 1


if __name__ == "__main__":
    sys.exit(main())
