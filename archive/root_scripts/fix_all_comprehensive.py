import os
#!/usr/bin/env python3
"""
COMPREHENSIVE FIX SCRIPT:
Problem 1: E8, E12, E14, E15, F3 — truncated tasks (missing Ответ/Что было главным)
Problem 2: G1,G2,G3,G4,G5,G7,H3,H5,E5a,F14,F15,F16,F17 (+H4) — training first task

Uses DeepSeek v4-pro for both fixes.
Saves incrementally to all_methods_real_final.json.
"""
import json, re, time, sys, os, random
import requests, urllib3

urllib3.disable_warnings()
API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
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
# SECTION FILTERS (from formyla_match_real.py)
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

# ===========================================================================
# PROBLEM 1: Fix truncated tasks
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
    context = task_text[-3000:]
    payload = {
        'model': MODEL, 'max_tokens': 2000, 'temperature': 0.3,
        'messages': [
            {'role': 'system', 'content': SYS_COMPLETE},
            {'role': 'user', 'content': f'Метод {code}: {name}\n\nТекст задачи (без Ответ/Что было главным):\n{context}'}
        ]
    }
    completion, _ = call_api(payload, label=f'{code}-complete')
    return completion.strip() if completion else None

for m in methods:
    code = m['method_code']
    if code not in PROBLEM1:
        continue
    name = m['method_name']
    we = m.get('worked_example_md','')
    tasks = we.split('### Задача')
    print(f'\n[{code}] {name} — {len(tasks)-1} tasks', flush=True)

    fixed_any = False
    for i in range(1, len(tasks)):
        t = tasks[i]
        has_a = '**Ответ:**' in t
        has_m = '**Что было главным:**' in t
        if has_a and has_m:
            print(f'  Task {i}: already complete', flush=True)
            continue
        print(f'  Task {i}: missing {"Ответ" if not has_a else ""} {"Что было главным" if not has_m else ""} — calling DeepSeek...', flush=True)
        prefix = '### Задача' + t
        completion = complete_task(code, name, prefix)
        if completion:
            # Remove any existing partial Ответ/Что было главным from task text (line-by-line safe)
            clean_t = t
            # Remove **Ответ:** line and everything after it in the same paragraph
            lines = clean_t.split('\n')
            new_lines = []
            in_bad_section = False
            for line in lines:
                if '**Ответ:**' in line or '**Что было главным:**' in line:
                    in_bad_section = True
                    continue
                if in_bad_section:
                    # End of bad section when we see a new section header or empty line then new content
                    if line.strip().startswith('**') or line.strip().startswith('###'):
                        in_bad_section = False
                        new_lines.append(line)
                    elif line.strip() == '':
                        in_bad_section = False
                    continue
                new_lines.append(line)
            clean_t = '\n'.join(new_lines).rstrip()
            tasks[i] = clean_t + '\n\n' + completion
            print(f'    => COMPLETED: {completion[:120]}...', flush=True)
            fixed_any = True
        else:
            print(f'    => FAILED to complete', flush=True)

    if fixed_any:
        m['worked_example_md'] = '### Задача'.join(tasks)
        # Save
        with open(OUTPUT, 'w', encoding='utf-8') as f:
            json.dump(methods, f, ensure_ascii=False, indent=2)
        print(f'  => SAVED after Problem 1 fix', flush=True)

print('\nProblem 1 DONE')

# ===========================================================================
# PROBLEM 2: Replace training first task with real task
# ===========================================================================
print('\n' + '='*70)
print('PROBLEM 2: Replacing training first task (13+ methods)')
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
    code = m['method_code']; name = m['method_name']
    section = m.get('section','')
    print(f'\n[{code}] {name[:50]} section={section}', flush=True)

    # Filter candidates
    method_text = name + ' ' + m.get('definition_md','')[:300]
    candidates = filter_tasks_by_section(olympiad_tasks, section, method_text)
    if not candidates:
        candidates = random.sample(olympiad_tasks, min(30, len(olympiad_tasks)))
    sample = candidates[:25]
    print(f'  Candidates: {len(sample)}', flush=True)

    # Step 1: Select
    cand_text = ''
    for i, t in enumerate(sample):
        cand_text += f"\n[{i+1}] task_uid: {t.get('task_uid','?')}\n"
        cand_text += f"    source: {t.get('source_name','?')}\n"
        cand_text += f"    grade: {t.get('grade','?')}\n"
        cand_text += f"    text: {t.get('text','')[:250]}\n"

    sel_prompt = f"""Метод: {code}: {name}
Раздел: {section}. Сложность: {m.get('difficulty_level','?')}/5.

Определение: {m.get('definition_md','')[:500]}

Приёмы: {m.get('typical_techniques_md','')[:400]}

Кандидаты (топ-25 задач из базы):
{cand_text}

Выбери ЛУЧШУЮ задачу. Верни task_uid и объяснение."""

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
    print(f'  Selected: {uid[:30]}...', flush=True)

    sel_task = tasks_by_uid.get(uid)
    if not sel_task:
        print(f'  FAILED: uid not in DB', flush=True); return False
    source_name = sel_task.get('source_name','?')
    print(f'  Source: {source_name}', flush=True)

    # Step 2: Analysis
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

    # Insert: prepend before existing tasks
    existing = m.get('worked_example_md','')
    # If existing has training first task, remove it (keep only tasks 2+)
    if existing:
        existing_tasks = existing.split('### Задача')
        # Keep only non-training tasks
        kept = ['### Задача']
        for i in range(2, len(existing_tasks)):
            kept.append(existing_tasks[i])
        if len(kept) == 1:
            existing = ''  # no real tasks to keep
        else:
            existing = '### Задача'.join(kept)

    m['worked_example_md'] = analysis.strip() + ('\n\n' + existing.strip() if existing.strip() else '')
    print(f'  => Inserted real task. New worked_example_md length: {len(m["worked_example_md"])}', flush=True)
    return True


for m in methods:
    code = m['method_code']
    if code not in PROBLEM2:
        continue
    we = m.get('worked_example_md','')
    tasks = we.split('### Задача')
    # Check if first task is training
    src_match = re.search(r'\*\*Источник:\*\*\s*(.+?)(?:\n|$)', tasks[1] if len(tasks)>1 else '')
    src = src_match.group(1) if src_match else ''
    is_training = 'тренировочная' in src.lower() or 'классическая задача' in src.lower() or len(tasks) <= 1

    if not is_training:
        print(f'[{code}] First task already real, skipping', flush=True)
        continue

    print(f'[{code}] Training first task detected (source: {src[:60]}), replacing...', flush=True)
    success = select_and_write_task(m)
    if success:
        with open(OUTPUT, 'w', encoding='utf-8') as f:
            json.dump(methods, f, ensure_ascii=False, indent=2)
        print(f'[{code}] SAVED after Problem 2 fix', flush=True)
    else:
        print(f'[{code}] FAILED', flush=True)

print('\nProblem 2 DONE')
print(f'\nFinal output saved to {OUTPUT}')
