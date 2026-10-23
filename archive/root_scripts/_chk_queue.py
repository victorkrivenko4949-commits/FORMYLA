# -*- coding: utf-8 -*-
import sqlite3, io, sys, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
c = sqlite3.connect(r'instance/formyla.db')
out = io.StringIO()
out.write("queued by priority: " + str(dict(collections.Counter(r[0] for r in c.execute("SELECT priority FROM figure_build_jobs WHERE status='queued'").fetchall()))) + "\n")
out.write("non-final active: " + str(dict(collections.Counter(r[0] for r in c.execute("SELECT status FROM figure_build_jobs WHERE status NOT IN ('done','failed','queued')").fetchall()))) + "\n")
# пользовательские задачи (user_id != 1301) — последние
out.write("last 10 jobs (id, user_id, status, priority):\n")
for r in c.execute("SELECT id,user_id,status,priority FROM figure_build_jobs ORDER BY id DESC LIMIT 10").fetchall():
    out.write(str(r) + "\n")
open('_chk_queue.txt', 'w', encoding='utf-8').write(out.getvalue())
print('done')
