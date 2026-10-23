import json, sys, collections
sys.stdout.reconfigure(encoding='utf-8')

p1 = r'c:/Users/Redmi/Downloads/all_formyla_1_4_final_CORRECTED_v2.jsonl'
rows1 = [json.loads(l) for l in open(p1, encoding='utf-8') if l.strip()]
print('=== all_formyla_1_4_final_CORRECTED_v2.jsonl ===')
print('rows:', len(rows1))
print('keys:', sorted(rows1[0].keys()))
print('уникальных topic:', len(set(r['topic'] for r in rows1)))
print('level:', dict(sorted(collections.Counter(str(r['level']) for r in rows1).items())))
print()

p2 = 'FORMYLA_SREZ.jsonl'
rows2 = [json.loads(l) for l in open(p2, encoding='utf-8') if l.strip()]
print('=== FORMYLA_SREZ.jsonl (банк среза) ===')
print('rows:', len(rows2))
print('keys:', sorted(rows2[0].keys()))
print('уникальных theme_id:', len(set(r['theme_id'] for r in rows2)))
print('level:', dict(sorted(collections.Counter(str(r['level']) for r in rows2).items())))
