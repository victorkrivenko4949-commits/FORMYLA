#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json, os, sys
from collections import Counter

def write_report(path):
    lines = []
    lines.append("=== QUICK AUDIT ===")
    
    # 1. victor2
    if os.path.exists('victor2_generated.json'):
        with open('victor2_generated.json','rb') as f:
            data = json.loads(f.read())
        lines.append(f"victor2_generated.json: {len(data)} records")
        
        cells = Counter()
        by_level = Counter()
        by_grade = Counter()
        no_stmt = 0
        for d in data:
            stmt = d.get('statement','') or ''
            if not stmt.strip():
                no_stmt += 1
                continue
            lv = d.get('level',0)
            if isinstance(lv,str) and lv.startswith('L'):
                lv = int(lv[1])
            lv = int(lv or 0)
            grade = d.get('grade',0)
            tid = d.get('theme_id','')
            if 1 <= lv <= 3 and grade in (5,6,7,8,9,10,11):
                cells[f'G{grade}|{tid}|L{lv}'] += 1
                by_level[lv] += 1
                by_grade[grade] += 1
        
        lines.append(f"With statement: {len(data)-no_stmt}")
        lines.append(f"Cells L1-L3: {len(cells)}")
        for l in [1,2,3]:
            lc = sum(1 for k in cells if f'L{l}' in k)
            lines.append(f"  L{l}: {by_level[l]} tasks, {lc} cells")
        for g in sorted(by_grade):
            lines.append(f"  Grade {g}: {by_grade[g]} tasks")
    
    # 2. Taxonomy
    if os.path.exists('taxonomy_by_grade.json'):
        with open('taxonomy_by_grade.json','rb') as f:
            tax = json.loads(f.read())
        gt = tax.get('grade_theme_map',{})
        lines.append(f"\nTaxonomy grades: {sorted(gt.keys())}")
        total_sub = 0
        for g in sorted(gt):
            themes = gt[g]['themes']
            subtopics = 0
            for tid in themes:
                td = tax.get('theme_definitions',{}).get(tid,{})
                subtopics += len(td.get('subtopics',[]))
            total_sub += subtopics
            lines.append(f"  Grade {g}: {len(themes)} themes, {subtopics} subtopics, ids={themes}")
        lines.append(f"TOTAL subtopics: {total_sub}")
        lines.append(f"TARGET cells: {total_sub * 3}")
        lines.append(f"TARGET tasks: {total_sub * 3 * 5}")
    
    # 3. Pipeline output
    outdir = 'l1_l3_generation/max_fill_20260722_111737'
    lines.append(f"\nPipeline output dir: {outdir}")
    if os.path.isdir(outdir):
        files = os.listdir(outdir)
        lines.append(f"Files: {files}")
        for fn in files:
            fp = os.path.join(outdir, fn)
            lines.append(f"  {fn}: {os.path.getsize(fp)} bytes")
    else:
        lines.append("DIR NOT FOUND - pipeline produced nothing")
    
    # 4. Pipeline checkpoint
    cp = 'l1_l3_generation/l1_l3_generation_checkpoint.json'
    if os.path.exists(cp):
        with open(cp,'rb') as f:
            ck = json.loads(f.read())
        lines.append(f"\nCheckpoint exists: keys={list(ck.keys())[:10]}")
        lines.append(f"  approved_count={ck.get('approved_count','?')}")
        lines.append(f"  total_candidates={ck.get('total_candidates','?')}")
    else:
        lines.append(f"\nNo checkpoint at {cp}")
    
    # 5. Summary
    lines.append(f"\n=== SUMMARY ===")
    lines.append(f"Task file: victor2_generated.json")
    lines.append(f"Total records: {len(data)}")
    lines.append(f"Existing L1-L3 cells: {len(cells)} of {total_sub * 3} needed")
    lines.append(f"Shortage estimate: {total_sub * 3 * 5 - sum(cells.values())}")
    
    # Write to file
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f"Report written to {path}")

if __name__ == '__main__':
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_quick_audit_report.txt')
    write_report(path)
