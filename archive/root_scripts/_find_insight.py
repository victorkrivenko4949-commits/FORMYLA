# -*- coding: utf-8 -*-
import io, sys, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
out = io.StringIO()
kw_list = ['insight_jobs', 'insightLlmClient', 'InsightJob', 'ScreenResult', 'DeepResult',
           'insightValidator', 'runScreen', 'runDeep', 'insight_practice', 'insights',
           'insight_notifications']
seen = set()
for root, dirs, files in os.walk('.'):
    if '.git' in root or '__pycache__' in root:
        continue
    for f in files:
        if not f.endswith('.py'):
            continue
        p = os.path.join(root, f)
        try:
            t = open(p, encoding='utf-8', errors='replace').read()
        except Exception:
            continue
        for kw in kw_list:
            if kw in t:
                seen.add((p, kw))
for p, kw in sorted(seen):
    out.write(f"{p} -> {kw}\n")
open('_find_insight.txt', 'w', encoding='utf-8').write(out.getvalue())
print('done')
