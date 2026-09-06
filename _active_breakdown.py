# -*- coding: utf-8 -*-
import io, sys, os, json, sqlite3, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
out = io.StringIO()

DB = 'instance/formyla.db'
c = sqlite3.connect(DB, timeout=30)
c.execute('PRAGMA busy_timeout=30000')

# status по generation_mode
out.write('active by (generation_mode, status):\n')
for r in c.execute("SELECT generation_mode, status, COUNT(*) FROM figure_build_jobs WHERE status NOT IN ('done','failed') GROUP BY generation_mode, status ORDER BY generation_mode, status"):
    out.write('  %s\n' % str(r))

# priority распределение активных
out.write('active by priority:\n')
for r in c.execute("SELECT priority, COUNT(*) FROM figure_build_jobs WHERE status NOT IN ('done','failed') GROUP BY priority"):
    out.write('  %s\n' % str(r))

# сколько уникальных problem_text активных
n_uniq = c.execute("SELECT COUNT(DISTINCT problem_text) FROM figure_build_jobs WHERE status NOT IN ('done','failed')").fetchone()[0]
n_all = c.execute("SELECT COUNT(*) FROM figure_build_jobs WHERE status NOT IN ('done','failed')").fetchone()[0]
out.write('active jobs=%d, unique problems=%d\n' % (n_all, n_uniq))

c.close()
open('_active_breakdown.txt', 'w', encoding='utf-8').write(out.getvalue())
print(out.getvalue())
