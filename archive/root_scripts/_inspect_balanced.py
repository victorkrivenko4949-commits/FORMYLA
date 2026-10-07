import json, sys, collections
sys.stdout.reconfigure(encoding='utf-8')
p = r'c:/Users/Redmi/Downloads/FORMYLA_4LEVEL_BALANCED_FIXED.jsonl'
rows = [json.loads(l) for l in open(p, encoding='utf-8') if l.strip()]
print('total rows:', len(rows))
print('keys:', sorted(rows[0].keys()))
print()
for k in sorted(rows[0].keys()):
    vals = [str(r.get(k)) for r in rows]
    c = collections.Counter(vals)
    if len(c) <= 15:
        print(f'{k!r}: {dict(c)}')
    else:
        print(f'{k!r}: {len(c)} distinct (sample: {list(c)[:4]})')
print()
print('--- sample row ---')
print(json.dumps(rows[0], ensure_ascii=False, indent=2)[:2000])
