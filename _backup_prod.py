import psycopg2, os, sys
from datetime import datetime, timezone

url = 'postgresql://formyla_user:HwFVHpWWNFZzLvB1m6aXAKfeijKLqtGe@dpg-d7n8uo0g4nts73b1n9k0-a.ohio-postgres.render.com/formyla?sslmode=require'
ts = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
os.makedirs('_recon', exist_ok=True)

print('Connecting...', flush=True)
conn = psycopg2.connect(url)
cur = conn.cursor()
cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
tables = [r[0] for r in cur.fetchall()]
print(f'TABLES: {len(tables)}', flush=True)

dump_path = f'_recon/prod_backup_{ts}.sql'
total_rows = 0
with open(dump_path, 'w', encoding='utf-8') as f:
    f.write(f'-- PROD BACKUP: {ts} UTC\n-- Database: formyla\n-- Tables: {len(tables)}\n\n')
    for tbl in tables:
        cur.execute("SELECT column_name FROM information_schema.columns "
                    "WHERE table_name=%s ORDER BY ordinal_position", (tbl,))
        cols = [r[0] for r in cur.fetchall()]
        f.write(f'-- {tbl} ({len(cols)} cols)\n')

        cur.execute(f'SELECT * FROM "{tbl}"')
        rows = cur.fetchall()
        f.write(f'-- rows: {len(rows)}\n')
        total_rows += len(rows)

        if rows:
            col_list = ', '.join(f'"{c}"' for c in cols)
            for row in rows:
                vals = []
                for v in row:
                    if v is None:
                        vals.append('NULL')
                    elif isinstance(v, (int, float)):
                        vals.append(str(v))
                    elif isinstance(v, bool):
                        vals.append('TRUE' if v else 'FALSE')
                    else:
                        s = str(v).replace('\\', '\\\\').replace("'", "''")
                        vals.append(f"'{s}'")
                f.write(f'INSERT INTO "{tbl}" ({col_list}) VALUES ({", ".join(vals)});\n')
        f.write('\n')
        print(f'  {tbl}: {len(rows)} rows', flush=True)

cur.close()
conn.close()

size = os.path.getsize(dump_path)
print(f'\nFILE: {dump_path}', flush=True)
print(f'SIZE: {size/(1024*1024):.1f} MB ({size} bytes)', flush=True)
print(f'TOTAL ROWS: {total_rows}', flush=True)
print(f'TIME: {ts} UTC', flush=True)
print('BACKUP DONE', flush=True)
