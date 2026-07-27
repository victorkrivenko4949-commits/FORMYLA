#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Параллельный аудит 150 пилотных задач через DeepSeek-reasoner (10 потоков).

Аудитор проверяет по критериям:
1. Соответствие уровня (L1-L5 по рубрике)
2. Соответствие класса (можно ли решить темами N класса)
3. Соответствие темы (правильно ли указана тема)
4. Корректность условия (нет ошибок, условие полное)

Стартуем с первых 10 задач в 10 параллельных потоков.
"""

import json
import os
import sys
import re
import ast
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

# Add ai module to path
sys.path.insert(0, os.path.dirname(__file__))
from ai.deepseek_client import DeepSeekClient, DeepSeekAPIError

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ─── Paths ──────────────────────────────────────────────────────────
BASE = r"C:\Users\Victor\Downloads\FORMYLA_CONDITION_COURT"
CURATED_BANK = os.path.join(
    BASE, r"runs\selection_1080_20260712_134037\curated_bank_L1_L5_pre_live.json"
)
CHECKPOINT = os.path.join(
    BASE, r"outputs\live_calibration_v2_1_20260713_082344\task_checkpoint.jsonl"
)
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "audit_150_results.json")

# ─── Level Rubric (L1-L5) ──────────────────────────────────────────
LEVEL_RUBRIC = """
L1 — Базовый уровень
  - Прямое применение одного известного факта или формулы
  - Одна тема школьной программы, стандартный алгоритм
  - Прямое применение правил, подстановка в формулу
  - Время решения: 2-5 минут
  - Примеры: "Вычислите 25 × 13", "Найдите площадь квадрата со стороной 8"

L2 — Повышенный уровень
  - Комбинация 2-3 шагов или нестандартное применение
  - Одна-две темы, требуется выбор правильного метода из нескольких
  - Многошаговое рассуждение, простая комбинаторика, применение свойств
  - Время решения: 5-10 минут

L3 — Высокий уровень
  - Нетривиальная комбинация идей для сильного ученика
  - Несколько тем, глубокое понимание связей
  - Нетривиальная комбинация фактов, оценка+пример, инварианты, продвинутая комбинаторика
  - Время решения: 10-20 минут

L4 — Региональный олимпиадный уровень
  - Оригинальная идея, нестандартная техника
  - Продвинутые разделы, олимпиадные техники
  - Оригинальная конструкция, глубокие инварианты, продвинутая теория чисел
  - Время решения: 20-45 минут
  - Примеры: "Найдите все функции f: ℕ → ℕ, такие что f(f(n)) = n + 1 для всех n"

L5 — Заключительный олимпиадный уровень
  - Сложная многоходовая комбинация
  - Глубокие олимпиадные разделы, редкие техники
  - Многоходовая комбинация, оценка+пример с нетривиальной конструкцией
  - Время решения: 45-120 минут
  - Примеры: "Докажите, что множество всех бесконечных последовательностей из 0 и 1 несчётно"
"""

# ─── System Prompt ──────────────────────────────────────────────────
SYSTEM_PROMPT = f"""Ты — строгий аудитор математических задач для системы адаптивного обучения Формула.

Твоя задача — проверить задачу по следующим критериям и выдать структурированный вердикт.

## Рубрика уровней (L1-L5):
{LEVEL_RUBRIC}

## Критерии проверки:

### 1. СООТВЕТСТВИЕ УРОВНЯ (level_match)
Оцени, соответствует ли задача заявленному уровню L1-L5 согласно рубрике.
Учитывай: количество шагов решения, сложность требуемых знаний, 
необходимость нестандартных идей.

### 2. СООТВЕТСТВИЕ КЛАССА (class_match)
Оцени, соответствует ли задача указанному классу.
Учитывай: программу этого класса, какие темы проходятся,
доступность задачи для ученика этого возраста.

### 3. СООТВЕТСТВИЕ ТЕМЫ (topic_match)
Оцени, правильно ли указана тема задачи.
Учитывай: действительно ли задача относится к заявленной теме,
или более подходящая тема иная.

### 4. КОРРЕКТНОСТЬ УСЛОВИЯ (condition_correctness)
Проверь условие задачи на:
- Логическую непротиворечивость
- Полноту данных (нет ли пропущенных рисунков, неопределённых терминов)
- Отсутствие ошибок в формулировке
- Чёткость и однозначность понимания

## Формат ответа:
Ты ДОЛЖЕН ответить строго в следующем JSON-формате (без markdown, без обрамления):

{{{{"overall":"PASS","level_match":{{"verdict":"PASS","reasoning":"...","suggested_level":null}},"class_match":{{"verdict":"PASS","reasoning":"...","suggested_class":null}},"topic_match":{{"verdict":"PASS","reasoning":"...","suggested_topic":null}},"condition_correctness":{{"verdict":"PASS","reasoning":"..."}},"issues":[],"summary":"..."}}}}

Где:
- overall: "PASS" если все проверки пройдены, "FAIL" если есть хотя бы одна серьёзная проблема, "MINOR" если есть незначительные замечания
- Для каждого критерия: verdict может быть "PASS", "MINOR" (незначительное несоответствие), "MAJOR" (серьёзное несоответствие)
- Если есть несоответствие уровня, укажи suggested_level (какой уровень更适合)
- Если есть несоответствие класса, укажи suggested_class
- Если есть несоответствие темы, укажи suggested_topic
- issues: массив строк с описанием проблем (если есть)
- summary: краткое итоговое заключение

ВАЖНО: Ответь ТОЛЬКО JSON-объектом, без пояснений, без markdown-обрамления.
"""


def load_curated_bank(count=150):
    """Load first `count` entries from curated bank."""
    with open(CURATED_BANK, "r", encoding="utf-8") as f:
        data = json.load(f)
    logger.info(f"Loaded {len(data)} entries from curated bank, taking first {count}")
    return data[:count]


def load_checkpoint():
    """Load checkpoint and build task_index -> result mapping."""
    mapping = {}
    with open(CHECKPOINT, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            idx = entry["task_index"]
            mapping[idx] = entry
    logger.info(f"Loaded {len(mapping)} checkpoint entries")
    return mapping


def safe_parse_json(text: str) -> dict:
    """Robust JSON extraction from model response.

    Handles:
    - Markdown code blocks (```json ... ```)
    - Single-quoted keys/values (Python-style dict repr)
    - Trailing commas
    - Extra text before/after JSON
    """
    text = text.strip()

    # 1. Strip markdown code blocks
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(
            line for line in lines
            if not line.strip().startswith("```")
        ).strip()

    # 2. Find outermost { ... }
    brace_depth = 0
    json_start = -1
    json_end = -1
    for i, ch in enumerate(text):
        if ch == '{':
            if brace_depth == 0:
                json_start = i
            brace_depth += 1
        elif ch == '}':
            brace_depth -= 1
            if brace_depth == 0 and json_start >= 0:
                json_end = i + 1
                break

    if json_start < 0:
        raise ValueError(f"No valid JSON object found in response: {text[:300]}")

    # Handle truncation: DeepSeek-reasoner may hit max_tokens mid-JSON.
    # If outermost closing } is missing, force-close by appending missing braces.
    if json_end <= json_start and brace_depth > 0:
        # First, close any unterminated string value (odd number of quotes => string cut off)
        quote_count = text.count('"')
        if quote_count % 2 == 1:
            text = text + '"'
        # Then close all unclosed braces
        text = text + "}" * brace_depth
        json_end = len(text)
    elif json_end <= json_start:
        raise ValueError(f"No valid JSON object found in response: {text[:300]}")

    json_str = text[json_start:json_end]

    # 3. Normalize double-brace {{...}} → {...} (deepseek-reasoner artifact)
    #    The model sometimes echoes {{...}} back literally from the prompt
    if json_str.startswith("{{") and json_str.endswith("}}"):
        json_str = json_str[1:-1]  # strip one layer of braces
    # Also handle internal double braces
    json_str = json_str.replace("{{", "{").replace("}}", "}")

    # 4. Try standard json.loads first
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass

    # 5. Fix common issues: single quotes → double quotes
    #    Replace single quotes that are NOT inside double-quoted strings
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
        return json.loads(json_fixed)
    except json.JSONDecodeError:
        pass

    # 6. Fix trailing commas before ] or }
    json_fixed = re.sub(r',\s*([}\]])', r'\1', json_fixed)
    try:
        return json.loads(json_fixed)
    except json.JSONDecodeError:
        pass

    # 7. Try ast.literal_eval (handles Python dict literals with single quotes)
    #    But first replace all double quotes with single quotes except the outer ones
    try:
        # Convert double-quoted JSON string to Python dict literal
        # by replacing only the values and keys with single quotes
        result = ast.literal_eval(json_fixed)
        if isinstance(result, dict):
            return result
    except (ValueError, SyntaxError, MemoryError):
        pass

    # 8. Last resort: try just removing whitespace and any non-JSON prefix/suffix
    json_str_clean = re.sub(r'^[^{]*', '', json_str)
    json_str_clean = re.sub(r'[^}]*$', '', json_str_clean)
    try:
        return json.loads(json_str_clean)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse JSON after all attempts: {e}\nExtracted: {json_str[:500]}")


def audit_single_task(client: DeepSeekClient, task: dict, task_index: int,
                      checkpoint_entry: dict) -> dict:
    """Audit a single task via DeepSeek-reasoner."""
    # Extract data
    task_text = task.get("task_text", "")
    class_level = task.get("class_level", "?")
    target_level = task.get("target_level", "?")
    topic = task.get("topic", "?")

    # Also get pipeline verdict if available
    pipeline_verdict = None
    pipeline_confidence = None
    if checkpoint_entry:
        result = checkpoint_entry.get("result", {})
        pipeline_verdict = result.get("final_verdict")
        pipeline_confidence = result.get("confidence")

    user_prompt = f"""Проверь задачу на соответствие всем критериям.

## Данные задачи:
- Условие: {task_text}
- Заявленный уровень: {target_level}
- Класс: {class_level}
- Тема: {topic}

## Инструкция:
1. Проанализируй условие задачи.
2. Определи, какому уровню по рубрике L1-L5 она соответствует.
3. Определи, для какого класса она подходит.
4. Определи, к какой теме она относится.
5. Проверь корректность условия.
6. Сравни с заявленными: уровень={target_level}, класс={class_level}, тема={topic}.
7. Выдай структурированный вердикт в JSON-формате, как указано в system prompt.
"""

    try:
        logger.info(f"[{task_index}] Sending to DeepSeek-reasoner: "
                     f"target_level={target_level}, class={class_level}, "
                     f"topic={topic[:30]}...")

        # Use generate_with_reasoning (deepseek-reasoner model)
        content = client.generate_with_reasoning(
            prompt=user_prompt,
            system_prompt=SYSTEM_PROMPT,
            max_tokens=4096,
            timeout=300,
            return_reasoning=False,
        )

        # Parse JSON from response (robust)
        audit_result = safe_parse_json(content)

        logger.info(f"[{task_index}] ✓ Audit complete: overall={audit_result.get('overall', '?')}")
        return {
            "task_index": task_index,
            "task_text": task_text,
            "class_level": class_level,
            "target_level": target_level,
            "topic": topic,
            "pipeline_verdict": pipeline_verdict,
            "audit_result": audit_result,
            "success": True,
            "error": None,
        }

    except (DeepSeekAPIError, json.JSONDecodeError, ValueError, Exception) as e:
        logger.error(f"[{task_index}] ✗ Audit failed: {e}")
        return {
            "task_index": task_index,
            "task_text": task_text,
            "class_level": class_level,
            "target_level": target_level,
            "topic": topic,
            "pipeline_verdict": pipeline_verdict,
            "audit_result": None,
            "success": False,
            "error": str(e),
        }


def main():
    """Run audit on all 150 pilot tasks (10 concurrent threads)."""
    logger.info("=" * 60)
    logger.info("FORMYLA Pilot Audit — DeepSeek-reasoner, 10 threads, 150 tasks")
    logger.info("=" * 60)

    # Load data
    tasks = load_curated_bank(150)
    checkpoint = load_checkpoint()

    # Map checkpoint entries by task_index
    checkpoint_map = {}
    for idx, entry in checkpoint.items():
        if idx < 150:
            checkpoint_map[idx] = entry

    # Initialize DeepSeek client
    client = DeepSeekClient()

    # Run ALL 150 tasks in parallel (10 concurrent threads)
    n_total = len(tasks)
    results = []
    import threading
    print_lock = threading.Lock()

    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_idx = {}
        for i in range(n_total):
            task = tasks[i]
            cp_entry = checkpoint_map.get(i)
            future = executor.submit(audit_single_task, client, task, i, cp_entry)
            future_to_idx[future] = i

        # Collect results as they complete
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                result = future.result()
                results.append(result)
                overall = result.get("audit_result", {}).get("overall", "?") if result.get("success") else "FAIL"
                with print_lock:
                    logger.info(f"[{idx}] → overall={overall}, success={result['success']}")
            except Exception as e:
                with print_lock:
                    logger.error(f"[{idx}] Exception in thread: {e}")
                results.append({
                    "task_index": idx,
                    "success": False,
                    "error": str(e),
                })

    # Sort results by task_index
    results.sort(key=lambda r: r.get("task_index", 0))

    # Compute summary stats
    passed = sum(1 for r in results if r.get("success") and r["audit_result"].get("overall") == "PASS")
    minor = sum(1 for r in results if r.get("success") and r["audit_result"].get("overall") == "MINOR")
    failed_audit = sum(1 for r in results if r.get("success") and r["audit_result"].get("overall") == "FAIL")
    api_fail = sum(1 for r in results if not r.get("success"))

    # Build level/class/topic discrepancy counters
    level_mismatches = []
    class_mismatches = []
    topic_mismatches = []
    cond_issues = []

    for r in results:
        if r.get("success") and r.get("audit_result"):
            ar = r["audit_result"]
            lm = ar.get("level_match", {})
            cm = ar.get("class_match", {})
            tm = ar.get("topic_match", {})
            cd = ar.get("condition_correctness", {})
            if lm.get("verdict") in ("MAJOR", "MINOR"):
                level_mismatches.append((r["task_index"], lm["verdict"], lm.get("reasoning", "")))
            if cm.get("verdict") in ("MAJOR", "MINOR"):
                class_mismatches.append((r["task_index"], cm["verdict"], cm.get("reasoning", "")))
            if tm.get("verdict") in ("MAJOR", "MINOR"):
                topic_mismatches.append((r["task_index"], tm["verdict"], tm.get("reasoning", "")))
            if cd.get("verdict") in ("MAJOR", "MINOR"):
                cond_issues.append((r["task_index"], cd["verdict"], cd.get("reasoning", "")))

    # Save results
    summary_stats = {
        "total": n_total,
        "passed": passed,
        "minor": minor,
        "failed_audit": failed_audit,
        "api_failures": api_fail,
        "level_mismatches": len(level_mismatches),
        "class_mismatches": len(class_mismatches),
        "topic_mismatches": len(topic_mismatches),
        "condition_issues": len(cond_issues),
    }

    output = {
        "audit_timestamp": datetime.now(timezone.utc).isoformat(),
        "model": "deepseek-reasoner",
        "summary": summary_stats,
        "level_mismatches": [{"task_index": x[0], "verdict": x[1], "detail": x[2]} for x in level_mismatches],
        "class_mismatches": [{"task_index": x[0], "verdict": x[1], "detail": x[2]} for x in class_mismatches],
        "topic_mismatches": [{"task_index": x[0], "verdict": x[1], "detail": x[2]} for x in topic_mismatches],
        "condition_issues": [{"task_index": x[0], "verdict": x[1], "detail": x[2]} for x in cond_issues],
        "results": results,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # Print summary
    logger.info("=" * 60)
    logger.info(f"AUDIT COMPLETE — All {n_total} tasks")
    logger.info(f"  PASS:            {passed}")
    logger.info(f"  MINOR:           {minor}")
    logger.info(f"  FAIL (audit):    {failed_audit}")
    logger.info(f"  FAIL (API):      {api_fail}")
    logger.info(f"  Level mism.:     {len(level_mismatches)}")
    logger.info(f"  Class mism.:     {len(class_mismatches)}")
    logger.info(f"  Topic mism.:     {len(topic_mismatches)}")
    logger.info(f"  Condition iss.:  {len(cond_issues)}")
    logger.info(f"Results saved to: {OUTPUT_FILE}")
    logger.info("=" * 60)

    # Print brief per-task summary
    for r in results:
        idx = r.get("task_index", "?")
        level = r.get("target_level", "?")
        cls = r.get("class_level", "?")
        text_preview = r.get("task_text", "")[:50]
        if r.get("success") and r.get("audit_result"):
            overall = r["audit_result"].get("overall", "?")
            level_v = r["audit_result"].get("level_match", {}).get("verdict", "?")
            class_v = r["audit_result"].get("class_match", {}).get("verdict", "?")
            topic_v = r["audit_result"].get("topic_match", {}).get("verdict", "?")
            cond_v = r["audit_result"].get("condition_correctness", {}).get("verdict", "?")
            print(f"  [{idx}] LvL={level} Cls={cls} | OVERALL={overall} "
                  f"| Lv:{level_v} Cl:{class_v} Tp:{topic_v} Cd:{cond_v} "
                  f"| {text_preview}...")
        else:
            print(f"  [{idx}] LvL={level} Cls={cls} | FAILED: {r.get('error', '?')}")
    print("=" * 60)


if __name__ == "__main__":
    main()
