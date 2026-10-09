# -*- coding: utf-8 -*-
import sqlite3
db = sqlite3.connect('instance/formyla.db')
db.execute("UPDATE daily_task_sets SET status='failed' WHERE status='generating'")
db.execute("UPDATE daily_generation_jobs SET state='failed',error_message='stale',finished_at=datetime('now') WHERE state='running'")
db.commit()
db.close()
print("DB cleaned")
