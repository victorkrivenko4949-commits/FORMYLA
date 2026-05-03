#!/usr/bin/env python3
"""Full audit: tasks per grade and per topic from Render PostgreSQL."""
import psycopg2

PG_URL = 'postgresql://formyla_user:HwFVHpWWNFZzLvB1m6aXAKfeijKLqtGe@dpg-d7n8uo0g4nts73b1n9k0-a.ohio-postgres.render.com/formyla?sslmode=require'

print('Connecting to Render PostgreSQL...')
conn = psycopg2.connect(PG_URL, connect_timeout=15)
cur = conn.cursor()

# Total
cur.execute('SELECT COUNT(*) FROM adaptive_tasks')
total = cur.fetchone()[0]
print(f'\nTotal tasks in DB: {total}\n')

# By grade
print('=' * 50)
print(f'{"Grade":<10} {"Count":<10} {"Status"}')
print('=' * 50)
cur.execute('SELECT class_level, COUNT(*) FROM adaptive_tasks GROUP BY class_level ORDER BY class_level')
for grade, count in cur.fetchall():
    status = 'OK' if count >= 1050 else 'LOW'
    print(f'{grade:<10} {count:<10} {status}')

# By grade and topic
print('\n' + '=' * 70)
print('TASKS BY GRADE AND TOPIC')
print('=' * 70)

cur.execute('''
    SELECT class_level, topic, COUNT(*) as cnt
    FROM adaptive_tasks
    GROUP BY class_level, topic
    ORDER BY class_level, topic
''')
rows = cur.fetchall()

current_grade = None
grade_total = 0
for grade, topic, count in rows:
    if grade != current_grade:
        if current_grade is not None:
            print(f'  {"TOTAL":<40} {grade_total}')
            print()
        current_grade = grade
        grade_total = 0
        print(f'--- Grade {grade} ---')
    grade_total += count
    print(f'  {topic:<40} {count}')

if current_grade is not None:
    print(f'  {"TOTAL":<40} {grade_total}')

# Topic summary across all grades
print('\n' + '=' * 70)
print('TOPIC TOTALS (ALL GRADES)')
print('=' * 70)
cur.execute('''
    SELECT topic, COUNT(*) as cnt
    FROM adaptive_tasks
    GROUP BY topic
    ORDER BY cnt DESC
''')
for topic, count in cur.fetchall():
    print(f'  {topic:<40} {count}')

# By difficulty
print('\n' + '=' * 70)
print('BY DIFFICULTY LEVEL')
print('=' * 70)
cur.execute('''
    SELECT difficulty_level, COUNT(*) as cnt
    FROM adaptive_tasks
    GROUP BY difficulty_level
    ORDER BY difficulty_level
''')
for diff, count in cur.fetchall():
    print(f'  Level {diff:<5} {count}')

conn.close()
print('\nDone!')
