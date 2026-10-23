import json, sys
from collections import Counter
sys.stdout.reconfigure(encoding='utf-8')

cp = json.load(open('audit_l4_checkpoint.json', encoding='utf-8'))
print('stats:', json.dumps(cp.get('stats'), ensure_ascii=False))
print('error_remain:', cp.get('error_remain'))

for f in ['DOUBLE_FAIL.jsonl', 'DISPUTED.jsonl', 'ERROR_REMAIN.jsonl']:
    try:
        rows = [json.loads(l) for l in open(f, encoding='utf-8') if l.strip()]
    except FileNotFoundError:
        print(f, '-> MISSING')
        continue
    print(f, '->', len(rows), 'rows')
    c = Counter()
    for r in rows:
        va = r.get('audit_a', {}).get('overall_verdict') or 'unknown'
        vb = r.get('audit_b', {}).get('overall_verdict') or 'unknown'
        c[(va, vb)] += 1
    for k, v in sorted(c.items(), key=lambda x: -x[1]):
        print(f'    {k[0]:10s} / {k[1]:10s} -> {v}')
