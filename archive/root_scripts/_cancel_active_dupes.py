# -*- coding: utf-8 -*-
"""Отменить ВСЕ активные джобы, чья задача уже имеет готовый SVG (в любом статусе)."""
import io, sys, os, json, glob, sqlite3
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
out = io.StringIO()

DB = 'instance/formyla.db'
OUT = 'scripts/batch/out'
SVG = os.path.join(OUT, 'svg_ready')

svg = set(os.path.basename(f).replace('.svg', '') for f in glob.glob(os.path.join(SVG, '*.svg')))

# condition -> tid
cond_to_tid = {}
for src in ['sample_file2.jsonl', 'sample_full.jsonl']:
    p = os.path.join(OUT, src)
    if not os.path.exists(p):
        continue
    for l in open(p, encoding='utf-8'):
        l = l.strip()
        if not l:
            continue
        try:
            r = json.loads(l)
        except json.JSONDecodeError:
            continue
        cond = (r.get('condition') or '').strip()
        if cond:
            cond_to_tid.setdefault(cond, str(r.get('task_id')))

c = sqlite3.connect(DB, timeout=30)
c.execute('PRAGMA busy_timeout=30000')

cancelled = 0
rows = c.execute("SELECT id, problem_text, status FROM figure_build_jobs WHERE status NOT IN ('done','failed')").fetchall()
for jid, problem, status in rows:
    cond = (problem or '').strip()
    if cond.startswith('##BT:'):
        nl = cond.find('\n')
        cond = cond[nl + 1:].strip() if nl != -1 else cond
    tid = cond_to_tid.get(cond)
    if tid is None:
        continue
    has = f"{tid}" in svg or any(b == tid or b.startswith(tid + '_') for b in svg)
    if has:
        c.execute("UPDATE figure_build_jobs SET status='failed', error='CANCELLED_DUPLICATE: already has SVG', updated_at=datetime('now') WHERE id=?", (jid,))
        cancelled += 1

c.commit()
n_active = c.execute("SELECT COUNT(*) FROM figure_build_jobs WHERE status NOT IN ('done','failed')").fetchone()[0]
out.write('cancelled active duplicates=%d, remaining active=%d\n' % (cancelled, n_active))
c.close()
open('_cancel_active_dupes.txt', 'w', encoding='utf-8').write(out.getvalue())
print(out.getvalue())
