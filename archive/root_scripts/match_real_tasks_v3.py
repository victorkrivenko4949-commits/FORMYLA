import os
#!/usr/bin/env python3
"""
FORMYLA — матчинг v3: точное извлечение из базы.
Для каждого метода:
1. Фильтрует 30 задач по разделу из базы 5218
2. DeepSeek выбирает ЛУЧШУЮ (по task_uid)
3. Берёт ТОЧНОЕ условие и решение из базы
4. DeepSeek пишет только разбор «Как думать»
5. Вставляет в метод перед тренировочными примерами

Преимущество: условие и решение берутся из базы as-is, 
DeepSeek только добавляет рассуждение.
"""
import json, re, time, requests, sys, random, os
import urllib3
urllib3.disable_warnings()

session = requests.Session()
session.verify = False
API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
headers = {'Authorization': f'Bearer {API_KEY}', 'Content-Type': 'application/json'}

METHODS_FILE = sys.argv[2] if len(sys.argv) > 2 else 'all_methods_fixed.json'
TASKS_FILE = sys.argv[3] if len(sys.argv) > 3 else 'olympiad_tasks_PERFECT-3.json'
OUTPUT = sys.argv[1] if len(sys.argv) > 1 else 'all_methods_real.json'
METHOD_FILTER = sys.argv[4].split(',') if len(sys.argv) > 4 else None

with open(METHODS_FILE, 'r', encoding='utf-8') as f:
    methods = json.load(f)
with open(TASKS_FILE, 'r', encoding='utf-8') as f:
    tasks = json.load(f)

print(f'Loaded {len(methods)} methods, {len(tasks)} tasks', flush=True)

# ─── Section -> keyword filter ───
SECTION_FILTERS = {
    'A': ['числ', 'сумм', 'произвед', 'делит', 'остат', 'цифр', 'дроб', 'процент', 
          'скорост', 'работ', 'движен', 'цена', 'стоим', 'покуп', 'зарпл', 'возраст',
          'год', 'рубл', 'копеек', 'килограмм', 'метр', 'литр'],
    'B': ['логик', 'игр', 'ход', 'выигрыш', 'проигрыш', 'шахмат', 'весы', 'монет',
          'фальшив', 'правд', 'лж', 'рыцар', 'лжец', 'стратег', 'колпак', 'гном'],
    'C': ['многочлен', 'корен', 'уравнен', 'виет', 'систем', 'алгебра', 'разложен', 
          'симметр', 'коэффициент', 'степен', 'переменн', 'значен'],
    'D': ['прост', 'составн', 'делител', 'сравнен', 'модул', 'нод', 'нок',
          'эйлер', 'ферм', 'остатк', 'делимост', 'степен', 'взаимно прост', 'последн'],
    'E': ['комбинатор', 'перестановк', 'размещен', 'сочетан', 'дирихле',
          'инвариант', 'граф', 'дерев', 'цикл', 'раскрас', 'подсчет', 'количеств',
          'способ', 'разрезан', 'круг', 'окружн', 'размест', 'выбрать', 'скольк',
          'остров', 'шар', 'ящик', 'клетк'],
    'F': ['треугольник', 'окружност', 'круг', 'угол', 'площад', 'периметр',
          'подоб', 'вектор', 'координат', 'симметр', 'поворот', 'медиан',
          'биссектр', 'высот', 'касательн', 'хорд', 'секущ', 'четырехугол',
          'параллел', 'ромб', 'прямоугол', 'квадрат', 'трапец', 'прямая', 'точк'],
    'G': ['неравенств', 'коши', 'йенсен', 'среднее', 'выпукл',
          'оценк', 'максимум', 'минимум', 'докажите', 'больше', 'меньш', 'не менее',
          'не более', 'сумма'],
    'H': ['производн', 'интеграл', 'предел', 'функци', 'непрерывн', 'дифференц',
          'касательн', 'возраст', 'убыван', 'экстремум', 'график', 'наибольш', 'наименьш']
}

def filter_tasks_by_section(all_tasks, section, method_text):
    """Pre-filter tasks by section keywords + method-specific keywords."""
    kws = SECTION_FILTERS.get(section, [])
    
    # Also extract keywords from method name
    method_name = method_text.lower()
    name_words = re.findall(r'[а-яё]{4,}', method_name)
    
    scored = []
    for t in all_tasks:
        text = (t.get('text','') + ' ' + str(t.get('solution','') or '')[:200]).lower()
        section_score = sum(1 for kw in kws if kw in text)
        name_score = sum(2 for w in name_words if len(w) > 4 and w in text)
        grade = t.get('grade', 0)
        grade_score = 1 if grade in [7,8,9] else 0  # prefer middle grades
        total = section_score + name_score + grade_score
        if total > 0:
            scored.append((total, t))
    
    scored.sort(key=lambda x: x[0], reverse=True)
    return [t for _, t in scored[:50]]


SYS = """Ты — эксперт по олимпиадной математике.

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

PROMPT = """Метод: {code}: {name}
Раздел: {section}. Сложность: {difficulty}/5.

Определение: {definition}

Приёмы: {techniques}

Кандидаты (30 задач из базы):
{candidates}

Выбери ЛУЧШУЮ задачу. Верни task_uid и объяснение."""

def normalize_latex(text):
    if not text: return text
    text = re.sub(r'\\\[(.+?)\\\]', r'$$\1$$', text, flags=re.DOTALL)
    text = re.sub(r'\\\((.+?)\\\)', r'$\1$', text, flags=re.DOTALL)
    return text

def call_with_retry(url, payload, max_tokens, timeout, max_retries=100):
    """Вызывает DeepSeek API с бесконечным retry при сетевых ошибках.
    Не пропускает ни один метод — ждёт пока интернет появится."""
    attempt = 0
    while True:
        attempt += 1
        try:
            r = session.post(url, json=payload, headers=headers, timeout=timeout)
            if r.status_code == 429:
                # Rate limit — ждём дольше
                wait = min(60, 10 * attempt)
                print(f'      Rate limit (429), жду {wait}с... (попытка {attempt})', flush=True)
                time.sleep(wait)
                continue
            if r.status_code >= 500:
                # Серверная ошибка — повторяем
                wait = min(60, 5 * attempt)
                print(f'      Серверная ошибка {r.status_code}, жду {wait}с... (попытка {attempt})', flush=True)
                time.sleep(wait)
                continue
            if r.status_code != 200:
                wait = min(30, 3 * attempt)
                print(f'      HTTP {r.status_code}, жду {wait}с... (попытка {attempt})', flush=True)
                time.sleep(wait)
                continue
            
            d = r.json()
            c = d['choices'][0]['message'].get('content','') or ''
            finish = d['choices'][0].get('finish_reason','')
            
            if not c and finish == 'length':
                new_max = min(int(max_tokens * 1.5), 32000)
                if new_max > max_tokens:
                    print(f'      Пустой ответ (finish=length), увеличиваю токены {max_tokens}->{new_max}', flush=True)
                    payload['max_tokens'] = new_max
                    max_tokens = new_max
                    time.sleep(2)
                    continue
            
            if not c:
                print(f'      Пустой ответ, retry через 5с... (попытка {attempt})', flush=True)
                time.sleep(5)
                continue
            
            return c, d.get('usage', {})
            
        except requests.exceptions.ConnectionError as e:
            wait = min(120, 10 * (attempt if attempt < 12 else 12))
            print(f'      НЕТ ИНТЕРНЕТА: {str(e)[:80]}', flush=True)
            print(f'      Жду {wait}с и повторяю... (попытка {attempt})', flush=True)
            time.sleep(wait)
            # Сбрасываем счётчик через час попыток
            if attempt % 360 == 0:
                attempt = 0
            continue
        except requests.exceptions.Timeout:
            wait = min(60, 5 * attempt)
            print(f'      Timeout, жду {wait}с... (попытка {attempt})', flush=True)
            time.sleep(wait)
            continue
        except Exception as e:
            wait = min(60, 5 * attempt)
            print(f'      Ошибка: {str(e)[:80]}, жду {wait}с... (попытка {attempt})', flush=True)
            time.sleep(wait)
            continue
    # unreachable, но на всякий случай
    return '', {}

# ─── Main ───
# Load existing output to skip already-processed methods
existing = {}
if os.path.exists(OUTPUT):
    with open(OUTPUT, 'r', encoding='utf-8') as f:
        existing_data = json.load(f)
        existing = {m['method_code']: m for m in existing_data}
    print(f'Loaded {len(existing)} existing entries from {OUTPUT}', flush=True)

to_process = []
for m in methods:
    if METHOD_FILTER and m['method_code'] not in METHOD_FILTER:
        continue
    # Skip if already has a real task (first task not training)
    if m['method_code'] in existing:
        we = existing[m['method_code']].get('worked_example_md','')
        if 'тренировочная' not in we[:500]:
            print(f'[{m["method_code"]}] already has real task, skip', flush=True)
            continue
    to_process.append(m)

print(f'Processing {len(to_process)} methods', flush=True)

stats = {'ok': 0, 'no_match': 0, 'failed': 0}

# Use existing data as base
methods_map = {m['method_code']: m for m in methods}
for code, ex in existing.items():
    if code in methods_map:
        methods_map[code] = ex
methods = [methods_map[m['method_code']] for m in methods]

for m in to_process:
    code = m['method_code']
    name = m['method_name']
    section = m.get('section','')
    print(f'[{code}] {name}', flush=True)
    
    # Get method text for scoring
    method_text = name + ' ' + m.get('definition_md','')[:300]
    
    # Filter and sample 30 candidates
    candidates = filter_tasks_by_section(tasks, section, method_text)
    if not candidates:
        candidates = random.sample(tasks, min(30, len(tasks)))
    sample = candidates[:30] if len(candidates) >= 30 else candidates
    
    # Build candidates text
    cand_text = ""
    for i, t in enumerate(sample):
        cand_text += f"\n[{i+1}] task_uid: {t.get('task_uid','?')}\n"
        cand_text += f"    source: {t.get('source_name','?')}\n"
        cand_text += f"    grade: {t.get('grade','?')}\n"
        cand_text += f"    text: {t.get('text','')[:300]}\n"
    
    # Step 1: Select best task
    select_payload = {
        'model': 'deepseek-v4-pro',
        'messages': [{'role':'system','content':SYS},{'role':'user','content':PROMPT.format(
            code=code, name=name, section=section,
            difficulty=m.get('difficulty_level','?'),
            definition=m.get('definition_md','')[:500],
            techniques=m.get('typical_techniques_md','')[:400],
            candidates=cand_text
        )}],
        'max_tokens': 4000, 'temperature': 0.3,
    }
    
    selection, usage1 = call_with_retry('https://api.deepseek.com/chat/completions', select_payload, 4000, 300)
    if not selection:
        print(f'  FAILED: no selection', flush=True)
        stats['failed'] += 1
        continue
    
    # Extract task_uid
    uid_match = re.search(r'task_uid:\s*(\S+)', selection)
    if not uid_match:
        print(f'  FAILED: no uid found in: {selection[:100]}', flush=True)
        stats['failed'] += 1
        continue
    
    uid = uid_match.group(1).strip()
    
    # Find the task in database
    selected_task = next((t for t in tasks if t.get('task_uid') == uid), None)
    if not selected_task:
        print(f'  FAILED: uid {uid[:20]} not in database', flush=True)
        stats['failed'] += 1
        continue
    
    print(f'  Selected: {selected_task["source_name"]}', flush=True)
    print(f'  Text: {selected_task["text"][:100]}', flush=True)
    
    # Step 2: Write analysis using the OFFICIAL solution from database
    sys2 = 'Ты — эксперт по олимпиадной математике и методист.\nНапиши разбор задачи в формате методической статьи.\nLaTeX: $...$ и $$...$$. НЕ меняй условие и решение — только добавь рассуждение.'
    
    prompt2 = f"""Метод: {code}: {name}

Определение метода: {m.get('definition_md','')[:400]}

Задача (РЕАЛЬНАЯ, из базы):
{selected_task.get('text','')}

Официальное решение:
{str(selected_task.get('solution','') or '')[:3000]}

Ответ: {str(selected_task.get('answer','') or '')}

Напиши разбор в формате:
### Задача 1. [точная формулировка из условия выше]
**Источник:** {selected_task.get('source_name','?')}
**Как думать (рассуждение ученика):**
1. *Что я вижу?*
2. *Какой триггер сработал?* (свяжи с методом {code})
3. *Первый ход?*
4. *Ключевая идея?*
**Решение:**
[перепиши решение с формулами $...$, добавь пояснения]
**Ответ:** [ответ]
**Что было главным:** [ключевой вывод метода]

Верни ТОЛЬКО текст разбора."""
    
    analysis_payload = {
        'model': 'deepseek-v4-pro',
        'messages': [{'role':'system','content':sys2},{'role':'user','content':prompt2}],
        'max_tokens': 8000, 'temperature': 0.3,
    }
    
    analysis, usage2 = call_with_retry('https://api.deepseek.com/chat/completions', analysis_payload, 8000, 600)
    
    if not analysis:
        print(f'  FAILED: no analysis', flush=True)
        stats['failed'] += 1
        continue
    
    analysis = normalize_latex(analysis)
    
    # Insert real task BEFORE existing examples
    existing = m.get('worked_example_md','')
    m['worked_example_md'] = analysis + '\n\n' + existing
    
    stats['ok'] += 1
    total_tokens = usage1.get('total_tokens',0) + usage2.get('total_tokens',0)
    print(f'  OK: {len(analysis)} chars, {total_tokens} tokens', flush=True)
    
    # Save after each method
    with open(OUTPUT, 'w', encoding='utf-8') as f:
        json.dump(methods, f, ensure_ascii=False, indent=2)

print(f'\nDone! ok={stats["ok"]}, no_match={stats["no_match"]}, failed={stats["failed"]}', flush=True)
print(f'Saved to {OUTPUT}', flush=True)
