import json

with open('olympiad-db/public/data/FORMYLA_olympiad_DB_no_holes_with_images.jsonl', 'r', encoding='utf-8') as f:
    lines = f.readlines()

print(f'Total lines: {len(lines)}')

# Find entries with empty/missing/blank id
empty_count = 0
for i, line in enumerate(lines):
    d = json.loads(line)
    cid = d.get('id')
    if cid == '' or cid is None:
        empty_count += 1
        print(f'EMPTY id at line {i}: id={repr(cid)}, olympiad={d.get("olympiad")}, year={d.get("year")}, grade={d.get("grade")}, round={d.get("round")}')
        for p in d.get('problems', []):
            imgs = p.get('images', [])
            if imgs:
                print(f'  prob {p.get("num")}: {len(imgs)} images, first kind={imgs[0].get("kind")}')

print(f'\nTotal entries with empty id: {empty_count}')
