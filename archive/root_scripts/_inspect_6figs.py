# -*- coding: utf-8 -*-
import zipfile, glob, io, sys, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

zips = [f for f in glob.glob(r'C:\Users\Redmi\Downloads\6*.*') if f.lower().endswith('.zip')]
for f in zips:
    print('=== ZIP:', os.path.basename(f))
    try:
        with zipfile.ZipFile(f) as z:
            for n in z.namelist():
                info = z.getinfo(n)
                print(f'  {n}  ({info.file_size} bytes)')
    except Exception as e:
        print('  ERROR:', e)
