#!/usr/bin/env python3
"""Full audit: tasks per grade and per topic from Render PostgreSQL."""
import psycopg2
import sys
import io

# Force UTF-8 output
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PG_URL = 'postgresql://formyla_user:HwFVHpWWNFZzLvB1m6aXAKfeijKLqtGe@dpg-d7n8uo0g4nts73b1n9k0-a.ohio-postgres.render.com/formyla?sslmode=require'

conn = psycopg2.connect(PG_URL, connect_timeout=15)
cur = conn.cursor()

# Total
cur.execute('SELECT COUNT(*) FROM adaptive_tasks')
total = cur.fetchone()[0]

# By grade
cur.execute('SELECT class_level, COUNT(*) FROM adaptive_tasks GROUP BY class_level ORDER BY class_level')
grades = cur.fetchall()

# By grade and topic
cur.execute('''
    SELECT class_level, topic, COUNT(*) as cnt
    FROM adaptive_tasks
    GROUP BY class_level, topic
    ORDER BY class_level, topic
''')
grade_topics = cur.fetchall()

conn.close()

# Write report
out = []
out.append(f'TOTAL TASKS IN DB: {total}\n')
out.append('=' * 60)
out.append(f'{"Grade":<10} {"Count":<10} {"Status"}')
out.append('=' * 60)
for grade, count in grades:
    status = 'OK' if count >= 1050 else 'LOW'
    out.append(f'{grade:<10} {count:<10} {status}')

out.append('')
out.append('=' * 80)
out.append('TASKS BY GRADE AND TOPIC')
out.append('=' * 80)

current_grade = None
grade_total = 0
for grade, topic, count in grade_topics:
    if grade != current_grade:
        if current_grade is not None:
            out.append(f'  {"--- TOTAL ---":<55} {grade_total}')
            out.append('')
        current_grade = grade
        grade_total = 0
        out.append(f'=== Grade {grade} ===')
    grade_total += count
    out.append(f'  {topic:<55} {count}')

if current_grade is not None:
    out.append(f'  {"--- TOTAL ---":<55} {grade_total}')

report = '\n'.join(out)

# Save to file
with open('data/audit/full_audit_report.txt', 'w', encoding='utf-8') as f:
    f.write(report)

# Also print
print(report)
print('\nSaved to data/audit/full_audit_report.txt')
