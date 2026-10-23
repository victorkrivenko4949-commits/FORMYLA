# -*- coding: utf-8 -*-
import io, sys, sqlite3, datetime, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
out = io.StringIO()

DB = 'instance/formyla.db'
c = sqlite3.connect(DB, timeout=30)
c.execute('PRAGMA busy_timeout=30000')

now = datetime.datetime.utcnow()

out.write('== активные по статусу ==\n')
out.write(str(dict(collections.Counter(r[0] for r in c.execute(
    "SELECT status FROM figure_build_jobs WHERE status NOT IN ('done','failed')")))) + '\n')

out.write('\n== зависшие base_thinking (по возрастанию updated_at) ==\n')
rows = c.execute(
    "SELECT id, status, priority, generation_mode, updated_at FROM figure_build_jobs "
    "WHERE status NOT IN ('done','failed','queued') ORDER BY updated_at LIMIT 30").fetchall()
for jid, status, prio, mode, updated in rows:
    try:
        age = (now - datetime.datetime.strptime(updated, '%Y-%m-%d %H:%M:%S.%f')).total_seconds()
    except Exception:
        age = -1
    out.write('  job=%d status=%-14s prio=%d age=%.0fs\n' % (jid, status, prio, age))

c.close()
open('_queue_stuck.txt', 'w', encoding='utf-8').write(out.getvalue())
print(out.getvalue())
