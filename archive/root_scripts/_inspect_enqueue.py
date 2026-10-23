# -*- coding: utf-8 -*-
import io, sys, os, json, re, sqlite3
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
out = io.StringIO()

# ── constants ──
txt = open('routes/figures_generator.py', encoding='utf-8').read()
for name in ['REASONER_MODEL', 'FIGURE_BASE_MODEL', 'QUEUE_POLL_INTERVAL',
             'MAX_CONCURRENT_JOBS', 'CONDITION_SOLUTION_ENABLED', 'MAX_PROBLEM_LENGTH',
             'RATE_LIMIT_MAX']:
    for m in re.finditer(r'^' + name + r'\s*=\s*(.+)$', txt, re.M):
        out.write('%s = %s\n' % (name, m.group(1).strip()[:100]))

# ── sample existing condition_solution job (user 1301) ──
c = sqlite3.connect('instance/formyla.db', timeout=30)
cols = [r[1] for r in c.execute("PRAGMA table_info(figure_build_jobs)")]
out.write('\nfigure_build_jobs columns: %s\n' % cols)

row = c.execute(
    "SELECT * FROM figure_build_jobs WHERE user_id=1301 AND generation_mode='condition_solution' "
    "ORDER BY id DESC LIMIT 1").fetchone()
if row:
    out.write('\nsample job row:\n')
    for k, v in zip(cols, row):
        s = str(v)
        if len(s) > 80:
            s = s[:80] + '...'
        out.write('  %s = %s\n' % (k, s))

# ── missing geometry tasks ──
sf = [json.loads(l) for l in open('scripts/batch/out/sample_full.jsonl', encoding='utf-8') if l.strip()]
import glob
svg = set(os.path.basename(f).replace('.svg', '') for f in glob.glob('scripts/batch/out/svg_ready/*.svg'))
missing = []
for r in sf:
    tid = str(r.get('task_id'))
    if f"{tid}_{r.get('grade')}" in svg:
        continue
    if any(b == tid or b.startswith(tid + '_') for b in svg):
        continue
    missing.append(r)

out.write('\nmissing tasks: %d\n' % len(missing))
for r in missing:
    cond = (r.get('condition') or '').strip()
    n = c.execute('SELECT COUNT(*) FROM figure_build_jobs WHERE problem_text=?', (cond,)).fetchone()[0]
    out.write('  %-55s grade=%s cond_len=%d existing_jobs=%d\n'
              % (r.get('task_id'), r.get('grade'), len(cond), n))

c.close()
open('_inspect_enqueue.txt', 'w', encoding='utf-8').write(out.getvalue())
print(out.getvalue())
