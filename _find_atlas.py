# -*- coding: utf-8 -*-
import os, glob, io

dl = r'C:\Users\Redmi\Downloads'
out = io.open('_atlas_paths.txt', 'w', encoding='utf-8')

for name in os.listdir(dl):
    low = name.lower()
    if name.lower().endswith('.html'):
        # ищем кандидатов: содержит "атлас" или "atlas" или "методы"
        if 'атлас' in low or 'atlas' in low or 'метод' in low:
            full = os.path.join(dl, name)
            out.write(name + '\t' + str(os.path.getsize(full)) + '\n')

out.close()
print('done')
