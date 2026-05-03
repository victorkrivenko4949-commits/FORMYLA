"""Check production database user count."""
import psycopg2

DB_URL = (
    "postgresql://formyla_user:HwFVHpWWNFZzLvB1m6aXAKfeijKLqtGe"
    "@dpg-d7n8uo0g4nts73b1n9k0-a.ohio-postgres.render.com"
    "/formyla?sslmode=require&connect_timeout=15"
)

print("Connecting to production DB...")
conn = psycopg2.connect(DB_URL)
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM users")
total = cur.fetchone()[0]

cur.execute("SELECT COUNT(*) FROM users WHERE is_guest = false")
registered = cur.fetchone()[0]

cur.execute("SELECT COUNT(*) FROM users WHERE is_guest = true")
guests = cur.fetchone()[0]

print(f"=== PRODUCTION DATABASE (Render PostgreSQL) ===")
print(f"Всего пользователей: {total}")
print(f"Зарегистрированных (не гости): {registered}")
print(f"Гостей: {guests}")

cur.execute("SELECT id, nickname, email, is_guest FROM users WHERE is_guest = false ORDER BY id")
rows = cur.fetchall()
print(f"\nЗарегистрированные пользователи:")
for r in rows:
    print(f"  ID={r[0]}, nickname={r[1]}, email={r[2]}")

conn.close()
print("\nDone.")
