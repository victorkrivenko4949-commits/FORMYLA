# -*- coding: utf-8 -*-
"""Собрать все готовые SVG в единый текстовый файл для Perplexity."""
import io, sys, os, glob
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

SVG = 'scripts/batch/out/svg_ready'
out = io.StringIO()

files = sorted(glob.glob(os.path.join(SVG, 'f2_*.svg')))
out.write('Файл содержит %d SVG-чертежей (чертёж = код SVG).\n\n' % len(files))

for f in files:
    tid = os.path.basename(f)[:-4]
    content = io.open(f, encoding='utf-8').read()
    out.write('### ЧЕРТЁЖ %s\n' % tid)
    out.write(content)
    out.write('\n\n')

txt = out.getvalue()
with io.open('file2_svg_bundle.txt', 'w', encoding='utf-8') as f:
    f.write(txt)

print('чертежей: %d' % len(files))
print('символов: %d' % len(txt))
print('файл: file2_svg_bundle.txt')
