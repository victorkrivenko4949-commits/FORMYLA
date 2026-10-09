#!/usr/bin/env python
# -*- coding: utf-8 -*-
import json, sys

bank = json.load(open('curated_bank_L1_L5_fixed.json', 'r', encoding='utf-8'))

# Find the single G2|L1 task
g2l1 = [t for t in bank if t.get('level')==1 and str(t.get('grade',''))=='2']
print('G2|L1 count: %d' % len(g2l1))
for t in g2l1:
    print('  Keys: %s' % list(t.keys()))
    print('  original_id: %s' % t.get('original_id'))
    print('  source_index: %s' % t.get('source_index'))
    print('  target_level: %s' % t.get('target_level'))
    print('  level: %s' % t.get('level'))
    print('  grade: %s (type: %s)' % (t.get('grade'), type(t.get('grade')).__name__))
    print('  topic: %s' % t.get('topic'))
    task_text = str(t.get('task_text',''))
    print('  task_text: %s' % task_text[:300])
    statement = str(t.get('statement',''))
    print('  statement: %s' % statement[:300])
    answer = str(t.get('answer',''))
    print('  answer: %s' % answer[:300])
    solution = str(t.get('solution',''))
    print('  solution: %s' % solution[:300])
    print('  quality_score: %s' % t.get('quality_score'))
    print('  rank_in_cell: %s' % t.get('rank_in_cell'))
    print('  total_in_cell_pool: %s' % t.get('total_in_cell_pool'))
    print('  fixed_by_ai: %s' % t.get('fixed_by_ai'))
    print('  pending_live_audit: %s' % t.get('pending_live_audit'))
    print('  changes_made: %s' % t.get('changes_made'))
    print('  source: %s' % t.get('source'))
    print('  audit_mode: %s' % t.get('audit_mode'))
    print('  evidence_source: %s' % t.get('evidence_source'))
