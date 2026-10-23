# -*- coding: utf-8 -*-
"""
Бэкфилл чертежей:
  1. FORMYLA_BANK.jsonl  — добавить figure_svg_path по совпадению (grade, условие)
     с file2_2187_conditions.jsonl.
  2. daily_task_items в БД — проставить figure_svg_path уже созданным задачам.
"""
import io, sys, json, re, sqlite3
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


def norm(x):
    return re.sub(r'\s+', ' ', (x or '')).strip()


# ── карта file2 ──
f2 = [json.loads(l) for l in open('file2_2187_conditions.jsonl', encoding='utf-8') if l.strip()]
fidx = {(r['grade'], norm(r['condition'])): r['figure_svg_path'] for r in f2}
print('file2 map:', len(fidx))

# ── 1. FORMYLA_BANK.jsonl ──
bank = [json.loads(l) for l in open('FORMYLA_BANK.jsonl', encoding='utf-8') if l.strip()]
hit = 0
for r in bank:
    svg = fidx.get((r.get('grade'), norm(r.get('task_text'))))
    if svg:
        r['figure_svg_path'] = svg
        hit += 1
with open('FORMYLA_BANK.jsonl', 'w', encoding='utf-8') as f:
    for r in bank:
        f.write(json.dumps(r, ensure_ascii=False) + '\n')
print('FORMYLA_BANK enriched:', hit, '/', len(bank))

# ── 2. daily_task_items ──
c = sqlite3.connect('instance/formyla.db')
rows = c.execute(
    "SELECT i.id, i.task_text, s.class_level FROM daily_task_items i "
    "JOIN daily_task_sets s ON s.id = i.daily_set_id"
).fetchall()
upd = 0
for iid, txt, grade in rows:
    if not txt:
        continue
    svg = fidx.get((grade, norm(txt)))
    if svg:
        c.execute("UPDATE daily_task_items SET figure_svg_path=? WHERE id=?", (svg, iid))
        upd += 1
c.commit()
print('daily_task_items backfilled:', upd, '/', len(rows))
