
import argparse, json, os, re, time
from pathlib import Path
import requests

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
SYSTEM_RULES = """Ты генерируешь и исправляешь задачи FORMYLA.
Верни строго один JSON-объект задачи без markdown.
Поля обязательны: id, grade, method_code, difficulty, task_text, correct_answer, solution, theme, subtopic, method.
LaTeX: используй $...$, команды с обратным слешем: \\frac, \\sqrt, \\cdot, \\leq.
Шкала: L6 = регион ВсОШ, L7 = сложный регион, L8 = финал/последние задачи перечневых олимпиад.
Для L7-L8 запрещены одношаговые остатки, НОД, делители, проценты, среднее арифметическое и прямые формулы.
Для L7-L8 нужна идея + доказательство оценки/невозможности/конструкции/единственности.
Используй только методы, допустимые для указанного класса.
Ответ должен следовать из решения и быть проверяемым.
"""

BAD_WORDS = ['не удалось', 'однако ответ', 'условие задачи указано', 'решение приведено', 'заменим задачу']
EASY_HIGH = ['остаток от деления', 'наибольший общий делитель', 'сколько натуральных делителей', 'среднее арифметическое', 'один карандаш стоит']

def make_prompt(job):
    method = job.get('method_code') or 'GEN'
    grade = job.get('grade')
    diff = job.get('difficulty')
    theme = job.get('theme') or ''
    subtopic = job.get('subtopic') or ''
    task_id = job.get('id') or f"{grade}-{method}-L{diff}-{job.get('job_id','gen')}"
    quality = job.get('quality_target', 'соответствие уровню, корректность ответа и решения')

    l8_rules = ""
    if int(diff) >= 8:
        l8_rules = """
Для L8:
- уровень финала/последних задач сильной олимпиады;
- запрещены одношаговые задачи на прямую формулу;
- нужна неочевидная идея, несколько шагов и доказательство единственности/оптимальности/невозможности;
- ответ должен быть однозначным и проверяемым;
- решение должно полностью доказывать ответ.
"""

    common = f"""
Ты генерируешь задачу для базы FORMYLA.

Верни строго один JSON-объект без markdown и без текста вне JSON.

Обязательные поля:
id, grade, method_code, difficulty, task_text, correct_answer, solution, theme, subtopic, method.

Параметры:
id: {task_id}
grade: {grade}
method_code: {method}
difficulty: {diff}
theme: {theme}
subtopic: {subtopic}
method: {method}

Требование к качеству:
{quality}
{l8_rules}

Запреты:
- не используй фразы “не удалось”, “условие противоречиво”, “решение не найдено”, “заменим задачу”;
- не создавай противоречивые условия;
- не оставляй placeholder-ответы;
- не используй markdown;
- LaTeX пиши внутри строк через $...$;
- все поля JSON должны быть валидными строками/числами без обрыва кавычек.

Финальный JSON должен иметь такой вид:
{{
  "id": "{task_id}",
  "grade": {grade},
  "method_code": "{method}",
  "difficulty": {diff},
  "task_text": "...",
  "correct_answer": "...",
  "solution": "...",
  "theme": "{theme}",
  "subtopic": "{subtopic}",
  "method": "{method}"
}}
"""

    if job.get('mode') == 'fill_missing':
        return common + """

Сгенерируй НОВУЮ оригинальную корректную задачу строго по указанной теме, подтеме, классу и уровню.
"""

    return common + f"""

Замени плохую задачу новой корректной задачей с тем же id.
Причины замены: {job.get('reasons', '')}
Сохрани тот же id: {task_id}
"""

def extract_json(text):
    text = text.strip()
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r'\{.*\}', text, flags=re.S)
        if not m:
            raise ValueError('No JSON object found')
        return json.loads(m.group(0))

def repair_mojibake_str(s):
    if not isinstance(s, str):
        return s
    if any(x in s for x in ['Р', 'СЃ', 'С‚', 'вЂ', 'С‡', 'Рё']):
        try:
            return s.encode('cp1251', errors='strict').decode('utf-8', errors='strict')
        except Exception:
            return s
    return s

def repair_mojibake_obj(x):
    if isinstance(x, dict):
        return {k: repair_mojibake_obj(v) for k, v in x.items()}
    if isinstance(x, list):
        return [repair_mojibake_obj(v) for v in x]
    if isinstance(x, str):
        return repair_mojibake_str(x)
    return x

def validate_task(t):
    issues=[]
    required=['id','grade','method_code','difficulty','task_text','correct_answer','solution','theme','subtopic','method']
    for f in required:
        if f not in t or t[f] in [None,'']:
            issues.append('missing_'+f)
    s=' '.join(str(t.get(f,'')) for f in ['task_text','correct_answer','solution'])
    if s.count('$') % 2:
        issues.append('odd_dollar')
    bal=0
    for ch in s:
        if ch=='{': bal+=1
        elif ch=='}': bal-=1
        if bal<0:
            issues.append('brace_order')
            break
    if bal != 0:
        issues.append('brace_balance')
    low=s.lower()
    if any(x in low for x in BAD_WORDS):
        issues.append('bad_meta_text')
    if int(t.get('difficulty',0) or 0) >= 7:
        if len(str(t.get('solution',''))) < 260:
            issues.append('short_solution_high_level')
        if any(x in str(t.get('task_text','')).lower() for x in EASY_HIGH):
            issues.append('too_easy_template_high_level')
    return issues

def call_deepseek(prompt, model, api_key, temperature=0.7, max_tokens=2200):
    headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}
    payload = {
        'model': model,
        'messages': [{'role':'system','content':SYSTEM_RULES},{'role':'user','content':prompt}],
        'temperature': temperature,
        'max_tokens': max_tokens,
        'response_format': {'type':'json_object'}
    }
    r = requests.post(DEEPSEEK_URL, headers=headers, json=payload, timeout=120)
    r.raise_for_status()
    return r.json()['choices'][0]['message']['content']

def generate_with_retries(job, model, api_key, retries=3):
    prompt = make_prompt(job)
    last = None
    for attempt in range(1, retries+1):
        extra = '' if attempt == 1 else f"\nПредыдущая попытка была плохой: {last}. Исправь и верни только валидный JSON."
        try:
            raw = call_deepseek(prompt + extra, model, api_key)
            task = repair_mojibake_obj(extract_json(raw))
            if job['mode'] == 'replace_bad':
                task['id'] = job['id']
            else:
                task['id'] = f"{job['grade']}-{job.get('method_code','GEN')}-L{job['difficulty']}-{job['job_id']}"
            task['grade'] = job['grade']
            task['difficulty'] = job['difficulty']
            task['theme'] = job['theme']
            task['subtopic'] = job['subtopic']
            if job.get('method_code'):
                task['method_code'] = job['method_code']
                task['method'] = task.get('method') or job['method_code']
            issues = validate_task(task)
            if not issues:
                return {'status':'ok','task':task,'attempts':attempt}
            last = issues
        except Exception as e:
            last = repr(e)
        time.sleep(1.5 * attempt)
    return {'status':'failed','error':last,'job':job,'prompt':prompt}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--worker', type=int, required=True)
    ap.add_argument('--queue', default='output')
    ap.add_argument('--out', default='output/formyla_parallel/results')
    ap.add_argument('--model', default=os.getenv('DEEPSEEK_MODEL','deepseek-chat'))
    ap.add_argument('--limit', type=int, default=0, help='0 = all jobs')
    args=ap.parse_args()
    api_key=os.getenv('DEEPSEEK_API_KEY')
    if not api_key:
        raise SystemExit('Set DEEPSEEK_API_KEY env var; do not hardcode API keys.')
    jobs=json.loads(Path(args.queue, f'formyla_worker_{args.worker:02d}_jobs.json').read_text(encoding='utf-8'))['jobs']
    if args.limit:
        jobs=jobs[:args.limit]
    Path(args.out).mkdir(parents=True, exist_ok=True)
    out_path=Path(args.out, f'worker_{args.worker:02d}_results.jsonl')
    with out_path.open('w',encoding='utf-8') as out:
        for job in jobs:
            rec=generate_with_retries(job, args.model, api_key)
            rec['job_id']=job['job_id']
            out.write(json.dumps(rec,ensure_ascii=False)+'\n')
            out.flush()

if __name__ == '__main__':
    main()
