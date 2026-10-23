# -*- coding: utf-8 -*-
import io, sys, sqlite3, datetime, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
out = io.StringIO()

c = sqlite3.connect('instance/formyla.db', timeout=30)
c.execute('PRAGMA busy_timeout=30000')
now = datetime.datetime.utcnow()

# распределение активных задач по user_id
out.write('активные задачи по user_id:\n')
out.write(str(dict(collections.Counter(r[0] for r in c.execute(
    "SELECT user_id FROM figure_build_jobs WHERE status NOT IN ('done','failed')")))) + '\n\n')

# распределение по (user_id, priority)
out.write('активные по (user_id, priority):\n')
for r in c.execute(
    "SELECT user_id, priority, COUNT(*) FROM figure_build_jobs "
    "WHERE status NOT IN ('done','failed') GROUP BY user_id, priority ORDER BY user_id, priority"):
    out.write('  %s\n' % str(r))

# задача 5422
out.write('\nзадача 5422:\n')
r = c.execute("SELECT id, user_id, status, priority, generation_mode, created_at FROM figure_build_jobs WHERE id=5422").fetchone()
out.write(str(r) + '\n')

# сколько batch (user 1301) активных
out.write('\nbatch (1301) активных: %d\n' % c.execute(
    "SELECT COUNT(*) FROM figure_build_jobs WHERE user_id=1301 AND status NOT IN ('done','failed')").fetchone()[0])

c.close()
open('_queue_who.txt', 'w', encoding='utf-8').write(out.getvalue())
print(out.getvalue())
