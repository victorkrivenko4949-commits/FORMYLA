# -*- coding: utf-8 -*-
"""Мониторинг wave4-retry + 23 геометрия-задачи + экспорт готовых SVG."""
import io, sys, os, json, glob, sqlite3, datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
out = io.StringIO()

DB = 'instance/formyla.db'
OUT = 'scripts/batch/out'
SVG_DIR = os.path.join(OUT, 'svg_ready')

# ── wave4 retry progress ──
d = os.path.join(OUT, 'wave4_retry_out')
total4 = 334
res_path = os.path.join(d, 'results.jsonl')
done4 = failed4 = timeout4 = 0
if os.path.exists(res_path):
    rows = [json.loads(l) for l in open(res_path, encoding='utf-8') if l.strip()]
    done4 = sum(1 for r in rows if r.get('status') == 'done')
    failed4 = sum(1 for r in rows if r.get('status') == 'failed')
    timeout4 = sum(1 for r in rows if r.get('status') == 'timeout')
out.write('WAVE4 retry: total=%d done=%d failed=%d timeout=%d remaining=%d\n'
          % (total4, done4, failed4, timeout4, total4 - len(rows)))

# ── geometry missing tasks ──
sf = [json.loads(l) for l in open(os.path.join(OUT, 'sample_full.jsonl'), encoding='utf-8') if l.strip()]
svg = set(os.path.basename(f).replace('.svg', '') for f in glob.glob(os.path.join(SVG_DIR, '*.svg')))
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

out.write('\nGEOMETRY missing=%d\n' % len(missing))
new_done = []
for r in missing:
    cond = (r.get('condition') or '').strip()
    row = c.execute(
        "SELECT id, status, svg_path FROM figure_build_jobs WHERE problem_text=? ORDER BY id DESC LIMIT 1",
        (cond,)).fetchone()
    if row is None:
        out.write('  %-55s NO JOB\n' % r.get('task_id'))
        continue
    jid, status, svg_path = row
    out.write('  %-55s job=%d status=%s svg=%s\n'
              % (r.get('task_id'), jid, status, 'Y' if svg_path else 'N'))
    if status == 'done' and svg_path:
        new_done.append((r.get('task_id'), r.get('grade'), svg_path))

# ── export new geometry SVGs ──
saved = 0
for tid, grade, svg_path in new_done:
    content = None
    if svg_path.lstrip().startswith('<?xml'):
        content = svg_path
    elif svg_path:
        try:
            content = open(svg_path, encoding='utf-8').read()
        except OSError:
            content = None
    if content:
        fname = '%s_%s.svg' % (tid, grade)
        with open(os.path.join(SVG_DIR, fname), 'w', encoding='utf-8') as f:
            f.write(content)
        saved += 1

out.write('\ngeometry svg exported now: %d\n' % saved)

# current geometry completeness
svg2 = set(os.path.basename(f).replace('.svg', '') for f in glob.glob(os.path.join(SVG_DIR, '*.svg')))
have = 0
for r in sf:
    tid = str(r.get('task_id'))
    if f"{tid}_{r.get('grade')}" in svg2 or any(b == tid or b.startswith(tid + '_') for b in svg2):
        have += 1
out.write('geometry completeness: %d / 362\n' % have)

c.close()
open('_monitor.txt', 'w', encoding='utf-8').write(out.getvalue())
print(out.getvalue())
