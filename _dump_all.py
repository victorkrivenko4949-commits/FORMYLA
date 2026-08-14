# -*- coding: utf-8 -*-
import sqlite3,json
db=sqlite3.connect('instance/formyla.db')

pools=db.execute("SELECT id,specs,tasks FROM task_pool WHERE status='ready' AND tasks IS NOT NULL").fetchall()

task_id=0
for pid,pspecs,ptasks in pools:
    specs=json.loads(pspecs) if isinstance(pspecs,str) else (pspecs or [])
    tasks=json.loads(ptasks) if isinstance(ptasks,str) else (ptasks or [])
    print(f'=== Pool #{pid} ({len(tasks)} tasks) ===')
    for i,t in enumerate(tasks):
        task_id+=1
        spec=specs[i] if i<len(specs) else {}
        lvl=spec.get('difficulty_level','?')
        sub=spec.get('subtopic','?')
        txt=(t.get('task_text','') or '')[:150].replace('\n',' ')
        ans=t.get('correct_answer','?')
        flagged=' [FLAGGED]' if t.get('is_flagged') else ''
        print(f'  [{task_id}] L{lvl} | {sub[:25]:25s}{flagged}')
        print(f'       {txt}')
        print(f'       >> {ans}')
        print()
    print()
db.close()
print(f'Total: {task_id} tasks')
