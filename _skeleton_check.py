import json, sys, collections
sys.stdout.reconfigure(encoding='utf-8')
p = r'c:/Users/Redmi/Downloads/all_formyla_1_4_final_CORRECTED_v2.jsonl'
rows = [json.loads(l) for l in open(p, encoding='utf-8') if l.strip()]
print('total:', len(rows))
print('keys:', sorted(rows[0].keys()))
print()
print('level dist:', dict(sorted(collections.Counter(str(r['level']) for r in rows).items())))
print('grade dist:', dict(sorted(collections.Counter(str(r['grade']) for r in rows).items())))
print('уникальных тем (topic):', len(set(r['topic'] for r in rows)))
print()
topics = collections.Counter(r['topic'] for r in rows)
print('топ-20 тем по числу задач:')
for t, c in topics.most_common(20):
    print(f'  {c:5d}  {t}')
