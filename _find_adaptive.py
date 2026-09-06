# -*- coding: utf-8 -*-
import io, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
out = io.StringIO()
t = open('app.py', encoding='utf-8').read()
lines = t.splitlines()
for i, l in enumerate(lines):
    if 'adaptive' in l.lower() or 'AdaptiveTest' in l:
        out.write(f"{i+1}: {l[:110]}\n")
open('_find_adaptive.txt', 'w', encoding='utf-8').write(out.getvalue())
print('done')
