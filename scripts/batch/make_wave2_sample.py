# -*- coding: utf-8 -*-
"""Создать sample из failed задач волны 1 (для волны 2)."""
import io, sys, os, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
_OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out')

# failed task_id из results.jsonl
failed_ids = set()
if os.path.exists(os.path.join(_OUT, 'results.jsonl')):
    for l in open(os.path.join(_OUT, 'results.jsonl'), encoding='utf-8'):
        r = json.loads(l)
        if r.get('status') in ('failed', 'timeout'):
            failed_ids.add(r['task_id'])

# исходный sample_missing
missing = [json.loads(l) for l in open(os.path.join(_OUT, 'sample_missing.jsonl'), encoding='utf-8')]
wave2 = [r for r in missing if r['task_id'] in failed_ids]

out_path = os.path.join(_OUT, 'sample_wave2.jsonl')
with open(out_path, 'w', encoding='utf-8') as f:
    for r in wave2:
        f.write(json.dumps(r, ensure_ascii=False) + '\n')
print(f"wave2: {len(wave2)} failed tasks -> {out_path}")
