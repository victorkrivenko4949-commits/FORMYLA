# -*- coding: utf-8 -*-
import io, os

files = [
    'FORMYLA_1_4_AUDIT_BOTH_CORRECT.jsonl',
    'FORMYLA_1_4_AUDIT_BOTH_INCORRECT.jsonl',
    'FORMYLA_1_4_AUDIT_DISPUTED.jsonl',
    'FORMYLA_1_4_AUDIT_ERROR.jsonl',
]

out = io.open('_counts.txt', 'w', encoding='utf-8')
tot = 0
for f in files:
    n = 0
    if os.path.exists(f):
        n = sum(1 for _ in io.open(f, encoding='utf-8'))
    tot += n
    out.write(f + '\t' + str(n) + '\n')
out.write('TOTAL\t' + str(tot) + '\n')
out.close()

# также прочитать чекпоинт
cp_path = 'audit_formyla_1_4_double_checkpoint.json'
if os.path.exists(cp_path):
    import json
    cp = json.load(io.open(cp_path, encoding='utf-8'))
    out2 = io.open('_cp.txt', 'w', encoding='utf-8')
    out2.write('done_idx: %d\n' % len(cp.get('done_idx', [])))
    out2.write('stats: %s\n' % json.dumps(cp.get('stats'), ensure_ascii=False))
    out2.close()
print('done')
