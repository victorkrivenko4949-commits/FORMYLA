# -*- coding: utf-8 -*-
import json
for g in [5, 6, 7, 8, 9, 10, 11]:
    fname = f'daily_tasks/data/task_bank/formyla_grade{g}.json'
    d = json.load(open(fname, 'r', encoding='utf-8'))
    probes = d.get('probes', [])
    before = {}
    for p in probes:
        lvl = p.get('level')
        before[lvl] = before.get(lvl, 0) + 1
    for p in probes:
        old = p.get('level')
        if old is not None and 4 <= old <= 8:
            p['level'] = old - 3
    after = {}
    for p in probes:
        lvl = p.get('level')
        after[lvl] = after.get(lvl, 0) + 1
    json.dump(d, open(fname, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print('grade {}: {} probes, before={} after={}'.format(g, len(probes), dict(sorted(before.items())), dict(sorted(after.items()))))
