# -*- coding: utf-8 -*-
"""Триггер перегенерации задач дня — в контексте Flask."""

import sys, os
os.chdir(r'c:\Users\Redmi\Desktop\Новая папка (2)')
sys.path.insert(0, '.')

print(">>> Importing app...", flush=True)
from app import app, db
from models import User
from daily_tasks.services import enqueue_daily_generation

print(">>> App context...", flush=True)
with app.app_context():
    user = db.session.get(User, 1)
    if user is None:
        users = User.query.limit(5).all()
        print(f"Users: {[(u.id, u.email) for u in users]}", flush=True)
        user = users[0] if users else None
    
    if user:
        print(f">>> User: id={user.id} email={user.email}", flush=True)
        print(">>> Calling enqueue_daily_generation(skip_bank=True)...", flush=True)
        result = enqueue_daily_generation(
            user_id=user.id,
            triggered_by="manual",
            skip_bank=True,
        )
        print(f">>> RESULT: {result}", flush=True)
    else:
        print(">>> NO USER FOUND", flush=True)

print(">>> DONE", flush=True)
