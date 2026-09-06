# -*- coding: utf-8 -*-
"""Копирует исправленный атлас в static/methods/index.html без чтения содержимого."""
import os, shutil, io

src = r'C:\Users\Redmi\Downloads\Metody-vizualnyi-atlas-ispravlennyi.html'
dst = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'methods', 'index.html')

report = io.open('_copy_report2.txt', 'w', encoding='utf-8')
if not os.path.exists(src):
    report.write('MISSING: %s\n' % src)
else:
    shutil.copyfile(src, dst)
    report.write('%s -> %s (%d bytes)\n' % (src, dst, os.path.getsize(dst)))
report.close()
print('copy done')
