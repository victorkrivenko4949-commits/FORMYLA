#!/usr/bin/env python3
"""Diagnose topic name mismatch between bank and canonical taxonomy."""
import sys, json, re
sys.stdout.reconfigure(encoding='utf-8')

print("=" * 60)
print("DIAGNOSTIC: Topic Mapping Analysis")
print("=" * 60)

# Load canonical taxonomy
with open('l4_l5_finalization/taxonomy_reconstruction/canonical_taxonomy.json', 'r', encoding='utf-8') as f:
    canon = json.load(f)

canon_themes = set()
for cc in canon['canonical_cells']:
    canon_themes.add(cc['theme_name'])

print(f"\n=== CANONICAL THEMES ({len(canon_themes)}) ===")
for t in sorted(canon_themes):
    print(f"  '{t}'")

# Load bank
with open('curated_bank_L1_L5_fixed.json', 'r', encoding='utf-8') as f:
    bank = json.load(f)

bank_topics = set()
for r in bank:
    t = r.get('topic') or r.get('theme_name') or ''
    if t:
        bank_topics.add(t)

print(f"\n=== BANK TOPICS ({len(bank_topics)}) ===")
for t in sorted(list(bank_topics)):
    print(f"  '{t}'")

# Overlap
overlap = canon_themes & bank_topics
print(f"\n=== OVERLAP: {len(overlap)} ===")
for t in overlap:
    print(f"  SHARED: '{t}'")

# Try normalized matching
def normalize(s):
    """Remove common separators, lowercase."""
    s = s.lower().strip()
    s = re.sub(r'[\s/:;,.-]+', ' ', s)
    s = s.replace('ё', 'е')
    return s.strip()

canon_normalized = {normalize(t): t for t in canon_themes}
bank_normalized = {normalize(t): t for t in bank_topics}

norm_overlap = set(canon_normalized.keys()) & set(bank_normalized.keys())
print(f"\n=== NORMALIZED OVERLAP: {len(norm_overlap)} ===")
for n in sorted(norm_overlap):
    print(f"  '{bank_normalized[n]}' -> '{canon_normalized[n]}'")

# Try substring matching
print("\n=== SUBSTRING MATCHES ===")
for bt in sorted(bank_topics):
    bt_lower = bt.lower()
    for ct in sorted(canon_themes):
        ct_lower = ct.lower()
        # Check if one is substring of the other (min 4 chars)
        if len(bt_lower) >= 4 and len(ct_lower) >= 4:
            if bt_lower in ct_lower or ct_lower in bt_lower:
                print(f"  '{bt}' <-> '{ct}'")
                break

# Try word overlap
print("\n=== WORD OVERLAP (bank topic -> canon theme) ===")
for bt in sorted(bank_topics):
    bt_words = set(normalize(bt).split())
    best_match = None
    best_score = 0
    for ct in canon_themes:
        ct_words = set(normalize(ct).split())
        if bt_words and ct_words:
            overlap_count = len(bt_words & ct_words)
            score = overlap_count / max(len(bt_words), len(ct_words))
            if score > best_score:
                best_score = score
                best_match = ct
    if best_score >= 0.5:
        print(f"  '{bt}' (score={best_score:.2f}) -> '{best_match}'")

print("\nDone.")
