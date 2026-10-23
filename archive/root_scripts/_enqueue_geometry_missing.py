# -*- coding: utf-8 -*-
"""Добавить недостающие 23 задачи geometry 7-11 в очередь (status=queued).

Вставляем напрямую в figure_build_jobs с priority=-1, чтобы служебные
batch-задачи обрабатывались ПОСЛЕ задач живых пользователей и не держали их
в статусе «В очереди» (и не требовали второго воркера с гонкой за SQLite).

После обработки их SVG попадёт в job.svg_path; отдельный экспорт заберёт их.
"""
import io, sys, os, json, glob, sqlite3, datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
out = io.StringIO()

DB = 'instance/formyla.db'
USER_ID = 1301
MODEL = 'deepseek-v4-pro'

svg = set(os.path.basename(f).replace('.svg', '') for f in glob.glob('scripts/batch/out/svg_ready/*.svg'))
sf = [json.loads(l) for l in open('scripts/batch/out/sample_full.jsonl', encoding='utf-8') if l.strip()]

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

now = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S.%f')
inserted = 0
for r in missing:
    cond = (r.get('condition') or '').strip()
    sol = (r.get('solution') or '').strip() or None
    # Не дублируем: если такой condition уже в очереди/обработке — пропуск.
    n = c.execute('SELECT COUNT(*) FROM figure_build_jobs WHERE problem_text=? AND status IN ("queued","base_thinking","base_drawing","thinking","drawing","auditing")', (cond,)).fetchone()[0]
    if n:
        out.write('SKIP (already active): %s\n' % r.get('task_id'))
        continue
    c.execute(
        "INSERT INTO figure_build_jobs "
        "(user_id, problem_text, solution_text, generation_mode, status, model_name, priority, "
        " has_aux, credit_charged, created_at, updated_at) "
        "VALUES (?, ?, ?, 'condition_solution', 'queued', ?, -1, 0, 0, ?, ?)",
        (USER_ID, cond, sol, MODEL, now, now),
    )
    inserted += 1

c.commit()
n_queued = c.execute("SELECT COUNT(*) FROM figure_build_jobs WHERE status='queued'").fetchone()[0]
out.write('inserted=%d, total queued now=%d\n' % (inserted, n_queued))
c.close()

open('_enqueue_geometry_missing.txt', 'w', encoding='utf-8').write(out.getvalue())
print(out.getvalue())
