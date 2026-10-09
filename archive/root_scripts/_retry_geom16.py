# -*- coding: utf-8 -*-
"""Проверить 16 недостающих geometry-задач и перезапустить неудачные."""
import io, sys, os, json, glob, sqlite3, datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
out = io.StringIO()

DB = 'instance/formyla.db'
OUT = 'scripts/batch/out'
SVG = os.path.join(OUT, 'svg_ready')

svg = set(os.path.basename(f).replace('.svg', '') for f in glob.glob(os.path.join(SVG, '*.svg')))
sf = [json.loads(l) for l in open(os.path.join(OUT, 'sample_full.jsonl'), encoding='utf-8') if l.strip()]
missing = []
for r in sf:
    tid = str(r.get('task_id'))
    if f"{tid}_{r.get('grade')}" in svg:
        continue
    if any(b == tid or b.startswith(tid + '_') for b in svg):
        continue
    missing.append(r)

c = sqlite3.connect(DB, timeout=30)
c.execute('PRAGMA busy_timeout=30000')

now = datetime.datetime.now(datetime.UTC).strftime('%Y-%m-%d %H:%M:%S.%f')
reinserted = 0
for r in missing:
    tid = str(r.get('task_id'))
    cond = (r.get('condition') or '').strip()
    sol = (r.get('solution') or '').strip() or None
    row = c.execute("SELECT id, status, error FROM figure_build_jobs WHERE problem_text=? ORDER BY id DESC LIMIT 1", (cond,)).fetchone()
    if row is None:
        st = 'NO JOB'
        err = ''
    else:
        st = row[1]
        err = (row[2] or '')[:60]
    out.write('%-55s status=%-12s %s\n' % (tid, st, err))

    # re-enqueue if failed or no job (and not already active)
    if row is None or row[1] == 'failed':
        active = c.execute(
            "SELECT COUNT(*) FROM figure_build_jobs WHERE problem_text=? AND status IN "
            "('queued','base_thinking','base_drawing','thinking','drawing','auditing',"
            "'aux_thinking','aux_drawing','coverage_check','visual_check','solving',"
            "'answer_verify','aux_compile','aux_usefulness','aux_template_match')", (cond,)).fetchone()[0]
        if active == 0:
            c.execute(
                "INSERT INTO figure_build_jobs "
                "(user_id, problem_text, solution_text, generation_mode, status, model_name, priority, "
                " has_aux, credit_charged, created_at, updated_at) "
                "VALUES (?, ?, ?, 'condition_solution', 'queued', 'deepseek-v4-pro', -1, 0, 0, ?, ?)",
                (1301, cond, sol, now, now))
            reinserted += 1
            out.write('   -> re-enqueued\n')

c.commit()
n_queued = c.execute("SELECT COUNT(*) FROM figure_build_jobs WHERE status='queued'").fetchone()[0]
out.write('\nreinserted=%d, total queued now=%d\n' % (reinserted, n_queued))
c.close()

open('_retry_geom16.txt', 'w', encoding='utf-8').write(out.getvalue())
print(out.getvalue())
