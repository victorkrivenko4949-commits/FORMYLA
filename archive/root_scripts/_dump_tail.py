# -*- coding: utf-8 -*-
import zipfile, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

z = zipfile.ZipFile(r'C:\Users\Redmi\_bundle_v1r2.zip')
s = z.read('VICTOR_BRIDGE_WHEELHOUSE_v1_r2/scripts/install_victor_bridge.ps1').decode('utf-8', 'replace')
lines = s.splitlines()
for i in range(215, 341):
    if i < len(lines):
        print(f'{i+1}: {lines[i]}')
