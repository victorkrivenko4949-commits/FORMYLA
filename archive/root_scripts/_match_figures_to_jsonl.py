#!/usr/bin/env python3
"""Match solution_figures_index.json entries to JSONL tasks and show results."""
import json
import os

JSONL_PATH = r'C:\Users\Victor\Downloads\olympiad_DB_final_fixed.jsonl'
FIGURES_INDEX_PATH = 'data/solution_figures_index.json'

# Load figures index
with open(FIGURES_INDEX_PATH, 'r', encoding='utf-8') as f:
    figures_index = json.load(f)

print(f"Total keys in solution_figures_index.json: {len(figures_index)}")
print(f"Sample keys: {list(figures_index.keys())[:10]}")

# Build lookup: for each key, store the figure file paths
# Key format: olympiad|year|grade|round|problem_num

# Now scan JSONL
matches = []
total = 0
with open(JSONL_PATH, 'r', encoding='utf-8') as f:
    for line in f:
        entry = json.loads(line)
        total += 1
        o = entry.get('olympiad', '')
        year = str(entry.get('year', ''))
        grade = str(entry.get('grade', ''))
        round_key = entry.get('round', '')
        problems = entry.get('problems', [])
        
        for pi, problem in enumerate(problems):
            if isinstance(problem, dict):
                num = problem.get('num', str(pi + 1))
            else:
                num = str(pi + 1)
            
            key = f"{o}|{year}|{grade}|{round_key}|{num}"
            if key in figures_index:
                matches.append({
                    'entry_id': entry.get('id'),
                    'olympiad': o,
                    'title': entry.get('olympiad_title', ''),
                    'year': year,
                    'grade': grade,
                    'round': round_key,
                    'problem_num': num,
                    'problem_text': (problem.get('text', '') if isinstance(problem, dict) else str(problem))[:300],
                    'figures': figures_index[key]
                })

print(f"\nTotal JSONL entries scanned: {total}")
print(f"Total matches found: {len(matches)}")

# Show first 10 matches
for i, m in enumerate(matches[:10]):
    print(f"\n{'='*80}")
    print(f"MATCH {i+1}: {m['olympiad']}|{m['year']}|{m['grade']}|{m['round']}|{m['problem_num']}")
    print(f"  Olympiad: {m['title']} (id={m['entry_id']})")
    print(f"  Problem text: {m['problem_text'][:200]}...")
    for fig in m['figures']:
        print(f"  Figure file: {fig['file']}")
        print(f"  Source URL: {fig.get('source_url', 'N/A')}")
        # Check if file exists
        fig_path = os.path.join('static', fig['file'])
        print(f"  Exists on disk: {os.path.isfile(fig_path)}")

# Show all unique olympiads that matched
olympiads_matched = set(m['olympiad'] for m in matches)
print(f"\n\nUnique olympiads with figure matches: {sorted(olympiads_matched)}")

# Count by olympiad
from collections import Counter
olympiad_counts = Counter(m['olympiad'] for m in matches)
for o, c in olympiad_counts.most_common():
    print(f"  {o}: {c} matches")

# Also check if any figure file references a fu (Физтех) image
print("\n\nChecking for fu/Fiztekh references in figures_index keys:")
fu_keys = [k for k in figures_index.keys() if k.startswith('fu')]
print(f"  fu keys: {len(fu_keys)} -> {fu_keys[:10]}")
