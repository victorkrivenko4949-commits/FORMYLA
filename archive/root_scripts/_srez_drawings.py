# -*- coding: utf-8 -*-
"""Собрать готовые чертежи для задач среза (FORMYLA_SREZ.jsonl).

Сопоставление по нормализованному тексту условия (statement) с figure_build_jobs
(user 1301, status=done). Результат — zip с SVG по task_uid + отчёт.
"""
import io, sys, os, json, glob, sqlite3, re, hashlib, zipfile
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
out = io.StringIO()

DB = 'instance/formyla.db'
SREZ = 'FORMYLA_SREZ.jsonl'
DELIV = '_deliverables'
os.makedirs(DELIV, exist_ok=True)


def norm(s):
    s = re.sub(r'\s+', ' ', (s or '')).lower().strip()
    return s


srez = [json.loads(l) for l in io.open(SREZ, encoding='utf-8') if l.strip()]

# ── готовые чертежи из БД ──
c = sqlite3.connect(DB, timeout=30)
c.execute('PRAGMA busy_timeout=30000')
ready = {}
for problem, svg_path in c.execute(
    "SELECT problem_text, svg_path FROM figure_build_jobs "
    "WHERE user_id=1301 AND status='done' AND svg_path IS NOT NULL AND svg_path != ''"
):
    n = norm(problem)
    if n not in ready:
        ready[n] = svg_path
c.close()

# ── сопоставление ──
matched = 0
files = []
missing_uids = []
for r in srez:
    uid = str(r.get('task_uid'))
    n = norm(r.get('statement'))
    svg = ready.get(n)
    if not svg:
        missing_uids.append(uid)
        continue
    content = svg
    if not content.lstrip().startswith('<?xml'):
        try:
            content = io.open(svg, encoding='utf-8').read()
        except OSError:
            content = None
    if not content:
        missing_uids.append(uid)
        continue
    fname = '%s.svg' % uid
    files.append((fname, content))
    matched += 1

# ── zip ──
zip_path = os.path.join(DELIV, 'srez_drawings.zip')
with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as z:
    for fname, content in files:
        z.writestr(fname, content)

out.write('srez total: %d\n' % len(srez))
out.write('с готовым чертежом: %d\n' % matched)
out.write('без чертежа: %d\n' % len(missing_uids))
out.write('zip: %s (%d байт)\n' % (zip_path, os.path.getsize(zip_path)))
out.write('первые 20 без чертежа: %s\n' % missing_uids[:20])

open('_srez_drawings.txt', 'w', encoding='utf-8').write(out.getvalue())
print(out.getvalue())
