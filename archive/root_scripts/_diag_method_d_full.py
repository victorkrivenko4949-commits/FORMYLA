#!/usr/bin/env python3
"""Comprehensive diagnostics for Method D metadata join."""
import sys
import json
from collections import defaultdict, Counter

sys.stdout.reconfigure(encoding='utf-8')

# ── 1. Load canonical taxonomy ──
with open('l4_l5_finalization/taxonomy_reconstruction/canonical_taxonomy.json', 'r', encoding='utf-8') as f:
    canon = json.load(f)

canonical_dict = {}
for cc in canon.get('canonical_cells', []):
    canonical_dict[cc['cell_key']] = {
        'grade': cc['grade'],
        'level': cc['level'],
        'topic_id': cc['topic_id'],
        'theme_name': cc['theme_name'],
        'subtopic_index': cc['subtopic_index'],
        'subtopic_name': cc['subtopic_name']
    }

print(f"Canonical taxonomy: {len(canonical_dict)} total cells")

# Level distribution
level_counts = Counter()
grade_level_counts = Counter()
for ck, cinfo in canonical_dict.items():
    level_counts[cinfo['level']] += 1
    grade_level_counts[(cinfo['grade'], cinfo['level'])] += 1

print(f"\nCanonical level distribution:")
for level, count in sorted(level_counts.items()):
    print(f"  {level}: {count} cells")

print(f"\nCanonical grade+level distribution:")
for (g, l), count in sorted(grade_level_counts.items()):
    print(f"  G{g}|{l}: {count} cells")

# ── 2. Load bank ──
with open('curated_bank_L1_L5_fixed.json', 'r', encoding='utf-8') as f:
    bank = json.load(f)

records = bank if isinstance(bank, list) else []
print(f"\nBank records: {len(records)} total")

# ── 3. Bank level distribution ──
bank_level_dist = Counter()
bank_grade_dist = Counter()
bank_grade_level_dist = Counter()
bank_topic_mismatches = Counter()

for r in records:
    if not isinstance(r, dict):
        continue
    lvl = r.get('level')
    gr = r.get('grade')
    topic = r.get('topic') or r.get('theme_name') or ''
    
    if lvl is not None:
        bank_level_dist[lvl] += 1
    if gr is not None:
        bank_grade_dist[gr] += 1
    if gr is not None and lvl is not None:
        bank_grade_level_dist[(gr, lvl)] += 1

print(f"\nBank level distribution (numeric):")
for level, count in sorted(bank_level_dist.items()):
    print(f"  Level {level}: {count} tasks")

print(f"\nBank grade distribution:")
for grade, count in sorted(bank_grade_dist.items()):
    print(f"  Grade {grade}: {count} tasks")

# ── 4. Build canonical lookup ──
grade_level_topic_lookup = defaultdict(list)
for ck, cinfo in canonical_dict.items():
    meta_key = (cinfo['grade'], cinfo['level'], cinfo['theme_name'])
    grade_level_topic_lookup[meta_key].append(ck)

print(f"\nCanonical grade+level+topic lookup: {len(grade_level_topic_lookup)} unique keys")

# ── 5. Count how many bank records can match via Method D ──
matched = 0
unmatched = 0
matched_by_grade_level = Counter()
unmatched_reasons = Counter()
total_l4_l5_bank = 0

for r in records:
    if not isinstance(r, dict):
        continue
    gr = r.get('grade')
    lvl = r.get('level')
    topic = r.get('topic') or r.get('theme_name') or ''
    
    # Count L4/L5 bank tasks
    if lvl in (4, 5):
        total_l4_l5_bank += 1
    
    if gr is not None and lvl is not None and topic:
        level_key = f"L{lvl}"
        meta_key = (int(gr), level_key, topic)
        
        if meta_key in grade_level_topic_lookup:
            matched += 1
            matched_by_grade_level[(int(gr), f"L{lvl}")] += 1
        else:
            unmatched += 1
            # Check WHY it doesn't match
            # Reason 1: Level not in canon at all for this grade
            g_l_keys = [(k, v) for k, v in grade_level_topic_lookup.items() 
                       if k[0] == int(gr) and k[1] == level_key]
            if not g_l_keys:
                unmatched_reasons[f"Grade {gr}/{level_key}: no cells in canon at all"] += 1
            else:
                # Reason 2: Topic mismatch
                unmatched_reasons[f"Grade {gr}/{level_key}: topic mismatch"] += 1
    else:
        unmatched += 1
        if gr is None:
            unmatched_reasons["Missing grade"] += 1
        elif lvl is None:
            unmatched_reasons["Missing level"] += 1
        else:
            unmatched_reasons["Missing topic"] += 1

print(f"\n── Method D Mapping Results ──")
print(f"  Total bank records: {len(records)}")
print(f"  L4/L5 bank tasks: {total_l4_l5_bank}")
print(f"  Mapped via Method D: {matched}")
print(f"  Unmapped: {unmatched}")

print(f"\n  Mapped by grade+level:")
for key, count in sorted(matched_by_grade_level.items()):
    print(f"    G{key[0]}|{key[1]}: {count}")

print(f"\n  Unmatched reasons (top 15):")
for reason, count in unmatched_reasons.most_common(15):
    print(f"    {reason}: {count}")

# ── 6. Check all canonical theme_names vs bank topics ──
canon_themes = set()
for ck, cinfo in canonical_dict.items():
    canon_themes.add(cinfo['theme_name'])

bank_topics = set()
for r in records:
    if isinstance(r, dict):
        t = r.get('topic') or ''
        if t:
            bank_topics.add(t)

overlap = canon_themes & bank_topics
canon_only = canon_themes - bank_topics
bank_only = bank_topics - canon_themes

print(f"\n── Topic/Theme Name Overlap ──")
print(f"  Canonical themes: {len(canon_themes)}")
print(f"  Bank topics: {len(bank_topics)}")
print(f"  Overlap: {len(overlap)}")
print(f"  Canon-only themes: {len(canon_only)}")
print(f"  Bank-only topics: {len(bank_only)}")

if canon_only:
    print(f"\n  Canon-only themes (up to 10):")
    for t in sorted(list(canon_only))[:10]:
        print(f"    {t!r}")
if bank_only:
    print(f"\n  Bank-only topics (up to 10):")
    for t in sorted(list(bank_only))[:10]:
        print(f"    {t!r}")
