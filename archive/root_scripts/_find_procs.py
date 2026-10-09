# -*- coding: utf-8 -*-
import io, sys, subprocess
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
out = io.StringIO()

# wmic список python процессов
try:
    r = subprocess.run(
        ['wmic', 'process', 'where', "name='python.exe'", 'get', 'ProcessId,CommandLine', '/format:csv'],
        capture_output=True, text=True, encoding='utf-8', errors='replace')
    out.write(r.stdout)
    out.write('ERR: ' + r.stderr)
except Exception as e:
    out.write('err %s\n' % e)

open('_find_procs.txt', 'w', encoding='utf-8').write(out.getvalue())
print(out.getvalue())
