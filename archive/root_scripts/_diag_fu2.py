import json
JSONL_PATH = r'C:\Users\Victor\Downloads\olympiad_DB_final_fixed.jsonl'
max_id = 0
entries = []
with open(JSONL_PATH, 'r', encoding='utf-8') as f:
    for line in f:
        entry = json.loads(line)
        if entry.get('olympiad') == 'formula_unity':
            eid = entry.get('id','')
            if eid:
                try:
                    eid_int = int(eid)
                    if eid_int > max_id:
                        max_id = eid_int
                except:
                    pass
            entries.append(entry)
print(f'Total formula_unity entries: {len(entries)}')
print(f'Max id among formula_unity: {max_id}')
for e in entries:
    eid = e.get('id','')
    yr = e.get('year','')
    gr = e.get('grade','')
    rd = e.get('round','')
    print(f'  id={eid!r:>6} year={yr} grade={gr} round={rd}')
