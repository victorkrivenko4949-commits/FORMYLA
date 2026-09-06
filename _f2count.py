# -*- coding: utf-8 -*-
import glob, io, sys, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
out = io.StringIO()
svg = glob.glob('scripts/batch/out/svg_ready/*.svg')
f2 = [f for f in svg if 'f2_' in os.path.basename(f)]
f1 = [f for f in svg if 'f2_' not in os.path.basename(f)]
out.write(f"Всего SVG: {len(svg)}\n")
out.write(f"Файл 1 (срез): {len(f1)}\n")
out.write(f"Файл 2 (сделано): {len(f2)}\n")
out.write(f"Файл 2 (осталось): {2187 - len(f2)}\n")
open('_f2count.txt', 'w', encoding='utf-8').write(out.getvalue())
print('done')
