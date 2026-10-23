#!/usr/bin/env python
"""
Stage 3: Multi-role AI auditing of weak generated tasks (L4/L5).

Each weak task is evaluated independently by 5 AI roles:
  1. SOLVER           — solves the problem blindly (no reference solution)
  2. ARBITER          — compares own solution with the stored reference; flags discrepancies
  3. TOPIC CLASSIFIER — determines the mathematical topic blindly
  4. LEVEL CALIBRATOR — determines the difficulty level (3/4/5/6) blindly
  5. DUPLICATE JUDGE  — checks for duplicates by mathematical structure within the cell

Pipeline:
  Phase 1: tasks with quality < 60   (25 tasks -> 125 API calls)
  Phase 2: tasks with quality 60–70  (38 tasks -> 190 API calls)

The script saves a checkpoint after each fully-evaluated task so it can be resumed
if interrupted.
"""

import json
import os
import sys
import time
import logging
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
WORK_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(WORK_DIR)  # "Новая папка (2)"

GENERATED_TASKS_PATH = os.path.join(
    PROJECT_DIR, "l4_l5_completion_work", "stage6_generated_tasks.json"
)
AUDIT_RESULTS_PATH = os.path.join(WORK_DIR, "stage3_audit_results.json")
CHECKPOINT_PATH = os.path.join(WORK_DIR, "stage3_checkpoint.json")
REPORT_PATH = os.path.join(WORK_DIR, "stage3_audit_report.txt")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(WORK_DIR, "stage3_audit.log"), encoding="utf-8"),
    ],
)
logger = logging.getLogger("stage3_auditor")

# ---------------------------------------------------------------------------
# Quality score function (mirrors _00_inventory.py:7)
# ---------------------------------------------------------------------------
def compute_quality_score(task: Dict[str, Any]) -> float:
    sol = task.get("solution", task.get("solution_text", ""))
    stmt = task.get("text", task.get("statement", task.get("task_text", "")))
    sol_len = len(sol.strip()) if sol else 0
    sol_completeness = min(1.0, sol_len / 500) if sol_len > 0 else 0.0
    stmt_len = len(stmt.strip()) if stmt else 0
    statement_clarity = min(1.0, stmt_len / 200) if stmt_len > 0 else 0.0
    subtopic_relevance = 0.7
    has_valid = task.get("has_valid_solution", task.get("solution_verified", False))
    difficulty_confidence = 0.9 if has_valid else 0.5
    olympiad = task.get("_olympiad", task.get("olympiad", ""))
    if olympiad in ("vsosh", "region", "final"):
        source_quality = 1.0
    elif olympiad in ("euler", "kysh", "turloomath"):
        source_quality = 0.9
    elif olympiad in ("mos", "spb", "mipt"):
        source_quality = 0.8
    elif olympiad:
        source_quality = 0.7
    else:
        source_quality = 0.5
    score = (
        0.30 * sol_completeness
        + 0.25 * statement_clarity
        + 0.20 * subtopic_relevance
        + 0.15 * difficulty_confidence
        + 0.10 * source_quality
    )
    return round(score * 100, 1)


# ---------------------------------------------------------------------------
# Load generated tasks, compute quality, split into phases
# ---------------------------------------------------------------------------
def load_tasks() -> List[Dict[str, Any]]:
    with open(GENERATED_TASKS_PATH, "r", encoding="utf-8") as f:
        tasks = json.load(f)
    logger.info("Loaded %d generated tasks from %s", len(tasks), GENERATED_TASKS_PATH)
    # Compute quality scores
    for t in tasks:
        t["_quality_score"] = compute_quality_score(t)
    return tasks


def split_phases(tasks: List[Dict[str, Any]]):
    phase1 = [t for t in tasks if t["_quality_score"] < 60]
    phase2 = [t for t in tasks if 60 <= t["_quality_score"] < 70]
    phase1.sort(key=lambda x: x["_quality_score"])
    phase2.sort(key=lambda x: x["_quality_score"])
    logger.info("Phase 1 (quality < 60):  %d tasks", len(phase1))
    logger.info("Phase 2 (quality 60–70): %d tasks", len(phase2))
    return phase1, phase2


# ---------------------------------------------------------------------------
# Checkpoint helpers
# ---------------------------------------------------------------------------
def load_checkpoint() -> Dict[str, Any]:
    if os.path.exists(CHECKPOINT_PATH):
        with open(CHECKPOINT_PATH, "r", encoding="utf-8") as f:
            cp = json.load(f)
        logger.info("Loaded checkpoint: %d tasks completed", len(cp.get("completed_ids", [])))
        return cp
    return {"completed_ids": [], "results": []}


def save_checkpoint(completed_ids: List[str], results: List[Dict[str, Any]]):
    data = {"completed_ids": completed_ids, "results": results}
    tmp = CHECKPOINT_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CHECKPOINT_PATH)
    logger.info("Checkpoint saved: %d tasks completed", len(completed_ids))


# ---------------------------------------------------------------------------
# Role prompts (in Russian, per specification)
# ---------------------------------------------------------------------------
SOLVER_SYSTEM_PROMPT = """Ты — независимый математик-решатель (SOLVER).
Твоя задача: реши предложенную задачу самостоятельно, НЕ глядя на готовое решение.
Выпиши полное, строгое решение с обоснованием каждого шага.
В конце укажи ответ.

ВАЖНО: Не используй символы обратного слеша в своём ответе.
Используй \( ... \) для формул.

Выведи результат строго в JSON-формате:
{
  "solver_solution": "твоё полное решение задачи",
  "solver_answer": "итоговый ответ",
  "solver_confidence": 0.0-1.0,
  "solver_notes": "любые замечания о сложности, неоднозначности условия и т.д."
}"""

ARBITER_SYSTEM_PROMPT = """Ты — арбитр (ARBITER).
Твоя задача: сравнить своё собственное решение задачи с эталонным решением, которое предоставлено.
Найди любые несоответствия, ошибки, пропущенные шаги или расхождения.

Выведи результат строго в JSON-формате:
{
  "arbiter_verdict": "совпадает | частично совпадает | не совпадает",
  "arbiter_discrepancies": ["список расхождений"],
  "arbiter_errors_in_reference": ["ошибки в эталонном решении, если есть"],
  "arbiter_notes": "дополнительные замечания"
}"""

TOPIC_CLASSIFIER_SYSTEM_PROMPT = """Ты — классификатор темы (TOPIC CLASSIFIER).
Твоя задача: прочитай условие задачи и определи её математическую тему, подтему и раздел.
НЕ используй информацию о cell_key, grade, level — определи тему ТОЛЬКО по условию.

Возможные темы (для справки):
- Алгебра (уравнения, неравенства, последовательности, функции)
- Теория чисел (делимость, НОД/НОК, остатки, диофантовы уравнения)
- Комбинаторика (перестановки, размещения, сочетания, правило произведения)
- Теория вероятностей (классическая вероятность, условная вероятность, формула Байеса)
- Геометрия (планиметрия, стереометрия, векторы)
- Графы (деревья, степень вершины, связность)
- Логика (таблицы истинности, булевы выражения)
- Текстовые задачи (движение, работа, проценты, смеси, отношения)

Выведи результат строго в JSON-формате:
{
  "predicted_theme": "название темы",
  "predicted_subtopic": "название подтемы",
  "confidence": 0.0-1.0,
  "reasoning": "почему ты так решил(а)"
}"""

LEVEL_CALIBRATOR_SYSTEM_PROMPT = """Ты — калибратор уровня (LEVEL CALIBRATOR).
Твоя задача: определи уровень сложности задачи ТОЛЬКО по условию.
Уровни: 3 (базовый), 4 (средний), 5 (продвинутый), 6 (олимпиадный).
НЕ используй информацию grade, level из метаданных — определи вслепую.

Ориентиры:
- Уровень 3: простые задачи в 1-2 действия, стандартные алгоритмы
- Уровень 4: задачи в 2-3 действия, требуется комбинировать знания
- Уровень 5: многошаговые задачи, требуется нестандартный подход
- Уровень 6: сложные олимпиадные задачи, глубокие математические идеи

Выведи результат строго в JSON-формате:
{
  "predicted_level": 3-6,
  "confidence": 0.0-1.0,
  "reasoning": "почему ты так решил(а)"
}"""

DUPLICATE_JUDGE_SYSTEM_PROMPT = """Ты — судья по дубликатам (DUPLICATE JUDGE).
Твоя задача: проанализируй математическую структуру задачи и сравни её с другими задачами из той же ячейки (cell_key).
Определи, является ли эта задача дубликатом других задач по математической сути.
Дубликат — это задача, которая решается тем же методом, имеет ту же математическую структуру,
даже если формулировка отличается.

Учитывай:
1. Если задачи отличаются только числами — это дубликат
2. Если задачи используют ту же идею/метод — возможно, дубликат
3. Если задачи имеют разную математическую структуру — не дубликат

Выведи результат строго в JSON-формате:
{
  "is_duplicate": true | false,
  "duplicate_of": ["task_id_1", "task_id_2", ...],
  "similarity_reason": "объяснение, почему задача дублирует или не дублирует другие",
  "uniqueness_score": 0.0-1.0
}"""


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Try to extract a JSON object from text, handling markdown fences."""
    # Remove markdown code fences
    import re
    # Try to find a JSON block between ```json and ```
    m = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if m:
        text = m.group(1)
    # Try to find { ... } directly
    m = re.search(r"(\{.*\})", text, re.DOTALL)
    if m:
        text = m.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def audit_solver(client, task: Dict[str, Any]) -> Dict[str, Any]:
    """Role 1: SOLVER — solve the problem blindly using reasoning model."""
    statement = task.get("statement", "")
    prompt = (
        f"Реши следующую математическую задачу. Выпиши полное решение.\n\n"
        f"---\n{statement}\n---\n\n"
        f"Выведи ответ строго в JSON-формате."
    )
    try:
        raw = client.generate_with_reasoning(
            prompt=prompt,
            system_prompt=SOLVER_SYSTEM_PROMPT,
            max_tokens=3000,
            timeout=300,
        )
        parsed = _extract_json(raw)
        if parsed:
            return {"role": "SOLVER", "status": "ok", "data": parsed}
        else:
            return {"role": "SOLVER", "status": "parse_failed", "raw": raw[:500]}
    except Exception as e:
        logger.error("SOLVER failed for %s: %s", task.get("task_id", "?"), str(e))
        return {"role": "SOLVER", "status": "error", "error": str(e)}


def audit_arbiter(client, task: Dict[str, Any]) -> Dict[str, Any]:
    """Role 2: ARBITER — compare own solution with reference."""
    statement = task.get("statement", "")
    reference_solution = task.get("solution", "")
    prompt = (
        f"Условие задачи:\n{statement}\n\n"
        f"Эталонное решение:\n{reference_solution}\n\n"
        f"Реши задачу самостоятельно, затем сравни своё решение с эталонным. "
        f"Найди расхождения, если они есть."
    )
    try:
        raw = client.generate(
            prompt=prompt,
            system_prompt=ARBITER_SYSTEM_PROMPT,
            temperature=0.2,
            max_tokens=2000,
            response_format={"type": "json_object"},
        )
        parsed = _extract_json(raw)
        if parsed:
            return {"role": "ARBITER", "status": "ok", "data": parsed}
        else:
            return {"role": "ARBITER", "status": "parse_failed", "raw": raw[:500]}
    except Exception as e:
        logger.error("ARBITER failed for %s: %s", task.get("task_id", "?"), str(e))
        return {"role": "ARBITER", "status": "error", "error": str(e)}


def audit_topic_classifier(client, task: Dict[str, Any]) -> Dict[str, Any]:
    """Role 3: TOPIC CLASSIFIER — determine topic blindly."""
    statement = task.get("statement", "")
    prompt = f"Определи математическую тему этой задачи только по условию:\n\n{statement}"
    try:
        raw = client.generate(
            prompt=prompt,
            system_prompt=TOPIC_CLASSIFIER_SYSTEM_PROMPT,
            temperature=0.2,
            max_tokens=1000,
            response_format={"type": "json_object"},
        )
        parsed = _extract_json(raw)
        if parsed:
            return {"role": "TOPIC_CLASSIFIER", "status": "ok", "data": parsed}
        else:
            return {"role": "TOPIC_CLASSIFIER", "status": "parse_failed", "raw": raw[:500]}
    except Exception as e:
        logger.error("TOPIC_CLASSIFIER failed for %s: %s", task.get("task_id", "?"), str(e))
        return {"role": "TOPIC_CLASSIFIER", "status": "error", "error": str(e)}


def audit_level_calibrator(client, task: Dict[str, Any]) -> Dict[str, Any]:
    """Role 4: LEVEL CALIBRATOR — determine level blindly."""
    statement = task.get("statement", "")
    prompt = f"Определи уровень сложности этой задачи (3, 4, 5 или 6) только по условию:\n\n{statement}"
    try:
        raw = client.generate(
            prompt=prompt,
            system_prompt=LEVEL_CALIBRATOR_SYSTEM_PROMPT,
            temperature=0.2,
            max_tokens=800,
            response_format={"type": "json_object"},
        )
        parsed = _extract_json(raw)
        if parsed:
            return {"role": "LEVEL_CALIBRATOR", "status": "ok", "data": parsed}
        else:
            return {"role": "LEVEL_CALIBRATOR", "status": "parse_failed", "raw": raw[:500]}
    except Exception as e:
        logger.error("LEVEL_CALIBRATOR failed for %s: %s", task.get("task_id", "?"), str(e))
        return {"role": "LEVEL_CALIBRATOR", "status": "error", "error": str(e)}


def audit_duplicate_judge(client, task: Dict[str, Any], cell_tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Role 5: DUPLICATE JUDGE — check for duplicates within the cell."""
    statement = task.get("statement", "")
    cell_key = task.get("cell_key", "")
    peer_statements = []
    for pt in cell_tasks:
        if pt.get("task_id") != task.get("task_id"):
            peer_statements.append({"task_id": pt.get("task_id"), "statement": pt.get("statement", "")})

    prompt = (
        f"Задача:\n{statement}\n\n"
        f"Другие задачи из той же ячейки ({cell_key}):\n"
    )
    for ps in peer_statements:
        prompt += f"- [{ps['task_id']}]: {ps['statement']}\n"
    prompt += "\nОпредели, является ли данная задача дубликатом каких-либо из перечисленных по математической структуре."
    try:
        raw = client.generate(
            prompt=prompt,
            system_prompt=DUPLICATE_JUDGE_SYSTEM_PROMPT,
            temperature=0.2,
            max_tokens=1000,
            response_format={"type": "json_object"},
        )
        parsed = _extract_json(raw)
        if parsed:
            return {"role": "DUPLICATE_JUDGE", "status": "ok", "data": parsed}
        else:
            return {"role": "DUPLICATE_JUDGE", "status": "parse_failed", "raw": raw[:500]}
    except Exception as e:
        logger.error("DUPLICATE_JUDGE failed for %s: %s", task.get("task_id", "?"), str(e))
        return {"role": "DUPLICATE_JUDGE", "status": "error", "error": str(e)}


# ---------------------------------------------------------------------------
# Main audit loop
# ---------------------------------------------------------------------------
def run_audit():
    # Import here to handle missing modules gracefully
    sys.path.insert(0, PROJECT_DIR)
    from ai.deepseek_client import DeepSeekClient

    client = DeepSeekClient()
    logger.info("DeepSeekClient initialized")

    # Load tasks
    tasks = load_tasks()
    phase1, phase2 = split_phases(tasks)

    # Build cell lookup for duplicate judge
    cell_lookup: Dict[str, List[Dict[str, Any]]] = {}
    for t in tasks:
        ck = t.get("cell_key", "")
        if ck not in cell_lookup:
            cell_lookup[ck] = []
        cell_lookup[ck].append(t)

    # Load checkpoint
    cp = load_checkpoint()
    completed_ids = set(cp.get("completed_ids", []))
    results = cp.get("results", [])
    logger.info("Resuming with %d already-completed tasks", len(completed_ids))

    # Process both phases sequentially
    all_weak = [(phase1, "Phase 1 (<60)"), (phase2, "Phase 2 (60-70)")]

    for phase_tasks, phase_name in all_weak:
        logger.info("=" * 60)
        logger.info("  Starting %s: %d tasks", phase_name, len(phase_tasks))
        logger.info("=" * 60)

        for idx, task in enumerate(phase_tasks):
            task_id = task.get("task_id", "?")
            cell_key = task.get("cell_key", "")
            quality = task["_quality_score"]

            if task_id in completed_ids:
                logger.info("[%s] [%d/%d] task %s already completed — skipping",
                            phase_name, idx + 1, len(phase_tasks), task_id)
                continue

            logger.info("[%s] [%d/%d] Auditing task %s | cell=%s | quality=%.1f",
                        phase_name, idx + 1, len(phase_tasks), task_id, cell_key, quality)
            logger.info("  Statement: %s", task.get("statement", "")[:100])

            task_result = {
                "task_id": task_id,
                "cell_key": cell_key,
                "quality_score": quality,
                "phase": phase_name,
                "statement": task.get("statement", ""),
                "solution": task.get("solution", ""),
                "reference_answer": task.get("answer", ""),
                "grade": task.get("grade"),
                "level": task.get("level"),
                "theme_name": task.get("theme_name", ""),
                "subtopic": task.get("subtopic", ""),
                "audits": [],
            }

            # 1) SOLVER (uses reasoning model)
            logger.info("  -> SOLVER...")
            solver_result = audit_solver(client, task)
            task_result["audits"].append(solver_result)
            time.sleep(1.5)  # rate limiting

            # 2) ARBITER
            logger.info("  -> ARBITER...")
            arbiter_result = audit_arbiter(client, task)
            task_result["audits"].append(arbiter_result)
            time.sleep(1.0)

            # 3) TOPIC CLASSIFIER
            logger.info("  -> TOPIC CLASSIFIER...")
            topic_result = audit_topic_classifier(client, task)
            task_result["audits"].append(topic_result)
            time.sleep(1.0)

            # 4) LEVEL CALIBRATOR
            logger.info("  -> LEVEL CALIBRATOR...")
            level_result = audit_level_calibrator(client, task)
            task_result["audits"].append(level_result)
            time.sleep(1.0)

            # 5) DUPLICATE JUDGE
            logger.info("  -> DUPLICATE JUDGE...")
            cell_tasks = cell_lookup.get(cell_key, [])
            dup_result = audit_duplicate_judge(client, task, cell_tasks)
            task_result["audits"].append(dup_result)
            time.sleep(1.0)

            # Save result
            results.append(task_result)
            completed_ids.add(task_id)

            # Save checkpoint every 3 tasks
            if len(completed_ids) % 3 == 0:
                save_checkpoint(list(completed_ids), results)

            # Log summary
            ok_count = sum(1 for a in task_result["audits"] if a["status"] == "ok")
            logger.info("  [OK] %d/%d roles OK for task %s", ok_count, 5, task_id)

        # Save checkpoint after each phase
        save_checkpoint(list(completed_ids), results)

    # Final save
    logger.info("Saving final results to %s", AUDIT_RESULTS_PATH)
    with open(AUDIT_RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # Generate summary report
    generate_report(results, phase1, phase2)
    logger.info("[OK] Stage 3 audit complete. %d tasks audited.", len(results))


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------
def generate_report(results: List[Dict], phase1: List[Dict], phase2: List[Dict]):
    total = len(results)
    phase1_audited = sum(1 for r in results if "Phase 1" in r.get("phase", ""))
    phase2_audited = sum(1 for r in results if "Phase 2" in r.get("phase", ""))

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("=" * 70 + "\n")
        f.write("  STAGE 3: MULTI-ROLE AUDIT REPORT\n")
        f.write("=" * 70 + "\n\n")

        f.write(f"  Total tasks audited: {total}\n")
        f.write(f"  Phase 1 (quality < 60):  {phase1_audited} / {len(phase1)} audited\n")
        f.write(f"  Phase 2 (quality 60-70): {phase2_audited} / {len(phase2)} audited\n\n")

        # Role success stats
        role_stats = {"SOLVER": 0, "ARBITER": 0, "TOPIC_CLASSIFIER": 0, "LEVEL_CALIBRATOR": 0, "DUPLICATE_JUDGE": 0}
        for r in results:
            for a in r.get("audits", []):
                role = a.get("role", "")
                if a["status"] == "ok" and role in role_stats:
                    role_stats[role] += 1

        f.write("  Role success rates:\n")
        for role, count in role_stats.items():
            pct = round(100 * count / max(total, 1), 1)
            f.write(f"    {role:<20s}: {count}/{total} ({pct}%)\n")

        f.write("\n  Per-task summary:\n")
        f.write("  " + "-" * 60 + "\n")
        for r in results:
            task_id = r.get("task_id", "?")
            quality = r.get("quality_score", 0)
            cell_key = r.get("cell_key", "")
            ok_count = sum(1 for a in r["audits"] if a["status"] == "ok")
            f.write(f"  {task_id[:12]:12s} | cell={cell_key:<20s} | Q={quality:5.1f} | roles OK={ok_count}/5\n")

        f.write("\n" + "=" * 70 + "\n")
        f.write("  END OF REPORT\n")
        f.write("=" * 70 + "\n")

    logger.info("Report saved to %s", REPORT_PATH)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    run_audit()
