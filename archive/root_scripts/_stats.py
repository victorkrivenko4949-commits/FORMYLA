# -*- coding: utf-8 -*-
import sqlite3,json
db=sqlite3.connect('instance/formyla.db')
print('=== GenConveyor ===')
for s,c in db.execute('SELECT status,COUNT(*) FROM gen_conveyor GROUP BY status').fetchall():
    print(f'  {s}: {c}')
print()
print('=== TaskPool ===')
for s,c in db.execute('SELECT status,COUNT(*) FROM task_pool GROUP BY status').fetchall():
    print(f'  {s}: {c}')
print()
total_tasks=0
pools_with_tasks=0
for pid,ptasks in db.execute("SELECT id,tasks FROM task_pool WHERE status='ready' AND tasks IS NOT NULL").fetchall():
    try:
        td=json.loads(ptasks) if isinstance(ptasks,str) else ptasks
        if isinstance(td,list) and len(td)>0:
            valid=sum(1 for t in td if not t.get('is_flagged',False))
            total_tasks+=len(td)
            pools_with_tasks+=1
    except: pass
print(f'Ready pools with tasks: {pools_with_tasks}')
print(f'Total tasks in ready pools: {total_tasks}')
print()
print('=== Recent TaskPool entries ===')
for pid,status,ckey in db.execute('SELECT id,status,cache_key FROM task_pool ORDER BY id DESC LIMIT 10').fetchall():
    tasks='?'
    pt=db.execute('SELECT tasks FROM task_pool WHERE id=?',(pid,)).fetchone()
    if pt and pt[0]:
        try:
            td=json.loads(pt[0]) if isinstance(pt[0],str) else pt[0]
            if isinstance(td,list): tasks=len(td)
        except: pass
    print(f'  #{pid} {status:10s} key={ckey[:12]}... tasks={tasks}')
print()
print('=== Sample tasks from latest ready pool ===')
pt=db.execute("SELECT tasks FROM task_pool WHERE status='ready' AND tasks IS NOT NULL ORDER BY id DESC LIMIT 1").fetchone()
if pt and pt[0]:
    td=json.loads(pt[0]) if isinstance(pt[0],str) else pt[0]
    if isinstance(td,list):
        for i,t in enumerate(td[:3]):
            txt=(t.get('task_text','') or '')[:100]
            ans=t.get('correct_answer','?')
            print(f'  [{i+1}] {txt}... => {ans}')
db.close()
