#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Fill L3 cell holes using two-stage pipeline:
  Stage 1 (deepseek-reasoner): Generate mathematical ideas/thoughts about what
    problems to create. No JSON required — just deep reasoning. We capture
    the reasoning_content (chain-of-thought).
  Stage 2 (deepseek-chat): Take the reasoning from Stage 1 as context and
    format it into clean JSON task objects with statement/answer/solution.

Why two-stage?
  - deepseek-reasoner almost never puts structured JSON in the `content` field.
    It puts everything in `reasoning_content` as chain-of-thought text, and
    the `content` field is often empty.
  - deepseek-chat (the non-reasoning model) is excellent at formatting
    structured output (JSON) when given clear context.
  - So: reasoner "thinks" -> chat "writes".

Strategy:
  - Small batches (TASKS_PER_CALL=2) for higher reliability.
  - Stage 1: 2 reasoner attempts (fast failure).
  - Stage 2: 3 chat attempts with increasing temperature (0.3, 0.5, 0.7).
  - If Stage 1 fails both times, Stage 2 runs from cell data alone.
  - Parallel processing via ThreadPoolExecutor (--workers N).
  - Checkpoint every cell for resume capability.

Usage:
  python _fill_l3_holes.py [--max-cells N] [--dry-run] [--resume]
"""

import json
import os
import sys
import re
import time
import logging
import argparse
import threading
from collections import defaultdict
from datetime import datetime
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(__file__))
from ai.deepseek_client import DeepSeekClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ─── config ────────────────────────────────────────────────────────────────
DB_PATH = "adaptive_data/adaptive_full_9120_fixed.json"
CHECKPOINT_PATH = "fill_l3_holes_checkpoint.json"
OUTPUT_FILE = "adaptive_data/adaptive_full_9120_fixed.json"
NEW_TASKS_FILE = "adaptive_data/_new_l3_tasks.json"
TARGET = 5
MAX_REASONER_ATTEMPTS = 2        # Stage 1: reasoner retries (fast fail)
MAX_CHAT_ATTEMPTS = 3            # Stage 2: chat formatter retries
CELL_TIMEOUT = 600               # 10 min per cell
SLEEP_BETWEEN_CELLS = 3          # small delay to avoid rate limiting
TASKS_PER_CALL = 2               # request 2 tasks per batch (manageable for chat formatter)


def _fix_invalid_escapes(text: str) -> str:
    """Fix common invalid escape sequences iteratively until stable."""
    replacements = {
        r'\\leq': r'\leq', r'\\ge': r'\ge', r'\\geq': r'\geq',
        r'\\le': r'\le', r'\\in': r'\in', r'\\notin': r'\notin',
        r'\\cup': r'\cup', r'\\cap': r'\cap',
        r'\\subset': r'\subset', r'\\supset': r'\supset',
        r'\\mathbb': r'\mathbb', r'\\rightarrow': r'\rightarrow',
        r'\\Rightarrow': r'\Rightarrow', r'\\leftarrow': r'\leftarrow',
        r'\\Leftarrow': r'\Leftarrow', r'\\leftrightarrow': r'\leftrightarrow',
        r'\\implies': r'\implies', r'\\iff': r'\iff',
        r'\\cdot': r'\cdot', r'\\times': r'\times', r'\\div': r'\div',
        r'\\pm': r'\pm', r'\\sqrt': r'\sqrt', r'\\frac': r'\frac',
        r'\\binom': r'\binom', r'\\sum': r'\sum', r'\\prod': r'\prod',
        r'\\int': r'\int', r'\\ldots': r'\ldots', r'\\cdots': r'\cdots',
        r'\\vdots': r'\vdots', r'\\ddots': r'\ddots',
        r'\\quad': r'\quad', r'\\qquad': r'\qquad',
        r'\\text': r'\text', r'\\boxed': r'\boxed',
        r'\\gcd': r'\gcd', r'\\lcm': r'\lcm',
        r'\\pmod': r'\pmod', r'\\bmod': r'\bmod',
        r'\\forall': r'\forall', r'\\exists': r'\exists',
        r'\\neg': r'\neg', r'\\land': r'\land', r'\\lor': r'\lor',
        r'\\Leftrightarrow': r'\Leftrightarrow',
    }
    prev = None
    current = text
    for _ in range(10):
        if current == prev:
            break
        prev = current
        for old, new in replacements.items():
            current = current.replace(old, new)
    return current


def _strip_control_chars(text: str) -> str:
    """Remove ASCII control characters except newline and tab."""
    return ''.join(ch for ch in text if ch == '\n' or ch == '\t' or ord(ch) >= 32 or ch == '\r')


def _try_parse_single_object(obj_str: str) -> Optional[dict]:
    """Try to parse a single JSON object with escape fixing."""
    fixed = _fix_invalid_escapes(obj_str)
    fixed = _strip_control_chars(fixed)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass
    # Try with single quotes -> double quotes
    try:
        converted = []
        in_double = False
        in_single = False
        escape = False
        for ch in fixed:
            if escape:
                converted.append(ch)
                escape = False
                continue
            if ch == '\\':
                converted.append(ch)
                escape = True
                continue
            if ch == '"' and not in_single:
                in_double = not in_double
                converted.append(ch)
                continue
            if ch == "'" and not in_double:
                in_single = not in_single
                converted.append('"')
                continue
            converted.append(ch)
        return json.loads(''.join(converted))
    except (json.JSONDecodeError, ValueError):
        pass
    return None


def _extract_individual_objects(text: str) -> Optional[list]:
    """Extract individual JSON objects {{...}} from text with brace tracking."""
    objects = []
    i = 0
    brace_depth = 0
    obj_start = -1
    while i < len(text):
        ch = text[i]
        if ch == '\\' and i + 1 < len(text) and text[i+1] in '{}':
            i += 2
            continue
        if ch == '{':
            if brace_depth == 0:
                obj_start = i
            brace_depth += 1
        elif ch == '}':
            brace_depth -= 1
            if brace_depth == 0 and obj_start >= 0:
                obj_str = text[obj_start:i+1]
                obj = _try_parse_single_object(obj_str)
                if obj is not None:
                    objects.append(obj)
                obj_start = -1
        i += 1
    return objects if objects else None


def safe_parse_json(text: str) -> Optional[list]:
    """Extract JSON array from model response, ultra-robust."""
    if not text:
        return None
    text = text.strip()
    # Strip markdown code blocks
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(
            line for line in lines
            if not line.strip().startswith("```")
        ).strip()
    # Find outermost [ ... ] with bracket-depth tracking
    bracket_depth = 0
    json_start = -1
    json_end = -1
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == '\\' and i + 1 < len(text) and text[i+1] in '[]{}':
            i += 2
            continue
        if ch == '[':
            if bracket_depth == 0:
                json_start = i
            bracket_depth += 1
        elif ch == ']':
            bracket_depth -= 1
            if bracket_depth == 0 and json_start >= 0:
                json_end = i + 1
                break
        i += 1
    if json_start < 0 or json_end <= json_start:
        return None
    json_str = text[json_start:json_end]
    json_str = _fix_invalid_escapes(json_str)
    json_str = _strip_control_chars(json_str)
    # Fix potential double brackets
    if json_str.startswith("[["):
        try:
            inner = json.loads(json_str)
            if isinstance(inner, list):
                return inner
        except json.JSONDecodeError:
            pass
        if json_str.startswith("[[") and json_str.endswith("]]"):
            json_str = json_str[1:-1]
    # Try standard parse
    try:
        result = json.loads(json_str)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass
    # Handle single quotes -> double quotes
    fixed = []
    in_double = False
    in_single = False
    escape = False
    for ch in json_str:
        if escape:
            fixed.append(ch)
            escape = False
            continue
        if ch == '\\':
            fixed.append(ch)
            escape = True
            continue
        if ch == '"' and not in_single:
            in_double = not in_double
            fixed.append(ch)
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
            fixed.append('"')
            continue
        fixed.append(ch)
    json_fixed = "".join(fixed)
    try:
        result = json.loads(json_fixed)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass
    # Fix trailing commas
    json_fixed2 = re.sub(r',\s*([\]}])', r'\1', json_fixed)
    try:
        result = json.loads(json_fixed2)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass
    # Try ast.literal_eval
    import ast
    try:
        result = ast.literal_eval(json_fixed)
        if isinstance(result, list):
            return result
    except (ValueError, SyntaxError, MemoryError):
        pass
    # FINAL FALLBACK: extract individual objects
    individual = _extract_individual_objects(text)
    if individual:
        logger.debug(f"Recovered {len(individual)} task(s) via individual object extraction")
        return individual
    return None


def load_db():
    with open(DB_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_checkpoint(data: dict):
    with open(CHECKPOINT_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(
        f"Checkpoint saved: {len(data.get('completed_cells', []))} cells, "
        f"{len(data.get('generated_tasks', []))} tasks"
    )


def load_checkpoint() -> Optional[dict]:
    if os.path.exists(CHECKPOINT_PATH):
        with open(CHECKPOINT_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


def get_l3_cells_with_holes(tasks):
    """Return list of L3 cells that need filling."""
    l3_tasks = [t for t in tasks if t.get('level') == 3]
    by_topic = defaultdict(list)
    by_section = {}
    for t in l3_tasks:
        grade = t.get('grade')
        topic = t.get('topic', '')
        section = t.get('section', '')
        by_topic[(grade, topic)].append(t)
        by_section[(grade, topic)] = section
    cells = []
    for (grade, topic), existing in by_topic.items():
        count = len(existing)
        if count < TARGET:
            needed = TARGET - count
            section = by_section.get((grade, topic), '')
            cells.append({
                'level': 3,
                'grade': grade,
                'topic': topic,
                'section': section,
                'existing_tasks': existing,
                'count': count,
                'needed': needed,
                'cell_key': f"L3|{grade}|{topic}"
            })
    cells.sort(key=lambda c: c['count'])
    return cells


# ═══════════════════════════════════════════════════════════════════════════
# PROMPTS
# ═══════════════════════════════════════════════════════════════════════════

def build_reasoner_idea_prompt(cell: dict, batch_size: int,
                               attempt: int = 0) -> str:
    """Prompt for Stage 1 (deepseek-reasoner).

    The reasoner should THINK about what problems to create, but NOT output
    JSON. We only need its reasoning_content for Stage 2 context.
    """
    grade = cell['grade']
    topic = cell['topic']
    section = cell['section']
    existing = cell['existing_tasks']

    prompt_parts = [
        f"Мне нужно составить {batch_size} олимпиадных задач(у) по математике "
        f"УРОВНЯ L3 (повышенная сложность) для следующих параметров:",
        f"- Класс: {grade}",
        f"- Раздел: {section}",
        f"- Тема: {topic}",
        "",
        "Пожалуйста, ПОДУМАЙ (в своем reasoning) о том, какие именно задачи "
        "можно составить. Рассмотри разные подходы, идеи, контексты.",
        "",
    ]

    if existing:
        prompt_parts.append(
            f"[!]️ В этой ячейке УЖЕ ЕСТЬ следующие {len(existing)} задач(и). "
            "Нужны ПРИНЦИПИАЛЬНО НОВЫЕ задачи, которые НЕ повторяют их:"
        )
        for i, t in enumerate(existing, 1):
            stmt = t.get('statement', '')[:200]
            prompt_parts.append(f"  {i}. {stmt}...")
        prompt_parts.append("")

    prompt_parts.append("Подумай о следующих аспектах:")
    prompt_parts.append("1. Какие математические идеи и методы можно использовать?")
    prompt_parts.append("2. Какие интересные числовые конструкции подходят?")
    prompt_parts.append("3. Как сделать задачу нестандартной и олимпиадной?")
    prompt_parts.append("4. Как связать с темой и классом?")
    prompt_parts.append("")

    if attempt > 0:
        prompt_parts.append(
            "[!]️ Попробуй СОВСЕМ ДРУГИЕ идеи, не те, что были в предыдущих попытках."
        )
        prompt_parts.append("")

    prompt_parts.append(
        "ВАЖНО: Не нужно выводить JSON или финальные формулировки задач. "
        "Просто подумай вслух о подходящих задачах, их условиях, решениях, "
        "ответах. Твои размышления будут использованы как контекст для "
        "составления финальных задач."
    )

    return "\n".join(prompt_parts)


def build_chat_formatter_prompt(cell: dict, batch_size: int,
                                reasoning_context: str = "",
                                attempt: int = 0) -> str:
    """Prompt for Stage 2 (deepseek-chat) — format ideas into JSON tasks.

    If reasoning_context is provided (from Stage 1 reasoner), use it as
    context with short truncation (4000 chars max). Otherwise, generate
    tasks from cell data alone.
    """
    grade = cell['grade']
    topic = cell['topic']
    section = cell['section']
    existing = cell['existing_tasks']

    prompt_parts = [
        f"Составь ровно {batch_size} олимпиадных задач(у) по математике "
        f"УРОВНЯ L3 (повышенная сложность) для:",
        f"- Класс: {grade}",
        f"- Раздел: {section}",
        f"- Тема: {topic}",
        "",
    ]

    if existing:
        prompt_parts.append(
            f"[!]️ В этой ячейке УЖЕ ЕСТЬ следующие {len(existing)} задач(и). "
            "ТЫ ДОЛЖЕН СГЕНЕРИРОВАТЬ НОВЫЕ, НЕ ПОВТОРЯЮЩИЕ ИХ:"
        )
        for i, t in enumerate(existing, 1):
            stmt = t.get('statement', '')[:200]
            prompt_parts.append(f"  {i}. {stmt}...")
        prompt_parts.append("")

    if reasoning_context:
        prompt_parts.append(
            "Контекст (размышления эксперта-математика):"
        )
        # Truncate reasoning to last 4000 chars — short enough to not
        # overwhelm the chat model with raw reasoning text
        truncated = reasoning_context[-4000:] if len(reasoning_context) > 4000 else reasoning_context
        prompt_parts.append(truncated)
        prompt_parts.append("")

    prompt_parts.append("ТРЕБОВАНИЯ К ЗАДАЧАМ:")
    prompt_parts.append("1. Уровень L3 — повышенная сложность, олимпиадные задачи.")
    prompt_parts.append("2. Задачи должны быть РАЗНЫМИ по типу и математической идее.")
    prompt_parts.append("3. У каждой задачи должно быть подробное решение.")
    prompt_parts.append("4. Ответ — числовой (число, дробь, выражение). Не да/нет.")
    prompt_parts.append("5. НЕ повторять существующие задачи из списка выше!")
    prompt_parts.append("6. Используй LaTeX (формат $$...$$).")
    prompt_parts.append("")

    prompt_parts.append("Формат ответа — JSON-массив объектов. Начало ответа с '[':")
    prompt_parts.append('''[
  {
    "statement": "Условие задачи с LaTeX",
    "answer": "Числовой ответ",
    "solution": "Подробное решение с LaTeX"
  }
]''')
    prompt_parts.append("")
    prompt_parts.append(
        f"Сгенерируй ровно {batch_size} задач(у). "
        "Верни ТОЛЬКО JSON-массив, начинающийся с '['. "
        "Никаких пояснений, никаких markdown-блоков, только JSON."
    )

    if attempt > 0:
        prompt_parts.append("")
        prompt_parts.append(
            "[!]️ Предыдущие попытки не дали результата. Попробуй ДРУГИЕ задачи "
            "с другими числами и контекстами."
        )

    return "\n".join(prompt_parts)


# ═══════════════════════════════════════════════════════════════════════════
# UTILITY FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

def get_fingerprint(statement: str) -> str:
    """Create a dedup fingerprint from first 100 chars of statement."""
    return statement.strip()[:100].lower().replace(' ', '')


def is_duplicate(statement: str, existing_fingerprints: set) -> bool:
    """Check if this statement is a duplicate by fingerprint."""
    fp = get_fingerprint(statement)
    return fp in existing_fingerprints


def _filter_dict_tasks(tasks: Optional[list]) -> Optional[list]:
    """Filter a list to only contain dict items (actual task objects)."""
    if not tasks:
        return None
    filtered = [t for t in tasks if isinstance(t, dict)]
    return filtered if filtered else None


def _enrich_and_dedup(tasks: list, cell: dict,
                      existing_fps: set) -> list:
    """Add cell metadata and deduplicate tasks."""
    validated = []
    for t in tasks:
        if not isinstance(t, dict):
            continue
        t['level'] = cell['level']
        t['grade'] = cell['grade']
        t['topic'] = cell['topic']
        t['section'] = cell['section']
        t['subject'] = 'math'

        if not t.get('statement') or not t.get('answer'):
            continue
        if not t.get('solution'):
            t['solution'] = t.get('answer', '')

        stmt = t.get('statement', '')
        if is_duplicate(stmt, existing_fps):
            continue

        existing_fps.add(get_fingerprint(stmt))
        validated.append(t)
    return validated


# ═══════════════════════════════════════════════════════════════════════════
# TWO-STAGE GENERATION
# ═══════════════════════════════════════════════════════════════════════════

def stage1_reasoner_ideas(client: DeepSeekClient, cell: dict,
                          batch_size: int,
                          attempt: int) -> Optional[str]:
    """Stage 1: Call deepseek-reasoner to generate mathematical ideas.

    Returns the reasoning_content (chain-of-thought text) for use as context
    in Stage 2. Returns None if all attempts fail.
    """
    prompt = build_reasoner_idea_prompt(cell, batch_size, attempt=attempt)
    system_prompt = (
        "Ты — профессиональный математик-олимпиадник. Твоя задача — "
        "придумать интересные олимпиадные задачи уровня L3 для указанной "
        "темы и класса. Размышляй вслух, анализируй возможные подходы, "
        "числовые конструкции, методы решений. Не нужно выводить JSON — "
        "просто думай."
    )

    try:
        raw_content, raw_reasoning = client.generate_with_reasoning(
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=8000,
            timeout=300,
            return_reasoning=True,
        )
    except Exception as e:
        logger.warning(f"  Stage 1 (reasoner) API failed: {e}")
        return None

    if raw_reasoning and len(raw_reasoning) > 200:
        logger.info(
            f"  Stage 1: Got {len(raw_reasoning)} chars of reasoning, "
            f"content={len(raw_content)} chars"
        )
        return raw_reasoning

    # If reasoning is empty or too short, try content as fallback
    if raw_content and len(raw_content) > 200:
        logger.info(
            f"  Stage 1: No reasoning, using content ({len(raw_content)} chars)"
        )
        return raw_content

    logger.warning(
        f"  Stage 1: Insufficient output "
        f"(reasoning={len(raw_reasoning)} chars, content={len(raw_content)} chars)"
    )
    return None


def stage2_chat_formatter(client: DeepSeekClient, cell: dict,
                          batch_size: int,
                          reasoning_context: str = "",
                          attempt: int = 0,
                          use_json_mode: bool = True) -> Optional[list]:
    """Stage 2: Call deepseek-chat to format ideas into JSON tasks.

    Takes reasoning_context from Stage 1 (or empty string if Stage 1 failed).
    Returns enriched+deduped task list, or None.

    When use_json_mode=True (default), passes response_format={"type":"json_object"}
    to the API, which forces the model to output ONLY valid JSON. This is the
    KEY fix for the model's inability to produce clean JSON reliably.
    """
    prompt = build_chat_formatter_prompt(
        cell, batch_size,
        reasoning_context=reasoning_context,
        attempt=attempt,
    )
    system_prompt = (
        "Ты — профессиональный составитель олимпиадных задач по математике. "
        "Твоя задача — создать задачи уровня L3 в формате JSON. "
        "Отвечай ТОЛЬКО JSON-массивом, без дополнительного текста. "
        "Каждый объект должен содержать поля: "
        '"statement", "answer", "solution".'
    )

    # Lower temperature for JSON mode — we want deterministic formatting
    # attempt 0: 0.1 (very deterministic, JSON mode)
    # attempt 1: 0.3 (slight variation)
    # attempt 2: 0.5 (more variation, fallback)
    if use_json_mode:
        temperature = 0.1 + attempt * 0.2  # 0.1, 0.3, 0.5
    else:
        temperature = 0.3 + attempt * 0.2  # 0.3, 0.5, 0.7

    try:
        kwargs = dict(
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=4000,
            temperature=temperature,
        )
        if use_json_mode:
            kwargs['response_format'] = {"type": "json_object"}
        raw = client.generate(**kwargs)
    except Exception as e:
        logger.warning(f"  Stage 2 (chat) API failed: {e}")
        return None

    if not raw:
        logger.warning(f"  Stage 2 attempt {attempt+1}: empty response")
        return None

    # Try to parse JSON from the response
    tasks = safe_parse_json(raw)
    if not tasks:
        logger.warning(
            f"  Stage 2 attempt {attempt+1}: JSON parse failed "
            f"({len(raw)} chars)"
        )
        return None

    dict_tasks = _filter_dict_tasks(tasks)
    if not dict_tasks:
        logger.warning(
            f"  Stage 2 attempt {attempt+1}: no dict tasks in parsed output"
        )
        return None

    logger.info(
        f"  Stage 2: Parsed {len(dict_tasks)} raw tasks from response"
    )
    return dict_tasks


def generate_batch(client: DeepSeekClient, cell: dict,
                   existing_fps: set, batch_size: int,
                   batch_idx: int = 0, total_batches: int = 1) -> Optional[list]:
    """Two-stage generation for one batch of tasks.

    Stage 1: reasoner thinks (2 attempts max — fast fail).
    Stage 2: chat formats (3 attempts with json_object mode + temperature ramp).
    FALLBACK: If Stage 2 fails with reasoning context, retry WITHOUT context
              (like _fill_cell_holes.py approach — pure chat generation).
    Returns enriched+deduped task list, or None.
    """
    cell_key = cell['cell_key']

    # ── Stage 1: Reasoner ideas ──────────────────────────────────────
    reasoning_context = None
    for attempt in range(MAX_REASONER_ATTEMPTS):
        logger.info(
            f"[{cell_key}] Batch {batch_idx}/{total_batches} \u2014 "
            f"Stage 1 (reasoner) {attempt+1}/{MAX_REASONER_ATTEMPTS}..."
        )
        reasoning_context = stage1_reasoner_ideas(
            client, cell, batch_size, attempt
        )
        if reasoning_context:
            logger.info(
                f"  Stage 1: Got {len(reasoning_context)} chars of ideas"
            )
            break
        logger.warning(f"  Stage 1 attempt {attempt+1}: no ideas generated")
        time.sleep(2)

    if not reasoning_context:
        logger.warning(
            f"[{cell_key}] Stage 1 failed after {MAX_REASONER_ATTEMPTS} "
            f"attempts. Stage 2 will run without reasoning context."
        )

    # ── Stage 2: Chat formatter WITH reasoning context ───────────────
    for attempt in range(MAX_CHAT_ATTEMPTS):
        logger.info(
            f"[{cell_key}] Batch {batch_idx}/{total_batches} \u2014 "
            f"Stage 2 (chat+json_mode) {attempt+1}/{MAX_CHAT_ATTEMPTS} "
            f"(temp={0.1 + attempt*0.2:.1f})..."
        )

        raw_tasks = stage2_chat_formatter(
            client, cell, batch_size,
            reasoning_context=reasoning_context or "",
            attempt=attempt,
            use_json_mode=True,
        )

        if not raw_tasks:
            time.sleep(2)
            continue

        # Enrich and deduplicate
        validated = _enrich_and_dedup(raw_tasks, cell, existing_fps)

        if validated:
            logger.info(
                f"  \u2713 Batch {batch_idx}: Got {len(validated)}/{batch_size} "
                f"valid tasks via chat formatter (with context)"
            )
            return validated[:batch_size]
        else:
            logger.warning(
                f"  Stage 2 attempt {attempt+1}: all tasks were "
                f"duplicates/invalid, retrying..."
            )
            time.sleep(2)
            continue

    # ── FALLBACK: Stage 2 WITHOUT reasoning context ──────────────────
    # If the reasoner context confused the chat model, try clean generation
    logger.warning(
        f"[{cell_key}] Stage 2 WITH reasoning context failed. "
        f"FALLBACK: trying WITHOUT context (pure chat generation)..."
    )
    for attempt in range(MAX_CHAT_ATTEMPTS):
        logger.info(
            f"[{cell_key}] Batch {batch_idx}/{total_batches} \u2014 "
            f"FALLBACK (chat, no context) {attempt+1}/{MAX_CHAT_ATTEMPTS} "
            f"(temp={0.1 + attempt*0.2:.1f})..."
        )

        raw_tasks = stage2_chat_formatter(
            client, cell, batch_size,
            reasoning_context="",
            attempt=attempt,
            use_json_mode=True,
        )

        if not raw_tasks:
            time.sleep(2)
            continue

        validated = _enrich_and_dedup(raw_tasks, cell, existing_fps)

        if validated:
            logger.info(
                f"  \u2713 FALLBACK: Got {len(validated)}/{batch_size} "
                f"valid tasks via pure chat generation"
            )
            return validated[:batch_size]
        else:
            logger.warning(
                f"  FALLBACK attempt {attempt+1}: all tasks were "
                f"duplicates/invalid, retrying..."
            )
            time.sleep(2)
            continue

    logger.error(
        f"[{cell_key}] Batch {batch_idx}: ALL generation strategies failed"
    )
    return None


# ═══════════════════════════════════════════════════════════════════════════
# CELL PROCESSING
# ═══════════════════════════════════════════════════════════════════════════

def generate_cell_tasks(client: DeepSeekClient, cell: dict) -> list:
    """Generate all needed tasks for a single L3 cell using two-stage pipeline."""
    needed = cell['needed']
    cell_key = cell['cell_key']
    all_validated = []

    # Build fingerprint set from existing cell tasks
    existing_fps = set()
    for t in cell['existing_tasks']:
        stmt = t.get('statement', '')
        if stmt:
            existing_fps.add(get_fingerprint(stmt))

    # Calculate how many batches we need
    batches = []
    remaining = needed
    while remaining > 0:
        batch_sz = min(remaining, TASKS_PER_CALL)
        batches.append(batch_sz)
        remaining -= batch_sz

    logger.info(
        f"[{cell_key}] Need {needed} tasks \u2192 {len(batches)} batch(es) "
        f"of sizes {batches}"
    )

    for batch_idx, batch_size in enumerate(batches):
        batch_tasks = generate_batch(
            client, cell, existing_fps, batch_size,
            batch_idx=batch_idx + 1,
            total_batches=len(batches),
        )

        if batch_tasks:
            all_validated.extend(batch_tasks)
            logger.info(
                f"[{cell_key}] Batch {batch_idx+1}/{len(batches)} complete: "
                f"+{len(batch_tasks)} tasks"
            )
        else:
            logger.error(
                f"[{cell_key}] Batch {batch_idx+1}/{len(batches)} FAILED"
            )

    if all_validated:
        logger.info(
            f"[{cell_key}] \u2713 Generated {len(all_validated)}/{needed} tasks total"
        )
    else:
        logger.error(f"[{cell_key}] \u2717 FAILED \u2014 zero tasks generated")

    return all_validated


def merge_into_db(db: list, new_tasks: list) -> list:
    """Merge new tasks into DB, avoiding duplicates by fingerprint."""
    existing_fps = set()
    for t in db:
        stmt = t.get('statement', '').strip()
        if stmt:
            existing_fps.add(get_fingerprint(stmt))

    added = 0
    skipped = 0
    for t in new_tasks:
        stmt = t.get('statement', '').strip()
        if not stmt:
            continue
        fp = get_fingerprint(stmt)
        if fp in existing_fps:
            skipped += 1
            continue
        existing_fps.add(fp)
        max_id = max(
            (int(x.get('id', 0)) for x in db if str(x.get('id', '')).isdigit()),
            default=0
        )
        t['id'] = max_id + 1 + added
        db.append(t)
        added += 1

    logger.info(f"Merged: +{added} new tasks, skipped {skipped} duplicates")
    return db


def main():
    parser = argparse.ArgumentParser(
        description="Fill L3 cell holes using two-stage (reasoner -> chat)"
    )
    parser.add_argument(
        '--max-cells', type=int, default=None,
        help='Max cells to process'
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Only list cells without generating'
    )
    parser.add_argument(
        '--resume', action='store_true',
        help='Resume from checkpoint'
    )
    parser.add_argument(
        '--workers', type=int, default=1,
        help='Number of parallel workers (threads). Default: 1 (sequential)'
    )
    args = parser.parse_args()

    # Load DB
    db = load_db()
    logger.info(f"Loaded {len(db)} total tasks")

    l3 = [t for t in db if t.get('level') == 3]
    logger.info(f"L3: {len(l3)} tasks")

    # Get cells with holes
    cells = get_l3_cells_with_holes(db)
    if not cells:
        logger.info("No L3 holes found! All cells are full or overfilled.")
        return

    total_needed = sum(c['needed'] for c in cells)
    logger.info(
        f"Found {len(cells)} L3 cells with holes, "
        f"need {total_needed} tasks total"
    )

    # Show distribution
    by_need = defaultdict(int)
    for c in cells:
        by_need[c['needed']] += 1
    logger.info(f"Need distribution: {dict(sorted(by_need.items()))}")

    by_grade = defaultdict(int)
    for c in cells:
        by_grade[c['grade']] += 1
    logger.info(f"By grade: {dict(sorted(by_grade.items()))}")

    if args.dry_run:
        logger.info("DRY RUN \u2014 showing all cells:")
        for c in cells:
            logger.info(
                f"  L3 | g{c['grade']} | {c['topic']} \u2014 "
                f"{c['count']}/{TARGET} (need {c['needed']})"
            )
        return

    # Load checkpoint if resuming
    checkpoint = None
    completed_keys = set()
    failed_keys = set()  # ⭐ Track cells that failed all retries
    all_generated_tasks = []

    if args.resume:
        checkpoint = load_checkpoint()
        if checkpoint:
            completed_keys = set(checkpoint.get('completed_cells', []))
            failed_keys = set(checkpoint.get('failed_cells', []))  # ⭐
            all_generated_tasks = checkpoint.get('generated_tasks', [])
            logger.info(
                f"Resumed: {len(completed_keys)} cells completed, "
                f"{len(failed_keys)} cells failed (skipped), "
                f"{len(all_generated_tasks)} tasks generated"
            )

    # Filter out already completed cells AND previously failed cells
    cells_to_process = [
        c for c in cells
        if c['cell_key'] not in completed_keys
        and c['cell_key'] not in failed_keys  # ⭐ skip stubborn cells
    ]
    if failed_keys:
        logger.info(
            f"Skipping {len(failed_keys)} previously failed cells: "
            f"{', '.join(sorted(failed_keys)[:5])}..."
        )
    logger.info(
        f"Cells to process: {len(cells_to_process)} "
        f"(skipping {len(cells) - len(cells_to_process)} completed)"
    )

    if args.max_cells:
        cells_to_process = cells_to_process[:args.max_cells]
        logger.info(f"Limiting to {args.max_cells} cells")

    if not cells_to_process:
        logger.info("All cells already processed!")
    else:
        total = len(cells_to_process)
        workers = args.workers
        logger.info(
            f"Processing {total} cells with {workers} worker(s)"
        )

        # Thread-safe checkpoint lock
        checkpoint_lock = threading.Lock()

        if workers == 1:
            # ── Sequential mode (same as before) ──
            client = DeepSeekClient()
            for idx, cell in enumerate(cells_to_process, 1):
                cell_key = cell['cell_key']
                logger.info(f"\n{'='*60}")
                logger.info(
                    f"[{idx}/{total}] Processing {cell_key} \u2014 "
                    f"{cell['count']}/{TARGET} (need {cell['needed']})"
                )
                logger.info(f"{'='*60}")

                new_tasks = generate_cell_tasks(client, cell)

                with checkpoint_lock:
                    if new_tasks:
                        all_generated_tasks.extend(new_tasks)
                        completed_keys.add(cell_key)
                        l3_so_far = len([
                            t for t in all_generated_tasks
                            if t.get('level') == 3
                        ])
                        logger.info(
                            f"\u2713 {cell_key} \u2014 +{len(new_tasks)} tasks "
                            f"({l3_so_far} L3 generated so far)"
                        )
                    else:
                        logger.error(
                            f"\u2717 {cell_key} \u2014 FAILED after all retries"
                        )
                        failed_keys.add(cell_key)

                    save_checkpoint({
                        'completed_cells': list(completed_keys),
                        'failed_cells': list(failed_keys),
                        'generated_tasks': all_generated_tasks,
                        'timestamp': datetime.now().isoformat(),
                    })

                if idx < total:
                    logger.info(
                        f"Waiting {SLEEP_BETWEEN_CELLS}s before next cell..."
                    )
                    time.sleep(SLEEP_BETWEEN_CELLS)
        else:
            # ── Parallel mode (ThreadPoolExecutor) ──
            completed_count = 0

            def _process_one_cell(cell: dict) -> tuple:
                """Process a single cell with its own client. Returns (cell_key, new_tasks)."""
                local_client = DeepSeekClient()
                cell_key = cell['cell_key']
                try:
                    new_tasks = generate_cell_tasks(local_client, cell)
                    return (cell_key, new_tasks if new_tasks else [])
                except Exception as e:
                    logger.error(
                        f"Exception in worker for {cell_key}: {e}"
                    )
                    return (cell_key, [])

            with ThreadPoolExecutor(max_workers=workers) as executor:
                future_map = {
                    executor.submit(_process_one_cell, cell): cell
                    for cell in cells_to_process
                }

                for future in as_completed(future_map):
                    cell = future_map[future]
                    cell_key = cell['cell_key']

                    try:
                        _, new_tasks = future.result(timeout=CELL_TIMEOUT)
                    except Exception as e:
                        logger.error(
                            f"Exception for {cell_key}: {e}"
                        )
                        new_tasks = []

                    with checkpoint_lock:
                        completed_count += 1
                        if new_tasks:
                            all_generated_tasks.extend(new_tasks)
                            completed_keys.add(cell_key)
                            l3_so_far = len([
                                t for t in all_generated_tasks
                                if t.get('level') == 3
                            ])
                            logger.info(
                                f"[{completed_count}/{total}] \u2713 "
                                f"{cell_key} \u2014 +{len(new_tasks)} tasks "
                                f"({l3_so_far} L3 total)"
                            )
                        else:
                            logger.error(
                                f"[{completed_count}/{total}] \u2717 "
                                f"{cell_key} \u2014 FAILED"
                            )
                            failed_keys.add(cell_key)

                        # Save checkpoint every 5 cells or on last
                        if (completed_count % 5 == 0
                                or completed_count == total):
                            save_checkpoint({
                                'completed_cells': list(completed_keys),
                                'failed_cells': list(failed_keys),
                                'generated_tasks': all_generated_tasks,
                                'timestamp': datetime.now().isoformat(),
                            })

            # Final checkpoint after parallel block
            with checkpoint_lock:
                save_checkpoint({
                    'completed_cells': list(completed_keys),
                    'failed_cells': list(failed_keys),
                    'generated_tasks': all_generated_tasks,
                    'timestamp': datetime.now().isoformat(),
                })

    # Save new tasks to separate file
    with open(NEW_TASKS_FILE, 'w', encoding='utf-8') as f:
        json.dump(all_generated_tasks, f, ensure_ascii=False, indent=2)
    logger.info(
        f"Saved {len(all_generated_tasks)} new tasks to {NEW_TASKS_FILE}"
    )

    # Merge into main DB
    if all_generated_tasks and not args.dry_run:
        db = load_db()
        db = merge_into_db(db, all_generated_tasks)
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
        logger.info(
            f"Merged into {OUTPUT_FILE} \u2014 total {len(db)} tasks"
        )

    # Summary
    logger.info(f"\n{'='*60}")
    logger.info("L3 Generation complete!")
    logger.info(f"  Cells processed: {len(completed_keys)}")
    logger.info(f"  New tasks generated: {len(all_generated_tasks)}")

    # Check remaining holes
    remaining = [c for c in cells if c['cell_key'] not in completed_keys]
    if remaining:
        logger.info(f"  Cells STILL with holes: {len(remaining)}")
        remaining_needed = sum(c['needed'] for c in remaining)
        logger.info(f"  Remaining tasks needed: {remaining_needed}")
        for c in remaining:
            logger.info(
                f"    {c['cell_key']} \u2014 {c['count']}/{TARGET} "
                f"(need {c['needed']})"
            )
    else:
        logger.info("  All L3 cells filled! \u2713")

    # Final DB stats
    db = load_db()
    l3_now = [t for t in db if t.get('level') == 3]
    logger.info(f"  L3 total after merge: {len(l3_now)} tasks")


if __name__ == '__main__':
    main()
