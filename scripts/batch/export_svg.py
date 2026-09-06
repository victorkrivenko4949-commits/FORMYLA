# -*- coding: utf-8 -*-
"""Экспортировать все готовые SVG в out/svg_ready/ для публикации на сайт."""
import io, os, sys, json, sqlite3
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_OUT = os.path.join(_SCRIPT_DIR, "out")
_SVG_DIR = os.path.join(_OUT, "svg_ready")
os.makedirs(_SVG_DIR, exist_ok=True)

c = sqlite3.connect(r'instance/formyla.db')
# Все done job'ы batch-пользователя.
rows = c.execute(
    "SELECT id, svg_path, problem_text, base_plan_json FROM figure_build_jobs "
    "WHERE user_id=1301 AND status='done'"
).fetchall()

# Маппинг job -> task_id из sample_full.
sample = {}
for l in open(os.path.join(_OUT, "sample_full.jsonl"), encoding='utf-8'):
    r = json.loads(l)
    sample[r['task_id']] = r

# Сопоставить job с task_id через condition (problem_text) — используем порядок
# job id по возрастанию с sample (обе последовательности одинаковые).
# Проще: пройти по results.jsonl, где уже есть job_id + task_id.
results = {}
for l in open(os.path.join(_OUT, "results.jsonl"), encoding='utf-8'):
    r = json.loads(l)
    results[r.get('job_id')] = r

saved = 0
index = []
for jid, svg, problem, plan in rows:
    r = results.get(jid, {})
    tid = r.get('task_id', f"job_{jid}")
    grade = r.get('grade', '')
    if svg and svg.lstrip().startswith('<?xml'):
        content = svg
    elif svg:
        try:
            with open(svg, encoding='utf-8') as f:
                content = f.read()
        except OSError:
            content = None
    else:
        content = None
    if content:
        fname = f"{tid}_{grade}.svg"
        with open(os.path.join(_SVG_DIR, fname), 'w', encoding='utf-8') as f:
            f.write(content)
        saved += 1
        index.append({"file": fname, "task_id": tid, "grade": grade})

# индекс
with open(os.path.join(_SVG_DIR, "index.json"), 'w', encoding='utf-8') as f:
    json.dump({"total": saved, "files": index}, f, ensure_ascii=False, indent=1)

print(f"Экспортировано SVG: {saved} -> {_SVG_DIR}")
