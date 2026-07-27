#!/usr/bin/env python3
"""Deep diagnostic: categorize WHY each L4/L5 record failed to map.

Categories:
  A. Topic NOT in curated mapping (no topic_id possible)
  B. Topic IS in mapping, but (grade, level, topic_id) combo NOT in canonical
  C. Topic IS in mapping, combo EXISTS, but other bug
"""
import json
import os
import sys
from collections import Counter, defaultdict

RECON_DIR = os.path.dirname(os.path.abspath(__file__))

# Import the mapping functions from _taxonomy_reconstruct.py
sys.path.insert(0, RECON_DIR)
from _taxonomy_reconstruct import build_curated_topic_mapping, map_curated_topic_to_theme


def load_canonical(recon_dir):
    """Load canonical taxonomy and build grade_level_topic_id_lookup."""
    canon_path = os.path.join(recon_dir, 'canonical_taxonomy.json')
    with open(canon_path, 'r', encoding='utf-8') as f:
        canon = json.load(f)
    
    # Build canonical_dict as used in step_14_5
    canonical_dict = {}
    for cell in canon.get('canonical_cells', []):
        ck = cell.get('cell_key') or f"{cell.get('grade')}|{cell.get('level')}|{cell.get('topic_id')}|{cell.get('subtopic_name','')}"
        canonical_dict[ck] = cell
    
    # Build the same lookups as step_14_5
    from collections import defaultdict
    grade_level_topic_id_lookup = defaultdict(list)
    for ck, cinfo in canonical_dict.items():
        tid_key = (cinfo["grade"], cinfo["level"], cinfo["topic_id"])
        grade_level_topic_id_lookup[tid_key].append(ck)
    
    return canon, canonical_dict, grade_level_topic_id_lookup


def main():
    crosswalk_path = os.path.join(RECON_DIR, 'bank_taxonomy_crosswalk.jsonl')
    
    # Load crosswalk
    unresolved = []
    resolved = []
    with open(crosswalk_path, 'r', encoding='utf-8') as f:
        for line in f:
            e = json.loads(line)
            if e.get('cell_key'):
                resolved.append(e)
            else:
                unresolved.append(e)
    
    print(f"Total: {len(unresolved)+len(resolved)}, Resolved: {len(resolved)}, Unresolved: {len(unresolved)}")
    
    # Load topic mapping
    topic_mapping = build_curated_topic_mapping()
    print(f"Curated topic mapping has {len(topic_mapping)} entries")
    
    # Load canonical
    canon, canonical_dict, grade_level_topic_id_lookup = load_canonical(RECON_DIR)
    
    # Only analyze L4/L5
    l4_l5_unresolved = [e for e in unresolved if e.get('bank_level') in [4, 5]]
    print(f"\nL4/L5 unresolved: {len(l4_l5_unresolved)}")
    
    # Categorize
    cat_a = []  # Topic not in mapping
    cat_b = []  # Topic in mapping, but (grade,level,topic_id) not in canonical
    cat_c = []  # Topic in mapping, combo exists, but still didn't match (bug)
    
    for e in l4_l5_unresolved:
        bank_topic = e.get('bank_topic', '')
        bank_grade = e.get('bank_grade')
        bank_level = e.get('bank_level')
        
        if not bank_topic:
            cat_a.append((e, "Empty topic"))
            continue
        
        topic_id = map_curated_topic_to_theme(bank_topic, topic_mapping)
        
        if not topic_id:
            cat_a.append((e, f"No mapping for topic '{bank_topic}'"))
            continue
        
        level_key = f"L{bank_level}"
        tid_key = (int(bank_grade), level_key, topic_id)
        candidates = grade_level_topic_id_lookup.get(tid_key, [])
        
        if not candidates:
            cat_b.append((e, f"Topic '{bank_topic}'->{topic_id}, but (grade={bank_grade}, level={level_key}, topic_id={topic_id}) NOT in canonical"))
        else:
            cat_c.append((e, f"BUG? Topic '{bank_topic}'->{topic_id}, {len(candidates)} candidates exist for ({bank_grade},{level_key},{topic_id})"))
    
    print(f"\n=== CATEGORIZATION ===")
    print(f"Category A (topic not in mapping): {len(cat_a)}")
    print(f"Category B (topic in mapping, combo not in canon): {len(cat_b)}")
    print(f"Category C (should have matched but didn't - BUG): {len(cat_c)}")
    
    # Category A: Topics not in mapping
    print(f"\n--- Category A: Topics not in curated mapping ({len(cat_a)}) ---")
    a_topic_counts = Counter(e[0].get('bank_topic','') for e in cat_a)
    for topic, count in a_topic_counts.most_common(50):
        grades = sorted(set(e[0].get('bank_grade') for e in cat_a if e[0].get('bank_topic') == topic))
        print(f"  '{topic}' (x{count}) [grades={grades}]")
    
    # Category B: Grade/topic combo not in canonical
    print(f"\n--- Category B: Grade+topic combo not in canonical ({len(cat_b)}) ---")
    
    # Group by topic_id
    b_by_topic = defaultdict(list)
    for e, reason in cat_b:
        bank_topic = e.get('bank_topic', '')
        topic_id = map_curated_topic_to_theme(bank_topic, topic_mapping)
        b_by_topic[topic_id].append(e)
    
    for topic_id in sorted(b_by_topic.keys()):
        entries = b_by_topic[topic_id]
        topic_name = entries[0].get('bank_topic', '')
        grade_levels = defaultdict(list)
        for e in entries:
            grade_levels[(e.get('bank_grade'), e.get('bank_level'))].append(e.get('bank_topic'))
        print(f"  {topic_id} (via '{topic_name}'): {len(entries)} records")
        
        # Show what grades canonical HAS for this topic
        canon_topic = canon.get('topics', {}).get(topic_id, {})
        canon_grades = canon_topic.get('grades', [])
        print(f"    Canonical grades for {topic_id}: {canon_grades}")
        
        # Show bank grades that don't match
        bank_grades = sorted(set(e.get('bank_grade') for e in entries))
        print(f"    Bank grades: {bank_grades}")
        
        # Show missing grades
        missing = [g for g in bank_grades if g not in canon_grades]
        print(f"    Missing from canonical: {missing}")
    
    # Category C: Should match but didn't - show details
    print(f"\n--- Category C: Should have matched but didn't ({len(cat_c)}) ---")
    c_by_topic = defaultdict(list)
    for e, reason in cat_c:
        bank_topic = e.get('bank_topic', '')
        topic_id = map_curated_topic_to_theme(bank_topic, topic_mapping)
        c_by_topic[topic_id].append(e)
    
    for topic_id in sorted(c_by_topic.keys()):
        entries = c_by_topic[topic_id]
        topic_name = entries[0].get('bank_topic', '')
        grade_levels = defaultdict(list)
        for e in entries:
            grade_levels[(e.get('bank_grade'), e.get('bank_level'))].append(e.get('bank_topic'))
        print(f"  {topic_id} (via '{topic_name}'): {len(entries)} records")
        for (g, l), topics in sorted(grade_levels.items()):
            print(f"    grade={g}, level=L{l}: {len(topics)} records")
    
    # Summary
    print(f"\n=== ACTIONABLE SUMMARY ===")
    print(f"Add {len(a_topic_counts)} missing topic names to curated mapping - could help some Category A records")
    print(f"Category B ({len(cat_b)}) cannot be fixed without expanding canonical taxonomy's grade ranges")
    print(f"Category C ({len(cat_c)}) records have valid (grade,level,topic_id) combo in canonical")
    print(f"  -> These {len(cat_c)} records would be resolved by a fresh run of step_14_5 with the updated mapping")


if __name__ == '__main__':
    main()
