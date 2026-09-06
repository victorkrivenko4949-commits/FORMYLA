# -*- coding: utf-8 -*-
import zipfile, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
z = zipfile.ZipFile(r'C:\Users\Redmi\_bundle_v1r2.zip')
print(z.read('VICTOR_BRIDGE_WHEELHOUSE_v1_r2/scripts/provision_ownership_kv.py').decode('utf-8', 'replace'))
