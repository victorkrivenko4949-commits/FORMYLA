import psycopg2
url = 'postgresql://formyla_user:HwFVHpWWNFZzLvB1m6aXAKfeijKLqtGe@dpg-d7n8uo0g4nts73b1n9k0-a.ohio-postgres.render.com/formyla?sslmode=require'
conn = psycopg2.connect(url)
cur = conn.cursor()

print('=== ШАГ 5: ПРОВЕРКА ПРОД-БАЗЫ ===')

# 1. Число задач, min и max уровня сложности (строго 1-5)
cur.execute('SELECT COUNT(*), MIN(difficulty_level), MAX(difficulty_level) FROM adaptive_tasks')
cnt, mn, mx = cur.fetchone()
print(f'1. adaptive_tasks: {cnt} шт., уровни от {mn} до {mx}')
assert mn == 1 and mx == 5, f'СТОП: уровни {mn}..{mx}, ожидалось 1..5!'

# 2. Колонки истории выдачи
cur.execute("SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name='task_assignment_history')")
has_history = cur.fetchone()[0]
print(f'2. task_assignment_history: {"ЕСТЬ" if has_history else "НЕТ"}')

cur.execute('SELECT COUNT(*) FROM task_assignment_history')
hist_cnt = cur.fetchone()[0]
print(f'   записей: {hist_cnt}')

# 3. Колонки долга
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='daily_task_items' AND column_name='debt_status'")
print(f'3. debt_status: {"ЕСТЬ" if cur.fetchone() else "НЕТ"}')

cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='daily_task_items' AND column_name='debt_until'")
print(f'   debt_until: {"ЕСТЬ" if cur.fetchone() else "НЕТ"}')

# 4. Поля анкеты
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='curator_state' AND column_name='prep_state'")
print(f'4. curator_state.prep_state: {"ЕСТЬ" if cur.fetchone() else "НЕТ"}')

# 5. Число пользователей
cur.execute('SELECT COUNT(*) FROM users')
print(f'5. users: {cur.fetchone()[0]}')

# 6. Число записей истории (все таблицы с историей)
cur.execute('SELECT COUNT(*) FROM task_assignment_history')
print(f'6. task_assignment_history: {cur.fetchone()[0]} записей')

cur.execute('SELECT COUNT(*) FROM daily_task_items')
print(f'   daily_task_items: {cur.fetchone()[0]} записей')

cur.execute('SELECT COUNT(*) FROM task_pool')
print(f'   task_pool: {cur.fetchone()[0]} записей')

# 7. Проверка range строго 1-5
cur.execute('SELECT difficulty_level, COUNT(*) FROM adaptive_tasks GROUP BY difficulty_level ORDER BY difficulty_level')
levels = cur.fetchall()
print('7. Распределение уровней:')
for lvl, n in levels:
    print(f'   Уровень {lvl}: {n} задач')
assert all(1 <= lvl <= 5 for lvl, _ in levels), 'СТОП: обнаружены уровни вне 1..5!'

cur.close(); conn.close()
print('\n=== ПРОВЕРКА ПРОЙДЕНА ===')
