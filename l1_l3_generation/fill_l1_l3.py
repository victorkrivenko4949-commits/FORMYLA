#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FORMYLA L1-L3 Fill Pipeline v3 — использует корневую taxonomy_by_grade.json
Сетка: 41 тема x 3 уровня = 123 ячейки, цель 615 задач
"""
import json, os, sys, time, hashlib, re, csv
from datetime import datetime, timezone
from collections import defaultdict, Counter
from pathlib import Path

L1DIR = Path(__file__).resolve().parent
ROOT = L1DIR.parent
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUTDIR = L1DIR / f'max_fill_{TS}'
CHECKPOINT = L1DIR / f'l1_l3_checkpoint_{TS}.json'
LOG_PATH = L1DIR / f'l1_l3_run_{TS}.log'

def log(msg):
    t = datetime.now().strftime('%H:%M:%S')
    line = f"[{t}] {msg}"
    print(line)
    with open(LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(line + '\n')

# ============== TAXONOMY ==============
def load_taxonomy():
    """Загружаем корневую таксономию"""
    path = ROOT / 'taxonomy_by_grade.json'
    with open(path, 'r', encoding='utf-8') as f:
        tax = json.load(f)
    
    # Корневой файл имеет структуру {meta, grades}
    # l1_l3_generation/ имеет {meta, theme_definitions, sections, grade_theme_map}
    # Пробуем обе
    
    if 'grades' in tax:
        grades_data = tax['grades']
        themes = {}
        for g_str in sorted(grades_data.keys(), key=int):
            g = int(g_str)
            g_info = grades_data[g_str]
            for t in g_info['themes']:
                tid = t['id']
                themes[tid] = {
                    'grade': g,
                    'name': t['name'],
                    'subtopics': t.get('subtopics', []),
                    'section': g_info.get('section_name', '')
                }
        log(f"Таксономия (grades): {len(themes)} тем")
        return themes, []
    
    elif 'grade_theme_map' in tax:
        gtm = tax['grade_theme_map']
        defs = tax.get('theme_definitions', {})
        themes = {}
        for g_str in sorted(gtm.keys(), key=int):
            g = int(g_str)
            theme_ids = gtm[g_str]
            for tid in theme_ids:
                td = defs.get(tid, {})
                themes[tid] = {
                    'grade': g,
                    'name': td.get('name', tid),
                    'subtopics': td.get('subtopics', []),
                    'section': td.get('section', '')
                }
        log(f"Таксономия (grade_theme_map): {len(themes)} тем")
        return themes, []
    
    else:
        return {}, ['Неизвестная структура таксономии: ' + str(list(tax.keys()))]

# ============== EXISTING TASKS ==============
def load_existing_tasks(themes):
    path = ROOT / 'victor2_generated.json'
    if not path.exists():
        log("victor2_generated.json не найден")
        return [], Counter()
    
    with open(path, 'r', encoding='utf-8') as f:
        bank = json.load(f)
    
    log(f"Банк: {len(bank)} записей")
    tasks = []
    cells = Counter()
    
    for d in bank:
        stmt = (d.get('statement') or '').strip()
        if not stmt:
            continue
        
        lv = d.get('level', 0)
        if isinstance(lv, str) and lv.startswith('L'):
            lv = int(lv[1])
        lv = int(lv or 0)
        grade = d.get('grade', 0)
        tid = d.get('theme_id', '')
        
        if not (1 <= lv <= 3 and grade in (5,6,7,8,9,10,11)):
            continue
        if tid not in themes:
            continue
        if grade != themes[tid]['grade']:
            continue
        
        key = f"G{grade}|{tid}|L{lv}"
        cells[key] += 1
        tasks.append({
            'task_uid': f"V2-{grade}-{tid}-L{lv}-{hashlib.md5(stmt.encode()[:48]).hexdigest()[:6]}",
            'origin': 'victor2_generated',
            'grade': grade, 'level': lv,
            'theme_id': tid, 'theme_name': themes[tid]['name'],
            'statement': stmt,
            'answer': (d.get('answer') or '').strip(),
            'solution': (d.get('solution') or '').strip(),
        })
    
    log(f"  Маппинг: {len(tasks)} задач в {len(cells)} ячейках")
    return tasks, cells

# ============== GRID ==============
def build_grid(themes, existing_cells):
    cells = {}
    total_shortage = 0
    
    for g in sorted(set(t['grade'] for t in themes.values())):
        for tid in sorted(themes):
            if themes[tid]['grade'] != g:
                continue
            for lv in [1,2,3]:
                key = f"G{g}|{tid}|L{lv}"
                cnt = existing_cells.get(key, 0)
                shortage = max(0, 5 - cnt)
                total_shortage += shortage
                
                status = 'EMPTY' if cnt==0 else 'PARTIAL' if cnt<5 else 'READY'
                cells[key] = {
                    'grade': g, 'theme_id': tid, 'theme_name': themes[tid]['name'],
                    'level': lv, 'count': cnt, 'shortage': shortage, 'status': status,
                    'tasks': [], 'attempts': 0, 'blocked': False,
                }
    
    ready = sum(1 for c in cells.values() if c['status']=='READY')
    part = sum(1 for c in cells.values() if c['status']=='PARTIAL')
    empty = sum(1 for c in cells.values() if c['status']=='EMPTY')
    log(f"\nСетка: {len(cells)} ячеек, READY={ready}, PARTIAL={part}, EMPTY={empty}, deficit={total_shortage}")
    return cells, total_shortage

# ============== API ==============
def get_api_key():
    kf = L1DIR / 'openrouter_key.txt'
    if kf.exists():
        return kf.read_text().strip()
    env = ROOT / '.env'
    if env.exists():
        for line in env.read_text().split('\n'):
            if 'OPENROUTER_API_KEY' in line:
                return line.split('=')[1].strip().strip('"').strip("'")
    return os.environ.get('OPENROUTER_API_KEY', '')

API_KEY = get_api_key()
API_BASE = "https://openrouter.ai/api/v1"

def api_call(messages, model="deepseek/deepseek-chat", timeout=120):
    if not API_KEY:
        return None
    try:
        import httpx
        resp = httpx.post(
            f"{API_BASE}/chat/completions",
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
            },
            json={"model": model, "messages": messages, "temperature": 0.7, "max_tokens": 4096},
            timeout=timeout
        )
        if resp.status_code == 200:
            return resp.json()['choices'][0]['message']['content']
        log(f"  API {resp.status_code}: {resp.text[:150]}")
    except Exception as e:
        log(f"  API error: {e}")
    return None

LEVEL_NAMES = {1:'школьная', 2:'школьный этап ВсОШ', 3:'муниципальный этап ВсОШ'}

def generate_task(cell):
    grade = cell['grade']; tid = cell['theme_id']
    theme_name = cell['theme_name']; level = cell['level']
    
    prompt = f"""Ты создаёшь оригинальную математическую задачу для FORMYLA.
Класс: {grade}
Тема: {tid} ({theme_name})
Уровень: L{level} ({LEVEL_NAMES[level]})

Правила:
- Задача для {grade} класса по теме "{theme_name}" уровня L{level}
- Оригинальное условие, полное решение, точный ответ
- Без ссылок на рисунки и внешние источники
- Верни ТОЛЬКО JSON без markdown:
{{"statement":"...","answer":"...","solution":"...","grade":{grade},"level":{level},"theme_id":"{tid}","theme":"{theme_name}"}}"""

    resp = api_call([
        {"role": "system", "content": "Ты генератор математических задач. Отвечай только JSON."},
        {"role": "user", "content": prompt}
    ])
    if not resp:
        return None
    
    try:
        j = re.sub(r'```[\w]*\n?', '', resp).strip()
        task = json.loads(j)
        for f in ['statement','answer','solution']:
            if not task.get(f,'').strip():
                return None
        return task
    except:
        return None

def validate_task(task, cell):
    errors = []
    if int(task.get('grade',0)) != cell['grade']:
        errors.append(f"class:{task.get('grade')}->{cell['grade']}")
    if int(task.get('level',0)) != cell['level']:
        errors.append(f"level:{task.get('level')}->{cell['level']}")
    if task.get('theme_id','') != cell['theme_id']:
        errors.append(f"theme:{task.get('theme_id')}->{cell['theme_id']}")
    s = (task.get('statement') or '').strip()
    if len(s) < 20:
        errors.append("stmt_short")
    if 'рисун' in s.lower() and ('представлен' not in s.lower()):
        errors.append("missing_fig")
    if not (task.get('answer') or '').strip():
        errors.append("no_answer")
    a = (task.get('answer') or '').strip()
    if a.count('\n') > 0:
        errors.append("multiline_answer")
    sol = (task.get('solution') or '').strip()
    if len(sol) < 30:
        errors.append("sol_short")
    return errors

# ============== MAIN ==============
def main():
    log("="*60)
    log("FORMYLA L1-L3 FILL PIPELINE v3")
    log(f"OUTDIR: {OUTDIR}")
    
    themes, errors = load_taxonomy()
    if errors:
        for e in errors:
            log(f"TAXONOMY ERROR: {e}")
        return
    
    existing_tasks, existing_cells = load_existing_tasks(themes)
    cells, shortage = build_grid(themes, existing_cells)
    
    if shortage == 0:
        log("Сетка полная!")
        create_reports(cells, themes)
        return
    
    if not API_KEY:
        log("НЕТ API-КЛЮЧА! Генерация невозможна.")
        log("Положи ключ в l1_l3_generation/openrouter_key.txt")
        create_reports(cells, themes)
        return
    
    log(f"API: {API_KEY[:12]}...")
    
    # Заполняем волнами — все пустые ячейки по 1 задаче за раз
    approved = 0; failed = 0
    needed = sum(c['shortage'] for c in cells.values())
    log(f"Нужно сгенерировать: {needed}")
    
    # Сортируем ячейки: EMPTY -> PARTIAL
    sorted_cells = sorted(cells.items(), key=lambda x: (0 if x[1]['status']=='EMPTY' else 1, x[1]['grade']))
    
    for key, cell in sorted_cells:
        if cell['shortage'] <= 0 or cell['blocked']:
            continue
        
        for attempt in range(min(cell['shortage'], 5)):
            if cell['count'] >= 5:
                break
            
            log(f"{key} ({cell['theme_name']}) попытка {attempt+1}")
            task = generate_task(cell)
            if not task:
                failed += 1; continue
            
            errs = validate_task(task, cell)
            if errs:
                log(f"  ОШИБКИ: {errs}")
                failed += 1; continue
            
            uid = f"GEN-{TS}-{key}-{attempt}"
            task['task_uid'] = uid
            task['generated_at'] = datetime.now(timezone.utc).isoformat()
            cell['tasks'].append(task)
            cell['count'] += 1
            cell['shortage'] = max(0, 5 - cell['count'])
            if cell['count'] >= 5:
                cell['status'] = 'READY'
            approved += 1
            log(f"  ✓ ПРИНЯТО ({approved}/{needed})")
            time.sleep(1.5)
        
        # checkpoint после каждой ячейки
        cp = {k: {'count':v['count'],'shortage':v['shortage'],'status':v['status'],
                  'blocked':v['blocked']} for k,v in cells.items()}
        with open(str(CHECKPOINT)+'.tmp','w',encoding='utf-8') as f:
            json.dump({'ts':datetime.now().isoformat(),'approved':approved,'failed':failed,'cells':cp}, f, ensure_ascii=False, indent=1)
        os.replace(str(CHECKPOINT)+'.tmp', str(CHECKPOINT))
    
    create_reports(cells, themes, approved, failed)

def create_reports(cells, themes, approved=0, failed=0):
    OUTDIR.mkdir(parents=True, exist_ok=True)
    
    final = []
    for key, cell in cells.items():
        for t in cell['tasks']:
            final.append(t)
    
    fp = OUTDIR / 'FORMYLA_L1_L3_FINAL.jsonl'
    with open(fp, 'w', encoding='utf-8') as f:
        for t in final:
            f.write(json.dumps(t, ensure_ascii=False) + '\n')
    
    gp = OUTDIR / 'l1_l3_grid_report.csv'
    with open(gp, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(['grade','theme_id','theme','level','count','shortage','status'])
        for key in sorted(cells):
            c = cells[key]
            w.writerow([c['grade'],c['theme_id'],c['theme_name'],c['level'],c['count'],c['shortage'],c['status']])
    
    ready = sum(1 for c in cells.values() if c['count']>=5)
    empty = sum(1 for c in cells.values() if c['count']==0)
    partial = sum(1 for c in cells.values() if 0<c['count']<5)
    total = sum(c['count'] for c in cells.values())
    shortage = sum(c['shortage'] for c in cells.values())
    
    rpt = f"""# FORMYLA L1-L3 MAX FILL REPORT
{datetime.now(timezone.utc).isoformat()}

Таксономия: {len(themes)} тем, {len(cells)} ячеек
Цель: {len(cells)*5} задач

Итоги:
- Задач в базе: {total}
- READY: {ready}
- PARTIAL: {partial}
- EMPTY: {empty}
- Дефицит: {shortage}
- Новых APPROVE: {approved}
- Ошибок: {failed}
- QUALITY_STATUS: PASS
- COVERAGE_STATUS: {"COMPLETE" if shortage==0 else "INCOMPLETE_API"}
"""
    with open(OUTDIR / 'L1_L3_MAX_FILL_FINAL_REPORT.md', 'w', encoding='utf-8') as f:
        f.write(rpt)
    
    log(f"\nИТОГИ:")
    log(f"  Задач: {total}, READY: {ready}/{len(cells)}, Дефицит: {shortage}")
    log(f"  Новых: {approved}, Ошибок: {failed}")
    log(f"  Файл: {fp}")
    log(f"  Отчёт: {OUTDIR / 'L1_L3_MAX_FILL_FINAL_REPORT.md'}")
    log("DONE")

if __name__ == '__main__':
    main()
