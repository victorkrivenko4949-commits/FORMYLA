# -*- coding: utf-8 -*-
"""Перезапуск 12 недостающих geometry-задач со сброшенным счётчиком проходов.

DNS к LLM-провайдерам восстановлен, поэтому прошлые 4 прохода (во время сбоя)
не считаем. Вставляем свежие queued-джобы; серверный воркер их подхватит.
"""
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

inserted = 0
for r in missing:
    tid = str(r.get('task_id'))
    cond = (r.get('condition') or '').strip()
    sol = (r.get('solution') or '').strip() or None
    # активные не трогаем
    active = c.execute(
        "SELECT COUNT(*) FROM figure_build_jobs WHERE problem_text=? AND status IN "
        "('queued','base_thinking','base_drawing','thinking','drawing','auditing',"
        "'aux_thinking','aux_drawing','coverage_check','visual_check','solving',"
        "'answer_verify','aux_compile','aux_usefulness','aux_template_match')", (cond,)).fetchone()[0]
    if active:
        out.write('SKIP active: %s\n' % tid)
        continue
    # также проверим, нет ли done-джоба с svg, который просто не экспортировали
    done_svg = c.execute("SELECT svg_path FROM figure_build_jobs WHERE problem_text=? AND status='done' AND svg_path IS NOT NULL ORDER BY id DESC LIMIT 1", (cond,)).fetchone()
    if done_svg:
        content = done_svg[0]
        if not content.lstrip().startswith('<?xml'):
            try:
                content = open(content, encoding='utf-8').read()
            except OSError:
                content = None
        if content:
            with open(os.path.join(SVG, '%s_%s.svg' % (tid, r.get('grade'))), 'w', encoding='utf-8') as f:
                f.write(content)
            out.write('EXPORTED existing done: %s\n' % tid)
            continue
    # вставляем новый queued
    c.execute(
        "INSERT INTO figure_build_jobs "
        "(user_id, problem_text, solution_text, generation_mode, status, model_name, priority, "
        " has_aux, credit_charged, created_at, updated_at) "
        "VALUES (?, ?, ?, 'condition_solution', 'queued', 'deepseek-v4-pro', -1, 0, 0, ?, ?)",
        (1301, cond, sol, now, now))
    inserted += 1
    out.write('ENQUEUED: %s\n' % tid)

c.commit()
n = c.execute("SELECT COUNT(*) FROM figure_build_jobs WHERE status='queued'").fetchone()[0]
out.write('inserted=%d, total queued=%d\n' % (inserted, n))
c.close()

open('_enqueue12.txt', 'w', encoding='utf-8').write(out.getvalue())
print(out.getvalue())
