# -*- coding: utf-8 -*-
"""Запуск: обновление curator_state + заполнение gen_conveyor + конвейер."""
import sys, os, time, threading

os.chdir(r'c:\Users\Redmi\Desktop\Новая папка (2)')
sys.path.insert(0, '.')

# ── Сервер ──
def run_server():
    from app import app
    app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)
threading.Thread(target=run_server, daemon=True).start()
time.sleep(5)

from app import app, db
from models_curator import CuratorState
from models import User
import json

NOW = '2026-08-07T00:00:00'
THEMES = {
    5: ['G5_T01','G5_T02','G5_T03','G5_T04','G5_T05','G5_T06','G5_T07'],
    6: ['G6_T01','G6_T02','G6_T03','G6_T04','G6_T05','G6_T06','G6_T07'],
    7: ['G7_T01','G7_T02','G7_T03','G7_T04','G7_T05','G7_T06','G7_T07'],
    8: ['G8_T01','G8_T02','G8_T03','G8_T04','G8_T05','G8_T06','G8_T07'],
    9: ['G9_T05','G9_T16','G9_T10','G9_T13','G9_T01','G9_T06','G9_T11'],
    10: ['G10_T01','G10_T02','G10_T03','G10_T04','G10_T05','G10_T06','G10_T07'],
    11: ['G11_T01','G11_T02','G11_T03','G11_T04','G11_T05','G11_T06','G11_T07'],
}

with app.app_context():
    # ── Шаг 1: чистим ──
    from daily_tasks.models import GenConveyor
    db.session.query(GenConveyor).delete()
    db.session.commit()
    print("[1] GenConveyor wiped")

    # ── Шаг 2: обновляем prep_state ──
    states = CuratorState.query.all()
    updated = 0
    for cs in states:
        ps = cs.prep_state if isinstance(cs.prep_state, dict) else {}
        mc = ps.get('monthly_cycle') if isinstance(ps, dict) else {}
        if isinstance(mc, dict) and mc.get('themes'):
            continue  # уже есть

        user = db.session.get(User, cs.user_id)
        grade = (user.preferred_grade if user else None) or 9
        themes = THEMES.get(grade, THEMES[9])

        ps = dict(ps) if isinstance(ps, dict) else {}
        ps['monthly_cycle'] = {
            'started_at': NOW, 'themes': themes,
            'day_index': 1, 'done_themes': [], 'finished_at': None,
        }
        cs.prep_state = ps
        updated += 1
        if updated % 100 == 0:
            db.session.commit()
    db.session.commit()
    print(f"[2] Updated {updated} curator_states with monthly_cycle")

    # ── Шаг 3: schedule_all_users ──
    from daily_tasks.services import schedule_all_users, conveyor_worker
    from daily_tasks.models import GenConveyor

    t0 = time.time()
    r = schedule_all_users()
    dt = time.time() - t0
    print(f"[3] schedule_all_users: scanned={r['users_scanned']} created={r['entries_created']} skipped={r['entries_skipped']} ({dt:.1f}s)")

    total = GenConveyor.query.count()
    pending = GenConveyor.query.filter_by(status='pending').count()
    unique = db.session.query(GenConveyor.cache_key).distinct().count()
    print(f"[4] GenConveyor: {total} entries, {pending} pending, {unique} unique cache_keys")
    print(f"    Estimated AI calls: {unique}")
    print(f"    Est. total time: {unique * 5 / 3:.0f} sec ({unique * 5 / 3 / 60:.1f} min) at 3 concurrent")

    # ── Шаг 4: запуск конвейера ──
    launched = conveyor_worker()
    print(f"[5] conveyor_worker launched: {launched}")

    stats = db.session.query(GenConveyor.status, db.func.count()).group_by(GenConveyor.status).all()
    for s, c in stats:
        print(f"    {s}: {c}")

    print("\n[DONE] Conveyor started! Monitor at http://127.0.0.1:5000/daily_tasks")
    print("Cron jobs: conveyor_worker (every 2 min), conveyor_schedule_all (every 60 min)")

# Keep alive
while True:
    time.sleep(30)
    with app.app_context():
        stats = db.session.query(GenConveyor.status, db.func.count()).group_by(GenConveyor.status).all()
        d = {s: c for s, c in stats}
        r, g, p, f = d.get('ready', 0), d.get('generating', 0), d.get('pending', 0), d.get('failed', 0)
        total = r + g + p + f
        pct = int((r / total * 100)) if total else 0
        bar = '█' * r + '▓' * g + '▒' * p
        print(f"[{time.strftime('%H:%M:%S')}] [{bar}] {pct}% | ready={r} gen={g} pend={p} fail={f}")
        if r + f == total and total > 0:
            print("[DONE] All entries processed!")
            # Show tasks generated
            from daily_tasks.models import TaskPool
            pools = TaskPool.query.filter_by(status='ready').all()
            total_tasks = 0
            for pool in pools:
                if pool.tasks:
                    tasks = json.loads(pool.tasks) if isinstance(pool.tasks, str) else []
                    total_tasks += len(tasks)
            print(f"Total ready pools: {len(pools)}, Total tasks: {total_tasks}")
            break
