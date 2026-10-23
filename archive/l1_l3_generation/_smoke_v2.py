#!/usr/bin/env python3
"""FORMYLA Full Pipeline Smoke Test v2 - qwen-plus, 2 задачи, все этапы"""
import json, re, requests, time, sys
from pathlib import Path

API_KEY_PATH = Path('l1_l3_generation/openrouter_key.txt')
API_BASE = 'https://openrouter.ai/api/v1/chat/completions'

TAX = json.load(open(Path('l1_l3_generation/taxonomy_by_grade.json'), 'r', encoding='utf-8'))
GRADES = {}
for gk, items in TAX.get('grades', {}).items():
    GRADES[int(gk)] = [{'theme_id': i['theme_id'], 'theme': i['theme'], 'section': i.get('section','')} for i in items]

def call_api(model, msgs, temperature=0.3, max_tokens=1024):
    key = open(API_KEY_PATH).read().strip()
    r = requests.post(API_BASE, headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
                      json={'model': model, 'messages': msgs, 'temperature': temperature, 'max_tokens': max_tokens}, timeout=90)
    if r.status_code == 200:
        j = r.json()
        cost = j.get('usage', {}).get('total_cost', 0)
        print(f'  cost=${cost:.8f}')
        return j
    if r.status_code == 402: return 'INSUFFICIENT_FUNDS'
    print(f'  API {r.status_code}: {r.text[:100]}')
    return None

def extract_json(text):
    text = re.sub(r'```(?:json)?', '', text).strip()
    for start in range(len(text)):
        if text[start] == '{':
            try: return json.loads(text[start:])
            except: continue
    return None

def run(model, g, lv):
    print(f'\n=== Model={model} G{g} L{lv} ===')
    ti = GRADES[g][0]
    print(f'[1] GENERATE {ti["theme_id"]} {ti["theme"]}')
    sys.stdout.flush()
    
    result = call_api(model, [
        {'role': 'system', 'content': f'Ты генератор. Класс {g}, тема "{ti["theme"]}", уровень L{lv}. Только JSON: {{"statement":"...","answer":"...","solution":"...","grade":{g},"level":{lv},"theme_id":"{ti["theme_id"]}"}}'},
        {'role': 'user', 'content': f'Задача L{lv} для {g} класса по "{ti["theme"]}". Только JSON.'}
    ], temperature=0.7)
    if result == 'INSUFFICIENT_FUNDS': return 'NO_FUNDS'
    if not result: return 'FAIL'
    data = extract_json(result['choices'][0]['message']['content'])
    if not data: return 'NO_JSON'
    for r in ['statement','answer','solution','grade','level','theme_id']:
        if r not in data: return f'MISS_{r}'
    print(f'  Statement: {data["statement"][:70]}...')
    
    print('[2] DET CHECK')
    if data['grade'] != g or not (1 <= data['level'] <= 3) or data['theme_id'] not in {i['theme_id'] for i in GRADES[g]} or len(data['statement']) < 10:
        return 'DET_FAIL'
    print('  OK')
    
    print('[3] SOLVER')
    sys.stdout.flush()
    sol = call_api(model, [
        {'role': 'system', 'content': 'Ты независимый решатель. JSON: {"solvable":true,"independent_answer":"...","independent_solution":"...","unambiguous":true,"data_sufficient":true}'},
        {'role': 'user', 'content': f'Реши:\n{data["statement"]}\nJSON'}
    ], temperature=0.2, max_tokens=768)
    if sol == 'INSUFFICIENT_FUNDS': return 'NO_FUNDS'
    if not sol: return 'SOLVER_FAIL'
    sv = extract_json(sol['choices'][0]['message']['content'])
    if not sv: return 'SV_NOJSON'
    if not sv.get('solvable'): return 'UNSOLVABLE'
    print(f'  Solver: {sv.get("independent_answer","")[:50]}')
    
    print('[4] CRITIC')
    sys.stdout.flush()
    cr = call_api(model, [
        {'role': 'system', 'content': 'Ты критик. JSON: {"verdict":"APPROVE","answer_match":true,"solution_correct":true,"grade_match":true,"theme_match":true,"level_match":true,"age_appropriate":true,"confidence":0.95}'},
        {'role': 'user', 'content': f'Класс:{g}, Уровень:{lv}\nУсловие:{data["statement"]}\nАвтор:{data["answer"]}\nРешение:{data["solution"]}\nНезависимо:{sv.get("independent_answer","")}\nJSON'}
    ], temperature=0.2, max_tokens=512)
    if cr == 'INSUFFICIENT_FUNDS': return 'NO_FUNDS'
    if not cr: return 'CR_FAIL'
    cv = extract_json(cr['choices'][0]['message']['content'])
    if not cv: return 'CR_NOJSON'
    verdict = cv.get('verdict', 'REJECT')
    conf = cv.get('confidence', 0)
    print(f'  Verdict: {verdict}, conf={conf}')
    return verdict if verdict == 'APPROVE' and conf >= 0.7 else verdict

if __name__ == '__main__':
    print('='*60)
    print('FORMYLA FULL PIPELINE SMOKE TEST v2')
    print('='*60)
    
    r1 = run('qwen/qwen-plus', 5, 1)
    print(f'\nRESULT 1 (G5 L1): {r1}')
    
    if r1 == 'APPROVE':
        r2 = run('qwen/qwen-plus-2025-07-28', 6, 2)
        print(f'RESULT 2 (G6 L2): {r2}')
    elif r1 == 'NO_FUNDS':
        print('\n*** BLOCKED: INSUFFICIENT FUNDS ***\nПополните OpenRouter.')
    else:
        r2 = 'SKIPPED'
    
    ok = r1 == 'APPROVE' and (r2 == 'APPROVE' if 'r2' in dir() else False)
    print(f'\n=== {"ALL PASSED" if ok else "PARTIAL"} ===')
    print(f'G5 L1: {r1}, G6 L2: {r2 if "r2" in dir() else "N/A"}')
