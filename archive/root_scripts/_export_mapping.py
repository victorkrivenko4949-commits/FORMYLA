# -*- coding: utf-8 -*-
"""Маппинг task_id <-> имя файла чертежа (с учётом суффикса класса)."""
import io, sys, os, json, glob
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

OUT = 'scripts/batch/out'
SVG = os.path.join(OUT, 'svg_ready')

sample = [json.loads(l) for l in io.open(os.path.join(OUT, 'sample_file2.jsonl'), encoding='utf-8') if l.strip()]

# все f2 svg файлы
files = {}
for f in glob.glob(os.path.join(SVG, 'f2_*.svg')):
    base = os.path.basename(f)[:-4]      # f2_<idx>_<grade>
    files[base] = f

lines = []
lines.append('Формат имени чертежа: <task_id>_<класс>.svg')
lines.append('Пример: f2_560_5.svg = задача f2_560 (класс 5).')
lines.append('Суффикс после последнего "_" — это КЛАСС, не часть id.')
lines.append('')
lines.append('task_id\tкласс\tфайл_чертежа')
lines.append('-' * 50)

matched = 0
for r in sample:
    tid = str(r.get('task_id'))
    grade = r.get('grade')
    # ищем файл с любым суффиксом класса для этого task_id
    cand = None
    for fname in files:
        if fname.rsplit('_', 1)[0] == tid:
            cand = fname
            break
    if cand:
        lines.append('%s\t%s\t%s.svg' % (tid, grade, cand))
        matched += 1
    else:
        lines.append('%s\t%s\t(НЕТ ЧЕРТЕЖА)' % (tid, grade))

txt = '\n'.join(lines)
with io.open('file2_taskid_to_svg_mapping.tsv', 'w', encoding='utf-8') as f:
    f.write(txt)

print('всего задач: %d' % len(sample))
print('с чертежом: %d' % matched)
print('без чертежа: %d' % (len(sample) - matched))
print('файл: file2_taskid_to_svg_mapping.tsv')
