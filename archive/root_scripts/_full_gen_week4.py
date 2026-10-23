import os
# -*- coding: utf-8 -*-
"""
FORMYLA — WEEK 4 GENERATOR (standalone, single file)
=====================================================
Generates week-4 tasks (level 4, 10 per topic, 5 cycles).
Skips already-done combos from _all_tasks.jsonl.
ALL PROMPTS EMBEDDED — no external files needed.

ALREADY DONE (in _all_tasks.jsonl): 36 (grade, topic) combos.

WHAT YOU NEED:
  pip install httpx
  python _full_gen_week4.py

OUTPUT:
  _all_tasks_week4.jsonl

MERGE:
  type _all_tasks.jsonl _all_tasks_week4.jsonl > _all_tasks_full.jsonl

TOTAL: 132 topics x 10 tasks x 5 cycles = 6600 tasks
       Minus 36 done combos x 5 cycles x 10 = 1800 done
       = ~4800 tasks to generate
"""

import sys, os, time, json, asyncio, signal, traceback, threading, sqlite3, httpx, re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Set

WORKSPACE = Path(__file__).resolve().parent
os.chdir(str(WORKSPACE))
sys.path.insert(0, str(WORKSPACE))

OUTPUT_FILE = WORKSPACE / '_all_tasks_week4.jsonl'
CHECKPOINT_FILE = WORKSPACE / '_gen_checkpoint_week4.json'
HEARTBEAT_FILE = WORKSPACE / '_gen_heartbeat_week4.txt'
PID_FILE = WORKSPACE / '_gen_pid_week4.txt'
EXISTING_JSONL = WORKSPACE / '_all_tasks.jsonl'

DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY', os.environ.get("DEEPSEEK_API_KEY", ""))
DEEPSEEK_BASE = "https://api.deepseek.com/v1"
DEEPSEEK_MODEL = "deepseek-v4-pro"
HTTP_TIMEOUT = httpx.Timeout(60.0, read=120.0, write=30.0, connect=15.0)
MAX_RETRIES = 10
MAX_AUDIT_ITERATIONS = 3
PARALLEL_WORKERS = 10
SEMAPHORE_LIMIT = 5

LEVEL = 4
TASKS_COUNT = 10
CYCLE_COUNT = 5

_heartbeat_msg = "starting"
_heartbeat_lock = threading.Lock()
_heartbeat_stop = threading.Event()
PID_FILE.write_text(str(os.getpid()), encoding='utf-8')
print(f"PID: {os.getpid()}", flush=True)

def _write_heartbeat():
    while not _heartbeat_stop.wait(30):
        with _heartbeat_lock: msg = _heartbeat_msg
        ts = time.strftime('%Y-%m-%d %H:%M:%S')
        HEARTBEAT_FILE.write_text(f"[{ts}] PID={os.getpid()} | {msg}", encoding='utf-8')
_heartbeat_thread = threading.Thread(target=_write_heartbeat, daemon=True); _heartbeat_thread.start()

def pulse(msg: str = ""):
    global _heartbeat_msg
    with _heartbeat_lock: _heartbeat_msg = msg

# ============== EMBEDDED PROMPTS ==============

GENERATE_PROMPT = r'''# Генератор «Задачи дня» — ТОЛЬКО УСЛОВИЕ И ОТВЕТ

Ты — генератор олимпиадных математических задач для школьников России.

На вход — одна или несколько «спек» (ТЗ от методиста). Для КАЖДОЙ спеки сгенерируй РОВНО ОДНУ задачу: только условие и правильный ответ. Решение и подсказки НЕ НУЖНЫ.

==============================================================
КРИТИЧЕСКИ ВАЖНО — ФОРМАТ ВЫХОДА:
==============================================================

1. ВЫХОД — ТОЛЬКО валидный JSON. Никаких ```json …```, никакого текста до или после.

2. Корневой ключ — РОВНО `"tasks"` (множественное число).

3. Каждая задача содержит ТОЛЬКО 3 поля:
   - `position` — целое число из spec.position.
   - `task_text` — условие задачи на русском языке.
   - `correct_answer` — короткий ответ (формат из spec.answer_form).

4. Если на входе N спек — на выходе РОВНО N задач, в том же порядке.

==============================================================
LATEX:
==============================================================

5. ВСЯ математика — ТОЛЬКО `$...$` (инлайн) и `$$...$$` (блок).
   - НЕЛЬЗЯ: `\\(...\\)`, `\\[...\\]`.
   - Команды: `\frac{a}{b}`, `\sqrt{x}`, `\cdot`, `\le`, `\ge`, `\ne`, `\in`, `\Rightarrow`, `\alpha`, `\beta`, `\sin`, `\cos`, `\log`.
   - Степени: `x^{10}`, `2^{n+1}`.
   - Скобки `{`, `}` сбалансированы.
   - ВАЖНО: задача должна быть КОРОТКОЙ — только условие + ответ. Не больше 500 слов.

==============================================================
СОДЕРЖАНИЕ:
==============================================================

6. Уровень сложности — строго из spec.difficulty_level (1..4):

   L1 — ПРОСТОЕ ДЕЙСТВИЕ (5 задач на тему):
   - Базовая арифметика, прямой подсчёт, простое применение одной формулы
   - НЕ тривиально: задача должна требовать хотя бы минимального осмысления
   - "3+6" — НЕЛЬЗЯ. "25 учеников, 12 мальчиков — сколько девочек?" — L1.

   L2 — ОДИН-ДВА СТАНДАРТНЫХ ПРИЁМА:
   - Известная формула + подстановка чисел
   - Простое уравнение с одним неизвестным
   - Разложение на простые множители
   - Стандартный подсчёт комбинаций (перестановки/сочетания по формуле)
   АНТИ-L2: если нужен нестандартный ход — это уже L3.

   L3 — ОДИН НЕШАБЛОННЫЙ ШАГ:
   - Типовой школьный этап ВсОШ (нешаблонный, но знакомый ход)
   - Разбиение на случаи, оценка + пример
   - Нестандартное применение известной теоремы
   АНТИ-L3: если задача шаблонная и не содержит неожиданности — это L2.

   L4 — НЕТРИВИАЛЬНАЯ ТВОРЧЕСКАЯ ОЛИМПИАДНАЯ ЗАДАЧА:
   - Муниципальный/региональный этап ВсОШ
   - Требуется ИЗОБРЕСТИ идею, которую НЕВОЗМОЖНО найти стандартным перебором методов
   - Неожиданный поворот или скрытая закономерность
   - 2-4 шага, требующих ТВОРЧЕСКОГО МЫШЛЕНИЯ
   - Задача должна быть ОЛИМПИАДНОЙ — не шаблонной, требующей изобретательности
   АНТИ-L4: если задача решается «в лоб» применением известного метода — это НЕ L4.

   Анти-завышение: название темы само по себе НЕ делает задачу сложной.
   L4 ОБЯЗАН иметь неожиданный поворот или скрытую идею.

7. Ответ ОДНОЗНАЧНЫЙ. Если множество — все элементы через запятую.

8. Задача ОБЯЗАНА соответствовать spec.subtopic. Не генери задачу на другую тему.

9. ЗАПРЕЩЕНЫ:
   - Тривиальные задачи (2+2, квадратное уравнение в лоб)
   - Задачи с противоречивым условием
   - Задачи, где ответ не следует из условия
   - Задачи, подогнанные под тему искусственно

10. ПРИНЦИПИАЛЬНО: проверь, что ответ следует из условия. Не пиши ответ который
    противоречит данным задачи. ОШИБКА В ОТВЕТЕ НЕДОПУСТИМА.

==============================================================
ВХОД И ВЫХОД:
==============================================================

{ "specs": [...] }

ТОЛЬКО JSON от первого до последнего символа.'''

AUDIT_PROMPT = r'''# Проверка условий задач (Quality Check — только условие)

Тебе дают набор пар `(spec, task)` — спецификация и сгенерированное условие задачи с ответом. Оцени корректность условия.

==============================================================
КРИТИЧЕСКИ ВАЖНО — ФОРМАТ ВЫХОДА:
==============================================================

1. Ответ — ТОЛЬКО валидный JSON-объект. Никакого markdown.

2. Корневой ключ — `"audit"` (массив).

3. На входе N items — на выходе РОВНО N entries.

4. Каждая entry содержит:
   - `position` — целое число из items[i].position.
   - `verdict` — `"approved"` или `"needs_fix"`.
   - `estimated_actual_level` — целое 2..4, твоя оценка реальной сложности условия.
   - `issues` — массив проблем (пустой `[]` если `"approved"`).

5. Каждая issue:
   - `code` — из списка ниже;
   - `severity` — `"low"`, `"medium"` или `"high"`;
   - `description` — 1-2 предложения;
   - `fix_instruction` — что конкретно переделать.

==============================================================
КАЛИБРОВКА L2..L4 (уровень 1 не используется):
==============================================================

- L2: ОДИН-ДВА СТАНДАРТНЫХ приёма, знакомых каждому школьнику.
  Но НЕ тривиально: задача должна требовать хотя бы минимального размышления.
  Если задача решается мгновенно в уме (например "3+6", "10-2") — это СЛИШКОМ ПРОСТО.
  АНТИ-L2: тривиальная задача без намёка на олимпиадность = needs_fix (trivial).

- L3: ОДИН нешаблонный шаг. Школьный этап ВсОШ.
  Если шаблонная задача без неожиданного поворота — это НЕ L3.
  АНТИ-L3: задача решается стандартным школьным алгоритмом = needs_fix (too_easy).

- L4: одна идея или короткая цепочка (2-3 шага). Муниципальный этап.
  Если не требует изобретательности — это НЕ L4.
  АНТИ-L4: если идея очевидна = needs_fix (too_easy).

Правило: |estimated_actual_level - spec.difficulty_level| <= 1 — ок. Иначе too_easy/too_hard.

ОСОБОЕ ВНИМАНИЕ:
- ВСЕ уровни: тривиальная задача (3+6, сколько будет 5*4 и т.п.) = needs_fix с кодом `trivial`. Такие задачи не должны попадать в банк никогда.
- L2 БАЗОВЫЙ ПОРОГ: задача должна требовать ХОТЯ БЫ ОДНОГО осмысленного шага. Не "посчитай 2+2", а "подумай и примени правило".
- ЛЮБОЙ уровень: если задача подогнана под тему искусственно — off_topic.

КРИТИЧЕСКИ ВАЖНО: ты ДОЛЖЕН проверять, что ответ МАТЕМАТИЧЕСКИ следует из условия! Подставь ответ обратно в условие и убедись, что он не противоречит данным.

ТЫ ДОЛЖЕН ПРОВЕРЯТЬ ЗАДАЧУ НА ПРОТИВОРЕЧИВОСТЬ:
- Может ли существовать объект с описанными свойствами?
- Достаточно ли данных для однозначного ответа?
- Нет ли в условии скрытого противоречия?

==============================================================
КОДЫ ОШИБОК:
==============================================================

- `too_easy` — задача легче заявленного на 2+ балла.
- `too_hard` — задача тяжелее на 2+ балла.
- `wrong_answer` — ответ НЕ следует из условия (проверь подстановкой!). HIGH severity.
- `impossible_task` — противоречивое или недоопределённое условие. HIGH severity.
- `spec_mismatch` — не та подтема.
- `off_topic` — задача не по теме из spec.
- `not_olympiad` — задача шаблонная/учебная, а не олимпиадная.
- `trivial` — задача тривиальна, решается мгновенно без размышлений (3+6, 10-2, 5*4 и т.п.). HIGH severity.

==============================================================
ПРИМЕР:
==============================================================

{
  "audit": [
    {"position": 1, "verdict": "approved", "estimated_actual_level": 3, "issues": []},
    {"position": 2, "verdict": "needs_fix", "estimated_actual_level": 2, "issues": [
      {"code": "too_easy", "severity": "high", "description": "Задача L2 вместо заявленной L3.", "fix_instruction": "Добавить нестандартный шаг, который требует догадаться."}
    ]}
  ]
}

==============================================================
ВХОД:
==============================================================

{ "items": [{"position": N, "spec": {...}, "task": {...}}, ...] }

==============================================================
ВЫХОД:
==============================================================

{ "audit": [...] }

Только JSON.'''

# ============== THEMES ==============

THEMES_BY_GRADE = {
    5: [
        "Числа, цифры и арифметические вычисления",
        "Делимость, простые и составные числа",
        "Решение задач на части",
        "Задачи на движение",
        "Площади, периметры и объёмы",
        "Обратный ход",
        "Логические задачи",
        "Графы, знакомства и маршруты", "Математические игры и стратегии",
        "Инварианты и раскраски", "Углы и простые конфигурации",
        "Длины, отношения и площади", "Разрезания, покрытия и замощения",
        "Клетчатая геометрия и конструкции",
    ],
    6: [
        "Делимость и простые числа", "НОД и НОК",
        "Цифры и системы счисления", "Обратный ход и перебор",
        "Задачи на движение", "Работа, смеси и проценты",
        "Алгебраические выражения и уравнения", "Текстовые неравенства",
        "Последовательности и суммы", "Площади и периметры",
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

# ============== SCAN EXISTING ==============

def scan_existing_l4() -> Set[Tuple[int, str]]:
    """Scan _all_tasks.jsonl for already-done (grade, topic) at level 4."""
    done: Set[Tuple[int, str]] = set()
    if not EXISTING_JSONL.exists():
        return done
    for line in EXISTING_JSONL.read_text(encoding='utf-8').strip().splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
            if obj.get('level') == 4:
                done.add((obj['grade'], obj['topic']))
        except Exception:
            pass
    return done


def build_work_queue(existing: Set[Tuple[int, str]]) -> List[Dict]:
    queue = []
    for cycle in range(1, CYCLE_COUNT + 1):
        for grade in sorted(THEMES_BY_GRADE):
            for topic in THEMES_BY_GRADE[grade]:
                if (grade, topic) in existing:
                    continue
                queue.append({
                    'grade': grade, 'topic': topic, 'level': LEVEL,
                    'num_tasks': TASKS_COUNT, 'done': False, 'cycle': cycle,
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
        cp = [{'grade': w['grade'], 'topic': w['topic'], 'level': w['level'],
               'cycle': w.get('cycle', 0), 'done': w.get('done', False)} for w in queue]
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
    for t in ['daily_task_items', 'daily_task_sets', 'daily_generation_jobs', 'task_pool', 'gen_conveyor']:
        try:
            cur.execute(f"DELETE FROM {t}")
            print(f"  OK {t}: removed {cur.rowcount} records", flush=True)
        except Exception:
            print(f"  SKIP {t}: no such table", flush=True)
    conn.commit(); conn.close()
    print("  DB cleaned.", flush=True)


_g_sem: Optional[asyncio.Semaphore] = None
def _get_sem() -> asyncio.Semaphore:
    global _g_sem
    if _g_sem is None:
        _g_sem = asyncio.Semaphore(SEMAPHORE_LIMIT)
    return _g_sem


async def ds_chat(messages: List[Dict], temperature: float = 0.7,
                  max_tokens: int = 16000) -> Tuple[str, int, int]:
    async with _get_sem():
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    resp = await client.post(
                        f"{DEEPSEEK_BASE}/chat/completions",
                        headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                                 "Content-Type": "application/json"},
                        json={"model": DEEPSEEK_MODEL, "messages": messages,
                              "temperature": temperature, "max_tokens": max_tokens},
                    )
                    if resp.status_code == 429:
                        await asyncio.sleep(min(2 ** attempt, 60)); continue
                    if resp.status_code != 200:
                        await asyncio.sleep(2); continue
                    data = resp.json()
                    text = data['choices'][0]['message']['content'] or ''
                    return text, data.get('usage', {}).get('prompt_tokens', 0), data.get('usage', {}).get('completion_tokens', 0)
                except Exception:
                    if attempt < MAX_RETRIES:
                        await asyncio.sleep(2 * attempt)
                    else:
                        return "", 0, 0
            return "", 0, 0


def _extract_json(text: str) -> Optional[Dict]:
    m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if m:
        try: return json.loads(m.group(1))
        except Exception: pass
    m = re.search(r'\{.*\}', text, re.DOTALL)
    if m:
        try: return json.loads(m.group(0))
        except Exception: pass
    return None


async def generate_one_task(spec: Dict, idx: int) -> Tuple[int, Dict, int, int]:
    user_msg = json.dumps(spec, ensure_ascii=False)
    messages = [{"role": "system", "content": GENERATE_PROMPT}, {"role": "user", "content": user_msg}]
    total_in = 0; total_out = 0
    for attempt in range(1, MAX_RETRIES + 1):
        text, in_tok, out_tok = await ds_chat(messages, temperature=0.7)
        total_in += in_tok; total_out += out_tok
        parsed = _extract_json(text)
        if parsed and parsed.get('task_text', '').strip():
            return idx, parsed, total_in, total_out
        await asyncio.sleep(1)
    return idx, {'_failed': True}, total_in, total_out


async def generate_batch(specs: List[Dict]) -> Tuple[List[Dict], int, int]:
    tasks = [None] * len(specs); total_in = 0; total_out = 0
    async def worker(i, spec):
        nonlocal total_in, total_out
        idx, task, in_tok, out_tok = await generate_one_task(spec, i)
        tasks[idx] = task; total_in += in_tok; total_out += out_tok
    await asyncio.gather(*[worker(i, s) for i, s in enumerate(specs)])
    return tasks, total_in, total_out


async def audit_batch(specs: List[Dict], tasks: List[Dict]) -> List[Dict]:
    tasks_json = json.dumps([{
        'position': t.get('position', i + 1),
        'task_text': t.get('task_text', ''),
        'correct_answer': t.get('correct_answer', ''),
    } for i, t in enumerate(tasks)], ensure_ascii=False)
    messages = [{"role": "system", "content": AUDIT_PROMPT}, {"role": "user", "content": tasks_json}]
    for attempt in range(1, 6):
        text, _, _ = await ds_chat(messages, temperature=0.5, max_tokens=8000)
        parsed = _extract_json(text)
        if parsed and isinstance(parsed, list) and len(parsed) > 0:
            return parsed
        if isinstance(parsed, dict):
            return [parsed]
        print(f"    WARN audit: {len(parsed) if parsed else 0} entries (attempt {attempt})", flush=True)
        await asyncio.sleep(2)
    return []


async def fix_one_task(spec: Dict, task: Dict, audit_entry: Dict, idx: int) -> Optional[Tuple[int, Dict]]:
    user_msg = json.dumps({'original_spec': spec, 'current_task': task, 'audit_feedback': audit_entry}, ensure_ascii=False)
    messages = [{"role": "system", "content": GENERATE_PROMPT}, {"role": "user", "content": user_msg}]
    for attempt in range(1, MAX_RETRIES + 1):
        text, _, _ = await ds_chat(messages, temperature=0.5)
        parsed = _extract_json(text)
        if parsed and parsed.get('task_text', '').strip():
            return idx, parsed
        await asyncio.sleep(1)
    return None


async def generate_with_audit(specs: List[Dict], grade: int, topic: str, level: int) -> List[Dict]:
    tasks, in_tok, out_tok = await generate_batch(specs)
    valid = sum(1 for t in tasks if t.get("task_text", "").strip() and not t.get("_failed"))
    print(f"    generated {valid}/{len(tasks)} valid, tokens: {in_tok}in/{out_tok}out", flush=True)
    for iteration in range(1, MAX_AUDIT_ITERATIONS + 1):
        audit_entries = await audit_batch(specs, tasks)
        to_fix = [(i, specs[i], tasks[i], ae) for i, ae in enumerate(audit_entries) if ae.get("verdict") != "approved"]
        if not to_fix:
            print(f"    all approved (iter {iteration})", flush=True); break
        print(f"    iter {iteration}: {len(tasks)-len(to_fix)} approved, {len(to_fix)} needs_fix", flush=True)
        if iteration >= MAX_AUDIT_ITERATIONS:
            print(f"    iteration limit reached", flush=True); break
        fix_results = await asyncio.gather(*[fix_one_task(s, t, ae, idx) for idx, s, t, ae in to_fix], return_exceptions=True)
        for r in fix_results:
            if isinstance(r, Exception) or r is None: continue
            idx, fixed = r; tasks[idx] = fixed
        await asyncio.sleep(2)
    return tasks


async def main_worker():
    existing = scan_existing_l4()
    print(f"Already-done week-4 combos: {len(existing)}", flush=True)
    queue = build_work_queue(existing)
    total_jobs = len(queue)
    total_tasks = sum(w['num_tasks'] for w in queue)
    if total_jobs == 0:
        print("\n  NOTHING TO DO - all week 4 already generated!", flush=True); return

    cp = load_checkpoint()
    if cp:
        done = sum(1 for c in cp if c.get('done'))
        print(f"Checkpoint: {done}/{total_jobs} done", flush=True)
        cp_map = {(c['grade'], c['topic'], c['level']): c.get('done', False) for c in cp}
        for w in queue:
            if cp_map.get((w['grade'], w['topic'], w['level'])): w['done'] = True

    remaining = sum(1 for w in queue if not w['done'])
    print(f"\n{'='*70}")
    print(f"  WEEK 4 ONLY (level 4, 10 tasks per topic)")
    print(f"  Skipped: {len(existing)} topics x {CYCLE_COUNT} cycles = {len(existing)*CYCLE_COUNT} batches")
    print(f"  TOTAL: {total_jobs} batches, {total_tasks} tasks")
    print(f"  LEFT: {remaining} batches, {sum(w['num_tasks'] for w in queue if not w['done'])} tasks")
    print(f"  KEY: {DEEPSEEK_API_KEY[:20]}... | MODEL: {DEEPSEEK_MODEL}")
    print(f"{'='*70}\n")

    with open(OUTPUT_FILE, 'a', encoding='utf-8') as outf:
        done_count = sum(1 for w in queue if w['done']); generated = 0
        start_time = time.monotonic()
        for idx, job in enumerate(queue):
            if job['done']: continue
            g, topic, lv, num = job['grade'], job['topic'], job['level'], job['num_tasks']
            label = f"G{g} L{lv} | {topic[:50]}"
            pulse(f"[{idx+1}/{total_jobs}] {label}")
            print(f"\n[{idx+1}/{total_jobs}] {label} ({num} tasks)", flush=True)
            t0 = time.monotonic()
            specs = make_specs(topic, lv, num)
            try:
                tasks = await generate_with_audit(specs, g, topic, lv)
            except Exception:
                print(f"  CRASH: {traceback.format_exc()[:300]}", flush=True)
                job['done'] = True; save_checkpoint(queue); continue
            dt = time.monotonic() - t0; ts = time.strftime('%Y-%m-%d %H:%M:%S')
            for j, task in enumerate(tasks):
                entry = {'grade': g, 'topic': topic, 'level': lv, 'position': j + 1,
                         'task_text': task.get('task_text', ''),
                         'correct_answer': task.get('correct_answer', ''),
                         'failed': task.get('_failed', False), 'generated_at': ts}
                outf.write(json.dumps(entry, ensure_ascii=False) + '\n'); outf.flush(); generated += 1
            job['done'] = True; done_count += 1
            elapsed = time.monotonic() - start_time
            avg = elapsed / max(done_count, 1); eta = avg * (total_jobs - done_count)
            msg = (f"  OK {sum(1 for t in tasks if t.get('task_text','').strip() and not t.get('_failed'))}/{num} valid, "
                   f"{dt:.0f}s | {done_count}/{total_jobs} ({done_count*100//total_jobs}%) | "
                   f"ETA: {eta/60:.0f}min | saved: {generated}")
            print(msg, flush=True); pulse(msg)
            if (idx + 1) % 5 == 0: save_checkpoint(queue)
    elapsed = time.monotonic() - start_time
    print(f"\n{'='*70}\n  DONE! {generated} tasks, {elapsed/60:.0f} min\n  File: {OUTPUT_FILE}")
    print(f"  Merge: type _all_tasks.jsonl _all_tasks_week4.jsonl > _all_tasks_full.jsonl\n{'='*70}")
    pulse(f"DONE -- {generated} tasks in {elapsed/60:.0f} min"); save_checkpoint(queue)


def on_signal(signum, frame):
    print(f"\nSignal {signum}, saving...", flush=True); _heartbeat_stop.set(); sys.exit(0)

signal.signal(signal.SIGINT, on_signal); signal.signal(signal.SIGTERM, on_signal)

if __name__ == '__main__':
    print("=" * 70); print("  FORMYLA WEEK 4 — standalone"); print("=" * 70)
    print("\n  -- DB Cleanup --"); clean_database()
    print("\n  -- Starting --")
    asyncio.run(main_worker())
    _heartbeat_stop.set(); print("\nDone.", flush=True)
