# -*- coding: utf-8 -*-
"""Find all routes related to adaptive/test in the project."""
import re

files_to_check = ['app.py', 'routes/prep.py', 'routes/wb_ws.py', 'routes/decorators.py']

for path in files_to_check:
    with open(path, 'r', encoding='utf-8') as f:
        txt = f.read()
    
    # Find all @...route(...) patterns
    routes = re.findall(r'@(?:app|prep_bp|bp)\.route\([^)]+\)|@(?:app|bp)\.route\([^)]+\)', txt)
    relevant = [r for r in routes if any(w in r.lower() for w in ['test', 'topic', 'adapt', 'themes', 'diagn', 'questionnaire'])]
    if relevant:
        print(f'\n=== {path} ===')
        for r in relevant:
            print(f'  {r}')

# Also check templates for links to test pages
import os
for root, dirs, files in os.walk('templates'):
    for f in files:
        if f.endswith('.html'):
            path = os.path.join(root, f)
            with open(path, 'r', encoding='utf-8') as fh:
                txt = fh.read()
            links = re.findall(r'href=["\'](/[^"\']+)["\']', txt)
            test_links = [l for l in links if any(w in l.lower() for w in ['test', 'topic', 'adapt', 'themes'])]
            if test_links:
                print(f'\n=== {path} (links) ===')
                for l in test_links:
                    print(f'  {l}')
