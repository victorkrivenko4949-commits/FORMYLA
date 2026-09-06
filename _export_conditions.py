# -*- coding: utf-8 -*-
"""Выгрузить условия ВСЕХ задач geometry 7-11 (362) в отдельный файл."""
import io, sys, os, json, glob
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

OUT = 'scripts/batch/out'
sf = [json.loads(l) for l in io.open(os.path.join(OUT, 'sample_full.jsonl'), encoding='utf-8') if l.strip()]

# сортировка по классу, затем по task_id
sf.sort(key=lambda r: (str(r.get('grade') or ''), str(r.get('task_id'))))

lines = []
for i, r in enumerate(sf, 1):
    lines.append('=' * 70)
    lines.append('ЗАДАЧА %d' % i)
    lines.append('task_id: %s' % r.get('task_id'))
    lines.append('класс: %s | уровень: %s' % (r.get('grade'), r.get('level')))
    lines.append('--- УСЛОВИЕ ---')
    lines.append(r.get('condition') or '')
    lines.append('--- ОТВЕТ ---')
    lines.append(str(r.get('answer')) or '(нет)')
    lines.append('')

txt = '\n'.join(lines)
with io.open('geometry_362_conditions.txt', 'w', encoding='utf-8') as f:
    f.write(txt)

# также JSONL только с условиями
with io.open('geometry_362_conditions.jsonl', 'w', encoding='utf-8') as f:
    for r in sf:
        f.write(json.dumps({
            'task_id': r.get('task_id'),
            'grade': r.get('grade'),
            'level': r.get('level'),
            'condition': r.get('condition'),
            'answer': r.get('answer'),
        }, ensure_ascii=False) + '\n')

print('exported %d tasks' % len(sf))
print('TXT:   geometry_362_conditions.txt')
print('JSONL: geometry_362_conditions.jsonl')
