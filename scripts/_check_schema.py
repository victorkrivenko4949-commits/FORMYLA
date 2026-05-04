import sqlite3
c = sqlite3.connect('instance/formyla.db')
cols = [r[1] for r in c.execute('PRAGMA table_info(daily_problems)').fetchall()]
print('daily_problems:', cols)
ить? Напи