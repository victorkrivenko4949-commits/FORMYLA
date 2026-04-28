# -*- coding: utf-8 -*-
"""
Прямая миграция SQLite -> PostgreSQL через psycopg3.
НЕ импортирует Flask app — использует psycopg3 напрямую.

Использование:
  python scripts/migrate_pg_direct.py                  # берёт URL из .env.migration
  python scripts/migrate_pg_direct.py <EXTERNAL_URL>   # явный URL
  python scripts/migrate_pg_direct.py --dry-run        # только показать план
  python scripts/migrate_pg_direct.py --wipe           # удалить+создать таблицы
"""
import os
import sys
import sqlite3
import argparse
from pathlib import Path

# --- Парсинг аргументов ---
parser = argparse.ArgumentParser(description="Прямая миграция SQLite -> Postgres")
parser.add_argument('url', nargs='?', help='External Postgres URL')
parser.add_argument('--dry-run', action='store_true', help='Только показать план')
parser.add_argument('--wipe', action='store_true', help='Удалить+создать таблицы')
parser.add_argument('--table', help='Мигрировать только эту таблицу')
args = parser.parse_args()

# --- Получение URL ---
EXTERNAL = args.url
if not EXTERNAL:
    env_file = Path('.env.migration')
    if env_file.exists():
        for line in env_file.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if line.startswith('EXTERNAL_DATABASE_URL='):
                EXTERNAL = line.split('=', 1)[1].strip()
                break
if not EXTERNAL:
    print('ОШИБКА: External Postgres URL не задан.')
    sys.exit(1)

# Для psycopg3 нужен postgresql:// (без +psycopg)
PG_URL = EXTERNAL
if PG_URL.startswith('postgres://'):
    PG_URL = PG_URL.replace('postgres://', 'postgresql://', 1)

# Добавляем sslmode=require для внешних подключений к Render
if '?' not in PG_URL:
    PG_URL += '?sslmode=require'
elif 'sslmode' not in PG_URL:
    PG_URL += '&sslmode=require'

at_pos = PG_URL.find('@')
print(f'[КОНФИГ] Цель: ...@{PG_URL[at_pos+1:].split("?")[0] if at_pos > 0 else "***"}')

# --- Тест подключения ---
try:
    import psycopg
except ImportError:
    print('ОШИБКА: psycopg не установлен. Запустите: pip install "psycopg[binary]"')
    sys.exit(1)

print('[ПОДКЛЮЧЕНИЕ] Тестируем PostgreSQL...')
try:
    pg = psycopg.connect(PG_URL, autocommit=False, connect_timeout=15)
    print('[ПОДКЛЮЧЕНИЕ] УСПЕХ')
except Exception as e:
    print(f'[ПОДКЛЮЧЕНИЕ] ОШИБКА: {e}')
    sys.exit(1)

# --- Открываем SQLite ---
SQLITE_PATH = Path('instance/formyla.db')
if not SQLITE_PATH.exists():
    print(f'ОШИБКА: SQLite не найден: {SQLITE_PATH}')
    sys.exit(1)

src = sqlite3.connect(str(SQLITE_PATH))
src.row_factory = sqlite3.Row

# Получаем все таблицы SQLite
sqlite_tables_raw = [
    r[0] for r in src.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
        "ORDER BY name"
    ).fetchall()
]

print(f'[SQLITE] Найдено {len(sqlite_tables_raw)} таблиц:')
table_counts = {}
for t in sqlite_tables_raw:
    cnt = src.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
    table_counts[t] = cnt
    print(f'  {t}: {cnt} строк')

# --- Импорт моделей для получения схемы ---
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Устанавливаем DATABASE_URL на sqlite чтобы app не пытался подключиться к PG
os.environ['DATABASE_URL'] = 'sqlite:///formyla.db'
print('[ИНИТ] Загрузка моделей (SQLite режим для схемы)...')

from models import db
from flask import Flask

# Создаём минимальное Flask приложение только для интроспекции моделей
_app = Flask(__name__)
_app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///formyla.db'
_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(_app)

with _app.app_context():
    # Строим маппинг tablename -> Model class
    models_by_table = {}
    for mapper in db.Model.registry.mappers:
        cls = mapper.class_
        tname = getattr(cls, '__tablename__', None)
        if tname:
            models_by_table[tname] = cls

    print(f'[МОДЕЛИ] Найдено {len(models_by_table)} моделей:')
    for t in sorted(models_by_table.keys()):
        print(f'  {t} -> {models_by_table[t].__name__}')

# --- Создание таблиц в Postgres через SQLAlchemy metadata ---
from sqlalchemy import create_engine

# URL для SQLAlchemy (нужен +psycopg)
SA_URL = EXTERNAL
if SA_URL.startswith('postgres://'):
    SA_URL = SA_URL.replace('postgres://', 'postgresql+psycopg://', 1)
elif SA_URL.startswith('postgresql://') and '+psycopg' not in SA_URL:
    SA_URL = SA_URL.replace('postgresql://', 'postgresql+psycopg://', 1)

# Добавляем sslmode
if '?' not in SA_URL:
    SA_URL += '?sslmode=require'
elif 'sslmode' not in SA_URL:
    SA_URL += '&sslmode=require'

pg_engine = create_engine(SA_URL, echo=False)

# --- Порядок миграции (родители первыми для FK) ---
PRIORITY_ORDER = [
    'users',
    'oauth_accounts',
    'secret_topics',
    'olympiad_secrets',
    'adaptive_tasks',
    'adaptive_tests',
    'adaptive_test_problems',
    'adaptive_test_results',
    'user_topic_progress',
    'topic_mastery',
    'user_streaks',
    'daily_quests',
    'chat_messages',
    'mock_exams',
    'mock_exam_tasks',
    'friendships',
    'notifications',
    'mentorships',
    'olympiad_generation_log',
]

def sort_key(table_name):
    try:
        return PRIORITY_ORDER.index(table_name)
    except ValueError:
        return 999

ordered_tables = sorted(sqlite_tables_raw, key=sort_key)
if args.table:
    ordered_tables = [t for t in ordered_tables if t == args.table]

# --- Создание таблиц ---
cur = pg.cursor()

if args.wipe and not args.dry_run:
    print('[POSTGRES] WIPE: удаляем все таблицы...')
    for t in reversed(PRIORITY_ORDER):
        try:
            cur.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE')
        except Exception as e:
            print(f'  drop {t}: {e}')
    for t in sqlite_tables_raw:
        if t not in PRIORITY_ORDER:
            try:
                cur.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE')
            except Exception:
                pass
    pg.commit()
    print('[POSTGRES] Таблицы удалены.')

print('[POSTGRES] Создание таблиц...')
with _app.app_context():
    metadata = db.metadata
    try:
        metadata.create_all(pg_engine)
        print('[POSTGRES] Таблицы созданы успешно.')
    except Exception as e:
        print(f'[POSTGRES] Ошибка create_all: {e}')
        for table in metadata.sorted_tables:
            try:
                table.create(pg_engine, checkfirst=True)
            except Exception as e2:
                print(f'  создание {table.name}: {e2}')

# --- Миграция данных ---
print(f'\n[МИГРАЦИЯ] Порядок: {ordered_tables}')
print('=' * 60)

total_ok = 0
total_fail = 0

for table in ordered_tables:
    Model = models_by_table.get(table)
    if not Model:
        print(f'[{table}] нет SQLAlchemy модели, ПРОПУСК')
        continue

    rows = src.execute(f'SELECT * FROM "{table}"').fetchall()
    if not rows:
        print(f'[{table}] пусто в SQLite, ПРОПУСК')
        continue

    # Проверяем есть ли данные в Postgres
    try:
        cur.execute(f'SELECT COUNT(*) FROM "{table}"')
        existing = cur.fetchone()[0]
    except Exception:
        pg.rollback()
        existing = 0

    if existing > 0 and not args.wipe:
        print(f'[{table}] уже {existing} строк в Postgres, ПРОПУСК (используй --wipe)')
        continue

    if args.dry_run:
        print(f'[{table}] DRY-RUN: будет мигрировано {len(rows)} строк')
        continue

    # Если wipe, очищаем данные
    if args.wipe and existing > 0:
        try:
            cur.execute(f'DELETE FROM "{table}"')
            pg.commit()
        except Exception:
            pg.rollback()

    # Получаем валидные колонки из модели
    model_columns = {c.name for c in Model.__table__.columns}

    # Получаем колонки из первой строки SQLite
    sqlite_cols = rows[0].keys()
    valid_cols = [c for c in sqlite_cols if c in model_columns]

    if not valid_cols:
        print(f'[{table}] нет совпадающих колонок, ПРОПУСК')
        continue

    # Строим INSERT
    col_list = ', '.join(f'"{c}"' for c in valid_cols)
    placeholders = ', '.join(f'%s' for _ in valid_cols)
    insert_sql = f'INSERT INTO "{table}" ({col_list}) VALUES ({placeholders})'

    ok = 0
    fail = 0
    batch = []
    batch_size = 200

    for r in rows:
        values = tuple(r[c] for c in valid_cols)
        batch.append(values)

        if len(batch) >= batch_size:
            try:
                cur.executemany(insert_sql, batch)
                pg.commit()
                ok += len(batch)
            except Exception as e:
                pg.rollback()
                # Пробуем по одной
                for v in batch:
                    try:
                        cur.execute(insert_sql, v)
                        pg.commit()
                        ok += 1
                    except Exception as e2:
                        pg.rollback()
                        fail += 1
                        if fail <= 5:
                            print(f'  ВНИМАНИЕ: {str(e2)[:200]}')
            batch = []

    # Остаток
    if batch:
        try:
            cur.executemany(insert_sql, batch)
            pg.commit()
            ok += len(batch)
        except Exception as e:
            pg.rollback()
            for v in batch:
                try:
                    cur.execute(insert_sql, v)
                    pg.commit()
                    ok += 1
                except Exception as e2:
                    pg.rollback()
                    fail += 1
                    if fail <= 5:
                        print(f'  ВНИМАНИЕ: {str(e2)[:200]}')

    # Сброс sequence для id
    if 'id' in valid_cols:
        try:
            cur.execute(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                f"COALESCE((SELECT MAX(id) FROM \"{table}\"), 1))"
            )
            pg.commit()
        except Exception:
            pg.rollback()

    total_ok += ok
    total_fail += fail
    status = 'OK' if fail == 0 else 'ЧАСТИЧНО'
    print(f'[{table}] {status}: OK={ok} FAIL={fail}')

print('=' * 60)
print(f'ИТОГО: OK={total_ok} FAIL={total_fail}')
if total_fail == 0 and total_ok > 0:
    print('ВСЕ МИГРАЦИИ УСПЕШНЫ')
elif total_fail > 0:
    print(f'ВНИМАНИЕ: {total_fail} строк с ошибками')
else:
    print('Нет строк для миграции (таблицы уже заполнены)')

src.close()
cur.close()
pg.close()
print('ГОТОВО')
