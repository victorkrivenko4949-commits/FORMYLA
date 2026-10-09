# -*- coding: utf-8 -*-
import io, sys, sqlite3, datetime, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
out = io.StringIO()

c = sqlite3.connect('instance/formyla.db', timeout=30)
c.execute('PRAGMA busy_timeout=30000')
now = datetime.datetime.utcnow()

out.write('статусы активных:\n')
out.write(str(dict(collections.Counter(r[0] for r in c.execute(
    "SELECT status FROM figure_build_jobs WHERE status NOT IN ('done','failed')")))) + '\n\n')

out.write('последние активные (по updated_at DESC):\n')
for jid, st, upd, prio in c.execute(
    "SELECT id, status, updated_at, priority FROM figure_build_jobs "
    "WHERE status NOT IN ('done','failed') ORDER BY updated_at DESC LIMIT 15"):
    try:
        age = (now - datetime.datetime.strptime(upd, '%Y-%m-%d %H:%M:%S.%f')).total_seconds()
    except Exception:
        age = -1
    out.write('  job=%d %-16s prio=%d age=%.0fs\n' % (jid, st, prio, age))

# сколько failed за последний час
out.write('\nfailed всего: %d\n' % c.execute("SELECT COUNT(*) FROM figure_build_jobs WHERE status='failed'").fetchone()[0])
out.write('done всего: %d\n' % c.execute("SELECT COUNT(*) FROM figure_build_jobs WHERE status='done'").fetchone()[0])

c.close()
open('_queue_now.txt', 'w', encoding='utf-8').write(out.getvalue())
print(out.getvalue())
