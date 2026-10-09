#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json, sys

with open('olympiads.py', 'r', encoding='utf-8') as f:
    src = f.read()

# Find the first few records to understand structure
# Just manually parse the JSON part
start = src.index('[')
json_str = src[start:]
db = json.loads(json_str)

rec = db[0]
print('Top keys:', list(rec.keys()))
probs = rec.get('problems', [])
if probs:
    p = probs[0]
    print('Problem keys:', list(p.keys()))
    print('solution_status:', p.get('solution_status'))
    print('solution type:', type(p.get('solution', '')).__name__)
    # find a problem with solution_status=generated
    for p2 in probs:
        if p2.get('solution_status') == 'generated':
            print()
            print('Found generated:')
            print('  keys:', list(p2.keys()))
            sol = str(p2.get('solution', ''))
            print('  solution[:150]:', sol[:150])
            break
    else:
        print('No generated solutions found')
        statuses = set(p.get('solution_status', 'MISSING') for p in probs)
        print('All solution_status values:', statuses)
