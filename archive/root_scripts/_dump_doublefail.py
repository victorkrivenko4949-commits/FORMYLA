import json, sys
sys.stdout.reconfigure(encoding='utf-8')
rows = [json.loads(l) for l in open('BALANCED_DOUBLE_FAIL.jsonl', encoding='utf-8') if l.strip()]
print('total DOUBLE_FAIL rows:', len(rows))
for i, r in enumerate(rows, 1):
    t = r['task']
    print(f'=== {i}. grade={t.get("grade")} level={t.get("level")} theme={t.get("theme")} ===')
    print('STATEMENT:', (t.get('statement') or '')[:400])
    print('ANSWER:', (t.get('answer') or '')[:200])
    print('A_errors:', json.dumps(r.get('audit_a', {}).get('errors') or [], ensure_ascii=False)[:400])
    print('B_errors:', json.dumps(r.get('audit_b', {}).get('errors') or [], ensure_ascii=False)[:400])
    print()
