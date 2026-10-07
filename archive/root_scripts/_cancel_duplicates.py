# -*- coding: utf-8 -*-
"""Отменить избыточные queued-джобы: задача уже имеет готовый SVG.

Помечает такие джобы failed с пометкой CANCELLED_DUPLICATE, чтобы воркер
не тратил на них API-кредиты повторно.
"""
import io, sys, os, json, glob, sqlite3
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
out = io.StringIO()

DB = 'instance/formyla.db'
OUT = 'scripts/batch/out'
SVG = os.path.join(OUT, 'svg_ready')

# задача -> уже есть svg?
svg = set(os.path.basename(f).replace('.svg', '') for f in glob.glob(os.path.join(SVG, '*.svg')))

# condition -> task_id (file2)
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
        tid = str(r.get('task_id'))
        if cond:
            cond_to_tid.setdefault(cond, tid)

c = sqlite3.connect(DB, timeout=30)
c.execute('PRAGMA busy_timeout=30000')

cancelled = 0
kept = 0
# все queued-джобы user 1301
rows = c.execute("SELECT id, problem_text FROM figure_build_jobs WHERE status='queued'").fetchall()
for jid, problem in rows:
    cond = (problem or '').strip()
    # убрать возможный префикс ##BT:...
    if cond.startswith('##BT:'):
        nl = cond.find('\n')
        cond = cond[nl + 1:].strip() if nl != -1 else cond
    tid = cond_to_tid.get(cond)
    if tid is None:
        # не нашли по условию — оставляем (может, geometry с другим форматом)
        kept += 1
        continue
    # есть ли SVG для этого task_id?
    has = f"{tid}" in svg or any(b == tid or b.startswith(tid + '_') for b in svg)
    if has:
        c.execute("UPDATE figure_build_jobs SET status='failed', error='CANCELLED_DUPLICATE: already has SVG', updated_at=datetime('now') WHERE id=?", (jid,))
        cancelled += 1
    else:
        kept += 1

c.commit()
n_queued = c.execute("SELECT COUNT(*) FROM figure_build_jobs WHERE status='queued'").fetchone()[0]
out.write('cancelled duplicates=%d, kept queued=%d, total queued now=%d\n' % (cancelled, kept, n_queued))
c.close()
open('_cancel_duplicates.txt', 'w', encoding='utf-8').write(out.getvalue())
print(out.getvalue())
