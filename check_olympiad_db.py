import sqlite3

conn = sqlite3.connect('instance/formyla.db')
cursor = conn.cursor()

# Check count
cursor.execute('SELECT COUNT(*) FROM olympiad_secrets')
print(f'Total records: {cursor.fetchone()[0]}')

# Sample records
cursor.execute('SELECT id, topic, title, LENGTH(content) FROM olympiad_secrets LIMIT 5')
print('\nSample records:')
for row in cursor.fetchall():
    print(f'  ID {row[0]}: {row[1]} - {row[2][:50]} (content length: {row[3]})')

# Check content sample
cursor.execute('SELECT content FROM olympiad_secrets LIMIT 1')
content = cursor.fetchone()[0]
print(f'\nSample content (first 500 chars):\n{content[:500]}')

conn.close()
