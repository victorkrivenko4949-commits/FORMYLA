# -*- coding: utf-8 -*-
import sqlite3

for db in ['instance/formyla.db', 'formyla.db']:
    print('====', db)
    conn = sqlite3.connect(db)
    c = conn.cursor()
    tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    print('tables count:', len(tables))
    if 'adaptive_tasks' in tables:
        print('adaptive_tasks total:', c.execute('SELECT COUNT(*) FROM adaptive_tasks').fetchone()[0])
        print('sources:')
        for row in c.execute("SELECT source, COUNT(*) FROM adaptive_tasks GROUP BY source ORDER BY 2 DESC LIMIT 30"):
            print('   ', row)
        print('nonempty solution total:', c.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE COALESCE(solution,'') != ''").fetchone()[0])
        print('anchors source rows:', c.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE source='formyla_anchors'").fetchone()[0])
    else:
        print('NO adaptive_tasks table')
    conn.close()
