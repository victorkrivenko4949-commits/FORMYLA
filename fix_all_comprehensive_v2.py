#!/usr/bin/env python3
"""
COMPREHENSIVE FIX SCRIPT v2 — clean, no regex-DOTALL bugs.

Problem 1: E8, E12, E14, E15, F3 — missing Ответ/Что было главным in ALL tasks
Problem 2: G1,G2,G3,G4,G5,G7,H3,H5,E5a,F14,F15,F16,F17,H4 — training first task

Uses DeepSeek v4-pro. Saves incrementally.
"""

import json, re, time, sys, os, random
import requests, urllib3

urllib3.disable_warnings()
API_KEY = 'sk-ad477f779a1045cba3cc09100e908370'
API_URL = 'https://api.deepseek.com/chat/completions'
MODEL = 'deepseek-v4-pro'

METHODS_FILE = 'all_methods_real_final.json'
TASKS_FILE = 'olympiad_tasks_PERFECT (3).json'
OUTPUT = 'all_methods_real_final.json'

PROBLEM1 = ['E8', 'E12', 'E14', 'E15', 'F3']
PROBLEM2 = ['G1', 'G2', 'G3', 'G4', 'G5', 'G7', 'H3', 'H5', 'E5a', 'F14', 'F15', 'F16', 'F17', 'H4']

# ===========================================================================
# API helper
# ===========================================================================
def call_api(payload, label='', max_retries=15):
    session = requests.Session()
    session.verify = False
    headers = {'Authorization': f'Bearer {API_KEY}', 'Content-Type': 'application/json'}
    for attempt in range(max_retries):
        try:
            r = session.post(API_URL, json=payload, headers=headers, timeout=180)
            if r.status_code == 429:
                wait = min(60, 10*(attempt+1))
                print(f'      [{label}] 429, wait {wait}s...', flush=True)
                time.sleep(wait); continue
            if r.status_code >= 500:
                wait = min(60, 5*(attempt+1))
                print(f'      [{label}] {r.status_code}, wait {wait}s...', flush=True)
                time.sleep(wait); continue
            if r.status_code != 200:
                print(f'      [{label}] HTTP {r.status_code}, retry...', flush=True)
                time.sleep(5); continue
            d = r.json()
            c = d['choices'][0]['message'].get('content','') or ''
            if not c:
                print(f'      [{label}] Empty, retry...', flush=True)
                time.sleep(5); continue
            return c, d.get('usage',{})
        except Exception as e:
            wait = min(60, 5*(attempt+1))
            print(f'      [{label}] {str(e)[:80]}, wait {wait}s...', flush=True)
            time.sleep(wait)
    return '', {}

# ===========================================================================
# LOAD DATA
# ===========================================================================
with open(METHODS_FILE, 'r', encoding='utf-8') as f:
    methods = json.load(f)
print(f'Loaded {len(methods)} methods', flush=True)

with open(TASKS_FILE, 'r', encoding='utf-8') as f:
    olympiad_tasks = json.load(f)
tasks_by_uid = {t['task_uid']: t for t in olympiad_tasks}
print(f'Loaded {len(olympiad_tasks)} olympiad tasks', flush=True)

# ===========================================================================
# SECTION FILTERS
# ===========================================================================
SECTION_FILTERS = {
    'A': ['числ','сумм','произвед','делит','остат','цифр','дроб','процент',
          'скорост','работ','движен','цена','стоим','покуп','возраст',
          'год','рубл','выражен','значен','вычислит','сложен','умножен'],
    'B': ['логик','игр','ход','выигрыш','проигрыш','шахмат','весы','монет',
          'фальшив','правд','лж','рыцар','лжец','стратег','можно ли','верно ли'],
    'C': ['многочлен','корен','уравнен','виет','систем','алгебра','разложен',
          'симметр','коэффициент','степен','переменн','квадратн','дискриминант'],
    'D': ['прост','составн','делител','сравнен','модул','нод','нок',
          'эйлер','остатк','делимост','взаимно прост','кратн','признак делимост'],
    'E': ['комбинатор','перестановк','размещен','сочетан','дирихле',
          'инвариант','граф','дерев','цикл','раскрас','подсчет','количеств',
          'способ','разрезан','скольк','вероятност','принцип'],
    'F': ['треугольник','окружност','круг','угол','площад','периметр',
          'подоб','вектор','координат','симметр','поворот','медиан',
          'биссектр','высот','касательн','хорд','четырехугол','вписан','описан'],
    'G': ['неравенств','коши','йенсен','среднее','выпукл',
          'оценк','максимум','минимум','докажите','больше','меньш',
          'наименьш','наибольш','доказат','выполняет'],
    'H': ['производн','интеграл','предел','функци','непрерывн','дифференц',
          'касательн','возраст','убыван','экстремум','график','монотон','выпукл']
}

def filter_tasks_by_section(all_tasks, section, method_text):
    kws = SECTION_FILTERS.get(section, [])
    name_words = re.findall(r'[а-яё]{4,}', method_text.lower())
    scored = []
    for t in all_tasks:
        text = (t.get('text','') + ' ' + str(t.get('solution','') or '')[:200]).lower()
        section_score = sum(1 for kw in kws if kw in text)
        name_score = sum(2 for w in name_words if len(w) > 4 and w in text)
        grade = t.get('grade',0)
        grade_score = 1 if grade in [7,8,9] else 0
        total = section_score + name_score + grade_score
        if total > 0:
            scored.append((total, t))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [t for _, t in scored[:40]]

def normalize_latex(text):
    if not text: return text
    text = re.sub(r'\\\[(.+?)\\\]', r'$$\1$$', text, flags=re.DOTALL)
    text = re.sub(r'\\\((.+?)\\\)', r'$\1$', text, flags=re.DOTALL)
    return text

def save():
    with open(OUTPUT, 'w', encoding='utf-8') as f:
        json.dump(methods, f, ensure_ascii=False, indent=2)

# ===========================================================================
# PROBLEM 1: Fix truncated tasks (missing Ответ/Что было главным)
# ===========================================================================
print('\n' + '='*70)
print('PROBLEM 1: Fixing truncated tasks (E8,E12,E14,E15,F3)')
print('='*70)

SYS_COMPLETE = """Ты — эксперт по олимпиадной математике и методист.
Тебе дан текст задачи из разбора метода, которому не хватает заключительных секций.
Допиши **Ответ:** и **Что было главным:** основываясь на тексте условия и решения.
Верни только эти 2 секции, в точном формате:

**Ответ:** [правильный ответ, формулы в $...$]

**Что было главным:** [ключевой вывод метода, 1-2 предложения на русском]"""

def complete_task(code, name, task_text):
    """Call DeepSeek to write Ответ + Что было главным for one task."""
    context = task_text[-3500:]  # last 3500 chars of task
    payload = {
        'model': MODEL, 'max_tokens': 2000, 'temperature': 0.3,
        'messages': [
            {'role': 'system', 'content': SYS_COMPLETE},
            {'role': 'user', 'content': f'Метод {code}: {name}\n\nТекст задачи (без Ответ/Что было главным):\n{context}'}
        ]
    }
    result, _ = call_api(payload, label=f'{code}-complete')
    return result.strip() if result else None

for m in methods:
    code = m['method_code']
    if code not in PROBLEM1:
        continue
    name = m['method_name']
    we = m.get('worked_example_md', '')

    # Split into tasks by "### Задача" marker
    # tasks[0] = preamble, tasks[1..] = task texts
    parts = we.split('### Задача')
    preamble = parts[0]
    task_parts = parts[1:]  # each starts with " N. title..."

    print(f'\n[{code}] {name} — {len(task_parts)} tasks', flush=True)

    fixed_any = False
    for idx, t in enumerate(task_parts):
        has_a = '**Ответ:**' in t
        has_m = '**Что было главным:**' in t
        if has_a and has_m:
            print(f'  Task {idx+1}: already complete', flush=True)
            continue

        desc = []
        if not has_a: desc.append('Ответ')
        if not has_m: desc.append('Что было главным')
        print(f'  Task {idx+1}: missing {", ".join(desc)} — calling DeepSeek...', flush=True)

        full_task = '### Задача' + t
        completion = complete_task(code, name, full_task)
        if completion:
            # Clean: remove any partial trailing Ответ/Что from task text
            clean_t = t
            # Remove from last **Ответ:** or **Что было главным:** to end
            ans_pos = clean_t.rfind('\n**Ответ:**')
            main_pos = clean_t.rfind('\n**Что было главным:**')
            cut_pos = max(ans_pos, main_pos)
            if cut_pos > 0:
                clean_t = clean_t[:cut_pos]
            clean_t = clean_t.rstrip()
            task_parts[idx] = clean_t + '\n\n' + completion
            print(f'    => COMPLETED ({len(completion)} chars)', flush=True)
            fixed_any = True
        else:
            print(f'    => FAILED', flush=True)

    if fixed_any:
        m['worked_example_md'] = preamble + '### Задача' + '### Задача'.join(task_parts)
        save()
        print(f'  => SAVED', flush=True)

print('\nProblem 1 COMPLETE')

# ===========================================================================
# PROBLEM 2: Replace training first task with real olympiad task
# ===========================================================================
print('\n' + '='*70)
print('PROBLEM 2: Replacing training first task')
print('='*70)

SYS_SELECT = """Ты — эксперт по олимпиадной математике.
Дано: описание метода и список реальных задач из базы.
Задача: выбери ОДНУ задачу, которая лучше всего иллюстрирует метод.
Критерии:
1. Задача решается именно этим методом
2. Не слишком сложная (классы 7-9)
3. С красивой идеей
Ответ: ТОЛЬКО task_uid и краткое объяснение.
Формат:
task_uid: <uid>
почему: <объяснение>"""

SYS_ANALYSIS = """Ты — эксперт по олимпиадной математике и методист.
Напиши разбор задачи в формате методической статьи.
LaTeX: $...$ и $$...$$.
НЕ меняй условие задачи и решение — только добавь рассуждение "Как думать"."""

def select_and_write_task(m):
    """Step 1: select best task. Step 2: write analysis. Insert into worked_example_md."""
    code = m['method_code']; name = m['method_name']
    section = m.get('section','')
    print(f'\n[{code}] {name[:60]} section={section}', flush=True)

    # Filter candidates
    method_text = name + ' ' + m.get('definition_md','')[:300]
    candidates = filter_tasks_by_section(olympiad_tasks, section, method_text)
    if not candidates:
        candidates = random.sample(olympiad_tasks, min(30, len(olympiad_tasks)))
    sample = candidates[:25]
    print(f'  Candidates: {len(sample)}', flush=True)

    # Build candidate list
    cand_lines = []
    for i, t in enumerate(sample):
        cand_lines.append(f"[{i+1}] task_uid: {t.get('task_uid','?')}")
        cand_lines.append(f"    source: {t.get('source_name','?')}")
        cand_lines.append(f"    grade: {t.get('grade','?')}")
        cand_lines.append(f"    text: {t.get('text','')[:250]}")
        cand_lines.append("")
    cand_text = '\n'.join(cand_lines)

    sel_prompt = f"""Метод: {code}: {name}
Раздел: {section}. Сложность: {m.get('difficulty_level','?')}/5.

Определение: {m.get('definition_md','')[:500]}

Приёмы: {m.get('typical_techniques_md','')[:400]}

Кандидаты (топ-25 задач из базы):
{cand_text}

Выбери ЛУЧШУЮ задачу. Верни task_uid и объяснение."""

    # Step 1: Select
    payload = {'model': MODEL, 'max_tokens': 3000, 'temperature': 0.3,
               'messages': [{'role': 'system', 'content': SYS_SELECT},
                            {'role': 'user', 'content': sel_prompt}]}
    selection, _ = call_api(payload, label=f'{code}-select')
    if not selection:
        print(f'  FAILED: no selection', flush=True); return False

    uid_m = re.search(r'task_uid:\s*(\S+)', selection)
    if not uid_m:
        print(f'  FAILED: no uid in: {selection[:150]}', flush=True); return False
    uid = uid_m.group(1).strip()
    print(f'  Selected uid={uid[:30]}...', flush=True)

    sel_task = tasks_by_uid.get(uid)
    if not sel_task:
        print(f'  FAILED: uid not in DB', flush=True); return False
    source_name = sel_task.get('source_name','?')
    print(f'  Source: {source_name}', flush=True)

    # Step 2: Write analysis
    analysis_prompt = f"""Метод: {code}: {name}

Определение метода: {m.get('definition_md','')[:400]}

Задача (РЕАЛЬНАЯ, из базы):
{sel_task.get('text','')}

Официальное решение:
{str(sel_task.get('solution','') or '')[:3000]}

Ответ: {str(sel_task.get('answer','') or '')}

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

    payload2 = {'model': MODEL, 'max_tokens': 12000, 'temperature': 0.3,
                'messages': [{'role': 'system', 'content': SYS_ANALYSIS},
                             {'role': 'user', 'content': analysis_prompt}]}
    analysis, _ = call_api(payload2, label=f'{code}-analysis')
    if not analysis:
        print(f'  FAILED: no analysis', flush=True); return False

    analysis = normalize_latex(analysis)

    # Quality check
    required = ['### Задача 1', '**Источник:**', '**Как думать:**', '**Решение:**', '**Ответ:**', '**Что было главным:**']
    missing = [r for r in required if r not in analysis]
    if missing:
        print(f'  WARNING: missing sections: {missing}', flush=True)

    # Keep existing tasks 2+ (skip training task 1)
    existing = m.get('worked_example_md','')
    parts = existing.split('### Задача')
    # parts[0] = preamble (if any), parts[1] = training task, parts[2..] = real tasks
    kept_tasks = parts[2:]  # tasks 2, 3, 4...

    # Build new worked_example_md
    if kept_tasks:
        m['worked_example_md'] = analysis.strip() + '\n\n### Задача' + '### Задача'.join(kept_tasks)
    else:
        m['worked_example_md'] = analysis.strip()

    print(f'  => Inserted. New length: {len(m["worked_example_md"])} chars', flush=True)
    return True


for m in methods:
    code = m['method_code']
    if code not in PROBLEM2:
        continue

    we = m.get('worked_example_md','')
    parts = we.split('### Задача')

    # Check if first task is training
    first_task = parts[1] if len(parts) > 1 else ''
    src_match = re.search(r'\*\*Источник:\*\*\s*(.+?)(?:\n|$)', first_task)
    src = src_match.group(1).strip() if src_match else ''
    is_training = 'тренировочная' in src.lower() or 'классическая задача' in src.lower() or len(parts) <= 1

    if not is_training:
        print(f'[{code}] First task already real (source: {src[:60]}), skipping', flush=True)
        continue

    print(f'[{code}] Training first task (source: {src[:60]}, {len(parts)-1} tasks), replacing...', flush=True)
    success = select_and_write_task(m)
    if success:
        save()
        print(f'[{code}] SAVED', flush=True)
    else:
        print(f'[{code}] FAILED — will need manual fix', flush=True)

print('\n' + '='*70)
print('ALL DONE! Final save...')
save()
print(f'Saved to {OUTPUT}')
print('='*70)
