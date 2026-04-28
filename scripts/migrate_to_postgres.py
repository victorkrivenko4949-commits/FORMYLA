"""
Миграция SQLite -> Render Postgres для FORMYLA.
Отправляет данные через HTTP API на Render Web Service,
который записывает их в Postgres через internal URL.
"""
import os
import sys
import sqlite3
import json
import argparse
import requests
from pathlib import Path

parser = argparse.ArgumentParser(description='Миграция SQLite -> Postgres через HTTP')
parser.add_argument('--dry-run', action='store_true',
                    help='Только показать план, без записи')
parser.add_argument('--wipe', action='store_true',
                    help='Удалить все данные из таблиц Postgres перед миграцией')
parser.add_argument('--batch-size', type=int, default=200,
                    help='Размер батча для отправки (по умолчанию 200)')
parser.add_argument('--table', type=str, default=None,
                    help='Мигрировать только указанную таблицу')
args = parser.parse_args()

# --- Конфигурация ---
RENDER_URL = 'https://formyla-com.onrender.com'
MIGRATE_SECRET = os.environ.get('MIGRATE_SECRET', 'formyla-migrate-2026')

print(f'[КОНФИГ] Render: {RENDER_URL}')
print(f'[КОНФИГ] Batch size: {args.batch_size}')

# --- SQLite ---
sqlite_path = Path('instance/formyla.db')
if not sqlite_path.exists():
    print(f'ОШИБКА: SQLite не найден: {sqlite_path}')
    sys.exit(1)

src = sqlite3.connect(str(sqlite_path))
src.row_factory = sqlite3.Row

# Получаем список таблиц SQLite
sqlite_tables = [
    r[0] for r in src.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
        "AND name NOT LIKE 'alembic_%' "
        "ORDER BY name"
    ).fetchall()
]

print(f'\n[SQLITE] Найдено таблиц: {len(sqlite_tables)}')
for t in sqlite_tables:
    cnt = src.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
    print(f'  {t}: {cnt} строк')

# --- Проверяем Render ---
print(f'\n[RENDER] Проверяем доступность...')
try:
    r = requests.get(
        f'{RENDER_URL}/api/migrate/tables',
        params={'secret': MIGRATE_SECRET},
        timeout=30
    )
    if r.status_code == 403:
        print('ОШИБКА: Неверный MIGRATE_SECRET')
        sys.exit(1)
    elif r.status_code == 404:
        print('ОШИБКА: Endpoint /api/migrate/tables не найден.')
        print('Нужно задеплоить app.py с endpoint миграции на Render.')
        sys.exit(1)
    elif r.status_code != 200:
        print(f'ОШИБКА: HTTP {r.status_code}: {r.text[:200]}')
        sys.exit(1)

    pg_tables = r.json()
    print(f'[RENDER] Postgres таблицы: {pg_tables}')
except requests.exceptions.ConnectionError as e:
    print(f'ОШИБКА: Не удалось подключиться к {RENDER_URL}: {e}')
    sys.exit(1)
except Exception as e:
    print(f'ОШИБКА: {e}')
    sys.exit(1)

# --- Порядок таблиц ---
priority = ['user', 'topic', 'category', 'tag',
            'article', 'olympiad', 'problem']

def prio(t):
    for i, p in enumerate(priority):
        if p in t.lower():
            return i
    return 999

ordered = sorted(sqlite_tables, key=prio)

# Фильтр по таблице если указан
if args.table:
    ordered = [t for t in ordered if t == args.table]
    if not ordered:
        print(f'ОШИБКА: Таблица "{args.table}" не найдена в SQLite')
        sys.exit(1)

print(f'\n[ПОРЯДОК] {ordered}')
print('=' * 60)

# --- Миграция ---
total_ok = 0
total_fail = 0
total_skip = 0

for table in ordered:
    rows_raw = src.execute(f'SELECT * FROM "{table}"').fetchall()
    row_count = len(rows_raw)

    if row_count == 0:
        print(f'[{table}] пусто в SQLite — пропуск')
        continue

    # Проверяем, есть ли данные в Postgres
    pg_count = pg_tables.get(table, -1)
    if pg_count > 0 and not args.wipe:
        print(f'[{table}] в Postgres уже {pg_count} строк — '
              f'пропуск (нужен --wipe для перезалива)')
        total_skip += row_count
        continue

    if args.dry_run:
        print(f'[{table}] DRY-RUN: будет мигрировано {row_count} строк')
        total_ok += row_count
        continue

    # Конвертируем Row в dict
    col_names = rows_raw[0].keys() if rows_raw else []
    rows = []
    for r in rows_raw:
        row_dict = {}
        for k in col_names:
            v = r[k]
            # bytes -> base64 для JSON
            if isinstance(v, bytes):
                import base64
                v = base64.b64encode(v).decode('ascii')
            row_dict[k] = v
        rows.append(row_dict)

    # Отправляем батчами
    ok = 0
    fail = 0
    errors = []

    for i in range(0, len(rows), args.batch_size):
        batch = rows[i:i + args.batch_size]
        batch_num = i // args.batch_size + 1
        total_batches = (len(rows) + args.batch_size - 1) // args.batch_size

        payload = {
            'secret': MIGRATE_SECRET,
            'table': table,
            'rows': batch,
            'wipe': args.wipe and i == 0  # Очищаем только в первом батче
        }

        try:
            resp = requests.post(
                f'{RENDER_URL}/api/migrate/push',
                json=payload,
                timeout=120
            )

            if resp.status_code == 200:
                result = resp.json()
                ok += result.get('ok', 0)
                fail += result.get('fail', 0)
                batch_errors = result.get('errors', [])
                errors.extend(batch_errors)
                print(f'  [{table}] батч {batch_num}/{total_batches}: '
                      f'OK={result.get("ok", 0)} FAIL={result.get("fail", 0)}')
            elif resp.status_code == 404:
                print(f'  [{table}] ОШИБКА: модель не найдена на Render')
                fail += len(batch)
                break
            else:
                print(f'  [{table}] ОШИБКА HTTP {resp.status_code}: '
                      f'{resp.text[:200]}')
                fail += len(batch)

        except requests.exceptions.Timeout:
            print(f'  [{table}] ТАЙМАУТ батча {batch_num}')
            fail += len(batch)
        except Exception as e:
            print(f'  [{table}] ОШИБКА: {e}')
            fail += len(batch)

    if errors:
        print(f'  [{table}] Примеры ошибок:')
        for err in errors[:3]:
            print(f'    {err[:150]}')

    print(f'[{table}] DONE OK={ok} FAIL={fail}')
    total_ok += ok
    total_fail += fail

print('=' * 60)
print(f'ИТОГО: OK={total_ok}  FAIL={total_fail}  SKIP={total_skip}')

# --- Финальная проверка ---
print('\n[ПРОВЕРКА] Количество строк в Postgres после миграции:')
try:
    r = requests.get(
        f'{RENDER_URL}/api/migrate/tables',
        params={'secret': MIGRATE_SECRET},
        timeout=30
    )
    if r.status_code == 200:
        for table, cnt in sorted(r.json().items()):
            print(f'  {table}: {cnt}')
except Exception as e:
    print(f'  Ошибка проверки: {e}')

src.close()
print('\nГОТОВО')
