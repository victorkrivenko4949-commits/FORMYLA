# -*- coding: utf-8 -*-
import zipfile, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

z = zipfile.ZipFile(r'C:\Users\Redmi\_bundle_v1r2.zip')
data = z.read('VICTOR_BRIDGE_WHEELHOUSE_v1_r2/extensions/roo-bridge-0.6.56.vsix')
z2 = zipfile.ZipFile(io.BytesIO(data))
src = z2.read('extension/out/extension.js').decode('utf-8', 'replace')
lines = src.splitlines()
for i, l in enumerate(lines):
    if any(k in l for k in ('registerHostFresh', 'workspaceFolders', 'current_workspace', 'getWorkspace', 'startServer', 'roo_webview_ready', 'onStartupFinished', 'activate')):
        print(f'{i+1}: {l[:200]}')
