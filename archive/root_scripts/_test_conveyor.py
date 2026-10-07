# -*- coding: utf-8 -*-
"""Test: run schedule_all_users() and check gen_conveyor table."""
from app import app, db

with app.app_context():
    from daily_tasks.services import schedule_all_users, conveyor_worker
    from daily_tasks.pipeline.deepseek_client import _GLOBAL_SEMAPHORE
    from daily_tasks.models import GenConveyor
    
    print(f"GLOBAL_SEMAPHORE value: {_GLOBAL_SEMAPHORE._value}")
    
    # Schedule all users
    result = schedule_all_users()
    print(f"schedule_all_users result: {result}")
    
    # Check table
    total = GenConveyor.query.count()
    pending = GenConveyor.query.filter_by(status='pending').count()
    ready = GenConveyor.query.filter_by(status='ready').count()
    print(f"GenConveyor: {total} total, {pending} pending, {ready} ready")
    
    # Show entries
    entries = GenConveyor.query.order_by(GenConveyor.day_index).limit(14).all()
    for e in entries:
        print(f"  #{e.id} user={e.user_id} day={e.day_index} "
              f"sub={e.curator_subtopic[:30]} status={e.status} priority={e.priority}")
    
    if pending > 0:
        print(f"\nLaunching conveyor_worker...")
        launched = conveyor_worker()
        print(f"Launched: {launched}")

print("DONE")
