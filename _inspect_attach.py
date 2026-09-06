# -*- coding: utf-8 -*-
import io, sys, json, glob, os, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
out = io.StringIO()

# 1) срез — есть ли figure-поля
rows = [json.loads(l) for l in open('FORMYLA_SREZ.jsonl', encoding='utf-8')]
out.write(f"SREZ rows={len(rows)}, keys={list(rows[0].keys())}\n")
fig_keys = set()
for r in rows:
    for k in r.keys():
        if 'fig' in k.lower() or 'svg' in k.lower() or 'draw' in k.lower() or 'чертеж' in k.lower() or 'aux' in k.lower():
            fig_keys.add(k)
out.write(f"SREZ figure-related keys: {fig_keys}\n\n")

# 2) daily_task_items — поля чертежа (из models.py уже знаем: figure_json, figure_status, aux_svg_path, has_aux)
# Проверим, как routes отдаёт figure пользователю (в templates)
for root, dirs, files in os.walk('.'):
    if '.git' in root:
        continue
    for f in files:
        if not (f.endswith('.py') or f.endswith('.html')):
            continue
        p = os.path.join(root, f)
        try:
            t = open(p, encoding='utf-8', errors='replace').read()
        except Exception:
            continue
        for i, l in enumerate(t.splitlines()):
            if ('figure_json' in l or 'figure_status' in l or 'aux_svg' in l) and ('daily' in p.lower() or 'figure' in l.lower()):
                out.write(f"{p}:{i+1}: {l.strip()[:130]}\n")

open('_inspect_attach.txt', 'w', encoding='utf-8').write(out.getvalue())
print('done')
