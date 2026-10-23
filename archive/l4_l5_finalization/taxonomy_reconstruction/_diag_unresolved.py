#!/usr/bin/env python3
"""Diagnose why 617/665 bank records are unresolved after Method D fixes."""
import json
import os
import sys
from collections import Counter

RECON_DIR = os.path.dirname(os.path.abspath(__file__))

def main():
    # 1. Read crosswalk
    crosswalk_path = os.path.join(RECON_DIR, 'bank_taxonomy_crosswalk.jsonl')
    unresolved = []
    resolved = []
    with open(crosswalk_path, 'r', encoding='utf-8') as f:
        for line in f:
            e = json.loads(line)
            if e.get('cell_key'):
                resolved.append(e)
            else:
                unresolved.append(e)

    print(f"Total crosswalk entries: {len(unresolved) + len(resolved)}")
    print(f"Total unresolved: {len(unresolved)}")
    print(f"Total resolved: {len(resolved)}")

    # 2. Level distribution
    level_counts = Counter(e.get('bank_level') for e in unresolved)
    print(f"\n--- Unresolved by bank_level ---")
    for level, count in sorted(level_counts.items(), key=lambda x: (x[0] is None, x[0] if x[0] is not None else 0)):
        label = f"L{level}" if level is not None else "None"
        print(f"  {label}: {count}")

    # 3. L4/L5 unresolved - show unique topics with grade breakdown
    l4_l5_unresolved = [e for e in unresolved if e.get('bank_level') in [4, 5]]
    print(f"\n--- L4/L5 Unresolved: {len(l4_l5_unresolved)} ---")
    topic_counts = Counter(e.get('bank_topic') for e in l4_l5_unresolved)
    print(f"Unique L4/L5 topics: {len(topic_counts)}")

    print(f"\nTop 30 L4/L5 unresolved topics:")
    for topic, count in topic_counts.most_common(30):
        grade_topic = Counter(f"G{e.get('bank_grade')}" for e in l4_l5_unresolved if e.get('bank_topic') == topic)
        grades = ', '.join(sorted(grade_topic.keys()))
        print(f"  '{topic}' (x{count}) [{grades}]")

    # 4. L4/L5 resolved - show topics that mapped successfully
    l4_l5_resolved = [e for e in resolved if e.get('bank_level') in [4, 5]]
    print(f"\n--- L4/L5 Resolved: {len(l4_l5_resolved)} ---")
    resolved_topics = Counter(e.get('bank_topic') for e in l4_l5_resolved)
    print(f"Unique L4/L5 topics resolved: {len(resolved_topics)}")
    print(f"\nResolved topics:")
    for topic, count in resolved_topics.most_common():
        print(f"  '{topic}' (x{count})")

    # 5. L1-L3 unresolved
    l1_l3_unresolved = [e for e in unresolved if e.get('bank_level') not in [4, 5] and e.get('bank_level') is not None]
    print(f"\n--- L1-L3 Unresolved: {len(l1_l3_unresolved)} ---")
    l1_l3_levels = Counter(e.get('bank_level') for e in l1_l3_unresolved if e.get('bank_level') is not None)
    print(f"By level: {dict(l1_l3_levels)}")
    l1_l3_topics = Counter(e.get('bank_topic') for e in l1_l3_unresolved)
    print(f"Unique topics: {len(l1_l3_topics)}")

    # 6. Read the curated topic mapping to see what topics are covered
    print(f"\n--- Curated Topic Mapping Analysis ---")
    # Read the mapping from _taxonomy_reconstruct.py's build_curated_topic_mapping()
    # or from _fill_l4_l5_pipeline.py
    # Let's check by looking at the crosswalk for what CAN be mapped
    print(f"\n--- Summary ---")
    print(f"L1-L3 records (can NEVER match canonical taxonomy): {len(l1_l3_unresolved)}")
    print(f"L4/L5 records that COULD match but didn't: {len(l4_l5_unresolved)}")
    print(f"L4/L5 records that DID match: {len(l4_l5_resolved)}")
    print(f"Total L4/L5 in bank: {len(l4_l5_unresolved) + len(l4_l5_resolved)}")

    # 7. Sample unresolved records (first 20)
    print(f"\n--- Sample L4/L5 unresolved records (first 15) ---")
    for e in l4_l5_unresolved[:15]:
        print(f"  grade={e.get('bank_grade')}, level={e.get('bank_level')}, topic='{e.get('bank_topic')}'")

    # 8. Check if the canonical taxonomy has entries for these grades
    print(f"\n--- Canonical taxonomy grades ---")
    canon_path = os.path.join(RECON_DIR, 'canonical_taxonomy.json')
    with open(canon_path) as f:
        canon = json.load(f)
    print(f"Meta grades: {canon.get('meta', {}).get('grades_present', [])}")
    print(f"Meta levels: {canon.get('meta', {}).get('levels', [])}")
    print(f"Total topics: {len(canon.get('topics', {}))}")
    print(f"Total canonical cells: {len(canon.get('canonical_cells', []))}")

    # Count canonical cells by (grade, level)
    cell_gl = Counter((c.get('grade'), c.get('level')) for c in canon.get('canonical_cells', []))
    print(f"\nCanonical cells by (grade, level):")
    for (g, l), count in sorted(cell_gl.items(), key=lambda x: (x[0][0] if x[0][0] is not None else 0, x[0][1] if x[0][1] is not None else 0)):
        g_label = g if g is not None else "None"
        l_label = l if l is not None else "None"
        print(f"  G{g_label} L{l_label}: {count} cells")

if __name__ == '__main__':
    main()
