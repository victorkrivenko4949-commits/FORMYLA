# -*- coding: utf-8 -*-
import sqlite3, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
c = sqlite3.connect(r'instance/formyla.db')
out = io.StringIO()
out.write("jobs user_id=1300 (реальные пользователи сайта):\n")
for r in c.execute("SELECT id,status,current_stage,priority,created_at,updated_at FROM figure_build_jobs WHERE user_id=1300 ORDER BY id DESC LIMIT 15").fetchall():
    out.write(str(r) + "\n")
out.write("\nвсе user_id кроме 1301 и 1300:\n")
for r in c.execute("SELECT id,user_id,status,priority FROM figure_build_jobs WHERE user_id NOT IN (1300,1301) ORDER BY id DESC LIMIT 20").fetchall():
    out.write(str(r) + "\n")
open('_chk_user1300.txt', 'w', encoding='utf-8').write(out.getvalue())
print('done')
