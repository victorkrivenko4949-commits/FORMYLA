#!/usr/bin/env python
# -*- coding: utf-8 -*-
import json, sys, os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

# --- Search 1: curated_bank_L1_L5_taxonomy_v2.json ---
print("="*70)
print("SEARCH 1: curated_bank_L1_L5_taxonomy_v2.json")
print("="*70)
try:
    with open('curated_bank_L1_L5_taxonomy_v2.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    physics_kw = ['физик','physics','механи','электр','оптик','кинематик','динамик',
                  'термодинам','энерг','импульс','ньютон','физ','физическ']
    found = []
    for i,item in enumerate(data):
        s = json.dumps(item,ensure_ascii=False).lower()
        for kw in physics_kw:
            if kw.lower() in s:
                found.append((i,str(item.get('id',item.get('task_id','?'))),kw))
                break
    print(f'Total items: {len(data)}')
    print(f'Physics matches: {len(found)}')
    for idx,tid,kw in found[:30]:
        print(f'  [{kw}] idx={idx} id={tid}')
    if len(found)>30: print(f'  ... +{len(found)-30} more')
except Exception as e:
    print(f'Error: {e}')

# --- Search 2: VICTOR2.0 directory ---
print()
print("="*70)
print("SEARCH 2: VICTOR2.0 directory")
print("="*70)
victor_dir = 'VICTOR2.0'
if os.path.isdir(victor_dir):
    files = os.listdir(victor_dir)
    print(f'Files: {files}')
    for fname in files:
        fpath = os.path.join(victor_dir, fname)
        size = os.path.getsize(fpath)
        print(f'  {fname}: {size} bytes')
        if fname.endswith('.json'):
            try:
                with open(fpath, 'r', encoding='utf-8') as jf:
                    jdata = json.load(jf)
                if isinstance(jdata, list):
                    print(f'    -> JSON array, {len(jdata)} items')
                    # search for physics
                    found2 = []
                    for i,item in enumerate(jdata):
                        s = json.dumps(item,ensure_ascii=False).lower()
                        for kw in physics_kw:
                            if kw.lower() in s:
                                found2.append((i,str(item.get('id',item.get('task_id','?'))),kw))
                                break
                    print(f'    Physics matches: {len(found2)}')
                    for idx,tid,kw in found2[:20]:
                        print(f'      [{kw}] idx={idx} id={tid}')
                elif isinstance(jdata, dict):
                    print(f'    -> JSON object, keys: {list(jdata.keys())[:15]}')
            except Exception as e:
                print(f'    -> Error reading JSON: {e}')
else:
    print(f'Directory {victor_dir} not found')

# --- Search 3: _grade_map_result.json ---
print()
print("="*70)
print("SEARCH 3: _grade_map_result.json")
print("="*70)
try:
    with open('_grade_map_result.json', 'r', encoding='utf-8') as f:
        gdata = json.load(f)
    
    def search_deep(obj, path='', depth=0):
        results = []
        if depth > 5: return results
        if isinstance(obj, dict):
            for k,v in obj.items():
                results.extend(search_deep(v, f'{path}.{k}', depth+1))
        elif isinstance(obj, list):
            for i,v in enumerate(obj):
                results.extend(search_deep(v, f'{path}[{i}]', depth+1))
        elif isinstance(obj, str):
            ol = obj.lower()
            for kw in physics_kw:
                if kw.lower() in ol:
                    results.append((path, kw, obj[:150]))
                    break
        return results
    
    results = search_deep(gdata)
    print(f'Physics matches: {len(results)}')
    for path,kw,ctx in results[:20]:
        print(f'  [{kw}] {path}')
        print(f'    -> {ctx}')
        print()
except Exception as e:
    print(f'Error: {e}')

print()
print("DONE")
