# -*- coding: utf-8 -*-
import os, glob, io, sys, shutil
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Find all png files under _6figs recursively
pngs = glob.glob('_6figs/**/*.png', recursive=True)
print('found pngs:')
for p in pngs:
    print('  ', repr(p))

# Map by trailing number in filename (Задача_N.png encoded as mojibake)
import re
target_dir = '_6figs'
for p in pngs:
    base = os.path.basename(p)
    # The mojibake name ends with _N.png
    m = re.search(r'_(\d+)\.png$', base)
    if m:
        num = int(m.group(1))
        newname = os.path.join(target_dir, f'task_{num}.png')
        shutil.copyfile(p, newname)
        print('copied', repr(p), '->', newname)
