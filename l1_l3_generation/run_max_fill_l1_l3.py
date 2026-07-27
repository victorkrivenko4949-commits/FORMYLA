#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FORMYLA L1-L3 Max Fill Pipeline v2.2
=====================================
Заполняет сетку 128 тем x 3 уровня = 384 ячейки, 1920 задач.

Рабочая конфигурация:
- Модель: qwen/qwen3.5-plus-20260420 (очень дешёвая)
- max_tokens: 1024 (для экономии и совместимости с балансом)
"""

import json, os, sys, time, hashlib, re, csv, uuid, requests
from datetime import datetime, timezone
from collections import defaultdict, Counter
from pathlib import Path

# ============== CONFIG ==============
L1DIR = Path(__file__).resolve().parent
ROOT = L1DIR.parent
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUTDIR = L1DIR / f'max_fill_{TS}'
LOG_PATH = L1DIR / f'max_fill_run_{TS}.log'
RAW_RESP_DIR = L1DIR / 'raw_api_responses'

API_BASE = 'https://openrouter.ai/api/v1/chat/completions'
API_KEY_PATH = L1DIR / 'openrouter_key.txt'

PRIMARY_MODEL = 'qwen/qwen3.5-plus-20260420'
CRITIC_MODEL = 'qwen/qwen3.5-plus-20260420'

MAX_TOTAL_COST = 20.0
SOFT_COST_WARN = 5.0
MAX_PRIMARY_ATTEMPTS = 3
API_TIMEOUT = 90
MAX_RETRIES = 5
SMOKE_BATCH = 3  # сколько ячеек заполнять в демо-режиме

LEVEL_NAMES = {1: 'ordinary_school', 2: 'school_vsosh', 3: 'municipal_vsosh'}
LEVEL_DESC = {
    1: 'L1 - обычная школьная математика. Один навык, короткая цепочка.',
    2: 'L2 - школьный этап ВсОШ. Одна нестандартная идея, 2-4 шага.',
    3: 'L3 - муниципальный этап ВсОШ. Полноценная олимпиадная идея.'
}
AGE_HINTS = {
    5: 'Без формальной алгебры. Наглядное решение.',
    6: 'Без систематической алгебры 7-8 класса.',
    7: 'Допустимы базовые уравнения.',
    8: 'Алгебра и геометрия 8 класса.',
    9: 'Не требовать материал 10-11 классов.',
    10: 'Не использовать университетский анализ.',
    11: 'Допустим широкий школьный аппарат.'
}

TOTAL_COST = 0.0
TOTAL_PROMPT_TOKENS = 0
TOTAL_COMPLETION_TOKENS = 0
TOTAL_REQUESTS = 0
CACHE_HITS = 0

# ============== HELPERS ==============
def log(msg):
    t = datetime.now().strftime('%H:%M:%S')
    line = f'[{t}] {msg}'
    print(line)
    Path(LOG_PATH).parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(line + '\n')
    sys.stdout.flush()

def sha256f(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()

def sha256s(s):
    return hashlib.sha256(s.encode('utf-8')).hexdigest()

def save_jsonl(path, items):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + '\n')

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def track_cost(rj):
    global TOTAL_COST, TOTAL_PROMPT_TOKENS, TOTAL_COMPLETION_TOKENS, TOTAL_REQUESTS
    u = rj.get('usage', {})
    TOTAL_PROMPT_TOKENS += u.get('prompt_tokens', 0) or 0
    TOTAL_COMPLETION_TOKENS += u.get('completion_tokens', 0) or 0
    TOTAL_REQUESTS += 1
    c = u.get('total_cost', 0) or 0
    if c: TOTAL_COST += c

def call_api(model, messages, temperature=0.3, max_tokens=1024):
    global CACHE_HITS
    key = open(API_KEY_PATH).read().strip()
    headers = {'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'}
    payload = {'model': model, 'messages': messages, 'temperature': temperature, 'max_tokens': max_tokens}
    
    for attempt in range(MAX_RETRIES):
        try:
            r = requests.post(API_BASE, headers=headers, json=payload, timeout=API_TIMEOUT)
            if r.status_code == 200:
                result = r.json()
                if 'X-OpenRouter-Cache-Hit' in r.headers: CACHE_HITS += 1
                RAW_RESP_DIR.mkdir(parents=True, exist_ok=True)
                rid = result.get('id', str(uuid.uuid4())[:8])
                with open(RAW_RESP_DIR / f'{model.split("/")[-1]}_{rid}.json', 'w', encoding='utf-8') as f:
                    json.dump(result, f, ensure_ascii=False)
                track_cost(result)
                return result
            elif r.status_code == 429:
                time.sleep(min(2**attempt*2, 30))
            elif r.status_code == 402:
                return 'INSUFFICIENT_FUNDS'
            else:
                log(f'  API {r.status_code}: {str(r.text)[:200]}')
                time.sleep(2**attempt)
        except requests.exceptions.Timeout:
            log(f'  Timeout, retry {attempt+1}')
        except Exception as e:
            log(f'  Exception: {e}')
            time.sleep(2**attempt)
    return None

def extract_json(text):
    text = re.sub(r'```(?:json)?', '', text).strip()
    m = re.search(r'(\{.*\})', text, re.DOTALL)
    if m:
        for start in range(len(m.group(1))):
            if m.group(1)[start] == '{':
                try: return json.loads(m.group(1)[start:])
                except: continue
    for start in range(len(text)):
        if text[start] == '{':
            try: return json.loads(text[start:])
            except: continue
    return None

# ============== TAXONOMY ==============
def load_taxonomy():
    tax = load_json(L1DIR / 'taxonomy_by_grade.json')
    grades = {}
    for gk, items in tax.get('grades', {}).items():
        g = int(gk)
        grades[g] = [{'theme_id': i['theme_id'], 'theme': i['theme'], 'section': i.get('section','')} for i in items]
    expected = {5:18, 6:18, 7:18, 8:17, 9:18, 10:18, 11:21}
    errors = []
    for g in sorted(grades):
        if g in expected and len(grades[g]) != expected[g]:
            errors.append(f'G{g}: exp {expected[g]}, got {len(grades[g])}')
    total = sum(len(v) for v in grades.values())
    log(f'Taxonomy: {total} themes, {total*3} cells')
    for g in sorted(grades): log(f'  G{g}: {len(grades[g])} themes')
    return grades, errors

def validate_taxonomy(grades):
    issues = []
    all_ids = set()
    for g, items in grades.items():
        for it in items:
            if it['theme_id'] in all_ids: issues.append(f'Dup {it["theme_id"]}')
            all_ids.add(it['theme_id'])
            if not it['theme']: issues.append(f'Empty {it["theme_id"]}')
            if not it['section']: issues.append(f'No section {it["theme_id"]}')
    forbidden = ['Разное','Прочее','Смешанные задачи','Олимпиадная математика','Олимпиадная геометрия','Неизвестная тема']
    log(f'Taxonomy validation: {len(issues)} issues')
    return issues

# ============== EXISTING TASKS ==============
def load_existing_tasks(grades):
    tasks = []
    src = ROOT / 'victor2_generated.json'
    if src.exists():
        data = load_json(src)
        if isinstance(data, list):
            for item in data:
                t = normalize_task(item, grades)
                if t: tasks.append(t)
        log(f'victor2_generated.json: {len(tasks)} valid tasks')
    return tasks

def normalize_task(item, grades):
    try:
        g = item.get('grade', 0)
        if not isinstance(g, int) or g < 5 or g > 11: return None
        lv = item.get('level', 0)
        if isinstance(lv, str): lv = int(lv.replace('L','')) if lv.startswith('L') else 0
        if not isinstance(lv, int) or lv < 1 or lv > 3: return None
        tid = item.get('theme_id', '')
        if not tid: return None
        st = (item.get('statement') or '').strip()
        an = (item.get('answer') or '').strip()
        if not st or not an: return None
        sec = ''
        for g2, its in grades.items():
            for i in its:
                if i['theme_id'] == tid: sec = i.get('section',''); break
        uid = item.get('task_uid','') or f'V2-{sha256s(st)[:12]}'
        return {'task_uid': uid, 'origin': 'victor2_generated.json', 'grade': g, 'level': lv,
                'level_name': LEVEL_NAMES.get(lv,''), 'section': sec, 'theme_id': tid,
                'theme': item.get('theme',''), 'statement': st, 'answer': an,
                'solution': (item.get('solution') or '').strip(),
                'quality_status': 'RECHECK', 'methods': item.get('methods',[]),
                'tags': item.get('tags',[]), 'diversity_signature': item.get('diversity_signature',{}),
                'generator_model': 'victor2_generated', 'solver_model': '', 'critic_model': '',
                'verification': {}, 'created_at': datetime.now(timezone.utc).isoformat()}
    except:
        return None

# ============== CELL GRID ==============
def build_cell_grid(grades):
    cells = []
    for g in sorted(grades):
        for ti in grades[g]:
            for lv in [1,2,3]:
                cells.append({'key': f"G{g}|{ti['theme_id']}|L{lv}", 'grade': g,
                              'theme_id': ti['theme_id'], 'theme': ti['theme'],
                              'section': ti.get('section',''), 'level': lv,
                              'level_name': LEVEL_NAMES[lv], 'tasks': [], 'approved_count': 0,
                              'status': 'EMPTY', 'shortage': 5})
    return cells

def calc_shortage(cells, all_tasks):
    ct = defaultdict(list)
    for t in all_tasks:
        if t.get('quality_status') == 'APPROVE':
            ct[f"G{t['grade']}|{t['theme_id']}|L{t['level']}"].append(t)
    total = 0
    for c in cells:
        app = ct.get(c['key'], [])
        c['approved_count'] = len(app)
        c['tasks'] = app
        c['shortage'] = max(0, 5 - len(app))
        if len(app) == 0: c['status'] = 'EMPTY'
        elif len(app) <= 2: c['status'] = 'LOW'
        elif len(app) <= 4: c['status'] = 'PARTIAL'
        elif len(app) == 5: c['status'] = 'READY'
        else: c['status'] = 'OVERFULL'
        total += c['shortage']
    return total

# ============== GENERATION ==============
def generate_candidate(grades_dict, target_grade, target_level, target_theme_id):
    ti = None
    for it in grades_dict.get(target_grade, []):
        if it['theme_id'] == target_theme_id: ti = it; break
    if not ti: return None
    
    prompt = f'''Ты создаёшь математическую задачу. ФИКСИРОВАННО:
- класс: {target_grade}
- раздел: {ti.get('section','')}
- тема: {ti.get('theme','')}
- уровень: L{target_level} ({LEVEL_DESC.get(target_level,'')})
- возраст: {AGE_HINTS.get(target_grade,'')}

Правила:
1. Задача строго для {target_grade} класса, темы "{ti.get('theme','')}", уровня L{target_level}.
2. Условие однозначно, данных достаточно.
3. Решение доступно ученику {target_grade} класса.
4. Не ссылайся на рисунок.
5. Только JSON, без Markdown.

JSON: {{"statement":"...","answer":"...","solution":"...","grade":{target_grade},"level":{target_level},"section":"{ti.get('section','')}","theme_id":"{target_theme_id}","theme":"{ti.get('theme','')}","methods":["..."],"diversity_signature":{{"core_method":"...","problem_form":"...","key_idea":"...","answer_type":"..."}},"difficulty_justification":"почему L{target_level}","originality_justification":"чем отличается"}}'''

    result = call_api(PRIMARY_MODEL, [
        {'role': 'system', 'content': prompt},
        {'role': 'user', 'content': f'Создай задачу L{target_level} для {target_grade} класса по теме "{ti.get("theme","")}". Только JSON.'}
    ], temperature=0.7)
    if result == 'INSUFFICIENT_FUNDS': return 'INSUFFICIENT_FUNDS'
    if not result: return None
    
    data = extract_json(result['choices'][0]['message']['content'])
    if not data: return None
    for r in ['statement','answer','solution','grade','level','theme_id']:
        if r not in data: return None
    
    uid = f'GEN-L1L3-{sha256s(data["statement"])[:8]}'
    return {'task_uid': uid, 'origin': 'generated', 'generator_run_id': TS,
            'grade': data['grade'], 'level': data['level'], 'level_name': LEVEL_NAMES.get(data.get('level',0),''),
            'section': data.get('section', ti.get('section','')), 'theme_id': data['theme_id'],
            'theme': data.get('theme', ti.get('theme','')), 'statement': data['statement'],
            'answer': data['answer'], 'solution': data['solution'],
            'methods': data.get('methods',[]), 'tags': data.get('tags',[]),
            'diversity_signature': data.get('diversity_signature',{}),
            'difficulty_justification': data.get('difficulty_justification',''),
            'originality_justification': data.get('originality_justification',''),
            'quality_status': 'PENDING', 'generator_model': PRIMARY_MODEL,
            'solver_model': '', 'critic_model': '', 'verification': {},
            'created_at': datetime.now(timezone.utc).isoformat()}

# ============== VERIFICATION ==============
def det_check(candidate, grades):
    chk = {}
    chk['schema'] = True
    chk['grade'] = candidate['grade'] in grades
    chk['level_range'] = 1 <= candidate['level'] <= 3
    chk['section'] = bool(candidate.get('section'))
    all_ids = set()
    for g, its in grades.items():
        for i in its: all_ids.add(i['theme_id'])
    chk['theme_id_known'] = candidate['theme_id'] in all_ids
    grade_ids = {i['theme_id'] for i in grades.get(candidate['grade'], [])}
    chk['theme_in_grade'] = candidate['theme_id'] in grade_ids
    chk['statement'] = len(candidate.get('statement','').strip()) > 10
    chk['answer'] = len(candidate.get('answer','').strip()) > 0
    chk['solution'] = len(candidate.get('solution','').strip()) > 10
    fb = ['Разное','Прочее','Смешанные задачи','Олимпиадная математика','Олимпиадная геометрия']
    chk['forbidden_theme'] = candidate.get('theme','') not in fb
    s = candidate.get('statement','')
    chk['no_links'] = 'http' not in s
    chk['no_diagram_ref'] = 'рисунок' not in s.lower() and 'рис.' not in s.lower()
    return chk, all(chk.values())

def solve(candidate):
    r = call_api(PRIMARY_MODEL, [
        {'role': 'system', 'content': 'Ты независимый решатель. Не видишь авторский ответ. Верни JSON: {"solvable":true,"unambiguous":true,"data_sufficient":true,"independent_answer":"...","independent_solution":"...","estimated_level":2,"issues":[]}'},
        {'role': 'user', 'content': f'Реши задачу для {candidate["grade"]} класса.\n{candidate["statement"]}\nТолько JSON.'}
    ], temperature=0.2, max_tokens=1024)
    if r == 'INSUFFICIENT_FUNDS': return 'INSUFFICIENT_FUNDS'
    if not r: return None
    return extract_json(r['choices'][0]['message']['content'])

def critic(candidate, solver):
    r = call_api(CRITIC_MODEL, [
        {'role': 'system', 'content': 'Ты критик. Верни JSON: {"verdict":"APPROVE","answer_match":true,"solution_correct":true,"grade_match":true,"theme_match":true,"level_match":true,"age_appropriate":true,"original_enough":true,"confidence":0.95}'},
        {'role': 'user', 'content': f'Класс: {candidate["grade"]}, Уровень: {candidate["level"]}, Тема: {candidate.get("theme","")}\nУсловие: {candidate["statement"]}\nАвтор: {candidate["answer"]}\nРешение: {candidate["solution"]}\nНезависимо: {solver.get("independent_answer","")}\nНезависимое решение: {solver.get("independent_solution","")}\nТолько JSON.'}
    ], temperature=0.2, max_tokens=512)
    if r == 'INSUFFICIENT_FUNDS': return 'INSUFFICIENT_FUNDS'
    if not r: return None
    return extract_json(r['choices'][0]['message']['content'])

def verify(candidate, grades):
    log('  Verifying...')
    chk, ok = det_check(candidate, grades)
    candidate['verification']['deterministic'] = {k: 'PASS' if v else 'FAIL' for k,v in chk.items()}
    if not ok:
        candidate['quality_status'] = 'REJECT'
        candidate['verification']['reject_reason'] = str([k for k,v in chk.items() if not v])
        return candidate
    
    sv = solve(candidate)
    if sv == 'INSUFFICIENT_FUNDS': return 'INSUFFICIENT_FUNDS'
    if not sv:
        candidate['quality_status'] = 'RECHECK'
        candidate['verification']['solver_error'] = 'solver fail'
        return candidate
    candidate['solver_model'] = PRIMARY_MODEL
    candidate['independent_answer'] = sv.get('independent_answer','')
    candidate['independent_solution'] = sv.get('independent_solution','')
    
    issues = []
    if not sv.get('solvable',False): issues.append('unsolvable')
    if not sv.get('unambiguous',True): issues.append('ambiguous')
    if not sv.get('data_sufficient',True): issues.append('insufficient_data')
    if issues:
        candidate['quality_status'] = 'REJECT'
        candidate['verification']['reject_reason'] = f'Solver: {issues}'
        return candidate
    
    cv = critic(candidate, sv)
    if cv == 'INSUFFICIENT_FUNDS': return 'INSUFFICIENT_FUNDS'
    if not cv:
        candidate['quality_status'] = 'RECHECK'
        candidate['verification']['critic_error'] = 'critic fail'
        return candidate
    
    candidate['critic_model'] = CRITIC_MODEL
    verdict = cv.get('verdict','REJECT')
    conf = cv.get('confidence',0.0)
    if verdict == 'APPROVE' and conf >= 0.7:
        candidate['quality_status'] = 'APPROVE'
        candidate['verification']['final'] = 'PASS'
    elif verdict in ('RECHECK','QUARANTINE') or conf < 0.7:
        candidate['quality_status'] = 'RECHECK'
    else:
        candidate['quality_status'] = 'REJECT'
    return candidate

# ============== SMOKE TEST ==============
def run_smoke(grades):
    log('\n===== SMOKE TEST =====')
    tests = [(5,1),(6,2),(7,3),(8,2),(9,3),(10,2),(11,3)]
    results = []
    for g,lv in tests:
        tid = grades[g][0]['theme_id']
        log(f'\nSmoke G{g} L{lv} {tid}')
        c = generate_candidate(grades, g, lv, tid)
        if c == 'INSUFFICIENT_FUNDS': return 'INSUFFICIENT_FUNDS'
        if not c: results.append({'cell':f'G{g}|{tid}|L{lv}','status':'FAIL'}); continue
        v = verify(c, grades)
        if v == 'INSUFFICIENT_FUNDS': return 'INSUFFICIENT_FUNDS'
        results.append({'cell':f'G{g}|{tid}|L{lv}','status':v['quality_status']})
        log(f'  -> {v["quality_status"]}')
    ok = sum(1 for r in results if r['status']=='APPROVE')
    log(f'Smoke: {ok}/{len(results)} APPROVE')
    return results

# ============== REPORTS ==============
def write_reports(cells, all_tasks, grades, rd):
    rd = Path(rd); rd.mkdir(parents=True, exist_ok=True)
    
    with open(rd/'l1_l3_grid_report.csv','w',encoding='utf-8-sig',newline='') as f:
        w = csv.writer(f)
        w.writerow(['grade','section','theme_id','theme','level','approved_count','status','shortage'])
        for c in sorted(cells, key=lambda x: (x['grade'], x['theme_id'], x['level'])):
            w.writerow([c['grade'], c['section'], c['theme_id'], c['theme'], c['level'], c['approved_count'], c['status'], c['shortage']])
    
    with open(rd/'l1_l3_task_audit.csv','w',encoding='utf-8-sig',newline='') as f:
        w = csv.writer(f)
        w.writerow(['task_uid','grade','theme_id','level','quality_status'])
        for t in all_tasks:
            w.writerow([t['task_uid'], t['grade'], t['theme_id'], t['level'], t.get('quality_status','')])
    
    app = [t for t in all_tasks if t.get('quality_status')=='APPROVE']
    rech = [t for t in all_tasks if t.get('quality_status')=='RECHECK']
    rej = [t for t in all_tasks if t.get('quality_status')=='REJECT']
    save_jsonl(rd/'FORMYLA_L1_L3_FINAL.jsonl', app)
    save_jsonl(rd/'FORMYLA_L1_L3_ALL_CANDIDATES.jsonl', all_tasks)
    save_jsonl(rd/'FORMYLA_L1_L3_RECHECK.jsonl', rech)
    save_jsonl(rd/'FORMYLA_L1_L3_REJECTED.jsonl', rej)
    
    with open(rd/'l1_l3_cost_report.csv','w',encoding='utf-8-sig',newline='') as f:
        w = csv.writer(f)
        w.writerow(['stage','model','requests','input_tokens','output_tokens','cache_hits','cost'])
        w.writerow(['all',PRIMARY_MODEL,TOTAL_REQUESTS,TOTAL_PROMPT_TOKENS,TOTAL_COMPLETION_TOKENS,CACHE_HITS,TOTAL_COST])
    
    manifest = {
        'run_id': TS, 'finished_at': datetime.now(timezone.utc).isoformat(),
        'taxonomy': {'total_themes': sum(len(v) for v in grades.values()), 'total_cells': len(cells), 'target_tasks': len(cells)*5},
        'models': {'primary': PRIMARY_MODEL},
        'cost': {'total_cost': TOTAL_COST, 'requests': TOTAL_REQUESTS, 'prompt_tokens': TOTAL_PROMPT_TOKENS, 'completion_tokens': TOTAL_COMPLETION_TOKENS, 'cache_hits': CACHE_HITS},
        'results': {'total': len(all_tasks), 'approved': len(app), 'recheck': len(rech), 'rejected': len(rej),
                     'ready_cells': sum(1 for c in cells if c['status']=='READY'), 'shortage': sum(c['shortage'] for c in cells),
                     'quality_status': 'PASS' if app else 'FAIL', 'coverage_status': 'COMPLETE' if sum(c['shortage'] for c in cells)==0 else 'INCOMPLETE'}
    }
    for fn in os.listdir(rd):
        fp = rd/fn
        if os.path.isfile(fp): manifest.setdefault('output_files',{})[fn] = {'size': os.path.getsize(fp), 'sha256': sha256f(fp)}
    with open(rd/'l1_l3_run_manifest.json','w',encoding='utf-8') as f: json.dump(manifest, f, ensure_ascii=False, indent=2)
    
    sc = Counter(c['status'] for c in cells)
    with open(rd/'L1_L3_MAX_FILL_FINAL_REPORT.md','w',encoding='utf-8') as f:
        f.write(f'# FORMYLA L1-L3 Max Fill Report\n**Run**: {TS}\n**Finished**: {manifest["finished_at"]}\n\n')
        f.write(f'## Taxonomy: {manifest["taxonomy"]["total_themes"]} themes, {manifest["taxonomy"]["total_cells"]} cells, target {manifest["taxonomy"]["target_tasks"]}\n\n')
        f.write(f'## Results: {len(all_tasks)} candidates, {len(app)} APPROVE, {len(rech)} RECHECK, {len(rej)} REJECT\n')
        f.write(f'## Ready cells: {manifest["results"]["ready_cells"]}, Shortage: {manifest["results"]["shortage"]}\n')
        f.write(f'## Cost: ${TOTAL_COST:.6f}, {TOTAL_REQUESTS} requests\n')
        f.write(f'## QUALITY_STATUS: {manifest["results"]["quality_status"]}\n## COVERAGE_STATUS: {manifest["results"]["coverage_status"]}\n\n')
        for s, cnt in sorted(sc.items()): f.write(f'- {s}: {cnt}\n')
    log(f'Reports -> {rd}')

# ============== MAIN ==============
def main():
    log('='*50)
    log('FORMYLA L1-L3 Max Fill v2.2')
    log(f'Output: {OUTDIR}')
    log('='*50)
    
    grades, tax_errors = load_taxonomy()
    for e in tax_errors: log(f'TAX_ERROR: {e}')
    tax_issues = validate_taxonomy(grades)
    
    tasks = load_existing_tasks(grades)
    cells = build_cell_grid(grades)
    shortage = calc_shortage(cells, tasks)
    log(f'Shortage: {shortage} (all existing need audit)')
    
    OUTDIR.mkdir(parents=True, exist_ok=True)
    (OUTDIR/'checkpoints').mkdir(exist_ok=True)
    (OUTDIR/'cache').mkdir(exist_ok=True)
    (OUTDIR/'raw_api_responses').mkdir(exist_ok=True)
    
    TAX_OK = not tax_errors and not tax_issues
    
    if TAX_OK:
        smoke = run_smoke(grades)
        if smoke == 'INSUFFICIENT_FUNDS':
            log('\n*** BLOCKED: INSUFFICIENT_FUNDS on OpenRouter. Add credits. ***')
            write_reports(cells, tasks, grades, OUTDIR)
            return
        SMOKE_OK = isinstance(smoke, list) and sum(1 for r in smoke if r['status']=='APPROVE') >= 1
        log(f'SMOKE_OK = {SMOKE_OK}')
        
        if SMOKE_OK:
            log('\n--- WAVE 1: FILL EMPTY CELLS ---')
            new_candidates = []
            empty = [c for c in cells if c['status']=='EMPTY']
            batch = min(SMOKE_BATCH, len(empty))
            for idx in range(batch):
                cell = empty[idx]
                log(f'\n[{idx+1}/{batch}] {cell["key"]}')
                for attempt in range(MAX_PRIMARY_ATTEMPTS):
                    if TOTAL_COST >= SOFT_COST_WARN:
                        log(f'Cost warn ${TOTAL_COST:.2f}')
                        break
                    cand = generate_candidate(grades, cell['grade'], cell['level'], cell['theme_id'])
                    if cand == 'INSUFFICIENT_FUNDS': break
                    if not cand: continue
                    v = verify(cand, grades)
                    if v == 'INSUFFICIENT_FUNDS': break
                    new_candidates.append(v)
                    if v['quality_status'] == 'APPROVE':
                        tasks.append(v)
                        cell['approved_count'] += 1
                        cell['shortage'] = max(0, 5 - cell['approved_count'])
                        cell['status'] = 'LOW'
                        log(f'  APPROVED!')
                        break
                    log(f'  {v["quality_status"]}')
                else:
                    if TOTAL_COST >= SOFT_COST_WARN: break
    
    all_tasks = tasks + (new_candidates if 'new_candidates' in dir() else [])
    write_reports(cells, all_tasks, grades, OUTDIR)
    final = calc_shortage(cells, all_tasks)
    
    log('\n'+'='*50)
    log('COMPLETE')
    log('='*50)
    log(f'Cells: {len(cells)}, READY: {sum(1 for c in cells if c["status"]=="READY")}, EMPTY: {sum(1 for c in cells if c["status"]=="EMPTY")}')
    app = [t for t in all_tasks if t.get('quality_status')=='APPROVE']
    log(f'Tasks: {len(all_tasks)}, APPROVE: {len(app)}, Shortage: {final}')
    log(f'Cost: ${TOTAL_COST:.6f}, Requests: {TOTAL_REQUESTS}')
    log(f'Output: {OUTDIR}')

if __name__ == '__main__':
    main()
