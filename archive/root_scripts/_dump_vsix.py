# -*- coding: utf-8 -*-
import zipfile, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

z = zipfile.ZipFile(r'C:\Users\Redmi\_bundle_v1r2.zip')
names = z.namelist()
vsix = [n for n in names if n.endswith('.vsix')]
print('VSIX entries:', vsix)

for v in vsix:
    data = z.read(v)
    print('===== ' + v + ' size=' + str(len(data)) + ' =====')
    z2 = zipfile.ZipFile(io.BytesIO(data))
    for n in z2.namelist():
        print('  ', n, z2.getinfo(n).file_size)
