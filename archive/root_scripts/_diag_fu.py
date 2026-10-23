import json
JSONL_PATH = r'C:\Users\Victor\Downloads\olympiad_DB_final_fixed.jsonl'
with open(JSONL_PATH, 'r', encoding='utf-8') as f:
    for line in f:
        entry = json.loads(line)
        if entry.get('olympiad') == 'formula_unity' and str(entry.get('year','')) == '2022' and str(entry.get('grade','')) == '6':
            print(json.dumps(entry, indent=2, ensure_ascii=False))
            break
