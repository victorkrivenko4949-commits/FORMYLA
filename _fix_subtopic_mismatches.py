#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Исправление 9 задач, не соответствующих своей подтеме.
Для каждой задачи:
- Найти peer-задачи в той же ячейке (тема, класс, уровень)
- Отправить DeepSeek-reasoner с указанием темы, класса, уровня
- Передать тексты peer-задач (до 4) как примеры ТОГО, ЧЕГО ДЕЛАТЬ НЕ НАДО
- Получить новую задачу, обновить curated_bank_L1_L5_fixed.json

Usage:
    python _fix_subtopic_mismatches.py
"""

import json
import os
import sys
import time
import logging
from datetime import datetime, timezone
from typing import Optional

sys.path.insert(0, os.path.dirname(__file__))
from ai.deepseek_client import DeepSeekClient, DeepSeekAPIError
from _audit_150_pilot import safe_parse_json

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ─── Paths ──────────────────────────────────────────────────────────
CURATED_BANK_FILE = "curated_bank_L1_L5_fixed.json"
OUTPUT_FILE = "_subtopic_fix_results.json"
CHECKPOINT_FILE = "_subtopic_fix_checkpoint.json"
REPORT_FILE = "_subtopic_fix_report.txt"

MAX_ATTEMPTS = 3
REASONER_TIMEOUT = 180
REASONER_MAX_TOKENS = 8192

# ─── Mismatch tasks: (original_id, topic, grade, level) ────────────
MISMATCH_INFO = [
    ("SEL1080-0293", "Системы", 8, 2),
    ("SEL1080-0304", "Системы и текстовые задачи", 8, 3),
    ("SEL1080-0573", "Алгебра. Неравенства и оценки", 11, 1),
    ("SEL1080-0068", "Раскраска", 8, 3),
    ("SEL1080-0075", "Раскраска", 5, 5),
    ("SEL1080-0073", "Принцип Дирихле", 5, 1),
    ("SEL1080-0377", "Логика. Логика, инварианты, стратегии", 9, 1),
    ("SEL1080-0127", "Уравнения и текстовые задачи", 6, 4),
    ("SEL1080-0672", "Раскраски", 11, 2),
]


# ─── Level Rubric (L1-L5) ──────────────────────────────────────────
LEVEL_RUBRIC = """
L1 — Базовый уровень
  - Прямое применение одного известного факта или формулы
  - Одна тема школьной программы, стандартный алгоритм
  - Прямое применение правил, подстановка в формулу

L2 — Повышенный уровень
  - Комбинация 2-3 простых шагов или фактов
  - Может потребоваться перебор небольшого числа вариантов
  - Простая текстовая задача, перевод на математический язык

L3 — Средний уровень
  - Требуется нестандартный подход или анализ
  - Определение стратегии решения из нескольких возможных
  - Задача на оценку + пример или перебор с обоснованием

L4 — Высокий уровень
  - Несколько различных идей или глубокое понимание теории
  - Задача на конструкцию + доказательство
  - Существенный перебор или анализ граничных случаев

L5 — Олимпиадный уровень
  - Творческая работа, комбинация глубоких идей
  - Оригинальная идея или изящное наблюдение
  - Несколько шагов рассуждения, требующих олимпиадной культуры
"""

# ─── System prompt для генерации новой задачи ──────────────────────
FIX_SYSTEM_PROMPT = """Ты — эксперт-методист по созданию математических задач для системы адаптивного обучения Формула.

Твоя задача — создать НОВУЮ математическую задачу строго по указанным параметрам: тема, класс, уровень сложности.

## Рубрика уровней (L1-L5):
{level_rubric}

## ГЛАВНОЕ ПРАВИЛО — РАЗНООБРАЗИЕ В ЯЧЕЙКЕ:
В каждой ячейке (тема + класс + уровень сложности) все 5 задач должны быть МАКСИМАЛЬНО РАЗНЫМИ между собой.
Категорически НЕЛЬЗЯ создавать задачу, похожую сюжетом, числами, математической идеей или формулировкой на любую другую задачу из этой же ячейки.
Твоя задача должна быть НЕ ПОХОЖА НИ НА ОДНУ из существующих задач в этой ячейке — другой сюжет, другие числа, другая математическая ситуация, другой подход к решению.

## Требования к задаче:
1. Условие должно быть логически непротиворечивым, полным и однозначным.
2. Уровень сложности должен строго соответствовать заявленному.
3. Задача должна быть решаема методами указанного класса.
4. Тема должна строго соответствовать указанной.
5. Если в задаче требуется рисунок или график — опиши его словами в условии.
6. Ответ и решение обязательны.
7. Задача должна быть НОВОЙ — не повторять формулировку, сюжет или идею задач из списка "Примеры задач, которых нужно ИЗБЕГАТЬ".

## Формат ответа:
Ты ДОЛЖЕН ответить строго в следующем JSON-формате (без markdown, без обрамления):

{{"statement":"...","answer":"...","solution":"...","level":N,"grade":M,"topic":"..."}}

Где:
- statement — условие задачи
- answer — ответ
- solution — решение
- level — уровень сложности (1-4)
- grade — класс
- topic — тема

ВАЖНО: Ответь ТОЛЬКО JSON-объектом, без пояснений, без markdown-обрамления.
"""


def build_fix_prompt(
    original_id: str,
    topic: str,
    grade: int,
    level: int,
    old_statement: str,
    peers: list,
) -> str:
    """Build user prompt for generating a replacement task on the correct subtopic.
    
    CRITICAL: All tasks in the same cell (topic+grade+level) must be MAXIMALLY DIFFERENT.
    The new task must NOT resemble ANY existing task in this cell in terms of:
    - plot/situation
    - numbers
    - mathematical idea
    - solution approach
    """
    # Build peer examples section
    peers_section = ""
    if peers:
        peers_lines = []
        for i, p in enumerate(peers, 1):
            stmt = p.get("statement", "").strip()
            ans = p.get("answer", "").strip()
            sol = p.get("solution", "").strip()
            pid = p.get("original_id", "?")
            peers_lines.append(f"  [{i}] ID={pid}: {stmt[:300]}")
            if ans:
                peers_lines.append(f"      Ответ: {ans[:150]}")
            if sol:
                # Extract first sentence to show approach
                first_sentence = sol[:200].split('.')[0]
                peers_lines.append(f"      Идея решения: {first_sentence}...")
        peers_text = "\n".join(peers_lines)
        peers_section = f"""
## [!]️ Примеры задач, которых нужно СТРОГО ИЗБЕГАТЬ:
В той же ячейке (тема={topic}, класс={grade}, уровень=L{level}) уже есть следующие задачи.
Твоя задача ОБЯЗАНА быть МАКСИМАЛЬНО НЕ ПОХОЖЕЙ на КАЖДУЮ из них.

Критерии различия (достаточно ОДНОГО):
- ДРУГОЙ сюжет (не про то же самое)
- ДРУГИЕ числа (не те же самые отношения)
- ДРУГАЯ математическая идея (другое свойство, другая формула)
- ДРУГОЙ подход к решению

Текущие задачи в ячейке (ИЗБЕГАТЬ):
{peers_text}
"""
    else:
        peers_section = f"""
## Информация о ячейке:
В ячейке (тема={topic}, класс={grade}, уровень=L{level}) пока нет других задач.
Создай первую задачу для этой ячейки.
"""

    prompt = f"""Создай НОВУЮ математическую задачу со следующими параметрами:

## Параметры задачи:
- Тема: {topic}
- Класс: {grade}
- Уровень сложности: L{level}

## Пояснение по подтеме:
Задача должна быть именно на тему "{topic}" и строго соответствовать этой подтеме.
{peers_section}

## Что нужно сделать (строго по порядку):
1. Внимательно изучи все существующие задачи в этой ячейке (если они есть).
2. Определи, какие сюжеты, числа, математические идеи УЖЕ ИСПОЛЬЗОВАНЫ.
3. Придумай задачу на тему "{topic}" для {grade} класса уровня L{level}, которая ИСПОЛЬЗУЕТ ДРУГУЮ математическую идею.
4. Убедись, что задача максимально не похожа на все существующие в ячейке.
5. Задача должна быть корректной, полной, однозначной.
6. Обязательно укажи ответ и решение.

## Важно:
[!]️ НЕДОПУСТИМО повторять сюжеты, числа или идеи из существующих задач
[!]️ Задача ДОЛЖНА БЫТЬ ПРИНЦИПИАЛЬНО ДРУГОЙ — другой раздел темы, другой подход
[OK] Придумай что-то оригинальное и интересное
[OK] Решение должно быть доступно ученику {grade} класса

Ответь JSON-объектом.
"""
    return prompt


def find_peers(bank: list, topic: str, grade: int, level: int, exclude_oids: set) -> list:
    """Find peer tasks in the same (topic, grade, level) cell, excluding mismatches.
    
    CRITICAL: If multiple tasks in the same cell are being fixed, the already-fixed
    ones are also excluded so they appear in the "avoid" list for subsequent fixes.
    This ensures all 5 tasks in a cell are maximally different.
    """
    return [
        t for t in bank
        if t.get("topic") == topic
        and t.get("grade") == grade
        and t.get("level") == level
        and t.get("original_id") not in exclude_oids
    ]


def fix_single_task(
    client: DeepSeekClient,
    bank: list,
    original_id: str,
    topic: str,
    grade: int,
    level: int,
    already_fixed_ids: set = None,
) -> dict:
    """Generate a replacement task for the mismatch using DeepSeek-reasoner.
    
    Args:
        already_fixed_ids: Set of original_ids in the same cell that were already
                          regenerated. Their NEW statements will be included as peers
                          to avoid, ensuring intra-cell diversity.
    """
    # Find the task entry in bank
    task_entry = None
    for t in bank:
        if t.get("original_id") == original_id:
            task_entry = t
            break

    if not task_entry:
        return {
            "original_id": original_id,
            "success": False,
            "error": f"Task {original_id} not found in curated bank",
        }

    old_statement = task_entry.get("statement", "")
    old_answer = task_entry.get("answer", "")
    old_solution = task_entry.get("solution", "")

    if already_fixed_ids is None:
        already_fixed_ids = set()
    
    # Build exclude set: current task + already-fixed tasks in this cell
    exclude_oids = {original_id} | already_fixed_ids
    
    # Find peers: correct tasks in same cell + ALREADY FIXED tasks (with new statements)
    peers = find_peers(bank, topic, grade, level, exclude_oids)
    
    # Add already-fixed tasks' NEW statements as peers to avoid
    if already_fixed_ids:
        for t in bank:
            if t.get("original_id") in already_fixed_ids:
                # Use the already-updated statement (IF the bank was updated)
                peers.append(t)
        logger.info(f"[{original_id}] Added {len(already_fixed_ids)} already-fixed task(s) from this cell to avoid-list")
    
    logger.info(f"[{original_id}] Found {len(peers)} peer(s) to avoid in cell ({topic}, gr{grade}, L{level})")

    # Build prompts
    user_prompt = build_fix_prompt(original_id, topic, grade, level, old_statement, peers)
    system_prompt = FIX_SYSTEM_PROMPT.format(level_rubric=LEVEL_RUBRIC)

    last_error = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            logger.info(f"[{original_id}] Attempt {attempt+1}/{MAX_ATTEMPTS} (deepseek-reasoner)...")
            content = client.generate_with_reasoning(
                prompt=user_prompt,
                system_prompt=system_prompt,
                max_tokens=REASONER_MAX_TOKENS,
                timeout=REASONER_TIMEOUT,
                return_reasoning=False,
            )

            parsed = safe_parse_json(content)
            if not parsed:
                raise ValueError("safe_parse_json returned empty dict")

            new_statement = parsed.get("statement", "").strip()
            new_answer = parsed.get("answer", "").strip()
            new_solution = parsed.get("solution", "").strip()
            new_level = parsed.get("level", level)
            new_grade = parsed.get("grade", grade)
            new_topic = parsed.get("topic", topic)

            if not new_statement:
                raise ValueError("Missing 'statement' in response")
            if not new_answer:
                raise ValueError("Missing 'answer' in response")
            if not new_solution:
                raise ValueError("Missing 'solution' in response")

            logger.info(f"[{original_id}] SUCCESS on attempt {attempt+1}")
            return {
                "original_id": original_id,
                "success": True,
                "error": None,
                "old_task": {
                    "statement": old_statement,
                    "answer": old_answer,
                    "solution": old_solution,
                },
                "new_task": {
                    "statement": new_statement,
                    "answer": new_answer,
                    "solution": new_solution,
                    "level": new_level,
                    "grade": new_grade,
                    "topic": new_topic,
                },
                "peer_ids": [p.get("original_id") for p in peers],
                "attempts_used": attempt + 1,
                "fixed_by_ai": True,
                "fix_timestamp": datetime.now(timezone.utc).isoformat(),
                "changes_made": [
                    f"Регенерирована задача: не соответствовала подтеме '{topic}'",
                    f"Старое условие: {old_statement[:100]}...",
                    f"Новое условие: {new_statement[:100]}...",
                ],
            }

        except (DeepSeekAPIError, ValueError, Exception) as e:
            last_error = str(e)
            logger.warning(f"[{original_id}] Attempt {attempt+1} failed: {type(e).__name__}: {str(e)[:200]}")
            if attempt < MAX_ATTEMPTS - 1:
                wait = 10 * (2 ** attempt)
                logger.info(f"[{original_id}] Waiting {wait}s before retry...")
                time.sleep(wait)

    logger.error(f"[{original_id}] ALL {MAX_ATTEMPTS} ATTEMPTS FAILED: {last_error}")
    return {
        "original_id": original_id,
        "success": False,
        "error": last_error,
        "old_task": {
            "statement": old_statement,
            "answer": old_answer,
            "solution": old_solution,
        },
        "new_task": None,
        "peer_ids": [p.get("original_id") for p in peers],
        "attempts_used": MAX_ATTEMPTS,
    }


def load_checkpoint() -> Optional[dict]:
    """Load fix checkpoint if exists."""
    if not os.path.exists(CHECKPOINT_FILE):
        return None
    try:
        with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        logger.info(f"Loaded checkpoint: {len(data.get('results', []))} tasks already done")
        return data
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"Could not load checkpoint: {e}")
        return None


def save_checkpoint(output: dict):
    """Save intermediate checkpoint."""
    tmp = CHECKPOINT_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CHECKPOINT_FILE)
    logger.info(f"Checkpoint saved ({len(output.get('results', []))} tasks)")


def update_curated_bank(bank: list, results: list) -> list:
    """Update curated bank entries with fixed tasks."""
    updated_count = 0
    bank_map = {t.get("original_id"): t for t in bank}

    for r in results:
        if not r.get("success"):
            continue
        oid = r["original_id"]
        new = r["new_task"]
        if oid not in bank_map:
            logger.warning(f"[{oid}] Not found in curated bank, cannot update")
            continue

        entry = bank_map[oid]
        entry["statement"] = new["statement"]
        entry["answer"] = new["answer"]
        entry["solution"] = new["solution"]
        entry["level"] = new.get("level", entry.get("level"))
        entry["grade"] = new.get("grade", entry.get("grade"))
        entry["topic"] = new.get("topic", entry.get("topic"))
        entry["fixed_by_ai"] = True
        entry["fix_timestamp"] = datetime.now(timezone.utc).isoformat()
        entry["changes_made"] = entry.get("changes_made", []) + r.get("changes_made", [])
        updated_count += 1
        logger.info(f"[{oid}] Updated in curated bank")

    logger.info(f"Total updated in bank: {updated_count}")
    return bank


def generate_report(results: list):
    """Generate human-readable fix report."""
    lines = []
    lines.append("=" * 70)
    lines.append("ОТЧЁТ ОБ ИСПРАВЛЕНИИ ЗАДАЧ, НЕ СООТВЕТСТВУЮЩИХ ПОДТЕМЕ")
    lines.append(f"Дата: {datetime.now(timezone.utc).isoformat()}")
    lines.append("=" * 70)
    lines.append("")

    successes = [r for r in results if r.get("success")]
    failures = [r for r in results if not r.get("success")]

    lines.append(f"Всего задач: {len(results)}")
    lines.append(f"Успешно исправлено: {len(successes)}")
    lines.append(f"Ошибок: {len(failures)}")
    lines.append("")

    if successes:
        lines.append("-" * 70)
        lines.append("УСПЕШНО ИСПРАВЛЕННЫЕ ЗАДАЧИ:")
        lines.append("-" * 70)
        for r in successes:
            lines.append(f"\n  [{r['original_id']}] (попыток: {r.get('attempts_used', '?')})")
            old = r.get("old_task", {})
            new = r.get("new_task", {})
            lines.append(f"  Старое условие: {old.get('statement', '')[:120]}...")
            lines.append(f"  Новое условие: {new.get('statement', '')[:120]}...")
            lines.append(f"  Ответ: {new.get('answer', '')[:80]}")
            peers = r.get("peer_ids", [])
            if peers:
                lines.append(f"  Peer-задачи (избегали): {', '.join(peers)}")
            lines.append("")

    if failures:
        lines.append("-" * 70)
        lines.append("ОШИБКИ:")
        lines.append("-" * 70)
        for r in failures:
            lines.append(f"\n  [{r['original_id']}] {r.get('error', 'Unknown error')}")
            lines.append("")

    lines.append("=" * 70)
    lines.append("КОНЕЦ ОТЧЁТА")
    lines.append("=" * 70)

    report = "\n".join(lines)
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write(report)
    logger.info(f"Report saved to {REPORT_FILE}")
    return report


def main():
    logger.info("=" * 60)
    logger.info("FIX SUBTOPIC MISMATCHES — Regenerating 9 mismatched tasks via DeepSeek-reasoner")
    logger.info("=" * 60)

    # ─── Load curated bank ─────────────────────────────────────────
    logger.info(f"Loading {CURATED_BANK_FILE}...")
    with open(CURATED_BANK_FILE, "r", encoding="utf-8") as f:
        bank = json.load(f)
    logger.info(f"Loaded {len(bank)} tasks from curated bank")

    # ─── Check checkpoint ──────────────────────────────────────────
    checkpoint = load_checkpoint()
    completed_ids = set()
    saved_results = []

    if checkpoint:
        saved_results = checkpoint.get("results", [])
        for r in saved_results:
            oid = r.get("original_id")
            if oid:
                completed_ids.add(oid)
        logger.info(f"Resuming from checkpoint: {len(completed_ids)} tasks already done")

    # Filter pending mismatches
    pending = [(oid, topic, grade, level) for (oid, topic, grade, level) in MISMATCH_INFO
               if oid not in completed_ids]
    logger.info(f"Pending tasks to process: {len(pending)} out of {len(MISMATCH_INFO)}")

    if not pending and saved_results:
        logger.info("All tasks already processed in checkpoint. Skipping API calls.")
        results = saved_results
    else:
        # ─── Init client ───────────────────────────────────────────
        client = DeepSeekClient()

        # ─── Process each mismatch sequentially ────────────────────
        results = list(saved_results)

        # Track already-fixed tasks per cell for intra-cell diversity
        # Key: (topic, grade, level) -> set of already-fixed original_ids
        cell_fixed_map: dict = {}
        
        for i, (oid, topic, grade, level) in enumerate(pending):
            logger.info(f"\n--- [{i+1}/{len(pending)}] Processing {oid} (topic='{topic}', gr={grade}, L{level}) ---")
            
            # Get already-fixed IDs in this cell
            cell_key = (topic, grade, level)
            already_fixed = cell_fixed_map.get(cell_key, set())
            if already_fixed:
                logger.info(f"  Cell has {len(already_fixed)} already-fixed task(s): {already_fixed}")
            
            result = fix_single_task(client, bank, oid, topic, grade, level, already_fixed)
            results.append(result)
            
            # If successful, record in cell_fixed_map for subsequent tasks in same cell
            if result.get("success"):
                if cell_key not in cell_fixed_map:
                    cell_fixed_map[cell_key] = set()
                cell_fixed_map[cell_key].add(oid)
                logger.info(f"  Recorded {oid} as fixed in cell {cell_key} for intra-cell diversity")

            # Save checkpoint after each task
            checkpoint_data = {
                "summary": {
                    "total": len(MISMATCH_INFO),
                    "processed": len(results),
                    "successful": len([r for r in results if r.get("success")]),
                    "failed": len([r for r in results if not r.get("success")]),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                "results": results,
            }
            save_checkpoint(checkpoint_data)

            # Brief delay between tasks
            if i < len(pending) - 1:
                delay = 5
                logger.info(f"Waiting {delay}s before next task...")
                time.sleep(delay)

    # ─── Summary ───────────────────────────────────────────────────
    successes = [r for r in results if r.get("success")]
    failures = [r for r in results if not r.get("success")]

    logger.info("\n" + "=" * 60)
    logger.info(f"FINAL RESULTS: {len(successes)} succeeded, {len(failures)} failed out of {len(results)}")
    if failures:
        logger.info(f"Failed IDs: {[r['original_id'] for r in failures]}")
    logger.info("=" * 60)

    # ─── Update curated bank ───────────────────────────────────────
    if successes:
        logger.info("\nUpdating curated bank...")
        bank = update_curated_bank(bank, results)

        # Save updated bank
        tmp = CURATED_BANK_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(bank, f, ensure_ascii=False, indent=2)
        os.replace(tmp, CURATED_BANK_FILE)
        logger.info(f"Updated {CURATED_BANK_FILE} saved")
    else:
        logger.warning("No successful fixes — curated bank NOT updated")

    # ─── Generate report ───────────────────────────────────────────
    generate_report(results)

    # ─── Save final results ────────────────────────────────────────
    final = {
        "summary": {
            "total": len(MISMATCH_INFO),
            "successful": len(successes),
            "failed": len(failures),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        "results": results,
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(final, f, ensure_ascii=False, indent=2)
    logger.info(f"Final results saved to {OUTPUT_FILE}")

    # ─── Clean up checkpoint ───────────────────────────────────────
    if os.path.exists(CHECKPOINT_FILE):
        os.remove(CHECKPOINT_FILE)
        logger.info("Checkpoint file removed")

    logger.info("Done!")


if __name__ == "__main__":
    main()
