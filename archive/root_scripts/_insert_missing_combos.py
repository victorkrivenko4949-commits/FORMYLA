import sqlite3, json
from datetime import datetime
conn = sqlite3.connect('instance/formyla.db')
c = conn.cursor()
catalog = json.load(open('data/olympiads/methods_catalog_89.json', 'r', encoding='utf-8'))
nm = {m['method_code']: m.get('method_name', '') for m in catalog}
sm = {m['method_code']: m.get('sort_order', 0) for m in catalog}
missing = [
    ('D11', 10, 'региональный', 'D'),
    ('E1', 10, 'региональный', 'E'),
    ('E14b', 10, 'региональный', 'E'),
    ('F4', 10, 'региональный', 'F'),
    ('F4b', 10, 'региональный', 'F'),
    ('F6', 10, 'региональный', 'F'),
    ('G6', 10, 'региональный', 'G'),
    ('C7', 11, 'заключительный', 'C'),
    ('C8', 11, 'заключительный', 'C'),
    ('E1', 11, 'заключительный', 'E'),
]
ins = 0
sk = 0
now = datetime.now().isoformat()
for mc, gr, st, se in missing:
    row = c.execute('SELECT COUNT(*) FROM vsosh_course_entries WHERE method_code=? AND grade=?', (mc, gr)).fetchone()
    if row[0] > 0:
        print('SKIP:', mc, 'grade', gr)
        sk += 1
        continue
    c.execute('INSERT INTO vsosh_course_entries (method_code,grade,stage,section,method_name,confidence_level,sort_order,created_at) VALUES (?,?,?,?,?,1,?,?)', (mc, gr, st, se, nm.get(mc, ''), sm.get(mc, 0), now))
    print('INSERTED:', mc, 'grade', gr)
    ins += 1
conn.commit()
print('Done. Inserted:', ins, 'Skipped:', sk, 'Total:', ins+sk)
conn.close()
