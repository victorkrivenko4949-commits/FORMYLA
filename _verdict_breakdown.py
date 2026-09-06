import json, sys
from collections import Counter
sys.stdout.reconfigure(encoding='utf-8')

for f in ['DOUBLE_FAIL.jsonl', 'DISPUTED.jsonl']:
    rows = [json.loads(l) for l in open(f, encoding='utf-8') if l.strip()]
    print('===', f, '| total', len(rows), '===')
    c = Counter()
    for r in rows:
        va = (r.get('audit_a', {}).get('overall_verdict') or 'unknown')
        vb = (r.get('audit_b', {}).get('overall_verdict') or 'unknown')
        c[(va, vb)] += 1
    for k, v in sorted(c.items(), key=lambda x: -x[1]):
        print(f'  {k[0]:10s} / {k[1]:10s} -> {v}')
    print()
