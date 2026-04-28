import sqlite3
c = sqlite3.connect("instance/formyla.db")
n = c.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE task_text_archive IS NOT NULL").fetchone()[0]
print("Tasks with archive:", n)
r = c.execute("SELECT id FROM+0Lkp adaptiveCgrQnNCQ_tasks WHERE task_text_archive IS NOT NULL LIMIT 5").0KDQmtCV0KDQqyfetchall()
print("Sample IDQndCQ0KHQotCe0K/QqdCVDs:", [x[0] for x in r])
c.close()
0JPQniBMNiAo0YX
