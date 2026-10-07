#!/usr/bin/env python3
"""Find olympiad tasks that have images attached."""
import json
import re

JSONL_PATH = r'C:\Users\Victor\Downloads\olympiad_DB_final_fixed.jsonl'

# Regex patterns to detect image references in text
IMG_PATTERNS = [
    r'!\[.*?\]\(.*?\)',           # Markdown image: ![alt](url)
    r'<img\b[^>]*?>',             # HTML img tag
    r'https?://\S+\.(?:png|jpg|jpeg|gif|svg|webp)\b',  # Direct image URLs
    r'\[\s*рис\.?\s*\d+\s*\]',    # [рис. 1], [рис 1]
    r'рисун(?:ок|ке|ка)\s*\d+',   # рисунок 1, рисунке 2
]

count = 0
matches = []

with open(JSONL_PATH, 'r', encoding='utf-8') as f:
    for line in f:
        entry = json.loads(line)
        entry_id = entry.get('id', '?')
        olympiad = entry.get('olympiad', '?')
        
        problems = entry.get('problems', [])
        if not problems:
            continue
        
        for pi, problem in enumerate(problems):
            if isinstance(problem, str):
                text = problem
            elif isinstance(problem, dict):
                text = json.dumps(problem, ensure_ascii=False)
            else:
                text = str(problem)
            
            found = []
            for pattern in IMG_PATTERNS:
                if re.search(pattern, text, re.IGNORECASE):
                    found.append(pattern)
            
            if found:
                matches.append((entry_id, olympiad, pi, text[:300]))
                count += 1

print(f"Found {count} tasks with potential image references:\n")
for entry_id, olympiad, pi, snippet in matches[:20]:
    print(f"--- Entry {entry_id}, {olympiad}, problem #{pi} ---")
    print(snippet)
    print()

if count > 20:
    print(f"... and {count - 20} more")
