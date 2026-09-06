# -*- coding: utf-8 -*-
"""Собрать компактный файл условий для загрузки в Perplexity одним сообщением."""
import io, sys, os, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

OUT = 'scripts/batch/out'
sample = [json.loads(l) for l in io.open(os.path.join(OUT, 'sample_file2.jsonl'), encoding='utf-8') if l.strip()]

# компактный формат: номер, класс, условие. Без лишних разделителей.
parts = []
for i, r in enumerate(sample, 1):
    cond = (r.get('condition') or '').strip()
    grade = r.get('grade')
    parts.append('%d. [%s класс] %s' % (i, grade, cond))

txt = '\n\n'.join(parts)

with io.open('file2_perplexity.txt', 'w', encoding='utf-8') as f:
    f.write(txt)

print('всего задач: %d' % len(sample))
print('символов: %d' % len(txt))
print('файл: file2_perplexity.txt')
