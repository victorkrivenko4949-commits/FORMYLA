#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf-8')

from olympiads import OLYMPIADS_DB

latex_tasks = []
plain_tasks = []
for c in OLYMPIADS_DB:
    for p in c.get('problems', []):
        t = p.get('text', '')
        if '\\' in t:
            latex_tasks.append((c.get('olympiad',''), t[:250]))
        elif len(t) > 30:
            plain_tasks.append((c.get('olympiad',''), t[:250]))

with open('scripts/_latex_analysis.txt', 'w', encoding='utf-8') as f:
    f.write(f'Tasks with backslash (LaTeX-like): {len(latex_tasks)}\n')
    f.write(f'Tasks without backslash (plain): {len(plain_tasks)}\n\n')
    f.write('=== LATEX SAMPLES ===\n')
    for slug, t in latex_tasks[:10]:
        f.write(f'[{slug}] {t}\n---\n')
    f.write('\n=== PLAIN SAMPLES ===\n')
    for slug, t in plain_tasks[:5]:
        f.write(f'[{slug}] {t}\n---\n')
