import sqlite3
conn = sqlite3.connect(r'instance\formyla.db')
c = conn.cursor()

# Check tables
c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
print("users table exists:", c.fetchone() is not None)

# Search for victor-related emails (case insensitive)
c.execute("SELECT id, email, nickname, created_at FROM users WHERE email LIKE '%victor%' OR email LIKE '%krvnk%'")
rows = c.fetchall()
print(f"\nSearch results for victor/krvnk: ({len(rows)} rows)")
for r in rows:
    print(f"  id={r[0]} email={r[1]} nickname={r[2]} created={r[3]}")

# Exact match (lowercase)
c.execute("SELECT id, email, nickname, created_at FROM users WHERE email = 'victorkrvnk@gmail.com'")
r = c.fetchone()
print(f"\nExact lowercase 'victorkrvnk@gmail.com': {r}")

# Uppercase match
c.execute("SELECT id, email, nickname, created_at FROM users WHERE email = 'VICTORKRVNK@GMAIL.COM'")
r = c.fetchone()
print(f"Exact uppercase 'VICTORKRVNK@GMAIL.COM': {r}")

# Case insensitive LIKE
c.execute("SELECT id, email, nickname, created_at FROM users WHERE LOWER(email) = 'victorkrvnk@gmail.com'")
r = c.fetchone()
print(f"LOWER(email) = 'victorkrvnk@gmail.com': {r}")

# Check unique index on email
c.execute("SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name='users' AND name LIKE '%email%'")
for r in c.fetchall():
    print(f"\nEmail index: {r[0]}")

# Check if email column is COLLATE NOCASE
c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'")
print(f"\nUsers table DDL: {c.fetchone()[0][:500]}")

conn.close()
