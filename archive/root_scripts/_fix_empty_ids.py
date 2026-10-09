"""Look up combo IDs from main JSONL for entries with empty id in images JSONL"""
import json

# Load main JSONL (has proper IDs)
main_data = {}
with open('../../Downloads/olympiad_DB_final_fixed.jsonl', 'r', encoding='utf-8') as f:
    for line in f:
        d = json.loads(line)
        cid = d.get('id')
        if cid is not None and cid != '':
            # Key by (olympiad, year, grade, round)
            key = (d.get('olympiad'), str(d.get('year', '')), str(d.get('grade', '')), d.get('round', ''))
            main_data[key] = cid

print(f"Main JSONL has {len(main_data)} entries with valid IDs")

# Load images JSONL
with open('olympiad-db/public/data/FORMYLA_olympiad_DB_no_holes_with_images.jsonl', 'r', encoding='utf-8') as f:
    img_lines = f.readlines()

missing_lookup = 0
found_lookup = 0
total_with_statement_imgs = 0

for i, line in enumerate(img_lines):
    d = json.loads(line)
    cid = d.get('id')
    if cid == '' or cid is None:
        key = (d.get('olympiad'), str(d.get('year', '')), str(d.get('grade', '')), d.get('round', ''))
        # Check if this combo has statement images
        has_statement = False
        for p in d.get('problems', []):
            for img in p.get('images', []):
                if img.get('kind') in ('statement', 'statement_page_crop'):
                    has_statement = True
                    break
            if has_statement:
                break
        
        if key in main_data:
            found_lookup += 1
            actual_id = main_data[key]
            if has_statement:
                total_with_statement_imgs += 1
                # Find which problems have statement images
                prob_nums = []
                for p in d.get('problems', []):
                    for img in p.get('images', []):
                        if img.get('kind') in ('statement', 'statement_page_crop'):
                            prob_nums.append(p.get('num'))
                            break
                if i < 60:  # Show first few
                    print(f"Line {i}: olympiad={d.get('olympiad')} year={d.get('year')} grade={d.get('grade')} round={d.get('round')} -> id={actual_id} problems_with_statement={prob_nums}")
        else:
            missing_lookup += 1
            if has_statement:
                print(f"MISSING from main: line {i}: olympiad={d.get('olympiad')} year={d.get('year')} grade={d.get('grade')} round={d.get('round')}")

print(f"\nFound in main JSONL: {found_lookup}")
print(f"Missing from main JSONL: {missing_lookup}")
print(f"Entries with statement images that need fixing: {total_with_statement_imgs}")
