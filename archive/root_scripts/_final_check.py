import json, sys
sys.stdout.reconfigure(encoding='utf-8')
for f in ['DOUBLE_FAIL.jsonl', 'DISPUTED.jsonl']:
    rows = [json.loads(l) for l in open(f, encoding='utf-8') if l.strip()]
    print(f, '->', len(rows), 'rows')
    if rows:
        print('  keys:', sorted(rows[0].keys()))
        t = rows[0].get('task', {})
        print('  sample:', t.get('grade'), '|', t.get('topic'))
        print('  verdicts:', rows[0].get('audit_a', {}).get('overall_verdict'),
              '/', rows[0].get('audit_b', {}).get('overall_verdict'))
    print()
