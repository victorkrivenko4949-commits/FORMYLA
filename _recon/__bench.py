"""Bench: 10 picks + cell_deficit on full DB."""
import os,sys,time,json,hashlib,sqlite3
os.chdir(r'c:\Users\Redmi\Desktop\Новая папка (2)'); sys.path.insert(0,'.')
os.environ['FLASK_DEBUG']='0'
import logging; logging.basicConfig(level=logging.CRITICAL)
for n in list(logging.root.manager.loggerDict.keys()): logging.getLogger(n).setLevel(logging.CRITICAL)

from app import app
from sqlalchemy import event

with app.app_context():
    from services.daily_task_rotation import pick_daily_set, cell_deficit_report
    dbp=app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///','')
    s=hashlib.md5(str(time.time()).encode()).hexdigest()[:8]
    e=f'l_bench_{s}@test.local'; n=f'b_{s}'
    import models; from models import db
    rc=sqlite3.connect(dbp)
    rc.execute("INSERT INTO users(email,name,nickname,preferred_grade,onboarding_completed,total_problems_solved,current_level,experience_points,mock_exams_passed,adaptive_tests_completed,highest_difficulty_solved,current_plan,generation_count_today,gens_extra_purchased,gens_unlimited,is_guest,ml_training_consent,created_at) VALUES(?,?,?,9,0,0,1,0,0,0,0,'free',0,0,0,0,0,datetime('now'))",(e,n,n))
    uid=rc.lastrowid
    p=json.dumps({'onboarding':{'grade':9,'daily_tasks':10,'route_ceiling':5,'target_level':3}})
    l=json.dumps({k:{'mu':2,'sigma':1,'n':0} for k in ['algebra','geometry','combinatorics','logic','number_theory']})
    try: rc.execute("INSERT INTO curator_state(user_id,grade,prep_state,level_mu,level_sigma,level_by_section,level_updated_at,summary) VALUES(?,9,?,2.0,1.0,?,datetime('now'),'bench_P2D2')",(uid,p,l))
    except: pass
    rc.commit(); rc.close()

    pick_daily_set(uid,force_regenerate=True)
    tt=[]; ss=[]
    for i in range(10):
        rc=sqlite3.connect(dbp)
        rc.execute("DELETE FROM daily_task_items WHERE daily_set_id IN(SELECT id FROM daily_task_sets WHERE user_id=?)",(uid,))
        rc.execute("DELETE FROM daily_task_sets WHERE user_id=?",(uid,))
        rc.execute("DELETE FROM task_assignment_history WHERE user_id=?",(uid,))
        rc.commit(); rc.close()
        c=[0]
        def cb(*a,**kw): c[0]+=1
        event.listen(db.engine,'before_cursor_execute',cb)
        t0=time.perf_counter(); r=pick_daily_set(uid,force_regenerate=True); dt=time.perf_counter()-t0
        event.remove(db.engine,'before_cursor_execute',cb)
        tt.append(dt); ss.append(c[0])
        print(f'  {i+1}: {dt:.4f}s {c[0]}q {r.get("count",0)}t')
    print(f'Avg: {sum(tt)/len(tt):.4f}s {sum(ss)/len(ss):.0f}q')
    t0=time.perf_counter(); rpt=cell_deficit_report(); dt=time.perf_counter()-t0
    print(f'cell_deficit: {dt:.4f}s {len(rpt)} cells')

    rc=sqlite3.connect(dbp)
    rc.execute("DELETE FROM daily_task_items WHERE daily_set_id IN(SELECT id FROM daily_task_sets WHERE user_id=?)",(uid,))
    rc.execute("DELETE FROM daily_task_sets WHERE user_id=?",(uid,))
    rc.execute("DELETE FROM task_assignment_history WHERE user_id=?",(uid,))
    rc.execute("DELETE FROM users WHERE id=?",(uid,))
    rc.execute("DELETE FROM curator_state WHERE user_id=?",(uid,))
    rc.commit(); rc.close()
