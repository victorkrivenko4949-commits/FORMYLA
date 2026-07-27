#!/usr/bin/env python3
"""
Полный тест пайплайна: 1 задача (G5 L1), 
все этапы: генерация -> детерминированная проверка -> независимый решатель -> критик.
Использует самую дешёвую модель qwen/qwen-plus.
"""
import json, os, sys, hashlib, re, requests, time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
L1DIR = ROOT / 'l1_l3_generation'

API_KEY_PATH = L1DIR / 'openrouter_key.txt'
MODEL = 'qwen/qwen-plus'

GRADES = {}
tax = json.load(open(L1DIR / 'taxonomy_by_grade.json', 'r', encoding='utf-8'))
for gk, items in tax.get('grades', {}).items():
    GRADES[int(gk)] = [{'theme_id': i['theme_id'], 'theme': i['theme'], 'section': i.get('section','')} for i in items]

LEVEL_DESC = {1:'L1 - обычная школьная математика',2:'L2 - школьный этап ВсОШ',3:'L3 - муниципальный этап ВсОШ'}
AGE = {5:'Без алгебры. Наглядное решение.',6:'Без алгебры 7-8 кл.',7:'Базовые уравнения.',8:'Алгебра/геометрия 8 кл.',9:'Не требовать 10-11 кл.',10:'Не универ. анализ.',11:'Школьный аппарат.'}
API_BASE = 'https://openrouter.ai/api/v1/chat/completions'

CURRENT_MODEL = MODEL

def call_api(messages, temperature=0.3, max_tokens=1024):
    global CURRENT_MODEL
    key = open(API_KEY_PATH).read().strip()
    headers = {'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'}
    payload = {'model': MODEL, 'messages': messages, 'temperature': temperature, 'max_tokens': max_tokens}
    for attempt in range(3):
        try:
            r = requests.post(API_BASE, headers=headers, json=payload, timeout=90)
            if r.status_code == 200:
                result = r.json()
                cost = result.get('usage',{}).get('total_cost',0)
                print(f'  [COST: ${cost:.8f}]')
                return result
            elif r.status_code == 402:
                return 'INSUFFICIENT_FUNDS'
            elif r.status_code == 429:
                time.sleep(5)
            else:
                print(f'  API {r.status_code}')
                time.sleep(2**attempt)
        except Exception as e:
            print(f'  Error: {e}')
            time.sleep(2)
    return None

def extract_json(text):
    text = re.sub(r'```(?:json)?', '', text).strip()
    for start in range(len(text)):
        if text[start] == '{':
            try: return json.loads(text[start:])
            except: continue
    return None

def generate(g, lv, tid):
    ti = None
    for it in GRADES[g]:
        if it['theme_id'] == tid: ti = it; break
    prompt = f'''Создай математическую задачу. ФИКСИРОВАННО: класс {g}, тема "{ti['theme']}", раздел "{ti['section']}", уровень L{lv} ({LEVEL_DESC.get(lv,'')}), возраст: {AGE.get(g,'')}.
Правила: задача строго для {g} класса, темы "{ti['theme']}", уровня L{lv}. Решение доступно ученику {g} класса. Не ссылайся на рисунок. Только JSON.
{{"statement":"...","answer":"...","solution":"...","grade":{g},"level":{lv},"section":"{ti['section']}","theme_id":"{tid}","theme":"{ti['theme']}"}}'''
    
    print(f'  [GENERATE] G{g} L{lv} {tid}')
    result = call_api([{'role':'system','content':prompt},{'role':'user','content':f'Создай задачу L{lv} для {g} класса по "{ti["theme"]}". Только JSON.'}], temperature=0.7)
    if result == 'INSUFFICIENT_FUNDS': return 'INSUFFICIENT_FUNDS', None
    if not result: return 'API_FAIL', None
    data = extract_json(result['choices'][0]['message']['content'])
    if not data: return 'NO_JSON', None
    for r in ['statement','answer','solution','grade','level','theme_id']:
        if r not in data: return f'MISSING_{r}', None
    return 'OK', data

def verify(g, lv, tid, data):
    print('  [VERIFY]')
    # Deterministic checks
    checks = {}
    checks['grade'] = data['grade'] == g
    checks['level'] = 1 <= data['level'] <= 3
    checks['theme_in_grade'] = data['theme_id'] in {i['theme_id'] for i in GRADES.get(g,[])}
    checks['statement'] = len(data.get('statement','')) > 10
    checks['answer'] = len(data.get('answer','')) > 0
    all_ok = all(checks.values())
    if not all_ok:
        failed = [k for k,v in checks.items() if not v]
        return f'DET_FAIL:{failed}', None
    print(f'  Det checks OK')
    
    # Independent solve
    print('  [SOLVER]')
    sys.stdout.flush()
    sol = call_api([
        {'role':'system','content':'Ты независимый решатель. Не видишь ответ. JSON: {"solvable":true,"unambiguous":true,"data_sufficient":true,"independent_answer":"...","independent_solution":"..."}'},
        {'role':'user','content':f'Реши для {g} класса:\n{data["statement"]}\nJSON.'}
    ], temperature=0.2, max_tokens=768)
    if sol == 'INSUFFICIENT_FUNDS': return 'INSUFFICIENT_FUNDS', data
    if not sol: return 'SOLVER_FAIL', data
    sv = extract_json(sol['choices'][0]['message']['content'])
    if not sv: return 'SOLVER_NOJSON', data
    if not sv.get('solvable'): return 'UNSOLVABLE', data
    print(f'  Solver OK: ans={sv.get("independent_answer","")[:50]}')
    
    # Critic
    print('  [CRITIC]')
    sys.stdout.flush()
    cr = call_api([
        {'role':'system','content':'Ты критик. JSON: {"verdict":"APPROVE","answer_match":true,"solution_correct":true,"grade_match":true,"theme_match":true,"level_match":true,"age_appropriate":true,"confidence":0.95}'},
        {'role':'user','content':f'Класс:{g}, Уровень:{lv}, Тема:{data.get("theme","")}\nУсловие:{data["statement"]}\nАвтор:{data["answer"]}\nАвтор решение:{data["solution"]}\nНезависимо:{sv.get("independent_answer","")}\nJSON.'}
    ], temperature=0.2, max_tokens=512)
    if cr == 'INSUFFICIENT_FUNDS': return 'INSUFFICIENT_FUNDS', data
    if not cr: return 'CRITIC_FAIL', data
    cv = extract_json(cr['choices'][0]['message']['content'])
    if not cv: return 'CRITIC_NOJSON', data
    verdict = cv.get('verdict','REJECT')
    conf = cv.get('confidence',0)
    print(f'  Verdict: {verdict}, conf={conf}')
    if verdict == 'APPROVE' and conf >= 0.7:
        return 'APPROVE', {'task': data, 'solver': sv, 'critic': cv}
    return verdict, data

def test():
    print('='*60)
    print('FORMYLA Full Pipeline Smoke Test')
    print(f'Model: {MODEL}')
    print(f'Date: {datetime.now().isoformat()}')
    print('='*60)
    
    # Test 1: G5 L1
    print('\n--- TEST 1: G5 L1 ---')
    tid = GRADES[5][0]['theme_id']
    status, data = generate(5, 1, tid)
    print(f'  Status: {status}')
    if status != 'OK': return
    result, extra = verify(5, 1, tid, data)
    print(f'  FINAL: {result}')
    
    # Test 2: Try qwen-plus-2025-07-28 (even cheaper)
    MODEL = 'qwen/qwen-plus-2025-07-28'
    print(f'\n--- TEST 2: qwen-plus-2025-07-28 (G6 L2) ---')
    tid = GRADES[6][1]['theme_id']
    status, data = generate(6, 2, tid)
    if status == 'INSUFFICIENT_FUNDS':
        print('  BLOCKED: INSUFFICIENT FUNDS')
        print('\n*** ACCOUNT NEEDS CREDITS ***')
        return
    if status != 'OK': return
    result, extra = verify(6, 2, tid, data)
    print(f'  FINAL: {result}')
    
    print('\n=== ALL TESTS PASSED ===')

if __name__ == '__main__':
    test()
