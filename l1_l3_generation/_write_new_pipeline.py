#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Fix script: overwrite _run_generation_pipeline.py with position-based version.
Uses the write_to_file workaround: write script, fix syntax, execute.
"""
import os
import json
import sys

TARGET = os.path.join(os.path.dirname(__file__), "_run_generation_pipeline.py")

content = r'''#!/usr/bin/env python
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
    - l1_l3_generated_raw.json         — all accepted tasks (flat list)
    - l1_l3_generated_audit.json       — generation metrics and status
    - l1_l3_generated_by_cell.json     — tasks grouped by level_cell
    - l1_l3_generated_statistics.json  — statistics
    - l1_l3_generated_by_grade.json    — tasks grouped by grade
    - l1_l3_generated_by_level.json    — tasks grouped by level
    - l1_l3_generated_by_topic.json    — tasks grouped by topic
    - l1_l3_verification_report.json   — per-task verification results
    - l1_l3_generation_checkpoint.json — resumable state
    - l1_l3_generation.progress        — progress tracker
    - FINAL_REPORT.md                  — final report
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
RATE_LIMIT_DELAY = 1.5  # seconds between API calls
CONSECUTIVE_TECH_ERROR_LIMIT = 10

CIRCUIT_BREAKER_LIMIT = 5  # consecutive non-retryable failures before halt
PILOT_CELLS =