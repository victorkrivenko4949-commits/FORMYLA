# -*- coding: utf-8 -*-
"""Копирует файлы атласа в static/methods/ без чтения их содержимого."""
import os, shutil, io

dl = r'C:\Users\Redmi\Downloads'
dst_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'methods')
os.makedirs(dst_dir, exist_ok=True)

mapping = {
    'Методы — визуальный атлас (очищенный).html': 'index.html',
    'olymp_methods_complete_visual_atlas.html': 'atlas.html',
}

report = io.open('_copy_report.txt', 'w', encoding='utf-8')
for src_name, dst_name in mapping.items():
    src = os.path.join(dl, src_name)
    dst = os.path.join(dst_dir, dst_name)
    if not os.path.exists(src):
        report.write('MISSING: %s\n' % src_name)
        continue
    shutil.copyfile(src, dst)
    report.write('%s -> %s (%d bytes)\n' % (src_name, dst_name, os.path.getsize(dst)))
report.close()
print('copy done')
