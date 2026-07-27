#!/usr/bin/env python3
"""Match problem_images/*.png to JSONL tasks and show them."""
import json, os, re

JSONL_PATH = r'C:\Users\Victor\Downloads\olympiad_DB_final_fixed.jsonl'
PROBLEM_IMG_DIR = 'static/problem_images'
FIGURES_INDEX_PATH = 'data/solution_figures_index.json'

# 1) Load all JSONL entries into a lookup by (olympiad, year, grade, problem_num)
print("Loading JSONL...")
entries_by_key = {}  # key: "olympiad|year|grade|num" -> entry
with open(JSONL_PATH, 'r', encoding='utf-8') as f:
    for line in f:
        entry = json.loads(line)
        o = entry.get('olympiad', '')
        year = str(entry.get('year', ''))
        grade = str(entry.get('grade', ''))
        problems = entry.get('problems', [])
        for pi, problem in enumerate(problems):
            if isinstance(problem, dict):
                num = str(problem.get('num', pi + 1))
                text = problem.get('text', '')
                solution = problem.get('solution', '')
            else:
                num = str(pi + 1)
                text = str(problem)
                solution = ''
            key = f"{o}|{year}|{grade}|{num}"
            if key not in entries_by_key:
                entries_by_key[key] = []
            entries_by_key[key].append({
                'entry': entry,
                'problem_num': num,
                'text': text[:500],
                'solution': solution[:200],
            })

print(f"Loaded {len(entries_by_key)} unique (olympiad|year|grade|num) keys")

# 2) Scan problem_images directory
if os.path.isdir(PROBLEM_IMG_DIR):
    images = sorted([f for f in os.listdir(PROBLEM_IMG_DIR) if f.endswith('.png')])
    print(f"\nFound {len(images)} images in problem_images/")
    
    # Parse filenames: olympiad_year_grade_num.png
    # e.g., formula_unity_2020_7_4.png
    img_pattern = re.compile(r'^(.+)_(\d{4})_(\d+)_(\d+)\.png$')
    
    for img in images:
        m = img_pattern.match(img)
        if not m:
            print(f"  SKIP (unparsable): {img}")
            continue
        olympiad = m.group(1)
        year = m.group(2)
        grade = m.group(3)
        num = m.group(4)
        
        # Also try with underscores - olympiad name might have underscores
        # e.g., "formula_unity" -> olympiad="formula_unity"
        # But actually formula_unity_2020_7_4.png gives olympiad="formula", year="unity"... 
        # That's wrong. Let me rethink.
        
        img_path = os.path.join(PROBLEM_IMG_DIR, img)
        img_size = os.path.getsize(img_path)
        
        # Try to find in JSONL - but the olympiad slug might differ
        key_attempts = []
        
        # The filename format could be:
        # formula_unity_2020_7_4.png -> olympiad="formula_unity", year=2020, grade=7, num=4
        # But regex gave olympiad="formula", year="unity"... Let me fix this.
        
        # Actually the names have multiple underscores. Let me parse properly:
        # formula_unity_2020_7_4.png -> parts = ['formula', 'unity', '2020', '7', '4']
        parts = img.replace('.png', '').split('_')
        # last 3 parts are year, grade, num
        year2 = parts[-3]
        grade2 = parts[-2]
        num2 = parts[-1]
        olympiad2 = '_'.join(parts[:-3])  # everything before year
        
        key = f"{olympiad2}|{year2}|{grade2}|{num2}"
        
        matched = entries_by_key.get(key, [])
        
        print(f"\n  IMAGE: {img} ({img_size//1024} KB)")
        print(f"    Parsed: olympiad='{olympiad2}', year={year2}, grade={grade2}, num={num2}")
        print(f"    Lookup key: {key}")
        
        if matched:
            m_data = matched[0]
            entry = m_data['entry']
            print(f"    MATCHED! Olympiad title: {entry.get('olympiad_title', 'N/A')}")
            print(f"    Round: {entry.get('round', 'N/A')}, Round title: {entry.get('round_title', 'N/A')}")
            print(f"    Text: {m_data['text'][:300]}")
        else:
            print(f"    NO MATCH in JSONL")
            # Try alternative key with round variations
            entry_rounds = set()
            for e_key, e_list in entries_by_key.items():
                e_parts = e_key.split('|')
                if len(e_parts) >= 4 and e_parts[0] == olympiad2 and e_parts[1] == year2 and e_parts[2] == grade2 and e_parts[3] == num2:
                    for e_item in e_list:
                        entry_rounds.add(e_item['entry'].get('round', ''))
            if entry_rounds:
                print(f"    Found entries with same o/y/g/n but different key format: rounds={entry_rounds}")

else:
    print(f"Directory {PROBLEM_IMG_DIR} not found!")

# 3) Also list the fu images that exist
print("\n\n" + "="*80)
print("FU (Физтех) IMAGES - checking if any JSONL entries reference them")
fu_dir = 'static/temp_unpack/images_package/static/images/problems'
if os.path.isdir(fu_dir):
    fu_images = sorted([f for f in os.listdir(fu_dir) if f.startswith('fu_') and f.endswith('.png')])
    print(f"Found {len(fu_images)} fu images on disk")
    
    # Parse fu_2024_g5_fig1.png -> fu, 2024, g5, fig1
    fu_pattern = re.compile(r'fu_(\d{4})_g(\d+)_fig(\d+)\.png')
    for img in fu_images[:5]:
        m = fu_pattern.match(img)
        if m:
            year = m.group(1)
            grade = m.group(2)
            fig = m.group(3)
            key = f"fu|{year}|{grade}|{fig}"
            # Check all keys
            matches = [k for k in entries_by_key.keys() if k.startswith(f"fu|{year}|{grade}|")]
            print(f"  {img}: look for 'fu' olympiad in JSONL -> matches: {len(matches)} (keys: {matches[:5]})")
    
    # Also check if fu images are referenced in any problem text/solution
    print("\nSearching JSONL text for 'fu_' references...")
    count = 0
    with open(JSONL_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            if 'fu_' in line.lower():
                count += 1
    print(f"  JSONL lines containing 'fu_': {count}")
