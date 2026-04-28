# -*- coding: utf-8 -*-
import sqlite3, sys, io, os, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

conn = sqlite3.connect('instance/formyla.db')
cur = conn.cursor()

# 1. Vse unikal'nye temy v BD
print('=== ALL DISTINCT TOPICS IN DB ===')
cur.execute('SELECT DISTINCT topic FROM adaptive_tasks ORDER BY topic')
all_topics = [r[0] for r in cur.fetchall()]
for t in all_topics:
    print(f'  [{t}]')

# 2. Kolichestvo zadach po temam i klassam (5-7)
print('\n=== TOPICS BY CLASS (5-7) ===')
cur.execute('''
    SELECT topic, class_level, COUNT(*) as cnt
    FROM adaptive_tasks
    WHERE class_level IN (5,6,7)
    GROUP BY topic, class_level
    ORDER BY class_level, cnt DESC
''')
for r in cur.fetchall():
    print(f'  class={r[1]} | cnt={r[2]:4d} | [{r[0]}]')

# 3. Poiskat 'movement' v adaptive_data
print('\n=== ADAPTIVE_DATA FILES ===')
for f in sorted(os.listdir('adaptive_data')):
    if f.endswith('.json'):
        try:
            with open(f'adaptive_data/{f}', encoding='utf-8') as fp:
                data = json.load(fp)
            if isinstance(data, list) and data:
                sample_topic = data[0].get('topic', 'N/A') if data else 'empty'
                print(f'  {f}: {len(data)} tasks, sample_topic=[{sample_topic}]')
        except Exception as e:
            print(f'  {f}: ERROR {e}')

# 4. Poiskat v app.py kak topic 'movement' mapitsya
print('\n=== TOPIC MAPPING IN APP ===')
with open('app.py', 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

# Naydti vse upominaniya 'movement'
lines = content.split('\n')
for i, line in enumerate(lines):
    if 'movement' in line.lower() and ('topic' in line.lower() or 'map' in line.lower() or 'dict' in line.lower()):
        print(f'  Line {i+1}: {line.strip()[:120]}')

conn.close()
print('\nDONE')
