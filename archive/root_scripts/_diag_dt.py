# -*- coding: utf-8 -*-
import os, sys, io, contextlib, traceback, json

os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.abspath('instance/formyla.db').replace('\\', '/')

res = io.StringIO()

with open('logs/_diag_dt_out.txt', 'w', encoding='utf-8') as fout:
    with contextlib.redirect_stdout(fout), contextlib.redirect_stderr(fout):
        from app import app
        from models import db, User, DailyTaskBank, BankIssue, UserSubtopicAssignment

        with app.app_context():
            res.write('=== User 1302 ===\n')
            u = User.query.get(1302)
            res.write('user=%s current_month=%s preferred_grade=%s\n' % (
                u.id if u else None,
                getattr(u, 'current_month', None) if u else None,
                getattr(u, 'preferred_grade', None) if u else None,
            ))

            res.write('\n=== DailyTaskBank count ===\n')
            res.write('daily_task_bank rows=%d\n' % DailyTaskBank.query.count())

            res.write('\n=== UserSubtopicAssignment for 1302 ===\n')
            rows = UserSubtopicAssignment.query.filter_by(user_id=1302).all()
            res.write('count=%d\n' % len(rows))
            for r in rows[:15]:
                res.write('  month=%s pos=%s subtopic=%s\n' % (r.month_number, r.position, r.subtopic))

            res.write('\n=== get_active_subtopics ===\n')
            try:
                from services.curator_plan_service import get_active_subtopics
                a, st = get_active_subtopics(1302)
                res.write('status=%s\n' % json.dumps(st, ensure_ascii=False))
                res.write('assignments=%d\n' % len(a))
            except Exception:
                res.write('ERR:\n%s\n' % traceback.format_exc())

            res.write('\n=== bank_daily.build_daily_set ===\n')
            try:
                from services.bank_daily import build_daily_set
                from datetime import date
                r = build_daily_set(1302, date.today())
                res.write('keys=%s\n' % json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in r.items()}, ensure_ascii=False, default=str))
            except Exception:
                res.write('ERR:\n%s\n' % traceback.format_exc())

            res.write('\n=== get_cycle_info ===\n')
            try:
                from curator.monthly_cycle import get_cycle_info
                ci = get_cycle_info(1302)
                res.write('%s\n' % json.dumps(ci, ensure_ascii=False, default=str))
            except Exception:
                res.write('ERR:\n%s\n' % traceback.format_exc())

            res.write('\n=== pick_daily_set (rotation) ===\n')
            try:
                from services.daily_task_rotation import pick_daily_set
                p = pick_daily_set(1302)
                res.write('keys=%s\n' % json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in p.items()}, ensure_ascii=False, default=str))
            except Exception:
                res.write('ERR:\n%s\n' % traceback.format_exc())

open('_diag_dt.txt', 'w', encoding='utf-8').write(res.getvalue())
print('done')
