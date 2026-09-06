# -*- coding: utf-8 -*-
"""Исправить приоритет batch-задач: поставить -1, чтобы не мешали живым юзерам."""
import io, sys, sqlite3
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
out = io.StringIO()

c = sqlite3.connect('instance/formyla.db', timeout=30)
c.execute('PRAGMA busy_timeout=30000')

# Все batch-задачи (user 1301) в queued — поставить priority -1
n = c.execute(
    "UPDATE figure_build_jobs SET priority=-1 "
    "WHERE user_id=1301 AND status='queued' AND priority != -1"
).rowcount
c.commit()

# проверить
out.write('переведено batch-задач в priority=-1: %d\n' % n)
out.write('распределение queued по (user_id, priority):\n')
for r in c.execute(
    "SELECT user_id, priority, COUNT(*) FROM figure_build_jobs WHERE status='queued' "
    "GROUP BY user_id, priority ORDER BY priority DESC"):
    out.write('  %s\n' % str(r))

c.close()
open('_fix_batch_priority.txt', 'w', encoding='utf-8').write(out.getvalue())
print(out.getvalue())
