# -*- coding: utf-8 -*-
import zipfile, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

z = zipfile.ZipFile(r'C:\Users\Redmi\_bundle_v1r2.zip')
data = z.read('VICTOR_BRIDGE_WHEELHOUSE_v1_r2/extensions/roo-bridge-0.6.56.vsix')
z2 = zipfile.ZipFile(io.BytesIO(data))
src = z2.read('extension/out/registry.js').decode('utf-8', 'replace')
lines = src.splitlines()
# print whole (it's ~51KB, but let's grep key patterns first)
for i, l in enumerate(lines):
    if any(k in l for k in ('current_workspace', 'instances.json', 'workspace', 'port', 'write', 'register', 'pid_vscode', '9876')):
        print(f'{i+1}: {l[:180]}')
