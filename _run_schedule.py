# -*- coding: utf-8 -*-
from app import app,db
with app.app_context():
    from daily_tasks.services import schedule_all_users,conveyor_worker
    import time
    t0=time.time()
    r=schedule_all_users()
    dt=time.time()-t0
    print(f'Result: scanned={r["users_scanned"]} created={r["entries_created"]} skipped={r["entries_skipped"]} time={dt:.1f}s')
    from daily_tasks.models import GenConveyor
    total=GenConveyor.query.count()
    pending=GenConveyor.query.filter_by(status='pending').count()
    print(f'GenConveyor: {total} total, {pending} pending')
    launched=conveyor_worker()
    print(f'Launched: {launched}')
    stats=db.session.query(GenConveyor.status,db.func.count()).group_by(GenConveyor.status).all()
    for s,c in stats: print(f'  {s}: {c}')
print('DONE')
