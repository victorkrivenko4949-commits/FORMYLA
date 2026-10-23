# -*- coding: utf-8 -*-
"""Task 1: verify anchors loading and picking."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app
app.config['SERVER_NAME'] = 'localhost'

with app.app_context():
    from services.anchors import load_anchors, pick_anchors, inspect_anchors, CANONICAL_SECTIONS_ORDER
    
    # 1. Load anchors
    a = load_anchors()
    print("=== load_anchors() ===")
    print("total_in_file:", a['total_in_file'])
    print("loaded:", a['loaded'])
    print("skipped:", a['skipped'])
    print("errors:", a['errors'])
    print("unmapped_themes:", a.get('unmapped_themes', []))
    
    # 2. Inspect
    insp = inspect_anchors()
    print("\n=== inspect_anchors() ===")
    print("total:", insp['total'])
    grades = sorted({int(g) for g in insp['by_grade'].keys()})
    print("grades:", grades)
    for g_str, data in sorted(insp['by_grade'].items(), key=lambda x: int(x[0])):
        print(f"  grade {g_str}: {data['count']} tasks, sections={data.get('sections', [])}")
    
    # 3. pick_anchors for each grade
    print("\n=== pick_anchors per grade ===")
    for g in range(5, 12):
        anchors, meta = pick_anchors(g)
        print(f"grade {g}: {len(anchors)} anchors, sections={[x['section'] for x in anchors]}, uids={[x['anchor_uid'] for x in anchors]}")
