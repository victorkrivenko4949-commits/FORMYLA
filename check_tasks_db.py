import sqlite3

conn = sqlite3.connect('instance/formyla.db')
cursor = conn.cursor()

# Check adaptive_tasks
cursor.execute('SELECT COUNT(*) FROM adaptive_tasks')
print(f'Total adaptive_tasks: {cursor.fetchone()[0]}')

# Sample records
cursor.execute('SELECT id, class_level, difficulty_level, topic, task_text FROM adaptive_tasks LIMIT 2')
print('\nSample adaptive_tasks:')
for row in cursor.fetchall():
    print(f'  ID {row[0]}: Class {row[1]}, Difficulty {row[2]}, Topic: {row[3][:30]}')
    print(f'  Task text (first 200 chars): {row[4][:200]}...\n')

# Check olympiad_secrets content field for LaTeX issues
cursor.execute('SELECT id, title, content FROM olympiad_secrets WHERE content LIKE "%sqrt%" OR content LIKE "%frac%" LIMIT 2')
print('\nOlympiad secrets with LaTeX:')
for row in cursor.fetchall():
    print(f'  ID {row[0]}: {row[1]}')
    # Find LaTeX examples
    content = row[2]
    if '\\sqrt' in content:
        idx = content.find('\\sqrt')
        print(f'    sqrt example: ...{content[max(0,idx-20):idx+40]}...')
    if '\\frac' in content:
        idx = content.find('\\frac')
        print(f'    frac example: ...{content[max(0,idx-20):idx+40]}...')

conn.close()
