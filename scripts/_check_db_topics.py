#!/usr/bin/env python3
import sys, json
sys.stdout.reconfigure(encoding='utf-8')

data = json.load(open('data/adaptive_full_db.json', 'r', encoding='utf-8'))

for grade in range(5, 12):
    g_tasks = [t for t in data if int(t.get('grade', 0)) == grade]
    topics = {}
    for t in g_tasks:
        tp = t.get('topic', '?')
        topics[tp] = topics.get(tp, 0) + 1
    
    # Check movement keywords
    mvt_kw = ['движен', 'скорост']
    
    print(f"\nGrade {grade}: {len(g_tasks)} tasks")
    for tp, c in sorted(topics.items(), key=lambda x: -x[1]):
        mvt = any(kw in tp.lower() for kw in mvt_kw)
        flag = ' ← MOVEMENT' if mvt else ''
        print(f"  {tp}: {c}{flag}")
