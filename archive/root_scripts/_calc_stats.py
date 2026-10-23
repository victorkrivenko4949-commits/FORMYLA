#!/usr/bin/env python
# -*- coding: utf-8 -*-
import json

bank = json.load(open('curated_bank_L1_L5_fixed.json', 'r', encoding='utf-8'))
lines = []
lines.append(f'count: {len(bank)}')

lvls = {}
for t in bank:
    l = t.get('level')
    lvls[str(l)] = lvls.get(str(l), 0) + 1
lines.append('levels: ' + str(dict(sorted(lvls.items()))))

srcs = {}
for t in bank:
    s = t.get('source', '?')
    srcs[s] = srcs.get(s, 0) + 1
lines.append('sources: ' + str(sorted(srcs.items(), key=lambda x: -x[1])))

oids = [int(t.get('original_id', '0').replace('SEL1080-', '')) for t in bank if t.get('original_id')]
lines.append(f'orig_ids range: {min(oids)}..{max(oids)}, unique: {len(set(oids))}')

orig_1080 = set(range(1, 1081))
survived = set(oids)
lines.append(f'survived from 1..1080: {len(survived & orig_1080)}')
lines.append(f'new (fill/regenerated beyond 1080): {len(survived - orig_1080)}')

open('_bank_stats.txt', 'w', encoding='utf-8').write('\n'.join(lines))
print('DONE')
