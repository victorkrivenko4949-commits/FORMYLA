# -*- coding: utf-8 -*-
import io, sys, json, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
out = io.StringIO()
rows = [json.loads(l) for l in open(r'C:\Users\Redmi\Downloads\geometry_needs_figure (2).jsonl', encoding='utf-8')]
topics = collections.Counter(r.get('topic') for r in rows)
out.write(f"topics: {len(topics)}\n")
for t, n in topics.most_common(20):
    out.write(f"  {n:4d}  {t}\n")

geom_words = ['треугольн', 'окруж', 'угол', 'периметр', 'площад', 'прямоугольн',
              'квадрат', 'параллел', 'трапец', 'ромб', 'диагонал', 'биссектр',
              'медиан', 'высот', 'касатель', 'хорд', 'радиус', 'диаметр',
              'геометр', 'четырёхугольн', 'многоугольн', 'сторон', 'вершин']
def is_geom(t):
    return any(w in t.lower() for w in geom_words)
g = sum(1 for r in rows if is_geom((r.get('topic') or '') + ' ' + (r.get('task_text') or '')))
out.write(f"\ngeometric-like: {g}/{len(rows)} = {round(100*g/len(rows),1)}%\n")
open('_geom_share.txt', 'w', encoding='utf-8').write(out.getvalue())
print('done')
