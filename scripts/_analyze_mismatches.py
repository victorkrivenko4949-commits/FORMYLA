#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

data = json.load(open('data/_audit_mismatches.json', 'r', encoding='utf-8'))
mm = data['mismatches']

# Group by category
cats = {}
for m in mm:
    c = m['category']
    if c not in cats:
        cats[c] = []
    cats[c].append(m)

print("=" * 70)
print("MISMATCH ANALYSIS")
print("=" * 70)

for cat in sorted(cats.keys()):
    items = cats[cat]
    print(f"\n{'='*50}")
    print(f"{cat.upper()}: {len(items)} mismatches")
    print(f"{'='*50}")
    
    # Show first 5 samples
    for m in items[:5]:
        print(f"\n  ID {m['id']} | Grade {m['grade']} | Topic: {m['topic']}")
        print(f"  Text: {m['text'][:200]}")
    
    # Show topic distribution
    topics = {}
    for m in items:
        t = m['topic']
        topics[t] = topics.get(t, 0) + 1
    print(f"\n  Topic distribution:")
    for t, cnt in sorted(topics.items(), key=lambda x: -x[1])[:10]:
        print(f"    {t}: {cnt}")

# Movement mismatches - show ALL
print(f"\n{'='*70}")
print(f"ALL MOVEMENT MISMATCHES ({len(cats.get('movement', []))})")
print(f"{'='*70}")
for m in cats.get('movement', []):
    print(f"\n  ID {m['id']} | Grade {m['grade']} | Topic: {m['topic']}")
    print(f"  Text: {m['text'][:250]}")

# Knights & Liars - should be 0 but let's check
kl = cats.get('knights_liars', [])
print(f"\n{'='*70}")
print(f"ALL KNIGHTS_LIARS MISMATCHES ({len(kl)})")
print(f"{'='*70}")
for m in kl:
    print(f"\n  ID {m['id']} | Grade {m['grade']} | Topic: {m['topic']}")
    print(f"  Text: {m['text'][:250]}")

# Grade issues
gi = data.get('grade_issues', [])
print(f"\n{'='*70}")
print(f"GRADE ISSUES ({len(gi)}) - first 10")
print(f"{'='*70}")
for g in gi[:10]:
    print(f"\n  ID {g['id']} | Grade {g['grade']} | Topic: {g['topic']}")
    print(f"  Reason: {g['reason']}")
    print(f"  Text: {g['text'][:200]}")
