# -*- coding: utf-8 -*-
"""Собрать ретрай-выборку для волны 4 file2 (failed + timeout)."""
import io, sys, os, json, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

OUT = os.path.join('scripts', 'batch', 'out')
W4 = os.path.join(OUT, 'sample_file2_wave4.jsonl')
RESULTS = os.path.join(OUT, 'results.jsonl')
RETRY = os.path.join(OUT, 'wave4_retry.jsonl')

def load(path):
    rows = []
    if not os.path.exists(path):
        return rows
    for l in open(path, encoding='utf-8'):
        l = l.strip()
        if not l:
            continue
        try:
            r = json.loads(l)
        except json.JSONDecodeError:
            continue
        if isinstance(r, dict):
            rows.append(r)
    return rows

w4 = load(W4)
results = load(RESULTS)
res_by_tid = {r['task_id']: r for r in results}

failed_tids = [r['task_id'] for r in results if r.get('status') in ('failed', 'timeout')]
failed_set = set(failed_tids)

# only wave4 tasks that failed
retry = [r for r in w4 if r.get('task_id') in failed_set]

st = collections.Counter(res_by_tid[r['task_id']]['status'] for r in retry)

with open(RETRY, 'w', encoding='utf-8') as f:
    for r in retry:
        f.write(json.dumps(r, ensure_ascii=False) + '\n')

print('wave4 total=%d' % len(w4))
print('failed+timeout in results=%d' % len(failed_tids))
print('retry sample (wave4 failed): %d -> %s' % (len(retry), RETRY))
print('retry status mix:', dict(st))
