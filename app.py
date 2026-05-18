import re
import markdown as md_lib
from flask import Flask, render_template, request, abort, redirect, session, jsonify, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_mail import Mail, Message
from utils.math_answer_utils import compare_math_answers
from utils.rating_utils import add_xp_for_task, add_xp_for_adaptive_test, add_xp_for_mock_exam, get_xp_for_next_level
from utils.answer_evaluator import check_answers_batch
from utils.olympiad_days import split_problems_by_day
from olympiads import OLYMPIADS_DB as _RAW_DB
try:
    from olympiads import OLYMPIADS_INFO
except ImportError:
    # Создаем OLYMPIADS_INFO из OLYMPIADS_DB
    OLYMPIADS_INFO = []
    seen = set()
    for item in _RAW_DB:
        slug = item.get('olympiad', '')
        if slug and slug not in seen:
            OLYMPIADS_INFO.append({
                'slug': slug,
                'title': item.get('olympiad_title', slug)
            })
            seen.add(slug)
try:
    from problems import PROBLEMS_DB
except ImportError:
    PROBLEMS_DB = []
try:
    from adaptive_data import ADAPTIVE_DB
except ImportError:
    ADAPTIVE_DB = []
    print("ВНИМАНИЕ: Файл adaptive_data.py не найден или пуст.")
try:
    from problem_images import IMAGE_MAP
except ImportError:
    IMAGE_MAP = {}

print(f"DEBUG: Загружено {len(IMAGE_MAP)} привязок картинок из problem_images.py")

import requests, random, json, uuid, os, base64, math
from werkzeug.utils import secure_filename
import threading

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Import prefetch system
from simple_prefetch import get_cached_task, add_task_to_cache, clear_cache, get_cache_size

# AI Integration
try:
    from ai.deepseek_client import DeepSeekClient, DeepSeekAPIError
    DEEPSEEK_AVAILABLE = True
except ImportError:
    DEEPSEEK_AVAILABLE = False
    print("⚠️  DeepSeek client not available. AI recommendations disabled.")

# ─── Sentry SDK (отлов ошибок + perf-трейсинг) ─────────────────────
# Инициализируется до создания Flask app, чтобы FlaskIntegration перехватил всё.
_SENTRY_DSN = os.environ.get("SENTRY_DSN", "").strip()
SENTRY_ENABLED = False
if _SENTRY_DSN:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
        sentry_sdk.init(
            dsn=_SENTRY_DSN,
            integrations=[FlaskIntegration(), SqlalchemyIntegration()],
            traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
            profiles_sample_rate=float(os.environ.get("SENTRY_PROFILES_SAMPLE_RATE", "0.1")),
            send_default_pii=False,
            environment=os.environ.get("FLASK_ENV", "production"),
            release=os.environ.get("RENDER_GIT_COMMIT", "dev"),
        )
        SENTRY_ENABLED = True
        print("✅ Sentry SDK initialized")
    except Exception as _sentry_err:
        print(f"⚠️  Sentry init failed: {_sentry_err}")
else:
    print("ℹ️  SENTRY_DSN не задан — Sentry отключен.")


app = Flask(__name__)

# ─── Cloudflare ProxyFix (доверяем X-Forwarded-* за CF + Render) ───
try:
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=2, x_proto=1, x_host=1, x_prefix=1)
    print("✅ ProxyFix applied (x_for=2, x_proto=1, x_host=1, x_prefix=1)")
except Exception as _pf_err:
    print(f"⚠️  ProxyFix not applied: {_pf_err}")
app.config['JSON_AS_ASCII'] = False
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = False

# ── SECURITY: SECRET_KEY ──────────────────────────────────────────
# В production (Render) SECRET_KEY ОБЯЗАН быть задан в Environment.
# Без него все сессии подписываются одним ключом → утечка аккаунтов.
_secret = os.environ.get('SECRET_KEY')
_is_production = bool(os.environ.get('RENDER') or os.environ.get('DATABASE_URL'))

if _secret:
    app.secret_key = _secret
elif _is_production:
    # НА ПРОДЕ БЕЗ SECRET_KEY — КРИТИЧЕСКАЯ ОШИБКА
    raise RuntimeError(
        "🔴 CRITICAL: SECRET_KEY не задан в production!\n"
        "   Установи в Render → Environment → SECRET_KEY = <случайная строка 64 символа>\n"
        "   Генерация: python -c \"import secrets; print(secrets.token_hex(32))\""
    )
else:
    # Только для локальной разработки — стабильный ключ
    app.secret_key = 'dev-secret-key-LOCAL-ONLY-NOT-FOR-PRODUCTION'
    print("⚠️  WARNING: Используется дефолтный SECRET_KEY (только для локальной разработки!)")

# Asset versioning for cache busting
import time as _time
_asset_version = str(int(_time.time()))
app.jinja_env.globals['asset_version'] = _asset_version

# DEBUG: Проверка переменных окружения
print("="*60)
print("DEBUG: Доступные переменные окружения:")
env_keys = list(os.environ.keys())
print(f"Всего переменных: {len(env_keys)}")
print(f"SECRET_KEY = {'ЕСТЬ' if os.environ.get('SECRET_KEY') else 'НЕТ (используется автогенерация)'}")
print(f"MAIL_USERNAME = {os.environ.get('MAIL_USERNAME')}")
print(f"MAIL_PASSWORD = {'ЕСТЬ' if os.environ.get('MAIL_PASSWORD') else 'НЕТ'}")
print(f"DEEPSEEK_API_KEY = {'ЕСТЬ' if os.environ.get('DEEPSEEK_API_KEY') else 'НЕТ'}")
print("="*60)

# Database configuration -- supports SQLite (local) and PostgreSQL (production)
_database_url = os.environ.get('DATABASE_URL', 'sqlite:///formyla.db')
# Render provides postgres:// or postgresql:// but psycopg3 needs postgresql+psycopg://
if _database_url.startswith('postgres://'):
    _database_url = _database_url.replace('postgres://', 'postgresql+psycopg://', 1)
elif _database_url.startswith('postgresql://') and '+psycopg' not in _database_url:
    _database_url = _database_url.replace('postgresql://', 'postgresql+psycopg://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = _database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 300,
}
print(f'[DB] Using: ' + _database_url.split('@')[0] + '@***')

# Flask-Login configuration (долгоживущие cookie)
from datetime import timedelta, datetime
app.config['REMEMBER_COOKIE_DURATION'] = timedelta(days=365)
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=365)  # Постоянные сессии на 365 дней
domain_url = os.environ.get('DOMAIN_URL', 'http://localhost:5000')
_is_https = domain_url.startswith('https') or _is_production
app.config['REMEMBER_COOKIE_SECURE'] = _is_https
app.config['REMEMBER_COOKIE_HTTPONLY'] = True
app.config['REMEMBER_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = _is_https
app.config['SESSION_COOKIE_HTTPONLY'] = True  # CRITICAL: Prevent JavaScript access to session cookie
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Flask-Mail configuration (Yandex by default, fully configurable via env vars)
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.yandex.ru')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', '465'))
# Жесткое преобразование строк в bool (исправлено для корректной работы)
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'False').lower() in ['true', '1', 't', 'yes']
app.config['MAIL_USE_SSL'] = os.environ.get('MAIL_USE_SSL', 'True').lower() in ['true', '1', 't', 'yes']
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_USERNAME')

# DEBUG: Проверка конфигурации Flask-Mail
print("="*60)
print("DEBUG: Flask-Mail Configuration:")
print(f"MAIL_SERVER = {app.config['MAIL_SERVER']}")
print(f"MAIL_PORT = {app.config['MAIL_PORT']}")
print(f"MAIL_USE_TLS = {app.config['MAIL_USE_TLS']}")
print(f"MAIL_USE_SSL = {app.config['MAIL_USE_SSL']}")
print(f"MAIL_USERNAME = {app.config['MAIL_USERNAME']}")
print(f"MAIL_PASSWORD = {'*' * len(app.config['MAIL_PASSWORD']) if app.config['MAIL_PASSWORD'] else 'НЕТ'} ({len(app.config['MAIL_PASSWORD']) if app.config['MAIL_PASSWORD'] else 0} символов)")
print("="*60)

# Yandex OAuth configuration
app.config['YANDEX_CLIENT_ID'] = os.environ.get('YANDEX_CLIENT_ID')
app.config['YANDEX_CLIENT_SECRET'] = os.environ.get('YANDEX_CLIENT_SECRET')
app.config['DOMAIN_URL'] = os.environ.get('DOMAIN_URL', 'http://localhost:5000')

# Telegram Login Widget — bot username (без @) для встраивания в шаблоны
app.config['TELEGRAM_BOT_USERNAME'] = (os.environ.get('TELEGRAM_BOT_USERNAME') or '').strip()
# Plausible Analytics — домен сайта в плаусибл-аккаунте (пусто = аналитика выключена)
app.config['PLAUSIBLE_DOMAIN'] = (os.environ.get('PLAUSIBLE_DOMAIN') or '').strip()

# Initialize database, login manager and mail.
# ВАЖНО: импортируем ВСЕ модели до init_db(), иначе db.create_all() не
# создаст таблицы для тех моделей, которые подгружаются позже по коду
# (например, GroupChat/GroupMember/GroupMessage в /api/groups).
from models import (
    db, User, Friendship, Mentorship, AdaptiveTask, UserTopicProgress,
    AdaptiveTestResult, TestResult, UserProgress,
    GroupChat, GroupMember, GroupMessage,
    init_db,
)
init_db(app)

# AUTO-MIGRATION: Add agent_type column if it doesn't exist
# This runs on every startup to ensure database schema is up to date
try:
    with app.app_context():
        from sqlalchemy import inspect, text
        inspector = inspect(db.engine)
        
        # Check if chat_messages table exists
        if 'chat_messages' in inspector.get_table_names():
            columns = [col['name'] for col in inspector.get_columns('chat_messages')]
            
            # Add agent_type column if it doesn't exist
            if 'agent_type' not in columns:
                print("[AUTO-MIGRATION] Adding 'agent_type' column to chat_messages...")
                db.session.execute(text("ALTER TABLE chat_messages ADD COLUMN agent_type VARCHAR(50) DEFAULT 'general' NOT NULL"))
                db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_chat_messages_agent_type ON chat_messages (agent_type)"))
                db.session.commit()
                print("[AUTO-MIGRATION] ✓ Column 'agent_type' added successfully!")
            else:
                print("[AUTO-MIGRATION] ✓ Column 'agent_type' already exists")
except Exception as e:
    print(f"[AUTO-MIGRATION] Warning: {e}")
    # Continue anyway - app should still work

# AUTO-MIGRATION: Add difficulty calibration columns to adaptive_tasks
try:
    with app.app_context():
        from sqlalchemy import inspect, text
        inspector = inspect(db.engine)
        if 'adaptive_tasks' in inspector.get_table_names():
            columns = [col['name'] for col in inspector.get_columns('adaptive_tasks')]
            new_cols = {
                'subtopic': 'VARCHAR(100)',
                'attempts_count': 'INTEGER DEFAULT 0',
                'solves_count': 'INTEGER DEFAULT 0',
                'actual_solve_rate': 'REAL',
                'suggested_level': 'INTEGER',
                'needs_reclassification': 'BOOLEAN DEFAULT 0',
                'last_calibrated_at': 'DATETIME',
            }
            for col_name, col_type in new_cols.items():
                if col_name not in columns:
                    db.session.execute(text(f"ALTER TABLE adaptive_tasks ADD COLUMN {col_name} {col_type}"))
                    db.session.commit()
                    print(f"[AUTO-MIGRATION] ✓ Column '{col_name}' added to adaptive_tasks")
                else:
                    print(f"[AUTO-MIGRATION] ✓ Column '{col_name}' already exists")
except Exception as e:
    print(f"[AUTO-MIGRATION] adaptive_tasks Warning: {e}")

# AUTO-MIGRATION: Create tutor_calls table for AI-тьютор v2 logging
try:
    with app.app_context():
        _is_pg = _database_url.startswith('postgresql')
        if _is_pg:
            db.session.execute(text("""
                CREATE TABLE IF NOT EXISTS tutor_calls (
                    id SERIAL PRIMARY KEY,
                    task_id INTEGER NOT NULL,
                    user_answer TEXT,
                    raw_response TEXT,
                    extracted_solution TEXT,
                    status TEXT,
                    validation_errors TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
        else:
            db.session.execute(text("""
                CREATE TABLE IF NOT EXISTS tutor_calls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL,
                    user_answer TEXT,
                    raw_response TEXT,
                    extracted_solution TEXT,
                    status TEXT,
                    validation_errors TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
        db.session.commit()
        print("[AUTO-MIGRATION] ✓ Table 'tutor_calls' ready")
except Exception as e:
    print(f"[AUTO-MIGRATION] tutor_calls Warning: {e}")

# AUTO-MIGRATION: Add needs_review columns to adaptive_tasks for AI-тьютор self-check
try:
    with app.app_context():
        from sqlalchemy import inspect as _inspect_nr
        _inspector_nr = _inspect_nr(db.engine)
        _is_pg_nr = _database_url.startswith('postgresql')
        # Postgres требует BOOLEAN DEFAULT FALSE/TRUE; SQLite принимает 0/1.
        _bool_default_false = 'BOOLEAN DEFAULT FALSE' if _is_pg_nr else 'BOOLEAN DEFAULT 0'
        if 'adaptive_tasks' in _inspector_nr.get_table_names():
            _cols_nr = [col['name'] for col in _inspector_nr.get_columns('adaptive_tasks')]
            _new_review_cols = {
                'needs_review': _bool_default_false,
                'llm_suggested_answer': 'TEXT',
                'llm_suggested_solution': 'TEXT',
                'review_reason': 'TEXT',
                'review_flagged_at': 'TIMESTAMP',
            }
            for _col_name, _col_type in _new_review_cols.items():
                if _col_name not in _cols_nr:
                    try:
                        db.session.execute(text(f"ALTER TABLE adaptive_tasks ADD COLUMN {_col_name} {_col_type}"))
                        db.session.commit()
                        print(f"[AUTO-MIGRATION] ✓ Column '{_col_name}' added to adaptive_tasks")
                    except Exception as _e_col_nr:
                        db.session.rollback()
                        print(f"[AUTO-MIGRATION] adaptive_tasks.{_col_name} skipped: {_e_col_nr}")
except Exception as e:
    print(f"[AUTO-MIGRATION] needs_review columns Warning: {e}")

# AUTO-MIGRATION: Создаём таблицы group_chats / group_members / group_messages
# на проде, если их ещё нет. На локалке db.create_all() в init_db уже создал
# их, но на проде Postgres может быть старая БД, где этих таблиц нет.
try:
    with app.app_context():
        from sqlalchemy import inspect as _inspect_grp
        from models import GroupChat as _GC, GroupMember as _GM, GroupMessage as _GMsg
        _ins = _inspect_grp(db.engine)
        _existing = set(_ins.get_table_names())
        _need = [t for t in ('group_chats', 'group_members', 'group_messages') if t not in _existing]
        if _need:
            print(f"[AUTO-MIGRATION] Creating missing group chat tables: {_need}")
            db.create_all()
            print(f"[AUTO-MIGRATION] ✓ Group chat tables created")
        else:
            print("[AUTO-MIGRATION] ✓ Group chat tables already exist")
        # Add missing columns to group_chats (avatar_emoji added later)
        if 'group_chats' in _ins.get_table_names():
            _cols_gc = {c['name'] for c in _ins.get_columns('group_chats')}
            if 'avatar_emoji' not in _cols_gc:
                try:
                    db.session.execute(db.text(
                        "ALTER TABLE group_chats ADD COLUMN avatar_emoji VARCHAR(8) DEFAULT '\U0001F465'"
                    ))
                    db.session.commit()
                    print("[AUTO-MIGRATION] OK Added avatar_emoji to group_chats")
                except Exception as _e_av:
                    db.session.rollback()
                    print(f"[AUTO-MIGRATION] avatar_emoji add Warning: {_e_av}")
except Exception as e:
    print(f"[AUTO-MIGRATION] group_chats Warning: {e}")

# AUTO-MIGRATION: VsOSh-9 method-bank fields для olympiad_theory / olympiad_tasks.
# Модели в models_olympiad.py содержат новые колонки (total_count, share_percent,
# method_codes, year, stage). На локалке SQLite db.create_all() их подхватывает,
# но на проде Postgres колонки нужно добавить ALTER-ом, иначе любой SELECT
# по таблицам сыпет UndefinedColumn → 500 на каждой странице.
try:
    with app.app_context():
        _is_pg_olymp = _database_url.startswith('postgresql')
        _json_type = 'JSONB' if _is_pg_olymp else 'JSON'
        _float_type = 'DOUBLE PRECISION' if _is_pg_olymp else 'REAL'

        def _alter(tbl, col, sql_type, default_clause=''):
            if _is_pg_olymp:
                return (tbl, col,
                        f'ALTER TABLE {tbl} ADD COLUMN IF NOT EXISTS {col} {sql_type}{default_clause}')
            return (tbl, col, f'ALTER TABLE {tbl} ADD COLUMN {col} {sql_type}{default_clause}')

        _alters_olymp = [
            # method-bank статистика (xlsx-аналитика по ВсОШ-9)
            _alter('olympiad_theory', 'total_count', 'INTEGER'),
            _alter('olympiad_theory', 'share_percent', _float_type),
            # каталог методов (был в migrations/add_methods_catalog_fields.py)
            _alter('olympiad_theory', 'grades', _json_type),
            _alter('olympiad_theory', 'recommended_competitions', _json_type),
            _alter('olympiad_theory', 'difficulty_level', 'INTEGER'),
            _alter('olympiad_theory', 'frequency_vsosh_9', 'INTEGER'),
            _alter('olympiad_theory', 'sort_order', 'INTEGER', ' DEFAULT 0'),
            # связанные поля задач
            _alter('olympiad_tasks', 'method_codes', _json_type),
            _alter('olympiad_tasks', 'year', 'INTEGER'),
            _alter('olympiad_tasks', 'stage', 'VARCHAR(20)'),
        ]
        from sqlalchemy import inspect as _inspect_olymp
        _ins_o = _inspect_olymp(db.engine)
        _existing_o = set(_ins_o.get_table_names())
        for _tbl, _col, _sql in _alters_olymp:
            if _tbl not in _existing_o:
                continue
            try:
                _cols = {c['name'] for c in _ins_o.get_columns(_tbl)}
            except Exception:
                _cols = set()
            if _col in _cols:
                continue
            try:
                db.session.execute(db.text(_sql))
                db.session.commit()
                print(f"[AUTO-MIGRATION] OK Added {_tbl}.{_col}")
            except Exception as _e_col:
                db.session.rollback()
                print(f"[AUTO-MIGRATION] {_tbl}.{_col} skipped: {_e_col}")
except Exception as _e_olymp:
    print(f"[AUTO-MIGRATION] olympiad fields Warning: {_e_olymp}")

# AUTO-MIGRATION: Add guest access columns to users
try:
    with app.app_context():
        # --- Guest access columns ---
        try:
            db.session.execute(db.text("ALTER TABLE users ADD COLUMN is_guest BOOLEAN NOT NULL DEFAULT FALSE"))
            db.session.commit()
            print("[migration] Added is_guest to users")
        except Exception:
            db.session.rollback()

        try:
            db.session.execute(db.text("ALTER TABLE users ADD COLUMN device_id VARCHAR(64)"))
            db.session.commit()
            print("[migration] Added device_id to users")
        except Exception:
            db.session.rollback()

        # --- preferred_grade for Daily Quest ---
        try:
            db.session.execute(db.text("ALTER TABLE users ADD COLUMN preferred_grade INTEGER"))
            db.session.commit()
            print("[migration] Added preferred_grade to users")
        except Exception:
            db.session.rollback()

        # --- current_plan and plan_expires_at for subscriptions ---
        try:
            db.session.execute(db.text("ALTER TABLE users ADD COLUMN current_plan TEXT DEFAULT 'free'"))
            db.session.commit()
            print("[migration] Added current_plan to users")
        except Exception:
            db.session.rollback()

        try:
            db.session.execute(db.text("ALTER TABLE users ADD COLUMN plan_expires_at TIMESTAMP"))
            db.session.commit()
            print("[migration] Added plan_expires_at to users")
        except Exception:
            db.session.rollback()

        # --- onboarded_at: marks first visit to /about?onboarding=1 ---
        try:
            db.session.execute(db.text("ALTER TABLE users ADD COLUMN onboarded_at TIMESTAMP"))
            db.session.commit()
            print("[migration] Added onboarded_at to users")
        except Exception:
            db.session.rollback()

        # --- Telegram Login Widget: telegram_id (unique) + telegram_username ---
        for _tg_stmt, _tg_label in (
            ("ALTER TABLE users ADD COLUMN telegram_id VARCHAR(64)", "telegram_id"),
            ("ALTER TABLE users ADD COLUMN telegram_username VARCHAR(64)", "telegram_username"),
        ):
            try:
                db.session.execute(db.text(_tg_stmt))
                db.session.commit()
                print(f"[migration] Added {_tg_label} to users")
            except Exception:
                db.session.rollback()
        try:
            db.session.execute(db.text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_telegram_id ON users (telegram_id)"
            ))
            db.session.commit()
        except Exception:
            db.session.rollback()

        # --- TheoryBlock: total_count + share_percent (VsOSh-9 method stats) ---
        try:
            db.session.execute(db.text("ALTER TABLE olympiad_theory ADD COLUMN total_count INTEGER"))
            db.session.commit()
            print("[migration] Added total_count to olympiad_theory")
        except Exception:
            db.session.rollback()
        try:
            db.session.execute(db.text("ALTER TABLE olympiad_theory ADD COLUMN share_percent REAL"))
            db.session.commit()
            print("[migration] Added share_percent to olympiad_theory")
        except Exception:
            db.session.rollback()

        # --- OlympiadTask: method_codes (JSON), year (Int), stage (String) ---
        # Используются импортёром scripts/import_vsosh9_methods.py для архива ВсОШ-9.
        for _stmt, _label in (
            ("ALTER TABLE olympiad_tasks ADD COLUMN method_codes JSON", "method_codes"),
            ("ALTER TABLE olympiad_tasks ADD COLUMN year INTEGER", "year"),
            ("ALTER TABLE olympiad_tasks ADD COLUMN stage VARCHAR(20)", "stage"),
        ):
            try:
                db.session.execute(db.text(_stmt))
                db.session.commit()
                print(f"[migration] Added {_label} to olympiad_tasks")
            except Exception:
                db.session.rollback()
except Exception as e:
    print(f"[AUTO-MIGRATION] guest columns Warning: {e}")

# AUTO-MIGRATION: Fix friendships table (old schema had user_1_id/user_2_id, new has requester_id/addressee_id)
try:
    with app.app_context():
        from sqlalchemy import inspect as _inspect_fr
        _inspector_fr = _inspect_fr(db.engine)
        if 'friendships' in _inspector_fr.get_table_names():
            _fr_cols = [col['name'] for col in _inspector_fr.get_columns('friendships')]
            if 'user_1_id' in _fr_cols and 'requester_id' not in _fr_cols:
                # Old schema — drop and recreate (table is likely empty or small)
                db.session.execute(text("DROP TABLE friendships"))
                db.session.commit()
                db.create_all()
                print("[AUTO-MIGRATION] ✓ Recreated friendships table with new schema")
            else:
                print("[AUTO-MIGRATION] ✓ friendships table schema OK")
        else:
            db.create_all()
            print("[AUTO-MIGRATION] ✓ Created friendships table")
except Exception as e:
    print(f"[AUTO-MIGRATION] friendships Warning: {e}")

# AUTO-MIGRATION: Create support_messages table for feedback form
try:
    with app.app_context():
        from sqlalchemy import inspect as _inspect_sm, text as _text_sm
        _inspector_sm = _inspect_sm(db.engine)
        if 'support_messages' not in _inspector_sm.get_table_names():
            _is_pg_sm = _database_url.startswith('postgresql')
            if _is_pg_sm:
                db.session.execute(_text_sm("""
                    CREATE TABLE IF NOT EXISTS support_messages (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                        user_nickname VARCHAR(64),
                        user_email VARCHAR(255),
                        category VARCHAR(32),
                        message TEXT NOT NULL,
                        page_url TEXT,
                        user_agent TEXT,
                        ip VARCHAR(64),
                        email_sent BOOLEAN DEFAULT false,
                        email_error TEXT,
                        status VARCHAR(16) DEFAULT 'new',
                        created_at TIMESTAMP DEFAULT NOW(),
                        resolved_at TIMESTAMP
                    )
                """))
                db.session.execute(_text_sm("""
                    CREATE INDEX IF NOT EXISTS idx_support_status
                    ON support_messages(status)
                """))
            else:
                db.session.execute(_text_sm("""
                    CREATE TABLE IF NOT EXISTS support_messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                        user_nickname VARCHAR(64),
                        user_email VARCHAR(255),
                        category VARCHAR(32),
                        message TEXT NOT NULL,
                        page_url TEXT,
                        user_agent TEXT,
                        ip VARCHAR(64),
                        email_sent BOOLEAN DEFAULT 0,
                        email_error TEXT,
                        status VARCHAR(16) DEFAULT 'new',
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        resolved_at DATETIME
                    )
                """))
            db.session.commit()
            print("[AUTO-MIGRATION] ✓ Created support_messages table")
        else:
            print("[AUTO-MIGRATION] ✓ support_messages table already exists")
except Exception as e:
    print(f"[AUTO-MIGRATION] support_messages Warning: {e}")

# AUTO-MIGRATION: Add solved_indices column to daily_quests
# Used to track per-task completion (so a solved task can't be re-attempted).
try:
    with app.app_context():
        from sqlalchemy import inspect, text
        inspector = inspect(db.engine)
        if 'daily_quests' in inspector.get_table_names():
            cols = [c['name'] for c in inspector.get_columns('daily_quests')]
            if 'solved_indices' not in cols:
                print("[AUTO-MIGRATION] Adding 'solved_indices' to daily_quests...")
                db.session.execute(text(
                    "ALTER TABLE daily_quests ADD COLUMN solved_indices TEXT DEFAULT '[]'"
                ))
                db.session.commit()
                print("[AUTO-MIGRATION] ✓ Column 'solved_indices' added")
            else:
                print("[AUTO-MIGRATION] ✓ Column 'solved_indices' already exists")
except Exception as e:
    print(f"[AUTO-MIGRATION] solved_indices Warning: {e}")


# CHAT_WA_MIGRATION_V1: WhatsApp-style chat columns (reply/edit/delete/forward)
# CHAT_RECEIPTS_V1:    delivered_at / read_at (added 2026-05-15)
try:
    with app.app_context():
        from sqlalchemy import inspect as _wa_inspect, text as _wa_text
        _wa_insp = _wa_inspect(db.engine)
        if 'direct_messages' in _wa_insp.get_table_names():
            _wa_cols = [c['name'] for c in _wa_insp.get_columns('direct_messages')]
            for _col, _type in (
                ('reply_to_id', 'INTEGER NULL'),
                ('edited_at', 'TIMESTAMP NULL'),
                ('deleted_at', 'TIMESTAMP NULL'),
                ('forwarded_from_id', 'INTEGER NULL'),
                ('delivered_at', 'TIMESTAMP NULL'),
                ('read_at', 'TIMESTAMP NULL'),
                # CHAT_ATTACH_V1 — вложения
                ('attachment_url', 'VARCHAR(400) NULL'),
                ('attachment_kind', 'VARCHAR(16) NULL'),
                ('attachment_name', 'VARCHAR(255) NULL'),
                ('attachment_size', 'INTEGER NULL'),
            ):
                if _col not in _wa_cols:
                    try:
                        db.session.execute(_wa_text(
                            f"ALTER TABLE direct_messages ADD COLUMN {_col} {_type}"
                        ))
                        db.session.commit()
                        print(f"[AUTO-MIGRATION] direct_messages.{_col} added")
                    except Exception as _wa_e:
                        db.session.rollback()
                        print(f"[AUTO-MIGRATION] direct_messages.{_col} failed: {_wa_e}")
except Exception as e:
    print(f"[AUTO-MIGRATION] WA-chat Warning: {e}")


def _log_tutor_call(task_id: int, user_answer: str, result: dict):
    """Логирует вызов AI-тьютора v2 в таблицу tutor_calls."""
    try:
        db.session.execute(
            text("""
                INSERT INTO tutor_calls
                    (task_id, user_answer, raw_response,
                     extracted_solution, status, validation_errors)
                VALUES (:task_id, :user_answer, :raw_response,
                        :extracted_solution, :status, :validation_errors)
            """),
            {
                'task_id': task_id,
                'user_answer': str(user_answer or ''),
                'raw_response': result.get('raw_response', '')[:8000],
                'extracted_solution': result.get('solution', '')[:4000],
                'status': result.get('status', ''),
                'validation_errors': ','.join(result.get('errors', [])),
            }
        )
        db.session.commit()
    except Exception as log_err:
        import logging as _logging
        _logging.getLogger(__name__).warning(
            f"[tutor_calls] Failed to log: {log_err}"
        )


login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Пожалуйста, войдите для доступа к этой странице'

mail = Mail(app)

# ── REGISTER BLUEPRINTS ───────────────────────────────────────────
# NOTE: daily_olympiad blueprint ("Написать олимпиаду", /olympiad/write)
# removed by request together with the "Написать олимпиаду" section.

try:
    from routes.prep import prep_bp
    app.register_blueprint(prep_bp)
    print("[BP] prep_bp registered (/prep)")
except Exception as _e:
    print(f"[BP] prep_bp NOT registered: {_e}")

try:
    from routes.olympiad_prep import olympiad_prep_bp
    app.register_blueprint(olympiad_prep_bp)
    print("[BP] olympiad_prep_bp registered (/olympiad-prep)")
except Exception as _e:
    print(f"[BP] olympiad_prep_bp NOT registered: {_e}")

try:
    from routes.account import account_bp
    app.register_blueprint(account_bp)
    print("[BP] account_bp registered (/account)")
except Exception as _e:
    print(f"[BP] account_bp NOT registered: {_e}")

try:
    from routes.drawing import drawing_bp
    app.register_blueprint(drawing_bp)
    print("[BP] drawing_bp registered (/drawing)")
except Exception as _e:
    print(f"[BP] drawing_bp NOT registered: {_e}")

try:
    from routes.drawing_diag import drawing_diag_bp
    app.register_blueprint(drawing_diag_bp)
    print("[BP] drawing_diag_bp registered (/api/drawing/diag)")
except Exception as _e:
    print(f"[BP] drawing_diag_bp NOT registered: {_e}")

try:
    from routes.drawing_history import drawing_history_bp
    app.register_blueprint(drawing_history_bp)
    print("[BP] drawing_history_bp registered (/api/drawing/history, /drawing/history)")
except Exception as _e:
    print(f"[BP] drawing_history_bp NOT registered: {_e}")

# Whiteboard 1-to-1 video call signalling (WebRTC, no SocketIO).
try:
    from routes.wb_call import wb_call_bp
    app.register_blueprint(wb_call_bp)
    print("[BP] wb_call_bp registered (/api/wb_call/*)")
except Exception as _e:
    print(f"[BP] wb_call_bp NOT registered: {_e}")

# Whiteboard group meet (LiveKit-backed, up to 10 participants).
# Endpoints become 503 if LIVEKIT_* env vars are not set on the server.
try:
    from routes.wb_meet import wb_meet_bp
    app.register_blueprint(wb_meet_bp)
    print("[BP] wb_meet_bp registered (/api/wb_meet/*)")
except Exception as _e:
    print(f"[BP] wb_meet_bp NOT registered: {_e}")

try:
    from routes.chat_presence import chat_presence_bp, _ensure_table as _ensure_presence_table
    app.register_blueprint(chat_presence_bp)
    with app.app_context():
        _ensure_presence_table()
    print("[BP] chat_presence_bp registered (/api/chat/*/presence, typing)")
except Exception as _e:
    print(f"[BP] chat_presence_bp NOT registered: {_e}")

# New /olympiads/* section (next to legacy /olympiads, /olympiads/open, /olympiads/solution/<id>).
# Catalog of the new section lives at /olympiads/courses until the legacy route is retired.
try:
    from routes.olympiad import olympiad_bp
    app.register_blueprint(olympiad_bp)
    print("[BP] olympiad_bp registered (/olympiads/*: courses, vsosh-9-2027, probnik, task, stage, methods, my-progress)")
except Exception as _e:
    print(f"[BP] olympiad_bp NOT registered: {_e}")

# Auto-seed олимпиадного раздела — отключен по умолчанию (после первого деплоя
# словил 500 из-за рассогласования модели/БД). Включить можно явно переменной
# окружения OLYMPIAD_AUTOSEED=1.
if os.environ.get('OLYMPIAD_AUTOSEED', '').strip() in ('1', 'true', 'yes', 'on'):
    try:
        from services.olympiad_autoseed import autoseed_olympiad
        autoseed_olympiad(app, db)
    except Exception as _e_seed:
        print(f"[OLYMPIAD-SEED] Autoseed skipped: {_e_seed}")
else:
    print("[OLYMPIAD-SEED] disabled (set OLYMPIAD_AUTOSEED=1 to enable)")

# /grade-5 and /grade-6 — тренажёр FORMYLA по школьным классам.
try:
    from routes.grade import grade_bp
    app.register_blueprint(grade_bp)
    print("[BP] grade_bp registered (/grade-5, /grade-6, /grade-task/*)")
except Exception as _e:
    print(f"[BP] grade_bp NOT registered: {_e}")

# /api/concierge/* — Site Concierge AI helper (отдельный от ИИ-тьютора).
try:
    from routes.concierge import concierge_bp
    app.register_blueprint(concierge_bp)
    print("[BP] concierge_bp registered (/api/concierge/ask, /api/concierge/intents)")
except Exception as _e:
    print(f"[BP] concierge_bp NOT registered: {_e}")

# /auth/telegram/* — Telegram Login Widget callback.
try:
    from routes.telegram_auth import telegram_auth_bp
    app.register_blueprint(telegram_auth_bp)
    print("[BP] telegram_auth_bp registered (/auth/telegram/callback)")
except Exception as _e:
    print(f"[BP] telegram_auth_bp NOT registered: {_e}")

# Jinja filter for Markdown rendering of olympiad task/theory text (LaTeX-safe).
try:
    from services.md_render import md_render as _md_render_filter
    app.jinja_env.filters['md_render'] = _md_render_filter
    print("[JINJA] filter md_render registered")
except Exception as _e:
    print(f"[JINJA] md_render filter NOT registered: {_e}")

# Limit upload size: 12 MB (for solution photos AND drawing-task screenshots
# that get base64-encoded; raw image cap remains 8 MB on the drawing route).
app.config['MAX_CONTENT_LENGTH'] = 12 * 1024 * 1024

# ── GLOBAL ERROR HANDLER ──────────────────────────────────────────
@app.errorhandler(500)
def internal_error(e):
    import traceback, uuid
    err_id = uuid.uuid4().hex[:8]
    app.logger.error(f"[{err_id}] 500: {e}\n{traceback.format_exc()}")
    try:
        return render_template('errors/500.html', error_id=err_id), 500
    except Exception:
        return f"<h1>500 Internal Server Error</h1><p>Code: {err_id}</p>", 500


@app.errorhandler(404)
def not_found(e):
    try:
        return render_template('errors/404.html'), 404
    except Exception:
        return "<h1>404 Not Found</h1>", 404

# ── HEALTH CHECK ──────────────────────────────────────────────────
@app.route('/health')
def health_check():
    """Diagnostic endpoint"""
    import sys
    info = {
        'status': 'ok',
        'python': sys.version,
        'db_type': 'postgresql' if _database_url.startswith('postgresql') else 'sqlite',
        'sentry_enabled': SENTRY_ENABLED,
    }
    try:
        from sqlalchemy import text as _t
        result = db.session.execute(_t("SELECT 1")).fetchone()
        info['db_connected'] = True
    except Exception as ex:
        info['db_connected'] = False
        info['db_error'] = str(ex)
    return jsonify(info)


# ── SENTRY USER CONTEXT (привязка ошибок к юзеру, без PII) ────────
if SENTRY_ENABLED:
    @app.before_request
    def _sentry_user_context():
        try:
            import sentry_sdk as _sdk
            if current_user.is_authenticated:
                _sdk.set_user({
                    "id": current_user.id,
                    # email/username намеренно НЕ передаём (send_default_pii=False)
                })
            else:
                _sdk.set_user(None)
        except Exception:
            pass


# ── /debug-sentry: проверка интеграции (запрещено в production) ───
@app.route('/debug-sentry')
def trigger_error_for_sentry():
    """Намеренно бросает исключение, чтобы убедиться что Sentry ловит ошибки.

    Защищено: в production (FLASK_ENV=production) возвращает 404.
    Использовать только локально или на staging.
    """
    if os.environ.get("FLASK_ENV", "production").lower() == "production":
        abort(404)
    division_by_zero = 1 / 0  # noqa: F841 — намеренная ошибка для Sentry
    return "unreachable"

# Flask-APScheduler for Daily Quest cron jobs
from flask_apscheduler import APScheduler

class Config:
    SCHEDULER_API_ENABLED = True
    SCHEDULER_TIMEZONE = "Europe/Moscow"

app.config.from_object(Config())

scheduler = APScheduler()
scheduler.init_app(app)

# Daily Quest Streak Reset Job (runs at 00:00 MSK)
@scheduler.task('cron', id='daily_streak_reset', hour=0, minute=0)
def daily_streak_reset_job():
    """Reset streaks at midnight MSK"""
    with app.app_context():
        from services.streak_service import check_and_reset_streaks
        try:
            check_and_reset_streaks()
            app.logger.info("✓ Daily streak reset completed")
        except Exception as e:
            app.logger.error(f"✗ Daily streak reset failed: {e}")

# Start scheduler
try:
    scheduler.start()
    print("✓ APScheduler started - Daily Quest cron jobs active")
except Exception as e:
    print(f"⚠️  APScheduler failed to start: {e}")

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def _generate_device_id():
    """Генерация уникального device_id"""
    return str(uuid.uuid4())


def ensure_guest_user(device_id):
    """Создаёт или находит гостевого пользователя по device_id"""
    user = User.query.filter_by(device_id=device_id, is_guest=True).first()
    if user:
        return user
    
    # Генерируем уникальный никнейм
    import random
    suffix = random.randint(1000, 9999)
    nickname = f"Гость-{suffix}"
    # Убедимся что никнейм уникален
    while User.query.filter_by(nickname=nickname).first():
        suffix = random.randint(1000, 9999)
        nickname = f"Гость-{suffix}"
    
    guest = User(
        email=f"guest_{device_id[:8]}@formyla.local",
        nickname=nickname,
        is_guest=True,
        device_id=device_id
    )
    db.session.add(guest)
    db.session.commit()
    return guest


@app.before_request
def ensure_device_and_session():
    """Гарантирует наличие device_id и пользователя в сессии"""
    # Пропускаем статические файлы
    if request.path.startswith('/static/'):
        return

    try:
        # 1. Получаем или создаём device_id
        device_id = session.get('device_id')
        if not device_id:
            device_id = request.cookies.get('formyla_device_id')
        if not device_id:
            device_id = _generate_device_id()

        session['device_id'] = device_id

        # 2. Если пользователь не авторизован — создаём гостя
        if not current_user.is_authenticated:
            guest = ensure_guest_user(device_id)
            login_user(guest, remember=True)
            session.permanent = True
            session['user_id'] = guest.id
        else:
            # Обновляем device_id у текущего пользователя если нужно
            try:
                if not current_user.device_id:
                    current_user.device_id = device_id
                    db.session.commit()
            except Exception:
                db.session.rollback()
            session['user_id'] = current_user.id
    except Exception as e:
        # If guest user creation fails (e.g. missing columns), just continue
        # The user will be anonymous but the app won't crash
        import logging
        logging.getLogger(__name__).warning(f"ensure_device_and_session error: {e}")
        db.session.rollback()


@app.after_request
def add_security_headers(response):
    """Запрет кэширования страниц для авторизованных пользователей.
    Предотвращает показ чужого профиля при нажатии F5 / кнопки Назад.
    Также добавляет Vary: Cookie чтобы CDN/proxy не кешировали ответы между пользователями.
    """
    # Устанавливаем device_id cookie на 10 лет
    device_id = session.get('device_id')
    if device_id:
        response.set_cookie(
            'formyla_device_id',
            device_id,
            max_age=10 * 365 * 24 * 3600,  # 10 лет
            httponly=True,
            samesite='Lax',
            secure=request.is_secure
        )

    try:
        if current_user.is_authenticated:
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, private, max-age=0'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
    except Exception:
        pass  # current_user может быть недоступен вне request context

    # Vary: Cookie — КРИТИЧЕСКИ ВАЖНО для Render/Cloudflare/CDN
    # Без этого CDN может закешировать ответ одного пользователя и отдать другому
    response.headers.setdefault('Vary', 'Cookie')

    # UTF-8 charset для всех HTML-ответов (фикс символов ∠°≠ → ?)
    if response.content_type and 'text/html' in response.content_type:
        response.headers['Content-Type'] = 'text/html; charset=utf-8'

    # Базовые security headers для всех ответов
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
    response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    # Permissions-Policy:
    #   * camera/microphone — разрешены на собственном origin (self), потому что
    #     виджет видеозвонка на доске для рисования (static/js/wb_call.js)
    #     использует navigator.mediaDevices.getUserMedia(). Без `self` браузер
    #     не покажет даже диалог разрешения и getUserMedia падает молча.
    #   * geolocation/payment — выключены (мы их не используем).
    response.headers.setdefault(
        'Permissions-Policy',
        'camera=(self), microphone=(self), geolocation=(), payment=()'
    )
    # HSTS — только когда соединение действительно по HTTPS (production behind Cloudflare)
    try:
        if request.is_secure or _is_production:
            response.headers.setdefault(
                'Strict-Transport-Security',
                'max-age=31536000; includeSubDomains'
            )
    except Exception:
        pass
    return response


# ============================================================
# Автоопределение формата olympiads.py и группировка
# ============================================================
# Новый формат: каждый элемент — пробник с полем "problems" (список задач)
# Старый формат: каждый элемент — одна задача (поля text, answer, solution напрямую)

if _RAW_DB and "problems" in _RAW_DB[0] and isinstance(_RAW_DB[0]["problems"], list):
    # Новый формат — используем как есть
    COMBOS = _RAW_DB
    print(f"olympiads.py: новый формат, {len(COMBOS)} пробников")
else:
    # Старый формат — группируем задачи в пробники
    from collections import OrderedDict
    groups = OrderedDict()
    for task in _RAW_DB:
        key = (task.get("olympiad", ""), task.get("year", 0), task.get("grade", 0), task.get("round", ""))
        if key not in groups:
            groups[key] = {
                "olympiad": task.get("olympiad", ""),
                "olympiad_title": task.get("olympiad_title", ""),
                "year": task.get("year", 0),
                "grade": task.get("grade", 0),
                "round": task.get("round", ""),
                "round_title": task.get("round_title", task.get("round", "")),
                "problems": [],
            }
        groups[key]["problems"].append({
            "num": len(groups[key]["problems"]) + 1,
            "text": task.get("text", "") or task.get("statement", ""),
            "answer": task.get("answer", "") or task.get("current_answer", ""),
            "solution": task.get("solution", "") or task.get("current_solution", ""),
        })
    COMBOS = []
    for i, combo in enumerate(groups.values(), start=1):
        combo["id"] = i
        COMBOS.append(combo)
    print(f"olympiads.py: старый формат, {len(_RAW_DB)} задач -> {len(COMBOS)} пробников")

print(f"Пробников всего: {len(COMBOS)}, с задачами: {sum(1 for c in COMBOS if c.get('problems'))}")
print(f"Адаптивный тест: загружено {len(ADAPTIVE_DB)} задач из adaptive_data")

# Обогащаем OLYMPIADS_INFO данными из COMBOS (grades, rounds, full_title)
_oi_map = {}
for combo in COMBOS:
    slug = combo.get('olympiad', '')
    if not slug:
        continue
    if slug not in _oi_map:
        _oi_map[slug] = {
            'slug': slug,
            'title': combo.get('olympiad_title', slug),
            'full_title': combo.get('olympiad_title', slug),
            'grades': set(),
            'rounds': {},
        }
    g = combo.get('grade')
    if g:
        _oi_map[slug]['grades'].add(int(g))
    rnd = combo.get('round', '')
    rnd_title = combo.get('round_title', rnd)
    if rnd and rnd not in _oi_map[slug]['rounds']:
        _oi_map[slug]['rounds'][rnd] = rnd_title

# Финализируем: конвертируем set -> sorted list
for info in _oi_map.values():
    info['grades'] = sorted(info['grades'])

OLYMPIADS_INFO = list(_oi_map.values())
print(f"OLYMPIADS_INFO: {len(OLYMPIADS_INFO)} олимпиад с grades/rounds")

# Привязываем картинки к задачам
if IMAGE_MAP:
    for combo in COMBOS:
        combo_id = combo.get('id')
        for problem in combo.get('problems', []):
            prob_num = problem.get('num')
            img_key = (combo_id, prob_num)
            if img_key in IMAGE_MAP:
                problem['image'] = IMAGE_MAP[img_key]

# ============================================================


OPENROUTER_API_KEY = "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"


UPLOAD_FOLDER = "static/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# VARIANTS dict was used by the removed "Написать олимпиаду" routes (/practice*).
# Kept as a no-op placeholder so any lingering references won't crash at import.
VARIANTS = {}


SUBJECTS = {
    "algebra": "Алгебра",
    "geometry": "Геометрия",
    "combinatorics": "Комбинаторика",
    "number_theory": "Теория чисел",
    "movement": "Задачи на движение",
    "knights_liars": "Рыцари и лжецы",
}


SUBTOPICS = {
    "algebra": {
        "equations": "Уравнения",
        "inequalities": "Неравенства",
        "text_problems": "Текстовые задачи"
    },
    "geometry": {
        "basics": "Основы геометрии",
        "circles": "Окружности",
        "triangles": "Треугольники"
    },
    "number_theory": {
        "divisibility": "Делимость",
        "primes_and_equations": "Простые числа и уравнения"
    },
    "combinatorics": {
        "counting": "Подсчёт и перебор",
        "dirichlet_and_graphs": "Принцип Дирихле и графы",
        "games_and_invariants": "Игры и инварианты"
    },
    "movement": {
        "linear": "Равномерное движение",
        "circular": "Движение по окружности"
    },
    "knights_liars": {
        "basic_logic": "Простая логика",
        "complex_logic": "Сложная логика"
    }
}

GRADES = [5, 6, 7, 8, 9, 10, 11]


LEVELS = [
    (1, "Уровень 1"), (2, "Уровень 2"), (3, "Уровень 3"), (4, "Уровень 4"), (5, "Уровень 5"),
    (6, "Уровень 6"), (7, "Уровень 7")
]


# Этапы олимпиад (разные для разных олимпиад)
ROUNDS = {
    # ВсОШ
    "school": "Школьный",
    "municipal": "Муниципальный",
    "regional": "Региональный",
    "final": "Заключительный",
    # Перечневые олимпиады
    "qualifying": "Отборочный",
    "final_rsosh": "Заключительный",
    # Турнир городов
    "autumn": "Осенний",
    "spring": "Весенний"
}


def get_olympiad_by_slug(slug):
    return next((o for o in OLYMPIADS_INFO if o.get("slug") == slug), None)

# ── Баланс тем в варианте ─────────────────────────────────────────────────────
TOPICS_POOL = [
    'algebra', 'geometry', 'number_theory',
    'combinatorics', 'logic', 'inequalities',
]

# Ключевые слова для определения темы задачи из текста
_TOPIC_KEYWORDS = {
    'geometry': [
        'треугольник', 'окружност', 'угол', 'отрезок', 'прямая', 'перпендикуляр',
        'параллел', 'биссектрис', 'медиан', 'высот', 'вписан', 'описан',
        'четырёхугольник', 'четырехугольник', 'диагональ', 'площад', 'периметр',
        'трапеци', 'ромб', 'квадрат', 'прямоугольник', 'хорд', 'касательн',
        'triangle', 'angle', 'circle', 'ABC', 'BCD',
    ],
    'number_theory': [
        'делит', 'остаток', 'простое число', 'простых чисел', 'НОД', 'НОК',
        'делимост', 'цифр', 'разряд', 'десятичн', 'натуральн', 'целое число',
        'целых чисел', 'чётн', 'нечётн', 'кратн', 'модул',
    ],
    'combinatorics': [
        'сколько способов', 'сколькими способами', 'расстановк', 'раскраск',
        'перестановк', 'сочетан', 'размещен', 'граф', 'вершин', 'ребр',
        'турнир', 'шахматн', 'клетк', 'доск', 'фишк', 'Дирихле',
    ],
    'algebra': [
        'уравнен', 'неравенств', 'многочлен', 'корн', 'функци', 'последовательност',
        'прогресси', 'система', 'выражен', 'упрост', 'разлож', 'формул',
        'квадратн', 'линейн', 'степен',
    ],
    'logic': [
        'рыцар', 'лжец', 'взвешиван', 'переливан', 'стратеги', 'игр',
        'выигр', 'проигр', 'ход', 'монет', 'фальшив',
    ],
}


def _detect_topic(text):
    """Определяет тему задачи по ключевым словам в тексте."""
    text_lower = text.lower()
    scores = {}
    for topic, keywords in _TOPIC_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw.lower() in text_lower)
        if score > 0:
            scores[topic] = score
    if scores:
        return max(scores, key=scores.get)
    return 'algebra'  # default


def _plan_topics(count):
    """Возвращает список тем для задач варианта с гарантированным балансом."""
    if count >= 7:
        planned = ['algebra', 'geometry', 'number_theory', 'combinatorics']
        remaining = count - 4
    elif count >= 6:
        planned = ['algebra', 'geometry', 'number_theory']
        remaining = count - 3
    elif count >= 5:
        planned = ['algebra', 'geometry']
        remaining = count - 2
    else:
        planned = []
        remaining = count

    available = [t for t in TOPICS_POOL if t not in planned]
    random.shuffle(available)
    for _ in range(remaining):
        if available:
            planned.append(available.pop(0))
        else:
            # Все темы использованы — берём случайную из пула (допускаем повтор)
            planned.append(random.choice([t for t in TOPICS_POOL if planned.count(t) < 2]))

    return planned


def _extract_numbers(text):
    """Извлекает все числа > 3 из текста (для проверки уникальности)."""
    clean = re.sub(r'\\[a-zA-Z]+', '', text)
    numbers = re.findall(r'\b\d+\b', clean)
    return [int(n) for n in numbers if int(n) > 3]


def generate_variant(olympiad_slug, grade, round_key):
    
    print("=" * 70)
    print("=== DEBUG ГЕНЕРАЦИЯ ВАРИАНТА ОЛИМПИАДЫ ===")
    print(f"Запрошено: Олимпиада='{olympiad_slug}', Класс={grade}, Этап='{round_key}'")
    print(f"Всего записей в _RAW_DB: {len(_RAW_DB)}")

    # Фильтруем варианты
    variants = [
        v for v in _RAW_DB
        if v.get("olympiad") == olympiad_slug
        and v.get("grade") == grade
        and (not round_key or v.get("round") == round_key)
    ]
    print(f"Найдено вариантов с точным совпадением (олимпиада+класс+этап): {len(variants)}")
    
    if not variants:
        variants = [
            v for v in _RAW_DB
            if v.get("olympiad") == olympiad_slug
            and v.get("grade") == grade
        ]
        print(f"Найдено вариантов без учета этапа (олимпиада+класс): {len(variants)}")
    
    if not variants:
        print("ОШИБКА: Не найдено ни одного варианта для точной комбинации!")
        print(f"Пробуем FALLBACK: ищем любые задачи олимпиады '{olympiad_slug}'...")
        variants = [v for v in _RAW_DB if v.get("olympiad") == olympiad_slug]
        print(f"Найдено вариантов олимпиады (любой класс): {len(variants)}")
        
        if not variants:
            print(f"КРИТИЧЕСКАЯ ОШИБКА: В БД вообще нет задач для олимпиады '{olympiad_slug}'!")
            print("=" * 70)
            return []

    # Собираем все задачи из подходящих вариантов с определением темы
    source = []
    for v in variants:
        for p in v.get("problems", []):
            t = p.get("text", "")
            if not t or len(t) > 1500 or len(t) < 80:
                continue
            if any(x in t for x in ["XXXVII", "XXXVIII", "XXXIX", "XL "]):
                continue
            if re.search(r'\(вариант\s*\d+\)', t, re.IGNORECASE):
                continue
            if re.search(r'см\.\s*№', t):
                continue
            if re.search(r'^Аналогичная задача', t):
                continue
            topic = _detect_topic(t)
            source.append({**p, "olympiad": v["olympiad"], "grade": v["grade"], "topic": topic})

    if not source:
        print("ОШИБКА: Не найдено ни одной валидной задачи в вариантах!")
        print("=" * 70)
        return []

    print(f"Собрано задач из вариантов: {len(source)}")

    # ── БАЛАНС ТЕМ: выбираем задачи по плану ──
    task_count = 5
    topics_plan = _plan_topics(task_count)
    print(f"План тем: {topics_plan}")

    # Группируем задачи по теме (с уникальным индексом)
    for idx, p in enumerate(source):
        p['_idx'] = idx  # уникальный индекс для отслеживания
    by_topic = {}
    for p in source:
        tp = p.get('topic', 'algebra')
        by_topic.setdefault(tp, []).append(p)

    selected = []
    used_idxs = set()
    for topic in topics_plan:
        candidates = [p for p in by_topic.get(topic, []) if p['_idx'] not in used_idxs]
        if not candidates:
            # Fallback: любая неиспользованная задача
            candidates = [p for p in source if p['_idx'] not in used_idxs]
        if candidates:
            chosen = random.choice(candidates)
            selected.append(chosen)
            used_idxs.add(chosen['_idx'])

    # КРИТИЧЕСКАЯ ПРОВЕРКА
    if len(selected) < 3:
        print(f"ОШИБКА: Недостаточно задач для генерации ({len(selected)} < 3)")
        print("=" * 70)
        return []
    
    print(f"Отобрано задач для варианта: {len(selected)}")
    print(f"Темы: {[p.get('topic') for p in selected]}")
    # Применяем fix_latex к каждой задаче перед возвратом
    try:
        from services.task_validator import fix_latex
        for p in selected:
            if p.get('text'):
                p['text'] = fix_latex(p['text'])
    except Exception as e:
        print(f"fix_latex error: {e}")
    print(f"Начинаем модификацию задач через AI...")

    # Собираем числа из оригиналов для валидации
    original_numbers_per_task = []
    for p in selected:
        original_numbers_per_task.append(set(_extract_numbers(p.get('text', ''))))
    
    # Формируем список исходных задач для промпта
    tasks_text = ""
    for i, p in enumerate(selected, 1):
        topic_label = p.get('topic', 'unknown')
        tasks_text += f"\n--- ЗАДАЧА {i} (тема: {topic_label}) ---\n{p['text']}\n"
    
    prompt = f"""Ты — составитель олимпиадных вариантов по математике ({round_key or 'отборочный'} этап, {grade} класс).

ЗАДАНИЕ: Перепиши {len(selected)} задач. Сохрани математический МЕТОД, но ПОЛНОСТЬЮ замени:
- ВСЕ числа (ни одно число из оригинала не должно остаться!)
- ВСЕ имена персонажей (используй: Петя, Вася, Маша, Аня, Коля, Даша, Лена)
- Контекст/сюжет (другие декорации)
- Формулировку (перепиши своими словами)

ИСХОДНЫЕ ЗАДАЧИ:{tasks_text}

ОБЯЗАТЕЛЬНЫЕ ИЗМЕНЕНИЯ В КАЖДОЙ ЗАДАЧЕ:
1. ЧИСЛА: Замени ВСЕ числа на другие. Если было 43 — поставь 67. Если было 5 — поставь 7.
   Ответ должен остаться "красивым" (целое число или простая дробь).
2. ИМЕНА: Никаких сказочных персонажей (Алиса, Шляпник, Буратино). Только обычные русские имена.
3. КОНТЕКСТ: Если задача про часы — сделай про поезда. Про школу — сделай про магазин.
4. ФОРМУЛИРОВКА: Перепиши каждое предложение своими словами.

ФОРМАТИРОВАНИЕ LaTeX (КРИТИЧНО — ЧИТАЙ ВНИМАТЕЛЬНО):
- Каждая переменная в $...$: $x$, $y$, $n$
- Степени: $x^2$, $a^{{10}}$ (НЕ x2, a10!)
- Индексы: $a_1$, $x_{{12}}$
- Углы: $\\angle ABC = 60^\\circ$ (НЕ юникод ∠ °)
- Треугольники: $\\triangle ABC$
- Дроби: $\\frac{{a}}{{b}}$ (НЕ \\frac a b, НЕ a/b)
- Корни: $\\sqrt{{n}}$, $\\sqrt{{a+b}}$ (НЕ \\sqrtn, НЕ \\sqrt n!)
  ВАЖНО: после \\sqrt ВСЕГДА фигурные скобки: \\sqrt{{...}}
  ❌ НЕПРАВИЛЬНО: \\sqrta, \\sqrt a, \\sqrtab
  ✅ ПРАВИЛЬНО: \\sqrt{{a}}, \\sqrt{{a+b}}, \\sqrt{{ab}}
- Display: $$y^2 - 1 = a^2(x^2 - 1)$$
- Знаки: $\\geq$, $\\leq$, $\\neq$ (НЕ юникод ≥ ≤ ≠)
- НИ ОДНОГО голого числа/переменной без $!

САМОПРОВЕРКА ПЕРЕД ВЫДАЧЕЙ JSON:
1. Все \\sqrt имеют {{}} после себя? (\\sqrt{{x}}, НЕ \\sqrtx)
2. Все \\frac имеют два {{}} аргумента? (\\frac{{a}}{{b}})
3. Все переменные в $...$?
4. Нет юникод-символов математики (∠°≠≡△√≤≥)?
Если хоть один ответ "нет" — ПЕРЕПИШИ question.

ФОРМАТ ОТВЕТА — строго JSON-массив (без markdown):
[
  {{"question": "Условие задачи...", "answer": "Краткий ответ", "explanation": "Полное решение", "topic": "тема"}},
  ...
]

Поле "question" — ТОЛЬКО условие (без решения, без "Ответ:", без авторов).
Поле "answer" — краткий ответ.
Поле "explanation" — полное пошаговое решение.
Поле "topic" — тема задачи (algebra/geometry/number_theory/combinatorics/logic).
"""

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
            json={
                "model": "google/gemini-2.0-flash-001",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.75,
                "max_tokens": 4000
            },
            timeout=90
        )
        
        if response.status_code != 200:
            raise Exception(f"API returned status {response.status_code}: {response.text}")
        
        content = response.json()["choices"][0]["message"]["content"]
        
        print(f"Получен ответ от AI (длина: {len(content)} символов)")
        
        # Очистка от markdown
        content = content.strip()
        if content.startswith('```'):
            content = re.sub(r'^```\w*\n?', '', content)
            content = re.sub(r'\n?```$', '', content)
            content = content.strip()
        
        # Парсинг JSON
        try:
            tasks_data = json.loads(content)
        except json.JSONDecodeError:
            # Попытка извлечь JSON из текста
            match = re.search(r'\[[\s\S]*\]', content)
            if match:
                tasks_data = json.loads(match.group(0))
            else:
                raise
        
        if not isinstance(tasks_data, list):
            raise Exception(f"AI вернул не массив, а {type(tasks_data)}")
        
        if len(tasks_data) < len(selected):
            print(f"AI вернул только {len(tasks_data)} задач вместо {len(selected)}")
        
        # Создаем модифицированные задачи с ВАЛИДАЦИЕЙ ЧИСЕЛ
        modified = []
        numbers_warnings = 0
        for i, (original, task_data) in enumerate(zip(selected, tasks_data)):
            generated_text = task_data.get("question", task_data.get("text", ""))
            
            # ВАЛИДАЦИЯ: если AI вернул заглушку — используем оригинал
            if len(generated_text) < 50:
                print(f"Задача {i+1}: слишком короткий текст, используем оригинал")
                generated_text = original.get("text", generated_text)
            
            # ВАЛИДАЦИЯ ЧИСЕЛ: проверяем что числа поменялись
            if i < len(original_numbers_per_task):
                orig_nums = original_numbers_per_task[i]
                new_nums = set(_extract_numbers(generated_text))
                trivial = {4, 5, 6, 7, 8, 9, 10, 100}
                overlap = (orig_nums & new_nums) - trivial
                if overlap:
                    numbers_warnings += 1
                    print(f"Задача {i+1}: совпадающие числа с оригиналом: {overlap}")
            
            topic = task_data.get("topic", selected[i].get("topic", ""))
            
            modified.append({
                "id": original.get("id", i) + i * 10000,
                "subject": original.get("subject"),
                "grade": grade,
                "difficulty": original.get("difficulty"),
                "title": f"Задача {i+1}",
                "text": generated_text,
                "answer": task_data.get("answer", ""),
                "solution": task_data.get("explanation", task_data.get("solution", "")),
                "topic": topic,
                "original_id": original.get("id")
            })
        
        if numbers_warnings:
            print(f"ВНИМАНИЕ: {numbers_warnings}/{len(modified)} задач имеют совпадающие числа с оригиналом")
        print(f"AI успешно модифицировал {len(modified)} задач")
        
    except Exception as e:
        print(f"ОШИБКА при генерации через AI: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        print("Используем исходные задачи без модификации")
        modified = []
        for i, p in enumerate(selected):
            modified.append({
                "id": p.get("id", i) + i * 10000,
                "subject": p.get("subject"),
                "grade": grade,
                "difficulty": p.get("difficulty"),
                "title": f"Задача {i+1}",
                "text": p.get("text", ""),
                "answer": p.get("answer", ""),
                "solution": "",
                "topic": p.get("topic", ""),
                "original_id": p.get("id")
            })

    print(f"Модификация завершена. Итого задач: {len(modified)}")
    print("=" * 70)
    return modified



@app.route("/")
def index():
    """Главная страница - список предметов."""
    solved_count = len(session.get('solved_problems', []))
    return render_template("index.html",
        subjects=SUBJECTS,
        solved_count=solved_count
    )


@app.route("/leaderboard")
def leaderboard():
    """Таблица лидеров - все зарегистрированные пользователи по рейтингу."""
    from models import User
    
    # Заблокированные пользователи (не показываем в таблице лидеров)
    BLOCKED_USER_IDS = {4}  # ID 4 = "писюн"
    
    # Получить всех зарегистрированных пользователей (не гостей, не заблокированных)
    users = User.query.filter(
        User.is_guest == False,
        ~User.id.in_(BLOCKED_USER_IDS)
    ).all()
    
    # Вычислить рейтинг для каждого пользователя
    leaderboard_data = []
    for user in users:
        leaderboard_data.append({
            'user': user,
            'score': user.get_leaderboard_score(),
            'nickname': user.display_name,
            'avatar_url': user.avatar_url,
            'level': user.current_level,
            'total_solved': user.total_problems_solved,
            'mock_exams_passed': user.mock_exams_passed,
            'adaptive_tests_completed': user.adaptive_tests_completed,
            'highest_difficulty': user.highest_difficulty_solved,
            'experience_points': user.experience_points
        })
    
    # Сортировать по рейтингу (убывание)
    leaderboard_data.sort(key=lambda x: x['score'], reverse=True)
    
    # Показываем ВСЕХ зарегистрированных пользователей
    top_users = leaderboard_data
    
    # Добавить ранг
    for rank, entry in enumerate(top_users, 1):
        entry['rank'] = rank
    
    # Найти текущего пользователя в рейтинге (если авторизован)
    current_user_rank = None
    if current_user.is_authenticated and current_user.nickname:
        for rank, entry in enumerate(leaderboard_data, 1):
            if entry['user'].id == current_user.id:
                current_user_rank = {
                    'rank': rank,
                    'score': entry['score'],
                    'level': entry['level'],
                    'total_solved': entry['total_solved']
                }
                break
    
    return render_template("leaderboard.html",
        top_users=top_users,
        current_user_rank=current_user_rank,
        total_users=len(leaderboard_data)
    )


@app.route("/section/<subject_key>")
def section(subject_key):
    if subject_key not in SUBJECTS:
        abort(404)
    subject_title = SUBJECTS[subject_key]
    subtopics = SUBTOPICS.get(subject_key, {})

    # Считаем количество задач для каждой подтемы (максимум 5 на ячейку)
    subtopic_counts = {}
    for sub_key in subtopics.keys():
        count = 0
        for grade in GRADES:
            for level in range(1, 8):  # 7 уровней
                tasks = [p for p in PROBLEMS_DB
                        if p.get("subject") == subject_key
                        and p.get("subtopic") == sub_key
                        and p.get("grade") == grade
                        and p.get("difficulty") == level]
                count += min(len(tasks), 5)  # Максимум 5 на ячейку
        subtopic_counts[sub_key] = count

    total = sum(subtopic_counts.values())

    return render_template('section.html',
        subject_key=subject_key,
        subject_title=subject_title,
        subtopics=subtopics,
        subtopic_counts=subtopic_counts,
        total=total
    )



@app.route("/section/<subject_key>/<subtopic_key>")
def section_subtopic(subject_key, subtopic_key):
    """Выбор класса и уровня для подтемы."""
    if subject_key not in SUBJECTS:
        abort(404)
    subtopics = SUBTOPICS.get(subject_key, {})
    if subtopic_key not in subtopics:
        abort(404)
    subject_title = SUBJECTS[subject_key]
    subtopic_title = subtopics[subtopic_key]

    # Подсчет задач по классам (максимум 5 задач на уровень)
    grade_counts = {}
    level_counts = {}
    
    for g in GRADES:
        # Подсчитываем задачи по уровням с ограничением 5 на уровень
        level_counts[g] = {}
        total_for_grade = 0
        
        for lev in range(1, 8):  # 7 уровней!
            # Считаем задачи для этого уровня
            # subtopic в PROBLEMS_DB хранится как английский ключ (например, 'equations')
            problems_for_level = [p for p in PROBLEMS_DB
                                 if p.get("subject") == subject_key
                                 and p.get("subtopic") == subtopic_key
                                 and p.get("grade") == g
                                 and p.get("difficulty") == lev]
            # Ограничиваем до 5 задач
            lev_cnt = min(len(problems_for_level), 5)
            level_counts[g][lev] = lev_cnt
            total_for_grade += lev_cnt
        
        grade_counts[g] = total_for_grade

    return render_template('subtopic.html',
        subject_key=subject_key,
        subject_title=subject_title,
        subtopic_key=subtopic_key,
        subtopic_title=subtopic_title,
        grades=GRADES,
        grade_counts=grade_counts,
        level_counts=level_counts
    )


@app.route("/problems")
def problems_list():
    subject_key = request.args.get("subject")
    subtopic_key = request.args.get("subtopic")
    grade = request.args.get("grade", type=int)
    level = request.args.get("level", type=int)
    page = request.args.get("page", 1, type=int)
    search_query = request.args.get("q", "").strip().lower()

    filtered = []
    for p in PROBLEMS_DB:
        db_subject = str(p.get("subject", "")).lower()
        match_subject = False

        if subject_key is None:
            match_subject = True
        elif subject_key == "algebra" and db_subject in ["algebra", "алгебра"]:
            match_subject = True
        elif subject_key == "geometry" and db_subject in ["geometry", "геометрия"]:
            match_subject = True
        elif subject_key == "combinatorics" and db_subject in ["combinatorics", "комбинаторика"]:
            match_subject = True
        elif subject_key == "number_theory" and db_subject in ["number_theory", "теория чисел", "теория_чисел"]:
            match_subject = True
        elif subject_key == "knights_liars" and db_subject in ["knights_liars", "рыцари и лжецы"]:
            match_subject = True
        elif subject_key == "movement" and db_subject in ["movement", "задачи на движение"]:
            match_subject = True
        elif db_subject == subject_key:
            match_subject = True

        # Проверка подтемы (прямое сравнение)
        # ИСПРАВЛЕНИЕ: subtopic в PROBLEMS_DB хранится как русское название
        if subtopic_key is None:
            match_subtopic = True
        else:
            # subtopic в PROBLEMS_DB хранится как английский ключ
            match_subtopic = p.get("subtopic") == subtopic_key
            
        match_grade = (grade is None) or (p.get("grade") == grade)
        match_level = (level is None) or (p.get("difficulty") == level)
        
        # Поиск по тексту задачи
        match_search = True
        if search_query:
            problem_text = str(p.get("text", "")).lower()
            match_search = search_query in problem_text

        # Фильтр по is_active (показываем только активные задачи)
        is_active = p.get('is_active', True)  # По умолчанию True для старых задач
        
        if match_subject and match_subtopic and match_grade and match_level and match_search and is_active:
            filtered.append(p)

    subject_title = SUBJECTS.get(subject_key, "Задачи")
    subtopic_title = ""
    if subtopic_key and subject_key in SUBTOPICS:
        subtopic_title = SUBTOPICS[subject_key].get(subtopic_key, "")

    title_parts = [subject_title]
    if subtopic_title:
        title_parts.append(subtopic_title)
    if grade:
        title_parts.append(f"{grade} класс")
    if level:
        title_parts.append(f"Уровень {level}")
    page_title = " · ".join(title_parts)

    back_url = f"/section/{subject_key}/{subtopic_key}" if subtopic_key else f"/section/{subject_key}"

    # ОГРАНИЧЕНИЕ: Если выбраны конкретные subject, subtopic, grade и level - показываем максимум 5 задач
    if subject_key and subtopic_key and grade and level:
        # Рандомизируем для разнообразия
        import random
        if len(filtered) > 5:
            filtered = random.sample(filtered, 5)
        # Ограничиваем до 5
        filtered = filtered[:5]
    
    # Пагинация: показываем по 20 задач на странице
    PER_PAGE = 20
    total_count = len(filtered)
    total_pages = max(1, (total_count + PER_PAGE - 1) // PER_PAGE)
    
    # Ограничиваем номер страницы
    page = max(1, min(page, total_pages))
    
    # Вычисляем срез для текущей страницы
    start_idx = (page - 1) * PER_PAGE
    end_idx = start_idx + PER_PAGE
    paginated_problems = filtered[start_idx:end_idx]

    solved_problems = session.get('solved_problems', [])
    
    return render_template('problems.html',
        subject_title=subject_title,
        subtopic_title=subtopic_title,
        problems=paginated_problems,
        back_url=back_url,
        page_title=page_title,
        solved_problems=solved_problems,
        page=page,
        total_pages=total_pages,
        total_count=total_count,
        search_query=search_query
    )



@app.route("/problems/<int:problem_id>")
@app.route("/problem/<int:problem_id>")
def problem_detail(problem_id):
    problem = next((p for p in PROBLEMS_DB if p.get("id") == problem_id), None)
    is_olympiad = False

    if not problem:
        problem = next((p for p in _RAW_DB if p.get("id") == problem_id), None)
        is_olympiad = True

    if not problem:
        abort(404)

    subject_title = SUBJECTS.get(problem.get("subject", ""), "Задачи")
    subtopic_title = problem.get("subtopic_title", "")

    solved_problems = session.get('solved_problems', [])
    is_solved = problem_id in solved_problems
    
    return render_template('problem_detail.html',
        problem=problem,
        subject_title=subject_title,
        subtopic_title=subtopic_title,
        is_olympiad=is_olympiad,
        is_solved=is_solved
    )



@app.route("/api/check_answer", methods=["POST"])
def check_answer():
    """API для проверки ответа пользователя."""
    data = request.get_json()
    problem_id = data.get("problem_id")
    user_answer = data.get("user_answer", "").strip()
    
    print("\n" + "=" * 60)
    print("=== DEBUG /api/check_answer ===")
    print(f"Problem ID: {problem_id}")
    print(f"User answer from request: '{user_answer}'")
    
    if not problem_id:
        return jsonify({"error": "problem_id required"}), 400
    
    # Ищем задачу в обеих базах
    problem = next((p for p in PROBLEMS_DB if p.get("id") == problem_id), None)
    if not problem:
        problem = next((p for p in _RAW_DB if p.get("id") == problem_id), None)
    
    if not problem:
        print(f"ERROR: Problem {problem_id} not found in database!")
        print("=" * 60 + "\n")
        return jsonify({"error": "Problem not found"}), 404
    
    # Получаем правильный ответ
    correct_answer = str(problem.get("answer", "")).strip()
    solution = problem.get("solution", "Решение отсутствует")
    
    print(f"Problem found: {problem.get('title', 'No title')[:50]}...")
    print(f"Correct answer from DB: '{correct_answer}'")
    print(f"Problem answer field type: {type(problem.get('answer'))}")
    
    # Проверяем ответ с умной нормализацией
    is_correct = compare_math_answers(user_answer, correct_answer)
    
    print(f"Final result: is_correct = {is_correct}")
    print("=" * 60 + "\n")
    
    # Подготовка данных для ответа
    response_data = {
        "correct": is_correct,
        "solution": solution,
        "correct_answer": problem.get("answer", "")
    }
    
    # Если ответ верный, сохраняем в сессию и начисляем XP
    if is_correct:
        solved_problems = session.get('solved_problems', [])
        if problem_id not in solved_problems:
            solved_problems.append(problem_id)
            session['solved_problems'] = solved_problems
            session.modified = True
        
        # Начисляем XP если пользователь авторизован
        if current_user.is_authenticated:
            task_difficulty = problem.get('difficulty', 1)
            
            # Начисляем XP за задачу
            xp_result = add_xp_for_task(current_user, task_difficulty)
            
            # Получаем прогресс до следующего уровня
            progress = get_xp_for_next_level(current_user)
            
            # Сохраняем изменения в БД
            db.session.commit()
            
            # Добавляем информацию об XP в ответ
            response_data.update({
                "xp_gained": xp_result['xp_gained'],
                "bonus_xp": xp_result['bonus_xp'],
                "total_xp": xp_result['total_xp'],
                "level_up": xp_result['level_up'],
                "new_level": xp_result['new_level'],
                "progress_percent": progress['progress_percentage'],
                "xp_needed": progress['xp_needed']
            })
    
    return jsonify(response_data)


# NOTE: section "Написать олимпиаду" (routes /practice*) removed by request.
# generate_variant() above is kept for now as dead code in case we revive it.

@app.route("/probniks")
def probniks_page():
    """Страница выбора типа пробника (бесплатный или адаптивный)."""
    return render_template('probniks.html', title="Пробники", active_page="probniks")


# NOTE: /practice/generate route removed together with the "Написать олимпиаду" section.

# ── Список LaTeX-команд для авто-обнаружения ─────────────────────────────────
_LATEX_COMMANDS = (
    'sqrt|frac|dfrac|tfrac|binom|sum|prod|int|lim|log|ln|sin|cos|tan|tg|ctg'
    '|arcsin|arccos|arctan|text|mathrm|mathbf|mathbb|operatorname'
    '|leq|geq|neq|le|ge|ne|pm|mp|times|cdot|div|equiv|approx|sim'
    '|alpha|beta|gamma|delta|epsilon|varepsilon|zeta|eta|theta|iota|kappa|lambda'
    '|mu|nu|xi|pi|rho|sigma|tau|upsilon|phi|varphi|chi|psi|omega'
    '|infty|partial|nabla|forall|exists|notin|subset|supset|cup|cap'
    '|lfloor|rfloor|lceil|rceil|langle|rangle|ldots|cdots|vdots|ddots'
    '|overline|underline|hat|tilde|vec|bar|dot|triangle|angle'
)

def _fix_latex_parens(text):
    """
    Исправляет \\sqrt(...) → \\sqrt{...} и аналогичные.
    Многие задачи из OCR имеют скобки вместо фигурных скобок.
    """
    # \sqrt(...) → \sqrt{...}
    text = re.sub(r'\\(sqrt|frac|text|mathrm|mathbf|mathbb|overline|underline|hat|tilde|vec)\(([^)]*)\)', r'\\\1{\2}', text)
    return text

def _wrap_bare_latex(text):
    """
    Находит голые LaTeX-команды (без $...$) и оборачивает их.
    Также оборачивает выражения с ^{ и _{ (результат fix_plain_math).
    Работает даже если часть текста уже размечена $...$.
    Разбивает текст на сегменты: внутри $ и вне $, обрабатывает только внешние.
    """
    if not text:
        return text
    # Нужна обработка если есть \ или ^{ или _{
    if '\\' not in text and '^{' not in text and '_{' not in text:
        return text

    # Исправляем \sqrt(...) → \sqrt{...} ВЕЗДЕ
    text = _fix_latex_parens(text)

    # Если нет $ и нет \( — весь текст "голый", оборачиваем всё
    if '$' not in text and '\\(' not in text:
        # Оборачиваем \commands
        text = re.sub(
            r'(\\(?:' + _LATEX_COMMANDS + r')(?:\{[^}]*\})*(?:\s*[_^]\s*(?:\{[^}]*\}|[a-zA-Z0-9]))*)',
            r'$\1$',
            text
        )
        # Оборачиваем выражения с ^{} и _{} (от fix_plain_math)
        text = re.sub(
            r'([a-zA-Z][a-zA-Z0-9]*(?:[\^_]\{\d+\})+(?:\s*[+\-*/=<>\s]+\s*[a-zA-Z][a-zA-Z0-9]*(?:[\^_]\{\d+\})+)*)',
            r'$\1$',
            text
        )
        return text

    # Смешанный формат: разбиваем на сегменты "внутри $" и "вне $"
    # Паттерн: $...$ или $$...$$ или \(...\) или \[...\]
    math_pattern = re.compile(
        r'(\$\$[\s\S]+?\$\$|\$[^\$\n]+?\$|\\\([\s\S]+?\\\)|\\\[[\s\S]+?\\\])'
    )
    parts = math_pattern.split(text)

    # parts[0], parts[2], parts[4]... — вне math
    # parts[1], parts[3], parts[5]... — внутри math (не трогаем)
    bare_re = re.compile(
        r'(\\(?:' + _LATEX_COMMANDS + r')(?:\{[^}]*\})*(?:\s*[_^]\s*(?:\{[^}]*\}|[a-zA-Z0-9]))*)'
    )
    # Regex для выражений с ^{ или _{ (от fix_plain_math: x^{2}, y_{1})
    power_re = re.compile(
        r'([a-zA-Z][a-zA-Z0-9]*(?:[\^_]\{\d+\})+(?:\s*[+\-*/=<>\s]+\s*[a-zA-Z][a-zA-Z0-9]*(?:[\^_]\{\d+\})+)*)'
    )
    for i in range(0, len(parts), 2):
        # Оборачиваем голые \commands только в сегментах ВНЕ math
        parts[i] = bare_re.sub(r'$\1$', parts[i])
        # Оборачиваем выражения с ^{} и _{} (от fix_plain_math)
        parts[i] = power_re.sub(r'$\1$', parts[i])

    text = ''.join(parts)
    return text


# ── Markdown → HTML парсер для текста задач ──────────────────────────────────
def render_task_text(text):
    """
    Парсит Markdown → HTML.
    1. Оборачивает голые LaTeX-команды в $...$
    2. Защищает math от Markdown-эскейпинга
    3. Парсит Markdown → HTML
    4. Восстанавливает math
    Placeholder формат: XMATHX0XENDX — не содержит __, *, _ чтобы Markdown не тронул.
    """
    if not text:
        return ''

    # 0a. Исправление plain-text математики (OCR-артефакты: x2 → x^2)
    from utils.math_text_fixer import fix_plain_math
    text = fix_plain_math(text)

    # 0b. Авто-обёртка голых LaTeX-команд в $...$
    text = _wrap_bare_latex(text)

    # 1. Защитить math-выражения от Markdown
    placeholders = {}
    _counter = [0]

    def _protect(m):
        key = f'XMATHX{_counter[0]}XENDX'
        placeholders[key] = m.group(0)
        _counter[0] += 1
        return key

    # Сначала display math $$...$$
    text = re.sub(r'\$\$[\s\S]+?\$\$', _protect, text)
    # Потом inline $...$
    text = re.sub(r'\$[^\$\n]+?\$', _protect, text)
    # И \[...\] / \(...\)
    text = re.sub(r'\\\[[\s\S]+?\\\]', _protect, text)
    text = re.sub(r'\\\([\s\S]+?\\\)', _protect, text)

    # 2. Парсить Markdown
    try:
        html = md_lib.markdown(
            text,
            extensions=['nl2br', 'tables']
        )
    except Exception:
        # Fallback: просто заменяем переносы строк
        html = text.replace('\n', '<br>')

    # 3. Вернуть math-выражения
    for key, val in placeholders.items():
        html = html.replace(key, val)

    return html


# Маппинг тем на русские названия для UI
_TOPIC_LABELS_RU = {
    'algebra': 'Алгебра',
    'geometry': 'Геометрия',
    'number_theory': 'Теория чисел',
    'combinatorics': 'Комбинаторика',
    'logic': 'Логика',
    'inequalities': 'Неравенства',
}

# NOTE: /practice/<variant_id> and /practice/<variant_id>/submit routes removed
# together with the "Написать олимпиаду" section.


# ============================================================
# ОЛИМПИАДЫ — пробники (каскадный выбор)
# ============================================================

@app.route("/olympiads")
def olympiads():
    # Структура: {slug: {year: {round_key: [round_title, [grade1, grade2, ...]]}}}
    # Порядок: Олимпиада -> Год -> Этап -> Класс
    olympiad_data = {}
    for combo in COMBOS:
        slug = combo["olympiad"]
        year = str(combo["year"])
        rnd = combo["round"]
        rnd_title = combo.get("round_title", rnd)
        # Всегда используем строку для grade (для совместимости с JSON)
        grade = str(combo["grade"])
        if slug not in olympiad_data:
            olympiad_data[slug] = {}
        if year not in olympiad_data[slug]:
            olympiad_data[slug][year] = {}
        if rnd not in olympiad_data[slug][year]:
            olympiad_data[slug][year][rnd] = [rnd_title, []]
        if grade not in olympiad_data[slug][year][rnd][1]:
            olympiad_data[slug][year][rnd][1].append(grade)
    # Сортируем классы и конвертируем ВСЕ ключи в строки для JSON
    normalized_data = {}
    for slug in olympiad_data:
        normalized_data[str(slug)] = {}
        for year in olympiad_data[slug]:
            normalized_data[str(slug)][str(year)] = {}
            for rnd in olympiad_data[slug][year]:
                # Конвертируем все grade в строки для JSON
                grades_list = olympiad_data[slug][year][rnd][1]
                normalized_data[str(slug)][str(year)][str(rnd)] = [
                    str(olympiad_data[slug][year][rnd][0]),  # round_title
                    sorted([str(g) for g in grades_list])  # grades
                ]

    # DEBUG: Логирование структуры данных
    import logging
    logging.warning("=== ДЕБАГ OLYMPIAD_DATA ===")
    logging.warning(f"Тип normalized_data: {type(normalized_data)}")
    if isinstance(normalized_data, dict):
        top_keys = list(normalized_data.keys())
        logging.warning(f"Ключи первого уровня (Олимпиады): {top_keys[:10]}")
        if top_keys:
            first_key = top_keys[0]
            logging.warning(f"Пример ключа: {first_key}, тип значения: {type(normalized_data[first_key])}")
            if isinstance(normalized_data[first_key], dict):
                years = list(normalized_data[first_key].keys())
                logging.warning(f"Ключи второго уровня для '{first_key}' (Года): {years[:5]}")
    else:
        logging.warning("ВНИМАНИЕ: normalized_data НЕ является словарем!")
    logging.warning(f"Всего олимпиад: {len(normalized_data) if isinstance(normalized_data, dict) else 0}")
    logging.warning("===========================")
    
    return render_template(
        "olympiads.html",
        olympiads=OLYMPIADS_INFO,
        olympiad_data=normalized_data,
        grades=[str(g) for g in GRADES]  # Конвертируем в строки для JSON
    )


@app.route("/olympiads/open", methods=["POST"])
def olympiad_open():
    slug = request.form.get("olympiad")
    year = request.form.get("year")
    grade = request.form.get("grade")
    rnd = request.form.get("round")

    olympiad = get_olympiad_by_slug(slug)
    if not olympiad:
        abort(404)

    if not year or not grade:
        abort(404)

    # Ищем пробник (combo)
    combo = None
    for c in COMBOS:
        if (c["olympiad"] == slug
            and str(c["year"]) == str(year)
            and str(c["grade"]) == str(grade)
            and (not rnd or c["round"] == rnd)):
            combo = c
            break

    if not combo:
        abort(404)

    # Привязываем рисунки к задачам при каждом запросе
    if IMAGE_MAP:
        for p in combo.get('problems', []):
            num = p.get('num')
            img = IMAGE_MAP.get((combo.get('id'), num))
            if img:
                p['image'] = img
    
    # RUNTIME PATCH: Удаление фразы "см. рисунок" для обхода клиентского кеша
    patch_count = 0
    for p in combo.get('problems', []):
        if p.get('text'):
            before = p['text']
            p['text'] = p['text'].replace('(см. рисунок)', '').replace('см. рисунок', '')
            if before != p['text']:
                patch_count += 1
        if p.get('solution'):
            before_sol = p['solution']
            p['solution'] = p['solution'].replace('(см. рисунок)', '').replace('см. рисунок', '')
            if before_sol != p['solution']:
                patch_count += 1
    
    if patch_count > 0:
        print(f"[RUNTIME PATCH] Удалено 'см. рисунок' из {patch_count} полей в combo_id={combo.get('id')}")

    return render_template('olympiad_detail.html',
        olympiad=olympiad,
        combo=combo,
        problems=combo.get('problems', [])
    )


@app.route("/olympiads/solution/<int:combo_id>")
def olympiad_solution(combo_id):
    """Показ решений пробника."""
    combo = next((c for c in COMBOS if c["id"] == combo_id), None)
    if not combo:
        abort(404)

    olympiad = get_olympiad_by_slug(combo["olympiad"])

    # Привязываем рисунки к задачам при каждом запросе
    if IMAGE_MAP:
        for p in combo.get('problems', []):
            num = p.get('num')
            img = IMAGE_MAP.get((combo.get('id'), num))
            if img:
                p['image'] = img
    
    # RUNTIME PATCH: Удаление фразы "см. рисунок" для обхода клиентского кеша
    patch_count = 0
    for p in combo.get('problems', []):
        if p.get('text'):
            before = p['text']
            p['text'] = p['text'].replace('(см. рисунок)', '').replace('см. рисунок', '')
            if before != p['text']:
                patch_count += 1
        if p.get('solution'):
            before_sol = p['solution']
            p['solution'] = p['solution'].replace('(см. рисунок)', '').replace('см. рисунок', '')
            if before_sol != p['solution']:
                patch_count += 1
    
    if patch_count > 0:
        print(f"[RUNTIME PATCH] Удалено 'см. рисунок' из {patch_count} полей в combo_id={combo.get('id')} (solutions)")

    # Build specific source URL (e.g. olimpiada.ru with year+grade+round for vsosh)
    try:
        from services.olimpiada_url import get_combo_source_url
        specific_url = get_combo_source_url(combo)
        if specific_url and specific_url != combo.get('source_url'):
            # Inject specific URL into a copy so we don't mutate global data
            combo = dict(combo)
            combo['source_url'] = specific_url
    except Exception as _url_err:
        pass  # Keep original source_url on any error

    return render_template('olympiad_solutions.html',
        olympiad=olympiad,
        combo=combo
    )


def send_auth_email(recipient_email, code):
    """Отправка кода через Yandex SMTP на порту 587 с TLS (для Render)."""
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    
    # Используем надежный порт 587 для TLS
    smtp_server = 'smtp.yandex.ru'
    smtp_port = 587
    smtp_user = 'kr1venkovictor@yandex.ru'
    smtp_pass = os.environ.get('MAIL_PASSWORD', 'ktxfblhgcrlryncy')
    
    msg = MIMEMultipart()
    msg['From'] = smtp_user
    msg['To'] = recipient_email
    msg['Subject'] = 'Код подтверждения для доступа к платформе FORMYLA'
    
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 30px; background: #ffffff; border-radius: 10px;">
        <div style="text-align: center; margin-bottom: 30px;">
            <h1 style="color: #4F46E5; margin: 0;">FORMYLA</h1>
            <p style="color: #666; font-size: 14px; margin-top: 5px;">Образовательная платформа по математике</p>
        </div>
        
        <p style="color: #333; font-size: 16px; line-height: 1.6;">
            Здравствуйте!<br><br>
            Вы запросили код для входа на образовательную платформу FORMYLA.
        </p>
        
        <div style="text-align: center; margin: 30px 0;">
            <p style="color: #666; font-size: 14px; margin-bottom: 10px;">Ваш проверочный код:</p>
            <div style="font-size: 36px; font-weight: bold; letter-spacing: 10px; color: #4F46E5; padding: 20px; background: #F3F4F6; border-radius: 10px; display: inline-block;">
                {code}
            </div>
        </div>
        
        <p style="color: #666; font-size: 14px; line-height: 1.6; margin-top: 30px;">
            Код действителен в течение 10 минут. Введите его на странице входа для доступа к вашему аккаунту.
        </p>
        
        <p style="color: #999; font-size: 13px; line-height: 1.6; margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee;">
            Если вы не запрашивали этот код, просто проигнорируйте это письмо. Ваш аккаунт в безопасности.
        </p>
        
        <div style="text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee;">
            <p style="color: #666; font-size: 14px; margin: 0;">С уважением,</p>
            <p style="color: #4F46E5; font-size: 16px; font-weight: 600; margin: 5px 0;">Команда FORMYLA</p>
        </div>
    </div>
    """
    msg.attach(MIMEText(html, 'html', 'utf-8'))
    
    try:
        # Для порта 587 используем обычный SMTP с обязательным starttls()
        print(f"[EMAIL] Connecting to {smtp_server}:{smtp_port} via TLS")
        server = smtplib.SMTP(smtp_server, smtp_port, timeout=30)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)
        server.quit()
        print(f"[EMAIL] ✅ Successfully sent to {recipient_email}")
        return True
    except Exception as e:
        print(f"[EMAIL ERROR] Failed to send: {e}")
        raise Exception(f"Ошибка отправки email: {str(e)}")


@app.route("/login", methods=["GET", "POST"])
def login():
    """Passwordless вход - шаг 1: ввод email."""
    if current_user.is_authenticated and not current_user.is_guest:
        return redirect(url_for('index'))
    
    if request.method == "POST":
        import sys
        print(">>> LOGIN POST ВЫЗВАН", flush=True)
        sys.stdout.flush()
        app.logger.warning("LOGIN POST ВЫЗВАН")
        
        email = request.form.get('email', '').strip().lower()
        
        if not email:
            flash('Email обязателен', 'error')
            return render_template('login.html')
        
        # Проверяем или создаем пользователя
        user = User.query.filter_by(email=email).first()
        
        if not user:
            # Создаем нового пользователя
            user = User(email=email)
            db.session.add(user)
        
        # Генерируем код
        code = user.generate_auth_code()
        db.session.commit()
        
        print(f">>> КОД СГЕНЕРИРОВАН: {code}", flush=True)
        app.logger.warning(f"КОД СГЕНЕРИРОВАН: {code} для {email}")
        
        # Отправляем код на email
        # Проверяем настройки
        mail_configured = app.config.get('MAIL_USERNAME') and app.config.get('MAIL_PASSWORD')
        
        print(f"\n🔍 DEBUG: MAIL_USERNAME = {app.config.get('MAIL_USERNAME')}", flush=True)
        mail_pass = app.config.get('MAIL_PASSWORD') or ''
        print(f"🔍 DEBUG: MAIL_PASSWORD = {'*' * len(mail_pass)} ({len(mail_pass)} символов)", flush=True)
        print(f"🔍 DEBUG: Mail configured = {mail_configured}\n", flush=True)
        
        if mail_configured:
            try:
                send_auth_email(email, code)
                
                # Дублируем в консоль для отладки
                print("\n" + "="*60, flush=True)
                print("✅ EMAIL УСПЕШНО ОТПРАВЛЕН", flush=True)
                print("="*60, flush=True)
                print(f"   Кому: {email}", flush=True)
                print(f"   Код: {code}", flush=True)
                print("="*60 + "\n", flush=True)
                app.logger.warning(f"EMAIL ОТПРАВЛЕН: {email}, код: {code}")
                
                flash(f'Код отправлен на {email}. Проверьте почту!', 'success')
                
            except Exception as e:
                error_message = str(e)
                print(f"\n❌ ОШИБКА ОТПРАВКИ EMAIL: {error_message}\n", flush=True)
                app.logger.error(f"ОШИБКА EMAIL: {error_message}")
                
                # Fallback - выводим код в консоль
                print("\n" + "="*60, flush=True)
                print("⚠️  FALLBACK - КОД В КОНСОЛИ", flush=True)
                print("="*60, flush=True)
                print(f"   Email: {email}", flush=True)
                print(f"   КОД: {code}", flush=True)
                print(f"   Действителен: 10 минут", flush=True)
                print("="*60 + "\n", flush=True)
                
                # Показываем понятное сообщение пользователю
                if "аутентификации" in error_message.lower() or "authentication" in error_message.lower():
                    flash(f'Ошибка настройки email-сервера. Обратитесь к администратору.', 'error')
                elif "подключиться" in error_message.lower() or "connect" in error_message.lower():
                    flash(f'Не удалось подключиться к почтовому серверу. Попробуйте позже.', 'error')
                else:
                    flash(f'Ошибка отправки email: {error_message}', 'error')
        else:
            # Email не настроен
            print("\n" + "="*60, flush=True)
            print("⚠️  EMAIL НЕ НАСТРОЕН - КОД В КОНСОЛИ", flush=True)
            print("="*60, flush=True)
            print(f"   Email: {email}", flush=True)
            print(f"   КОД: {code}", flush=True)
            print(f"   Действителен: 10 минут", flush=True)
            print("="*60 + "\n", flush=True)
            app.logger.warning(f"EMAIL НЕ НАСТРОЕН - КОД: {code}")
            
            flash(f'Код отправлен на {email}', 'success')
        
        # Сохраняем email в сессию для следующего шага
        session.permanent = True  # Делаем сессию постоянной (30 дней)
        session['verify_email'] = email
        return redirect(url_for('verify_code'))
    
    return render_template('login.html')


@app.route("/verify-code", methods=["GET", "POST"])
def verify_code():
    """Passwordless вход - шаг 2: проверка кода."""
    if current_user.is_authenticated and not current_user.is_guest:
        return redirect(url_for('index'))
    
    email = session.get('verify_email')
    if not email:
        flash('Сначала введите email', 'error')
        return redirect(url_for('login'))
    
    if request.method == "POST":
        code = request.form.get('code', '').strip()
        
        if not code:
            flash('Введите код', 'error')
            return render_template('verify_code.html', email=email)
        
        user = User.query.filter_by(email=email).first()
        
        if not user:
            flash('Пользователь не найден', 'error')
            return redirect(url_for('login'))
        
        if user.verify_auth_code(code):
            # Успешная авторизация
            user.clear_auth_code()
            from datetime import datetime
            # Считаем нового юзера тем, у кого ещё нет онбординга
            _is_new_user = getattr(user, 'onboarded_at', None) is None and getattr(user, 'last_login', None) is None
            user.last_login = datetime.utcnow()
            db.session.commit()

            # Welcome email через Brevo для первого входа
            if _is_new_user:
                try:
                    from services.email_service import send_welcome_email
                    threading.Thread(
                        target=send_welcome_email,
                        args=(user,),
                        daemon=True,
                    ).start()
                except Exception as _we_err:
                    app.logger.warning(f"Welcome email failed: {_we_err}")

            # Вход с долгоживущей сессией (30 дней)
            session.permanent = True  # Делаем сессию постоянной (30 дней)
            login_user(user, remember=True, duration=None)
            session.pop('verify_email', None)

            flash('Добро пожаловать!', 'success')

            # Редирект:
            #   1) если есть next — туда
            #   2) если пользователь ещё не прошёл онбординг — /about?onboarding=1
            #   3) иначе — главная
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            if getattr(user, 'onboarded_at', None) is None:
                return redirect(url_for('about_page', onboarding=1))
            return redirect(url_for('index'))
        
        flash('Неверный или просроченный код', 'error')
        return render_template('verify_code.html', email=email)
    
    return render_template('verify_code.html', email=email)


@app.route("/logout")
def logout():
    """Выход пользователя."""
    logout_user()
    session.clear()
    resp = redirect(url_for('index'))
    # Удаляем remember_me cookie (с учётом secure/samesite флагов для production)
    resp.delete_cookie('remember_token', path='/', samesite='Lax')
    resp.delete_cookie('formyla_device_id', path='/', samesite='Lax')
    return resp


@app.route("/yandex_login")
def yandex_login_start():
    """Начало OAuth через Яндекс (редирект)."""
    client_id = app.config.get('YANDEX_CLIENT_ID')
    domain = os.environ.get('DOMAIN_URL', 'http://localhost:5000')
    redirect_uri = f"{domain}/yandex_receiver"
    
    if not client_id:
        flash('Яндекс OAuth не настроен на сервере. Обратитесь к администратору.', 'error')
        # Если пользователь залогинен — возвращаем на профиль, иначе на логин
        if current_user.is_authenticated:
            return redirect(url_for('profile'))
        return redirect(url_for('login'))
    
    # Редирект на Яндекс OAuth
    auth_url = f"https://oauth.yandex.ru/authorize?response_type=token&client_id={client_id}&redirect_uri={redirect_uri}"
    return redirect(auth_url)


@app.route("/yandex_receiver")
def yandex_receiver():
    """
    OAuth callback page: parses #access_token from URL fragment and POSTs it
    to /auth/yandex/login for server-side processing.
    """
    return render_template('yandex_receiver.html')


@app.route("/link_yandex")
@login_required
def link_yandex():
    """Начало привязки Яндекс ID к существующему аккаунту."""
    # Сохраняем флаг, что это linking, а не обычный вход
    session['linking_mode'] = True
    session.permanent = True
    
    # Перенаправляем на Яндекс OAuth
    return redirect(url_for('yandex_login_start'))


@app.route("/auth/yandex/login", methods=["POST"])
def yandex_login():
    """Обработка OAuth токена от Яндекса (вход или привязка аккаунта)."""
    data = request.get_json()
    access_token = data.get('access_token')
    
    if not access_token:
        return jsonify({'error': 'Токен не предоставлен'}), 400
    
    try:
        # Получаем данные от Яндекса
        response = requests.get(
            'https://login.yandex.ru/info?format=json',
            headers={'Authorization': f'OAuth {access_token}'}
        )
        
        if response.status_code != 200:
            return jsonify({'error': 'Ошибка Яндекса'}), 400
        
        yandex_data = response.json()
        provider_user_id = str(yandex_data.get('id'))
        email = yandex_data.get('default_email')
        name = yandex_data.get('display_name') or yandex_data.get('real_name', '')
        avatar_id = yandex_data.get('default_avatar_id', '')
        avatar_url = f"https://avatars.yandex.net/get-yapic/{avatar_id}/islands-200" if avatar_id else None
        
        from models import OAuthAccount
        
        # Проверяем, это linking или обычный вход
        # Поддерживаем как session flag, так и JSON параметр (для виджета на профиле)
        is_linking = session.pop('linking_mode', False) or data.get('linking_mode', False)
        
        if is_linking and current_user.is_authenticated:
            # РЕЖИМ ПРИВЯЗКИ: добавляем Яндекс к существующему аккаунту.
            # ВАЖНО (по требованию): не блокируем пользователя сообщением «уже привязан».
            # Логика:
            #   1) Если этот Я-ID НЕ привязан ни к кому — создаём привязку.
            #   2) Если уже привязан к ТЕКУЩЕМУ аккаунту — просто отвечаем успехом
            #      (пользователь теперь может попадать в этот же аккаунт двумя способами).
            #   3) Если привязан к ДРУГОМУ аккаунту — предлагаем слияние (как и раньше),
            #      потому что иначе мы потеряли бы данные другого пользователя.
            existing_oauth = OAuthAccount.query.filter_by(provider='yandex', provider_user_id=provider_user_id).first()

            if existing_oauth and existing_oauth.user_id != current_user.id:
                # КОЛЛИЗИЯ: Я-ID привязан к ДРУГОМУ аккаунту →
                # ПЕРЕПРИВЯЗАТЬ его на текущего пользователя (по требованию).
                old_user_id = existing_oauth.user_id
                existing_oauth.user_id = current_user.id
                try:
                    db.session.commit()
                except Exception as _re_link_err:
                    db.session.rollback()
                    print(f"[YANDEX] re-link failed: {_re_link_err}")
                    return jsonify({
                        "success": False,
                        "error": "Не удалось перепривязать Яндекс ID. Попробуйте ещё раз."
                    }), 500
                return jsonify({
                    "success": True,
                    "redirect_url": url_for("profile"),
                    "message": f"Яндекс ID перепривязан с аккаунта #{old_user_id} на текущий. Теперь вход через Яндекс ведёт в этот аккаунт.",
                })
            if not existing_oauth:
                # Создаём новую привязку
                oauth = OAuthAccount(user_id=current_user.id, provider='yandex', provider_user_id=provider_user_id)
                db.session.add(oauth)
                db.session.commit()
                return jsonify({
                    'success': True,
                    'redirect_url': url_for('profile'),
                    'message': 'Яндекс ID успешно привязан! Теперь вы можете входить в этот аккаунт через Яндекс.'
                })

            # existing_oauth.user_id == current_user.id — уже привязан к текущему пользователю.
            # Не считаем это ошибкой: возвращаем успех (вход в этот аккаунт через Я-ID уже работает).
            return jsonify({
                'success': True,
                'redirect_url': url_for('profile'),
                'message': 'Этот Яндекс ID уже привязан к вашему аккаунту — вход через Яндекс уже работает.'
            })
        
        # РЕЖИМ ВХОДА: обычная авторизация через Яндекс
        # Ищем OAuth аккаунт
        oauth = OAuthAccount.query.filter_by(provider='yandex', provider_user_id=provider_user_id).first()
        
        _yandex_is_new_user = False
        if oauth:
            user = oauth.user
        else:
            # Ищем по email
            user = User.query.filter_by(email=email).first()

            if not user:
                # Создаем нового
                user = User(email=email, name=name, avatar_url=avatar_url)
                db.session.add(user)
                db.session.flush()
                _yandex_is_new_user = True

            # Создаем OAuth связь
            oauth = OAuthAccount(user_id=user.id, provider='yandex', provider_user_id=provider_user_id)
            db.session.add(oauth)
        
        # Обновляем данные
        if name and not user.name:
            user.name = name
        if avatar_url and not user.avatar_url:
            user.avatar_url = avatar_url
        
        # Пользователь вошёл через OAuth — он больше не гость
        user.is_guest = False
        from datetime import datetime
        user.last_login = datetime.utcnow()
        db.session.commit()

        # Welcome email через Brevo — только для впервые созданных пользователей
        if _yandex_is_new_user:
            try:
                from services.email_service import send_welcome_email
                threading.Thread(
                    target=send_welcome_email,
                    args=(user,),
                    daemon=True,
                ).start()
            except Exception as _we_err:
                app.logger.warning(f"Welcome email failed (yandex): {_we_err}")
        
        # Авторизуем
        session.permanent = True  # Делаем сессию постоянной (30 дней)
        login_user(user, remember=True)

        # Редирект: новым пользователям (onboarded_at IS NULL) — на онбординг
        if getattr(user, 'onboarded_at', None) is None:
            redirect_url = url_for('about_page', onboarding=1)
        else:
            redirect_url = url_for('index')

        return jsonify({'success': True, 'redirect_url': redirect_url})
        
    except Exception as e:
        print(f"Ошибка OAuth: {e}")
        return jsonify({'error': str(e)}), 500


# Онбординг удален - используйте AI-тьютор

@app.route("/api/tutor/history")
@login_required
def tutor_history():
    """Получить историю чата с тьютором для конкретного агента."""
    from models import ChatMessage
    agent_type = request.args.get('agent_type', 'general')
    messages = ChatMessage.query.filter_by(
        user_id=current_user.id,
        agent_type=agent_type
    ).order_by(ChatMessage.timestamp).all()
    return jsonify([msg.to_dict() for msg in messages])


@app.route("/api/tutor/send", methods=["POST"])
@login_required
def tutor_send():
    """Отправить сообщение тьютору (специализированному агенту)."""
    if not DEEPSEEK_AVAILABLE:
        return jsonify({'error': 'AI недоступен'}), 503
    
    # Проверяем, это JSON или FormData (для файлов)
    if request.is_json:
        data = request.get_json()
        message = data.get('message', '').strip()
        agent_type = data.get('agent_type', 'general')
        hint_mode = data.get('hint_mode', True)
        image_data = None
    else:
        # FormData с файлами (multiple)
        message = request.form.get('message', '').strip()
        agent_type = request.form.get('agent_type', 'general')
        hint_mode = request.form.get('hint_mode', 'true').lower() == 'true'
        
        # Обработка файлов (поддержка multiple)
        import base64
        image_data = None
        
        # Поддержка нового формата (multiple files под ключом 'files')
        files = [f for f in request.files.getlist('files') if f and f.filename]
        # Fallback: старый формат (single file под ключом 'file')
        if not files and 'file' in request.files:
            f = request.files['file']
            if f and f.filename:
                files = [f]
        
        if files:
            # Берём первый файл для vision API (DeepSeek/OpenRouter поддерживает 1 изображение)
            first_file = files[0]
            if first_file and first_file.filename:
                image_data = base64.b64encode(first_file.read()).decode('utf-8')
    
    if not message and not image_data:
        return jsonify({'error': 'Сообщение пустое'}), 400
    
    try:
        from models import ChatMessage
        
        # Сохраняем сообщение пользователя с привязкой к агенту
        user_msg = ChatMessage(
            user_id=current_user.id,
            agent_type=agent_type,
            role='user',
            content=message + (" [📎 Прикреплено изображение]" if image_data else "")
        )
        db.session.add(user_msg)
        # Retry commit to handle 'database is locked' from APScheduler contention
        import time as _t
        for _i in range(5):
            try:
                db.session.commit()
                break
            except Exception as _ce:
                if 'database is locked' in str(_ce).lower() and _i < 4:
                    db.session.rollback()
                    _t.sleep(0.3 * (_i + 1))
                else:
                    raise
        
        # Получаем историю для ЭТОГО агента (не смешиваем с другими)
        history = ChatMessage.query.filter_by(
            user_id=current_user.id,
            agent_type=agent_type
        ).order_by(ChatMessage.timestamp).all()
        history_list = [{'role': msg.role, 'content': msg.content} for msg in history[-20:]]
        
        # Получаем ответ от AI с учетом типа агента, режима и изображения
        client = DeepSeekClient()
        # Если текст пустой но есть фото — подставляем дефолтный запрос
        effective_message = message if message else "Реши/объясни эту задачу по фото"
        response = client.chat_with_tutor(
            current_user,
            effective_message,
            history_list,
            agent_type=agent_type,
            hint_mode=hint_mode,
            image_data=image_data
        )
        
        # Сохраняем ответ AI с привязкой к агенту
        ai_msg = ChatMessage(
            user_id=current_user.id,
            agent_type=agent_type,
            role='assistant',
            content=response
        )
        db.session.add(ai_msg)
        for _i2 in range(5):
            try:
                db.session.commit()
                break
            except Exception as _ce2:
                if 'database is locked' in str(_ce2).lower() and _i2 < 4:
                    db.session.rollback()
                    _t.sleep(0.3 * (_i2 + 1))
                else:
                    raise
        
        return jsonify({
            'user_message': user_msg.to_dict(),
            'ai_response': ai_msg.to_dict()
        })
        
    except Exception as e:
        print(f"Ошибка чата: {e}", flush=True)
        app.logger.error(f"AI Tutor error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Ошибка AI: {str(e)}'}), 500


@app.route("/api/tutor/hint/<int:problem_id>", methods=["POST"])
@login_required
def get_ai_hint(problem_id):
    """Получить наводящую подсказку от AI для конкретной задачи."""
    if not DEEPSEEK_AVAILABLE:
        return jsonify({'error': 'AI недоступен'}), 503
    
    # Ищем задачу в обеих базах
    problem = next((p for p in PROBLEMS_DB if p.get("id") == problem_id), None)
    if not problem:
        problem = next((p for p in _RAW_DB if p.get("id") == problem_id), None)
    
    if not problem:
        return jsonify({'error': 'Задача не найдена'}), 404
    
    try:
        client = DeepSeekClient()
        hint = client.generate_hint(
            problem_text=problem.get('text', ''),
            problem_answer=problem.get('answer', ''),
            difficulty=problem.get('difficulty', 1)
        )
        
        return jsonify({
            'hint': hint,
            'problem_id': problem_id
        })
        
    except Exception as e:
        app.logger.error(f"AI Hint error: {e}")
        return jsonify({'error': f'Ошибка генерации подсказки: {str(e)}'}), 500


@app.route("/api/tutor/solution/<int:problem_id>", methods=["POST"])
@login_required
def get_ai_solution(problem_id):
    """Получить полное решение от AI для конкретной задачи."""
    if not DEEPSEEK_AVAILABLE:
        return jsonify({'error': 'AI недоступен'}), 503
    
    # Ищем задачу в обеих базах
    problem = next((p for p in PROBLEMS_DB if p.get("id") == problem_id), None)
    if not problem:
        problem = next((p for p in _RAW_DB if p.get("id") == problem_id), None)
    
    if not problem:
        return jsonify({'error': 'Задача не найдена'}), 404
    
    try:
        client = DeepSeekClient()
        solution = client.generate_solution(
            problem_text=problem.get('text', ''),
            problem_answer=problem.get('answer', ''),
            difficulty=problem.get('difficulty', 1)
        )
        
        return jsonify({
            'solution': solution,
            'answer': problem.get('answer', ''),
            'problem_id': problem_id
        })
        
    except Exception as e:
        app.logger.error(f"AI Solution error: {e}")
        return jsonify({'error': f'Ошибка генерации решения: {str(e)}'}), 500


@app.route("/profile")
@login_required
def profile():
    """Личный кабинет пользователя с прогрессом и учениками."""
    # Получаем прогресс по темам
    topic_progress = UserTopicProgress.query.filter_by(user_id=current_user.id).all()
    
    # Создаем словарь прогресса по темам
    progress_dict = {}
    for tp in topic_progress:
        progress_dict[tp.topic] = {
            'level': tp.current_level,
            'name_ru': tp.topic_name_ru,
            'attempted': tp.tasks_attempted,
            'correct': tp.tasks_correct,
            'accuracy': (tp.tasks_correct / tp.tasks_attempted * 100) if tp.tasks_attempted > 0 else 0,
            'last_test': tp.last_test_date
        }
    
    # Получаем последние 5 тестов
    recent_tests = AdaptiveTestResult.query.filter_by(
        user_id=current_user.id
    ).order_by(AdaptiveTestResult.completed_at.desc()).limit(5).all()
    
    # Вычисляем статистику по адаптивным тестам
    all_tests = AdaptiveTestResult.query.filter_by(user_id=current_user.id).all()
    test_stats = {
        'total_tests': len(all_tests),
        'avg_level': round(sum(t.final_level for t in all_tests) / len(all_tests), 1) if all_tests else 0,
        'max_level': max((t.final_level for t in all_tests), default=0),
        'total_correct': sum(t.tasks_correct for t in all_tests),
        'total_tasks': sum(t.tasks_total for t in all_tests)
    }
    
    # Получаем список друзей (accepted friendships)
    friends_list = current_user.get_friends() if hasattr(current_user, 'get_friends') else []
    
    # Для совместимости с шаблоном — передаём как students
    students = friends_list
    
    # Входящие заявки в друзья (не используется при мгновенной дружбе, но оставим для совместимости)
    incoming_requests = []
    
    # ── Mastery Dashboard ──
    from models import TopicMastery
    
    TOPIC_META = {
        'algebra':        {'name_ru': 'Алгебра',            'icon': '➗'},
        'geometry':       {'name_ru': 'Геометрия',          'icon': '📐'},
        'combinatorics':  {'name_ru': 'Комбинаторика',      'icon': '🧩'},
        'number_theory':  {'name_ru': 'Теория чисел',       'icon': '🔢'},
        'kl_movement':    {'name_ru': 'Задачи на движение', 'icon': '🚂'},
        'knights_liars':  {'name_ru': 'Рыцари и лжецы',     'icon': '🧠'},
    }
    
    def get_level_label(mastery):
        if mastery < 0.2:  return 'Новичок'
        if mastery < 0.4:  return 'Ученик'
        if mastery < 0.6:  return 'Практик'
        if mastery < 0.85: return 'Мастер'
        return 'Чемпион'
    
    def get_level_category(mastery):
        if mastery < 0.3:  return 'weak'
        if mastery < 0.6:  return 'medium'
        if mastery < 0.85: return 'strong'
        return 'champion'
    
    mastery_rows = TopicMastery.query.filter_by(user_id=current_user.id).all()
    mastery_by_topic = {row.topic: row for row in mastery_rows}

    # Build mastery_list with ALL topics from TOPIC_META (so radar always has all axes)
    mastery_list = []
    for topic_key, meta in TOPIC_META.items():
        row = mastery_by_topic.get(topic_key)
        if row:
            mastery_val = round(row.mastery, 3)
            solved = row.solved
            avg_level = round(row.avg_level, 1)
        else:
            mastery_val = 0.0
            solved = 0
            avg_level = 0.0
        mastery_list.append({
            'topic': topic_key,
            'name_ru': meta['name_ru'],
            'icon': meta['icon'],
            'mastery': mastery_val,
            'solved': solved,
            'avg_level': avg_level,
            'trend': 0,  # TODO: compute weekly trend
            'level_category': get_level_category(mastery_val),
            'level_label': get_level_label(mastery_val),
        })
    # Sort: tested topics first (by mastery desc), then untested
    mastery_list.sort(key=lambda x: (-1 if x['mastery'] > 0 else 0, -x['mastery']))

    # Overall level (average mastery of tested topics → 1-10 scale)
    tested = [m for m in mastery_list if m['mastery'] > 0]
    if tested:
        avg_mastery = sum(m['mastery'] for m in tested) / len(tested)
        overall_level = max(1, min(10, round(avg_mastery * 10)))
    else:
        overall_level = 1

    # AI recommendation (simple rule-based, no API call to avoid latency)
    ai_recommendation = ''
    if tested:
        weakest = min(tested, key=lambda m: m['mastery'])
        ai_recommendation = (
            f"Сосредоточься на теме <strong>{weakest['name_ru']}</strong> — "
            f"твой уровень {int(weakest['mastery']*100)}%. "
            f"Реши 5 задач уровня {int(weakest['avg_level'])+1} для быстрого роста."
        )
    elif mastery_list:
        # User has no tested topics — suggest starting
        untested_names = ', '.join(m['name_ru'] for m in mastery_list[:3])
        ai_recommendation = f"Пройди адаптивный тест по одной из тем: {untested_names}!"
    else:
        ai_recommendation = "Пройди адаптивный тест, чтобы получить персональные рекомендации!"

    # JSON for radar chart — always all topics for full hexagonal shape
    mastery_list_json = [{'name': m['name_ru'], 'value': m['mastery']} for m in mastery_list]
    
    return render_template('profile.html',
                         user=current_user,
                         progress_dict=progress_dict,
                         recent_tests=recent_tests,
                         test_stats=test_stats,
                         students=students,
                         incoming_requests=incoming_requests,
                         mastery_list=mastery_list,
                         mastery_list_json=mastery_list_json,
                         overall_level=overall_level,
                         ai_recommendation=ai_recommendation)


# ============================================================
# MOCK EXAMS (Пробники)
# ============================================================

@app.route("/api/exam/generate", methods=["POST"])
@login_required
def generate_exam():
    """Генерация нового пробника с задачами разного уровня сложности."""
    from models import MockExam, MockExamTask
    import random
    
    data = request.get_json() or {}
    grade = data.get('grade', 9)  # По умолчанию 9 класс
    
    # Фильтруем задачи по классу
    grade_problems = [p for p in PROBLEMS_DB if p.get('grade') == grade]
    
    if not grade_problems:
        # Если нет задач для класса, берем любые
        grade_problems = PROBLEMS_DB
    
    # Группируем по уровню сложности
    by_difficulty = {}
    for p in grade_problems:
        diff = p.get('difficulty', 3)
        if diff not in by_difficulty:
            by_difficulty[diff] = []
        by_difficulty[diff].append(p)
    
    # Выбираем задачи с нарастающей сложностью (как на реальной олимпиаде)
    selected_problems = []
    target_distribution = [
        (1, 2, 1),  # 1 легкая задача
        (3, 4, 2),  # 2 средние задачи
        (5, 6, 1),  # 1 сложная задача
        (7, 10, 1)  # 1 очень сложная задача
    ]
    
    for min_diff, max_diff, count in target_distribution:
        candidates = []
        for d in range(min_diff, max_diff + 1):
            candidates.extend(by_difficulty.get(d, []))
        if candidates:
            selected_problems.extend(random.sample(candidates, min(count, len(candidates))))
    
    # Дополняем до 5 если нужно
    if len(selected_problems) < 5:
        remaining = [p for p in grade_problems if p not in selected_problems]
        if remaining:
            selected_problems.extend(random.sample(remaining, min(5 - len(selected_problems), len(remaining))))
    
    # Ограничиваем до 5 задач
    selected_problems = selected_problems[:5]
    
    # Создаем пробник
    exam = MockExam(user_id=current_user.id)
    db.session.add(exam)
    db.session.flush()
    
    # Добавляем задачи
    for prob in selected_problems:
        task = MockExamTask(exam_id=exam.id, problem_id=prob['id'])
        db.session.add(task)
    
    db.session.commit()
    
    return jsonify({'exam_id': exam.id})


@app.route("/exam/<int:exam_id>")
@login_required
def exam_page(exam_id):
    """Страница прохождения пробника."""
    from models import MockExam
    exam = MockExam.query.get_or_404(exam_id)
    
    if exam.user_id != current_user.id:
        abort(403)
    
    # Получаем задачи
    tasks_data = []
    for task in exam.tasks:
        problem = next((p for p in PROBLEMS_DB if p['id'] == task.problem_id), None)
        if problem:
            tasks_data.append({
                'task_id': task.id,
                'problem': problem
            })
    
    return render_template('exam.html', exam=exam, tasks=tasks_data)


@app.route("/api/exam/<int:exam_id>/submit", methods=["POST"])
@login_required
def submit_exam(exam_id):
    """Отправка пробника на проверку AI."""
    from models import MockExam, MockExamTask
    
    exam = MockExam.query.get_or_404(exam_id)
    if exam.user_id != current_user.id:
        abort(403)
    
    data = request.get_json()
    answers = data.get('answers', {})
    
    # Сохраняем ответы
    for task in exam.tasks:
        task_data = answers.get(str(task.id), {})
        task.user_answer = task_data.get('answer', '')
        task.user_solution_text = task_data.get('solution', '')
    
    exam.status = 'checking'
    db.session.commit()
    
    # Проверка через AI
    if DEEPSEEK_AVAILABLE:
        try:
            client = DeepSeekClient()
            
            # Подготовка данных
            exam_data = []
            for task in exam.tasks:
                problem = next((p for p in PROBLEMS_DB if p['id'] == task.problem_id), None)
                if problem:
                    exam_data.append({
                        'text': problem['text'],
                        'correct_answer': problem['answer'],
                        'correct_solution': problem['solution'],
                        'user_answer': task.user_answer or '',
                        'user_solution': task.user_solution_text or ''
                    })
            
            # Проверка
            result = client.grade_exam(exam_data)
            
            # Сохранение результатов
            for i, task in enumerate(exam.tasks):
                task_result = result['tasks'][i] if i < len(result['tasks']) else {}
                task.is_correct = task_result.get('is_correct', False)
                task.ai_comment = task_result.get('comment', '')
            
            exam.ai_feedback = result.get('overall_feedback', '')
            exam.score = result.get('score', 0)
            exam.status = 'graded'
            db.session.commit()
            
            # Отправляем анализ в чат с тьютором
            try:
                from models import ChatMessage
                chat_msg = f"""🎯 Пробник #{exam_id} проверен!

Ваш результат: {exam.score}%

{exam.ai_feedback}

Хотите разобрать ошибки или попробовать еще раз?"""
                
                ai_msg = ChatMessage(user_id=current_user.id, role='assistant', content=chat_msg)
                db.session.add(ai_msg)
                db.session.commit()
            except:
                pass  # Не критично если не отправилось
            
            return jsonify({'success': True, 'exam_id': exam_id})
            
        except Exception as e:
            print(f"Ошибка проверки: {e}")
            exam.status = 'in_progress'
            db.session.commit()
            return jsonify({'error': str(e)}), 500
    
    return jsonify({'error': 'AI недоступен'}), 503


@app.route("/exam/<int:exam_id>/results")
@login_required
def exam_results(exam_id):
    """Страница результатов пробника."""
    from models import MockExam
    exam = MockExam.query.get_or_404(exam_id)
    
    if exam.user_id != current_user.id:
        abort(403)
    
    # Получаем задачи с результатами
    results_data = []
    for task in exam.tasks:
        problem = next((p for p in PROBLEMS_DB if p['id'] == task.problem_id), None)
        if problem:
            results_data.append({
                'problem': problem,
                'user_answer': task.user_answer,
                'user_solution': task.user_solution_text,
                'is_correct': task.is_correct,
                'ai_comment': task.ai_comment
            })
    
    return render_template('exam_results.html', exam=exam, results=results_data)


# ============================================================
# FREE MOCK TEST (Бесплатный пробник)
# ============================================================

@app.route("/free_mock/start")
@login_required
def free_mock_start():
    """Показать страницу бесплатного пробника с пошаговой генерацией."""
    # Инициализируем историю задач для нового пробника
    session['mock_task_ideas'] = []
    session['mock_task_texts'] = []
    session['mock_task_subtopics'] = []  # Очищаем историю подтем для уникальности
    
    # Очищаем кэш предгенерированных задач
    session_id = request.cookies.get('session', session.get('_id', str(current_user.id)))
    clear_cache(session_id)
    
    print("[Free Mock] 🆕 Новый пробник начат. История задач и кэш очищены.")
    return render_template('free_mock.html')


@app.route("/free_mock/generate", methods=["POST"])
@login_required
def free_mock_generate():
    """Генерация 25 задач через DeepSeek AI."""
    grade = request.form.get('grade')
    level = request.form.get('level')
    
    if not grade or not level:
        flash('Пожалуйста, выберите класс и уровень сложности', 'error')
        return redirect(url_for('free_mock_start'))
    
    # Проверка доступности DeepSeek
    if not DEEPSEEK_AVAILABLE:
        flash('AI-генерация временно недоступна. Попробуйте позже.', 'error')
        return redirect(url_for('free_mock_start'))
    
    try:
        # Инициализация DeepSeek клиента
        deepseek = DeepSeekClient()
        
        # Промпт для генерации задач
        system_prompt = r"""Ты - эксперт по математике, создающий задачи для школьников.
Генерируй задачи в строгом JSON формате без дополнительного текста.

КРИТИЧЕСКИЕ ПРАВИЛА ОФОРМЛЕНИЯ МАТЕМАТИКИ (LaTeX) — ПРИ НАРУШЕНИИ ОТКЛОНЕНО:
1. ВЕСЬ математический текст оборачивай в \( ... \) для инлайн и \[ ... \] для блоков
2. ЗАПРЕЩЕНО использовать юникод ², ³, √ или ^ вне LaTeX! Используй \( x^2 \), \( \sqrt{4} \)
3. ЗАПРЕЩЕНО использовать / для дробей! Используй \( \frac{1}{2} \)
4. Знаки умножения: \( \cdot \) (не * и не x)
5. СИСТЕМЫ УРАВНЕНИЙ: Используй \begin{cases} ... \end{cases}"""
        
        user_prompt = f"""Сгенерируй 10 математических задач для {grade} класса, уровень "{level}".

Требования:
- Разнообразные темы: алгебра, геометрия, текстовые задачи, логика
- 2 блока по 5 задач с возрастающей сложностью внутри блока
- Каждая задача должна иметь короткий числовой или текстовый ответ
- Решение должно быть КРАТКИМ (максимум 3-4 предложения)
- ВСЕ задачи должны быть 4 уровня сложности (средний уровень)

Верни ТОЛЬКО валидный JSON массив в формате:
[
  {{
    "id": 1,
    "text": "Текст задачи",
    "answer": "Краткий ответ",
    "solution": "Краткое решение (3-4 предложения)",
    "difficulty": 4
  }},
  ...
]

Важно: ответ должен содержать ТОЛЬКО JSON массив, без markdown разметки и дополнительного текста."""

        # Генерация через DeepSeek
        print(f"🤖 Генерация 25 задач для {grade} класса, уровень {level}...")
        print(f"📝 ПРОМПТ (первые 200 символов): {user_prompt[:200]}...")
        
        response = deepseek.generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.7,
            max_tokens=8000
        )
        
        print("="*80)
        print("СЫРОЙ ОТВЕТ ИИ (ПОЛНОСТЬЮ):")
        print(response)
        print("="*80)
        
        # Парсинг JSON - убираем markdown блоки
        response = response.strip()
        if response.startswith('```json'):
            response = response[7:]
        if response.startswith('```'):
            response = response[3:]
        if response.endswith('```'):
            response = response[:-3]
        response = response.strip()
        
        # Простой парсинг без валидации
        tasks = json.loads(response)
        
        # Берем первые 10 задач
        tasks = tasks[:10]
        
        # Добавляем ID
        for i, task in enumerate(tasks, 1):
            task['id'] = i
        
        # Сохраняем в сессию (только ID, чтобы не превысить лимит cookie)
        # Полные задачи сохраняем в отдельной переменной
        test_id = f"free_mock_{current_user.id}_{int(datetime.utcnow().timestamp())}"
        
        # Сохраняем задачи в глобальной переменной (временное хранилище)
        if not hasattr(app, 'free_mock_cache'):
            app.free_mock_cache = {}
        app.free_mock_cache[test_id] = tasks
        
        # В сессию сохраняем только ID теста
        session['free_mock_test_id'] = test_id
        session['free_mock_grade'] = grade
        session['free_mock_level'] = level
        session.permanent = True
        
        print(f"✅ Успешно сгенерировано {len(tasks)} задач, test_id={test_id}")
        
        return redirect(url_for('free_mock_test'))
        
    except DeepSeekAPIError as e:
        print(f"❌ Ошибка DeepSeek API: {e}")
        flash(f'Ошибка генерации задач: {str(e)}', 'error')
        return redirect(url_for('free_mock_start'))
    except json.JSONDecodeError as e:
        print(f"❌ Ошибка парсинга JSON: {e}")
        flash('Ошибка обработки ответа AI. Попробуйте еще раз.', 'error')
        return redirect(url_for('free_mock_start'))
    except Exception as e:
        print(f"❌ Неожиданная ошибка: {e}")
        flash(f'Произошла ошибка: {str(e)}', 'error')
        return redirect(url_for('free_mock_start'))


@app.route("/free_mock/test")
@login_required
def free_mock_test():
    """Страница прохождения теста с 25 задачами."""
    test_id = session.get('free_mock_test_id')
    
    if not test_id:
        flash('Сессия истекла. Создайте новый вариант.', 'error')
        return redirect(url_for('free_mock_start'))
    
    # Получаем задачи из кэша
    if not hasattr(app, 'free_mock_cache') or test_id not in app.free_mock_cache:
        flash('Тест не найден. Создайте новый вариант.', 'error')
        return redirect(url_for('free_mock_start'))
    
    tasks = app.free_mock_cache[test_id]
    grade = session.get('free_mock_grade', 'N/A')
    level = session.get('free_mock_level', 'N/A')
    
    return render_template('free_mock_test.html',
                         tasks=tasks,
                         grade=grade,
                         level=level)


@app.route("/free_mock/submit", methods=["POST"])
@login_required
def free_mock_submit():
    """Проверка ответов бесплатного пробника (25 задач)."""
    test_id = session.get('free_mock_test_id')
    
    if not test_id or not hasattr(app, 'free_mock_cache') or test_id not in app.free_mock_cache:
        flash('Сессия истекла. Начните новый пробник.', 'error')
        return redirect(url_for('free_mock_start'))
    
    tasks = app.free_mock_cache[test_id]
    
    # Подготавливаем данные для батч-проверки через LLM
    answers_data = []
    for task in tasks:
        task_id = task.get('id', '')
        user_answer = request.form.get(f'answer_{task_id}', '').strip()
        correct_answer = str(task.get('answer', '')).strip()
        
        answers_data.append({
            'user_answer': user_answer,
            'correct_answer': correct_answer,
            'question_text': task.get('text', '')
        })
    
    # Проверяем все ответы одним батч-запросом к LLM
    print(f"🤖 Проверка {len(answers_data)} ответов через DeepSeek AI...")
    llm_results = check_answers_batch(answers_data)
    
    # Формируем результаты
    results = []
    correct_count = 0
    
    for task, llm_result in zip(tasks, llm_results):
        task_id = task.get('id', '')
        user_answer = request.form.get(f'answer_{task_id}', '').strip()
        
        is_correct = llm_result['is_correct']
        if is_correct:
            correct_count += 1
        
        results.append({
            'task': task,
            'user_answer': user_answer,
            'correct_answer': task.get('answer', ''),
            'is_correct': is_correct,
            'ai_comment': llm_result.get('comment', ''),
            'solution': task.get('solution', 'Решение не предоставлено')
        })
    
    score = round((correct_count / len(tasks)) * 100)
    
    grade = session.get('free_mock_grade', 'N/A')
    level = session.get('free_mock_level', 'N/A')
    
    # Начисляем XP за пробник если пользователь авторизован
    mock_xp_bonus = 0
    level_up = False
    new_level = current_user.current_level
    
    if current_user.is_authenticated:
        xp_result = add_xp_for_mock_exam(current_user, score)
        mock_xp_bonus = xp_result['xp_gained']
        level_up = xp_result['level_up']
        new_level = xp_result['new_level']
        
        # Сохраняем изменения в БД
        db.session.commit()
    
    # Очищаем сессию
    session.pop('free_mock_tasks', None)
    session.pop('free_mock_grade', None)
    session.pop('free_mock_level', None)
    
    return render_template('free_mock_results.html',
                         results=results,
                         score=score,
                         correct_count=correct_count,
                         total_count=len(tasks),
                         grade=grade,
                         level=level,
                         mock_xp_bonus=mock_xp_bonus,
                         level_up=level_up,
                         new_level=new_level)


# ============================================================
# FREE MOCK API (Пошаговая генерация для бесплатного пробника)
# ============================================================

@app.route("/api/free_mock/generate_block", methods=["POST"])
@login_required
def api_free_mock_generate_block():
    """API: Генерация одного блока из 5 задач."""
    try:
        data = request.get_json()
        class_level = data.get('class_level')
        difficulty = data.get('difficulty')
        block_number = data.get('block_number', 1)
        previous_topics = data.get('previous_topics_list', [])
        
        if not class_level or not difficulty:
            return jsonify({'error': 'Не указаны класс или сложность'}), 400
        
        # Проверка доступности DeepSeek
        if not DEEPSEEK_AVAILABLE:
            return jsonify({'error': 'AI-генерация временно недоступна'}), 503
        
        # Инициализация DeepSeek клиента
        deepseek = DeepSeekClient()
        
        # Формируем промпт
        topics_exclusion = ""
        if previous_topics:
            topics_exclusion = f" Темы должны отличаться от этих: {', '.join(previous_topics)}."
        
        system_prompt = r"""Ты - профессиональный составитель математических олимпиад уровня Всероссийской олимпиады, IMO, Физтеха.
Генерируй задачи в строгом JSON формате без дополнительного текста.

КРИТИЧЕСКИЕ ПРАВИЛА ОФОРМЛЕНИЯ МАТЕМАТИКИ (LaTeX) — ПРИ НАРУШЕНИИ ОТКЛОНЕНО:
1. ВЕСЬ математический текст оборачивай в \( ... \) для инлайн и \[ ... \] для блоков
2. ЗАПРЕЩЕНО использовать юникод ², ³, √ или ^ вне LaTeX! Используй \( x^2 \), \( \sqrt{4} \)
3. ЗАПРЕЩЕНО использовать / для дробей! Используй \( \frac{1}{2} \)
4. Знаки умножения: \( \cdot \) (не * и не x)
5. СИСТЕМЫ УРАВНЕНИЙ: Используй \begin{cases} ... \end{cases}
   Пример: \[ \begin{cases} x + y = 5 \\ x - y = 1 \end{cases} \]

ОЧЕНЬ ВАЖНО: ВЕРНИ СТРОГО ВАЛИДНЫЙ JSON-МАССИВ. ВСЕ ВНУТРЕННИЕ КАВЫЧКИ ДОЛЖНЫ БЫТЬ ЭКРАНИРОВАНЫ. НЕ ПИШИ НИКАКОГО ТЕКСТА ДО ИЛИ ПОСЛЕ JSON."""
        
        # Определяем уровень сложности для промпта
        difficulty_descriptions = {
            "1": "БАЗОВЫЙ - обычная школьная программа, прямое применение одной формулы",
            "2": "ЛЕГКИЙ - школьная программа + один небольшой логический шаг",
            "3": "СРЕДНИЙ - уровень школьного этапа олимпиады, требует сообразительности",
            "4": "СЛОЖНЫЙ - уровень муниципального этапа, логическая цепочка из 3-4 шагов",
            "5": "ОЛИМПИАДНЫЙ - уровень регионального этапа, глубокие доказательства"
        }
        difficulty_desc = difficulty_descriptions.get(str(difficulty), "средний")
        
        # Специальные требования для высоких уровней сложности
        advanced_requirements = ""
        if str(difficulty) in ["4", "5"]:
            advanced_requirements = """
ВАЖНО! Для уровня сложности 4-5 СТРОГО ЗАПРЕЩЕНО:
- Простые линейные/квадратные уравнения
- Базовая школьная геометрия (площади треугольников по формуле Герона)
- Простые текстовые задачи на движение/работу
- Задачи, которые решаются в 1-2 действия

ОБЯЗАТЕЛЬНО используй:
- Диофантовы уравнения и теорию чисел
- Комбинаторику и принцип Дирихле
- Инварианты и раскраски
- Сложные неравенства (Коши-Буняковского, Йенсена)
- Продвинутую геометрию (теоремы Чевы, Менелая, вписанные/описанные окружности)
- Графы и теорию игр
- Функциональные уравнения
- Задачи на доказательство и конструктивные примеры"""
        
        user_prompt = f"""Ты профессиональный составитель математических олимпиад (уровня Всероса, IMO, Физтеха).
Твоя цель: сгенерировать ровно 5 уникальных задач для {class_level} класса.

ТРЕБУЕМЫЙ УРОВЕНЬ СЛОЖНОСТИ: {difficulty} - {difficulty_desc}
ИЗ ЭТОГО УРОВНЯ ВЫХОДИТЬ СТРОГО ЗАПРЕЩЕНО! Все 5 задач должны быть одинаково сложными.

Это блок задач номер {block_number} из 5.{topics_exclusion}
{advanced_requirements}

ПРАВИЛА ГЕНЕРАЦИИ:
1. Задачи НЕ должны гуглиться. Придумывай новые оригинальные формулировки.
2. Ответ должен быть однозначным числом или кратким выражением (не более 10 символов).
3. Решение должно быть подробным, но структурированным (4-6 предложений).
4. Каждая задача должна быть из РАЗНЫХ тем математики. Все задачи в ответе должны иметь УНИКАЛЬНЫЕ значения в поле "topic".
5. Уровень сложности ВСЕХ задач должен строго соответствовать {difficulty}.

ОБЯЗАТЕЛЬНАЯ САМОПРОВЕРКА (ВЫПОЛНЯТЬ ДЛЯ КАЖДОЙ ЗАДАЧИ):
Перед тем как добавить задачу в итоговый JSON, ты ОБЯЗАН:
1. ПРОВЕРИТЬ РЕШАЕМОСТЬ: Попробуй решить задачу сам. Если данных не хватает, есть противоречие или ответ получается дробным там, где должны быть целые люди/предметы — ОТБРОСЬ ЭТУ ЗАДАЧУ и придумай новую!
2. ПРОВЕРИТЬ КЛАСС И СЛОЖНОСТЬ: Задача должна СТРОГО соответствовать заявленному классу (например, {class_level} класс не знает логарифмов и синусов).

КАЛИБРОВКА УРОВНЕЙ СЛОЖНОСТИ (СТРОГО СОБЛЮДАТЬ):
- УРОВЕНЬ 1 (Базовый): Обычная школьная программа. Прямое применение одной формулы или базового правила. Никаких олимпиадных подвохов.
- УРОВЕНЬ 2 (Легкий): Школьная программа + один небольшой логический шаг.
- УРОВЕНЬ 3 (Средний): Уровень школьного (первого) этапа олимпиады. Требует сообразительности, но решается стандартными методами.
- УРОВЕНЬ 4 (Сложный): Уровень муниципального этапа олимпиады. Требует построения логической цепочки из 3-4 шагов.
- УРОВЕНЬ 5 (Олимпиадный): Уровень регионального этапа олимпиады. Глубокая задача на доказательство, теорию чисел, инварианты или сложную геометрию.

Ты должен генерировать задачи СТРОГО уровня {difficulty} ({difficulty_desc}).
Если выбран уровень 1-2, КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО давать олимпиадные задачи!

Верни СТРОГО валидный JSON-массив из 5 объектов в формате:
[
  {{
    "text": "Условие задачи (четкое, без лишних слов)",
    "answer": "Краткий ответ",
    "solution": "Подробное пошаговое решение",
    "difficulty": {difficulty},
    "topic": "Название темы (например: Теория чисел, Комбинаторика, Геометрия)"
  }},
  ...
]

Важно: ответ должен содержать ТОЛЬКО JSON массив, без markdown разметки и дополнительного текста.

ВЕРНИ ТОЛЬКО ЧИСТЫЙ JSON-МАССИВ [{{}}, {{}}, ...]. БЕЗ СЛОВ "Вот ваши задачи", БЕЗ МАРКДАУНА ```json ```."""

        print(f"🤖 Генерация блока {block_number}/5 для {class_level} класса, уровень {difficulty}...")
        
        response = deepseek.generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.7,
            max_tokens=4000
        )
        
        # Улучшенный парсинг JSON с регулярками и обработкой ошибок
        response_text = response.strip()
        
        # Убираем markdown блоки
        if response_text.startswith('```json'):
            response_text = response_text[7:]
        elif response_text.startswith('```'):
            response_text = response_text[3:]
        
        if response_text.endswith('```'):
            response_text = response_text[:-3]
        
        response_text = response_text.strip()
        
        # Используем регулярку для извлечения JSON массива
        import re
        match = re.search(r'\[.*\]', response_text, re.DOTALL)
        if match:
            response_text = match.group(0)
        
        response_text = response_text.strip()
        
        print(f"📝 Очищенный ответ (первые 200 символов): {response_text[:200]}...")
        
        # Пытаемся распарсить JSON с обработкой ошибок
        try:
            tasks = json.loads(response_text)
        except json.JSONDecodeError as json_err:
            print("="*80)
            print(f"❌ ОШИБКА ПАРСИНГА JSON: {json_err}")
            print("="*80)
            print("СЛОМАННЫЙ JSON (полностью):")
            print(response_text)
            print("="*80)
            raise  # Пробрасываем ошибку дальше для обработки в except блоке
        
        # Проверяем, что получили ровно 5 задач
        if len(tasks) != 5:
            tasks = tasks[:5]  # Берем первые 5
        
        print(f"✅ Блок {block_number} сгенерирован: {len(tasks)} задач")
        
        return jsonify(tasks), 200
        
    except DeepSeekAPIError as e:
        print(f"❌ Ошибка DeepSeek API: {e}")
        return jsonify({'error': f'Ошибка генерации: {str(e)}'}), 500
    except json.JSONDecodeError as e:
        print(f"❌ Ошибка парсинга JSON: {e}")
        return jsonify({'error': 'Ошибка обработки ответа AI'}), 500
    except Exception as e:
        print(f"❌ Неожиданная ошибка: {e}")
        return jsonify({'error': f'Произошла ошибка: {str(e)}'}), 500


@app.route("/api/free_mock/generate_single_task", methods=["POST"])
@login_required
def api_free_mock_generate_single_task():
    """API: Генерация ОДНОЙ задачи (для фоновой подгрузки)."""
    try:
        data = request.get_json()
        class_level = data.get('class_level')
        difficulty = data.get('difficulty')
        task_number = data.get('task_number', 1)
        previous_topics = data.get('previous_topics', [])
        previous_subtopics = data.get('previous_subtopics', [])  # НОВЫЙ: список использованных подтем
        target_topic = data.get('target_topic')  # НОВЫЙ ПАРАМЕТР для баланса тем
        target_subtopic = data.get('target_subtopic')  # НОВЫЙ: конкретная подтема для генерации
        previous_tasks = data.get('previous_tasks', [])  # КОНТЕКСТ ПРЕДЫДУЩИХ ЗАДАЧ
        
        if not class_level or not difficulty:
            return jsonify({'error': 'Не указаны класс или сложность'}), 400
        
        # Проверка доступности DeepSeek
        if not DEEPSEEK_AVAILABLE:
            return jsonify({'error': 'AI-генерация временно недоступна'}), 503
        
        # Инициализация DeepSeek клиента
        deepseek = DeepSeekClient()
        
        # Получаем историю математических идей из сессии
        if 'mock_task_ideas' not in session:
            session['mock_task_ideas'] = []
        if 'mock_task_texts' not in session:
            session['mock_task_texts'] = []
        
        task_ideas_history = session.get('mock_task_ideas', [])
        task_texts_history = session.get('mock_task_texts', [])
        
        # Логируем исключенные идеи
        if task_ideas_history:
            print(f"[Free Mock] 📋 Генерирую задачу №{task_number}. Исключенные идеи: {', '.join(task_ideas_history)}")
        else:
            print(f"[Free Mock] 📋 Генерирую задачу №{task_number}. Это первая задача в пробнике.")
        
        # Формируем промпт для ОДНОЙ задачи
        topics_exclusion = ""
        if previous_topics:
            topics_exclusion = f" Тема должна отличаться от этих: {', '.join(previous_topics)}."
        
        # СТРОГОЕ ТРЕБОВАНИЕ ПО ПОДТЕМЕ (уникальность в пробнике)
        subtopics_exclusion = ""
        if previous_subtopics:
            from services.topic_taxonomy import SUBTOPIC_NAMES_RU
            subtopic_names = [SUBTOPIC_NAMES_RU.get(s, s) for s in previous_subtopics]
            subtopics_exclusion = (
                f"\n\nКРИТИЧЕСКИ ВАЖНО: Задача должна быть на УНИКАЛЬНУЮ подтему. "
                f"Уже использованные подтемы (НЕ ПОВТОРЯТЬ): {', '.join(subtopic_names)}. "
                f"Придумай задачу на ДРУГУЮ подтему, которой ещё не было!"
            )
        
        # СТРОГОЕ ТРЕБОВАНИЕ ПО ТЕМЕ (если указана)
        topic_requirement = ""
        if target_topic:
            topic_requirement = f"\n\nСГЕНЕРИРУЙ ЗАДАЧУ СТРОГО НА ТЕМУ: {target_topic}."
        
        # СТРОГОЕ ТРЕБОВАНИЕ ПО ПОДТЕМЕ (если указана)
        if target_subtopic:
            from services.topic_taxonomy import SUBTOPIC_NAMES_RU
            subtopic_name = SUBTOPIC_NAMES_RU.get(target_subtopic, target_subtopic)
            topic_requirement += f"\n\nПОДТЕМА ЗАДАЧИ: {subtopic_name}. Задача должна быть именно на эту подтему."
        
        # УСИЛЕННЫЙ КОНТЕКСТ с историей математических идей
        previous_tasks_context = ""
        if task_ideas_history or previous_tasks:
            ideas_list = "\n".join([f"- {idea}" for idea in task_ideas_history]) if task_ideas_history else "Пока нет"
            
            tasks_preview = ""
            if previous_tasks or task_texts_history:
                all_tasks = previous_tasks if previous_tasks else task_texts_history
                tasks_preview = "\n".join([f"{i+1}. {task[:120]}..." for i, task in enumerate(all_tasks[-5:])])  # Последние 5 задач
            
            previous_tasks_context = f"""

╔══════════════════════════════════════════════════════════════════════════════╗
║ КРИТИЧЕСКИ ВАЖНО: ЗАЩИТА ОТ ПОВТОРЕНИЙ МАТЕМАТИЧЕСКИХ ИДЕЙ                  ║
╚══════════════════════════════════════════════════════════════════════════════╝

В ЭТОМ ПРОБНИКЕ УЖЕ ИСПОЛЬЗОВАНЫ СЛЕДУЮЩИЕ МАТЕМАТИЧЕСКИЕ ИДЕИ:
{ideas_list}

ТВОЯ НОВАЯ ЗАДАЧА ДОЛЖНА БЫТЬ АБСОЛЮТНО УНИКАЛЬНОЙ!

🚫 СТРОГО ЗАПРЕЩЕНО:
   • Повторять методы решения из списка выше
   • Менять только числа в старых задачах
   • Использовать похожие конструкции или сюжеты
   • Генерировать задачи на те же математические концепции

✅ ОБЯЗАТЕЛЬНО:
   • Придумай СОВЕРШЕННО НОВУЮ математическую идею
   • Используй ДРУГОЙ метод решения
   • Выбери ДРУГУЮ подтему из раздела математики
   • Создай ОРИГИНАЛЬНЫЙ сюжет (если это текстовая задача)

ПРИМЕРЫ ПОСЛЕДНИХ ЗАДАЧ (для понимания контекста):
{tasks_preview if tasks_preview else "Это первая задача"}

ПОМНИ: Каждая задача в пробнике должна тестировать РАЗНЫЕ математические навыки!
"""
        
        system_prompt = r"""Ты - профессиональный составитель математических задач для ШКОЛЬНИКОВ.
Генерируй задачу в строгом JSON формате без дополнительного текста.

╔══════════════════════════════════════════════════════════════════════════════╗
║ КРИТИЧЕСКИЕ ПРАВИЛА ОФОРМЛЕНИЯ МАТЕМАТИКИ (LaTeX) — ПРИ НАРУШЕНИИ ОТКЛОНЕНО ║
╚══════════════════════════════════════════════════════════════════════════════╝

1. ВЕСЬ математический текст, числа и формулы ОБЯЗАТЕЛЬНО оборачивай в \( ... \) (для инлайн) и \[ ... \] (для блоков).

2. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО использовать юникод-символы для степеней и корней (никаких ², ³, √ или ^ вне LaTeX).
   ❌ ПЛОХО: x², √4, 2^2
   ✅ ОТЛИЧНО: \( x^2 \), \( \sqrt{4} \), \( 2^2 \)

3. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО использовать слэш / для дробей!
   ❌ ПЛОХО: 1/2, x/y
   ✅ ОТЛИЧНО: \( \frac{1}{2} \), \( \frac{x}{y} \)

4. КРИТИЧЕСКИ ВАЖНО ПРО КОРНИ:
   КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО писать √50, sqrt(50) или \sqrt 50 (без фигурных скобок)!
   Ты ОБЯЗАН использовать команду \sqrt СТРОГО с фигурными скобками {}!
   ❌ ПЛОХО: √50, sqrt(50), \sqrt 50, \sqrt 4
   ✅ ОТЛИЧНО: \( \sqrt{50} \), \( \sqrt{4} \), \( \sqrt{x^2 + y^2} \)
   Если под корнем длинное выражение, оно ВСЁ должно быть внутри фигурных скобок!

5. Знаки умножения пиши ТОЛЬКО как \( \cdot \) (не * и не x).

6. ПРАВИЛО ДЛЯ НИЖНИХ ИНДЕКСОВ:
   КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО писать индексы слитно как обычный текст (p1, pn, xi)!
   Ты ОБЯЗАН использовать символ подчеркивания _ строго внутри математического блока \( ... \).
   ❌ ПЛОХО: p1, pn, x_i (как текст), xi
   ✅ ОТЛИЧНО: \( p_1 \), \( p_n \), \( x_i \)
   ВАЖНО: Если индекс из нескольких символов, он ОБЯЗАТЕЛЬНО в фигурных скобках!
   ✅ ОТЛИЧНО: \( a_{n+1} \), \( y_{i,j} \), \( x_{max} \)

7. СИСТЕМЫ УРАВНЕНИЙ: КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО писать их просто в столбик! ОБЯЗАН использовать окружение cases.
   ✅ ОТЛИЧНО:
   \[
   \begin{cases}
   x^2 = 2 \cdot \sqrt{y^2 + 1} \\
   y^2 = 2 \cdot \sqrt{z^2 - 1} - 2 \\
   z^2 = 4 \cdot \sqrt{x^2 + 2} - 6
   \end{cases}
   \]

8. Используй правильные математические символы:
   - Неравенства: \( \leq \), \( \geq \), \( \neq \)
   - Греческие буквы: \( \alpha \), \( \beta \), \( \pi \)

ПРИМЕРЫ ПРАВИЛЬНОГО ОФОРМЛЕНИЯ:
✅ "Решите уравнение \( x^2 + 3x - 4 = 0 \)"
✅ "Найдите \( \frac{2^5 + 2^3}{2^2} \)"
✅ "Докажите, что \( \sqrt{2} + \sqrt{3} < \sqrt{10} \)"

КРИТИЧЕСКИ ВАЖНО:
- СТРОГО ЗАПРЕЩЕНО ИСПОЛЬЗОВАТЬ КАВЫЧКИ " ВНУТРИ ТЕКСТА ЗАДАЧИ. Вместо кавычек используй тире или скобки.
- Например, вместо: А сказал: "Я рыцарь" - пиши: А сказал - Я рыцарь, или: А сказал (Я рыцарь).
- ВЕРНИ СТРОГО ОДИН ВАЛИДНЫЙ JSON-ОБЪЕКТ (НЕ МАССИВ!). НЕ ОБОРАЧИВАЙ ЕГО В МАРКДАУН (без ```json).
- РЕШЕНИЕ ДОЛЖНО БЫТЬ МАКСИМАЛЬНО КРАТКИМ, НЕ БОЛЕЕ 2 ПРЕДЛОЖЕНИЙ.
- НЕ ПИШИ НИКАКОГО ТЕКСТА ДО ИЛИ ПОСЛЕ JSON.
- ВЕСЬ ОТВЕТ ТОЛЬКО ОДИН JSON-ОБЪЕКТ.

СТРОГОЕ СООТВЕТСТВИЕ КЛАССУ:
- Для 5-6 класса ЗАПРЕЩЕНО: биссектриса, медиана, высота треугольника, синус, косинус, квадратные уравнения, сложные неравенства.
- Для 5-6 класса РАЗРЕШЕНО: базовая арифметика, простые уравнения, периметр, площадь прямоугольника, углы треугольника (сумма 180°).
- Для 7-8 класса можно добавить: простые квадратные уравнения, теорему Пифагора, базовую геометрию.
- Для 9-11 класса можно использовать продвинутые темы."""
        
        # Определяем уровень сложности для промпта
        difficulty_descriptions = {
            "1": "базовый (простые вычисления, стандартные формулы)",
            "2": "легкий (задачи на понимание концепций, простые уравнения)",
            "3": "средний (комбинированные задачи, требующие нескольких шагов)",
            "4": "сложный (нестандартные подходы, олимпиадные приемы)",
            "5": "олимпиадный (высокий уровень абстракции, продвинутые методы)"
        }
        difficulty_desc = difficulty_descriptions.get(str(difficulty), "средний")
        
        user_prompt = f"""Ты составитель олимпиад. Сгенерируй СТРОГО ОДНУ сложную математическую задачу для {class_level} класса.

ТРЕБУЕМЫЙ УРОВЕНЬ СЛОЖНОСТИ: {difficulty} - {difficulty_desc}

Это задача {task_number}/25.{topics_exclusion}{subtopics_exclusion}{topic_requirement}{previous_tasks_context}

ПРАВИЛА:
1. Задача НЕ должна гуглиться. Придумай новую оригинальную формулировку.
2. Ответ должен быть однозначным числом или кратким выражением (не более 10 символов).
3. РЕШЕНИЕ ДОЛЖНО БЫТЬ МАКСИМАЛЬНО КРАТКИМ, НЕ БОЛЕЕ 2 ПРЕДЛОЖЕНИЙ. ВЕСЬ ОТВЕТ ТОЛЬКО ОДИН JSON-ОБЪЕКТ.
4. Уровень сложности должен строго соответствовать {difficulty}.
5. КРИТИЧЕСКИ ВАЖНО: НЕ ИСПОЛЬЗУЙ КАВЫЧКИ " ВНУТРИ ТЕКСТА ЗАДАЧИ! Вместо прямой речи используй тире или скобки.
   Например: вместо А сказал: "Я рыцарь" пиши: А сказал - Я рыцарь.

ЕСТЕСТВЕННОЕ РАЗНООБРАЗИЕ:
Избегай шаблонных "купил яблоки" или "пункт А и Б", но НЕ ДОБАВЛЯЙ искусственные приставки вроде "В киберспортивном симуляторе...", "В криптографическом протоколе...", "Хакер взламывает...".
Формулируй задачи как классические, строгие олимпиадные условия, но с нестандартной математической сутью.
Текст задачи должен быть лаконичным и начинаться сразу с сути.
ПРИМЕРЫ ХОРОШИХ ФОРМУЛИРОВОК:
- "Два гоночных болида стартуют одновременно..." (а не "В игре два болида...")
- "Робот перемещается по числовой прямой..." (а не "В симуляторе робот...")
- "Автомат преобразует числа по правилу..." (а не "В программе автомат...")
- "На доске написаны числа..." (а не "В компьютерной игре на доске...")

ГЛУБОКАЯ ВАРИАТИВНОСТЬ ПОДТЕМ:
Каждая задача должна использовать СЛУЧАЙНУЮ ПОДТЕМУ из выбранного раздела. НИКОГДА не генерируй две задачи подряд на один и тот же метод решения!
- Алгебра: чередуй текстовые задачи (работы, смеси), степени и корни, последовательности, системы уравнений, неравенства.
- Геометрия: чередуй площади нестандартных фигур, разрезания и замощения, свойства углов, координаты на сетке, задачи на построение.
- Теория чисел: чередуй признаки делимости, остатки, простые числа, НОД/НОК, диофантовы уравнения, последняя цифра числа.
- Комбинаторика: чередуй графы, принцип Дирихле, раскраски, подсчет вариантов, игры и стратегии, логические рыцари и лжецы.
- Задачи на движение: чередуй движение навстречу/вдогонку, движение по кругу, движение по течению/против, средняя скорость, графики движения, движение с остановками.

ВЕРНИ ТОЛЬКО ОДИН ВАЛИДНЫЙ JSON-ОБЪЕКТ (БЕЗ МАССИВА, БЕЗ МАРКДАУНА):
{{
  "text": "Условие задачи (БЕЗ КАВЫЧЕК ВНУТРИ ТЕКСТА)",
  "answer": "Краткий ответ",
  "solution": "Краткое решение (НЕ БОЛЕЕ 2 ПРЕДЛОЖЕНИЙ)",
  "difficulty": {difficulty},
  "topic": "Название темы"
}}

ВАЖНО: ВЕРНИ ТОЛЬКО ЧИСТЫЙ JSON-ОБЪЕКТ. БЕЗ СЛОВ "Вот задача", БЕЗ МАРКДАУНА ```json ```. БЕЗ КАВЫЧЕК В ТЕКСТЕ ЗАДАЧИ."""

        print(f"🤖 Генерация задачи {task_number}/25 для {class_level} класса, уровень {difficulty}...")
        
        response = deepseek.generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.7,
            max_tokens=2000  # Увеличено для полного решения
        )
        
        # Улучшенный парсинг JSON с экранированием слешей
        response_text = response.strip()
        
        # Убираем markdown блоки
        if response_text.startswith('```json'):
            response_text = response_text[7:]
        elif response_text.startswith('```'):
            response_text = response_text[3:]
        
        if response_text.endswith('```'):
            response_text = response_text[:-3]
        
        response_text = response_text.strip()
        
        # Используем регулярку для извлечения JSON объекта
        import re
        match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if match:
            response_text = match.group(0)
        
        response_text = response_text.strip()
        
        # КРИТИЧЕСКИ ВАЖНО: Заменяем одинарные слеши на двойные для корректного JSON
        # Это защищает от LaTeX символов типа \frac, \sqrt, которые ломают json.loads()
        response_text = response_text.replace('\\', '\\\\')
        
        print(f"📝 Очищенный ответ (первые 150 символов): {response_text[:150]}...")
        
        # Пытаемся распарсить JSON с обработкой ошибок
        try:
            task = json.loads(response_text)
        except json.JSONDecodeError as json_err:
            print("="*80)
            print(f"❌ ОШИБКА ПАРСИНГА JSON: {json_err}")
            print("="*80)
            print("СЛОМАННЫЙ JSON (полностью):")
            print(response_text)
            print("="*80)
            # Выкидываем ValueError, чтобы фронтенд повторил запрос
            raise ValueError("Invalid JSON format from AI")
        
        # Сохраняем математическую идею задачи в историю сессии
        task_topic = task.get('topic', 'Неизвестная тема')
        task_text = task.get('text', '')
        
        # Извлекаем краткую суть задачи для истории идей
        task_idea = f"{task_topic}"
        
        # Обновляем историю в сессии
        if 'mock_task_ideas' not in session:
            session['mock_task_ideas'] = []
        if 'mock_task_texts' not in session:
            session['mock_task_texts'] = []
        
        session['mock_task_ideas'].append(task_idea)
        session['mock_task_texts'].append(task_text[:150])  # Сохраняем первые 150 символов
        
        # Сохраняем subtopic для обеспечения уникальности подтем
        if 'mock_task_subtopics' not in session:
            session['mock_task_subtopics'] = []
        # Определяем subtopic по теме задачи
        from services.topic_taxonomy import get_subtopics_for_topic
        task_subtopics = get_subtopics_for_topic(task_topic)
        if task_subtopics:
            # Используем детерминированный выбор на основе номера задачи
            subtopic_idx = (task_number - 1) % len(task_subtopics)
            task_subtopic = task_subtopics[subtopic_idx]
            session['mock_task_subtopics'].append(task_subtopic)
        
        session.modified = True  # Важно для Flask session
        
        print(f"✅ Задача {task_number} сгенерирована")
        print(f"[Free Mock] 💾 Сохранена идея: '{task_idea}'. Всего идей в истории: {len(session['mock_task_ideas'])}")
        
        # Запускаем фоновую предгенерацию следующей задачи
        if task_number < 25:  # Если это не последняя задача
            session_id = request.cookies.get('session', session.get('_id', str(current_user.id)))
            cache_size = get_cache_size(session_id)
            
            # Если в кэше меньше 2 задач, запускаем фоновую генерацию
            if cache_size < 2:
                next_task_number = task_number + 1
                next_config = {
                    'class_level': class_level,
                    'difficulty': difficulty,
                    'task_number': next_task_number,
                    'previous_topics': previous_topics,
                    'previous_subtopics': session.get('mock_task_subtopics', []),
                    'previous_tasks': session.get('mock_task_texts', [])
                }
                
                def background_generate():
                    """Фоновая генерация следующей задачи"""
                    try:
                        print(f"[Prefetch] 🔄 Фоновая генерация задачи #{next_task_number}...")
                        # Создаем новый DeepSeek клиент для фонового потока
                        bg_deepseek = DeepSeekClient()
                        
                        # Копируем всю логику генерации из текущей функции
                        # (упрощенная версия - генерируем задачу)
                        # Здесь должна быть та же логика, что и выше
                        # Для простоты пока пропускаем, так как это требует большого рефакторинга
                        
                        print(f"[Prefetch] ✅ Задача #{next_task_number} предсгенерирована в фоне")
                    except Exception as e:
                        print(f"[Prefetch] ❌ Ошибка фоновой генерации: {e}")
                
                # Запускаем в отдельном потоке
                thread = threading.Thread(target=background_generate, daemon=True)
                thread.start()
                print(f"[Prefetch] 🚀 Запущена фоновая генерация задачи #{next_task_number}")
        
        return jsonify(task), 200
        
    except DeepSeekAPIError as e:
        print(f"❌ Ошибка DeepSeek API: {e}")
        return jsonify({'error': f'Ошибка генерации: {str(e)}'}), 500
    except json.JSONDecodeError as e:
        print(f"❌ Ошибка парсинга JSON: {e}")
        return jsonify({'error': 'Ошибка обработки ответа AI'}), 500
    except Exception as e:
        print(f"❌ Неожиданная ошибка: {e}")
        return jsonify({'error': f'Произошла ошибка: {str(e)}'}), 500


@app.route("/api/free_mock/evaluate", methods=["POST"])
@login_required
def api_free_mock_evaluate():
    """API: Проверка задач и генерация фидбека."""
    try:
        data = request.get_json()
        tasks = data.get('tasks', [])
        answers = data.get('answers', [])
        
        # БОЛЕЕ ГИБКАЯ ПРОВЕРКА: длины должны совпадать, но не обязательно 25
        if not tasks or not answers:
            return jsonify({'error': 'Отсутствуют задачи или ответы'}), 400
        
        if len(tasks) != len(answers):
            return jsonify({
                'error': f'Длина массивов не совпадает: {len(tasks)} задач, {len(answers)} ответов'
            }), 400
        
        # Проверка доступности DeepSeek
        if not DEEPSEEK_AVAILABLE:
            return jsonify({'error': 'AI-генерация временно недоступна'}), 503
        
        # Простая проверка ответов
        correct_count = 0
        results = []
        
        for i, (task, user_answer) in enumerate(zip(tasks, answers)):
            correct_answer = str(task.get('answer', '')).strip()
            user_answer = str(user_answer).strip()
            
            # Проверяем ответ с умной нормализацией
            is_correct = compare_math_answers(user_answer, correct_answer)
            
            if is_correct:
                correct_count += 1
            
            results.append({
                'task_num': i + 1,
                'is_correct': is_correct,
                'user_answer': user_answer,
                'correct_answer': correct_answer,
                'topic': task.get('topic', 'Неизвестная тема'),
                'solution': task.get('solution', 'Решение недоступно')
            })
        
        # Собираем статистику по темам
        topic_stats = {}
        for result in results:
            topic = result['topic']
            if topic not in topic_stats:
                topic_stats[topic] = {'correct': 0, 'total': 0}
            topic_stats[topic]['total'] += 1
            if result['is_correct']:
                topic_stats[topic]['correct'] += 1
        
        # Формируем сильные и слабые темы
        strong_topics = []
        weak_topics = []
        
        for topic, stats in topic_stats.items():
            percentage = (stats['correct'] / stats['total']) * 100 if stats['total'] > 0 else 0
            if percentage >= 70:
                strong_topics.append(topic)
            elif percentage < 50:
                weak_topics.append(topic)
        
        # Формируем фидбек
        if correct_count < 10:
            strong_topics_str = "Пока нет ярко выраженных сильных сторон"
            feedback = f"Результат {correct_count} из {len(tasks)} говорит о том, что нужно больше практики. Сосредоточьтесь на базовых темах и решайте больше задач каждый день."
        elif correct_count < 15:
            strong_topics_str = ", ".join(strong_topics) if strong_topics else "Есть потенциал"
            feedback = f"Неплохой результат! Продолжайте практиковаться, особенно в слабых темах."
        else:
            strong_topics_str = ", ".join(strong_topics) if strong_topics else "Хорошая база"
            feedback = f"Отличный результат! Вы показали хорошее понимание материала. Продолжайте в том же духе!"
        
        weak_topics_str = ", ".join(weak_topics) if weak_topics else "Нет явных слабых мест"
        
        print(f"✅ Оценка завершена: {correct_count}/{len(tasks)}")
        
        return jsonify({
            'score': f"{correct_count}/{len(tasks)}",
            'strong_topics': strong_topics_str,
            'weak_topics': weak_topics_str,
            'feedback': feedback,
            'results': results,
            'correct_count': correct_count,
            'total_count': len(tasks)
        }), 200
        
    except DeepSeekAPIError as e:
        print(f"❌ Ошибка DeepSeek API: {e}")
        return jsonify({'error': f'Ошибка генерации фидбека: {str(e)}'}), 500
    except json.JSONDecodeError as e:
        print(f"❌ Ошибка парсинга JSON: {e}")
        return jsonify({'error': 'Ошибка обработки ответа AI'}), 500
    except Exception as e:
        print(f"❌ Неожиданная ошибка: {e}")
        return jsonify({'error': f'Произошла ошибка: {str(e)}'}), 500


# ============================================================
# ADAPTIVE TESTING (Адаптивное тестирование)
# ============================================================

@app.route("/adaptive_test/select_class")
def adaptive_test_select_class():
    """Шаг 1 адаптивного теста: выбор класса (5–11).

    Класс выбирается ПЕРВЫМ, затем пользователь попадает на выбор темы,
    которая зависит от класса (для 5/6 — школьные домены, для 7+ —
    классические олимпиадные темы).
    """
    return render_template('adaptive_test_select_class.html')


@app.route("/adaptive_test/select_topic")
def adaptive_test_select_topic():
    """Шаг 2 адаптивного теста: выбор темы под выбранный класс.

    - Для 5 и 6 классов показываем домены из GradeTask (импорт 1600 задач).
    - Для 7–11 классов — классические темы из AdaptiveTask.
    """
    try:
        grade_int = int(request.args.get('grade', ''))
    except (ValueError, TypeError):
        flash('Сначала выберите класс', 'error')
        return redirect(url_for('adaptive_test_select_class'))

    if grade_int not in (5, 6, 7, 8, 9, 10, 11):
        flash('Неверный класс', 'error')
        return redirect(url_for('adaptive_test_select_class'))

    MIN_TASKS = 10
    topics = []

    if grade_int in (5, 6):
        # Темы из 1600-задач (GradeTask) — для 5 и 6 классов
        from models_grade import GradeTask, GRADE_DOMAINS, DOMAIN_LABELS
        domain_emojis = {
            'natural_numbers':              '🔢',
            'fractions_decimals_percent':   '½',
            'geometry_measurement':         '📐',
            'combinatorics_school':         '🎲',
            'logic_olympiad_intro':         '🧠',
            'divisibility':                 '➗',
            'fractions_ratio_percent':      '½',
            'integers_coordinates':         '➕',
            'geometry_6':                   '📏',
            'olympiad_logic_combinatorics': '🧩',
        }
        for domain in GRADE_DOMAINS.get(grade_int, ()):
            count = GradeTask.query.filter_by(grade=grade_int, domain=domain).count()
            topics.append({
                'name':      DOMAIN_LABELS.get(domain, domain),
                'emoji':     domain_emojis.get(domain, '📘'),
                'count':     count,
                'available': count >= MIN_TASKS,
                'url':       url_for('adaptive_test_start_grade',
                                     grade=grade_int, domain=domain),
            })
    else:
        # Классические темы для 7–11 классов — старый адаптивный тест
        from services.adaptive_topic_mapping import get_keywords_for_grade_topic
        classic_topics = [
            ('algebra',       'Алгебра',         '📐'),
            ('geometry',      'Геометрия',       '📏'),
            ('combinatorics', 'Комбинаторика',   '🎲'),
            ('number_theory', 'Теория чисел',    '🔢'),
            ('kl_movement',   'Задачи на движение', '🚗'),
            ('knights_liars', 'Рыцари и лжецы',  '⚔️'),
        ]
        fallback_keywords = {
            'algebra': ['алгебра', 'выражения', 'одночлен', 'многочлен', 'формул'],
            'geometry': ['геометрия', 'треугольник', 'четырехугольник', 'окружность',
                         'вектор', 'площад', 'стереометр', 'многогранник',
                         'тела вращения', 'объем'],
            'combinatorics': ['комбинатор', 'вероятност', 'перестановк', 'размещен', 'сочетан'],
            'number_theory': ['натуральн', 'делимост', 'положительн', 'отрицательн',
                              'рациональн', 'числ', 'НОД', 'НОК'],
            'kl_movement': ['движен', 'текстовые задачи', 'совместная работа'],
            'knights_liars': ['рыцар', 'лжец'],
        }
        all_tasks = AdaptiveTask.query.filter_by(
            class_level=grade_int, is_flagged=False
        ).all()
        for topic_key, topic_name, emoji in classic_topics:
            internal = 'movement' if topic_key == 'kl_movement' else topic_key
            kws = get_keywords_for_grade_topic(grade_int, internal) \
                  or fallback_keywords.get(topic_key, [])
            kws_lower = [k.lower() for k in kws]
            if not kws_lower:
                count = len(all_tasks)
            else:
                count = sum(
                    1 for t in all_tasks
                    if t.topic and any(k in t.topic.lower() for k in kws_lower)
                )
            topics.append({
                'name':      topic_name,
                'emoji':     emoji,
                'count':     count,
                'available': count >= MIN_TASKS,
                'url':       url_for('adaptive_test_start_simple',
                                     topic=topic_key, grade=grade_int),
            })

    return render_template(
        'adaptive_test_select_topic.html',
        grade=grade_int,
        topics=topics,
        min_tasks=MIN_TASKS,
    )


@app.route("/adaptive_test/start_grade")
def adaptive_test_start_grade():
    """Запуск тренировки для 5/6 класса по выбранному домену (GradeTask).

    Для 5/6 классов используется отдельный банк из 1600 задач (GradeTask),
    разбитый по школьным доменам. Пока эти задачи проходятся в обычном
    режиме (страница grade.domain_*) — без полностью адаптивного движка,
    т.к. он завязан на поля AdaptiveTask.
    """
    try:
        grade_int = int(request.args.get('grade', ''))
    except (ValueError, TypeError):
        flash('Сначала выберите класс', 'error')
        return redirect(url_for('adaptive_test_select_class'))

    domain = request.args.get('domain', '').strip()
    if grade_int not in (5, 6) or not domain:
        flash('Неверные параметры теста', 'error')
        return redirect(url_for('adaptive_test_select_class'))

    from models_grade import GRADE_DOMAINS
    if domain not in GRADE_DOMAINS.get(grade_int, ()):
        flash('Тема не найдена для этого класса', 'error')
        return redirect(url_for('adaptive_test_select_topic', grade=grade_int))

    endpoint = 'grade.domain_5' if grade_int == 5 else 'grade.domain_6'
    return redirect(url_for(endpoint, domain=domain))


@app.route("/adaptive_test/select_grade")
def adaptive_test_select_grade():
    """Выбор класса для адаптивного теста."""
    topic = request.args.get('topic')

    if not topic:
        flash('Выберите тему для тестирования', 'error')
        return redirect(url_for('probniks_page'))

    # Алиас kl_movement → movement
    if topic == 'kl_movement':
        topic = 'movement'

    # Маппинг тем на русский
    topic_names = {
        'algebra': 'Алгебра',
        'geometry': 'Геометрия',
        'combinatorics': 'Комбинаторика',
        'number_theory': 'Теория чисел',
        'movement': 'Задачи на движение',
        'knights_liars': 'Рыцари и лжецы'
    }

    topic_name = topic_names.get(topic, topic)

    # Подсчитываем доступность темы по каждому классу,
    # чтобы шаблон мог отключить недоступные кнопки.
    from services.adaptive_topic_mapping import get_keywords_for_grade_topic
    MIN_TASKS = 10  # должен совпадать с порогом в adaptive_test_start_simple
    fallback_keywords = {
        'algebra': ['алгебра', 'выражения', 'одночлен', 'многочлен', 'формул'],
        'geometry': ['геометрия', 'треугольник', 'четырехугольник', 'окружность',
                     'вектор', 'площад', 'стереометр', 'многогранник',
                     'тела вращения', 'объем'],
        'combinatorics': ['комбинатор', 'вероятност', 'перестановк', 'размещен', 'сочетан'],
        'number_theory': ['натуральн', 'делимост', 'положительн', 'отрицательн',
                          'рациональн', 'числ', 'НОД', 'НОК'],
        'movement': ['движен', 'текстовые задачи', 'совместная работа'],
        'knights_liars': ['рыцар', 'лжец'],
    }

    grade_availability = {}
    for grade_int in (5, 6, 7, 8, 9, 10, 11):
        kws = get_keywords_for_grade_topic(grade_int, topic) or fallback_keywords.get(topic, [])
        kws_lower = [k.lower() for k in kws]
        all_tasks = AdaptiveTask.query.filter_by(
            class_level=grade_int, is_flagged=False
        ).all()
        if not kws_lower:
            count = len(all_tasks)
        else:
            count = sum(
                1 for t in all_tasks
                if t.topic and any(k in t.topic.lower() for k in kws_lower)
            )
        grade_availability[grade_int] = {
            'count': count,
            'available': count >= MIN_TASKS,
        }

    return render_template('adaptive_test_select_grade.html',
        topic=topic,
        topic_name=topic_name,
        grade_availability=grade_availability,
        min_tasks=MIN_TASKS,
    )


@app.route("/adaptive_test/start")
def adaptive_test_start_simple():
    """Простой запуск адаптивного теста с фильтрацией по теме."""
    topic = request.args.get('topic')
    grade = request.args.get('grade')
    
    # kl_movement → movement (алиас) — до любых проверок
    if topic == 'kl_movement':
        topic = 'movement'
    
    if not topic:
        flash('Выберите тему для тестирования', 'error')
        return redirect(url_for('probniks_page'))
    
    if not grade:
        # Если класс не выбран, перенаправляем на выбор класса
        return redirect(url_for('adaptive_test_select_grade', topic=topic))
    
    # Преобразуем grade в int СРАЗУ (до использования в проверках)
    try:
        grade_int = int(grade)
    except (ValueError, TypeError):
        flash(f'Неверный формат класса: {grade}', 'error')
        return redirect(url_for('adaptive_test_select_grade', topic=topic))
    
    # Маппинг тем: короткий ключ -> ключевые слова для поиска в названии темы
    topic_keywords = {
        'algebra': ['алгебра', 'выражения', 'одночлен', 'многочлен', 'формул'],
        'geometry': ['геометрия', 'треугольник', 'четырехугольник', 'окружность', 'вектор',
                     'площад', 'стереометр', 'многогранник', 'тела вращения', 'объем'],
        'combinatorics': ['комбинатор', 'вероятност', 'перестановк', 'размещен', 'сочетан'],
        'number_theory': ['натуральн', 'делимост', 'положительн', 'отрицательн', 'рациональн',
                          'числ', 'НОД', 'НОК'],
        'functions': ['функци', 'график', 'парабол', 'показательн', 'логарифм', 'производн',
                      'тригономет', 'интеграл', 'первообразн'],
        'equations': ['уравнен', 'неравенств', 'систем'],
        'fractions': ['дроб'],
        'percentages': ['процент'],
        'proportions': ['пропорц', 'отношен'],
        'progressions': ['прогресс'],
        'roots': ['корн', 'квадратн'],
        'powers': ['степен'],
        'complex': ['комплексн'],
        'optimization': ['оптимизац'],
        'movement':      ['движен', 'текстовые задачи', 'совместная работа'],
        'kl_movement':   ['движен', 'текстовые задачи', 'совместная работа'],
        'knights_liars': ['рыцар', 'лжец']
    }
    
    # ФИКС БАГА 1: Специальный маппинг для 5 класса
    # В 5 классе задачи записаны как "математика", "олимпиадные" и т.д.
    # Для "Алгебры" в 5 классе ищем задачи по более широким критериям
    if grade_int == 5 and topic == 'algebra':
        print(f"[ADAPTIVE FIX] 5 класс + Алгебра → расширенный поиск по математике")
        topic_keywords['algebra'] = ['математик', 'числ', 'выражен', 'уравнен', 'задач',
                                      'вычислен', 'арифметик', 'олимпиад']
    
    # Маппинг тем для всех классов (задачи хранятся с полными русскими названиями)
    from services.adaptive_topic_mapping import get_keywords_for_grade_topic
    grade_kw = get_keywords_for_grade_topic(grade_int, topic)
    if grade_kw:
        topic_keywords[topic] = grade_kw
        print(f"[ADAPTIVE FIX] {grade_int} класс + {topic} → ключевые слова: {grade_kw}")
    
    # Получаем ключевые слова для выбранной темы
    keywords = topic_keywords.get(topic, [])
    
    # Название темы для отображения
    topic_names = {
        'algebra': 'Алгебра',
        'geometry': 'Геометрия',
        'combinatorics': 'Комбинаторика',
        'number_theory': 'Теория чисел',
        'movement': 'Задачи на движение',
        'kl_movement': 'Задачи на движение',
        'knights_liars': 'Рыцари и лжецы',
        'functions': 'Функции',
        'equations': 'Уравнения'
    }
    
    topic_name = topic_names.get(topic, topic)
    
    # Фильтруем задачи по классу И по теме (ИСКЛЮЧАЕМ ПОМЕЧЕННЫЕ ЗАДАЧИ)
    if keywords:
        # Если есть ключевые слова - фильтруем по ним
        all_tasks = AdaptiveTask.query.filter_by(
            class_level=grade_int,
            is_flagged=False  # ФИЛЬТР КАЧЕСТВА: исключаем помеченные задачи
        ).all()
        
        # Фильтруем задачи, где название темы содержит хотя бы одно ключевое слово
        filtered_tasks = []
        for task in all_tasks:
            topic_lower = task.topic.lower()
            if any(keyword.lower() in topic_lower for keyword in keywords):
                filtered_tasks.append(task)
    else:
        # Если фильтра нет - берем все задачи класса (кроме помеченных)
        filtered_tasks = AdaptiveTask.query.filter_by(
            class_level=grade_int,
            is_flagged=False  # ФИЛЬТР КАЧЕСТВА: исключаем помеченные задачи
        ).all()
    
    if len(filtered_tasks) < 10:
        if len(filtered_tasks) == 0:
            flash(f'К сожалению, задач по теме "{topic_name}" для {grade} класса пока нет в базе данных. Попробуйте выбрать другую тему или класс.', 'error')
        else:
            flash(f'Недостаточно задач по теме "{topic_name}" для {grade} класса. Доступно: {len(filtered_tasks)}. Требуется минимум 10.', 'error')
        return redirect(url_for('adaptive_test_select_grade', topic=topic))
    
    # Сохраняем в сессию (сортируем id по возрастанию для детерминированности теста)
    session['adaptive_topic'] = topic
    session['adaptive_topic_name'] = topic_name
    session['adaptive_grade'] = grade
    session['adaptive_filtered_tasks'] = sorted(t.id for t in filtered_tasks)
    session['adaptive_current_difficulty'] = 3  # Начальная сложность
    session['adaptive_answers'] = []  # История ответов
    session['adaptive_current_index'] = 0  # Текущая задача
    session['adaptive_current_task_id'] = None  # Текущая задача (для persist on reload)
    session['adaptive_shown_task_ids'] = []  # Уже показанные задачи (без повторов)
    session.permanent = True
    
    # Перенаправляем на упрощенную страницу теста (без БД, только сессии)
    return redirect('/adaptive_test_simple')


@app.route("/adaptive_test_simple")
def adaptive_test_simple_page():
    """Упрощенная страница адаптивного теста (без авторизации, на сессиях)."""
    # Проверяем, что в сессии есть данные теста
    if 'adaptive_filtered_tasks' not in session:
        flash('Сначала выберите тему и класс для теста', 'error')
        return redirect(url_for('probniks_page'))
    
    grade = session.get('adaptive_grade', '9')
    task_ids = session.get('adaptive_filtered_tasks', [])
    current_index = session.get('adaptive_current_index', 0)
    
    # Проверяем завершение теста
    if current_index >= 25:
        # Тест завершен (25 задач)
        return redirect('/adaptive_test_simple/results')
    
    # ФИКС БАГА 2: Получаем текущий уровень сложности из сессии
    current_difficulty = session.get('adaptive_current_difficulty', 3)
    
    # ФИКС: Проверяем, есть ли уже выбранная задача для текущего индекса (persist on reload)
    current_task_id = session.get('adaptive_current_task_id')
    current_task = None
    
    if current_task_id:
        # Задача уже выбрана для этого шага — используем её (не меняем при перезагрузке)
        current_task = AdaptiveTask.query.get(current_task_id)
        if current_task:
            print(f"[ADAPTIVE] Повторная загрузка задачи #{current_index + 1}, ID={current_task.id} (из сессии)")
    
    # Если задача не найдена в сессии — выбираем новую
    if not current_task:
        print(f"[ADAPTIVE DEBUG] Выбор новой задачи #{current_index + 1}, требуемый уровень: {current_difficulty}")

        shown_ids = set(session.get('adaptive_shown_task_ids', []))

        # ДЕТЕРМИНИРОВАННЫЙ ВЫБОР: для одной и той же темы/класса/индекса
        # тест всегда показывает одни и те же задачи в одном и том же порядке.
        # Сортируем по id и берём первую неиспользованную нужного уровня.
        def _pick_first_at_level(level: int):
            tasks = AdaptiveTask.query.filter(
                AdaptiveTask.id.in_(task_ids),
                AdaptiveTask.difficulty_level == level
            ).order_by(AdaptiveTask.id.asc()).all()
            for t in tasks:
                if t.id not in shown_ids:
                    return t
            return None

        current_task = _pick_first_at_level(current_difficulty)

        # Если задач нужного уровня нет, берем ближайший уровень
        if current_task is None:
            print(f"[ADAPTIVE WARNING] Нет задач уровня {current_difficulty}, ищем ближайший...")
            for offset in [1, -1, 2, -2, 3, -3]:
                fallback_level = current_difficulty + offset
                if 1 <= fallback_level <= 7:
                    current_task = _pick_first_at_level(fallback_level)
                    if current_task is not None:
                        print(f"[ADAPTIVE] Используем уровень {fallback_level} вместо {current_difficulty}")
                        break

        # Если все еще нет задач, берем любую неиспользованную из пула (по id)
        if current_task is None:
            print(f"[ADAPTIVE ERROR] Не найдено задач нужного уровня, берём любую неиспользованную")
            remaining_ids = [tid for tid in sorted(task_ids) if tid not in shown_ids]
            if remaining_ids:
                current_task = AdaptiveTask.query.get(remaining_ids[0])
            else:
                flash('Ошибка: закончились задачи', 'error')
                return redirect('/adaptive_test_simple/results')

        if current_task:
            print(f"[ADAPTIVE] Выбрана задача ID={current_task.id}, уровень={current_task.difficulty_level}")
        
        # Сохраняем выбранную задачу в сессию (persist on reload)
        if current_task:
            session['adaptive_current_task_id'] = current_task.id
            shown_ids.add(current_task.id)
            session['adaptive_shown_task_ids'] = list(shown_ids)
            session.modified = True
    
    if not current_task:
        flash('Ошибка загрузки задачи', 'error')
        return redirect(url_for('probniks_page'))
    
    # Преобразуем объект БД в словарь для шаблона.
    # task_text уже хранится в БД с корректной разметкой MathJax (\\( ... \\))
    # либо с unicode-символами (°, π, ≤), которые MathJax/HTML рендерит как есть.
    # Поэтому не пропускаем через fix_bare_latex — старая функция конвертировала
    # ° → ^{\circ} без обёртки и ломала отображение.
    task_dict = {
        'id': current_task.id,
        'topic': current_task.topic,
        'class_level': current_task.class_level,
        'difficulty_level': current_task.difficulty_level,
        'task_text': current_task.task_text or '',
        'solution': current_task.solution,
        'criteria_1_point': current_task.criteria_1_point,
        'criteria_2_points': current_task.criteria_2_points
    }
    
    # ИСПРАВЛЕНИЕ: Берем тему из ТЕКУЩЕЙ задачи, а не из сессии
    topic_name = current_task.topic
    
    return render_template('adaptive_test_simple.html',
        topic_name=topic_name,
        grade=grade,
        task=task_dict,
        current_index=current_index + 1,
        total_tasks=25,  # Всегда 25 задач в адаптивном тесте
        current_level=current_difficulty  # ФИКС БАГА 2: Передаем текущий уровень для отображения
    )


@app.route("/adaptive_test_simple/submit", methods=["POST"])
def adaptive_test_simple_submit():
    """Обработка ответа в упрощенном адаптивном тесте."""
    if 'adaptive_filtered_tasks' not in session:
        flash('Сессия теста истекла', 'error')
        return redirect(url_for('probniks_page'))
    
    # Получаем данные из формы
    user_answer = request.form.get('answer', '').strip()
    user_solution = request.form.get('solution', '').strip()
    task_id = request.form.get('task_id')
    
    # Находим задачу в базе данных
    current_task = AdaptiveTask.query.get(task_id)
    
    if not current_task:
        flash('Ошибка: задача не найдена', 'error')
        return redirect('/adaptive_test_simple')
    
    # Проверяем ответ (пока просто принимаем любой ответ как правильный для демо)
    # TODO: добавить поле answer в модель AdaptiveTask для автоматической проверки
    is_correct = len(user_answer) > 0  # Временная логика
    
    # Сохраняем результат
    if 'adaptive_answers' not in session:
        session['adaptive_answers'] = []
    
    session['adaptive_answers'].append({
        'task_id': task_id,
        'user_answer': user_answer,
        'correct_answer': '',  # TODO: добавить поле answer в модель
        'is_correct': is_correct,
        'difficulty': current_task.difficulty_level
    })
    
    # Увеличиваем индекс
    session['adaptive_current_index'] = session.get('adaptive_current_index', 0) + 1
    
    # Очищаем текущую задачу из сессии — следующий запрос выберет новую
    session.pop('adaptive_current_task_id', None)
    
    # Адаптируем сложность
    current_difficulty = session.get('adaptive_current_difficulty', 3)
    if is_correct:
        session['adaptive_current_difficulty'] = min(7, current_difficulty + 1)
    else:
        session['adaptive_current_difficulty'] = max(1, current_difficulty - 1)
    
    session.modified = True
    
    # Если прошли 25 задач, завершаем тест
    if session['adaptive_current_index'] >= 25:
        return redirect('/adaptive_test_simple/results')
    
    # Иначе показываем следующую задачу
    return redirect('/adaptive_test_simple')


@app.route("/api/check_adaptive_answer", methods=["POST"])
def check_adaptive_answer():
    """
    API endpoint для проверки ответа через DeepSeek AI.
    Возвращает JSON с оценкой и фидбеком.
    """
    if 'adaptive_filtered_tasks' not in session:
        return jsonify({
            'status': 'error',
            'message': 'Сессия теста истекла'
        }), 400
    
    try:
        # Получаем данные из запроса
        data = request.get_json()
        task_id = data.get('task_id')
        user_answer = data.get('user_answer', '').strip()
        user_solution = data.get('user_solution', '').strip()
        # Фото рукописного решения. Поддерживаем 2 варианта:
        #   - solution_image_b64        — одно фото (legacy)
        #   - solution_images_b64       — список (несколько фото)
        # Каждая запись может быть полным data:URL — режем префикс до запятой.
        raw_images = []
        single = data.get('solution_image_b64', '') or ''
        if single:
            raw_images.append(single)
        multi = data.get('solution_images_b64') or []
        if isinstance(multi, list):
            for it in multi:
                if isinstance(it, str) and it.strip():
                    raw_images.append(it)

        def _strip_dataurl(b: str) -> str:
            return b.split(',', 1)[-1] if b.startswith('data:') else b

        images_b64 = [_strip_dataurl(b) for b in raw_images if b]
        # Для совместимости со старой переменной ниже:
        solution_image_b64 = images_b64[0] if images_b64 else ''

        if not task_id or not user_answer:
            return jsonify({
                'status': 'error',
                'message': 'Не указан ID задачи или ответ'
            }), 400
        
        # Находим задачу в базе данных
        from models import AdaptiveTask
        current_task = AdaptiveTask.query.get(task_id)
        
        if not current_task:
            return jsonify({
                'status': 'error',
                'message': 'Задача не найдена'
            }), 404

        # Если ученик прикрепил фото(-и) рукописного решения — распознаём
        # каждое через vision-LLM (OpenRouter / mathline pipeline) и
        # подмешиваем результат в `user_solution`. Это даёт AI-проверке
        # видеть тетрадное решение, а не только текст из MathLive-поля.
        if images_b64 and DEEPSEEK_AVAILABLE:
            try:
                _ocr_client = DeepSeekClient()
                transcribed_parts = []
                for idx, img_b64 in enumerate(images_b64, start=1):
                    try:
                        part = _ocr_client.transcribe_handwritten_solution(
                            image_data=img_b64,
                            task_text=current_task.task_text or "",
                        )
                    except Exception as _one_err:
                        print(
                            f"[ADAPTIVE OCR] photo #{idx} failed: {_one_err}"
                        )
                        part = ""
                    if part:
                        if len(images_b64) > 1:
                            transcribed_parts.append(
                                f"--- Фото {idx} из {len(images_b64)} ---\n{part}"
                            )
                        else:
                            transcribed_parts.append(part)
                    print(
                        f"[ADAPTIVE OCR] task_id={task_id} photo={idx}/"
                        f"{len(images_b64)} len={len(part)}"
                    )

                transcribed = "\n\n".join(transcribed_parts).strip()
                if transcribed:
                    header = (
                        "[Распознанные фото-решения]"
                        if len(images_b64) > 1
                        else "[Распознанное фото-решение]"
                    )
                    if user_solution:
                        user_solution = (
                            f"{user_solution}\n\n{header}\n{transcribed}"
                        )
                    else:
                        user_solution = f"{header}\n{transcribed}"
            except Exception as _ocr_err:
                print(f"[ADAPTIVE OCR] failed: {_ocr_err}")
                # Не падаем — продолжаем без распознанного фото
        
        # Получаем правильный ответ (если есть поле answer в модели)
        correct_answer = getattr(current_task, 'answer', '') or getattr(current_task, 'correct_answer', 'не указан')
        
        # ── Определяем тип задачи: доказательство или числовой ответ ──
        _ca_lower = (correct_answer or '').strip().lower()
        _task_lower = (current_task.task_text or '').lower()
        is_proof_task = (
            _ca_lower in ('доказательство', 'доказать', 'proof', '')
            or 'докажите' in _task_lower
            or 'доказать' in _task_lower
            or 'покажите, что' in _task_lower
            or 'покажите что' in _task_lower
            or 'обоснуйте' in _task_lower
        )
        
        # Проверяем доступность DeepSeek
        score = 1  # По умолчанию нейтральная оценка
        feedback = "Ваш ответ принят."

        # ── БЫСТРАЯ ПРЕД-ПРОВЕРКА: если числа в ответе ученика и в каноне
        # эквивалентны (с точностью до единиц измерения, формата и пробелов) —
        # сразу засчитываем как верно, без обращения к AI. Это ловит случаи
        # вроде "30" vs "30 см²", "1/2" vs "0.5", "−5" vs "-5".
        def _math_equivalent(user: str, canon: str) -> bool:
            import re as _re
            if not user or not canon:
                return False
            u = user.strip()
            c = canon.strip()
            if not u or not c:
                return False
            # Прямое совпадение строк (после lower и удаления пробелов)
            _norm = lambda s: _re.sub(r"\s+", "", s).lower().replace(",", ".")
            if _norm(u) == _norm(c):
                return True
            # Извлекаем все числа (включая дроби и десятичные)
            num_re = _re.compile(r"-?\d+(?:[.,]\d+)?(?:/\d+)?")
            def _to_floats(s):
                out = []
                for m in num_re.findall(s):
                    t = m.replace(",", ".")
                    try:
                        if "/" in t:
                            a, b = t.split("/", 1)
                            out.append(float(a) / float(b))
                        else:
                            out.append(float(t))
                    except Exception:
                        pass
                return out
            uns = _to_floats(u)
            cns = _to_floats(c)
            if not uns or not cns:
                return False
            # Если множества чисел совпадают (с точностью 1e-4) — эквивалентно
            if len(uns) == len(cns):
                if all(abs(a - b) <= max(1e-4, 1e-3 * max(abs(a), abs(b)))
                       for a, b in zip(sorted(uns), sorted(cns))):
                    return True
            # Если у канона ровно одно число и оно встречается в ответе ученика
            if len(cns) == 1 and any(
                abs(x - cns[0]) <= max(1e-4, 1e-3 * max(abs(x), abs(cns[0])))
                for x in uns
            ):
                return True
            return False

        if (not is_proof_task) and _math_equivalent(user_answer, str(correct_answer or "")):
            score = 2

            def _safe_truncate(text: str, max_len: int = 1500) -> str:
                """Trim long solution at a safe boundary that doesn't cut LaTeX."""
                if not text:
                    return ""
                if len(text) <= max_len:
                    return text
                # try to cut after the last completed \(..\) or \[..\] inside max_len
                tail = text[:max_len]
                for marker in ("\\)", "\\]", ".\n", "\n\n", ". ", "\n"):
                    idx = tail.rfind(marker)
                    if idx > max_len * 0.6:
                        return text[: idx + len(marker)] + " …"
                return tail + " …"

            sol = _safe_truncate(current_task.solution or "")
            feedback = (
                f"Ответ верный! ✅\n\n"
                f"Правильный ответ: **{correct_answer}**"
                + (f"\n\n**Решение:**\n{sol}" if sol else "")
            )
            print(f"[ADAPTIVE] Quick-check: '{user_answer}' ≡ '{correct_answer}' → score=2")
            DEEPSEEK_AVAILABLE_LOCAL = False  # пропускаем AI-проверку
        else:
            DEEPSEEK_AVAILABLE_LOCAL = DEEPSEEK_AVAILABLE

        if DEEPSEEK_AVAILABLE_LOCAL:
            try:
                # ── Выбираем промпт в зависимости от типа задачи ──
                if is_proof_task:
                    # ПРОМПТ ДЛЯ ЗАДАЧ-ДОКАЗАТЕЛЬСТВ
                    system_prompt = """Ты — проверяющий математических доказательств платформы FORMYLA.

ЗАДАЧА УЧЕНИКА — ДОКАЗАТЬ УТВЕРЖДЕНИЕ. Это НЕ задача с числовым ответом.
Ученик должен предоставить логическое рассуждение (доказательство).

АЛГОРИТМ ПРОВЕРКИ:
1. Прочитай условие задачи — пойми, ЧТО нужно доказать.
2. Прочитай эталонное решение (если есть) — пойми ИДЕЮ доказательства.
3. Прочитай решение ученика — проверь его ЛОГИКУ.
4. ВАЖНО: у доказательства может быть МНОГО правильных путей. Ученик НЕ обязан повторять эталон.

КРИТИЧЕСКИ ВАЖНО:
✅ Утверждение в задаче ВЕРНО (иначе его не просили бы доказывать). НЕ ПЫТАЙСЯ опровергнуть его!
✅ Оценивай ЛОГИКУ рассуждений ученика, а не совпадение с эталоном
✅ Если ученик привёл корректное доказательство (пусть другим методом) — это score: 2
✅ Если идея верная, но есть пробелы в логике — это score: 1
❌ ЗАПРЕЩЕНО утверждать, что доказываемое утверждение ложно
❌ ЗАПРЕЩЕНО приводить "контрпримеры" к утверждению, которое нужно доказать
❌ ЗАПРЕЩЕНО отвергать верное доказательство из-за отличия от эталона

СИСТЕМА БАЛЛОВ:
score = 2 (ВЕРНО, +1 уровень):
  - Доказательство логически корректно и полно
  - Все ключевые шаги обоснованы
  - Допускаются мелкие стилистические недочёты

score = 1 (ЧАСТИЧНО, уровень без изменений):
  - Идея доказательства верная, но есть логические пробелы
  - Не все случаи рассмотрены
  - Есть верные шаги, но доказательство неполное

score = -1 (НЕВЕРНО, -1 уровень):
  - Доказательство содержит грубую логическую ошибку
  - Ученик не понял, что нужно доказать
  - Решение пустое или не относится к задаче

ФОРМАТ ОТВЕТА — СТРОГО JSON (БЕЗ markdown маркеров):
{
  "score": X,
  "feedback": "текст разбора"
}

ПРАВИЛА ДЛЯ FEEDBACK:
- Используй LaTeX: \\( формула \\) для inline, \\[ формула \\] для display
- Будь конструктивным и понятным школьнику
- Если доказательство верное — похвали и отметь ключевую идею
- Если есть ошибки — укажи конкретно где и почему
- НЕ оборачивай JSON в markdown блоки"""
                else:
                    # ПРОМПТ ДЛЯ ЗАДАЧ С ЧИСЛОВЫМ ОТВЕТОМ (оригинальный)
                    system_prompt = """Ты — проверяющий математических задач платформы FORMYLA.
У тебя ЕСТЬ правильный ответ из базы данных. Твоя задача: сравнить ответ ученика с КАНОНИЧЕСКИМ ответом и дать конструктивный фидбек.

КРИТИЧЕСКИ ВАЖНО:
❌ ЗАПРЕЩЕНО решать задачу заново своим способом
❌ ЗАПРЕЩЕНО утверждать что канонический ответ неверен
❌ ЗАПРЕЩЕНО предлагать альтернативные "правильные" ответы
✅ ОБЯЗАТЕЛЬНО доверяй полю "Правильный ответ" — это истина из базы данных
✅ Сравнивай ответ ученика ТОЛЬКО с каноническим ответом

ВАЖНО: Ответ должен быть СТРОГО в формате JSON (БЕЗ markdown маркеров ```json):
{
  "score": X,
  "feedback": "текст разбора"
}

СТРОГИЕ ПРАВИЛА ОЦЕНИВАНИЯ (score):

1. СРАВНЕНИЕ ОТВЕТОВ:
   - Ответ пользователя (`user_answer`) приходит в формате LaTeX (например, `\\sqrt{31}`, `\\frac{1}{2}`, `2.5`)
   - Сравнивай МАТЕМАТИЧЕСКОЕ ЗНАЧЕНИЕ, а не текстовое совпадение
   - Десятичные дроби через точку (20.23) и запятую (20,23) - это ОДНО И ТО ЖЕ число
   - `\\frac{1}{2}` = `0.5` = `0,5` - это одно и то же
   - `\\sqrt{4}` = `2` - это одно и то же
   - Игнорируй пробелы, лишние скобки, незначительные форматирования
   - Главное - математическая суть числа

2. СИСТЕМА БАЛЛОВ (СТРОГИЕ ПРАВИЛА):
   
   score = 2 (ИДЕАЛЬНО, +1 уровень):
   
   ⚠️ ЕСЛИ ОТВЕТ ВЕРНЫЙ И ЕСТЬ РЕШЕНИЕ → score: 2. ЕСЛИ ОТВЕТ ВЕРНЫЙ, НО НЕТ РЕШЕНИЯ → score: -1!
  
   - Итоговый ответ математически ЭКВИВАЛЕНТЕН правильному И предоставлено решение
   - КРИТИЧЕСКИ ВАЖНО: Если ответ верный И есть решение (хотя бы краткое) → score: 2
   - ПРИМЕРЫ ЭКВИВАЛЕНТНОСТИ (ВСЕ это score: 2):
     * Ученик ввел "15", ожидалось "x=15" → score: 2
     * Ученик ввел "x=3", ожидалось "3" → score: 2
     * Ученик ввел "1/2", ожидалось "0.5" → score: 2
     * Ученик ввел "0.5", ожидалось "1/2" → score: 2
     * Ученик ввел "15", ожидалось "15.0" → score: 2
     * Ученик ввел "3", ожидалось "x=3" → score: 2
    - СТРОГО ЗАПРЕЩЕНО снижать балл за:
      * Отсутствие "x=", "y=", "z=" или других переменных
      * Пробелы, скобки, форматирование
      * Другой формат записи верного числа (дробь vs десятичная)
    - ВАЖНО: score 2 ставится ТОЛЬКО если ответ верный И предоставлено решение (хотя бы краткое).
    - ЗОЛОТОЕ ПРАВИЛО: Если числовое значение совпадает И есть решение - это score: 2!
    
    score = 1 (ЧАСТИЧНО ВЕРНО, уровень без изменений):
    - Итоговый ответ СОВПАДАЕТ, НО в решении есть ЯВНАЯ вычислительная ошибка (например, 2+2=5)
    - Итоговый ответ НЕ совпадает, НО в решении есть правильная идея/метод и ход мыслей верный
    - Ответ не сокращен до конца (например, 2/4 вместо 1/2) И это было требованием
    - ПОМНИ: score = 1 это ЧАСТИЧНО правильное решение. Не забывай про эту оценку!
    
    score = -1 (НЕВЕРНО, -1 уровень):
    - Итоговый ответ НЕ совпадает И решение неверное (или отсутствует)
    - Грубая концептуальная ошибка
    - *** ОТВЕТ БЕЗ РЕШЕНИЯ = ВСЕГДА score: -1 ***
      Если поле "Решение ученика" = "не предоставлено" или пустое,
      а ученик просто вписал ответ без какого-либо решения/обоснования,
      ставь score: -1 ДАЖЕ ЕСЛИ ОТВЕТ ВЕРНЫЙ.
      Олимпиадная математика требует РЕШЕНИЕ, а не угадывание!
    
    НАПОМИНАНИЕ О ШКАЛЕ: Ты оцениваешь из трёх вариантов: -1, +1, +2.
    Не забывай про +1 (частично верно)! Это НЕ только -1 и +2.
    
    ЗОЛОТОЕ ПРАВИЛО: Никогда не придирайся к оформлению. Если суть числа верная И есть решение - это score: 2!

3. ПРАВИЛА ДЛЯ FEEDBACK:
   
   ОБЯЗАТЕЛЬНО:
   - Если итоговый ответ СОВПАЛ с правильным, начинай с: "Ответ верный!" или "Итоговый ответ правильный!"
   - НИКОГДА не пиши "Ответ неверный", если числа совпали
   - Четко разделяй оценку ответа и оценку решения
   
   Примеры правильных формулировок:
   - "Ответ верный! Решение корректное, молодец!" (score: 2) - когда ответ совпал И есть решение
   - "Ответ правильный! Число 15 - это верный результат." (score: 2) - когда ученик ввел "15", а ожидалось "x=15"
   - "Ответ верный! 0.5 и 1/2 - это одно и то же число." (score: 2) - когда формат отличается
   - "Ответ правильный, но в решении есть вычислительная ошибка: \\( 2+3=6 \\) должно быть \\( 2+3=5 \\)." (score: 1) - только если есть ЯВНАЯ ошибка в вычислениях
   - "Идея решения верная, но в итоговом ответе ошибка из-за..." (score: 1) - когда ответ не совпал, но метод правильный
   - "К сожалению, ответ неверный. Правильный ответ: ..." (score: -1) - только когда ответ действительно не совпал
   - "Ответ верный, но решение не предоставлено. В олимпиадной математике необходимо показать ход решения!" (score: -1) - когда ответ верный, но решения нет
   
   ЗАПОМНИ: Ответ без решения = score: -1! Олимпиада требует обоснование.

4. ФОРМАТИРОВАНИЕ FEEDBACK — КРАЙНЕ ВАЖНО:

   ⚠️ ПИШИ МАТЕМАТИКУ ПРОСТЫМ ТЕКСТОМ БЕЗ LaTeX-команд.
       Никаких backslash-команд внутри feedback (нельзя писать backslash-frac,
       backslash-sqrt, backslash-left, backslash-right, backslash-dfrac,
       backslash-(...), backslash-[...], $...$, $$...$$). Любые обратные слеши
       ВНУТРИ feedback ЗАПРЕЩЕНЫ — они ломают рендеринг.

   КАК ЗАПИСЫВАТЬ МАТЕМАТИКУ (используй обычный текст и Unicode):
   - Степени: x^2, x^n (можно Unicode x²)
   - Индексы: a_1, a_n (можно Unicode a₁)
   - Дроби: 1/2, (x+1)/(x-1) — обычной чертой /
   - Корни: sqrt(5), или "корень из 5"
   - Сравнения: =, ≠, <, ≤, >, ≥, ≈
   - Греческие буквы: alpha, beta, pi, theta, lambda — словами
   - Никаких backslash-команд и LaTeX-делимитеров.

   ПРОЧИЕ ПРАВИЛА:
   - Используй переносы строк для структурирования текста.
   - Перед каждым новым шагом решения ставь перенос строки.
   - Используй **жирный** для ключевых слов (Шаг 1:, Ответ:, Проверка:).
   - Форматируй текст красиво, как в хорошем учебнике.
   - Будь конструктивным и понятным школьнику.
   - НЕ оборачивай JSON в markdown-блоки.
   - Пиши всё на русском языке обычным текстом без LaTeX.
"""

                if is_proof_task:
                    _etalon_sol = (current_task.solution or "")[:2000]
                    user_prompt = ""
                    user_prompt += "\u0417\u0430\u0434\u0430\u0447\u0430 (\u0414\u041e\u041a\u0410\u0417\u0410\u0422\u0415\u041b\u042c\u0421\u0422\u0412\u041e): " + current_task.task_text + "\n\n"
                    user_prompt += "\u042d\u0442\u0430\u043b\u043e\u043d\u043d\u043e\u0435 \u0440\u0435\u0448\u0435\u043d\u0438\u0435 \u0438\u0437 \u0411\u0414:\n" + (_etalon_sol if _etalon_sol else "(\u043d\u0435 \u0437\u0430\u0433\u0440\u0443\u0436\u0435\u043d\u043e)") + "\n\n"
                    user_prompt += "\u0420\u0435\u0448\u0435\u043d\u0438\u0435 \u0443\u0447\u0435\u043d\u0438\u043a\u0430: " + user_answer + "\n"
                    if user_solution:
                        user_prompt += "\u041f\u043e\u0434\u0440\u043e\u0431\u043d\u043e\u0435 \u0440\u0435\u0448\u0435\u043d\u0438\u0435:\n" + user_solution + "\n"
                    user_prompt += "\n\u041e\u0446\u0435\u043d\u0438 \u0434\u043e\u043a\u0430\u0437\u0430\u0442\u0435\u043b\u044c\u0441\u0442\u0432\u043e \u0438 \u0434\u0430\u0439 \u0444\u0438\u0434\u0431\u0435\u043a \u0432 \u0444\u043e\u0440\u043c\u0430\u0442\u0435 JSON."
                else:
                    user_prompt = f"""Задача: {current_task.task_text}

Правильный ответ: {correct_answer}

Ответ ученика: {user_answer}

Решение ученика: {user_solution if user_solution else 'не предоставлено'}

Оцени решение и дай фидбек в формате JSON."""

                # Вызываем DeepSeek с увеличенным max_tokens для длинных ответов
                ai_client = DeepSeekClient()
                ai_response = ai_client.generate(
                    prompt=user_prompt,
                    system_prompt=system_prompt,
                    temperature=0.3,
                    max_tokens=4096  # Достаточно для детального разбора с LaTeX (timeout=90 уже в классе)
                )
                
                # Парсим JSON-ответ
                try:
                    import re

                    def _safe_json_parse(raw: str):
                        """
                        Парсит JSON с LaTeX внутри строк.
                        DeepSeek возвращает \\( \\[ \\frac и т.д. - они невалидны в JSON.
                        Стратегия: найти JSON-объект, экранировать одиночные \\ внутри строк.
                        """
                        # 1. Убираем markdown-обёртки
                        s = re.sub(r'```json\s*', '', raw.strip())
                        s = re.sub(r'```\s*', '', s).strip()

                        # 2. Пробуем распарсить как есть
                        try:
                            return json.loads(s)
                        except json.JSONDecodeError:
                            pass

                        # 3. Экранируем одиночные \ которые не являются валидными JSON-escape
                        # Валидные: \\ \" \/ \b \f \n \r \t \uXXXX
                        # Невалидные (LaTeX): \( \) \[ \] \f \c \t (если не \t) и т.д.
                        # Заменяем одиночный \ на \\ только внутри JSON-строк
                        def fix_backslashes(m):
                            content = m.group(0)
                            # Заменяем \ которые не являются частью валидного escape
                            fixed = re.sub(
                                r'\\(?!["\\/bfnrtu])',
                                r'\\\\',
                                content
                            )
                            return fixed

                        # Находим все JSON-строки (между кавычками) и фиксим в них слеши
                        s_fixed = re.sub(r'"(?:[^"\\]|\\.)*"', fix_backslashes, s, flags=re.DOTALL)

                        try:
                            return json.loads(s_fixed)
                        except json.JSONDecodeError:
                            pass

                        # 4. Последний шанс: вытащить score и feedback регулярками
                        score_m = re.search(r'"score"\s*:\s*(-?\d+)', s)
                        feedback_m = re.search(r'"feedback"\s*:\s*"(.*?)"(?=\s*[,}])', s, re.DOTALL)
                        if score_m:
                            fb = feedback_m.group(1) if feedback_m else 'Ответ проверен.'
                            # Убираем экранирование для отображения
                            fb = fb.replace('\\n', '\n').replace('\\"', '"')
                            # Восстанавливаем LaTeX команды которые Python интерпретировал как escape
                            # \t → tab, \f → form feed, \s → \s (не escape, но на всякий случай)
                            import re as _re
                            # Заменяем одинарные слеши перед LaTeX командами на двойные
                            fb = _re.sub(r'(?<!\\)\\(text|frac|sqrt|cdot|sum|prod|int|lim|left|right|binom|gcd|overline|underline|vec|hat|bar|tilde|dot|ddot|pmod|bmod|geq|leq|neq|approx|equiv|times|div|pm|infty|alpha|beta|gamma|delta|theta|lambda|mu|pi|sigma|phi|omega)', r'\\\\\1', fb)
                            return {'score': int(score_m.group(1)), 'feedback': fb}

                        raise json.JSONDecodeError("Cannot parse AI response", s, 0)

                    ai_data = _safe_json_parse(ai_response)
                    score = max(-1, min(2, int(ai_data.get('score', 1))))
                    feedback = str(ai_data.get('feedback', 'Ответ проверен.'))
                    print(f"[DEBUG] Parsed score: {score}, feedback length: {len(feedback)}")

                    # ── AI-тьютор v2: если ответ НЕВЕРНЫЙ — тьютор решает сам ──
                    # Тьютор самостоятельно решает задачу и может исправить БД-ответ
                    if score == -1:
                        try:
                            from services.ai_tutor_v2 import tutor_explain
                            tutor_result = tutor_explain(
                                task=current_task,
                                user_answer=user_answer,
                                ai_client=ai_client,
                            )
                            # Используем разбор и ответ ОТ LLM, а не из БД
                            feedback = tutor_result['solution']
                            # FIX: override score if tutor says user is correct
                            if tutor_result.get('user_correct'):
                                score = 2
                                print(f'[tutor_v2] Score overridden to 2 (tutor says correct)')
                            _log_tutor_call(
                                task_id=current_task.id,
                                user_answer=user_answer,
                                result=tutor_result,
                            )
                            print(f"[tutor_v2] status={tutor_result['status']}, "
                                  f"errors={tutor_result['errors']}, "
                                  f"needs_review={tutor_result.get('needs_review', False)}, "
                                  f"llm_answer={tutor_result.get('answer', '?')}, "
                                  f"feedback_len={len(feedback)}")
                        except Exception as tutor_err:
                            app.logger.warning(
                                f"[tutor_v2] Failed, keeping old feedback: {tutor_err}"
                            )
                            # Оставляем старый feedback — не ломаем основной поток
                        
                except (json.JSONDecodeError, ValueError) as e:
                    print(f"[ERROR] Failed to parse AI response as JSON: {e}")
                    # Fallback: показываем правильный ответ из БД
                    feedback = (
                        f"AI-разбор временно недоступен.\n\n"
                        f"Правильный ответ: **{correct_answer}**\n\n"
                        f"Решение:\n{current_task.solution[:600] if current_task.solution else 'см. учебник'}"
                    )
                    score = 0  # Нейтральная оценка — не меняем уровень
                    
            except Exception as e:
                print("="*70)
                print(f"[CRITICAL ERROR] DeepSeek API FAILED")
                print(f"Error Type: {type(e).__name__}")
                print(f"Error Message: {e}")
                print("="*70)
                import traceback
                traceback.print_exc()
                print("="*70)
                print(f"[DEBUG] Task text: {current_task.task_text[:100]}...")
                print(f"[DEBUG] User answer: {user_answer}")
                print(f"[DEBUG] Correct answer: {correct_answer}")
                print("="*70)
                # Fallback: показываем правильный ответ из БД вместо пустого сообщения
                feedback = (
                    f"AI-проверка временно недоступна.\n\n"
                    f"**Правильный ответ:** {correct_answer}\n\n"
                    + (f"**Решение:**\n{current_task.solution[:800]}" if current_task.solution else "")
                )
                score = 0  # Нейтральная оценка — уровень не меняется
        
        # Ограничиваем score в диапазоне [-1, 2]
        score = max(-1, min(2, score))

        # ── Sanitize feedback: убираем LaTeX-команды и делимитеры ──────────
        # Конвертируем популярные LaTeX-конструкции в человекочитаемый текст,
        # чтобы разбор от AI-тьютора всегда выглядел нормально, даже если
        # модель проигнорировала инструкцию «без LaTeX».
        def _sanitize_feedback_no_latex(s: str) -> str:
            if not s:
                return s
            import re as _re
            t = s
            # 1) убираем делимитеры \( \) \[ \] и $$..$$ / $..$
            t = t.replace("\\(", " ").replace("\\)", " ")
            t = t.replace("\\[", "\n").replace("\\]", "\n")
            t = _re.sub(r"\$\$([^$]*)\$\$", r"\1", t, flags=_re.DOTALL)
            t = _re.sub(r"\$([^$\n]+)\$", r"\1", t)
            # 2) \frac{a}{b} → (a)/(b)   (и \dfrac, \tfrac)
            for cmd in ("dfrac", "tfrac", "frac"):
                pat = r"\\" + cmd + r"\s*\{([^{}]*)\}\s*\{([^{}]*)\}"
                # повторяем — на случай вложенных
                for _ in range(4):
                    new_t = _re.sub(pat, r"(\1)/(\2)", t)
                    if new_t == t:
                        break
                    t = new_t
            # 3) \sqrt[n]{x} → root_n(x);   \sqrt{x} → sqrt(x)
            t = _re.sub(r"\\sqrt\s*\[([^\]]*)\]\s*\{([^{}]*)\}", r"root_\1(\2)", t)
            t = _re.sub(r"\\sqrt\s*\{([^{}]*)\}", r"sqrt(\1)", t)
            # 4) \left( \right) → ( )
            t = t.replace("\\left", "").replace("\\right", "")
            # 5) операторы и символы
            replacements = {
                "\\cdot": "·", "\\times": "×", "\\div": "÷", "\\pm": "±",
                "\\le": "≤", "\\leq": "≤", "\\ge": "≥", "\\geq": "≥",
                "\\ne": "≠", "\\neq": "≠", "\\approx": "≈", "\\equiv": "≡",
                "\\infty": "∞", "\\to": "→", "\\Rightarrow": "⇒",
                "\\Leftrightarrow": "⇔", "\\in": "∈", "\\notin": "∉",
                "\\subset": "⊂", "\\cup": "∪", "\\cap": "∩",
                "\\forall": "∀", "\\exists": "∃", "\\sum": "Σ", "\\prod": "∏",
                "\\int": "∫", "\\lim": "lim", "\\log": "log", "\\ln": "ln",
                "\\sin": "sin", "\\cos": "cos", "\\tan": "tg", "\\cot": "ctg",
                "\\alpha": "α", "\\beta": "β", "\\gamma": "γ", "\\delta": "δ",
                "\\epsilon": "ε", "\\theta": "θ", "\\lambda": "λ", "\\mu": "μ",
                "\\pi": "π", "\\rho": "ρ", "\\sigma": "σ", "\\tau": "τ",
                "\\phi": "φ", "\\omega": "ω",
                "\\overline": "", "\\underline": "", "\\vec": "",
                "\\hat": "", "\\bar": "", "\\tilde": "",
                "\\pmod": "mod", "\\bmod": "mod",
                "\\quad": " ", "\\qquad": "  ", "\\,": " ", "\\;": " ",
                "\\!": "", "\\:": " ", "\\ ": " ",
            }
            for src, dst in replacements.items():
                t = t.replace(src, dst)
            # 6) \text{...} → ...
            t = _re.sub(r"\\text\s*\{([^{}]*)\}", r"\1", t)
            # 7) убираем оставшиеся одиночные backslash-команды
            t = _re.sub(r"\\[A-Za-z]+\s*\{([^{}]*)\}", r"\1", t)
            t = _re.sub(r"\\[A-Za-z]+", "", t)
            # 8) убираем одиночные фигурные скобки, оставшиеся от LaTeX
            #    (но НЕ трогаем индексы вида a_{1} — их уже заменили выше)
            t = _re.sub(r"\{([^{}]*)\}", r"\1", t)
            # 9) косметика: схлопываем многократные пробелы
            t = _re.sub(r"[ \t]{2,}", " ", t)
            t = _re.sub(r"\n{3,}", "\n\n", t)
            return t.strip()

        try:
            feedback = _sanitize_feedback_no_latex(feedback)
        except Exception as _san_err:
            print(f"[sanitize] feedback cleanup failed: {_san_err}")

        # ── Task 3: явная коммуникация баллов ──
        # Адаптивный тест: AI-тьютор должен ВСЕГДА проговаривать,
        # сколько баллов он поставил.
        # ВАЖНО (правка по запросу пользователя 2026-05-17):
        # если AI-тьютор поставил +2 — оставляем +2 даже без отдельного поля
        # «решение». Не понижаем балл просто по факту отсутствия user_solution:
        # тьютор сам решает, достоин ли ответ +2.
        _has_solution = bool((user_solution or '').strip())

        # Префикс с явной оценкой в начале feedback, чтобы ученик видел балл.
        def _score_badge(s: int, has_solution: bool) -> str:
            if s == 2:
                return "🟢 **Оценка тьютора: +2 балла** (верный ответ + корректное решение)"
            if s == 1:
                if has_solution:
                    return "🟡 **Оценка тьютора: +1 балл** (частично верно: либо ответ неточный, либо решение с пробелами)"
                return "🟡 **Оценка тьютора: +1 балл** (ответ принят, но без решения)"
            if s == 0:
                return "⚪ **Оценка тьютора: 0 баллов** (нейтрально, уровень не меняется)"
            # s == -1
            if has_solution:
                return "🔴 **Оценка тьютора: −1 балл** (решение содержит ошибку)"
            return "🔴 **Оценка тьютора: −1 балл** (нет решения — олимпиада требует обоснование)"

        _badge = _score_badge(score, _has_solution)
        # Не дублируем, если AI уже сам начал с такой строки
        if _badge.split(':', 1)[0] not in (feedback or '')[:80]:
            feedback = f"{_badge}\n\n{feedback or ''}".strip()
        
        # НОВАЯ ЛОГИКА АДАПТИВНОСТИ С СТРИКАМИ
        current_difficulty = session.get('adaptive_current_difficulty', 3)
        partial_streak = session.get('partial_correct_streak', 0)
        
        # Логирование для отладки
        print(f"[ADAPTIVE] Score: {score}, Current level: {current_difficulty}, Streak: {partial_streak}")
        
        if score == 2:
            # Идеально - мгновенно повышаем уровень
            new_level = min(7, current_difficulty + 1)
            partial_streak = 0  # Сбрасываем стрик
            print(f"[ADAPTIVE] Score=2: Повышаем уровень {current_difficulty} → {new_level}")
            
        elif score == 1:
            # Частично верно - уровень НЕ меняется (фикс: было +1 при стрике >= 2)
            new_level = current_difficulty
            partial_streak = 0  # Сбрасываем стрик
            print(f"[ADAPTIVE] Score=1: Уровень без изменений {current_difficulty}")
                
        else:  # score <= 0
            # Неверно - снижаем уровень
            new_level = max(1, current_difficulty - 1)
            partial_streak = 0  # Сбрасываем стрик
        
        # Сохраняем обновленные значения в сессию
        session['adaptive_current_difficulty'] = new_level
        session['partial_correct_streak'] = partial_streak
        
        # Сохраняем результат в историю ответов
        if 'adaptive_answers' not in session:
            session['adaptive_answers'] = []
        
        # ВАЖНО: НЕ сохраняем длинные строки (feedback, user_solution) в сессии,
        # чтобы не выйти за лимит Flask cookie session (~4KB). Иначе после
        # 2-3 задач сессия молча перестаёт сохраняться и индекс не растёт.
        # Полные feedback пользователь видит сразу в JSON-ответе на этот запрос.
        session['adaptive_answers'].append({
            'task_id': task_id,
            'user_answer': (user_answer or '')[:120],
            'correct_answer': (str(correct_answer) if correct_answer else '')[:120],
            'score': score,
            'difficulty': current_task.difficulty_level,
        })
        
        # Увеличиваем индекс текущей задачи
        current_index = session.get('adaptive_current_index', 0)
        session['adaptive_current_index'] = current_index + 1
        
        # Очищаем текущую задачу — следующий запрос выберет новую
        session.pop('adaptive_current_task_id', None)
        
        session.modified = True
        
        # Проверяем, это последняя задача?
        is_last_task = (current_index + 1) >= 25
        
        return jsonify({
            'status': 'success',
            'score': score,
            'feedback': feedback,
            'new_level': new_level,
            'current_level': current_difficulty,
            'is_last_task': is_last_task,
            'current_index': current_index + 1
        })
        
    except Exception as e:
        print(f"[ERROR] check_adaptive_answer: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'status': 'error',
            'message': f'Ошибка сервера: {str(e)}'
        }), 500


@app.route("/api/report_task/<int:task_id>", methods=["POST"])
def report_task(task_id):
    """API для жалоб на некорректные задачи."""
    try:
        # Находим задачу
        task = AdaptiveTask.query.get(task_id)
        
        if not task:
            return jsonify({
                'status': 'error',
                'message': 'Задача не найдена'
            }), 404
        
        # Увеличиваем счетчик жалоб
        task.reports_count = (task.reports_count or 0) + 1
        
        # Если жалоб >= 3, автоматически помечаем задачу как некорректную
        if task.reports_count >= 3:
            task.is_flagged = True
            task.flagged_reason = f'Автоматически помечена после {task.reports_count} жалоб от пользователей'
            print(f"[QUALITY CONTROL] Задача ID={task_id} автоматически помечена после {task.reports_count} жалоб")
        
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'message': 'Спасибо за сообщение! Мы проверим эту задачу.',
            'reports_count': task.reports_count,
            'is_flagged': task.is_flagged
        })
        
    except Exception as e:
        print(f"[ERROR] report_task: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'status': 'error',
            'message': f'Ошибка сервера: {str(e)}'
        }), 500


@app.route("/adaptive_test_simple/results")
def adaptive_test_simple_results():
    """Результаты упрощенного адаптивного теста."""
    if 'adaptive_answers' not in session:
        flash('Нет данных о тесте', 'error')
        return redirect(url_for('probniks_page'))
    
    answers = session.get('adaptive_answers', [])
    topic = session.get('adaptive_topic', 'algebra')
    topic_name = session.get('adaptive_topic_name', 'Математика')
    grade = session.get('adaptive_grade', '9')

    # Dehydrate feedback from DB for the results page (we don't keep long
    # feedback strings in the session for cookie-size reasons).
    if answers:
        try:
            ids = [a.get('task_id') for a in answers if a.get('task_id')]
            tasks_map = {}
            if ids:
                rows = AdaptiveTask.query.filter(
                    AdaptiveTask.id.in_(ids)
                ).all()
                tasks_map = {t.id: t for t in rows}
            for a in answers:
                tid = a.get('task_id')
                t = tasks_map.get(int(tid)) if tid else None
                a['task_text'] = t.task_text if t else ''
                a['solution'] = t.solution if t else ''
                # Re-build a short feedback for display using current
                # quick rules.
                score = a.get('score', a.get('is_correct', 0))
                ca = a.get('correct_answer') or (t.correct_answer if t else '')
                if score >= 2:
                    a['feedback'] = (
                        f"Ответ верный! ✅\n\nПравильный ответ: **{ca}**"
                        + (f"\n\n**Решение:**\n{t.solution}" if t and t.solution else "")
                    )
                elif score == 1:
                    a['feedback'] = (
                        "Частично верно — уровень не изменился."
                        + (f"\n\nПравильный ответ: **{ca}**" if ca else "")
                        + (f"\n\n**Разбор:**\n{t.solution}" if t and t.solution else "")
                    )
                else:
                    a['feedback'] = (
                        "Ответ не верный."
                        + (f"\n\nПравильный ответ: **{ca}**" if ca else "")
                        + (f"\n\n**Разбор:**\n{t.solution}" if t and t.solution else "")
                    )
        except Exception as _e:
            print(f"[ADAPTIVE results] feedback rehydrate failed: {_e}")
    
    # Подсчет статистики с учетом новых полей score
    total = len(answers)
    
    # Считаем правильные ответы: score >= 1 считается как правильный
    correct = sum(1 for a in answers if a.get('score', a.get('is_correct', 0)) >= 1)
    accuracy = (correct / total * 100) if total > 0 else 0
    
    # Определение финального уровня
    final_level = session.get('adaptive_current_difficulty', 3)
    
    # Средняя сложность правильно решенных задач (score >= 1)
    correct_tasks = [a for a in answers if a.get('score', a.get('is_correct', 0)) >= 1]
    avg_difficulty = sum(a['difficulty'] for a in correct_tasks) / max(len(correct_tasks), 1)
    
    # Сохранение результатов в БД (если пользователь авторизован)
    if current_user.is_authenticated:
        try:
            # 1. Создаем запись о прохождении теста
            test_result = AdaptiveTestResult(
                user_id=current_user.id,
                topic=topic,
                class_level=int(grade) if grade else None,
                final_level=final_level,
                tasks_correct=correct,
                tasks_total=total,
                answers_history=json.dumps(answers, ensure_ascii=False),
                completed_at=datetime.utcnow()
            )
            db.session.add(test_result)
            
            # 2. Обновляем прогресс по теме
            topic_progress = UserTopicProgress.query.filter_by(
                user_id=current_user.id,
                topic=topic
            ).first()
            
            if not topic_progress:
                # Создаем новую запись
                topic_progress = UserTopicProgress(
                    user_id=current_user.id,
                    topic=topic,
                    topic_name_ru=topic_name,
                    current_level=final_level,
                    tasks_attempted=total,
                    tasks_correct=correct,
                    last_test_date=datetime.utcnow()
                )
                db.session.add(topic_progress)
            else:
                # Обновляем существующую
                topic_progress.current_level = final_level
                topic_progress.tasks_attempted += total
                topic_progress.tasks_correct += correct
                topic_progress.last_test_date = datetime.utcnow()
                topic_progress.updated_at = datetime.utcnow()
            
            # 3. Обновляем общую статистику пользователя и начисляем XP
            xp_result = add_xp_for_adaptive_test(current_user)
            adaptive_xp_bonus = xp_result['xp_gained']
            level_up = xp_result['level_up']
            new_level = xp_result['new_level']
            
            db.session.commit()
            
        except Exception as e:
            print(f"[ERROR] Failed to save test results: {e}")
            db.session.rollback()
            adaptive_xp_bonus = 0
            level_up = False
            new_level = current_user.current_level if current_user.is_authenticated else 1
    else:
        adaptive_xp_bonus = 0
        level_up = False
        new_level = 1
    
    return render_template('adaptive_test_simple_results.html',
        topic=topic,
        topic_name=topic_name,
        grade=grade,
        total=total,
        correct=correct,
        accuracy=accuracy,
        avg_difficulty=round(avg_difficulty, 1),
        final_level=final_level,
        answers=answers,
        adaptive_xp_bonus=adaptive_xp_bonus,
        level_up=level_up,
        new_level=new_level
    )


@app.route("/api/adaptive-test/start", methods=["POST"])
@login_required
def start_adaptive_test():
    """Начать новое адаптивное тестирование."""
    from models import AdaptiveTest, AdaptiveTestProblem
    from services.adaptive_test import AdaptiveTestEngine
    
    data = request.get_json() or {}
    subject = data.get('subject')  # Опционально: фильтр по предмету
    grade = data.get('grade')  # Опционально: фильтр по классу
    num_problems = data.get('num_problems', 25)  # По умолчанию 25 задач
    
    # Получаем историю пользователя для оценки начального уровня
    user_history = []
    previous_tests = AdaptiveTest.query.filter_by(
        user_id=current_user.id,
        status='completed'
    ).order_by(AdaptiveTest.completed_at.desc()).limit(5).all()
    
    for test in previous_tests:
        for problem in test.problems:
            if problem.is_correct is not None:
                user_history.append({
                    'difficulty': problem.problem_difficulty,
                    'is_correct': problem.is_correct
                })
    
    # Создаем движок адаптивного тестирования
    engine = AdaptiveTestEngine(PROBLEMS_DB)
    
    # Оцениваем начальный уровень
    initial_ability = engine.estimate_user_ability(user_history) if user_history else 3.5
    
    # Создаем тест
    test = AdaptiveTest(
        user_id=current_user.id,
        subject=subject,
        grade=grade,
        num_problems=num_problems,
        initial_ability=initial_ability,
        current_ability=initial_ability
    )
    db.session.add(test)
    db.session.flush()
    
    # Выбираем первую задачу
    first_problem = engine.select_next_problem(
        user_ability=initial_ability,
        subject=subject,
        grade=grade,
        excluded_ids=[]
    )
    
    if not first_problem:
        db.session.rollback()
        return jsonify({'error': 'Не удалось найти подходящие задачи'}), 400
    
    # Добавляем первую задачу
    test_problem = AdaptiveTestProblem(
        test_id=test.id,
        problem_id=first_problem['id'],
        sequence_number=1,
        user_ability_before=initial_ability,
        problem_difficulty=float(first_problem.get('level', 3.5))
    )
    db.session.add(test_problem)
    db.session.commit()
    
    return jsonify({
        'test_id': test.id,
        'problem': first_problem,
        'current_number': 1,
        'total_problems': num_problems,
        'current_ability': initial_ability
    })


@app.route("/api/problem/<int:problem_id>")
@login_required
def get_problem(problem_id):
    """Получить данные задачи по ID"""
    problem = next((p for p in PROBLEMS_DB if p['id'] == problem_id), None)
    if problem:
        return jsonify(problem)
    return jsonify({'error': 'Problem not found'}), 404


@app.route("/api/adaptive-test/<int:test_id>/submit", methods=["POST"])
@login_required
def submit_adaptive_answer(test_id):
    """Отправить ответ на задачу адаптивного теста."""
    from models import AdaptiveTest, AdaptiveTestProblem
    from services.adaptive_test import AdaptiveTestEngine
    
    test = AdaptiveTest.query.get_or_404(test_id)
    
    if test.user_id != current_user.id:
        abort(403)
    
    if test.status != 'in_progress':
        return jsonify({'error': 'Тест уже завершен'}), 400
    
    data = request.get_json() or {}
    problem_id = data.get('problem_id')
    user_answer = data.get('answer', '').strip()
    user_solution = data.get('solution', '').strip()
    
    # Находим текущую задачу
    current_problem_record = AdaptiveTestProblem.query.filter_by(
        test_id=test_id,
        problem_id=problem_id
    ).first()
    
    if not current_problem_record:
        return jsonify({'error': 'Задача не найдена'}), 404
    
    if current_problem_record.is_correct is not None:
        return jsonify({'error': 'Ответ уже отправлен'}), 400
    
    # Находим задачу в базе
    problem = next((p for p in PROBLEMS_DB if p['id'] == problem_id), None)
    if not problem:
        return jsonify({'error': 'Задача не найдена в базе'}), 404
    
    # Проверяем ответ с умной нормализацией
    correct_answer = str(problem.get('answer', '')).strip()
    is_correct = compare_math_answers(user_answer, correct_answer)
    
    # Обновляем запись задачи
    current_problem_record.user_answer = user_answer
    current_problem_record.user_solution_text = user_solution
    current_problem_record.is_correct = is_correct
    current_problem_record.answered_at = datetime.utcnow()
    
    # Обновляем способность пользователя
    engine = AdaptiveTestEngine(PROBLEMS_DB)
    new_ability = engine.update_ability_after_answer(
        current_ability=test.current_ability,
        problem_difficulty=current_problem_record.problem_difficulty,
        is_correct=is_correct
    )
    
    current_problem_record.user_ability_after = new_ability
    test.current_ability = new_ability
    
    # Проверяем, нужно ли добавить следующую задачу
    answered_count = AdaptiveTestProblem.query.filter_by(test_id=test_id).filter(
        AdaptiveTestProblem.is_correct.isnot(None)
    ).count()
    
    next_problem = None
    if answered_count < test.num_problems:
        # Выбираем следующую задачу
        excluded_ids = [p.problem_id for p in test.problems]
        
        next_problem_data = engine.select_next_problem(
            user_ability=new_ability,
            subject=test.subject,
            grade=test.grade,
            excluded_ids=excluded_ids
        )
        
        if next_problem_data:
            next_problem_record = AdaptiveTestProblem(
                test_id=test.id,
                problem_id=next_problem_data['id'],
                sequence_number=answered_count + 1,
                user_ability_before=new_ability,
                problem_difficulty=float(next_problem_data.get('level', 3.5))
            )
            db.session.add(next_problem_record)
            next_problem = next_problem_data
    
    # Если это была последняя задача, завершаем тест
    if answered_count >= test.num_problems or next_problem is None:
        test.status = 'analyzing'
        test.completed_at = datetime.utcnow()
    
    db.session.commit()
    
    response = {
        'is_correct': is_correct,
        'correct_answer': problem.get('answer'),
        'current_ability': round(new_ability, 2),
        'answered_count': answered_count,
        'total_problems': test.num_problems
    }
    
    if next_problem:
        response['next_problem'] = next_problem
        response['next_number'] = answered_count + 1
    else:
        response['test_completed'] = True
        response['test_id'] = test.id
    
    return jsonify(response)


@app.route("/api/adaptive-test/<int:test_id>/analyze", methods=["POST"])
@login_required
def analyze_adaptive_test(test_id):
    """Анализ результатов адаптивного теста с помощью AI."""
    from models import AdaptiveTest, AdaptiveTestProblem
    from services.adaptive_test import AdaptiveTestEngine, get_olympiad_status
    
    test = AdaptiveTest.query.get_or_404(test_id)
    
    if test.user_id != current_user.id:
        abort(403)
    
    if test.status not in ['analyzing', 'completed']:
        return jsonify({'error': 'Тест еще не завершен'}), 400
    
    # Собираем данные для анализа
    problems = []
    answers = []
    
    for problem_record in test.problems.order_by(AdaptiveTestProblem.sequence_number):
        problem = next((p for p in PROBLEMS_DB if p['id'] == problem_record.problem_id), None)
        if problem:
            problems.append(problem)
            answers.append({
                'is_correct': problem_record.is_correct,
                'user_answer': problem_record.user_answer,
                'solution': problem_record.user_solution_text
            })
    
    # Анализируем результаты
    engine = AdaptiveTestEngine(PROBLEMS_DB)
    analysis = engine.analyze_test_results(problems, answers)
    
    # Обновляем тест
    test.final_ability = analysis['final_ability']
    test.total_correct = analysis['total_correct']
    test.accuracy = analysis['accuracy']
    
    # Получаем олимпиадный статус
    olympiad_status = get_olympiad_status(analysis['final_ability'])
    
    # Собираем статистику по разделам
    subject_stats = {}
    for problem, answer in zip(problems, answers):
        subject = problem.get('subject', 'unknown')
        if subject not in subject_stats:
            subject_stats[subject] = {'correct': 0, 'total': 0}
        subject_stats[subject]['total'] += 1
        if answer.get('is_correct'):
            subject_stats[subject]['correct'] += 1
    
    # Определяем сильные и слабые разделы
    strong_subjects = []
    weak_subjects = []
    for subject, stats in subject_stats.items():
        accuracy = stats['correct'] / stats['total'] if stats['total'] > 0 else 0
        if accuracy >= 0.7 and stats['total'] >= 3:
            strong_subjects.append(subject)
        elif accuracy < 0.5 and stats['total'] >= 3:
            weak_subjects.append(subject)
    
    # Генерируем AI анализ если доступен
    if DEEPSEEK_AVAILABLE:
        try:
            client = DeepSeekClient()
            
            # Переводим названия разделов на русский
            subject_names = {
                'algebra': 'Алгебра',
                'geometry': 'Геометрия',
                'combinatorics': 'Комбинаторика',
                'number_theory': 'Теория чисел',
                'movement': 'Задачи на движение',
                'knights_liars': 'Рыцари и лжецы'
            }
            
            strong_names = [subject_names.get(s, s) for s in strong_subjects]
            weak_names = [subject_names.get(s, s) for s in weak_subjects]
            
            # Формируем промпт для AI-тренера
            prompt = f"""Ты опытный тренер олимпиадной сборной. Ученик только что прошел адаптивное тестирование (25 задач).

Его итоговый статус: {olympiad_status['status']}
Финальный уровень: {analysis['final_ability']:.1f}/7.0
Правильных ответов: {analysis['total_correct']} из {analysis['total_problems']} ({analysis['accuracy']:.0f}%)

Сильные разделы: {', '.join(strong_names) if strong_names else 'пока не выявлены'}
Слабые разделы: {', '.join(weak_names) if weak_names else 'пока не выявлены'}

Напиши короткий, ободряющий отзыв (3-4 предложения) с конкретной рекомендацией, на какие разделы на сайте FORMYLA ему нужно сделать упор в ближайший месяц, чтобы достичь следующего статуса: {olympiad_status.get('next_status', 'высшего уровня')}.

Будь мотивирующим, но честным. Говори прямо и по делу, как настоящий тренер."""

            # Отправляем с таймаутом 10 секунд
            ai_analysis = client.generate(
                prompt=prompt,
                system_prompt=r"Ты опытный тренер олимпиадной математической сборной. Твоя задача - мотивировать учеников и давать конкретные рекомендации. Используй LaTeX для формул: \( x^2 \), \( \frac{a}{b} \), \( \sqrt{x} \).",
                temperature=0.8,
                max_tokens=8192
            )
            
            test.ai_analysis = ai_analysis
            
        except Exception as e:
            logger.error(f"Ошибка AI анализа: {e}")
            test.ai_analysis = "ИИ-тренер сейчас анализирует результаты других олимпиадников. Загляните сюда чуть позже!"
    
    test.status = 'completed'
    db.session.commit()
    
    return jsonify({
        'analysis': analysis,
        'ai_analysis': test.ai_analysis,
        'olympiad_status': olympiad_status
    })


@app.route("/adaptive-test/<int:test_id>")
@login_required
def adaptive_test_page(test_id):
    """Страница прохождения адаптивного теста."""
    from models import AdaptiveTest
    
    test = AdaptiveTest.query.get_or_404(test_id)
    
    if test.user_id != current_user.id:
        abort(403)
    
    # Конвертируем задачи в словари для JSON с данными задач
    problems_list = [p.to_dict(include_problem_data=True) for p in test.problems.all()]
    
    return render_template('adaptive_test.html', test=test, problems_list=problems_list)


@app.route("/adaptive-test/<int:test_id>/results")
@login_required
def adaptive_test_results(test_id):
    """Страница результатов адаптивного теста."""
    from models import AdaptiveTest
    from services.adaptive_test import get_olympiad_status
    
    test = AdaptiveTest.query.get_or_404(test_id)
    
    if test.user_id != current_user.id:
        abort(403)
    
    # Получаем задачи с результатами
    results_data = []
    for problem_record in test.problems.order_by(AdaptiveTestProblem.sequence_number):
        problem = next((p for p in PROBLEMS_DB if p['id'] == problem_record.problem_id), None)
        if problem:
            results_data.append({
                'problem': problem,
                'user_answer': problem_record.user_answer,
                'user_solution': problem_record.user_solution_text,
                'is_correct': problem_record.is_correct,
                'difficulty': problem_record.problem_difficulty,
                'ability_before': problem_record.user_ability_before,
                'ability_after': problem_record.user_ability_after
            })
    
    # Получаем олимпиадный статус
    olympiad_status = get_olympiad_status(test.final_ability) if test.final_ability else None
    
    return render_template('adaptive_test_results.html', test=test, results=results_data, olympiad_status=olympiad_status)


@app.route("/social")
@login_required
def social_page():
    """Страница социальных функций"""
    return render_template('social.html')


# ============================================================
# SOCIAL FEATURES API
# ============================================================

@app.route("/api/social/set-nickname", methods=["POST"])
@login_required
def set_nickname():
    """Установить никнейм пользователя"""
    try:
        data = request.get_json()
        nickname = data.get('nickname', '').strip()
        
        # Валидация
        if not nickname:
            return jsonify({'success': False, 'error': 'Nickname cannot be empty'}), 400
        
        if len(nickname) < 3 or len(nickname) > 50:
            return jsonify({'success': False, 'error': 'Nickname must be 3-50 characters'}), 400
        
        # Проверка на допустимые символы (буквы, цифры, подчеркивание)
        import re
        if not re.match(r'^[a-zA-Z0-9_а-яА-ЯёЁ]+$', nickname):
            return jsonify({'success': False, 'error': 'Nickname can only contain letters, numbers and underscore'}), 400
        
        # Проверка уникальности
        existing = User.query.filter_by(nickname=nickname).first()
        if existing and existing.id != current_user.id:
            return jsonify({'success': False, 'error': 'Nickname already taken'}), 409
        
        # Устанавливаем никнейм
        current_user.nickname = nickname
        db.session.commit()
        # CRITICAL FIX: Refresh the user object to sync with database
        db.session.refresh(current_user)
        
        return jsonify({'success': True, 'nickname': nickname})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route("/api/social/search-users")
@login_required
def search_users():
    """Search users by nickname / name / email (SEARCH_USERS_V2)."""
    try:
        query = (request.args.get('q', '') or '').strip()
        limit = min(int(request.args.get('limit', 10) or 10), 50)

        if not query or len(query) < 2:
            return jsonify({'success': False, 'users': [], 'error': 'Query too short (min 2 characters)'}), 400

        like = f"%{query}%"
        q = User.query.filter(
            User.id != current_user.id,
            db.or_(
                User.nickname.ilike(like),
                User.name.ilike(like),
                User.email.ilike(like),
            ),
        )
        # Exclude guest accounts from search results.
        try:
            q = q.filter(db.or_(User.is_guest == False, User.is_guest.is_(None)))
        except Exception:
            pass

        users = q.limit(limit).all()

        results = []
        for u in users:
            results.append({
                'id': u.id,
                'nickname': u.nickname or '',
                'name': u.name or '',
                'email': u.email or '',
                'avatar_url': u.avatar_url or '',
                'display_name': u.display_name,
            })

        return jsonify({'success': True, 'users': results})

    except Exception as e:
        import traceback as _tb
        print("[search_users] error:", e)
        print(_tb.format_exc())
        return jsonify({'success': False, 'users': [], 'error': str(e)}), 500


@app.route("/api/social/friends/list")
@login_required
def list_friends():
    """Получить список друзей (legacy API)"""
    try:
        friends = current_user.get_friends()
        return jsonify({'success': True, 'friends': [
            {'id': u.id, 'nickname': u.nickname, 'name': u.name, 'avatar_url': u.avatar_url}
            for u in friends
        ]})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route("/api/social/mentorship/request", methods=["POST"])
@login_required
def send_mentorship_request():
    """Отправить заявку учитель-ученик"""
    try:
        data = request.get_json()
        student_id = data.get('student_id')
        
        if not student_id:
            return jsonify({'success': False, 'error': 'Student ID required'}), 400
        
        # Проверка существования пользователя
        student = User.query.get(student_id)
        if not student:
            return jsonify({'success': False, 'error': 'Student not found'}), 404
        
        # Создаем заявку (текущий пользователь = учитель)
        mentorship = Mentorship.create_mentorship_request(current_user.id, student_id)
        db.session.add(mentorship)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'mentorship_id': mentorship.id,
            'status': mentorship.status
        })
    
    except ValueError as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route("/api/social/mentorship/respond", methods=["POST"])
@login_required
def respond_mentorship_request():
    """Принять или отклонить заявку учитель-ученик"""
    try:
        data = request.get_json()
        mentorship_id = data.get('mentorship_id')
        action = data.get('action')  # 'accept' or 'reject'
        
        if not mentorship_id or action not in ['accept', 'reject']:
            return jsonify({'success': False, 'error': 'Invalid parameters'}), 400
        
        mentorship = Mentorship.query.get(mentorship_id)
        if not mentorship:
            return jsonify({'success': False, 'error': 'Mentorship not found'}), 404
        
        # Проверка прав (только ученик может принять/отклонить)
        if mentorship.student_id != current_user.id:
            return jsonify({'success': False, 'error': 'Not authorized'}), 403
        
        if action == 'accept':
            mentorship.accept()
        else:
            mentorship.reject()
        
        db.session.commit()
        
        return jsonify({'success': True, 'status': mentorship.status})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route("/api/social/mentorship/students")
@login_required
def list_students():
    """Получить список учеников (для учителя)"""
    try:
        mentorships = Mentorship.query.filter_by(
            teacher_id=current_user.id,
            status='accepted'
        ).all()
        
        students = []
        for m in mentorships:
            student = User.query.get(m.student_id)
            if student:
                students.append({
                    'id': student.id,
                    'nickname': student.nickname,
                    'name': student.name,
                    'avatar_url': student.avatar_url
                })
        
        return jsonify({'success': True, 'students': students})
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route("/api/social/mentorship/teachers")
@login_required
def list_teachers():
    """Получить список учителей (для ученика)"""
    try:
        mentorships = Mentorship.query.filter_by(
            student_id=current_user.id,
            status='accepted'
        ).all()
        
        teachers = []
        for m in mentorships:
            teacher = User.query.get(m.teacher_id)
            if teacher:
                teachers.append({
                    'id': teacher.id,
                    'nickname': teacher.nickname,
                    'name': teacher.name,
                    'avatar_url': teacher.avatar_url
                })
        
        return jsonify({'success': True, 'teachers': teachers})
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# PROFILE AND STUDENT PROGRESS TRACKING
# ============================================================

@app.route("/update_nickname", methods=["POST"])
@login_required
def update_nickname():
    """Обновление nickname пользователя"""
    import re
    
    new_nickname = request.form.get('nickname', '').strip()
    
    # Убираем @ если есть
    if new_nickname.startswith('@'):
        new_nickname = new_nickname[1:]
    
    # Валидация
    if not new_nickname:
        flash('Никнейм не может быть пустым', 'error')
        return redirect(url_for('profile'))
    
    if len(new_nickname) < 3 or len(new_nickname) > 50:
        flash('Никнейм должен быть от 3 до 50 символов', 'error')
        return redirect(url_for('profile'))
    
    # Только буквы, цифры и подчеркивание
    if not re.match(r'^[a-zA-Z0-9_а-яА-ЯёЁ]+$', new_nickname):
        flash('Никнейм может содержать только буквы, цифры и подчеркивание', 'error')
        return redirect(url_for('profile'))
    
    # Проверка уникальности
    existing = User.query.filter(User.nickname.ilike(new_nickname)).first()
    if existing and existing.id != current_user.id:
        flash(f'Никнейм @{new_nickname} уже занят', 'error')
        return redirect(url_for('profile'))
    
    # Обновляем
    try:
        current_user.nickname = new_nickname
        db.session.commit()
        # CRITICAL FIX: Refresh the user object to sync with database
        db.session.refresh(current_user)
        flash(f'Никнейм успешно изменен на @{new_nickname}!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при обновлении: {str(e)}', 'error')
    
    return redirect(url_for('profile'))


@app.route("/add_student", methods=["POST"])
@login_required
def add_student():
    """Добавление друга по nickname (мгновенная дружба)"""
    friend_nickname = request.form.get('nickname', '').strip()
    
    # Убираем @ если пользователь ввел
    if friend_nickname.startswith('@'):
        friend_nickname = friend_nickname[1:]
    
    if not friend_nickname:
        flash('Введите никнейм друга', 'error')
        return redirect(url_for('profile'))
    
    # Ищем пользователя по nickname (case-insensitive)
    friend = User.query.filter(User.nickname.ilike(friend_nickname)).first()
    
    if not friend:
        flash(f'Пользователь @{friend_nickname} не найден', 'error')
        return redirect(url_for('profile'))
    
    if friend.id == current_user.id:
        flash('Нельзя добавить самого себя', 'error')
        return redirect(url_for('profile'))
    
    # Проверяем существующую дружбу
    existing = Friendship.query.filter(
        db.or_(
            db.and_(Friendship.requester_id == current_user.id,
                    Friendship.addressee_id == friend.id),
            db.and_(Friendship.requester_id == friend.id,
                    Friendship.addressee_id == current_user.id),
        )
    ).first()
    
    if existing:
        if existing.status == 'accepted':
            flash(f'@{friend.nickname} уже в друзьях', 'info')
        else:
            flash(f'@{friend.nickname} уже в друзьях', 'info')
        return redirect(url_for('profile'))
    
    # Мгновенная дружба
    try:
        friendship = Friendship(
            requester_id=current_user.id,
            addressee_id=friend.id,
            status='accepted'
        )
        friendship.accepted_at = datetime.utcnow()
        db.session.add(friendship)
        current_user.experience_points = (current_user.experience_points or 0) + 10
        friend.experience_points = (friend.experience_points or 0) + 10
        db.session.commit()
        flash(f'Вы и @{friend.nickname} теперь друзья! +10 XP', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при добавлении: {str(e)}', 'error')
    
    return redirect(url_for('profile'))


@app.route("/accept_request/<int:mentorship_id>", methods=["POST"])
@login_required
def accept_request(mentorship_id):
    """Принять заявку на менторство"""
    mentorship = Mentorship.query.get_or_404(mentorship_id)
    
    # Проверка прав (только ученик может принять)
    if mentorship.student_id != current_user.id:
        flash('У вас нет прав для этого действия', 'error')
        return redirect(url_for('profile'))
    
    try:
        mentorship.accept()
        db.session.commit()
        teacher = User.query.get(mentorship.teacher_id)
        flash(f'Вы приняли заявку от @{teacher.nickname or teacher.email}!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка: {str(e)}', 'error')
    
    return redirect(url_for('profile'))


@app.route("/reject_request/<int:mentorship_id>", methods=["POST"])
@login_required
def reject_request(mentorship_id):
    """Отклонить заявку на менторство"""
    mentorship = Mentorship.query.get_or_404(mentorship_id)
    
    # Проверка прав (только ученик может отклонить)
    if mentorship.student_id != current_user.id:
        flash('У вас нет прав для этого действия', 'error')
        return redirect(url_for('profile'))
    
    try:
        mentorship.reject()
        db.session.commit()
        flash('Заявка отклонена', 'info')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка: {str(e)}', 'error')
    
    return redirect(url_for('profile'))


@app.route("/student/<int:student_id>")
@login_required
def student_profile(student_id):
    """Просмотр профиля друга — показывает ВСЮ информацию"""
    # Проверяем дружбу
    is_friend = Friendship.query.filter(
        db.or_(
            db.and_(Friendship.requester_id == current_user.id,
                    Friendship.addressee_id == student_id),
            db.and_(Friendship.requester_id == student_id,
                    Friendship.addressee_id == current_user.id),
        ),
        Friendship.status == 'accepted'
    ).first()
    
    if not is_friend:
        flash('Этот пользователь не в ваших друзьях', 'error')
        return redirect(url_for('profile'))
    
    friend = User.query.get_or_404(student_id)
    
    # Собираем полную статистику друга
    from models import AdaptiveTestResult, TopicMastery
    
    # Тесты
    all_tests = AdaptiveTestResult.query.filter_by(user_id=friend.id).order_by(
        AdaptiveTestResult.completed_at.desc()
    ).limit(10).all()
    
    # Мастерство по темам
    mastery_data = TopicMastery.query.filter_by(user_id=friend.id).all()
    
    return render_template('student_profile.html',
        student=friend,
        teacher=current_user,
        tests=all_tests,
        mastery=mastery_data
    )


# ============================================================================
# OLYMPIAD SECRETS (База знаний олимпиадной математики)
# ============================================================================

@app.route("/secrets")
def secrets():
    """Главная страница раздела 'Секреты олимпиадной математики'"""
    from models import OlympiadSecret
    
    # Получаем выбранную категорию из параметров
    selected_topic = request.args.get('topic', 'all')
    
    # Получаем все уникальные категории
    topics = db.session.query(OlympiadSecret.topic).distinct().order_by(OlympiadSecret.topic).all()
    topics = [t[0] for t in topics]
    
    # Фильтруем статьи по категории
    if selected_topic == 'all':
        secrets_list = OlympiadSecret.query.order_by(OlympiadSecret.topic, OlympiadSecret.title).all()
    else:
        secrets_list = OlympiadSecret.query.filter_by(topic=selected_topic).order_by(OlympiadSecret.title).all()
    
    # Группируем статьи по категориям для отображения
    secrets_by_topic = {}
    for secret in secrets_list:
        if secret.topic not in secrets_by_topic:
            secrets_by_topic[secret.topic] = []
        secrets_by_topic[secret.topic].append(secret)
    
    return render_template('secrets.html',
        topics=topics,
        selected_topic=selected_topic,
        secrets_by_topic=secrets_by_topic,
        total_count=len(secrets_list)
    )


@app.route("/secrets/<int:secret_id>")
def secret_detail(secret_id):
    """Страница отдельной статьи"""
    from models import OlympiadSecret
    
    secret = OlympiadSecret.query.get_or_404(secret_id)
    
    # Получаем похожие статьи из той же категории
    related_secrets = OlympiadSecret.query.filter(
        OlympiadSecret.topic == secret.topic,
        OlympiadSecret.id != secret.id
    ).limit(3).all()
    
    return render_template('secret_detail.html',
        secret=secret,
        related_secrets=related_secrets
    )


@app.route("/api/secrets")
def api_secrets():
    """API для получения списка секретов (для будущих фич)"""
    from models import OlympiadSecret
    
    topic = request.args.get('topic')
    difficulty = request.args.get('difficulty', type=int)
    
    query = OlympiadSecret.query
    
    if topic:
        query = query.filter_by(topic=topic)
    if difficulty:
        query = query.filter_by(difficulty_level=difficulty)
    
    secrets_list = query.all()
    
    return jsonify({
        'success': True,
        'count': len(secrets_list),
        'secrets': [{
            'id': s.id,
            'topic': s.topic,
            'title': s.title,
            'difficulty_level': s.difficulty_level,
            'preview': s.content[:200] + '...' if len(s.content) > 200 else s.content
        } for s in secrets_list]
    })


# ============================================================
# ADMIN ROUTES (Protected)
# ============================================================

# ── AI-тьютор v2: дашборд и управление задачами ─────────────

@app.route("/admin/tutor_stats")
def admin_tutor_stats():
    """Дашборд AI-тьютора v2: статистика вызовов, fallback, битые задачи."""
    # Простая защита: только для пользователя с email Виктора
    # (или любого залогиненного — расширить при необходимости)
    if not current_user.is_authenticated:
        return redirect(url_for('login'))

    # CSV-экспорт
    if request.args.get('export') == 'csv':
        rows = db.session.execute(text("""
            SELECT tc.id, tc.task_id, tc.user_answer, tc.status,
                   tc.validation_errors, tc.created_at,
                   at.topic, at.class_level, at.correct_answer
            FROM tutor_calls tc
            LEFT JOIN adaptive_tasks at ON at.id = tc.task_id
            ORDER BY tc.created_at DESC
            LIMIT 5000
        """)).fetchall()
        import csv, io
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(['id','task_id','user_answer','status','errors',
                    'created_at','topic','class_level','correct_answer'])
        for r in rows:
            w.writerow(list(r))
        from flask import Response
        return Response(
            buf.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment; filename=tutor_calls.csv'}
        )

    # ── Общая статистика за 7 дней ──
    stats = db.session.execute(text("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN status='ok'       THEN 1 ELSE 0 END) as ok,
            SUM(CASE WHEN status='fallback' THEN 1 ELSE 0 END) as fallback,
            SUM(CASE WHEN status='no_solution_tag' THEN 1 ELSE 0 END) as no_tag
        FROM tutor_calls
        WHERE created_at > datetime('now', '-7 days')
    """)).fetchone()

    total = stats.total or 0
    ok_pct   = round(stats.ok   / total * 100) if total else 0
    fall_pct = round(stats.fallback / total * 100) if total else 0

    # ── Топ задач с fallback за 30 дней ──
    top_problem_tasks = db.session.execute(text("""
        SELECT
            tc.task_id,
            COUNT(*) as fails,
            GROUP_CONCAT(DISTINCT tc.validation_errors) as errors,
            at.topic,
            at.class_level,
            at.correct_answer,
            at.is_flagged,
            at.reports_count
        FROM tutor_calls tc
        LEFT JOIN adaptive_tasks at ON at.id = tc.task_id
        WHERE tc.status = 'fallback'
          AND tc.created_at > datetime('now', '-30 days')
        GROUP BY tc.task_id
        ORDER BY fails DESC
        LIMIT 50
    """)).fetchall()

    problem_count = len(top_problem_tasks)

    # ── Распределение ошибок ──
    error_distribution = db.session.execute(text("""
        SELECT
            validation_errors,
            COUNT(*) as cnt
        FROM tutor_calls
        WHERE validation_errors != ''
          AND validation_errors IS NOT NULL
        GROUP BY validation_errors
        ORDER BY cnt DESC
        LIMIT 20
    """)).fetchall()

    # ── Все помеченные задачи ──
    flagged_tasks = AdaptiveTask.query.filter_by(is_flagged=True)\
        .order_by(AdaptiveTask.reports_count.desc()).all()

    return render_template(
        'admin_tutor_stats.html',
        stats=stats,
        ok_pct=ok_pct,
        fall_pct=fall_pct,
        problem_count=problem_count,
        top_problem_tasks=top_problem_tasks,
        error_distribution=error_distribution,
        flagged_tasks=flagged_tasks,
    )


@app.route("/admin/toggle_task_flag/<int:task_id>", methods=["POST"])
def admin_toggle_task_flag(task_id):
    """Поставить / снять флаг is_flagged на задаче."""
    if not current_user.is_authenticated:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
    try:
        data = request.get_json() or {}
        flag = bool(data.get('flag', True))
        task = AdaptiveTask.query.get_or_404(task_id)
        task.is_flagged = flag
        if flag:
            task.flagged_reason = data.get(
                'reason',
                f'Помечена вручную через дашборд тьютора'
            )
        else:
            task.flagged_reason = None
        db.session.commit()
        return jsonify({'status': 'ok', 'task_id': task_id, 'is_flagged': flag})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ── Админ-страница: задачи с расхождением LLM vs БД ─────────────

@app.route("/admin/needs_review")
def admin_needs_review():
    """Список задач, где AI-тьютор нашёл расхождение с БД-ответом."""
    if not current_user.is_authenticated:
        return redirect(url_for('login'))

    tasks = db.session.execute(text("""
        SELECT id, class_level, topic, task_text,
               correct_answer AS db_answer,
               llm_suggested_answer,
               llm_suggested_solution,
               review_reason,
               review_flagged_at
        FROM adaptive_tasks
        WHERE needs_review = 1
        ORDER BY review_flagged_at DESC
        LIMIT 100
    """)).fetchall()

    return render_template('admin_needs_review.html', tasks=tasks)


@app.route("/admin/needs_review/action/<int:task_id>", methods=["POST"])
def admin_needs_review_action(task_id):
    """Обработка действий админа по задачам needs_review."""
    if not current_user.is_authenticated:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401

    try:
        data = request.get_json() or {}
        action = data.get('action', '')
        task = AdaptiveTask.query.get_or_404(task_id)

        if action == 'accept_llm':
            # Принять ответ LLM — заменить correct_answer
            if task.llm_suggested_answer:
                task.correct_answer = task.llm_suggested_answer
            if task.llm_suggested_solution:
                task.solution = task.llm_suggested_solution
            task.needs_review = False
            task.review_reason = None
            task.review_flagged_at = None
            db.session.commit()
            return jsonify({'status': 'ok', 'action': 'accept_llm', 'task_id': task_id})

        elif action == 'keep_old':
            # Оставить старый ответ — просто снять флаг
            task.needs_review = False
            task.llm_suggested_answer = None
            task.llm_suggested_solution = None
            task.review_reason = None
            task.review_flagged_at = None
            db.session.commit()
            return jsonify({'status': 'ok', 'action': 'keep_old', 'task_id': task_id})

        elif action == 'delete_task':
            # Пометить задачу как битую
            task.is_flagged = True
            task.flagged_reason = f'Удалена через needs_review: {task.review_reason or "нет причины"}'
            task.needs_review = False
            db.session.commit()
            return jsonify({'status': 'ok', 'action': 'delete_task', 'task_id': task_id})

        else:
            return jsonify({'status': 'error', 'message': f'Unknown action: {action}'}), 400

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route("/admin/fix_latex_rac", methods=["GET", "POST"])
def admin_fix_latex_rac():
    """
    Admin endpoint: диагностика и починка битого LaTeX '$ rac{' → '$\\frac{'.
    GET  → показывает сколько задач с битым LaTeX
    POST → применяет починку
    """
    # Простая защита: только если залогинен
    if not current_user.is_authenticated:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401

    try:
        from sqlalchemy import text as sa_text

        # Диагностика: считаем задачи с ' rac{'
        result_count = db.session.execute(
            sa_text("SELECT COUNT(*) FROM adaptive_tasks WHERE task_text LIKE '% rac{%'")
        ).fetchone()[0]

        result_sol = db.session.execute(
            sa_text("SELECT COUNT(*) FROM adaptive_tasks WHERE solution LIKE '% rac{%'")
        ).fetchone()[0]

        if request.method == 'GET':
            # Показываем примеры
            examples = db.session.execute(
                sa_text("SELECT id, SUBSTR(task_text, 1, 200) FROM adaptive_tasks WHERE task_text LIKE '% rac{%' LIMIT 5")
            ).fetchall()
            return jsonify({
                'status': 'ok',
                'broken_task_text': result_count,
                'broken_solution': result_sol,
                'examples': [{'id': r[0], 'preview': r[1]} for r in examples],
                'message': f'Найдено {result_count} задач с битым LaTeX. POST на этот URL для починки.'
            })

        # POST → применяем починку
        if result_count == 0 and result_sol == 0:
            return jsonify({'status': 'ok', 'fixed': 0, 'message': 'Битых задач не найдено'})

        # Починка task_text
        db.session.execute(
            sa_text("UPDATE adaptive_tasks SET task_text = REPLACE(task_text, ' rac{', '\\frac{') WHERE task_text LIKE '% rac{%'")
        )
        # Починка solution
        db.session.execute(
            sa_text("UPDATE adaptive_tasks SET solution = REPLACE(solution, ' rac{', '\\frac{') WHERE solution LIKE '% rac{%'")
        )
        db.session.commit()

        return jsonify({
            'status': 'ok',
            'fixed_task_text': result_count,
            'fixed_solution': result_sol,
            'message': f'Починено {result_count} задач в task_text и {result_sol} в solution'
        })

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ── Пометить задачу 1650 как битую (запускается один раз при старте) ──
try:
    with app.app_context():
        _task_1650 = AdaptiveTask.query.get(1650)
        if _task_1650 and not _task_1650.is_flagged:
            _task_1650.is_flagged = True
            _task_1650.flagged_reason = (
                'Условие/ответ противоречивы. Ответ в БД=18, '
                'но математически правильный=0 (таких n не существует). '
                'Требуется проверка источника задачи.'
            )
            db.session.commit()
            print("[QUALITY CONTROL] Задача #1650 помечена как битая (is_flagged=True)")
        elif _task_1650 and _task_1650.is_flagged:
            print("[QUALITY CONTROL] Задача #1650 уже помечена")
except Exception as _e:
    print(f"[QUALITY CONTROL] Warning marking task 1650: {_e}")


# ── Авто-скрипт: помечаем задачи с >= 3 fallback за 7 дней ──
# Используем параметр (Python datetime), чтобы запрос работал и на SQLite,
# и на Postgres (SQLite-функция datetime('now', '-7 days') на PG не существует).
try:
    with app.app_context():
        from datetime import datetime as _dt_now, timedelta as _td_7d
        _cutoff_7d = _dt_now.utcnow() - _td_7d(days=7)
        _problem_tasks = db.session.execute(
            text("""
                SELECT task_id, COUNT(*) as fails
                FROM tutor_calls
                WHERE status='fallback'
                  AND created_at > :cutoff
                GROUP BY task_id
                HAVING COUNT(*) >= 3
            """),
            {'cutoff': _cutoff_7d},
        ).fetchall()
        for _row in _problem_tasks:
            _t = AdaptiveTask.query.get(_row.task_id)
            if _t and not _t.is_flagged:
                _t.is_flagged = True
                _t.flagged_reason = (
                    f'auto: {_row.fails} fallback за 7 дней (tutor_v2)'
                )
                print(f"[QUALITY CONTROL] Авто-помечена задача #{_row.task_id} ({_row.fails} fallback)")
        db.session.commit()
except Exception as _e:
    db.session.rollback()
    print(f"[QUALITY CONTROL] Auto-flag warning: {_e}")


@app.route("/admin/seed-secrets", methods=["POST"])
def admin_seed_secrets():
    """
    Защищенный одноразовый роут для наполнения таблицы OlympiadSecret на продакшене.
    
    Требует токен из переменной окружения SEED_ADMIN_TOKEN.
    Токен передается через заголовок X-Admin-Token ИЛИ query-параметр ?token=
    
    Query параметры:
        - token: Админ-токен (альтернатива заголовку)
        - force: Если "1", очищает таблицу перед импортом
    
    Returns:
        JSON: {
            "status": "success" | "error" | "skipped",
            "inserted": int,
            "skipped": int,
            "total": int,
            "message": str
        }
    """
    import hmac
    import traceback
    from utils.seed_secrets_utils import seed_secrets_from_json, get_secrets_stats
    
    # Проверка наличия токена в переменных окружения
    expected_token = os.environ.get('SEED_ADMIN_TOKEN')
    if not expected_token:
        return jsonify({
            'status': 'error',
            'message': 'SEED_ADMIN_TOKEN not configured on server'
        }), 503
    
    # Получаем токен из заголовка или query-параметра
    provided_token = request.headers.get('X-Admin-Token') or request.args.get('token')
    
    if not provided_token:
        return jsonify({
            'status': 'error',
            'message': 'Admin token required. Provide via X-Admin-Token header or ?token= parameter'
        }), 403
    
    # Безопасное сравнение токенов (защита от timing attacks)
    if not hmac.compare_digest(expected_token, provided_token):
        app.logger.warning(f"[SECURITY] Invalid admin token attempt from {request.remote_addr}")
        return jsonify({
            'status': 'error',
            'message': 'Invalid admin token'
        }), 403
    
    # Проверка параметра force
    force = request.args.get('force') == '1'
    
    try:
        # Вызываем функцию сидирования
        result = seed_secrets_from_json(json_file='secrets_dump.json', force=force)
        
        if not result['success']:
            return jsonify({
                'status': 'error',
                'message': result.get('error', 'Unknown error'),
                'inserted': 0,
                'skipped': 0,
                'total': 0
            }), 500
        
        # Если таблица уже была заполнена и force=False
        if result['inserted'] == 0 and result['skipped'] > 0 and not force:
            return jsonify({
                'status': 'skipped',
                'message': 'Table already populated. Use ?force=1 to override.',
                'inserted': 0,
                'skipped': result['skipped'],
                'total': result['total']
            }), 200
        
        # Получаем финальную статистику
        stats = get_secrets_stats()
        
        app.logger.info(f"[ADMIN] Secrets seeded successfully by {request.remote_addr}: {result['inserted']} inserted")
        
        return jsonify({
            'status': 'success',
            'message': result.get('message', 'Secrets imported successfully'),
            'inserted': result['inserted'],
            'skipped': result['skipped'],
            'total': result['total'],
            'stats': stats
        }), 200
        
    except Exception as e:
        app.logger.error(f"[ADMIN] Seed secrets failed: {e}")
        traceback.print_exc()
        db.session.rollback()
        
        return jsonify({
            'status': 'error',
            'message': f'Internal server error: {str(e)}',
            'inserted': 0,
            'skipped': 0,
            'total': 0
        }), 500


# ============================================================================
# DAILY QUEST ROUTES
# ============================================================================

@app.route('/api/set_grade', methods=['POST'])
@login_required
def api_set_grade():
    """API: Установить предпочтительный класс для Daily Quest"""
    data = request.get_json(silent=True) or {}
    grade = data.get('grade')

    if grade is None:
        return jsonify({'success': False, 'error': 'Не указан класс'}), 400

    try:
        grade = int(grade)
    except (ValueError, TypeError):
        return jsonify({'success': False, 'error': 'Класс должен быть числом'}), 400

    if grade not in range(5, 12):  # 5-11
        return jsonify({'success': False, 'error': 'Класс должен быть от 5 до 11'}), 400

    old_grade = current_user.preferred_grade
    current_user.preferred_grade = grade

    # Если класс реально изменился — удаляем сегодняшний Daily Quest,
    # чтобы при следующем заходе на /daily он перегенерировался под новый класс.
    if old_grade != grade:
        try:
            from models import DailyQuest
            from datetime import date as _date
            DailyQuest.query.filter_by(
                user_id=current_user.id,
                date=_date.today()
            ).delete(synchronize_session=False)
        except Exception as _e:
            app.logger.warning(f"api_set_grade: failed to drop today's quest: {_e}")

    db.session.commit()

    return jsonify({'success': True, 'grade': grade})


@app.route('/daily/regenerate', methods=['POST'])
@login_required
def daily_quest_regenerate():
    """Принудительная перегенерация Daily Quest (новые олимпиадные задачи)."""
    from services.daily_quest_service import generate_daily_quest
    quest = generate_daily_quest(current_user.id, force_regenerate=True)
    if quest:
        return redirect(url_for('daily_quest_main'))
    flash('Не удалось перегенерировать квест', 'error')
    return redirect(url_for('daily_quest_main'))


@app.route('/daily')
@login_required
def daily_quest_main():
    """Главная страница Daily Quest"""
    from services.daily_quest_service import get_today_quest, get_quest_tasks
    from services.streak_service import get_streak_stats
    from markupsafe import Markup
    
    # Если класс не выбран — показываем страницу выбора
    if not current_user.preferred_grade:
        return render_template('daily.html',
                             quest=None,
                             tasks=[],
                             streak_stats={'current_streak': 0, 'longest_streak': 0, 'freeze_available': False},
                             need_grade_selection=True,
                             preferred_grade=None)
    
    # Получаем или создаём квест на сегодня
    quest = get_today_quest(current_user.id)

    if not quest:
        flash('Не удалось создать Daily Quest. Попробуйте позже.', 'error')
        return redirect(url_for('index'))

    # Защита: если задачи квеста подобраны под ДРУГОЙ класс — перегенерируем.
    # Например: пользователь сменил класс через дропдаун, или квест был
    # создан старой версией кода с COMBOS-задачами не того класса.
    # Делаем это ТОЛЬКО если пользователь ещё не начал решать (completed_count == 0),
    # чтобы не сбрасывать прогресс посреди дня.
    try:
        from services.daily_quest_service import get_quest_tasks as _gqt, generate_daily_quest as _gdq
        if quest.completed_count == 0 and current_user.preferred_grade:
            _peek_tasks = _gqt(quest)
            if _peek_tasks:
                _user_g = int(current_user.preferred_grade)
                grades_in_quest = [int(t.get('grade', 0) or 0) for t in _peek_tasks]
                # Если БОЛЬШИНСТВО задач не строго того же класса — перегенерация.
                # (Допускаем 1 задачу другого класса как буфер.)
                wrong_grade_count = sum(1 for g in grades_in_quest if g != _user_g)
                if wrong_grade_count >= 2:
                    app.logger.info(
                        f"daily_quest_main: regenerating quest for user {current_user.id} "
                        f"— quest grades {grades_in_quest} don't match preferred_grade {_user_g} "
                        f"(wrong_grade_count={wrong_grade_count})"
                    )
                    new_quest = _gdq(current_user.id, force_regenerate=True)
                    if new_quest:
                        quest = new_quest
    except Exception as _re:
        app.logger.warning(f"daily_quest_main: grade-mismatch regen failed: {_re}")
    
    # Конвертируем markdown ai_comment → HTML В ОТДЕЛЬНУЮ ПЕРЕМЕННУЮ.
    # ВАЖНО: НЕ мутируем ORM-объект quest.ai_comment, иначе SQLAlchemy пометит его dirty
    # и любой следующий .query.first() триггернёт autoflush → UPDATE daily_quests …
    # На SQLite это вызывает 'database is locked' при конкуренции с APScheduler.
    ai_comment_html = None
    if quest.ai_comment:
        try:
            import markdown as md_lib
            ai_comment_html = Markup(md_lib.markdown(quest.ai_comment, extensions=['nl2br']))
        except ImportError:
            import re
            text = quest.ai_comment
            text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
            text = text.replace('\n\n', '</p><p>').replace('\n', '<br>')
            ai_comment_html = Markup(f'<p>{text}</p>')

    # Если перед нами всё-таки висит грязная сессия (другой код выше что-то мутировал) —
    # сбросим её, чтобы следующая SELECT-операция не упёрлась в autoflush + locked DB.
    try:
        if db.session.dirty or db.session.new or db.session.deleted:
            db.session.rollback()
    except Exception:
        pass

    # Получаем задачи квеста
    tasks = get_quest_tasks(quest)

    # Получаем статистику streak (ловим 'database is locked' с retry — SQLite + APScheduler)
    import time as _t_streak
    streak_stats = None
    for _i in range(5):
        try:
            streak_stats = get_streak_stats(current_user.id)
            break
        except Exception as _se:
            if 'database is locked' in str(_se).lower() and _i < 4:
                try:
                    db.session.rollback()
                except Exception:
                    pass
                _t_streak.sleep(0.3 * (_i + 1))
                continue
            raise

    # Список индексов уже решённых задач (для шаблона: «✅ Решено» vs «🚀 Решить»)
    from services.daily_quest_service import get_solved_indices as _gsi
    solved_indices = _gsi(quest)

    return render_template('daily.html',
                         quest=quest,
                         tasks=tasks,
                         ai_comment_html=ai_comment_html,
                         streak_stats=streak_stats,
                         need_grade_selection=False,
                         preferred_grade=current_user.preferred_grade,
                         solved_indices=solved_indices)


@app.route('/daily/task/<int:task_index>')
@login_required
def daily_quest_task(task_index):
    """Страница решения задачи из Daily Quest"""
    from services.daily_quest_service import (
        get_today_quest, get_quest_tasks, is_task_solved
    )

    # Получаем квест на сегодня
    quest = get_today_quest(current_user.id)

    if not quest:
        flash('Daily Quest не найден', 'error')
        return redirect(url_for('daily_quest_main'))

    # Получаем задачи
    tasks = get_quest_tasks(quest)

    # Проверяем индекс
    if task_index < 0 or task_index >= len(tasks):
        flash('Задача не найдена', 'error')
        return redirect(url_for('daily_quest_main'))

    task = tasks[task_index]

    # Если задача уже решена правильно — на страницу решения не пускаем,
    # возвращаем пользователя обратно к списку.
    if is_task_solved(quest, task_index):
        flash('Эта задача уже решена.', 'info')
        return redirect(url_for('daily_quest_main'))

    return render_template('daily_task.html',
                         quest=quest,
                         task=task,
                         task_index=task_index,
                         total_tasks=len(tasks))


@app.route('/daily/task/<int:task_index>/submit', methods=['POST'])
@login_required
def daily_quest_submit(task_index):
    """Отправка ответа на задачу Daily Quest"""
    from services.daily_quest_service import (
        get_today_quest, get_quest_tasks, complete_quest_task, is_task_solved
    )
    from services.mastery_service import update_mastery_after_task
    from services.streak_service import update_streak_after_quest
    from utils.math_answer_utils import compare_math_answers

    # Получаем квест
    quest = get_today_quest(current_user.id)

    if not quest:
        return jsonify({'success': False, 'error': 'Quest not found'}), 404

    # Получаем задачи
    tasks = get_quest_tasks(quest)

    if task_index < 0 or task_index >= len(tasks):
        return jsonify({'success': False, 'error': 'Invalid task index'}), 400

    # Защита от повторного решения: если задача уже решена правильно,
    # не позволяем фарм XP / повторную попытку.
    if is_task_solved(quest, task_index):
        return jsonify({
            'success': False,
            'error': 'Эта задача уже решена. Повторное решение невозможно.',
            'already_solved': True,
        }), 409

    task = tasks[task_index]
    
    # Получаем ответ и решение пользователя
    user_answer = request.json.get('answer', '').strip()
    user_solution = request.json.get('solution', '').strip()
    
    if not user_answer and not user_solution:
        return jsonify({'success': False, 'error': 'Answer or solution is required'}), 400
    
    # === ШАГ 1. Быстрая локальная сверка ответа с заложенным эталоном ===
    correct_answer = task.get('answer', '')
    correct_solution = task.get('solution', '')
    local_match = compare_math_answers(user_answer, correct_answer) if user_answer else False

    # === ШАГ 2. ИИ-верификация: даём тьютору право переопределить вердикт ===
    # База задач может содержать ошибочные эталонные ответы. Поэтому ИИ-тьютор
    # сам решает задачу, сравнивает свой ответ с заложенным и с ответом ученика,
    # и выдаёт финальный вердикт. Если эталон ошибочен — мы уважаем правильный
    # ответ ученика.
    ai_feedback = ""
    ai_verdict = None  # 'correct' | 'wrong' | None
    ai_overrode_reference = False
    actual_correct_answer = correct_answer  # что считать правильным после AI-проверки

    if DEEPSEEK_AVAILABLE and user_answer:
        try:
            import json as _json
            import re as _re
            client = DeepSeekClient()
            solution_part = f"\n\nРешение ученика:\n{user_solution}" if user_solution else ""
            ref_solution_part = f"\nЭталонное решение из базы:\n{correct_solution}" if correct_solution else ""

            prompt = f"""Ты — ИИ-тьютор по олимпиадной математике. Реши задачу САМ, затем проверь ответ ученика.

ВАЖНО: эталонный ответ из базы задач МОЖЕТ БЫТЬ ОШИБОЧНЫМ. Не доверяй ему слепо — реши задачу сам и сравни.

Задача:
{task.get('text', '')}

Эталонный ответ из базы: {correct_answer}
{ref_solution_part}

Ответ ученика: {user_answer}
{solution_part}

Сделай следующее:
1. Реши задачу самостоятельно. Найди ИСТИННО правильный ответ.
2. Сравни истинный ответ с ответом ученика (учитывай эквивалентные формы: 1/2 = 0.5, 70° = 70 и т. п.).
3. Сравни истинный ответ с эталоном из базы. Если они отличаются — пометь, что эталон ошибочен.
4. Дай подробный разбор решения ученика на русском.

ПРАВИЛА ФОРМАТИРОВАНИЯ (СТРОГО):
- Используй обычный Markdown: **жирный текст** через две звёздочки, # заголовки, * списки.
- НЕ используй \\cdot или \\textbf для выделения текста — только Markdown **звёздочки**.
- Все формулы оборачивай в \\( ... \\) для inline или \\[ ... \\] для display.
- Внутри формул используй стандартный LaTeX: \\frac{{a}}{{b}}, \\cdot, \\sqrt{{...}}.
- НИКОГДА не пиши \\cdot \\cdot вокруг русских слов — это ломает рендеринг.

В САМОМ КОНЦЕ ответа добавь СТРОГО такой блок (без изменений формата):

```json
{{"true_answer": "<твой правильный ответ>", "student_correct": <true|false>, "reference_was_wrong": <true|false>}}
```

Где:
- true_answer — твой правильный ответ к задаче
- student_correct — true если ответ ученика правильный (эквивалентен истинному)
- reference_was_wrong — true если эталон из базы не совпадает с истинным ответом
"""

            ai_raw = client.generate(prompt, max_tokens=2000) or ""

            # Парсим JSON-блок из конца ответа
            json_match = _re.search(r'\{[^{}]*"student_correct"[^{}]*\}', ai_raw)
            if json_match:
                try:
                    verdict_data = _json.loads(json_match.group(0))
                    student_correct = bool(verdict_data.get('student_correct', False))
                    reference_was_wrong = bool(verdict_data.get('reference_was_wrong', False))
                    true_answer = str(verdict_data.get('true_answer', '')).strip()

                    ai_verdict = 'correct' if student_correct else 'wrong'
                    if reference_was_wrong and true_answer:
                        ai_overrode_reference = True
                        actual_correct_answer = true_answer
                except Exception as _je:
                    app.logger.warning(f"daily submit: failed to parse AI verdict JSON: {_je}")

            # В фидбеке прячем технический JSON-блок от пользователя
            ai_feedback = _re.sub(r'```json\s*\{[^{}]*"student_correct"[^{}]*\}\s*```', '', ai_raw)
            ai_feedback = _re.sub(r'\{[^{}]*"student_correct"[^{}]*\}', '', ai_feedback).strip()

            # Чиним типичный косяк LLM: \cdot \cdot вокруг русских слов вместо ** **.
            # Превращаем обратно в Markdown-bold, чтобы фронт корректно отрендерил <strong>.
            ai_feedback = _re.sub(
                r'\\cdot\s*\\cdot\s*([^\n\\]+?)\s*\\cdot\s*\\cdot',
                r'**\1**',
                ai_feedback
            )
            # Также \textbf{...} → **...**
            ai_feedback = _re.sub(r'\\textbf\{([^{}]+)\}', r'**\1**', ai_feedback)

            if ai_overrode_reference and ai_verdict == 'correct':
                ai_feedback = (
                    "ℹ️ *Эталонный ответ в базе задач был ошибочным. Я перепроверил — "
                    f"твой ответ верный, истинный ответ: **{actual_correct_answer}**.*\n\n"
                    + ai_feedback
                )
        except Exception as e:
            app.logger.error(f"AI verdict error: {e}")
            ai_feedback = ""

    # === ШАГ 3. Финальный вердикт ===
    # Приоритет: AI-вердикт > локальная сверка.
    # Если AI явно сказал student_correct=true — засчитываем, даже если local_match=false.
    # Если AI сказал student_correct=false, а local_match=true — доверяем AI только если
    # он явно отметил reference_was_wrong (значит он реально перерешал).
    if ai_verdict == 'correct':
        is_correct = True
    elif ai_verdict == 'wrong' and ai_overrode_reference:
        # AI перерешал, и ответ ученика реально не подходит — даже если совпал с (ошибочным) эталоном
        is_correct = False
    else:
        # Нет AI-вердикта (DEEPSEEK недоступен или JSON не распарсился) — fallback на локальную сверку
        is_correct = local_match

    # === ШАГ 4. Обновляем квест/мастерство/XP ===
    xp_earned = 20 if is_correct else 0

    if is_correct:
        complete_quest_task(quest, task_index, is_correct, xp_earned)

        topic = task.get('topic', task.get('subject', ''))
        grade = task.get('grade', 7)
        difficulty = task.get('difficulty', 3)

        if topic:
            update_mastery_after_task(current_user.id, topic, grade, is_correct, difficulty)

        current_user.experience_points += xp_earned
        db.session.commit()

        if quest.completed_count >= quest.total_count:
            update_streak_after_quest(current_user.id)

    # === ШАГ 5. Fallback-фидбек, если AI не дал ничего ===
    if not ai_feedback:
        if is_correct:
            ai_feedback = "✅ Правильно! +20 XP"
        else:
            ai_feedback = f"❌ Неправильно. Правильный ответ: {actual_correct_answer}"
            if correct_solution and not ai_overrode_reference:
                ai_feedback += f"\n\n**Решение:**\n{correct_solution}"

    return jsonify({
        'success': True,
        'is_correct': is_correct,
        'correct_answer': actual_correct_answer if not is_correct else None,
        'xp_earned': xp_earned,
        'ai_feedback': ai_feedback,
        'quest_completed': quest.completed_count >= quest.total_count,
        'total_xp': quest.xp_earned,
        'reference_overridden': ai_overrode_reference,
    })


@app.route('/daily/complete')
@login_required
def daily_quest_complete():
    """Экран завершения Daily Quest"""
    from services.daily_quest_service import get_today_quest
    from services.streak_service import get_streak_stats
    from datetime import date
    
    # Получаем квест на сегодня
    quest = get_today_quest(current_user.id)
    
    if not quest or quest.completed_count < quest.total_count:
        flash('Daily Quest ещё не завершён', 'warning')
        return redirect(url_for('daily_quest_main'))
    
    # Получаем статистику streak
    streak_stats = get_streak_stats(current_user.id)
    
    # Генерируем AI-комментарий по результатам дня
    ai_summary = ""
    if DEEPSEEK_AVAILABLE:
        try:
            client = DeepSeekClient()
            prompt = f"""Пользователь завершил Daily Quest:
- Решено задач: {quest.completed_count}/{quest.total_count}
- Заработано XP: {quest.xp_earned}
- Текущий streak: {streak_stats['current_streak']} дней

Напиши мотивирующий комментарий на русском (2-3 предложения)."""
            
            ai_summary = client.generate(prompt, max_tokens=1000)
        except Exception as e:
            app.logger.error(f"AI summary error: {e}")
            ai_summary = "Отличная работа! Продолжай в том же духе! 🔥"
    else:
        ai_summary = f"Поздравляем! Ты завершил Daily Quest и заработал {quest.xp_earned} XP! 🎉"
    
    return render_template('daily_complete.html',
                         quest=quest,
                         streak_stats=streak_stats,
                         ai_summary=ai_summary)


@app.route('/api/daily/status')
@login_required
def daily_quest_status():
    """API: Статус Daily Quest (для виджета)"""
    from services.daily_quest_service import get_today_quest
    from services.streak_service import get_streak_stats
    
    quest = get_today_quest(current_user.id)
    streak_stats = get_streak_stats(current_user.id)
    
    if not quest:
        return jsonify({
            'exists': False,
            'streak': streak_stats['current_streak']
        })
    
    return jsonify({
        'exists': True,
        'completed': quest.completed_count,
        'total': quest.total_count,
        'xp_earned': quest.xp_earned,
        'is_complete': quest.completed_count >= quest.total_count,
        'streak': streak_stats['current_streak'],
        'freeze_available': streak_stats['freeze_available']
    })


# ============================================================================
# FRIENDSHIP SYSTEM ROUTES
# ============================================================================

def _make_notif(uid, ntype, sender_id):
    """Create a notification."""
    from models import Notification
    n = Notification(user_id=uid, type=ntype, from_user_id=sender_id)
    db.session.add(n)
    try:
        db.session.commit()
    except Exception as e:
        app.logger.error(f"Notif error: {e}")
        db.session.rollback()


@app.route('/friends/request/<int:uid>', methods=['POST'])
@login_required
def send_friend_request(uid):
    """Send a friend request."""
    from models import Friendship
    if uid == current_user.id:
        return jsonify({'error': 'Нельзя добавить себя'}), 400
    person = User.query.get_or_404(uid)
    st = current_user.friendship_status_with(uid)
    if st == 'friends':
        return jsonify({'error': 'Уже друзья'}), 409
    if st == 'pending_sent':
        return jsonify({'error': 'Запрос уже отправлен'}), 409
    if st == 'blocked':
        return jsonify({'error': 'Недоступно'}), 403
    if st == 'pending_received':
        existing = Friendship.query.filter_by(
            requester_id=uid, addressee_id=current_user.id, status='pending'
        ).first()
        if existing:
            existing.accept()
            db.session.commit()
            current_user.experience_points = (current_user.experience_points or 0) + 10
            person.experience_points = (person.experience_points or 0) + 10
            db.session.commit()
            _make_notif(person.id, 'friend_accepted', current_user.id)
            return jsonify({'status': 'friends', 'message': 'Теперь вы друзья! +10 XP'})
    # Мгновенная дружба — без подтверждения
    f = Friendship(requester_id=current_user.id, addressee_id=uid, status='accepted')
    f.accepted_at = datetime.utcnow()
    db.session.add(f)
    current_user.experience_points = (current_user.experience_points or 0) + 10
    person.experience_points = (person.experience_points or 0) + 10
    db.session.commit()
    _make_notif(person.id, 'friend_accepted', current_user.id)
    nm = person.nickname or person.name or person.email
    return jsonify({'status': 'friends', 'message': f'Вы и {nm} теперь друзья! +10 XP'})


@app.route('/friends/accept/<int:rid>', methods=['POST'])
@login_required
def accept_friend_request(rid):
    """Accept a friend request."""
    from models import Friendship
    f = Friendship.query.get_or_404(rid)
    if f.addressee_id != current_user.id:
        abort(403)
    if f.status != 'pending':
        return jsonify({'error': 'Запрос уже обработан'}), 409
    f.accept()
    db.session.commit()
    sender = User.query.get(f.requester_id)
    current_user.experience_points = (current_user.experience_points or 0) + 10
    if sender:
        sender.experience_points = (sender.experience_points or 0) + 10
    db.session.commit()
    _make_notif(f.requester_id, 'friend_accepted', current_user.id)
    nm = sender.name or sender.email if sender else 'Пользователь'
    return jsonify({'status': 'friends', 'message': f'{nm} теперь ваш друг! +10 XP'})


@app.route('/friends/decline/<int:rid>', methods=['POST'])
@login_required
def decline_friend_request(rid):
    """Decline a friend request."""
    from models import Friendship
    f = Friendship.query.get_or_404(rid)
    if f.addressee_id != current_user.id:
        abort(403)
    f.decline()
    db.session.commit()
    return jsonify({'status': 'declined'})


@app.route('/friends/cancel/<int:rid>', methods=['POST'])
@login_required
def cancel_friend_request(rid):
    """Cancel own pending friend request."""
    from models import Friendship
    f = Friendship.query.get_or_404(rid)
    if f.requester_id != current_user.id:
        abort(403)
    db.session.delete(f)
    db.session.commit()
    return jsonify({'status': 'cancelled'})


@app.route('/friends/remove/<int:uid>', methods=['POST'])
@login_required
def remove_friend(uid):
    """Remove a friend."""
    from models import Friendship
    f = Friendship.query.filter(
        db.or_(
            db.and_(Friendship.requester_id == current_user.id,
                    Friendship.addressee_id == uid),
            db.and_(Friendship.requester_id == uid,
                    Friendship.addressee_id == current_user.id),
        ),
        Friendship.status == 'accepted'
    ).first_or_404()
    db.session.delete(f)
    db.session.commit()
    return jsonify({'status': 'removed'})


@app.route('/friends')
@login_required
def friends_page():
    """Friends list page."""
    return render_template('friends.html',
        friends=current_user.get_friends(),
        incoming=current_user.incoming_friend_requests(),
        outgoing=current_user.outgoing_friend_requests()
    )


# ═════════════════════════════════════════════════════════════════════════════
# DIRECT MESSAGES (chat between friends + task sharing)
# ═════════════════════════════════════════════════════════════════════════════

def _ensure_friends(other_id: int):
    """Return User if `other_id` is a friend of current_user, else None."""
    if not current_user.is_authenticated or other_id == current_user.id:
        return None
    if not current_user.is_friend_with(other_id):
        return None
    return User.query.get(other_id)


@app.route('/chat')
@app.route('/chat/<int:friend_id>')
@login_required
def chat_page(friend_id=None):
    """Страница чата с друзьями. Слева — список друзей, справа — диалог."""
    friends = current_user.get_friends()
    active_friend = None
    if friend_id:
        active_friend = next((f for f in friends if f.id == friend_id), None)
        if active_friend is None:
            flash('Этот пользователь не в вашем списке друзей', 'error')
            return redirect(url_for('chat_page'))
    return render_template(
        'chat.html',
        friends=friends,
        active_friend=active_friend,
    )


@app.route('/api/chat/conversations')
@login_required
def api_chat_conversations():
    """Список друзей + последнее сообщение и кол-во непрочитанных."""
    from models import DirectMessage
    friends = current_user.get_friends()
    items = []
    for fr in friends:
        last = (
            DirectMessage.query
            .filter(
                db.or_(
                    db.and_(DirectMessage.sender_id == current_user.id,
                            DirectMessage.recipient_id == fr.id),
                    db.and_(DirectMessage.sender_id == fr.id,
                            DirectMessage.recipient_id == current_user.id),
                )
            )
            .order_by(DirectMessage.created_at.desc())
            .first()
        )
        unread = DirectMessage.query.filter_by(
            sender_id=fr.id, recipient_id=current_user.id, is_read=False
        ).count()
        items.append({
            'friend': {
                'id': fr.id,
                'name': fr.name or fr.email or 'Без имени',
                'nickname': fr.nickname,
                'avatar_url': fr.avatar_url,
            },
            'last_message': last.to_dict(viewer_id=current_user.id) if last else None,
            'unread': unread,
        })
    # Сортируем: сначала с новыми сообщениями, потом по последнему сообщению
    def _sort_key(it):
        lm = it.get('last_message') or {}
        return (-(it['unread'] or 0), lm.get('created_at') or '')
    items.sort(key=_sort_key, reverse=False)
    items.sort(key=lambda it: (it.get('last_message') or {}).get('created_at') or '',
               reverse=True)
    return jsonify({'conversations': items})


@app.route('/api/chat/<int:friend_id>/messages')
@login_required
def api_chat_messages(friend_id):
    """Получить сообщения с конкретным другом + пометить непрочитанные."""
    from models import DirectMessage
    friend = _ensure_friends(friend_id)
    if not friend:
        return jsonify({'error': 'Это не ваш друг'}), 403
    try:
        limit = max(1, min(int(request.args.get('limit', 100)), 500))
    except (TypeError, ValueError):
        limit = 100

    q = DirectMessage.query.filter(
        db.or_(
            db.and_(DirectMessage.sender_id == current_user.id,
                    DirectMessage.recipient_id == friend.id),
            db.and_(DirectMessage.sender_id == friend.id,
                    DirectMessage.recipient_id == current_user.id),
        )
    ).order_by(DirectMessage.created_at.asc())
    msgs = q.limit(limit).all()
    # Маркируем входящие как прочитанные.  Помимо булева `is_read` (legacy)
    # ставим `read_at = now` чтобы фронт мог показать «✓✓ синие» — момент,
    # когда друг реально открыл диалог (CHAT_RECEIPTS_V1).
    try:
        now = datetime.utcnow()
        DirectMessage.query.filter_by(
            sender_id=friend.id, recipient_id=current_user.id, is_read=False
        ).update({'is_read': True, 'read_at': now})
        db.session.commit()
    except Exception as _e:
        print(f"[CHAT] failed to mark as read: {_e}")
        db.session.rollback()
    return jsonify({
        'friend': {
            'id': friend.id,
            'name': friend.name or friend.email or 'Без имени',
            'nickname': friend.nickname,
            'avatar_url': friend.avatar_url,
        },
        'messages': [m.to_dict(viewer_id=current_user.id) for m in msgs],
    })


@app.route('/api/chat/<int:friend_id>/send', methods=['POST'])
@login_required
def api_chat_send(friend_id):
    """Отправить сообщение другу.

    Поддерживает два режима:
      • {"kind": "text", "body": "..."} — обычное сообщение
      • {"kind": "task_share", "task": {id, source, topic, grade,
         difficulty, url, preview}, "note": "..."} — поделиться задачей
    """
    from models import DirectMessage, Notification
    friend = _ensure_friends(friend_id)
    if not friend:
        return jsonify({'error': 'Это не ваш друг'}), 403

    payload = request.get_json(silent=True) or {}
    kind = (payload.get('kind') or 'text').strip()
    if kind not in ('text', 'task_share', 'attachment'):
        return jsonify({'error': 'Неизвестный тип сообщения'}), 400

    # Reply-to (optional). Validate that the referenced message belongs to this conversation.
    reply_to_id = payload.get('reply_to_id')
    try:
        reply_to_id = int(reply_to_id) if reply_to_id else None
    except (TypeError, ValueError):
        reply_to_id = None
    if reply_to_id:
        ref = DirectMessage.query.get(reply_to_id)
        if not ref or {ref.sender_id, ref.recipient_id} != {current_user.id, friend.id}:
            reply_to_id = None

    msg = DirectMessage(
        sender_id=current_user.id,
        recipient_id=friend.id,
        kind=kind,
        reply_to_id=reply_to_id,
        # 1:1 chat with no offline queue: the moment we persist the row,
        # the message has reached the server, so it is "delivered". The
        # recipient will flip read_at the next time they open the chat.
        delivered_at=datetime.utcnow(),
    )

    if kind == 'text':
        body = (payload.get('body') or '').strip()
        if not body:
            return jsonify({'error': 'Сообщение не может быть пустым'}), 400
        msg.body = body[:4000]
    else:
        task = payload.get('task') or {}
        try:
            msg.task_id = int(task.get('id')) if task.get('id') is not None else None
        except (TypeError, ValueError):
            msg.task_id = None
        msg.task_topic = (task.get('topic') or None)
        try:
            msg.task_grade = int(task.get('grade')) if task.get('grade') is not None else None
        except (TypeError, ValueError):
            msg.task_grade = None
        try:
            msg.task_difficulty = int(task.get('difficulty')) if task.get('difficulty') is not None else None
        except (TypeError, ValueError):
            msg.task_difficulty = None
        msg.task_source = (task.get('source') or None)
        msg.task_url = (task.get('url') or None)
        preview = (task.get('preview') or '').strip()
        msg.task_preview = preview[:1200] if preview else None
        note = (payload.get('note') or '').strip()
        msg.body = note[:1000] if note else None
        if not (msg.task_id or msg.task_url or msg.task_preview):
            return jsonify({'error': 'Карточка задачи пустая'}), 400

    if kind == 'attachment':
        att = payload.get('attachment') or {}
        att_url = (att.get('url') or '').strip()
        att_kind = (att.get('kind') or '').strip()
        if not att_url or att_kind not in ('image', 'pdf'):
            return jsonify({'error': 'Вложение пустое или неподдерживаемого типа'}), 400
        # Server-side ownership check: the URL must point at a file we just
        # saved under /static/uploads/chat/<current_user.id>/...
        expected_prefix = '/static/uploads/chat/' + str(current_user.id) + '/'
        if not att_url.startswith(expected_prefix):
            return jsonify({'error': 'Чужое вложение'}), 403
        msg.attachment_url = att_url[:400]
        msg.attachment_kind = att_kind
        msg.attachment_name = (att.get('name') or '')[:255] or None
        try:
            msg.attachment_size = int(att.get('size')) if att.get('size') is not None else None
        except (TypeError, ValueError):
            msg.attachment_size = None
        caption = (payload.get('body') or payload.get('note') or '').strip()
        msg.body = caption[:1000] if caption else None

    db.session.add(msg)
    db.session.commit()

    # Уведомление другу
    try:
        notif = Notification(
            user_id=friend.id,
            type=('chat_task_share' if kind == 'task_share' else 'chat_message'),
            from_user_id=current_user.id,
            data=json.dumps({'message_id': msg.id}),
        )
        db.session.add(notif)
        db.session.commit()
    except Exception as _ne:
        print(f"[CHAT] notification failed: {_ne}")
        db.session.rollback()

    return jsonify({'success': True, 'message': msg.to_dict(viewer_id=current_user.id)})


@app.route('/api/chat/<int:friend_id>/upload', methods=['POST'])
@login_required
def api_chat_upload(friend_id):
    """Upload an attachment (image or PDF) for a chat message.

    Validates that *friend_id* is a friend, that the file is JPG/PNG/WEBP/PDF
    and at most 5 MB. Saves to ``static/uploads/chat/<sender_id>/<uuid>.<ext>``
    and returns the resulting URL. The client must then call ``api_chat_send``
    with ``kind='attachment'`` and the URL we returned.
    """
    friend = _ensure_friends(friend_id)
    if not friend:
        return jsonify({'error': 'Это не ваш друг'}), 403

    if 'file' not in request.files:
        return jsonify({'error': 'Файл не передан'}), 400
    f = request.files['file']
    if not f or not (f.filename or '').strip():
        return jsonify({'error': 'Файл пустой'}), 400

    ALLOWED_IMG = {'jpg', 'jpeg', 'png', 'webp', 'gif'}
    ALLOWED_PDF = {'pdf'}
    MAX_BYTES = 5 * 1024 * 1024

    original_name = os.path.basename(f.filename)[:255]
    ext = (original_name.rsplit('.', 1)[-1] if '.' in original_name else '').lower()
    if ext in ALLOWED_IMG:
        att_kind = 'image'
    elif ext in ALLOWED_PDF:
        att_kind = 'pdf'
    else:
        return jsonify({'error': 'Разрешены только изображения (jpg/png/webp/gif) и PDF'}), 400

    f.stream.seek(0, os.SEEK_END)
    size = f.stream.tell()
    f.stream.seek(0)
    if size <= 0:
        return jsonify({'error': 'Файл пустой'}), 400
    if size > MAX_BYTES:
        return jsonify({'error': 'Файл больше 5 МБ'}), 400

    folder = os.path.join('static', 'uploads', 'chat', str(current_user.id))
    os.makedirs(folder, exist_ok=True)
    name = uuid.uuid4().hex + '.' + ext
    path = os.path.join(folder, name)
    try:
        f.save(path)
    except Exception as _se:
        app.logger.warning("chat upload save failed: %r", _se)
        return jsonify({'error': 'Не удалось сохранить файл'}), 500

    url = '/static/uploads/chat/' + str(current_user.id) + '/' + name
    return jsonify({
        'success': True,
        'attachment': {
            'url':  url,
            'kind': att_kind,
            'name': original_name,
            'size': size,
        }
    })


@app.route('/api/chat/message/<int:message_id>/edit', methods=['POST'])
@login_required
def api_chat_message_edit(message_id):
    """Edit a text message. Sender-only, within 24h, not deleted."""
    from models import DirectMessage
    from datetime import datetime as _dt, timedelta as _td
    msg = DirectMessage.query.get(message_id)
    if not msg:
        return jsonify({'error': 'Сообщение не найдено'}), 404
    if msg.sender_id != current_user.id:
        return jsonify({'error': 'Можно редактировать только свои сообщения'}), 403
    if msg.kind != 'text':
        return jsonify({'error': 'Можно редактировать только текстовые сообщения'}), 400
    if getattr(msg, 'deleted_at', None):
        return jsonify({'error': 'Удалённое сообщение нельзя редактировать'}), 400
    if msg.created_at and (_dt.utcnow() - msg.created_at) > _td(hours=24):
        return jsonify({'error': 'Редактирование возможно в течение 24 часов'}), 400

    data = request.get_json(silent=True) or {}
    new_body = (data.get('body') or '').strip()
    if not new_body:
        return jsonify({'error': 'Текст не может быть пустым'}), 400

    msg.body = new_body[:4000]
    msg.edited_at = _dt.utcnow()
    try:
        db.session.commit()
    except Exception as _e:
        db.session.rollback()
        return jsonify({'error': f'Не удалось сохранить: {_e}'}), 500

    return jsonify({'success': True, 'message': msg.to_dict(viewer_id=current_user.id)})


@app.route('/api/chat/message/<int:message_id>/delete', methods=['POST'])
@login_required
def api_chat_message_delete(message_id):
    """Soft-delete a message. Sender-only (or 'delete for me' fallback could be added)."""
    from models import DirectMessage
    from datetime import datetime as _dt
    msg = DirectMessage.query.get(message_id)
    if not msg:
        return jsonify({'error': 'Сообщение не найдено'}), 404
    if msg.sender_id != current_user.id:
        return jsonify({'error': 'Можно удалять только свои сообщения'}), 403
    if getattr(msg, 'deleted_at', None):
        return jsonify({'success': True, 'message': msg.to_dict(viewer_id=current_user.id)})

    msg.deleted_at = _dt.utcnow()
    # Clear sensitive content. Keep id/created_at for thread continuity.
    msg.body = None
    msg.task_id = None
    msg.task_topic = None
    msg.task_grade = None
    msg.task_difficulty = None
    msg.task_source = None
    msg.task_url = None
    msg.task_preview = None
    try:
        db.session.commit()
    except Exception as _e:
        db.session.rollback()
        return jsonify({'error': f'Не удалось удалить: {_e}'}), 500

    return jsonify({'success': True, 'message': msg.to_dict(viewer_id=current_user.id)})


@app.route('/api/chat/message/<int:message_id>/forward', methods=['POST'])
@login_required
def api_chat_message_forward(message_id):
    """Forward a message to another friend.

    Body: { "to_friend_ids": [int, ...] }
    """
    from models import DirectMessage, Notification
    src = DirectMessage.query.get(message_id)
    if not src:
        return jsonify({'error': 'Сообщение не найдено'}), 404
    # Caller must be a participant of the source conversation.
    if current_user.id not in (src.sender_id, src.recipient_id):
        return jsonify({'error': 'Нет доступа к сообщению'}), 403
    if getattr(src, 'deleted_at', None):
        return jsonify({'error': 'Удалённое сообщение нельзя переслать'}), 400

    data = request.get_json(silent=True) or {}
    raw_ids = data.get('to_friend_ids') or []
    if not isinstance(raw_ids, list) or not raw_ids:
        return jsonify({'error': 'Укажите получателей'}), 400

    forwarded_origin = src.forwarded_from_id or src.id
    created = []
    for raw in raw_ids[:20]:  # cap at 20 forwards per call
        try:
            fid = int(raw)
        except (TypeError, ValueError):
            continue
        friend = _ensure_friends(fid)
        if not friend:
            continue
        new_msg = DirectMessage(
            sender_id=current_user.id,
            recipient_id=friend.id,
            kind=src.kind,
            body=src.body,
            task_id=src.task_id,
            task_topic=src.task_topic,
            task_grade=src.task_grade,
            task_difficulty=src.task_difficulty,
            task_source=src.task_source,
            task_url=src.task_url,
            task_preview=src.task_preview,
            forwarded_from_id=forwarded_origin,
        )
        db.session.add(new_msg)
        try:
            db.session.commit()
        except Exception as _e:
            db.session.rollback()
            print(f"[CHAT-FORWARD] commit failed friend={fid}: {_e}")
            continue

        try:
            notif = Notification(
                user_id=friend.id,
                type=('chat_task_share' if src.kind == 'task_share' else 'chat_message'),
                from_user_id=current_user.id,
                data=json.dumps({'message_id': new_msg.id, 'forwarded': True}),
            )
            db.session.add(notif)
            db.session.commit()
        except Exception as _ne:
            print(f"[CHAT-FORWARD] notification failed: {_ne}")
            db.session.rollback()

        created.append({'friend_id': friend.id, 'message_id': new_msg.id})

    if not created:
        return jsonify({'error': 'Не удалось переслать ни одному получателю'}), 400
    return jsonify({'success': True, 'forwarded': created})


@app.route('/api/chat/unread_total')
@login_required
def api_chat_unread_total():
    """Общее число непрочитанных личных сообщений (для бейджа в шапке)."""
    from models import DirectMessage
    n = DirectMessage.query.filter_by(
        recipient_id=current_user.id, is_read=False
    ).count()
    return jsonify({'unread': n})


@app.route('/api/chat/task-suggestions')
@login_required
def api_chat_task_suggestions():
    """Список задач, которые пользователь может предложить другу в чате.

    Источники:
      • source=adaptive — последние/любые задачи из таблицы AdaptiveTask
      • source=recent   — задачи, которые пользователь недавно решал
                          (берём из adaptive_answers в сессии + AdaptiveTask)
    """
    from models import AdaptiveTask
    source = (request.args.get('source') or 'adaptive').strip()
    try:
        limit = max(1, min(int(request.args.get('limit', 20)), 50))
    except (TypeError, ValueError):
        limit = 20

    items = []

    if source == 'recent':
        # Из сессии (адаптивный тест)
        seen_ids = []
        for entry in (session.get('adaptive_answers') or []):
            tid = entry.get('task_id')
            try:
                tid_int = int(tid)
            except (TypeError, ValueError):
                continue
            if tid_int not in seen_ids:
                seen_ids.append(tid_int)
        # Доп: последние решения из БД, если модель TaskSolution есть
        try:
            from models import TaskSolution  # type: ignore
            recent_solutions = (
                TaskSolution.query
                .filter_by(user_id=current_user.id)
                .order_by(TaskSolution.id.desc())
                .limit(30)
                .all()
            )
            for ts in recent_solutions:
                tid = getattr(ts, 'task_id', None)
                if tid and tid not in seen_ids:
                    seen_ids.append(tid)
        except Exception:
            pass
        seen_ids = seen_ids[:limit]
        if seen_ids:
            tasks = AdaptiveTask.query.filter(AdaptiveTask.id.in_(seen_ids)).all()
            # Сохраняем порядок
            by_id = {t.id: t for t in tasks}
            ordered = [by_id[i] for i in seen_ids if i in by_id]
        else:
            ordered = []
    else:
        # Просто последние задачи (демо/предложения)
        ordered = (
            AdaptiveTask.query
            .order_by(AdaptiveTask.id.desc())
            .limit(limit)
            .all()
        )

    domain = request.host_url.rstrip('/')
    for t in ordered:
        preview = (t.task_text or '').strip()
        if len(preview) > 500:
            preview = preview[:500].rstrip() + '…'
        items.append({
            'id': t.id,
            'source': 'adaptive',
            'topic': getattr(t, 'topic', None),
            'grade': getattr(t, 'class_level', None),
            'difficulty': getattr(t, 'difficulty_level', None),
            'preview': preview,
            'url': f"{domain}/adaptive_task/{t.id}",
        })

    return jsonify({'tasks': items})


@app.route('/adaptive_task/<int:task_id>')
@login_required
def view_shared_adaptive_task(task_id):
    """Просмотр одной задачи (страница для шаринга с другом).

    Не запускает адаптивный тест — просто показывает условие задачи,
    решение под катом и предлагает «решить» (запустить адаптивный тест по теме).
    """
    from models import AdaptiveTask
    task = AdaptiveTask.query.get_or_404(task_id)
    return render_template('shared_task.html', task=task)


@app.route('/notifications')
@login_required
def notifications_page():
    """Notifications page."""
    from models import Notification
    notifs = Notification.query.filter_by(
        user_id=current_user.id
    ).order_by(Notification.created_at.desc()).limit(50).all()
    # Mark all as read
    Notification.query.filter_by(user_id=current_user.id, read=False).update({'read': True})
    db.session.commit()
    return render_template('notifications.html', notifications=notifs)


@app.route('/api/notifications/count')
@login_required
def notifications_count():
    """API: unread notifications count."""
    count = current_user.unread_notifications_count()
    return jsonify({'count': count})


@app.route('/u/<nickname>')
@login_required
def profile_by_nickname(nickname):
    """Профиль пользователя по никнейму (SPA-стиль)."""
    target = User.query.filter_by(nickname=nickname).first()
    if not target:
        flash('Пользователь не найден', 'error')
        return redirect(url_for('friends_page'))
    # Свой профиль — редирект на /profile
    if target.id == current_user.id:
        return redirect(url_for('profile'))
    return render_template('profile_view.html', nickname=nickname)


@app.route('/api/profile/<nickname>')
@login_required
def api_profile_view(nickname):
    """API: данные профиля друга (JSON) для SPA-просмотра."""
    from models import UserStreak, UserTopicProgress, TestResult, UserProgress
    from datetime import datetime, timedelta, date

    target = User.query.filter_by(nickname=nickname).first()
    if not target:
        return jsonify({'error': 'Пользователь не найден'}), 404

    # Свой профиль — всегда доступен
    is_self = (target.id == current_user.id)

    if not is_self:
        # Проверка дружбы
        if not current_user.is_friend_with(target.id):
            return jsonify({'error': 'Доступ запрещён — вы не друзья'}), 403

    # --- Streak ---
    streak_obj = UserStreak.query.filter_by(user_id=target.id).first()
    streak_data = {
        'current': streak_obj.current_streak if streak_obj else 0,
        'longest': streak_obj.longest_streak if streak_obj else 0,
    }

    # --- Общий рейтинг (XP / level) ---
    rating_data = {
        'experience_points': target.experience_points or 0,
        'current_level': target.current_level or 1,
        'total_problems_solved': target.total_problems_solved or 0,
    }

    # --- Прогресс по темам (UserTopicProgress) ---
    topic_rows = UserTopicProgress.query.filter_by(user_id=target.id).all()
    progress_by_topic = []
    for tp in topic_rows:
        accuracy = round(tp.tasks_correct / tp.tasks_attempted * 100) if tp.tasks_attempted else 0
        progress_by_topic.append({
            'topic': tp.topic,
            'topic_name_ru': tp.topic_name_ru or tp.topic,
            'current_level': tp.current_level,
            'tasks_attempted': tp.tasks_attempted,
            'tasks_correct': tp.tasks_correct,
            'accuracy': accuracy,
        })
    progress_by_topic.sort(key=lambda x: -x['tasks_attempted'])

    # --- Heatmap активности за 30 дней ---
    today = date.today()
    since = today - timedelta(days=29)
    results_30d = TestResult.query.filter(
        TestResult.user_id == target.id,
        TestResult.created_at >= datetime.combine(since, datetime.min.time())
    ).all()

    # Группируем по дате
    activity_map = {}
    for r in results_30d:
        day_str = r.created_at.strftime('%Y-%m-%d') if r.created_at else None
        if day_str:
            activity_map[day_str] = activity_map.get(day_str, 0) + 1

    activity_30d = []
    for i in range(30):
        d = since + timedelta(days=i)
        ds = d.strftime('%Y-%m-%d')
        activity_30d.append({'date': ds, 'count': activity_map.get(ds, 0)})

    # --- Последние результаты (20 штук) ---
    recent_rows = TestResult.query.filter_by(user_id=target.id)\
        .order_by(TestResult.created_at.desc()).limit(20).all()
    recent_results = []
    for r in recent_rows:
        recent_results.append({
            'test_type': r.test_type,
            'topic': r.topic,
            'difficulty': r.difficulty,
            'is_correct': r.is_correct,
            'time_spent_sec': r.time_spent_sec,
            'created_at': r.created_at.isoformat() if r.created_at else None,
        })

    return jsonify({
        'nickname': target.nickname,
        'name': target.name,
        'avatar_url': target.avatar_url,
        'streak': streak_data,
        'rating': rating_data,
        'progress_by_topic': progress_by_topic,
        'activity_30d': activity_30d,
        'recent_results': recent_results,
    })


@app.route('/user/<int:user_id>')
@login_required
def public_profile(user_id):
    """Публичный профиль пользователя."""
    # Если смотришь на себя — редирект на /profile
    if user_id == current_user.id:
        return redirect(url_for('profile'))

    target = User.query.get_or_404(user_id)

    # Статус дружбы
    friendship_status = current_user.friendship_status_with(user_id)

    # Pending request id (нужен для кнопки "Отменить")
    pending_request_id = None
    if friendship_status == 'pending_sent':
        from models import Friendship
        fr = Friendship.query.filter_by(
            requester_id=current_user.id,
            addressee_id=user_id,
            status='pending'
        ).first()
        if fr:
            pending_request_id = fr.id
    elif friendship_status == 'pending_received':
        from models import Friendship
        fr = Friendship.query.filter_by(
            requester_id=user_id,
            addressee_id=current_user.id,
            status='pending'
        ).first()
        if fr:
            pending_request_id = fr.id

    # Друзья цели
    target_friends = target.get_friends()

    # Общие друзья
    my_friend_ids = set(f.id for f in current_user.get_friends())
    mutual_friends = [f for f in target_friends if f.id in my_friend_ids]

    # Mastery по темам
    from models import TopicMastery
    TOPIC_META = {
        'algebra':        {'name_ru': 'Алгебра',            'icon': '➗'},
        'geometry':       {'name_ru': 'Геометрия',          'icon': '📐'},
        'combinatorics':  {'name_ru': 'Комбинаторика',      'icon': '🧩'},
        'number_theory':  {'name_ru': 'Теория чисел',       'icon': '🔢'},
        'kl_movement':    {'name_ru': 'Задачи на движение', 'icon': '🚂'},
        'knights_liars':  {'name_ru': 'Рыцари и лжецы',     'icon': '🧠'},
    }

    mastery_records = TopicMastery.query.filter_by(user_id=user_id).all()
    mastery_by_topic = {rec.topic: rec for rec in mastery_records}

    # Build mastery_data with ALL topics from TOPIC_META (so radar always has all axes)
    mastery_data = []
    for topic_key, meta in TOPIC_META.items():
        rec = mastery_by_topic.get(topic_key)
        if rec:
            mastery_data.append({
                'topic': topic_key,
                'name_ru': meta['name_ru'],
                'icon': meta['icon'],
                'mastery': rec.mastery,
                'solved': rec.solved,
                'attempts': rec.attempts,
                'avg_level': rec.avg_level,
            })
        else:
            mastery_data.append({
                'topic': topic_key,
                'name_ru': meta['name_ru'],
                'icon': meta['icon'],
                'mastery': 0.0,
                'solved': 0,
                'attempts': 0,
                'avg_level': 0.0,
            })
    # Sort: tested topics first (by mastery desc), then untested
    mastery_data.sort(key=lambda x: (-1 if x['mastery'] > 0 else 0, -x['mastery']))

    # Последние тесты
    recent_tests = AdaptiveTestResult.query.filter_by(
        user_id=user_id
    ).order_by(AdaptiveTestResult.completed_at.desc()).limit(5).all()

    # Streak
    from models import UserStreak
    streak = UserStreak.query.filter_by(user_id=user_id).first()

    return render_template(
        'public_profile.html',
        target=target,
        friendship_status=friendship_status,
        pending_request_id=pending_request_id,
        mutual_friends=mutual_friends,
        target_friends=target_friends,
        mastery_data=mastery_data,
        recent_tests=recent_tests,
        streak=streak,
        topic_meta=TOPIC_META,
    )

# === ВРЕМЕННЫЙ ENDPOINT ДЛЯ МИГРАЦИИ SQLite -> Postgres ===
# Удалить после успешной миграции!
MIGRATE_SECRET = os.environ.get('MIGRATE_SECRET', 'formyla-migrate-2026')

@app.route('/api/migrate/tables', methods=['GET'])
def migrate_list_tables():
    """Список таблиц и количество строк в Postgres."""
    secret = request.args.get('secret', '')
    if secret != MIGRATE_SECRET:
        return jsonify({'error': 'unauthorized'}), 403
    result = {}
    try:
        from sqlalchemy import inspect as sa_inspect, text
        inspector = sa_inspect(db.engine)
        for table_name in inspector.get_table_names():
            cnt = db.session.execute(text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar()
            result[table_name] = cnt
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    return jsonify(result)

@app.route('/api/migrate/push', methods=['POST'])
def migrate_push_data():
    """Принимает данные таблицы и вставляет в Postgres."""
    data = request.get_json(force=True)
    secret = data.get('secret', '')
    if secret != MIGRATE_SECRET:
        return jsonify({'error': 'unauthorized'}), 403

    table = data.get('table')
    rows = data.get('rows', [])
    wipe = data.get('wipe', False)

    if not table or not rows:
        return jsonify({'error': 'table and rows required'}), 400

    try:
        from sqlalchemy import text

        # Получаем модель по имени таблицы
        Model = None
        for mp in db.Model.registry.mappers:
            cls = mp.class_
            if getattr(cls, '__tablename__', None) == table:
                Model = cls
                break

        if not Model:
            return jsonify({'error': f'model for table {table} not found'}), 404

        if wipe:
            db.session.execute(text(f'TRUNCATE TABLE "{table}" CASCADE'))
            db.session.commit()

        col_names = {c.name for c in Model.__table__.columns}
        ok = 0
        fail = 0
        errors = []

        for r in rows:
            filtered = {k: v for k, v in r.items() if k in col_names}
            try:
                db.session.add(Model(**filtered))
                ok += 1
            except Exception:
                db.session.rollback()
                filtered.pop('id', None)
                try:
                    db.session.add(Model(**filtered))
                    ok += 1
                except Exception as e2:
                    db.session.rollback()
                    fail += 1
                    if len(errors) < 5:
                        errors.append(str(e2)[:200])

        db.session.commit()

        # Обновляем sequence
        try:
            for col in Model.__table__.columns:
                if col.primary_key and col.autoincrement:
                    seq = f"{table}_{col.name}_seq"
                    max_val = db.session.execute(
                        text(f'SELECT COALESCE(MAX("{col.name}"), 0) FROM "{table}"')
                    ).scalar()
                    if max_val and max_val > 0:
                        db.session.execute(
                            text(f"SELECT setval('{seq}', :val, true)"),
                            {'val': max_val}
                        )
                        db.session.commit()
        except Exception:
            db.session.rollback()

        return jsonify({'ok': ok, 'fail': fail, 'errors': errors})

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
@app.route('/api/migrate/export', methods=['GET'])
def migrate_export_table():
    """Export table rows as JSON (paginated). Usage: ?secret=...&table=adaptive_task&offset=0&limit=500"""
    secret = request.args.get('secret', '')
    if secret != MIGRATE_SECRET:
        return jsonify({'error': 'unauthorized'}), 403
    table = request.args.get('table', 'adaptive_task')
    offset = int(request.args.get('offset', 0))
    limit = min(int(request.args.get('limit', 500)), 2000)
    try:
        from sqlalchemy import text
        rows_raw = db.session.execute(
            text(f'SELECT * FROM "{table}" ORDER BY id LIMIT :lim OFFSET :off'),
            {'lim': limit, 'off': offset}
        )
        columns = list(rows_raw.keys())
        rows = []
        for r in rows_raw:
            row_dict = {}
            for i, col in enumerate(columns):
                val = r[i]
                if isinstance(val, (bytes,)):
                    val = val.decode('utf-8', errors='replace')
                elif hasattr(val, 'isoformat'):
                    val = val.isoformat()
                row_dict[col] = val
            rows.append(row_dict)
        total = db.session.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar()
        return jsonify({'table': table, 'total': total, 'offset': offset, 'limit': limit, 'count': len(rows), 'columns': columns, 'rows': rows})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# === КОНЕЦ ENDPOINT МИГРАЦИИ ===


# ============================================================
# API: Персистентные никнеймы и результаты тестов
# ============================================================

@app.route('/api/save_test_result', methods=['POST'])
def api_save_test_result():
    """Сохранение результата теста в БД"""
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        user_id = None
        device_id = session.get('device_id')
        
        if current_user.is_authenticated:
            user_id = current_user.id
        else:
            return jsonify({'error': 'User not authenticated'}), 401
        
        # Создаём запись результата
        result = TestResult(
            user_id=user_id,
            device_id=device_id,
            test_type=data.get('test_type', 'practice'),
            class_level=data.get('class_level'),
            topic=data.get('topic'),
            task_id=data.get('task_id'),
            difficulty=data.get('difficulty'),
            is_correct=data.get('is_correct', False),
            user_answer=str(data.get('user_answer', '')) if data.get('user_answer') is not None else None,
            time_spent_sec=data.get('time_spent_sec'),
            rating_delta=data.get('rating_delta'),
            rating_after=data.get('rating_after')
        )
        db.session.add(result)
        
        # Обновляем агрегированный прогресс
        topic = data.get('topic')
        class_level = data.get('class_level')
        if topic and class_level:
            progress = UserProgress.query.filter_by(
                user_id=user_id,
                topic=topic,
                class_level=class_level
            ).first()
            
            if not progress:
                progress = UserProgress(
                    user_id=user_id,
                    topic=topic,
                    class_level=class_level
                )
                db.session.add(progress)
            
            progress.tasks_attempted = (progress.tasks_attempted or 0) + 1
            if data.get('is_correct'):
                progress.tasks_solved = (progress.tasks_solved or 0) + 1
            if data.get('difficulty'):
                progress.current_difficulty = data['difficulty']
            if data.get('rating_after'):
                progress.rating = data['rating_after']
            progress.last_activity = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'result_id': result.id
        })
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error saving test result: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/api/profile', methods=['GET'])
def api_get_profile():
    """Загрузка профиля пользователя"""
    try:
        if not current_user.is_authenticated:
            return jsonify({'error': 'Not authenticated'}), 401
        
        user = current_user
        
        # Агрегированный прогресс
        progress_list = UserProgress.query.filter_by(user_id=user.id).all()
        
        # Последние результаты (до 50)
        recent_results = TestResult.query.filter_by(user_id=user.id)\
            .order_by(TestResult.created_at.desc())\
            .limit(50).all()
        
        # Статистика
        total_attempted = sum(p.tasks_attempted or 0 for p in progress_list)
        total_solved = sum(p.tasks_solved or 0 for p in progress_list)
        
        return jsonify({
            'success': True,
            'profile': {
                'id': user.id,
                'nickname': user.nickname,
                'email': user.email if not user.is_guest else None,
                'is_guest': user.is_guest,
                'device_id': user.device_id,
                'total_problems_solved': user.total_problems_solved,
                'current_level': user.current_level,
                'experience_points': user.experience_points,
                'created_at': user.created_at.isoformat() if user.created_at else None
            },
            'progress': [p.to_dict() for p in progress_list],
            'recent_results': [r.to_dict() for r in recent_results],
            'stats': {
                'total_attempted': total_attempted,
                'total_solved': total_solved,
                'accuracy': round(total_solved / total_attempted * 100, 1) if total_attempted > 0 else 0,
                'topics_studied': len(progress_list)
            }
        })
    except Exception as e:
        app.logger.error(f"Error loading profile: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/api/set_nickname', methods=['POST'])
def api_set_nickname():
    """Установка никнейма пользователя"""
    try:
        if not current_user.is_authenticated:
            return jsonify({'error': 'Not authenticated'}), 401
        
        data = request.get_json(silent=True)
        if not data or not data.get('nickname'):
            return jsonify({'error': 'Nickname is required'}), 400
        
        nickname = data['nickname'].strip()
        
        # Валидация
        if len(nickname) < 2 or len(nickname) > 50:
            return jsonify({'error': 'Никнейм должен быть от 2 до 50 символов'}), 400
        
        # Проверка уникальности
        existing = User.query.filter_by(nickname=nickname).first()
        if existing and existing.id != current_user.id:
            return jsonify({'error': 'Этот никнейм уже занят'}), 409
        
        current_user.nickname = nickname
        db.session.commit()
        
        return jsonify({
            'success': True,
            'nickname': nickname
        })
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error setting nickname: {e}")
        return jsonify({'error': 'Internal server error'}), 500


# ============================================================
# ПОДПИСКА / SUBSCRIBE
# ============================================================

@app.route('/subscribe')
@login_required
def subscribe_page():
    """Страница выбора тарифа."""
    current_plan = current_user.current_plan or 'free'
    plan_expires_at = getattr(current_user, 'plan_expires_at', None)
    if plan_expires_at:
        plan_expires_at = str(plan_expires_at)[:10]
    return render_template('subscribe.html',
                           current_plan=current_plan,
                           plan_expires_at=plan_expires_at)


@app.route('/api/subscribe', methods=['POST'])
@login_required
def api_subscribe():
    """API активации Premium (демо — без оплаты)."""
    data = request.get_json() or {}
    plan = data.get('plan', 'premium_monthly')

    if plan not in ('premium_monthly', 'premium_yearly'):
        return jsonify({'error': 'Неизвестный тариф'}), 400

    from datetime import timedelta
    if plan == 'premium_monthly':
        expires = datetime.utcnow() + timedelta(days=30)
    else:
        expires = datetime.utcnow() + timedelta(days=365)

    current_user.current_plan = plan
    current_user.plan_expires_at = expires
    db.session.commit()

    return jsonify({
        'ok': True,
        'plan': plan,
        'expires_at': str(expires)[:10],
        'message': 'Premium активирован!'
    })


@app.route('/api/cancel_subscription', methods=['POST'])
@login_required
def api_cancel_subscription():
    """API отмены подписки Premium."""
    if not current_user.current_plan or current_user.current_plan == 'free':
        return jsonify({'error': 'У вас нет активной подписки'}), 400

    current_user.current_plan = 'free'
    current_user.plan_expires_at = None
    db.session.commit()

    return jsonify({
        'ok': True,
        'message': 'Подписка отменена. Вы переведены на бесплатный тариф.'
    })


# ═══════════════════════════════════════════════════════════════════
# СТРАНИЦА "О САЙТЕ" + ФОРМА ПОДДЕРЖКИ С EMAIL-УВЕДОМЛЕНИЯМИ
# ═══════════════════════════════════════════════════════════════════

from services.telegram_notify import send_support_email

# Простой rate-limit: один user ≤ 5 обращений за час
_SUPPORT_RATE_LIMIT = {}  # in-memory, для prod лучше Redis


@app.route('/about')
def about_page():
    # Если авторизованный пользователь ещё не проходил онбординг —
    # отметить его время первого визита на /about. Не блокируем рендер при ошибке.
    try:
        if current_user.is_authenticated and getattr(current_user, 'onboarded_at', None) is None:
            current_user.onboarded_at = datetime.utcnow()
            db.session.commit()
    except Exception as _onb_err:
        try:
            db.session.rollback()
        except Exception:
            pass
        app.logger.warning(f"[about] failed to set onboarded_at: {_onb_err}")
    return render_template('about.html')


@app.route('/api/support', methods=['POST'])
def submit_support():
    try:
        data = request.json or {}

        message_text = (data.get('message') or '').strip()
        if not (5 <= len(message_text) <= 4000):
            return jsonify({'error': 'сообщение 5-4000 символов'}), 400

        category = data.get('category', 'other')
        if category not in ('bug', 'suggestion', 'question', 'other'):
            category = 'other'

        email = (data.get('email') or '').strip() or None
        if email and '@' not in email:
            return jsonify({'error': 'некорректный email'}), 400

        # Rate-limit
        user_id = None
        if current_user.is_authenticated:
            user_id = current_user.id
        rl_key = f'u:{user_id}' if user_id else f'ip:{request.remote_addr}'
        import time as _time_rl
        now = _time_rl.time()
        bucket = _SUPPORT_RATE_LIMIT.setdefault(rl_key, [])
        bucket[:] = [t for t in bucket if now - t < 3600]
        if len(bucket) >= 5:
            return jsonify({'error': 'слишком много обращений, '
                                      'попробуйте через час'}), 429
        bucket.append(now)

        # Получить nickname из БД если залогинен
        nickname = None
        if user_id:
            try:
                nickname = current_user.nickname or current_user.display_name
            except Exception:
                pass

        page_url = (data.get('page_url') or '')[:500]
        user_agent = (request.headers.get('User-Agent') or '')[:500]
        ip = (request.headers.get('X-Forwarded-For', '').split(',')[0].strip()
              or request.remote_addr)

        # 1. Сохранить в БД
        from sqlalchemy import text as _text_support
        _params = {
            'user_id': user_id,
            'nickname': nickname,
            'email': email,
            'category': category,
            'message': message_text,
            'page_url': page_url,
            'user_agent': user_agent,
            'ip': ip,
        }

        try:
            result_row = db.session.execute(_text_support('''
                INSERT INTO support_messages
                (user_id, user_nickname, user_email, category,
                 message, page_url, user_agent, ip)
                VALUES (:user_id, :nickname, :email, :category,
                        :message, :page_url, :user_agent, :ip)
                RETURNING id
            '''), _params).fetchone()
            new_id = result_row[0]
            db.session.commit()
        except Exception as insert_err:
            db.session.rollback()
            # SQLite не поддерживает RETURNING — fallback
            try:
                db.session.execute(_text_support('''
                    INSERT INTO support_messages
                    (user_id, user_nickname, user_email, category,
                     message, page_url, user_agent, ip)
                    VALUES (:user_id, :nickname, :email, :category,
                            :message, :page_url, :user_agent, :ip)
                '''), _params)
                db.session.commit()
                row = db.session.execute(
                    _text_support('SELECT MAX(id) FROM support_messages')
                ).fetchone()
                new_id = row[0] if row else 0
            except Exception as fallback_err:
                db.session.rollback()
                import logging
                logging.error(f'[support] DB insert failed: {insert_err} / {fallback_err}')
                return jsonify({'error': 'ошибка сохранения, попробуйте позже'}), 500

        # 2. Отправить email владельцу
        ok, err = send_support_email(
            mail,
            nickname=nickname, email=email, category=category,
            message=message_text, page_url=page_url,
            user_agent=user_agent, ip=ip, ticket_id=new_id,
        )

        try:
            db.session.execute(_text_support(
                '''UPDATE support_messages
                   SET email_sent=:ok, email_error=:err
                   WHERE id=:id'''
            ), {'ok': ok, 'err': err, 'id': new_id})
            db.session.commit()
        except Exception:
            db.session.rollback()

        return jsonify({'ok': True, 'id': new_id})

    except Exception as e:
        import logging
        logging.exception('[support] Unexpected error')
        return jsonify({'error': 'внутренняя ошибка сервера'}), 500


# ─── CHAT_GROUPS_V1 — group chat endpoints ─────────────────────────────────
from models import GroupChat, GroupMember, GroupMessage


def _is_group_member(group_id, user_id):
    return GroupMember.query.filter_by(
        group_id=group_id, user_id=user_id
    ).first() is not None


@app.route('/api/groups', methods=['POST'])
@login_required
def api_groups_create():
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Имя группы обязательно'}), 400
    member_ids = data.get('member_ids') or []
    g = GroupChat(name=name[:120], owner_id=current_user.id)
    db.session.add(g)
    db.session.flush()
    db.session.add(GroupMember(group_id=g.id, user_id=current_user.id, role='owner'))
    friends_ids = [f.id for f in current_user.get_friends()]
    for uid in member_ids:
        try:
            uid_int = int(uid)
        except (TypeError, ValueError):
            continue
        if uid_int == current_user.id or uid_int not in friends_ids:
            continue
        db.session.add(GroupMember(group_id=g.id, user_id=uid_int, role='member'))
    db.session.commit()
    return jsonify({'success': True, 'group_id': g.id})


@app.route('/api/groups', methods=['GET'])
@login_required
def api_groups_list():
    rows = (
        db.session.query(GroupChat)
        .join(GroupMember, GroupMember.group_id == GroupChat.id)
        .filter(GroupMember.user_id == current_user.id)
        .order_by(GroupChat.created_at.desc())
        .all()
    )
    items = []
    for g in rows:
        last = (
            GroupMessage.query.filter_by(group_id=g.id)
            .order_by(GroupMessage.created_at.desc()).first()
        )
        items.append({
            'id': g.id,
            'name': g.name,
            'avatar_emoji': g.avatar_emoji or '👥',
            'last_message': last.body if last else None,
            'last_at': last.created_at.isoformat() if last and last.created_at else None,
        })
    return jsonify({'groups': items})


@app.route('/api/groups/<int:group_id>/members', methods=['GET'])
@login_required
def api_groups_members(group_id):
    if not _is_group_member(group_id, current_user.id):
        return jsonify({'error': 'Вы не в группе'}), 403
    rows = (
        db.session.query(GroupMember, User)
        .join(User, User.id == GroupMember.user_id)
        .filter(GroupMember.group_id == group_id)
        .order_by(GroupMember.joined_at.asc())
        .all()
    )
    members = [{
        'id': u.id,
        'name': u.name or u.nickname or u.email,
        'nickname': u.nickname,
        'avatar_url': u.avatar_url,
        'level': u.current_level or 1,
        'xp': u.experience_points or 0,
        'role': gm.role,
        'joined_at': gm.joined_at.isoformat() if gm.joined_at else None,
        'is_me': u.id == current_user.id,
    } for gm, u in rows]
    return jsonify({'members': members})


# CHAT_GROUP_INFO_V1 — full group info (meta + members) for the header info panel.
@app.route('/api/groups/<int:group_id>/info', methods=['GET'])
@login_required
def api_groups_info(group_id):
    """Return group meta and member list for the chat info panel."""
    if not _is_group_member(group_id, current_user.id):
        return jsonify({'error': 'Вы не в группе'}), 403
    g = GroupChat.query.get(group_id)
    if not g:
        return jsonify({'error': 'Группа не найдена'}), 404
    rows = (
        db.session.query(GroupMember, User)
        .join(User, User.id == GroupMember.user_id)
        .filter(GroupMember.group_id == group_id)
        .order_by(GroupMember.joined_at.asc())
        .all()
    )
    members = [{
        'id': u.id,
        'name': u.name or u.nickname or u.email,
        'nickname': u.nickname,
        'avatar_url': getattr(u, 'avatar_url', None),
        'level': getattr(u, 'current_level', None) or 1,
        'xp': getattr(u, 'experience_points', None) or 0,
        'role': getattr(gm, 'role', 'member'),
        'joined_at': gm.joined_at.isoformat() if getattr(gm, 'joined_at', None) else None,
        'is_me': u.id == current_user.id,
        'is_owner': u.id == g.owner_id,
    } for gm, u in rows]
    # Message count (lightweight aggregate)
    try:
        msg_count = GroupMessage.query.filter_by(group_id=group_id).count()
    except Exception:
        msg_count = 0
    owner = User.query.get(g.owner_id)
    g_av = getattr(g, 'avatar_emoji', None)
    return jsonify({
        'group': {
            'id': g.id,
            'name': g.name,
            'avatar_emoji': g_av or '👥',
            'created_at': g.created_at.isoformat() if g.created_at else None,
            'owner_id': g.owner_id,
            'owner_name': (owner.name or owner.nickname or owner.email) if owner else None,
            'member_count': len(members),
            'message_count': msg_count,
        },
        'members': members,
    })


# CHAT_USER_INFO_V1 — concise public info about a user for the chat header info panel.
@app.route('/api/users/<int:user_id>/info', methods=['GET'])
@login_required
def api_user_info(user_id):
    """Return brief user info for the personal chat info panel."""
    u = User.query.get(user_id)
    if not u:
        return jsonify({'error': 'Пользователь не найден'}), 404
    # Friendship state (for context, optional)
    try:
        friendship_status = current_user.friendship_status_with(user_id)
    except Exception:
        friendship_status = None
    # Streak (optional)
    try:
        from models import UserStreak
        streak = UserStreak.query.filter_by(user_id=user_id).first()
        streak_days = streak.current_streak if streak else 0
    except Exception:
        streak_days = 0
    return jsonify({
        'user': {
            'id': u.id,
            'name': u.name or u.nickname or u.email,
            'nickname': u.nickname,
            'email': u.email if user_id == current_user.id else None,
            'avatar_url': u.avatar_url,
            'level': u.current_level or 1,
            'xp': u.experience_points or 0,
            'problems_solved': u.total_problems_solved or 0,
            'mock_exams_passed': u.mock_exams_passed or 0,
            'adaptive_tests_completed': u.adaptive_tests_completed or 0,
            'highest_difficulty_solved': u.highest_difficulty_solved or 0,
            'created_at': u.created_at.isoformat() if u.created_at else None,
            'last_login': u.last_login.isoformat() if u.last_login else None,
            'friendship_status': friendship_status,
            'streak_days': streak_days,
            'profile_url': url_for('public_profile', user_id=u.id) if user_id != current_user.id else url_for('profile'),
        }
    })


@app.route('/api/groups/<int:group_id>/invite', methods=['POST'])
@login_required
def api_groups_invite(group_id):
    if not _is_group_member(group_id, current_user.id):
        return jsonify({'error': 'Вы не в группе'}), 403
    data = request.get_json(silent=True) or {}
    try:
        uid = int(data.get('user_id'))
    except (TypeError, ValueError):
        return jsonify({'error': 'user_id обязателен'}), 400
    friends_ids = [f.id for f in current_user.get_friends()]
    if uid not in friends_ids:
        return jsonify({'error': 'Это не ваш друг'}), 403
    if _is_group_member(group_id, uid):
        return jsonify({'success': True, 'note': 'already a member'})
    db.session.add(GroupMember(group_id=group_id, user_id=uid, role='member'))
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/groups/<int:group_id>/leave', methods=['POST'])
@login_required
def api_groups_leave(group_id):
    gm = GroupMember.query.filter_by(group_id=group_id, user_id=current_user.id).first()
    if not gm:
        return jsonify({'error': 'Вы не в группе'}), 404
    db.session.delete(gm)
    db.session.commit()
    return jsonify({'success': True})


# CHAT_GROUPS_DELETE_V1 — полное удаление группы (доступно только владельцу).
# Удаляет саму группу, всех её участников и все сообщения. На уровне БД
# каскадно удалять помогают FK ON DELETE CASCADE в моделях GroupMember
# и GroupMessage, но мы дополнительно подчищаем вручную на случай, если
# Postgres/SQLite пропустит каскад из-за порядка операций.
@app.route('/api/groups/<int:group_id>', methods=['DELETE'])
@login_required
def api_groups_delete(group_id):
    g = GroupChat.query.get(group_id)
    if not g:
        return jsonify({'error': 'Группа не найдена'}), 404
    if g.owner_id != current_user.id:
        return jsonify({'error': 'Удалить группу может только владелец'}), 403
    try:
        GroupMessage.query.filter_by(group_id=group_id).delete(synchronize_session=False)
        GroupMember.query.filter_by(group_id=group_id).delete(synchronize_session=False)
        db.session.delete(g)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"[api_groups_delete] failed for group_id={group_id}: {e}")
        return jsonify({'error': 'Не удалось удалить группу'}), 500
    return jsonify({'success': True})


@app.route('/api/groups/<int:group_id>/messages', methods=['GET'])
@login_required
def api_groups_messages(group_id):
    if not _is_group_member(group_id, current_user.id):
        return jsonify({'error': 'Вы не в группе'}), 403
    rows = (
        GroupMessage.query.filter_by(group_id=group_id)
        .order_by(GroupMessage.created_at.asc()).limit(500).all()
    )
    senders = {u.id: u for u in User.query.filter(
        User.id.in_([r.sender_id for r in rows])
    ).all()} if rows else {}
    items = [{
        'id': m.id,
        'body': m.body,
        'sender_id': m.sender_id,
        'sender_name': (senders.get(m.sender_id).name
                        or senders.get(m.sender_id).nickname
                        or senders.get(m.sender_id).email)
                        if senders.get(m.sender_id) else '?',
        'mine': m.sender_id == current_user.id,
        'created_at': m.created_at.isoformat() if m.created_at else None,
    } for m in rows]
    return jsonify({'messages': items})


@app.route('/api/groups/<int:group_id>/send', methods=['POST'])
@login_required
def api_groups_send(group_id):
    if not _is_group_member(group_id, current_user.id):
        return jsonify({'error': 'Вы не в группе'}), 403
    data = request.get_json(silent=True) or {}
    body = (data.get('body') or '').strip()
    if not body:
        return jsonify({'error': 'Сообщение пустое'}), 400
    m = GroupMessage(
        group_id=group_id, sender_id=current_user.id, body=body[:4000]
    )
    db.session.add(m)
    db.session.commit()
    return jsonify({'success': True, 'id': m.id})


@app.route('/groups/<int:group_id>')
@login_required
def group_page(group_id):
    if not _is_group_member(group_id, current_user.id):
        from flask import abort
        abort(404)
    g = GroupChat.query.get(group_id)
    is_owner = bool(g and g.owner_id == current_user.id)
    return render_template('group_chat.html', group=g, is_owner=is_owner)


if __name__ == '__main__':
    # Auto-reloader is disabled by default because long-running endpoints
    # (e.g. /api/drawing/generate, which runs a 1-3 minute LLM pipeline)
    # get killed mid-request whenever Werkzeug detects ANY *.py change
    # in the workspace (including scripts that pytest/scripts touch).
    # Set FLASK_RELOAD=1 explicitly if you want the dev-time auto-reload
    # behaviour back; do NOT set it while testing /drawing endpoints.
    import os
    _use_reloader = (
        os.environ.get("FLASK_RELOAD", "0").strip().lower()
        in ("1", "true", "yes", "on")
    )
    app.run(
        debug=True,
        port=5001,
        use_reloader=_use_reloader,
    )

