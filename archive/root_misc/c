#!/usr/bin/env python3
"""
Полный тест пайплайна: G5 L1, G6 L2
Генерация -> детерминированная проверка -> независимый решатель -> критик
Модели: qwen/qwen-plus, потом qwen/qwen-plus-2025-07-28
"""
import json, os, sys, hashlib, re, requests, time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
L1DIR = ROOT / 'l1_l3_generation'
API_KEY_PATH = L1DIR / 'openrouter_key.txt'
API_BASE = 'https://openrouter.ai/api/v1/chat/completions'

GRADES = {}
tax = json.load(open(L1DIR / 'taxonomy_by_grade.json', 'r', encoding='utf-8'))
for gk, items in tax.get('grades', {}).items():
    GRADES[int(gk)] = [{'theme_id': i['theme_id'], 'theme': i['theme'], 'section': i.get('section','')} for i in items]

LEVEL_DESC = {1:'L1 - школьная математика',2:'L2 - школьный этап',3:'L3 - муниципальный этап'}
AGE = {5:'Без алгебры',6:'Без алгебры 7-8',7:'Базовые уравнения',8:'Алгебра/геометрия 8',9:'Не 10-11',10:'Не универ',11:'Школьный аппарат'}

def call_api(model, messages, temperature=0.3, max_tokens=1024):
    key = open(API_KEY_PATH).read().strip()
    headers = {'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'}
    payload = {'model': model, 'messages': messages, 'temperature': temperature, 'max_tokens': max_tokens}
    for attempt in range(3):
        try:
            r = requests.post(API_BASE, headers=headers, json=payload, timeout=90)
            if r.status_code == 200:
                result = r.json()
                cost = result.get('usage',{}).get('total_cost',0)
                print(f'  [COST: ${cost:.8f}]')
                return result
            elif r.status_code == 402: return 'INSUFFICIENT_FUNDS'
            elif r.status_code == 429: time.sleep(5)
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

def run_test(model, g, lv):
    print(f'\n--- TEST {model} G{g} L{lv} ---')
    tid = GRADES[g][0]['theme_id']
    ti = GRADES[g][0]
    
    # GENERATE
    print(f'[1] GEN')
    prompt = f'''Создай задачу. Класс {g}, тема "{ti['theme']}", раздел "{ti['section']}", уровень L{lv}.
Только JSON: {{"statement":"...","answer":"...","solution":"...","grade":{g},"level":{lv},"section":"{ti['section']}","theme_id":"{tid}","theme":"{ti['theme']}"}}'''
    result = call_api(model, [{'role':'system','content':prompt},{'role':'user','content':f'Создай задачу L{lv} для {g} класса по "{ti["theme"]}". Только JSON.'}], temperature=0.7)
    if result == 'INSUFFICIENT_FUNDS': print('  BLOCKED'); return 'INSUFFICIENT_FUNDS'
    if not result: print('  FAIL'); return 'FAIL'
    data = extract_json(result['choices'][0]['message']['content'])
    if not data: print('  NO JSON'); return 'FAIL'
    for r in ['statement','answer','solution','grade','level','theme_id']:
        if r not in data: print(f'  Missing {r}'); return 'FAIL'
    print(f'  Task: {data["statement"][:60]}...')
    
    # VERIFY
    print('[2] DET CHECK')
    checks = {'grade': data['grade']==g, 'level_ok': 1<=data['level']<=3, 'theme_in_grade': data['theme_id'] in {i['theme_id'] for i in GRADES[g]}, 'statement_ok': len(data['statement'])>10}
    if not all(checks.values()): print(f'  DET FAIL: {[k for k,v in checks.items() if not v]}'); return 'DET_FAIL'
    print('  PASS')
    
    print('[3] SOLVER')
    sol = call_api(model, [
        {'role':'system','content':'Ты независимый решатель. JSON: {"solvable":true,"independent_answer":"...","independent_solution":"...","unambiguous":true,"data_sufficient":true,"issues":[]}'},
        {'role':'user','content':f'Реши для {g} класса:\n{data["statement"]}\nJSON.'}
    ], temperature=0.2, max_tokens=768)
    if sol == 'INSUFFICIENT_FUNDS': return 'INSUFFICIENT_FUNDS'
    if not sol: print('  SOLVER FAIL'); return 'FAIL'
    sv = extract_json(sol['choices'][0]['message']['content'])
    if not sv: print('  NO JSON'); return 'FAIL'
    if not sv.get('solvable'): print('  UNSOLVABLE'); return 'UNSOLVABLE'
    print(f'  Solver: {sv.get("independent_answer","")[:50]}')
    
    print('[4] CRITIC')
    cr = call_api(model, [
        {'role':'system','content':'Ты критик. JSON: {"verdict":"APPROVE","answer_match":true,"solution_correct":true,"grade_match":true,"theme_match":true,"level_match":true,"age_appropriate":true,"confidence":0.95}'},
        {'role':'user','content':f'Класс:{g}, Уровень:{lv}\nУсловие:{data["statement"]}\nАвтор:{data["answer"]}\nРешение:{data["solution"]}\nНезависимо:{sv.get("independent_answer","")}\nJSON.'}
    ], temperature=0.2, max_tokens=512)
    if cr == 'INSUFFICIENT_FUNDS': return 'INSUFFICIENT_FUNDS'
    if not cr: print('  CRITIC FAIL'); return 'FAIL'
    cv = extract_json(cr['choices'][0]['message']['content'])
    if not cv: print('  NO JSON'); return 'FAIL'
    verdict = cv.get('verdict','REJECT')
    conf = cv.get('confidence',0)
    print(f'  Verdict: {verdict}, conf={conf}')
    return verdict if verdict=='APPROVE' and conf>=0.7 else verdict

def main():
    print('='*60)
    print('FORMYLA FULL PIPELINE SMOKE TEST')
    print('='*60)
    
    r1 = run_test('qwen/qwen-plus', 5, 1)
    if r1 == 'INSUFFICIENT_FUNDS':
        print('\n*** INSUFFICIENT FUNDS: нужно пополнить OpenRouter ***')
        return
    print(f'\nRESULT 1 (G5 L1): {r1}')
    
    r2 = run_test('qwen/qwen-plus-2025-07-28', 6, 2)
    if r2 == 'INSUFFICIENT_FUNDS':
        print('\n*** INSUFFICIENT FUNDS ***')
        return
    print(f'RESULT 2 (G6 L2): {r2}')
    
    print(f'\n=== ALL TESTS {"PASSED" if r1=="APPROVE" and r2=="APPROVE" else "PARTIAL"} ===')

if __name__ == '__main__':
    main()
