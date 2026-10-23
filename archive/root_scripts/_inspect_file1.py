# -*- coding: utf-8 -*-
import io, sys, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
out = io.StringIO()

for f in ['1', '5', '20', '148', '200']:
    out.write('== %r exists=%s\n' % (f, os.path.exists(f)))
    if os.path.exists(f):
        out.write('size=%d\n' % os.path.getsize(f))
        try:
            data = open(f, 'rb').read(500)
            out.write(repr(data) + '\n')
        except Exception as e:
            out.write('err %s\n' % e)
    out.write('\n')

open('_inspect_file1.txt', 'w', encoding='utf-8').write(out.getvalue())
print('done')
