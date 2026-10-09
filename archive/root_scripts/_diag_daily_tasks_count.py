"""Diagnose: how many DailyTaskItems exist for today's sets?"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__) or '.')

from app import app
from daily_tasks.models import DailyTaskSet, DailyTaskItem
from datetime import date, datetime
import logging
logging.basicConfig(level=logging.DEBUG)

with app.app_context():
    print(f"=== DB DIAGNOSTIC: {datetime.now()} ===")
    
    # Count all DailyTaskSets
    all_sets = DailyTaskSet.query.all()
    print(f"\nTotal DailyTaskSets in DB: {len(all_sets)}")
    for s in all_sets:
        print(f"  Set ID={s.id}, user_id={s.user_id}, date={s.date}, status={s.status}")
        items = DailyTaskItem.query.filter_by(set_id=s.id).order_by(DailyTaskItem.position).all()
        print(f"    Items: {len(items)}")
        for it in items:
            txt_preview = (it.task_text or "")[:80] if it.task_text else "EMPTY!"
            print(f"      pos={it.position}, id={it.id}, text='{txt_preview}...'")
    
    # Today's sets
    today = date.today()
    print(f"\n=== Today ({today}) ===")
    today_sets = DailyTaskSet.query.filter_by(date=today).all()
    print(f"Today's sets: {len(today_sets)}")
    for s in today_sets:
        items = DailyTaskItem.query.filter_by(set_id=s.id).order_by(DailyTaskItem.position).all()
        print(f"  Set ID={s.id}, user_id={s.user_id}, status={s.status}")
        print(f"  Items count: {len(items)}")
        empty_texts = [i for i in items if not (i.task_text or "").strip()]
        print(f"  Items with empty task_text: {len(empty_texts)}")
        for it in items:
            txt_preview = (it.task_text or "")[:100] if it.task_text else "EMPTY!"
            flagged = "FLAGGED" if it.is_flagged else ""
            failed = "GEN_FAILED" if it._generation_failed else ""
            tags = " ".join(filter(None, [flagged, failed]))
            print(f"    pos={it.position}, id={it.id}, {tags} text='{txt_preview}'")

    print("\n=== DONE ===")
