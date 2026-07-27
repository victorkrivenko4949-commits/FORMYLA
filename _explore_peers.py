#!/usr/bin/env python
"""Explore peer tasks for each mismatch — same (topic, grade, level)."""
import sys, json
sys.stdout.reconfigure(encoding='utf-8')

with open('curated_bank_L1_L5_fixed.json', 'r', encoding='utf-8') as f:
    bank = json.load(f)

mismatch_info = [
    ('SEL1080-0293', 'Системы', 8, 2),
    ('SEL1080-0304', 'Системы и текстовые задачи', 8, 3),
    ('SEL1080-0573', 'Алгебра. Неравенства и оценки', 11, 1),
    ('SEL1080-0068', 'Раскраска', 8, 3),
    ('SEL1080-0075', 'Раскраска', 5, 5),
    ('SEL1080-0073', 'Принцип Дирихле', 5, 1),
    ('SEL1080-0377', 'Логика. Логика, инварианты, стратегии', 9, 1),
    ('SEL1080-0127', 'Уравнения и текстовые задачи', 6, 4),
    ('SEL1080-0672', 'Раскраски', 11, 2),
]

for oid, topic, grade, level in mismatch_info:
    peers = [
        t for t in bank 
        if t.get('topic') == topic 
        and t.get('grade') == grade 
        and t.get('level') == level
        and t.get('original_id') != oid
    ]
    print(f"\n{'='*60}")
    print(f"MATCH: {oid} | topic='{topic}' | grade={grade} | level={level}")
    print(f"Total peers in same cell: {len(peers)}")
    print(f"{'='*60}")
    
    if len(peers) == 0:
        print("  ⚠️  No peer tasks in this cell! Need to generate replacement from scratch.")
        continue
    
    for i, p in enumerate(peers[:6], 1):
        fixed = p.get('fixed_by_ai', False)
        stmt = p.get('statement', '')[:100]
        print(f"  [{i}] {p['original_id']} (fixed_by_ai={fixed})")
        print(f"      {stmt}...")
    
    if len(peers) > 6:
        print(f"  ... and {len(peers) - 6} more peers")
