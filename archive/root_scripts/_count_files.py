import json, sys, collections, os
sys.stdout.reconfigure(encoding='utf-8')

p = r'c:/Users/Redmi/Downloads/FORMYLA_4LEVEL_BALANCED_FIXED.jsonl'
rows = [json.loads(l) for l in open(p, encoding='utf-8') if l.strip()]
print('FORMYLA_4LEVEL_BALANCED_FIXED.jsonl rows:', len(rows))
print('level dist:', dict(sorted(collections.Counter(str(r['level']) for r in rows).items())))
print('grade dist:', dict(sorted(collections.Counter(str(r['grade']) for r in rows).items())))

print()
# проверить другие похожие файлы
import glob
for pat in [r'c:/Users/Redmi/Downloads/FORMYLA_4LEVEL*.jsonl', r'c:/Users/Redmi/Downloads/FORMYLA*LEVEL*.jsonl']:
    for f in glob.glob(pat):
        n = sum(1 for _ in open(f, encoding='utf-8'))
        print(f, '->', n, 'rows')
