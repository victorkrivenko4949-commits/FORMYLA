# -*- coding: utf-8 -*-
"""Inspect olympiad data structure"""
import sys
sys.path.insert(0, '.')

from olympiads import OLYMPIADS_DB

print(f"Total combos: {len(OLYMPIADS_DB)}")
print()

# Show unique olympiads and their source_urls
seen = {}
for c in OLYMPIADS_DB:
    slug = c.get('olympiad', '')
    if slug not in seen:
        seen[slug] = {
            'url': c.get('source_url', ''),
            'title': c.get('olympiad_title', ''),
            'rounds': set(),
            'years': set(),
            'grades': set(),
        }
    seen[slug]['rounds'].add(c.get('round', ''))
    seen[slug]['years'].add(c.get('year', ''))
    seen[slug]['grades'].add(c.get('grade', ''))

print("=== UNIQUE OLYMPIADS ===")
for slug, info in seen.items():
    print(f"\n{slug}:")
    print(f"  title: {info['title']}")
    print(f"  source_url: {info['url']}")
    print(f"  rounds: {sorted(info['rounds'])}")
    print(f"  years: {sorted(info['years'])}")
    print(f"  grades: {sorted(info['grades'])}")

# Check which ones are on olimpiada.ru
print("\n=== OLIMPIADA.RU CANDIDATES ===")
for slug, info in seen.items():
    if 'olimpiada.ru' in info['url'] or 'vsosh' in slug.lower():
        print(f"  {slug}: {info['url']}")
