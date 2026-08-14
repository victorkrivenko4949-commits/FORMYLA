# -*- coding: utf-8 -*-
"""
ROBUST FULL GENERATION v2 -- NO app.py, NO APScheduler, direct HTTP
===================================================================
660 batches x (5+10+10+10+10) = 5,940 tasks
- Direct httpx calls with 120s timeout per request
- No app.py import (avoids APScheduler cron jobs)
- Sqlite3 directly for DB cleanup
- 10 parallel generate + 10 parallel audit + fix loop
- JSONL output + checkpoint + heartbeat
"""
import sys
import os
import time
import json
import asyncio
import signal
import traceback
import threading
import sqlite3
import httpx
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# -- Setup --
WORKSPACE = Path(__file__).resolve().parent
os.chdir(str(WORKSPACE))
sys.path.insert(0, str(WORKSPACE))

OUTPUT_FILE = WORKSPACE / '_all_tasks.jsonl'
CHECKPOINT_FILE = WORKSPACE / '_gen_checkpoint.json'
HEARTBEAT_FILE = WORKSPACE / '_gen_heartbeat.txt'
PID_FILE = WORKSPACE / '_gen_pid.txt'

# -- Config --
DEEPSEEK_API_KEY = "sk-87c7e276289a48269afe7d91d08d3f38"
DEEPSEEK_BASE = "https://api.deepseek.com/v1"
DEEPSEEK_MODEL = "deepseek-v4-pro"
HTTP_TIMEOUT = httpx.Timeout(60.0, read=120.0, write=30.0, connect=15.0)
MAX_RETRIES = 10
MAX_AUDIT_ITERATIONS = 3
PARALLEL_WORKERS = 10
SEMAPHORE_LIMIT = 10  # Rate limit: max 10 concurrent API calls (stress test passed at 20)

# -- Heartbeat --
_heartbeat_msg = "starting"
_heartbeat_lock = threading.Lock()
_heartbeat_stop = threading.Event()

PID_FILE.write_text(str(os.getpid()), encoding='utf-8')
print(f"PID: {os.getpid()}", flush=True)


def _write_heartbeat():
    while not _heartbeat_stop.wait(30):
        with _heartbeat_lock:
            msg = _heartbeat_msg
        ts = time.strftime('%Y-%m-%d %H:%M:%S')
        HEARTBEAT_FILE.write_text(
            f"[{ts}] PID={os.getpid()} | {msg}", encoding='utf-8')


_heartbeat_thread = threading.Thread(target=_write_heartbeat, daemon=True)
_heartbeat_thread.start()


def pulse(msg: str = ""):
    global _heartbeat_msg
    with _heartbeat_lock:
        _heartbeat_msg = msg


# -- THEMES --
THEMES_BY_GRADE = {
    5: [
        "Числа, цифры и арифметические конструкции",
        "Делимость, остатки и чётность", "Числовые ребусы",
        "Задачи на движение", "Работа, части и отношения",
        "Время, возраст и календарь", "Логические задачи",
        "Взвешивания и переливания", "Процессы и алгоритмы",
        "Оценка и построение примера", "Перебор и подсчёт вариантов",
        "Принцип Дирихле", "Графы, знакомства и маршруты",
        "Математические игры и стратегии", "Инварианты и раскраски",
        "Длины, периметры и площади", "Разрезания, складывания и замощения",
        "Клетчатая геометрия и конструкции",
    ],
    6: [
        "Делимость, остатки и чётность",
        "Простые числа, делители, НОД и НОК", "Цифры и числовые ребусы",
        "Задачи на движение", "Работа и производительность",
        "Части, отношения и пропорции", "Проценты, смеси и концентрации",
        "Логические задачи", "Взвешивания и переливания",
        "Процессы, алгоритмы и конструкции", "Оценка и построение примера",
        "Комбинаторный подсчёт", "Принцип Дирихле",
        "Графы, знакомства и маршруты", "Математические игры и стратегии",
        "Инварианты и раскраски", "Углы и простые конфигурации",
        "Длины, отношения и площади", "Разрезания, покрытия и замощения",
        "Клетчатая геометрия и конструкции",
    ],
    7: [
        "Делимость и сравнения по модулю",
        "Простые числа, делители, НОД и НОК", "Цифры и системы счисления",
        "Уравнения в целых числах", "Задачи на движение",
        "Работа, смеси и отношения", "Алгебраические преобразования и уравнения",
        "Неравенства и оценки", "Последовательности и числовые закономерности",
        "Комбинаторный подсчёт", "Принцип Дирихле и двойной подсчёт",
        "Графы и турниры", "Математические игры и стратегии",
        "Инварианты и раскраски", "Процессы, алгоритмы и конструкции",
        "Углы и геометрические конфигурации", "Отрезки, отношения и площади",
        "Дополнительные построения и преобразования",
        "Разрезания, покрытия и клетчатая геометрия",
    ],
    8: [
        "Делимость и сравнения по модулю", "Простые числа и разложения",
        "Цифры и системы счисления", "Диофантовы уравнения",
        "Алгебраические тождества и многочлены", "Уравнения и системы",
        "Неравенства и экстремальные оценки",
        "Последовательности и рекуррентные процессы", "Задачи на движение",
        "Комбинаторный подсчёт", "Принцип Дирихле и двойной подсчёт",
        "Графы и турниры", "Математические игры и стратегии",
        "Инварианты и раскраски", "Процессы, алгоритмы и конструкции",
        "Углы и вписанные конфигурации", "Отрезки, отношения и площади",
        "Дополнительные построения и преобразования",
        "Разрезания, покрытия и клетчатая геометрия",
    ],
    9: [
        "Делимость и сравнения по модулю", "Простые числа и разложения",
        "Диофантовы уравнения", "Цифры и системы счисления",
        "Многочлены и алгебраические тождества",
        "Алгебраические уравнения и системы",
        "Неравенства и экстремальные оценки", "Функциональные уравнения",
        "Последовательности и рекуррентности", "Комбинаторный подсчёт",
        "Принцип Дирихле и двойной подсчёт", "Графы и турниры",
        "Математические игры и стратегии", "Инварианты и раскраски",
        "Процессы, алгоритмы и конструкции", "Углы и вписанные конфигурации",
        "Отрезки, отношения и площади", "Дополнительные построения и преобразования",
    ],
    10: [
        "Простые числа и разложения", "Делимость и сравнения по модулю",
        "Диофантовы уравнения", "Арифметические конструкции",
        "Многочлены и алгебраические конструкции",
        "Алгебраические уравнения и системы",
        "Неравенства и экстремальные оценки", "Функциональные уравнения",
        "Последовательности и рекуррентности", "Комбинаторный подсчёт",
        "Принцип Дирихле и двойной подсчёт", "Графы и турниры",
        "Математические игры и стратегии", "Инварианты и раскраски",
        "Процессы, алгоритмы и конструкции", "Углы и вписанные конфигурации",
        "Отрезки, отношения и площади", "Дополнительные построения и преобразования",
    ],
    11: [
        "Функциональные уравнения", "Делимость и сравнения по модулю",
        "Простые числа и арифметические функции", "Диофантовы уравнения",
        "Арифметические конструкции", "Многочлены и алгебраические конструкции",
        "Алгебраические уравнения и системы",
        "Неравенства и экстремальные задачи",
        "Последовательности, рекуррентности и пределы",
        "Тригонометрические и аналитические конструкции",
        "Комбинаторный подсчёт", "Двойной подсчёт и экстремальный принцип",
        "Графы и экстремальная комбинаторика",
        "Математические игры и стратегии", "Инварианты и раскраски",
        "Процессы, алгоритмы и конструкции", "Углы и вписанные конфигурации",
        "Отрезки, отношения и площади", "Дополнительные построения и преобразования",
        "Пространственные конфигурации",
    ],
}

LEVELS = [1, 2, 3]  # Levels 1-3 here (level 4 in separate script)
CYCLE_COUNT = 5
TASKS_PER_LEVEL = {1: 5, 2: 10, 3: 10, 4: 10}  # 5+10+10+10=35


# -- Prompt loading --
def load_generate_prompt() -> str:
    p = WORKSPACE / 'daily_tasks' / 'pipeline' / 'prompts' / 'opus_generate.md'
    return p.read_text(encoding='utf-8')


def load_audit_prompt() -> str:
    p = WORKSPACE / 'daily_tasks' / 'pipeline' / 'prompts' / 'gpt_audit.md'
    return p.read_text(encoding='utf-8')


def build_work_queue():
    """132 topics x 3 levels x 5 cycles = 1980 batches (L1-L3 only)."""
    queue = []
    for cycle in range(1, CYCLE_COUNT + 1):
        for grade in sorted(THEMES_BY_GRADE):
            for topic in THEMES_BY_GRADE[grade]:
                for level in LEVELS:
                    queue.append({
                        'grade': grade, 'topic': topic, 'level': level,
                        'num_tasks': TASKS_PER_LEVEL[level], 'done': False,
                        'cycle': cycle,
                    })
    return queue


def make_specs(topic: str, level: int, count: int) -> List[Dict]:
    return [{
        'position': i + 1, 'difficulty_level': level,
        'topic': topic, 'subtopic': topic, 'subject': 'math',
        'slot_kind': 'calibration', 'target_level': level,
    } for i in range(count)]


def load_checkpoint():
    try:
        if CHECKPOINT_FILE.exists():
            return json.loads(CHECKPOINT_FILE.read_text(encoding='utf-8'))
    except Exception:
        pass
    return None


def save_checkpoint(queue):
    try:
        cp = [{
            'grade': w['grade'], 'topic': w['topic'], 'level': w['level'],
            'cycle': w.get('cycle', 0), 'done': w.get('done', False),
        } for w in queue]
        CHECKPOINT_FILE.write_text(json.dumps(cp, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception as e:
        print(f"  CHECKPOINT SAVE ERROR: {e}", flush=True)


def clean_database():
    DB_PATH = WORKSPACE / 'instance' / 'formyla.db'
    if not DB_PATH.exists():
        DB_PATH = WORKSPACE / 'formyla.db'
    if not DB_PATH.exists():
        print("  No database found, skipping cleanup", flush=True)
        return
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    tables = ['daily_task_items', 'daily_task_sets', 'daily_generation_jobs', 'task_pool', 'gen_conveyor']
    for t in tables:
        try:
            cur.execute(f"DELETE FROM {t}")
            print(f"  OK {t}: removed {cur.rowcount} records", flush=True)
        except Exception:
            print(f"  SKIP {t}: no such table", flush=True)
    conn.commit()
    conn.close()
    print("  DB cleaned.", flush=True)


# -- Semaphore --
_g_sem: Optional[asyncio.Semaphore] = None


def _get_sem() -> asyncio.Semaphore:
    global _g_sem
    if _g_sem is None:
        _g_sem = asyncio.Semaphore(SEMAPHORE_LIMIT)
    return _g_sem


async def ds_chat(messages: List[Dict], temperature: float = 0.7,
                  max_tokens: int = 16000,
                  response_format: Optional[Dict] = None) -> Tuple[str, int, int]:
    """Call DeepSeek API. Returns (text, input_tokens, output_tokens)."""
    async with _get_sem():
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    body = {
                        "model": DEEPSEEK_MODEL,
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    }
                    if response_format:
                        body["response_format"] = response_format
                    resp = await client.post(
                        f"{DEEPSEEK_BASE}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                            "Content-Type": "application/json",
                        },
                        json=body,
                    )
                    if resp.status_code == 429:
                        wait = min(2 ** attempt, 60)
                        await asyncio.sleep(wait)
                        continue
                    if resp.status_code != 200:
                        await asyncio.sleep(2)
                        continue
                    data = resp.json()
                    text = data['choices'][0]['message']['content'] or ''
                    in_tok = data.get('usage', {}).get('prompt_tokens', 0)
                    out_tok = data.get('usage', {}).get('completion_tokens', 0)
                    return text, in_tok, out_tok
                except Exception:
                    if attempt < MAX_RETRIES:
                        await asyncio.sleep(2 * attempt)
                    else:
                        return "", 0, 0
            return "", 0, 0


def _extract_json(text: str) -> Optional[Dict]:
    """Extract JSON from LLM response, handling markdown fences."""
    import re
    m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    m = re.search(r'\{.*\}', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return None


async def generate_one_task(spec: Dict, idx: int) -> Tuple[int, Dict, int, int]:
    prompt_text = load_generate_prompt()
    user_msg = json.dumps(spec, ensure_ascii=False)
    messages = [
        {"role": "system", "content": prompt_text},
        {"role": "user", "content": user_msg},
    ]
    total_in = 0
    total_out = 0
    for attempt in range(1, MAX_RETRIES + 1):
        text, in_tok, out_tok = await ds_chat(messages, temperature=0.7)
        total_in += in_tok
        total_out += out_tok
        parsed = _extract_json(text)
        # Handle both {"task_text": ...} and {"tasks": [{"task_text": ...}]}
        task = parsed
        if parsed and isinstance(parsed, dict):
            if 'tasks' in parsed and isinstance(parsed['tasks'], list) and parsed['tasks']:
                task = parsed['tasks'][0]
            if task.get('task_text', '').strip():
                return idx, task, total_in, total_out
        await asyncio.sleep(1)
    return idx, {'_failed': True}, total_in, total_out


async def generate_batch(specs: List[Dict]) -> Tuple[List[Dict], int, int]:
    tasks = [None] * len(specs)
    total_in = 0
    total_out = 0

    async def worker(i, spec):
        nonlocal total_in, total_out
        idx, task, in_tok, out_tok = await generate_one_task(spec, i)
        tasks[idx] = task
        total_in += in_tok
        total_out += out_tok

    await asyncio.gather(*[worker(i, s) for i, s in enumerate(specs)])
    # Fill any None slots
    for i in range(len(tasks)):
        if tasks[i] is None:
            tasks[i] = {"position": specs[i]["position"],
                        "task_text": "", "correct_answer": "", "_failed": True}
    return tasks, total_in, total_out


# -- Audit --
_audit_prompt_cache = None


async def audit_batch(specs: List[Dict], tasks: List[Dict],
                      max_retries: int = 5) -> List[Dict]:
    """Audit all tasks. Returns audit entries."""
    global _audit_prompt_cache
    if _audit_prompt_cache is None:
        _audit_prompt_cache = load_audit_prompt()

    items = [{"position": s["position"], "spec": s, "task": t}
             for s, t in zip(specs, tasks)]

    prompt = _audit_prompt_cache
    placeholder = '{ "items": [{"position": N, "spec": {...}, "task": {...}}, ...] }'
    items_json = json.dumps({"items": items}, ensure_ascii=False, indent=2)
    if placeholder in prompt:
        formatted = prompt.replace(placeholder, items_json)
    else:
        formatted = prompt + "\n\n" + items_json

    messages = [
        {"role": "system",
         "content": "Output ONLY valid JSON: {\"audit\":[...]}. No markdown."},
        {"role": "user", "content": formatted},
    ]

    for attempt in range(max_retries):
        try:
            raw, _, _ = await ds_chat(
                messages, temperature=0.2, max_tokens=6144,
                response_format={"type": "json_object"},
            )
            parsed = _extract_json(raw)
            if parsed and "audit" in parsed:
                entries = parsed["audit"]
                if isinstance(entries, list) and len(entries) == len(tasks):
                    return entries
            print(f"    WARN audit: {len(parsed.get('audit',[])) if parsed else 0} "
                  f"entries (attempt {attempt+1})", flush=True)
        except Exception as e:
            print(f"    WARN audit error (attempt {attempt+1}): {str(e)[:100]}",
                  flush=True)

        if attempt < max_retries - 1:
            await asyncio.sleep(5 * (attempt + 1))

    return []


async def fix_one_task(spec: Dict, task: Dict, audit_entry: Dict,
                       idx: int) -> Optional[Tuple[int, Dict]]:
    prompt_text = load_generate_prompt()
    user_msg = json.dumps({
        'original_spec': spec,
        'current_task': task,
        'audit_feedback': audit_entry,
    }, ensure_ascii=False)
    messages = [
        {"role": "system", "content": prompt_text},
        {"role": "user", "content": user_msg},
    ]
    for attempt in range(1, MAX_RETRIES + 1):
        text, _, _ = await ds_chat(messages, temperature=0.5)
        parsed = _extract_json(text)
        if parsed and parsed.get('task_text', '').strip():
            return idx, parsed
        await asyncio.sleep(1)
    return None


async def generate_with_audit(specs: List[Dict], grade: int, topic: str,
                              level: int) -> List[Dict]:
    """Full pipeline for one batch. Returns final tasks."""
    # Step 1: Generate
    tasks, in_tok, out_tok = await generate_batch(specs)
    valid_first = sum(1 for t in tasks if t.get("task_text", "").strip() and not t.get("_failed"))
    print(f"    generated {valid_first}/{len(tasks)} valid, "
          f"tokens: {in_tok}in/{out_tok}out", flush=True)

    # SKIP audit for L1 (probe tasks)
    if level == 1:
        print(f"    audit skipped (L1)", flush=True)
        return tasks

    # Step 2: Audit + fix loop
    for iteration in range(1, MAX_AUDIT_ITERATIONS + 1):
        audit_entries = await audit_batch(specs, tasks)

        to_fix = []
        for i, ae in enumerate(audit_entries):
            if ae.get("verdict") != "approved":
                to_fix.append((i, specs[i], tasks[i], ae))

        if not to_fix:
            print(f"    all approved (iter {iteration})", flush=True)
            break

        n_approved = len(tasks) - len(to_fix)
        print(f"    iter {iteration}: {n_approved} approved, "
              f"{len(to_fix)} needs_fix", flush=True)

        if iteration >= MAX_AUDIT_ITERATIONS:
            print(f"    iteration limit reached", flush=True)
            break

        # Fix in parallel
        fix_results = await asyncio.gather(
            *[fix_one_task(s, t, ae, idx) for idx, s, t, ae in to_fix],
            return_exceptions=True,
        )
        for r in fix_results:
            if isinstance(r, Exception):
                continue
            idx, fixed = r
            tasks[idx] = fixed

        await asyncio.sleep(2)

    return tasks


# -- Main --
async def main_worker():
    queue = build_work_queue()
    total_jobs = len(queue)
    total_tasks = sum(w['num_tasks'] for w in queue)

    cp = load_checkpoint()
    if cp:
        done = sum(1 for c in cp if c.get('done'))
        print(f"Checkpoint: {done}/{total_jobs} done", flush=True)
        # Match by key, not index (handles queue length changes)
        cp_map = {(c['grade'], c['topic'], c['level']): c.get('done', False) for c in cp}
        for w in queue:
            key = (w['grade'], w['topic'], w['level'])
            if cp_map.get(key):
                w['done'] = True

    remaining = sum(1 for w in queue if not w['done'])
    remaining_tasks = sum(w['num_tasks'] for w in queue if not w['done'])
    print(f"\n{'='*70}")
    print(f"  TOTAL: {total_jobs} batches, {total_tasks} tasks")
    print(f"  LEFT: {remaining} batches, {remaining_tasks} tasks")
    print(f"  L1: no audit | L2+L3: audit")
    print(f"  KEY: {DEEPSEEK_API_KEY[:20]}...")
    print(f"  MODEL: {DEEPSEEK_MODEL}")
    print(f"{'='*70}\n")

    with open(OUTPUT_FILE, 'a', encoding='utf-8') as outf:
        done_count = sum(1 for w in queue if w['done'])
        generated = 0
        start_time = time.monotonic()

        for idx, job in enumerate(queue):
            if job['done']:
                continue

            g, topic, lv, num = job['grade'], job['topic'], job['level'], job['num_tasks']
            label = f"G{g} L{lv} | {topic[:50]}"
            pulse(f"[{idx+1}/{total_jobs}] {label}")

            print(f"\n[{idx+1}/{total_jobs}] {label} ({num} tasks)", flush=True)
            t0 = time.monotonic()

            specs = make_specs(topic, lv, num)

            try:
                tasks = await generate_with_audit(specs, g, topic, lv)
            except Exception:
                tb = traceback.format_exc()[:300]
                print(f"  CRASH: {tb}", flush=True)
                job['done'] = True
                save_checkpoint(queue)
                continue

            dt = time.monotonic() - t0
            ts = time.strftime('%Y-%m-%d %H:%M:%S')

            for j, task in enumerate(tasks):
                entry = {
                    'grade': g, 'topic': topic, 'level': lv,
                    'position': j + 1,
                    'task_text': task.get('task_text', ''),
                    'correct_answer': task.get('correct_answer', ''),
                    'failed': task.get('_failed', False),
                    'generated_at': ts,
                }
                outf.write(json.dumps(entry, ensure_ascii=False) + '\n')
                outf.flush()
                generated += 1

            valid = sum(1 for t in tasks
                        if t.get('task_text', '').strip() and not t.get('_failed'))
            job['done'] = True
            done_count += 1

            elapsed = time.monotonic() - start_time
            avg = elapsed / max(done_count, 1)
            eta = avg * (total_jobs - done_count)
            pct = done_count * 100 // total_jobs

            msg = (f"  OK {valid}/{num} valid, {dt:.0f}s | "
                   f"{done_count}/{total_jobs} ({pct}%) | "
                   f"ETA: {eta/60:.0f}min | saved: {generated}")
            print(msg, flush=True)
            pulse(msg)

            if (idx + 1) % 5 == 0:
                save_checkpoint(queue)

    elapsed = time.monotonic() - start_time
    print(f"\n{'='*70}")
    print(f"  DONE! {generated} tasks, {elapsed/60:.0f} min")
    print(f"  File: {OUTPUT_FILE}")
    print(f"{'='*70}")
    pulse(f"DONE -- {generated} tasks in {elapsed/60:.0f} min")
    save_checkpoint(queue)


def on_signal(signum, frame):
    print(f"\nSignal {signum}, saving...", flush=True)
    _heartbeat_stop.set()
    sys.exit(0)


signal.signal(signal.SIGINT, on_signal)
signal.signal(signal.SIGTERM, on_signal)

if __name__ == '__main__':
    print("=" * 70)
    print("  FORMYLA v2 -- direct API, no Flask")
    print("=" * 70)

    print("\n  -- DB Cleanup --")
    clean_database()

    print("\n  -- Starting --")
    asyncio.run(main_worker())

    _heartbeat_stop.set()
    print("\nDone.", flush=True)
