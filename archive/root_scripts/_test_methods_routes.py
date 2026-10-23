# -*- coding: utf-8 -*-
"""Быстрый тест маршрута каталога методов через Flask test client."""
import io

try:
    import app as app_module
except Exception as e:
    print('IMPORT_FAIL:', e)
    raise

client = app_module.app.test_client()

out = io.open('_methods_test.txt', 'w', encoding='utf-8')
for path in ['/olympiads/methods']:
    r = client.get(path)
    out.write('%s -> HTTP %s, content-type=%s, len=%d\n' % (
        path, r.status_code, r.content_type, len(r.data)))
out.close()
print('test done')
