import psycopg2, sys
url = 'postgresql://formyla_user:HwFVHpWWNFZzLvB1m6aXAKfeijKLqtGe@dpg-d7n8uo0g4nts73b1n9k0-a.ohio-postgres.render.com/formyla?sslmode=require'
conn = psycopg2.connect(url)
conn.autocommit = True
cur = conn.cursor()

# Add debt_status
try:
    cur.execute("ALTER TABLE daily_task_items ADD COLUMN debt_status VARCHAR(20) DEFAULT 'active'")
    print('debt_status: ADDED', flush=True)
except Exception as e:
    if 'already exists' in str(e) or 'duplicate column' in str(e).lower():
        print('debt_status: ALREADY EXISTS', flush=True)
    else:
        print(f'debt_status ERROR: {e}', flush=True)

# Add debt_until
try:
    cur.execute("ALTER TABLE daily_task_items ADD COLUMN debt_until DATE DEFAULT NULL")
    print('debt_until: ADDED', flush=True)
except Exception as e:
    if 'already exists' in str(e) or 'duplicate column' in str(e).lower():
        print('debt_until: ALREADY EXISTS', flush=True)
    else:
        print(f'debt_until ERROR: {e}', flush=True)

cur.close(); conn.close()
print('DONE', flush=True)
