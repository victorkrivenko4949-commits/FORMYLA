import sqlite3
c = sqlite3.connect("instance/formyla.db")
for r in c.execute("PRAGMA table_info(daily_problems)").fetchall():
    print(r[1])
