#!/usr/bin/env python3
"""Extract all PDF links from olymp.mipt.ru/olympiad/samples and categorize them."""
import urllib.request
import os
import re
import json

out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_probe_results.txt')
results = []
BASE = 'https://olymp.mipt.ru'

def fetch(url):
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    })
    r = urllib.request.urlopen(req, timeout=15)
    return r.read().decode('utf-8', errors='replace')

# Fetch the samples page and extract ALL PDF links
html = fetch(BASE + '/olympiad/samples')
pdf_links = re.findall(r'href=["\']([^"\']*\.pdf)["\']', html, re.IGNORECASE)
results.append(f"Total PDF links in /olympiad/samples: {len(pdf_links)}")
results.append("")

# Categorize
math_pdfs = []
physics_pdfs = []
other_pdfs = []

for link in pdf_links:
    # Get filename from the URL
    fname = link.split('/')[-1]
    url = BASE + link if link.startswith('/') else link
    
    # Categorize by content of filename
    fname_lower = fname.lower()
    if 'matem' in fname_lower or 'math' in fname_lower or 'матем' in fname_lower:
        math_pdfs.append((url, fname))
    elif 'fizik' in fname_lower or 'fizika' in fname_lower or 'phys' in fname_lower or 'физик' in fname_lower:
        physics_pdfs.append((url, fname))
    elif 'razball' in fname_lower or 'критери' in fname_lower or 'criteri' in fname_lower:
        other_pdfs.append((url, f'[CRITERIA] {fname}'))
    elif 'reshenie' in fname_lower or 'resh' in fname_lower or 'решен' in fname_lower or 'solution' in fname_lower:
        other_pdfs.append((url, f'[SOLUTION] {fname}'))
    elif 'bilet' in fname_lower or 'вариант' in fname_lower or 'variant' in fname_lower:
        other_pdfs.append((url, f'[TASK] {fname}'))
    else:
        # Try to detect from full URL path context
        other_pdfs.append((url, f'[OTHER] {fname}'))

results.append(f"=== Math PDFs ({len(math_pdfs)}) ===")
for url, fname in math_pdfs:
    results.append(f"  {url}")
    results.append(f"    -> {fname}")

results.append(f"\n=== Physics PDFs ({len(physics_pdfs)}) ===")
for url, fname in physics_pdfs[:10]:
    results.append(f"  {fname}")

results.append(f"\n=== Other PDFs ({len(other_pdfs)}) ===")
for url, fname in other_pdfs:
    results.append(f"  {fname}")

# Also try to access the page content more fully - look for year mentions with context
years_found = set(re.findall(r'20\d\d', html))
results.append(f"\n=== Years found: {sorted(years_found)} ===")

# Look for grade mentions with context
grades_found = set(re.findall(r'(\d+)\s*класс', html))
results.append(f"Grades found: {sorted(grades_found)}")

with open(out_path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(results))

print(f'Results written to: {out_path}', flush=True)
