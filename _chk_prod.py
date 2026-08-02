import psycopg2, sys
url = 'postgresql://formyla_user:HwFVHpWWNFZzLvB1m6aXAKfeijKLqtGe@dpg-d7n8uo0g4nts73b1n9k0-a.ohio-postgres.render.com/formyla?sslmode=require'
conn = psycopg2.connect(url)
cur = conn.cursor()

try:
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='adaptive_tasks' AND column_name='difficulty_level_src'")
    print(f'difficulty_level_src: {"YES" if cur.fetchone() else "NO"}')

    cur.execute('SELECT MIN(difficulty_level), MAX(difficulty_level) FROM adaptive_tasks')
    mn, mx = cur.fetchone()
    print(f'difficulty_level: {mn}..{mx}')

    cur.execute('SELECT COUNT(*) FROM adaptive_tasks')
    print(f'adaptive_tasks: {cur.fetchone()[0]}')

    cur.execute("SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name='task_assignment_history')")
    print(f'task_assignment_history: {"YES" if cur.fetchone()[0] else "NO"}')

    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='daily_task_items' AND column_name='debt_status'")
    print(f'debt_status: {"YES" if cur.fetchone() else "NO"}')

    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='daily_task_items' AND column_name='debt_until'")
    print(f'debt_until: {"YES" if cur.fetchone() else "NO"}')

    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='curator_state' AND column_name='prep_state'")
    print(f'curator_state.prep_state: {"YES" if cur.fetchone() else "NO"}')

    cur.execute('SELECT COUNT(*) FROM users')
    print(f'users: {cur.fetchone()[0]}')

    try:
        cur.execute('SELECT COUNT(*) FROM task_assignment_history')
        print(f'task_assignment_history rows: {cur.fetchone()[0]}')
    except Exception as e:
        print(f'task_assignment_history rows: ERROR - {e}')

finally:
    cur.close(); conn.close()
print('ALL DONE', flush=True)
