# -*- coding: utf-8 -*-
"""P2 test: verify семёрка selection for 3 different 9th grade profiles."""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

# Avoid encoding issues by writing to file
results = []

results.append('=== ПРОФИЛЬ 1: первый цикл 9 класс (без mu) ===')
from curator.monthly_cycle import _select_first_cycle_themes
from daily_tasks.monthly_plan import subtopic_title
from services.theme_registry import section_of_theme

t1 = _select_first_cycle_themes(9)
for i, t in enumerate(t1, 1):
    sec = section_of_theme(t) or '?'
    name = subtopic_title(t)
    results.append(f'  {i}. {t} [{sec}] {name}')
sc = {}
for t in t1:
    s = section_of_theme(t) or '?'
    sc[s] = sc.get(s, 0) + 1
results.append(f'  Section counts: {sc}')
fail = any(c > 2 for c in sc.values())
results.append(f'  П2(в) max-2-per-section: {"PASS" if not fail else "FAIL"}')

results.append('')
results.append('=== ПРОФИЛЬ 2: повторный вызов (детерминизм) ===')
t2 = _select_first_cycle_themes(9)
for i, t in enumerate(t2, 1):
    results.append(f'  {i}. {t} [{section_of_theme(t) or "?"}] {subtopic_title(t)}')
results.append(f'  Same as Profile 1: {t1 == t2}')

results.append('')
results.append('=== ПРОФИЛЬ 3: первый цикл 10 класс ===')
t3 = _select_first_cycle_themes(10)
for i, t in enumerate(t3, 1):
    results.append(f'  {i}. {t} [{section_of_theme(t) or "?"}] {subtopic_title(t)}')
sc3 = {}
for t in t3:
    s = section_of_theme(t) or '?'
    sc3[s] = sc3.get(s, 0) + 1
results.append(f'  Section counts: {sc3}')
fail3 = any(c > 2 for c in sc3.values())
results.append(f'  П2(в) max-2-per-section: {"PASS" if not fail3 else "FAIL"}')

# Write results
out_path = os.path.join(os.path.dirname(__file__), '_p2_results.txt')
with open(out_path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(results))
print(f'Results written to {out_path}')
