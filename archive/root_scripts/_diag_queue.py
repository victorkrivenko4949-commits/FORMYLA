# -*- coding: utf-8 -*-
import io, sys, sqlite3, datetime, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
out = io.StringIO()

c = sqlite3.connect('instance/formyla.db', timeout=30)
c.execute('PRAGMA busy_timeout=30000')

out.write('== status distribution ==\n')
out.write(str(dict(collections.Counter(r[0] for r in c.execute("SELECT status FROM figure_build_jobs")))) + '\n')

out.write('\n== active (non-final) jobs with updated_at ==\n')
now = datetime.datetime.utcnow()
rows = c.execute(
    "SELECT id, status, priority, generation_mode, updated_at FROM figure_build_jobs "
    "WHERE status NOT IN ('done','failed') ORDER BY updated_at").fetchall()
for jid, status, prio, mode, updated in rows:
    age = (now - datetime.datetime.strptime(updated, '%Y-%m-%d %H:%M:%S.%f')).total_seconds()
    out.write('  job=%d status=%-14s prio=%d mode=%-18s age=%.0fs\n' % (jid, status, prio, mode, age))

out.write('\n== queued count by priority ==\n')
out.write(str(dict(collections.Counter(r[0] for r in c.execute("SELECT priority FROM figure_build_jobs WHERE status='queued'")))) + '\n')

c.close()
open('_diag_queue.txt', 'w', encoding='utf-8').write(out.getvalue())
print(out.getvalue())
