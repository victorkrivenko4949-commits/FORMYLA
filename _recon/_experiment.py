"""
Experiment: lifecycle, daily tasks, date shift, incomplete anchor slice.
Uses Flask SQLAlchemy for DB writes, test_client for API.
"""
import os, sys, json, time
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

def dump_sqlalchemy(email_like):
    """Dump via SQLAlchemy ORM."""
    from models import User
    from models_curator import CuratorState
    from daily_tasks.models import DailyTaskSet, DailyTaskItem, DailyGenerationJob
    
    print(f"\n{'='*60}")
    print(f"DB DUMP: LIKE '%{email_like}%'")
    print(f"{'='*60}")
    for u in User.query.filter(User.email.like(f'%{email_like}%')).all():
        uid = u.id
        print(f"User: id={uid} email={u.email} grade={u.preferred_grade}")
        
        cs = CuratorState.query.filter_by(user_id=uid).first()
        if cs:
            print(f"  CuratorState: mu={cs.level_mu} sigma={cs.level_sigma} onboard_done={cs.onboarding_done}")
            if cs.level_by_section:
                try:
                    lbs = json.loads(cs.level_by_section) if isinstance(cs.level_by_section, str) else cs.level_by_section
                    for sec, sd in lbs.items():
                        if isinstance(sd, dict): print(f"    {sec}: mu={sd.get('mu')} sigma={sd.get('sigma')} n={sd.get('n')}")
                except: pass
            if cs.prep_state:
                try:
                    ps = json.loads(cs.prep_state) if isinstance(cs.prep_state, str) else cs.prep_state
                    o = ps.get('onboarding', {})
                    if o: print(f"    onboard: daily_tasks={o.get('daily_tasks')} prior_mu={o.get('prior_mu')} rc={o.get('route_ceiling')}")
                    mc = ps.get('monthly_cycle', {})
                    if mc: print(f"    mc: day={mc.get('day_index')} themes={mc.get('themes')}")
                except: pass
        
        sets = DailyTaskSet.query.filter_by(user_id=uid).order_by(DailyTaskSet.target_date).all()
        print(f"  DailyTaskSets ({len(sets)}):")
        for s in sets:
            a = DailyTaskItem.query.filter(DailyTaskItem.daily_set_id == s.id, DailyTaskItem.is_correct.isnot(None)).count()
            t = DailyTaskItem.query.filter_by(daily_set_id=s.id).count()
            print(f"    id={s.id} date={s.target_date} status={s.status} answered={a}/{t}")
        
        jobs = DailyGenerationJob.query.filter_by(user_id=uid).order_by(DailyGenerationJob.target_date).all()
        print(f"  Jobs ({len(jobs)}):")
        for j in jobs: print(f"    id={j.id} date={j.target_date} state={j.state} step={j.current_step} pct={j.progress_pct}")

def run():
    from app import app, db
    from models import User
    from flask_login import login_user
    from sqlalchemy import text as sqltxt
    
    with app.app_context():
        # Ensure thematic_day_sets exists
        try:
            db.session.execute(sqltxt('''CREATE TABLE IF NOT EXISTS thematic_day_sets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                target_date DATE NOT NULL,
                subject VARCHAR(100), class_level INTEGER,
                status VARCHAR(32) NOT NULL DEFAULT 'generating',
                triggered_by VARCHAR(64), current_step VARCHAR(64),
                progress_pct INTEGER NOT NULL DEFAULT 0,
                tasks_json TEXT, pipeline_log TEXT, error_message TEXT,
                total_cost_usd FLOAT NOT NULL DEFAULT 0.0,
                started_at DATETIME, finished_at DATETIME,
                generated_at DATETIME, created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, target_date)
            )'''))
            db.session.commit()
        except: db.session.rollback()
        
        # Clean old recon
        User.query.filter(User.email.like('recon_%@test.local')).delete()
        db.session.commit()
        print("Old recon_* cleaned")
        
        # Create user
        user = User(email='recon_a@test.local', name='Recon A', nickname='recon_a_test', preferred_grade=9)
        db.session.add(user)
        db.session.commit()
        uid = user.id
        print(f"Created user id={uid}")
        dump_sqlalchemy('recon_a')
    
    # --- Onboarding ---
    with app.test_client() as c:
        with app.app_context():
            u = db.session.get(User, uid)
            login_user(u)
        with c.session_transaction() as s:
            s['_user_id'] = str(uid)
            s['_fresh'] = True
        
        print("\n--- ONBOARDING ---")
        r = c.get('/api/onboarding/start')
        sd = r.get_json() or {}
        print(f"start: step={sd.get('step')}")
        
        q = sd.get('question')
        while q:
            opts = q.get('options', [])
            if not opts: break
            key = opts[0]['key']
            r = c.post('/api/onboarding/answer', json={'qid': q['id'], 'key': key})
            ad = r.get_json() or {}
            print(f"  q={q['id']} -> step={ad.get('step')}")
            if ad.get('done'): break
            q = ad.get('question')
        
        r = c.get('/api/onboarding/state')
        st = r.get_json() or {}
        anchors = st.get('anchor_tasks', [])
        print(f"State: step={st.get('step')} anchors={len(anchors)}")
        
        for i, a in enumerate(anchors):
            tid = a.get('task_id') or a.get('id')
            ca = a.get('correct_answer', '')
            ans = ca if i < 3 else 'WRONG_999_X'
            r = c.post('/api/onboarding/submit_anchor', json={'task_id': tid, 'user_answer': ans})
            ad = r.get_json() or {}
            print(f"  anchor {i+1}: id={tid} correct={ad.get('correct')}")
        
        r = c.get('/api/onboarding/finish')
        fd = r.get_json() or {}
        res = fd.get('result', {})
        print(f"Finish: done={fd.get('done')} prior_mu={res.get('prior_mu')} daily_tasks={res.get('daily_tasks')}")
    
    dump_sqlalchemy('recon_a')
    
    # --- Daily tasks ---
    from daily_tasks.services import enqueue_daily_generation, get_daily_tasks, submit_answer, today_in_user_tz
    
    today = today_in_user_tz()
    print(f"\n--- DAILY TASKS ({today}) ---")
    
    with app.app_context():
        try:
            from services.daily_task_rotation import pick_daily_set
            pick_daily_set(uid)
            print("pick_daily_set: OK")
        except Exception as e:
            print(f"pick_daily_set: {e}")
        
        r = enqueue_daily_generation(uid, triggered_by="manual")
        print(f"enqueue: status={r.get('status')} set_id={r.get('daily_set_id')}")
        
        if r.get('status') == 'generating':
            print("Waiting LLM...")
            for wi in range(90):
                time.sleep(2)
                td = get_daily_tasks(uid)
                if td.get('status') in ('ready', 'partial', 'failed'):
                    print(f"Done {(wi+1)*2}s: {td['status']}")
                    break
                if wi % 10 == 0: print(f"  {(wi+1)*2}s...")
    
    dump_sqlalchemy('recon_a')
    
    with app.app_context():
        td = get_daily_tasks(uid)
        items = td.get('items', [])
        print(f"\ntasks: status={td.get('status')} items={len(items)}")
        for it in items[:5]:
            print(f"  pos={it.get('position')} topic={it.get('topic')} level={it.get('difficulty')} calib={it.get('is_calibration')}")
        
        if items:
            print("\n--- ANSWER 3/10 ---")
            for i, it in enumerate(items[:3]):
                r = submit_answer(it['id'], it.get('correct_answer', ''), 60)
                print(f"  {i+1}: id={it['id']} correct={r.get('is_correct')}")
    
    dump_sqlalchemy('recon_a')
    
    # --- Date shift ---
    print("\n--- DATE SHIFT +2 DAYS ---")
    with app.app_context():
        from daily_tasks.models import DailyTaskSet as DTS
        ts = DTS.query.filter_by(user_id=uid, target_date=today).first()
        if ts:
            newd = today - timedelta(days=2)
            ts.target_date = newd
            try: db.session.commit()
            except: db.session.rollback()
            print(f"Shifted {ts.id}: {today} -> {newd}")
        
        td2 = get_daily_tasks(uid)
        print(f"After shift: status={td2.get('status')} items={len(td2.get('items', []))}")
    
    dump_sqlalchemy('recon_a')
    
    # --- Experiment B: incomplete slice ---
    print("\n" + "="*60)
    print("EXPERIMENT B: Incomplete anchor slice (2/5)")
    print("="*60)
    
    with app.app_context():
        user_b = User(email='recon_b@test.local', name='Recon B', nickname='recon_b_test', preferred_grade=9)
        db.session.add(user_b)
        db.session.commit()
        uid_b = user_b.id
    
    with app.test_client() as c2:
        with app.app_context():
            ub = db.session.get(User, uid_b)
            login_user(ub)
        with c2.session_transaction() as s:
            s['_user_id'] = str(uid_b)
            s['_fresh'] = True
        
        r = c2.get('/api/onboarding/start')
        sd = r.get_json() or {}
        q = sd.get('question')
        while q:
            opts = q.get('options', [])
            if not opts: break
            r = c2.post('/api/onboarding/answer', json={'qid': q['id'], 'key': opts[0]['key']})
            ad = r.get_json() or {}
            if ad.get('done'): break
            q = ad.get('question')
        
        r = c2.get('/api/onboarding/state')
        st2 = r.get_json() or {}
        anchors_b = st2.get('anchor_tasks', [])
        print(f"anchors={len(anchors_b)}")
        for i, a in enumerate(anchors_b[:2]):
            tid = a.get('task_id') or a.get('id')
            ca = a.get('correct_answer', '')
            r = c2.post('/api/onboarding/submit_anchor', json={'task_id': tid, 'user_answer': ca})
            ad = r.get_json() or {}
            print(f"  anchor {i+1}: id={tid} correct={ad.get('correct')}")
        print("LEFT incomplete (2/5)")
    
    dump_sqlalchemy('recon_b')
    
    print("\n--- RETURN ---")
    with app.test_client() as c2b:
        with app.app_context():
            ub2 = db.session.get(User, uid_b)
            login_user(ub2)
        with c2b.session_transaction() as s:
            s['_user_id'] = str(uid_b)
            s['_fresh'] = True
        
        r = c2b.get('/api/onboarding/state')
        st2b = r.get_json() or {}
        anchors_2b = st2b.get('anchor_tasks', [])
        print(f"Return: step={st2b.get('step')} anchors={len(anchors_2b)}")
        for i, a in enumerate(anchors_2b):
            tid = a.get('task_id') or a.get('id')
            ca = a.get('correct_answer', '')
            ans = ca if i < len(anchors_2b) - 1 else 'WRONG'
            r = c2b.post('/api/onboarding/submit_anchor', json={'task_id': tid, 'user_answer': ans})
            ad = r.get_json() or {}
            print(f"  anchor {i+1}: id={tid} correct={ad.get('correct')}")
        r = c2b.get('/api/onboarding/finish')
        print(f"Finish: done={r.get_json().get('done')}")
    
    dump_sqlalchemy('recon_b')
    
    # Cleanup
    print("\n--- CLEANUP ---")
    with app.app_context():
        User.query.filter(User.email.like('recon_%@test.local')).delete()
        db.session.commit()
        n = User.query.filter(User.email.like('recon_%@test.local')).count()
        print(f"Remaining recon_*: {n}")
    print("DONE")

if __name__ == '__main__':
    run()
