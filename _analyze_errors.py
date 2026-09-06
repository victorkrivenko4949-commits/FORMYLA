# -*- coding: utf-8 -*-
import io, json

path = 'FORMYLA_1_4_AUDIT_ERROR.jsonl'
rows = []
with io.open(path, encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue

out = io.open('_error_analysis.txt', 'w', encoding='utf-8')
out.write('TOTAL error rows: %d\n' % len(rows))
out.write('\n')

# собрать причины ошибок
from collections import Counter
reasons = Counter()
for r in rows:
    a = r.get('audit_a', {})
    b = r.get('audit_b', {})
    err = a.get('_error') or b.get('_error') or 'unknown'
    # нормализовать
    s = str(err)
    if 'невалидный JSON' in s:
        reasons['invalid_json'] += 1
    elif '429' in s:
        reasons['http_429'] += 1
    elif 'HTTP 5' in s or 'HTTP 500' in s:
        reasons['http_5xx'] += 1
    elif 'timed out' in s.lower() or 'timeout' in s.lower():
        reasons['timeout'] += 1
    else:
        reasons['other:' + s[:60]] += 1

out.write('REASONS:\n')
for k, v in reasons.most_common(30):
    out.write('  %d\t%s\n' % (v, k))

out.write('\n')

# проверить _idx
has_idx = sum(1 for r in rows if r.get('_idx') is not None)
out.write('rows with _idx: %d / %d\n' % (has_idx, len(rows)))

out.write('\nSAMPLE (first 2):\n')
for r in rows[:2]:
    out.write(json.dumps(r, ensure_ascii=False)[:1200] + '\n---\n')

out.close()
print('done')
