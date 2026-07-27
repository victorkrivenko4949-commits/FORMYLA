# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding='utf-8')

from app import app
from daily_tasks.models import DailyTaskSet, DailyTaskItem
import json

with app.app_context():
    ds = DailyTaskSet.query.order_by(DailyTaskSet.id.desc()).first()
    if ds:
        print("=== LATEST DAILY TASK SET ===")
        print("ID: {} Status: {} Generated: {}".format(ds.id, ds.status, ds.generated_at))
        print("Target date: {} Class: {}".format(ds.target_date, ds.class_level))
        print("Triggered by: {} Cost: ${}".format(ds.triggered_by, ds.total_cost_usd))
        print("")
        items = DailyTaskItem.query.filter_by(daily_set_id=ds.id).order_by(DailyTaskItem.position).all()
        print("ITEMS: {}".format(len(items)))
        for item in items:
            print("")
            print("=== TASK #{} (id={}) ===".format(item.position, item.id))
            print("Subject: {} Topic: {} Subtopic: {}".format(item.subject, item.topic, item.subtopic))
            print("Difficulty: {} Slot: {} Calibration: {}".format(item.difficulty_level, item.slot_kind, item.is_calibration))
            print("Status: {} Flagged: {} Flag_reason: {}".format(item.status, item.is_flagged, item.flag_reason))
            txt = (item.task_text or "")[:500]
            print("TEXT: {}".format(txt))
            ans = (item.correct_answer or "")[:200]
            print("ANS: {}".format(ans))
            sol = (item.solution or "")[:200]
            print("SOL: {}".format(sol))
    else:
        print("NO DAILY TASK SETS FOUND")
