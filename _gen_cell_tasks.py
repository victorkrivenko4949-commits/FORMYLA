#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ГЕНЕРАЦИЯ задач для конкретных ячеек курса ВсОШ.
Скрипт обходит VserossCourseEntry и для каждой ячейки (grade, stage, method_code)
проверяет наличие задач в MethodTask. Если задач недостаточно — генерирует новые
через DeepSeek API и сохраняет напрямую в БД.

Стратегия:
1. Группирует ячейки по (method_code, grade) — если метод встречается в нескольких
   этапах одного класса, генерируем общие задачи для этого метода/класса.
2. Каждая задача получает stage из первого подходящего этапа (или NULL).
3. Задачи сохраняются с ID = {grade}-{method_code}-{n}.
4. Цель: 25 задач на (method_code, grade).
"""

import json
import logging
import os
import sqlite3
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# Fix Windows console encoding
if sys.platform == 'win32':
    import codecs
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'replace')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'replace')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
)
logger = logging.getLogger('gen_cell_tasks')

# ─── Import DeepSeekClient from gen_678 ────────────────────────────────
from _gen_678 import DeepSeekClient, DeepSeekAPIError

# ─── Config ─────────────────────────────────────────────────────────────
DB_PATH = "instance/formyla.db"
TARGET_TASKS_PER_COMBO = 25  # Сколько задач генерировать на (method_code, grade)
MAX_RETRIES_PER_TASK = 3     # Сколько раз пробовать генерацию одной задачи
CHECKPOINT_PATH = "gen_cells_checkpoint.json"

# ─── Database helpers ───────────────────────────────────────────────────

def get_db() -> sqlite3.Connection:
    """Open connection to formyla.db with UTF-8 text factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.text_factory = lambda x: x.decode('utf-8', errors='replace')
    return conn


def get_cell_combos(conn: sqlite3.Connection, grade_filter: Optional[int] = None) -> List[dict]:
    """
    Get all (method_code, grade) combos from VserossCourseEntry.
    Returns list of dicts with: method_code, grade, method_name, section, first_stage, cell_count
    """
    query = """
        SELECT
            v.method_code,
            v.grade,
            v.method_name,
            v.section,
            MIN(v.stage) as first_stage,
            COUNT(*) as cell_count
        FROM vsosh_course_entries v
        {grade_where}
        GROUP BY v.method_code, v.grade
        ORDER BY v.grade, v.method_code
    """
    grade_where = ""
    params = ()
    if grade_filter is not None:
        grade_where = "WHERE v.grade = ?"
        params = (grade_filter,)

    c = conn.cursor()
    c.execute(query.format(grade_where=grade_where), params)
    rows = c.fetchall()

    combos = []
    for r in rows:
        combos.append({
            'method_code': r[0],
            'grade': r[1],
            'method_name': r[2] or '',
            'section': r[3] or '',
            'first_stage': r[4] or '',
            'cell_count': r[5],
        })
    return combos


def get_existing_task_count(conn: sqlite3.Connection, method_code: str, grade: int) -> int:
    """How many MethodTask rows exist for this (method_code, grade)."""
    c = conn.cursor()
    c.execute(
        "SELECT COUNT(*) FROM method_tasks WHERE method_code = ? AND grade = ?",
        (method_code, grade)
    )
    return c.fetchone()[0]


def get_max_task_number(conn: sqlite3.Connection, method_code: str, grade: int) -> int:
    """Get the highest numeric task number suffix for this combo.

    Uses Python-side extraction (rsplit on '-') to avoid SQLite
    lexicographic sort issues (e.g. '9' > '20' as strings).
    SQLite has no REVERSE() function, so we do the parsing in Python.
    """
    c = conn.cursor()
    c.execute(
        "SELECT id FROM method_tasks WHERE method_code = ? AND grade = ?",
        (method_code, grade)
    )
    rows = c.fetchall()
    if not rows:
        return 0
    max_n = 0
    for (task_id,) in rows:
        try:
            n = int(task_id.rsplit('-', 1)[1])
            if n > max_n:
                max_n = n
        except (ValueError, IndexError):
            continue
    return max_n


def save_task(conn: sqlite3.Connection, task: dict) -> bool:
    """
    Save one task to method_tasks table.
    task dict keys: id, grade, method_code, method_name, section, stage,
                    text, answer, solution_idea, difficulty, difficulty_label,
                    difficulty_color, task_type, olympiad, subject
    Returns True if saved, False if duplicate or error.
    """
    try:
        cur = conn.execute("""
            INSERT OR IGNORE INTO method_tasks
                (id, grade, method_code, method_name, section, stage,
                 text, answer, solution_idea, difficulty, difficulty_label,
                 difficulty_color, task_type, olympiad, subject, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            task['id'], task['grade'], task['method_code'],
            task.get('method_name', ''), task.get('section', ''),
            task.get('stage', ''),
            task['text'], task.get('answer', ''),
            task.get('solution_idea', ''),
            task.get('difficulty'),
            task.get('difficulty_label', ''),
            task.get('difficulty_color', ''),
            task.get('task_type', ''),
            task.get('olympiad', 'VsOSh'),
            task.get('subject', 'math'),
            datetime.now(timezone.utc).isoformat(),
        ))
        conn.commit()
        # rowcount is 0 when INSERT OR IGNORE skips a duplicate
        if cur.rowcount == 0:
            logger.warning(f"  DUPLICATE (rowcount=0): {task['id']} already exists")
            return False
        return True
    except Exception as e:
        conn.rollback()
        logger.error(f"DB save error for {task['id']}: {e}")
        return False


# ─── DeepSeek task generation ───────────────────────────────────────────

def build_cell_generation_prompt(method_name: str, method_code: str,
                                  section: str, grade: int) -> str:
    """
    Build a prompt for generating a single task for a specific method/cell.
    """
    topic_instruction = ""
    if method_name:
        topic_instruction = (
            f"\n\nСОЗДАЙ ЗАДАЧУ ПО ТЕМЕ: «{method_name}»."
            f"\nКод метода: {method_code}. Раздел: {section}."
            f"\nЗадача должна быть для {grade} класса."
        )
    elif section:
        topic_instruction = (
            f"\n\nСОЗДАЙ ЗАДАЧУ ПО РАЗДЕЛУ: «{section}»."
            f"\nДля {grade} класса."
        )

    # --- Grade-adaptive difficulty anchors ---
    if grade <= 6:
        difficulty_anchor = (
            "L6=сложная школьная олимпиада / муниципальный этап, "
            "L7=очень сложная (уровень Матпраздника), "
            "L8=самые сложные задачи Матпраздника"
        )
        class_range = "5-6"
        math_constraints = (
            "\n5. ЗАПРЕЩЕНЫ: векторы, производные, интегралы, тригонометрия, "
            "системы уравнений с 3+ переменными, отрицательные числа.\n"
            "6. Допустимы: натуральные числа, дроби, простые уравнения, "
            "логические рассуждения, геометрия (без тригонометрии).\n"
            "7. Решение — не более 4-5 шагов, без громоздких выкладок."
        )
    elif grade <= 8:
        difficulty_anchor = (
            "L6=муниципальный этап ВсОШ, "
            "L7=региональный этап ВсОШ (средняя сложность), "
            "L8=самые сложные задачи регионального этапа"
        )
        class_range = "7-8"
        math_constraints = (
            "\n5. Допустимы: квадратные уравнения, системы уравнений, "
            "степени, делимость, комбинаторика, геометрия.\n"
            "6. ЗАПРЕЩЕНЫ: производные, интегралы, тригонометрия, "
            "векторы, матрицы.\n"
            "7. Решение — не более 5-7 шагов."
        )
    else:
        difficulty_anchor = (
            "L6=регион задача №2, "
            "L7=сложный регион, "
            "L8=заключительный этап ВсОШ"
        )
        class_range = "9-11"
        math_constraints = (
            "\n5. Любые темы школьной олимпиадной математики (9-11 класс).\n"
            "6. Решение — развёрнутое, 5-10 шагов."
        )

    prompt = f"""Создай ОРИГИНАЛЬНУЮ олимпиадную задачу по математике уровня 6-8 (по 8-балльной шкале).{topic_instruction}

КРИТИЧЕСКИ ВАЖНО: задача ДОЛЖНА БЫТЬ ОРИГИНАЛЬНОЙ. Не копируй известные задачи из сборников!

ЗАПРЕЩЁННЫЕ ТИПЫ ЗАДАЧ:
1. Теорема Рамсея: "В стране N городов, каждые два соединены... найти одноцветный треугольник"
2. Интерполяция Лагранжа
3. Системы с модулями и корнями вида |x|+|y|+|z|=1
4. "n⁴+2n³+3n²+2n+2025 — точный квадрат" и подобные
5. Оценки для |f(x)|≤1, f(x)=x³+ax+b
6. "2^p-2 — точная степень" (числа Мерсенна)
7. "3^n+n^2 — полный квадрат"
8. Симметрия графика
9. Системы |x|+|y|+√(x²+y²)=4
10. Вписанная окружность, точки касания
11. Функциональное уравнение P(x)² = P(x²+2x)+2P(x)+1
12. "Сумма цифр" и "произведение цифр" в чистом виде
13. Классические задачи на раскраску графа
14. "Квадрат суммы цифр"
15. Поиск n при котором число — точный квадрат
16. Диофантовы x²+y²=z²
17. "Рыцари и лжецы" в стандартной формулировке
18. Инвариант "сумма/произведение чисел на доске"
19. "Шары в урне" и классическая вероятность
20. Среднее арифметическое/геометрическое в лоб
21. Задачи, где ответ "0" или "1" без содержательной проверки

ТРЕБОВАНИЯ К НОВОЙ ЗАДАЧЕ:
1. ОРИГИНАЛЬНАЯ — придумай НОВУЮ конструкцию или необычную комбинацию идей.
2. Уровень: 6-8 ({difficulty_anchor}).
3. Для классов {class_range}.
4. Изящное решение, не перебор.{math_constraints}
8. Чёткая формулировка, проверяемый ответ.

ОТВЕТ ДАЙ В ВИДЕ JSON:
{{
  "task_text": "Текст задачи с LaTeX ($$...$$ для формул)",
  "solution": "Полное решение с объяснениями (LaTeX, не менее 500 символов)",
  "correct_answer": "Краткий ответ",
  "class_level": {class_range},
  "topic": "Алгебра | Теория чисел | Комбинаторика | Геометрия | Логика",
  "difficulty_level": 6, 7 или 8,
  "key_method": "Ключевая идея",
  "idea_count": число (3-8)
}}"""
    return prompt


def extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Extract JSON from LLM response, handling code fences and extra text."""
    # Try to find ```json ... ``` block first
    import re
    json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if json_match:
        candidate = json_match.group(1).strip()
    else:
        candidate = text.strip()

    # Try to find outermost { ... }
    brace_start = candidate.find('{')
    brace_end = candidate.rfind('}')
    if brace_start >= 0 and brace_end > brace_start:
        candidate = candidate[brace_start:brace_end + 1]

    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None


def _call_with_timeout(client: DeepSeekClient, prompt: str, system_prompt: str, max_tokens: int, timeout: int) -> str:
    """Call DeepSeek API with a hard wall-clock timeout using ThreadPoolExecutor.
    
    This prevents hangs where requests.post() timeout doesn't trigger
    (e.g., TCP-level stalls). The executor gives us a hard kill after `timeout` seconds.
    """
    API_WALL_TIMEOUT = timeout + 30  # 30s buffer over the requests timeout
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(client.call, prompt, system_prompt=system_prompt, max_tokens=max_tokens, timeout=timeout)
        try:
            return future.result(timeout=API_WALL_TIMEOUT)
        except TimeoutError:
            raise TimeoutError(f"API call timed out after {API_WALL_TIMEOUT}s (hard wall-clock timeout)")


def generate_one_task(client: DeepSeekClient, combo: dict) -> Optional[dict]:
    """
    Generate a single task for the given combo via DeepSeek API.
    Returns dict ready for DB insertion, or None on failure.
    """
    method_name = combo['method_name']
    method_code = combo['method_code']
    section = combo['section']
    grade = combo['grade']
    first_stage = combo['first_stage']

    prompt = build_cell_generation_prompt(method_name, method_code, section, grade)

    system_prompt = (
        "Ты — генератор оригинальных задач по математике. "
        "Твои задачи используются в адаптивном тесте (уровни 6-8 по 8-балльной шкале). "
        "Для 9-11 классов задачи ориентированы на уровень ВсОШ, "
        "для 5-8 классов — на уровень Матпраздника и этапов ВсОШ. "
        "Каждая задача должна быть НОВОЙ, не скопированной из известных источников. "
        "Отвечай ТОЛЬКО в формате JSON, без лишнего текста."
    )

    for attempt in range(1, MAX_RETRIES_PER_TASK + 1):
        try:
            logger.info(f"  Generating task for {method_code} G{grade} (attempt {attempt})...")
            response = _call_with_timeout(client, prompt, system_prompt=system_prompt, max_tokens=16384, timeout=300)

            parsed = extract_json(response)
            if not parsed:
                logger.warning(f"  Failed to parse JSON response (attempt {attempt})")
                if attempt < MAX_RETRIES_PER_TASK:
                    time.sleep(3)
                continue

            task_text = parsed.get('task_text', '').strip()
            solution = parsed.get('solution', '').strip()
            correct_answer = parsed.get('correct_answer', '').strip()
            difficulty = parsed.get('difficulty_level', 6)

            if not task_text or not solution:
                logger.warning(f"  Empty task_text or solution (attempt {attempt})")
                if attempt < MAX_RETRIES_PER_TASK:
                    time.sleep(3)
                continue

            # Map difficulty to label/color
            diff_map = {
                6: ('L6', '#4CAF50'),
                7: ('L7', '#FF9800'),
                8: ('L8', '#F44336'),
            }
            dl, dc = diff_map.get(difficulty, ('L6', '#4CAF50'))

            # Determine task_type from topic
            topic = parsed.get('topic', '')
            task_type_map = {
                'Алгебра': 'algebra',
                'Теория чисел': 'number_theory',
                'Комбинаторика': 'combinatorics',
                'Геометрия': 'geometry',
                'Логика': 'logic',
            }
            task_type = task_type_map.get(topic, 'other')

            # Determine section from topic (fallback)
            section_map = {
                'Алгебра': 'A',
                'Теория чисел': 'D',
                'Комбинаторика': 'E',
                'Геометрия': 'F',
                'Логика': 'H',
            }
            derived_section = section_map.get(topic, section or 'A')

            return {
                'text': task_text,
                'answer': correct_answer,
                'solution_idea': solution,
                'difficulty': difficulty,
                'difficulty_label': dl,
                'difficulty_color': dc,
                'task_type': task_type,
                'section': derived_section,
                'method_code': method_code,
                'method_name': method_name,
                'grade': grade,
                'stage': first_stage,
                'olympiad': 'VsOSh',
                'subject': 'math',
            }

        except DeepSeekAPIError as e:
            if '402' in str(e):
                logger.error(f"  CREDIT EXHAUSTED (402). Stopping generation.")
                return None  # Signal to stop entirely
            logger.warning(f"  API error (attempt {attempt}): {e}")
            if attempt < MAX_RETRIES_PER_TASK:
                time.sleep(5 * attempt)
        except TimeoutError as e:
            logger.warning(f"  Wall-clock timeout (attempt {attempt}): {e}")
            if attempt < MAX_RETRIES_PER_TASK:
                time.sleep(5)
        except Exception as e:
            logger.warning(f"  Unexpected error (attempt {attempt}): {e}")
            if attempt < MAX_RETRIES_PER_TASK:
                time.sleep(5)

    logger.error(f"  All {MAX_RETRIES_PER_TASK} attempts failed for {method_code} G{grade}")
    return None


# ─── Checkpoint management ──────────────────────────────────────────────

def load_checkpoint() -> Optional[Dict[str, Any]]:
    """Load checkpoint from file."""
    if os.path.exists(CHECKPOINT_PATH):
        try:
            with open(CHECKPOINT_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load checkpoint: {e}")
    return None


def save_checkpoint(data: Dict[str, Any]):
    """Save checkpoint to file."""
    try:
        with open(CHECKPOINT_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"Checkpoint saved: {data.get('combo_index', '?')}/{data.get('total_combos', '?')}")
    except Exception as e:
        logger.warning(f"Failed to save checkpoint: {e}")


def clear_checkpoint():
    """Remove checkpoint file."""
    if os.path.exists(CHECKPOINT_PATH):
        os.remove(CHECKPOINT_PATH)
        logger.info("Checkpoint cleared.")


# ─── Main generation loop ───────────────────────────────────────────────

class TaskCounter:
    """Track generation statistics."""
    def __init__(self):
        self.generated = 0
        self.failed = 0
        self.skipped = 0
        self.errors = 0
        self.by_grade = {}  # grade -> count

    def add_generated(self, grade: int):
        self.generated += 1
        self.by_grade[grade] = self.by_grade.get(grade, 0) + 1

    def report(self) -> str:
        lines = [
            f"Generated: {self.generated}",
            f"Failed: {self.failed}",
            f"Skipped: {self.skipped}",
            f"Errors: {self.errors}",
        ]
        for grade in sorted(self.by_grade.keys()):
            lines.append(f"  Grade {grade}: {self.by_grade[grade]} tasks")
        return "\n".join(lines)


def process_combos(combos: List[dict], grade_filter: Optional[int] = None,
                   target: int = TARGET_TASKS_PER_COMBO) -> TaskCounter:
    """
    Main generation loop.
    For each combo, check existing tasks and generate missing ones.
    """
    client = DeepSeekClient()
    # Use deepseek-chat instead of deepseek-reasoner to avoid empty content issue.
    # deepseek-reasoner consumes tokens for reasoning and often leaves nothing for final content.
    client.MODEL = "deepseek-chat"
    counter = TaskCounter()
    conn = get_db()

    # Filter by grade if specified
    if grade_filter is not None:
        combos = [c for c in combos if c['grade'] == grade_filter]

    total_combos = len(combos)
    logger.info(f"Processing {total_combos} combos, target {target} tasks each")

    # Load checkpoint
    cp = load_checkpoint()
    start_index = cp.get('combo_index', 0) if cp else 0
    existing_state = cp.get('existing_counts', {}) if cp else {}

    for idx, combo in enumerate(combos):
        if idx < start_index:
            logger.info(f"Skipping combo {idx+1}/{total_combos} (already completed in checkpoint): "
                       f"{combo['method_code']} G{combo['grade']}")
            # Restore counts from checkpoint
            key = f"{combo['method_code']}_{combo['grade']}"
            counter.generated += existing_state.get(key, {}).get('generated', 0)
            counter.failed += existing_state.get(key, {}).get('failed', 0)
            continue

        mc = combo['method_code']
        gr = combo['grade']
        existing = get_existing_task_count(conn, mc, gr)
        max_n = get_max_task_number(conn, mc, gr)

        logger.info(f"[{idx+1}/{total_combos}] {mc} G{gr} — existing: {existing}/{target}, "
                   f"stages: {combo['cell_count']}, method: {combo['method_name'][:40]}")

        if existing >= target:
            logger.info(f"  Already has {existing} tasks, skipping")
            counter.skipped += 1
            continue

        needed = target - existing
        logger.info(f"  Need {needed} more tasks, starting from n={max_n + 1}")

        combo_generated = 0
        combo_failed = 0

        for n in range(1, needed + 1):
            task_num = max_n + n

            # Generate the task
            task_data = generate_one_task(client, combo)

            if task_data is None:
                # 402 error — stop everything
                logger.error("CREDITS EXHAUSTED. Stopping all generation.")
                combo_failed += 1
                counter.errors += 1
                break

            # Build task ID
            task_id = f"{gr}-{mc}-{task_num}"
            task_data['id'] = task_id

            # Save to database
            saved = save_task(conn, task_data)
            if saved:
                logger.info(f"  SAVED: {task_id}")
                combo_generated += 1
                counter.add_generated(gr)
            else:
                logger.warning(f"  DUPLICATE/FAILED: {task_id} (might already exist)")
                combo_failed += 1
                counter.failed += 1

            # Save checkpoint every task
            key = f"{mc}_{gr}"
            cp_data = {
                'combo_index': idx,
                'total_combos': total_combos,
                'existing_counts': {
                    key: {'generated': combo_generated, 'failed': combo_failed}
                },
                'last_task': task_id,
                'timestamp': datetime.now(timezone.utc).isoformat(),
            }
            save_checkpoint(cp_data)

        if combo_generated > 0:
            logger.info(f"  ✓ Combo {mc} G{gr}: generated {combo_generated}, failed {combo_failed}")

        # Brief pause between combos to avoid rate limiting
        time.sleep(2)

    conn.close()
    return counter


# ─── Entry point ────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Generate tasks for VserossCourseEntry cells")
    parser.add_argument('--grade', type=int, choices=[5, 6, 7, 8, 9, 10, 11], default=None,
                        help="Only process this grade (default: all grades)")
    parser.add_argument('--target', type=int, default=TARGET_TASKS_PER_COMBO,
                        help=f"Target tasks per (method_code, grade) combo (default: {TARGET_TASKS_PER_COMBO})")
    parser.add_argument('--reset', action='store_true',
                        help="Reset checkpoint and start from scratch")
    parser.add_argument('--dry-run', action='store_true',
                        help="Only show what would be done, don't generate")
    parser.add_argument('--report', action='store_true',
                        help="Only show gap analysis report, don't generate")

    args = parser.parse_args()

    if args.reset:
        clear_checkpoint()

    # Get all combos
    conn = get_db()
    combos = get_cell_combos(conn, grade_filter=args.grade)
    conn.close()

    if not combos:
        logger.error("No combos found. Check the database path.")
        sys.exit(1)

    # Show summary
    print(f"\n{'='*60}")
    print(f"  CELL TASK GENERATOR")
    print(f"{'='*60}")
    print(f"  Database: {DB_PATH}")
    print(f"  Total combos: {len(combos)}")
    if args.grade:
        print(f"  Filter: grade {args.grade}")
    print(f"  Target: {args.target} tasks per combo")
    print()

    # Count gaps
    conn = get_db()
    total_existing = 0
    total_needed = 0
    gaps = []
    for c in combos:
        exist = get_existing_task_count(conn, c['method_code'], c['grade'])
        total_existing += exist
        need = max(0, args.target - exist)
        if need > 0:
            total_needed += need
            gaps.append((c['grade'], c['method_code'], c['method_name'], exist, need, c['cell_count']))
    conn.close()

    print(f"  Existing tasks: {total_existing}")
    print(f"  Needed tasks:   {total_needed}")
    print(f"\n  {'Grade':<7} {'Code':<8} {'Method':<35} {'Have':<6} {'Need':<6} {'Cells':<6}")
    print(f"  {'-'*68}")
    for g, mc, mn, exist, need, cells in sorted(gaps):
        print(f"  G{g:<5} {mc:<8} {str(mn)[:33]:<35} {exist:<6} {need:<6} {cells:<6}")
    print(f"\n  Total gaps: {len(gaps)} combos, {total_needed} tasks needed")

    if args.report:
        print(f"\n{'='*60}")
        print("  REPORT ONLY — no generation")
        return

    if args.dry_run:
        print(f"\n  DRY RUN — no generation")
        return

    if total_needed == 0:
        print(f"\n  No gaps to fill! All combos have {args.target}+ tasks.")
        return

    # Ask for confirmation
    print(f"\n  Ready to generate {total_needed} tasks via DeepSeek API.")
    print(f"  This will call the API {total_needed} times.")
    print(f"  Press Ctrl+C to abort.")
    print()

    # Small delay to let user cancel
    try:
        for i in range(5, 0, -1):
            print(f"  Starting in {i}...", end='\r')
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n  Aborted by user.")
        return

    print("  Starting generation...\n")

    # Run generation
    counter = process_combos(combos, grade_filter=args.grade, target=args.target)

    # Final report
    print(f"\n{'='*60}")
    print(f"  GENERATION COMPLETE")
    print(f"{'='*60}")
    print(f"  {counter.report()}")

    # Clear checkpoint on success
    if counter.errors == 0 and counter.failed == 0:
        clear_checkpoint()
        print(f"\n  All tasks generated successfully!")
    else:
        print(f"\n  Some tasks failed. Checkpoint kept for resume.")


if __name__ == '__main__':
    main()
