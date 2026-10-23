import os, psycopg
c = psycopg.connect(os.environ["DATABASE_URL"])
print("ТАБЛИЦЫ:")
for r in c.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'"):
    print(" ", r[0])
print("КОЛОНКИ tasks:")
for r in c.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='tasks'"):
    print(" ", r[0], r[1])
