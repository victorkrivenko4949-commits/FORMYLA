import json, sys, os
from collections import Counter
sys.stdout.reconfigure(encoding='utf-8')

SRC = r'c:/Users/Redmi/Downloads/FORMYLA_4LEVEL_BALANCED_FIXED.jsonl'
DST = r'c:/Users/Redmi/Desktop/Новая папка (2)/FORMYLA_SREZ.jsonl'

out = []
skipped = 0
with open(SRC, 'r', encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            skipped += 1
            continue
        methods = d.get('methods') or []
        if isinstance(methods, list):
            method = ', '.join(str(m) for m in methods if m)
        elif methods:
            method = str(methods)
        else:
            method = ''
        out.append({
            'grade': d.get('grade'),
            'theme_id': (d.get('theme_id') or '').strip(),
            'theme': d.get('theme') or '',
            'level': d.get('level'),
            'text': d.get('statement') or '',
            'answer': d.get('answer') or '',
            'solution': d.get('solution') or '',
            'method': method,
        })

with open(DST, 'w', encoding='utf-8') as f:
    for row in out:
        f.write(json.dumps(row, ensure_ascii=False) + '\n')

print(f'converted {len(out)} rows -> {DST}')
print(f'skipped {skipped} malformed lines')
