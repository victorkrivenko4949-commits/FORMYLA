#!/usr/bin/env python3
"""
FORMYLA — матчинг v4: параллельная обработка (ThreadPoolExecutor, 6 потоков).
Для каждого метода:
1. Фильтрует топ-30 задач по разделу из базы 5218
2. DeepSeek v4-pro выбирает ЛУЧШУЮ (по task_uid)
3. Берёт ТОЧНОЕ условие/решение/ответ из базы
4. DeepSeek v4-pro пишет разбор «Как думать»
5. Вставляет в начало worked_example_md
6. Сохраняет после каждого метода в all_methods_real_final.json

Поведение при перезапуске: пропускает уже обработанные методы.
"""
import json
import re
import time
import sys
import os
import threading
import random
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import urllib3
urllib3.disable_warnings()

# ═══════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════
API_KEY = 'sk-ad477f779a1045cba3cc09100e908370'
API_URL = 'https://api.deepseek.com/chat/completions'
MODEL = 'deepseek-v4-pro'

METHODS_FILE = 'all_methods_fixed.json'
TASKS_FILE = 'olympiad_tasks_PERFECT (3).json'
EXISTING_OUTPUT = 'all_methods_real.json'
OUTPUT = 'all_methods_real_final.json'

MAX_WORKERS = 6
TEMPERATURE = 0.3
TIMEOUT = 600  # секунд
MAX_TOKENS_STEP1 = 8000
MAX_TOKENS_STEP2 = 12000

# Thread safety
save_lock = threading.Lock()
stats_lock = threading.Lock()
stats = {'ok': 0, 'failed': 0, 'skipped': 0}

# ═══════════════════════════════════════════════════════════════
# LOAD DATA
# ═══════════════════════════════════════════════════════════════
with open(METHODS_FILE, 'r', encoding='utf-8') as f:
    methods = json.load(f)
with open(TASKS_FILE, 'r', encoding='utf-8') as f:
    tasks = json.load(f)

print(f'Loaded {len(methods)} methods, {len(tasks)} tasks', flush=True)

# Build task lookup by uid for fast access
tasks_by_uid = {t['task_uid']: t for t in tasks}

# ═══════════════════════════════════════════════════════════════
# SECTION -> KEYWORD FILTER
# ═══════════════════════════════════════════════════════════════
SECTION_FILTERS = {
    'A': ['числ', 'сумм', 'произвед', 'делит', 'остат', 'цифр', 'дроб', 'процент',
          'скорост', 'работ', 'движен', 'цена', 'стоим', 'покуп', 'зарпл', 'возраст',
          'год', 'рубл', 'копеек', 'килограмм', 'метр', 'литр', 'выражен', 'значен',
          'вычислит', 'сложен', 'умножен', 'разност', 'квадрат'],
    'B': ['логик', 'игр', 'ход', 'выигрыш', 'проигрыш', 'шахмат', 'весы', 'монет',
          'фальшив', 'правд', 'лж', 'рыцар', 'лжец', 'стратег', 'колпак', 'гном',
          'утвержден', 'можно ли', 'верно ли', 'всегда ли', 'существует ли'],
    'C': ['многочлен', 'корен', 'уравнен', 'виет', 'систем', 'алгебра', 'разложен',
          'симметр', 'коэффициент', 'степен', 'переменн', 'значен', 'трёхчлен',
          'квадратн', 'дискриминант', 'тождеств', 'преобразован'],
    'D': ['прост', 'составн', 'делител', 'сравнен', 'модул', 'нод', 'нок',
          'эйлер', 'ферм', 'остатк', 'делимост', 'степен', 'взаимно прост', 'последн',
          'цифр', 'разложен', 'канонич', 'кратн', 'признак делимост'],
    'E': ['комбинатор', 'перестановк', 'размещен', 'сочетан', 'дирихле',
          'инвариант', 'граф', 'дерев', 'цикл', 'раскрас', 'подсчет', 'количеств',
          'способ', 'разрезан', 'размест', 'выбрать', 'скольк',
          'остров', 'шар', 'ящик', 'клетк', 'принцип', 'вероятност'],
    'F': ['треугольник', 'окружност', 'круг', 'угол', 'площад', 'периметр',
          'подоб', 'вектор', 'координат', 'симметр', 'поворот', 'медиан',
          'биссектр', 'высот', 'касательн', 'хорд', 'секущ', 'четырехугол',
          'параллел', 'ромб', 'прямоугол', 'квадрат', 'трапец', 'прямая', 'точк',
          'сторон', 'вершин', 'диагонал', 'вписан', 'описан'],
    'G': ['неравенств', 'коши', 'йенсен', 'среднее', 'выпукл',
          'оценк', 'максимум', 'минимум', 'докажите', 'больше', 'меньш', 'не менее',
          'не более', 'наименьш', 'наибольш', 'доказат', 'выполняет'],
    'H': ['производн', 'интеграл', 'предел', 'функци', 'непрерывн', 'дифференц',
          'касательн', 'возраст', 'убыван', 'экстремум', 'график', 'наибольш',
          'наименьш', 'монотон', 'выпукл', 'точк', 'касательн', 'первообразн']
}


def filter_tasks_by_section(all_tasks, section, method_text):
    """Pre-filter tasks by section keywords and method-specific words.
    Returns top-50 scored candidates."""
    kws = SECTION_FILTERS.get(section, [])
    method_name = method_text.lower()
    name_words = re.findall(r'[а-яё]{4,}', method_name)

    scored = []
    for t in all_tasks:
        text = (t.get('text', '') + ' ' + str(t.get('solution', '') or '')[:200]).lower()
        section_score = sum(1 for kw in kws if kw in text)
        name_score = sum(2 for w in name_words if len(w) > 4 and w in text)
        grade = t.get('grade', 0)
        grade_score = 1 if grade in [7, 8, 9] else 0
        total = section_score + name_score + grade_score
        if total > 0:
            scored.append((total, t))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [t for _, t in scored[:50]]


def normalize_latex(text):
    r"""Convert \(...\) -> $...$ and \[...\] -> $$...$$"""
    if not text:
        return text
    text = re.sub(r'\\\[(.+?)\\\]', r'$$\1$$', text, flags=re.DOTALL)
    text = re.sub(r'\\\((.+?)\\\)', r'$\1$', text, flags=re.DOTALL)
    return text


def quality_check(analysis, source_name):
    """Verify that the analysis has all required sections."""
    required = ['### Задача 1', '**Источник:**', '**Как думать:**',
                 '**Решение:**', '**Ответ:**', '**Что было главным:**']
    missing = [r for r in required if r not in analysis]
    # Also check that the source is from the database (not made up)
    if source_name and source_name not in analysis:
        missing.append(f'source_name "{source_name}" not in text')
    return missing


# ═══════════════════════════════════════════════════════════════
# API CALL WITH INFINITE RETRY
# ═══════════════════════════════════════════════════════════════

def call_api(payload, max_tokens, timeout, label=''):
    """Calls DeepSeek API with infinite retry on network errors.
    Returns (content, usage_dict) or ('', {}) on ultimate failure."""
    session = requests.Session()
    session.verify = False
    headers = {
        'Authorization': f'Bearer {API_KEY}',
        'Content-Type': 'application/json'
    }

    attempt = 0
    while True:
        attempt += 1
        try:
            r = session.post(API_URL, json=payload, headers=headers, timeout=timeout)

            if r.status_code == 429:
                wait = min(60, 10 * attempt)
                print(f'      [{label}] Rate limit (429), жду {wait}с... (попытка {attempt})', flush=True)
                time.sleep(wait)
                continue

            if r.status_code >= 500:
                wait = min(60, 5 * attempt)
                print(f'      [{label}] Server error {r.status_code}, жду {wait}с... (попытка {attempt})', flush=True)
                time.sleep(wait)
                continue

            if r.status_code != 200:
                wait = min(30, 3 * attempt)
                print(f'      [{label}] HTTP {r.status_code}, жду {wait}с... (попытка {attempt})', flush=True)
                time.sleep(wait)
                continue

            d = r.json()
            c = d['choices'][0]['message'].get('content', '') or ''
            finish = d['choices'][0].get('finish_reason', '')

            # Empty response with length limit -> increase tokens
            if not c and finish == 'length':
                new_max = min(int(max_tokens * 1.5), 32000)
                if new_max > max_tokens:
                    print(f'      [{label}] Empty (finish=length), tokens {max_tokens}->{new_max}', flush=True)
                    payload['max_tokens'] = new_max
                    max_tokens = new_max
                    time.sleep(2)
                    continue

            if not c:
                print(f'      [{label}] Empty response, retry 5s... (attempt {attempt})', flush=True)
                time.sleep(5)
                continue

            return c, d.get('usage', {})

        except requests.exceptions.ConnectionError as e:
            wait = min(120, 10 * (attempt if attempt < 12 else 12))
            print(f'      [{label}] NO INTERNET: {str(e)[:80]}', flush=True)
            print(f'      [{label}] Waiting {wait}s... (attempt {attempt})', flush=True)
            time.sleep(wait)
            if attempt % 360 == 0:
                attempt = 0
            continue

        except requests.exceptions.Timeout:
            wait = min(60, 5 * attempt)
            print(f'      [{label}] Timeout, waiting {wait}s... (attempt {attempt})', flush=True)
            time.sleep(wait)
            continue

        except Exception as e:
            wait = min(60, 5 * attempt)
            print(f'      [{label}] Error: {str(e)[:80]}, waiting {wait}s... (attempt {attempt})', flush=True)
            time.sleep(wait)
            continue


def save_methods_safe():
    """Thread-safe save of the entire methods list to OUTPUT."""
    with save_lock:
        with open(OUTPUT, 'w', encoding='utf-8') as f:
            json.dump(methods, f, ensure_ascii=False, indent=2)


# ═══════════════════════════════════════════════════════════════
# PROMPTS
# ═══════════════════════════════════════════════════════════════

SYS_SELECT = """Ты — эксперт по олимпиадной математике.

Дано: описание метода и список реальных задач из базы.
Задача: выбери ОДНУ задачу, которая лучше всего иллюстрирует метод.

Критерии выбора:
1. Задача должна решаться именно этим методом
2. Не слишком сложная (классы 7-9)
3. С красивой идеей
4. Если ни одна не подходит идеально — выбери лучшую

Ответ: ТОЛЬКО task_uid выбранной задачи и краткое объяснение (1-2 предложения) почему она подходит.

Формат:
task_uid: <uid>
почему: <объяснение>"""

PROMPT_SELECT = """Метод: {code}: {name}
Раздел: {section}. Сложность: {difficulty}/5.

Определение: {definition}

Приёмы: {techniques}

Кандидаты (топ-30 задач из базы):
{candidates}

Выбери ЛУЧШУЮ задачу. Верни task_uid и объяснение."""

SYS_ANALYSIS = """Ты — эксперт по олимпиадной математике и методист.
Напиши разбор задачи в формате методической статьи.
LaTeX: $...$ и $$...$$.
НЕ меняй условие задачи и решение — только добавь рассуждение "Как думать".
Условие и решение должны быть ТОЧНО как в исходных данных."""

PROMPT_ANALYSIS = """Метод: {code}: {name}

Определение метода: {definition}

Задача (РЕАЛЬНАЯ, из базы):
{text}

Официальное решение:
{solution}

Ответ: {answer}

Напиши разбор в формате:

### Задача 1. [точная формулировка из условия выше]

**Источник:** {source_name}

**Как думать (рассуждение ученика):**
1. *Что я вижу?* ...
2. *Какой триггер сработал?* (свяжи с методом {code}) ...
3. *Первый ход?* ...
4. *Ключевая идея?* ...

**Решение:**
[перепиши решение с формулами $...$, добавь пояснения]

**Ответ:** [ответ]

**Что было главным:** [ключевой вывод метода]

Верни ТОЛЬКО текст разбора."""


# ═══════════════════════════════════════════════════════════════
# PROCESS ONE METHOD
# ═══════════════════════════════════════════════════════════════

def process_method(m):
    """Process a single method: select task -> write analysis -> insert into worked_example_md.
    Returns True on success, False on failure."""
    code = m['method_code']
    name = m['method_name']
    section = m.get('section', '')
    label = f'{code}:{name[:20]}'

    print(f'\n[{code}] {name}', flush=True)
    print(f'  Section={section}, difficulty={m.get("difficulty_level","?")}', flush=True)

    # ── Step 1: filter candidates ──
    method_text = name + ' ' + m.get('definition_md', '')[:300]
    candidates = filter_tasks_by_section(tasks, section, method_text)

    if not candidates:
        print(f'  [{code}] WARNING: No candidates from section filter, using random sample', flush=True)
        candidates = random.sample(tasks, min(30, len(tasks)))

    sample = candidates[:30] if len(candidates) >= 30 else candidates
    print(f'  [{code}] Candidates: {len(sample)}', flush=True)

    # Build candidates text
    cand_text = ""
    for i, t in enumerate(sample):
        cand_text += f"\n[{i+1}] task_uid: {t.get('task_uid','?')}\n"
        cand_text += f"    source: {t.get('source_name','?')}\n"
        cand_text += f"    grade: {t.get('grade','?')}\n"
        cand_text += f"    text: {t.get('text','')[:300]}\n"

    # ── Step 1: Select best task via API ──
    print(f'  [{code}] Step 1/2: Selecting best task...', flush=True)

    select_payload = {
        'model': MODEL,
        'messages': [
            {'role': 'system', 'content': SYS_SELECT},
            {'role': 'user', 'content': PROMPT_SELECT.format(
                code=code, name=name, section=section,
                difficulty=m.get('difficulty_level', '?'),
                definition=m.get('definition_md', '')[:500],
                techniques=m.get('typical_techniques_md', '')[:400],
                candidates=cand_text
            )}
        ],
        'max_tokens': MAX_TOKENS_STEP1,
        'temperature': TEMPERATURE,
    }

    selection, usage1 = call_api(select_payload, MAX_TOKENS_STEP1, TIMEOUT, label)
    if not selection:
        print(f'  [{code}] FAILED: no selection response', flush=True)
        with stats_lock:
            stats['failed'] += 1
        return False

    # Extract task_uid
    uid_match = re.search(r'task_uid:\s*(\S+)', selection)
    if not uid_match:
        print(f'  [{code}] FAILED: no uid in: {selection[:150]}', flush=True)
        with stats_lock:
            stats['failed'] += 1
        return False

    uid = uid_match.group(1).strip()
    print(f'  [{code}] Step 1/2 OK -> uid={uid[:24]}...', flush=True)

    # Find the task in database
    selected_task = tasks_by_uid.get(uid)
    if not selected_task:
        print(f'  [{code}] FAILED: uid {uid[:30]} not in database', flush=True)
        with stats_lock:
            stats['failed'] += 1
        return False

    source_name = selected_task.get('source_name', '?')
    print(f'  [{code}] Source: {source_name}', flush=True)
    print(f'  [{code}] Text: {selected_task["text"][:120]}...', flush=True)

    # ── Step 2: Write analysis ──
    print(f'  [{code}] Step 2/2: Writing analysis...', flush=True)

    analysis_payload = {
        'model': MODEL,
        'messages': [
            {'role': 'system', 'content': SYS_ANALYSIS},
            {'role': 'user', 'content': PROMPT_ANALYSIS.format(
                code=code, name=name,
                definition=m.get('definition_md', '')[:400],
                text=selected_task.get('text', ''),
                solution=str(selected_task.get('solution', '') or '')[:3000],
                answer=str(selected_task.get('answer', '') or ''),
                source_name=source_name
            )}
        ],
        'max_tokens': MAX_TOKENS_STEP2,
        'temperature': TEMPERATURE,
    }

    analysis, usage2 = call_api(analysis_payload, MAX_TOKENS_STEP2, TIMEOUT, label)
    if not analysis:
        print(f'  [{code}] FAILED: no analysis response', flush=True)
        with stats_lock:
            stats['failed'] += 1
        return False

    # Normalize LaTeX
    analysis = normalize_latex(analysis)

    # Quality check
    missing = quality_check(analysis, source_name)
    if missing:
        print(f'  [{code}] WARNING: Quality check missing: {missing}', flush=True)
        # Continue anyway — partial result is better than nothing

    # Insert real task BEFORE existing examples
    existing_we = m.get('worked_example_md', '')
    m['worked_example_md'] = analysis + '\n\n' + existing_we

    total_tokens = usage1.get('total_tokens', 0) + usage2.get('total_tokens', 0)
    print(f'  [{code}] Step 2/2 OK: {len(analysis)} chars, {total_tokens} tokens', flush=True)

    with stats_lock:
        stats['ok'] += 1

    # Save after each method (thread-safe)
    save_methods_safe()
    print(f'  [{code}] SAVED [OK]', flush=True)

    return True


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    global methods

    # ── Determine which methods are already processed ──
    to_process = []
    already_processed = set()

    if os.path.exists(EXISTING_OUTPUT):
        with open(EXISTING_OUTPUT, 'r', encoding='utf-8') as f:
            existing_data = json.load(f)
        existing_map = {m['method_code']: m for m in existing_data}
        print(f'Loaded {len(existing_map)} entries from {EXISTING_OUTPUT}', flush=True)

        for m in methods:
            code = m['method_code']
            if code in existing_map:
                we = existing_map[code].get('worked_example_md', '')
                # Check if first task has a real (non-training) source
                task1_idx = we.find('### Задача 1')
                if task1_idx >= 0:
                    src_idx = we.find('**Источник:**', task1_idx)
                    if src_idx >= 0:
                        src_end = we.find('\n', src_idx)
                        src_line = we[src_idx:src_end] if src_end > 0 else we[src_idx:src_end+100]
                        src_lower = src_line.lower()
                        if ('тренировочная' not in src_lower
                                and 'классическая задача' not in src_lower
                                and 'по легенде' not in src_lower):
                            # Already has real task — use it
                            m['worked_example_md'] = we
                            already_processed.add(code)
                            print(f'  [{code}] [OK] Already processed (source: {src_line[14:80]}...)', flush=True)
                            continue
                # Not processed or has training task — needs processing
            to_process.append(m)
    else:
        print(f'{EXISTING_OUTPUT} not found, processing all methods', flush=True)
        to_process = list(methods)

    print(f'\n{"=" * 60}')
    print(f'Already processed: {len(already_processed)} methods')
    print(f'To process:        {len(to_process)} methods')
    if to_process:
        print(f'Remaining codes:   {[m["method_code"] for m in to_process]}')
    print(f'{"=" * 60}\n', flush=True)

    if not to_process:
        # Just save the final output
        save_methods_safe()
        print(f'All methods already processed! Saved to {OUTPUT}', flush=True)
        return

    # ── Process in parallel ──
    print(f'Starting parallel processing with {MAX_WORKERS} workers...\n', flush=True)

    # Sort by section for better cache locality (same section tasks similar)
    to_process.sort(key=lambda m: (m.get('section', ''), m.get('method_code', '')))

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_method, m): m for m in to_process}

        for future in as_completed(futures):
            m = futures[future]
            try:
                success = future.result()
                if not success:
                    print(f'  [{m["method_code"]}] [FAIL]', flush=True)
            except Exception as e:
                print(f'  [{m["method_code"]}] [EXCEPTION]: {e}', flush=True)
                with stats_lock:
                    stats['failed'] += 1

    # ── Final report ──
    print(f'\n{"=" * 60}')
    print(f'DONE! ok={stats["ok"]}, failed={stats["failed"]}, skipped={stats["skipped"]}')
    print(f'Saved to {OUTPUT}')
    print(f'{"=" * 60}', flush=True)


if __name__ == '__main__':
    main()
