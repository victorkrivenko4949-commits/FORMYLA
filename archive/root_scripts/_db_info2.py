import sqlite3, json
conn = sqlite3.connect(r'c:\Users\Redmi\Desktop\Новая папка (2)\instance\formyla.db')
cur = conn.cursor()

# class_level distribution
cur.execute('SELECT class_level, COUNT(*) FROM adaptive_tasks GROUP BY class_level ORDER BY class_level')
print('=== Class level distribution ===')
for r in cur.fetchall(): print(f'  Grade {r[0]}: {r[1]}')

# Unique topics
cur.execute('SELECT topic, COUNT(*) as c FROM adaptive_tasks GROUP BY topic ORDER BY c DESC LIMIT 20')
print('\n=== Topics ===')
for r in cur.fetchall(): print(f'  {r[0]}: {r[1]}')

# Full level+subject matrix
cur.execute('SELECT difficulty_level, subject, COUNT(*) FROM adaptive_tasks GROUP BY difficulty_level, subject ORDER BY difficulty_level, subject')
print('\n=== Level × Subject matrix ===')
for r in cur.fetchall(): print(f'  L{r[0]} {r[1]}: {r[2]}')

# olympiad_tasks distribution
cur.execute('SELECT difficulty_level, COUNT(*) FROM olympiad_tasks GROUP BY difficulty_level ORDER BY difficulty_level')
print('\n=== Olympiad levels ===')
for r in cur.fetchall(): print(f'  L{r[0]}: {r[1]}')

# Check columns
cur.execute('PRAGMA table_info(olympiad_tasks)')
cols = [r[1] for r in cur.fetchall()]
print('\n=== olympiad_tasks cols ===')
print(cols)

# questionnaire_state structure
cur.execute('SELECT id, email, preferred_grade, questionnaire_state FROM users')
print('\n=== Users ===')
for r in cur.fetchall(): 
    q = r[3]
    if q:
        try: q = json.loads(q)
        except: pass
    print(f'  #{r[0]} {r[1]} grade={r[2]} qs={str(q)[:200]}')

conn.close()
