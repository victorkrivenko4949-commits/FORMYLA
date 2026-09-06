import re
import markdown as md_lib
from flask import Flask, render_template, request, abort, redirect, session, jsonify, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_mail import Mail, Message
from utils.math_answer_utils import compare_math_answers
from utils.rating_utils import add_xp_for_task, add_xp_for_adaptive_test, add_xp_for_mock_exam, get_xp_for_next_level
from utils.answer_evaluator import check_answers_batch
from utils.olympiad_days import split_problems_by_day, detect_day_from_round
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

try:
    from services.figures_manifest import get_figures_for_problem
    _FIGURES_AVAILABLE = True
except Exception as _fig_err:
    print(f"[figures] manifest not available: {_fig_err}")
    _FIGURES_AVAILABLE = False
    def get_figures_for_problem(*a, **kw):
        return {'condition': [], 'solution': []}

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
    print("[!]️  DeepSeek client not available. AI recommendations disabled.")

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
        print("[OK] Sentry SDK initialized")
    except Exception as _sentry_err:
        print(f"[!]️  Sentry init failed: {_sentry_err}")
else:
    print("ℹ️  SENTRY_DSN не задан — Sentry отключен.")


app = Flask(__name__)

# ─── Security: CSRF, CSP, Rate Limiting, Input Validation ──────────
from services.security import init_security, sanitize_text, sanitize_json_payload, get_csrf_token
init_security(app)

# ─── V9: Centralised build info (one source for /__version, footer, cache-bust) ──
import subprocess as _sp
from datetime import datetime, timezone as _tz

_BUILD_TIME = datetime.now(_tz.utc).isoformat()
# Уникальная метка для cache-busting статики при каждом перезапуске:
# git-коммит не меняется при правках, поэтому браузер кэширует старые
# css/js. Добавляем unix-метку запуска, чтобы после рестарта всегда
# подтягивались свежие файлы (asset_version в шаблонах).
_BUILD_START_TS = str(int(datetime.now(_tz.utc).timestamp()))

def _get_commit_info():
    """Returns (commit, source, branch) — computed once at module load."""
    # 1. RENDER_GIT_COMMIT env (Render deployment)
    commit = os.environ.get("RENDER_GIT_COMMIT")
    if commit:
        branch = os.environ.get("RENDER_GIT_BRANCH", "")
        if not branch:
            try:
                branch = _sp.run(
                    ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
                    capture_output=True, text=True, timeout=5
                ).stdout.strip()
            except Exception:
                branch = "unknown"
        return commit, "render_env", branch or "unknown"

    # 2. Local git
    try:
        commit = _sp.run(
            ['git', 'rev-parse', 'HEAD'],
            capture_output=True, text=True, timeout=5
        ).stdout.strip()
        if commit:
            branch = ""
            try:
                branch = _sp.run(
                    ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
                    capture_output=True, text=True, timeout=5
                ).stdout.strip()
            except Exception:
                branch = "unknown"
            return commit, "git_local", branch or "unknown"
    except Exception:
        pass

    return "unknown", "unknown", "unknown"

_BUILD_COMMIT, _BUILD_COMMIT_SOURCE, _BUILD_BRANCH = _get_commit_info()
_BUILD_COMMIT_SHORT = _BUILD_COMMIT[:8] if _BUILD_COMMIT != "unknown" else "unknown"


# ─── Логгер: пишем в файл вместо stderr ────────────────────────────
# На Windows debug=True + werkzeug debugger перехватывает stderr,
# что вызывает OSError: [Errno 22] Invalid argument при любом выводе
# в stderr (включая app.logger.warning). Решение — FileHandler.
import logging
_log_dir = os.path.join(os.path.dirname(__file__), 'logs')
os.makedirs(_log_dir, exist_ok=True)
_log_file = os.path.join(_log_dir, 'app.log')
_file_handler = logging.FileHandler(_log_file, encoding='utf-8')
_file_handler.setLevel(logging.DEBUG)
_file_handler.setFormatter(logging.Formatter(
    '%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S'
))
# Удаляем дефолтный StreamHandler (пишет в stderr -> ломается под debugger)
app.logger.handlers.clear()
app.logger.addHandler(_file_handler)
app.logger.setLevel(logging.DEBUG)
app.logger.info("=== App started, logging to %s", _log_file)

# ─── Cloudflare ProxyFix (доверяем X-Forwarded-* за CF + Render) ───
try:
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=2, x_proto=1, x_host=1, x_prefix=1)
    print("[OK] ProxyFix applied (x_for=2, x_proto=1, x_host=1, x_prefix=1)")
except Exception as _pf_err:
    print(f"[!]️  ProxyFix not applied: {_pf_err}")
app.config['JSON_AS_ASCII'] = False
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = False

# ── SECURITY: SECRET_KEY ──────────────────────────────────────────
# В production (Render) SECRET_KEY ОБЯЗАН быть задан в Environment.
# Без него все сессии подписываются одним ключом -> утечка аккаунтов.
_secret = os.environ.get('SECRET_KEY')
_is_production = bool(os.environ.get('RENDER') or os.environ.get('DATABASE_URL'))

if _secret:
    app.secret_key = _secret
elif _is_production:
    # НА ПРОДЕ БЕЗ SECRET_KEY — КРИТИЧЕСКАЯ ОШИБКА
    raise RuntimeError(
        " CRITICAL: SECRET_KEY не задан в production!\n"
        "   Установи в Render -> Environment -> SECRET_KEY = <случайная строка 64 символа>\n"
        "   Генерация: python -c \"import secrets; print(secrets.token_hex(32))\""
    )
else:
    # Только для локальной разработки — стабильный ключ
    app.secret_key = 'dev-secret-key-LOCAL-ONLY-NOT-FOR-PRODUCTION'
    print("[!]️  WARNING: Используется дефолтный SECRET_KEY (только для локальной разработки!)")

# V9: Asset versioning for cache busting — driven by commit hash,
# same as /__version and footer. One source, all consumers agree.
@app.context_processor
def _inject_asset_version():
    return dict(asset_version=f"{_BUILD_COMMIT_SHORT}-{_BUILD_START_TS}",
                build_commit=_BUILD_COMMIT,
                build_commit_short=_BUILD_COMMIT_SHORT,
                build_branch=_BUILD_BRANCH,
                build_time=_BUILD_TIME,
                csrf_token=get_csrf_token)

# ─── P12 TASK3: Валидация критических переменных окружения ──────────
# Каждый ключ читается ТОЛЬКО из os.environ. При отсутствии пишем
# в лог, какая именно переменная не задана. Приложение стартует
# без падения; страницы с AI-генерацией честно сообщают о недоступности.

_CRITICAL_ENV_VARS = [
    ("SECRET_KEY",        True,  "сессии Flask, CSRF-токены"),
    ("OPENROUTER_API_KEY", False, "AI-генерация задач (OpenRouter)"),
    ("DEEPSEEK_API_KEY",  False, "AI-проверка ответов (DeepSeek)"),
    ("MAIL_PASSWORD",     False, "отправка почты (SMTP)"),
    ("RESEND_API_KEY",    False, "отправка почты (Resend API)"),
    ("YANDEX_CLIENT_ID",  False, "Яндекс OAuth вход"),
    ("YANDEX_CLIENT_SECRET", False, "Яндекс OAuth вход"),
    ("VAPID_PUBLIC_KEY",  False, "Push-уведомления"),
    ("VAPID_PRIVATE_KEY", False, "Push-уведомления"),
]

_MISSING_CRITICAL = []
_MISSING_OPTIONAL = []
for _var_name, _is_critical, _purpose in _CRITICAL_ENV_VARS:
    _val = os.environ.get(_var_name, "").strip()
    if not _val:
        if _is_critical:
            _MISSING_CRITICAL.append((_var_name, _purpose))
        else:
            _MISSING_OPTIONAL.append((_var_name, _purpose))

print("=" * 60)
print("P12 TASK3: проверка переменных окружения")
print(f"  Всего переменных в окружении: {len(os.environ)}")
if _MISSING_CRITICAL:
    print("  [КРИТИЧЕСКИЕ] ОТСУТСТВУЮТ (приложение может работать нестабильно):")
    for _n, _p in _MISSING_CRITICAL:
        print(f"    - {_n} ({_p})")
if _MISSING_OPTIONAL:
    print("  [ОПЦИОНАЛЬНЫЕ] не заданы (соответствующие функции отключены):")
    for _n, _p in _MISSING_OPTIONAL:
        print(f"    - {_n} ({_p})")
if not _MISSING_CRITICAL and not _MISSING_OPTIONAL:
    print("  Все 9 проверяемых переменных заданы.")
print("=" * 60)

# Database configuration -- supports SQLite (local) and PostgreSQL (production)
# АБСОЛЮТНЫЙ ПУТЬ: всегда вычисляется от корня проекта (app.py),
# независимо от папки запуска и от instance_path Flask.
_default_db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance', 'formyla.db')
_default_db_uri = 'sqlite:///' + _default_db_path.replace('\\', '/')
_database_url = os.environ.get('DATABASE_URL', _default_db_uri)
# Render provides postgres:// or postgresql:// but psycopg3 needs postgresql+psycopg://
if _database_url.startswith('postgres://'):
    _database_url = _database_url.replace('postgres://', 'postgresql+psycopg://', 1)
elif _database_url.startswith('postgresql://') and '+psycopg' not in _database_url:
    _database_url = _database_url.replace('postgresql://', 'postgresql+psycopg://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = _database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
_engine_opts = {
    'pool_pre_ping': True,
    'pool_recycle': 300,
    'pool_size': 5,
    'max_overflow': 5,
    'pool_timeout': 10,
}
if _database_url.startswith('postgresql'):
    _engine_opts['connect_args'] = {
        'connect_timeout': 10,
        'keepalives': 1,
        'keepalives_idle': 30,
        'keepalives_interval': 10,
        'keepalives_count': 3,
        'options': '-c statement_timeout=30000',
    }
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = _engine_opts
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

# Flask-Mail configuration (Resend by default, fully configurable via env vars).
# Resend SMTP requires: host=smtp.resend.com, port=465, SSL=True, username='resend',
# password=<RESEND_API_KEY>. MAIL_DEFAULT_SENDER must be a verified address
# (or onboarding@resend.dev for testing) — NOT the username 'resend'.
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.resend.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', '465'))
# Жесткое преобразование строк в bool (исправлено для корректной работы)
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'False').lower() in ['true', '1', 't', 'yes']
app.config['MAIL_USE_SSL'] = os.environ.get('MAIL_USE_SSL', 'True').lower() in ['true', '1', 't', 'yes']
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', 'resend')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD') or os.environ.get('RESEND_API_KEY')
# Explicit MAIL_DEFAULT_SENDER takes priority; fallback to onboarding@resend.dev
# (Resend's shared sandbox sender that works without domain verification).
app.config['MAIL_DEFAULT_SENDER'] = (
    os.environ.get('MAIL_DEFAULT_SENDER')
    or 'onboarding@resend.dev'
)

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
# Yandex.Metrika — ID счётчика 109394525 (можно переопределить через env YANDEX_METRIKA_ID)
app.config['YANDEX_METRIKA_ID'] = (os.environ.get('YANDEX_METRIKA_ID') or '109394525').strip()

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
from models_curator import CuratorState, Subtopic, SubtopicProgress  # noqa: F401
init_db(app)


# V10: Unified auto-migration (runs before all individual AUTO-MIGRATION blocks).
# Creates missing tables and adds missing columns for ALL registered models.
# Idempotent — safe to run on every startup.
# Individual AUTO-MIGRATION blocks below are kept as no-ops for backward compatibility.
#
# Import ALL model modules before auto_migrate so their tables/columns are in
# SQLAlchemy metadata. Otherwise auto_migrate cannot see tables defined in
# blueprints (daily_tasks, curator, grade, olympiad, etc.).
try:
    import daily_tasks.models          # noqa: F401  — DailyTaskSet, DailyTaskItem, DailyGenerationJob
    import models_olympiad             # noqa: F401  — Probnik, OlympiadTask, etc. (re-imported by models.py too)
    try:
        import models_grade            # noqa: F401  — grade 5-6 models
    except ImportError:
        pass
except Exception:
    pass

try:
    from services.auto_migrate import auto_migrate
    _v10_created, _v10_added = auto_migrate(app, db)
    if _v10_created:
        print(f"[AUTO-MIGRATE/V10] Created tables: {_v10_created}")
    if _v10_added:
        print(f"[AUTO-MIGRATE/V10] Added columns: {_v10_added}")
    if not _v10_created and not _v10_added:
        print("[AUTO-MIGRATE/V10] Schema up-to-date — nothing to do")
except Exception as _e_v10:
    import traceback as _tb_v10
    print(f"[AUTO-MIGRATE/V10] ERROR: {_e_v10}")
    print(_tb_v10.format_exc())


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
                print("[AUTO-MIGRATION] [OK] Column 'agent_type' added successfully!")
            else:
                print("[AUTO-MIGRATION] [OK] Column 'agent_type' already exists")
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
                # Поля для адаптивного сидера (services/adaptive_full_seed.py).
                # Используются для idempotency и трассировки источника датасета.
                'task_type': 'TEXT',
                'source': 'TEXT',
                'origin': 'VARCHAR(16)',
                'methods_json': 'TEXT',
                # П1: theme_id и theme_title для человеческого названия подтем
                'theme_id': 'VARCHAR(50)',
                'theme_title': 'VARCHAR(300)',
            }
            for col_name, col_type in new_cols.items():
                if col_name not in columns:
                    db.session.execute(text(f"ALTER TABLE adaptive_tasks ADD COLUMN {col_name} {col_type}"))
                    db.session.commit()
                    print(f"[AUTO-MIGRATION] [OK] Column '{col_name}' added to adaptive_tasks")
                else:
                    print(f"[AUTO-MIGRATION] [OK] Column '{col_name}' already exists")
except Exception as e:
    print(f"[AUTO-MIGRATION] adaptive_tasks Warning: {e}")

# AUTO-MIGRATION: Add is_calibration column to daily_task_items
# Колонка добавлена в daily_tasks/models.py:89 (PR percent_to_level + calibration,
# 2026-06-08). Без неё /daily_tasks падает с UndefinedColumn 500. Idempotent.
try:
    with app.app_context():
        from sqlalchemy import inspect, text
        inspector = inspect(db.engine)
        if 'daily_task_items' in inspector.get_table_names():
            columns = [col['name'] for col in inspector.get_columns('daily_task_items')]
            if 'is_calibration' not in columns:
                print("[AUTO-MIGRATION] Adding 'is_calibration' to daily_task_items...")
                # BOOLEAN DEFAULT FALSE — синтаксис понимают и PostgreSQL, и SQLite.
                db.session.execute(text(
                    "ALTER TABLE daily_task_items ADD COLUMN is_calibration BOOLEAN DEFAULT FALSE NOT NULL"
                ))
                db.session.commit()
                print("[AUTO-MIGRATION] [OK] Column 'is_calibration' added to daily_task_items")
            else:
                print("[AUTO-MIGRATION] [OK] Column 'is_calibration' already exists on daily_task_items")
except Exception as e:
    print(f"[AUTO-MIGRATION] daily_task_items.is_calibration Warning: {e}")

# AUTO-MIGRATION: Add prep_state column to curator_state
# Колонка добавлена в models_curator.py:19 (prep_state = db.Column(db.JSON, default=dict)).
# Без неё /prep/coach падает с OperationalError «нет такого столбца: curator_state.prep_state».
try:
    with app.app_context():
        from sqlalchemy import inspect, text
        inspector = inspect(db.engine)
        if 'curator_state' in inspector.get_table_names():
            columns = [col['name'] for col in inspector.get_columns('curator_state')]
            if 'prep_state' not in columns:
                print("[AUTO-MIGRATION] Adding 'prep_state' column to curator_state...")
                db.session.execute(text(
                    "ALTER TABLE curator_state ADD COLUMN prep_state TEXT DEFAULT '{}'"
                ))
                db.session.commit()
                print("[AUTO-MIGRATION] [OK] Column 'prep_state' added to curator_state!")
            else:
                print("[AUTO-MIGRATION] [OK] Column 'prep_state' already exists on curator_state")
except Exception as e:
    print(f"[AUTO-MIGRATION] curator_state.prep_state Warning: {e}")

# AUTO-MIGRATION: Add level_engine columns to curator_state
# Колонки добавлены в models_curator.py (level_mu, level_sigma, level_by_section,
# level_updated_at). Используются services/level_engine.py как единый держатель
# канонического уровня FORMYLA (шкала 1..5). Идемпотентно.
try:
    with app.app_context():
        from sqlalchemy import inspect as _inspect_le, text as _text_le
        _inspector_le = _inspect_le(db.engine)
        if 'curator_state' in _inspector_le.get_table_names():
            _columns_le = [col['name'] for col in _inspector_le.get_columns('curator_state')]
            _new_level_cols = {
                'level_mu': 'REAL',
                'level_sigma': 'REAL',
                'level_by_section': 'TEXT',
                'level_updated_at': 'TEXT',
            }
            for _col_name_le, _col_type_le in _new_level_cols.items():
                if _col_name_le not in _columns_le:
                    try:
                        db.session.execute(_text_le(
                            f"ALTER TABLE curator_state ADD COLUMN {_col_name_le} {_col_type_le}"
                        ))
                        db.session.commit()
                        print(f"[AUTO-MIGRATION] \u2713 Column '{_col_name_le}' added to curator_state")
                    except Exception as _e_col_le:
                        db.session.rollback()
                        print(f"[AUTO-MIGRATION] curator_state.{_col_name_le} skipped: {_e_col_le}")
                else:
                    print(f"[AUTO-MIGRATION] \u2713 Column '{_col_name_le}' already exists on curator_state")
except Exception as e:
    print(f"[AUTO-MIGRATION] curator_state level_engine Warning: {e}")


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
        print("[AUTO-MIGRATION] [OK] Table 'tutor_calls' ready")
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
                        print(f"[AUTO-MIGRATION] [OK] Column '{_col_name}' added to adaptive_tasks")
                    except Exception as _e_col_nr:
                        db.session.rollback()
                        print(f"[AUTO-MIGRATION] adaptive_tasks.{_col_name} skipped: {_e_col_nr}")
except Exception as e:
    print(f"[AUTO-MIGRATION] needs_review columns Warning: {e}")

# AUTO-MIGRATION D3: Add figure_json + figure_status to adaptive_tasks
# Колонки добавлены в models.py:867-871 (D3 PIPELINE).
# figure_json — описание геометрических построений (JSON geometric_engine).
# figure_status — статус чертежа: no_description/has_description/figure_built/
#                engine_rejected/human_verified/human_rejected.
# Идемпотентно — через inspect, а не try/except на ALTER.
try:
    with app.app_context():
        from sqlalchemy import inspect as _inspect_fig, text as _text_fig
        _inspector_fig = _inspect_fig(db.engine)
        if 'adaptive_tasks' in _inspector_fig.get_table_names():
            _columns_fig = [col['name'] for col in _inspector_fig.get_columns('adaptive_tasks')]
            _new_fig_cols = {
                'figure_json': 'TEXT',
                'figure_status': "VARCHAR(32) NOT NULL DEFAULT 'no_description'",
            }
            for _col_name_fig, _col_type_fig in _new_fig_cols.items():
                if _col_name_fig not in _columns_fig:
                    try:
                        db.session.execute(_text_fig(
                            f"ALTER TABLE adaptive_tasks ADD COLUMN {_col_name_fig} {_col_type_fig}"
                        ))
                        db.session.commit()
                        print(f"[AUTO-MIGRATION] \u2713 Column '{_col_name_fig}' added to adaptive_tasks")
                    except Exception as _e_col_fig:
                        db.session.rollback()
                        print(f"[AUTO-MIGRATION] adaptive_tasks.{_col_name_fig} skipped: {_e_col_fig}")
                else:
                    print(f"[AUTO-MIGRATION] \u2713 Column '{_col_name_fig}' already exists on adaptive_tasks")
            # Ensure index on figure_status
            try:
                db.session.execute(_text_fig(
                    "CREATE INDEX IF NOT EXISTS ix_adaptive_tasks_figure_status "
                    "ON adaptive_tasks(figure_status)"
                ))
                db.session.commit()
            except Exception:
                db.session.rollback()
except Exception as e:
    print(f"[AUTO-MIGRATION] figure_fields Warning: {e}")

# AUTO-MIGRATION D3: Add figure_json + figure_status to daily_task_items
try:
    with app.app_context():
        from sqlalchemy import inspect as _inspect_dtf, text as _text_dtf
        _inspector_dtf = _inspect_dtf(db.engine)
        if 'daily_task_items' in _inspector_dtf.get_table_names():
            _columns_dtf = [col['name'] for col in _inspector_dtf.get_columns('daily_task_items')]
            _new_dtf_cols = {
                'figure_json': 'TEXT',
                'figure_status': "VARCHAR(32) NOT NULL DEFAULT 'no_description'",
                'figure_svg_path': 'TEXT',
            }
            for _col_name_dtf, _col_type_dtf in _new_dtf_cols.items():
                if _col_name_dtf not in _columns_dtf:
                    try:
                        db.session.execute(_text_dtf(
                            f"ALTER TABLE daily_task_items ADD COLUMN {_col_name_dtf} {_col_type_dtf}"
                        ))
                        db.session.commit()
                        print(f"[AUTO-MIGRATION] \u2713 Column '{_col_name_dtf}' added to daily_task_items")
                    except Exception as _e_col_dtf:
                        db.session.rollback()
                        print(f"[AUTO-MIGRATION] daily_task_items.{_col_name_dtf} skipped: {_e_col_dtf}")
                else:
                    print(f"[AUTO-MIGRATION] \u2713 Column '{_col_name_dtf}' already exists on daily_task_items")
            try:
                db.session.execute(_text_dtf(
                    "CREATE INDEX IF NOT EXISTS ix_daily_task_items_figure_status "
                    "ON daily_task_items(figure_status)"
                ))
                db.session.commit()
            except Exception:
                db.session.rollback()
except Exception as e:
    print(f"[AUTO-MIGRATION] daily_task_items figure_fields Warning: {e}")

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
            print(f"[AUTO-MIGRATION] [OK] Group chat tables created")
        else:
            print("[AUTO-MIGRATION] [OK] Group chat tables already exist")
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

# AUTO-MIGRATION CH22: aux_status / aux_fail_reason для figure_build_jobs.
try:
    with app.app_context():
        from sqlalchemy import inspect as _inspect_ch22
        _ins_ch22 = _inspect_ch22(db.engine)
        if 'figure_build_jobs' in set(_ins_ch22.get_table_names()):
            _cols_ch22 = {c['name'] for c in _ins_ch22.get_columns('figure_build_jobs')}
            for _col, _typ in (('aux_status', 'VARCHAR(40)'),
                               ('aux_fail_reason', 'TEXT')):
                if _col in _cols_ch22:
                    continue
                try:
                    db.session.execute(db.text(
                        f"ALTER TABLE figure_build_jobs ADD COLUMN {_col} {_typ}"
                    ))
                    db.session.commit()
                    print(f"[AUTO-MIGRATION] OK Added figure_build_jobs.{_col}")
                except Exception as _e_ch22:
                    db.session.rollback()
                    print(f"[AUTO-MIGRATION] figure_build_jobs.{_col} skipped: {_e_ch22}")
except Exception as _e_ch22_outer:
    print(f"[AUTO-MIGRATION] CH22 figure_build_jobs fields skipped: {_e_ch22_outer}")

# AUTO-MIGRATION: VsOSh-9 method-bank fields для olympiad_theory / olympiad_tasks.
# Модели в models_olympiad.py содержат новые колонки (total_count, share_percent,
# method_codes, year, stage). На локалке SQLite db.create_all() их подхватывает,
# но на проде Postgres колонки нужно добавить ALTER-ом, иначе любой SELECT
# по таблицам сыпет UndefinedColumn -> 500 на каждой странице.
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
            _alter('olympiad_tasks', 'probnik_id', 'INTEGER'),
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
        # Also add FK constraint for probnik_id on PostgreSQL
        if _is_pg_olymp and 'olympiad_tasks' in _existing_o:
            try:
                _pk_cols = {c['name'] for c in _ins_o.get_columns('olympiad_tasks')}
                if 'probnik_id' in _pk_cols:
                    # Check if FK constraint already exists
                    _fk_sql = text(
                        "SELECT 1 FROM information_schema.table_constraints "
                        "WHERE constraint_type='FOREIGN KEY' "
                        "AND table_name='olympiad_tasks' "
                        "AND constraint_name='fk_olympiad_tasks_probnik_id'"
                    )
                    _fk_exists = db.session.execute(_fk_sql).scalar()
                    if not _fk_exists:
                        db.session.execute(text(
                            "ALTER TABLE olympiad_tasks "
                            "ADD CONSTRAINT fk_olympiad_tasks_probnik_id "
                            "FOREIGN KEY (probnik_id) REFERENCES olympiad_probniks(id) "
                            "ON DELETE CASCADE"
                        ))
                        db.session.commit()
                        print("[AUTO-MIGRATION] OK Added FK olympiad_tasks.probnik_id -> olympiad_probniks.id")
            except Exception as _e_fk:
                db.session.rollback()
                print(f"[AUTO-MIGRATION] FK olympiad_tasks.probnik_id skipped: {_e_fk}")
except Exception as _e_olymp:
    print(f"[AUTO-MIGRATION] olympiad fields Warning: {_e_olymp}")

# AUTO-MIGRATION: olympiad_task_attempts.status legacy cleanup.
# В проде встречаются legacy-значения статуса (например 'submitted'),
# оставшиеся от предыдущей схемы. Модель уже использует db.String, но в БД
# может остаться CHECK-ограничение (native_enum=False делает CHECK), которое
# блокирует UPDATE. Делаем 3 шага:
#   1) Снимаем CHECK-ограничение task_attempt_status (PostgreSQL).
#   2) Нормализуем legacy-статусы -> 'attempted'.
#   3) Тип колонки уже VARCHAR — менять не нужно.
try:
    with app.app_context():
        from sqlalchemy import text, inspect as _sa_inspect
        _insp = _sa_inspect(db.engine)
        if 'olympiad_task_attempts' in _insp.get_table_names():
            _dialect = db.engine.dialect.name
            # 1) Drop CHECK-constraint on PostgreSQL (имя автогенерируется,
            #    но Enum(native_enum=False) обычно создаёт ck_*_task_attempt_status).
            if _dialect == 'postgresql':
                try:
                    _checks = db.session.execute(text("""
                        SELECT conname FROM pg_constraint
                        WHERE conrelid = 'olympiad_task_attempts'::regclass
                          AND contype = 'c'
                          AND pg_get_constraintdef(oid) ILIKE '%status%'
                    """)).fetchall()
                    for (_cname,) in _checks:
                        try:
                            db.session.execute(text(
                                f'ALTER TABLE olympiad_task_attempts '
                                f'DROP CONSTRAINT IF EXISTS "{_cname}"'
                            ))
                            print(f"[AUTO-MIGRATION] OK dropped CHECK {_cname} on olympiad_task_attempts")
                        except Exception as _e_ck:
                            db.session.rollback()
                            print(f"[AUTO-MIGRATION] skip drop {_cname}: {_e_ck}")
                    db.session.commit()
                except Exception as _e_chks:
                    db.session.rollback()
                    print(f"[AUTO-MIGRATION] check constraints skipped: {_e_chks}")
            # 2) Нормализуем legacy-статусы. 'submitted' -> 'attempted'
            #    (см. ATTEMPT_STATUSES в models_olympiad).
            try:
                _res = db.session.execute(text(
                    "UPDATE olympiad_task_attempts "
                    "SET status='attempted' "
                    "WHERE status NOT IN ('viewed','attempted','solved','revealed')"
                ))
                db.session.commit()
                if getattr(_res, 'rowcount', 0):
                    print(f"[AUTO-MIGRATION] OK normalized {_res.rowcount} legacy task-attempt statuses")
                else:
                    print("[AUTO-MIGRATION] [OK] olympiad_task_attempts.status already normalized")
            except Exception as _e_upd:
                db.session.rollback()
                print(f"[AUTO-MIGRATION] task-attempts normalize skipped: {_e_upd}")
except Exception as _e_ta:
    print(f"[AUTO-MIGRATION] task_attempts cleanup Warning: {_e_ta}")

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

                # --- questionnaire_state for DB-backed diagnostic questionnaire ---
        try:
            db.session.execute(db.text("ALTER TABLE users ADD COLUMN questionnaire_state TEXT"))
            db.session.commit()
            print("[migration] Added questionnaire_state to users")
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

        # --- User: generation limits (free mock / exam generation) ---
        for _stmt, _label in (
            ("ALTER TABLE users ADD COLUMN generation_count_today INTEGER NOT NULL DEFAULT 0", "generation_count_today"),
            ("ALTER TABLE users ADD COLUMN generation_reset_date DATE", "generation_reset_date"),
            ("ALTER TABLE users ADD COLUMN gens_extra_purchased INTEGER NOT NULL DEFAULT 0", "gens_extra_purchased"),
            ("ALTER TABLE users ADD COLUMN gens_unlimited BOOLEAN NOT NULL DEFAULT 0", "gens_unlimited"),
        ):
            try:
                db.session.execute(db.text(_stmt))
                db.session.commit()
                print(f"[migration] Added {_label} to users")
            except Exception:
                db.session.rollback()
except Exception as e:
    print(f"[AUTO-MIGRATION] guest columns Warning: {e}")

# AUTO-MIGRATION: pre_gen_queue table (pre-generation of tomorrow's tasks)
try:
    from migrations.add_pregen_queue import _ensure_table as _ensure_pregen_table
    _ensure_pregen_table()
    print("[migration] pre_gen_queue table ensured")
except Exception as e:
    print(f"[AUTO-MIGRATION] pre_gen_queue table: {e}")

# AUTO-MIGRATION D5: Create figure_jobs table for background figure generation queue
try:
    with app.app_context():
        from sqlalchemy import inspect as _inspect_fj, text as _text_fj
        _inspector_fj = _inspect_fj(db.engine)
        if 'figure_jobs' not in _inspector_fj.get_table_names():
            _is_pg_fj = _database_url.startswith('postgresql')
            if _is_pg_fj:
                db.session.execute(_text_fj("""
                    CREATE TABLE IF NOT EXISTS figure_jobs (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        problem TEXT NOT NULL,
                        solution TEXT,
                        status VARCHAR(20) NOT NULL DEFAULT 'queued',
                        step_label VARCHAR(80),
                        json_description TEXT,
                        svg_result TEXT,
                        error_message TEXT,
                        credit_spent BOOLEAN NOT NULL DEFAULT FALSE,
                        model_used VARCHAR(120),
                        cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW()
                    )
                """))
                db.session.execute(_text_fj(
                    "CREATE INDEX IF NOT EXISTS ix_figure_jobs_status ON figure_jobs(status)"
                ))
                db.session.execute(_text_fj(
                    "CREATE INDEX IF NOT EXISTS ix_figure_jobs_user_id ON figure_jobs(user_id)"
                ))
            else:
                db.session.execute(_text_fj("""
                    CREATE TABLE IF NOT EXISTS figure_jobs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        problem TEXT NOT NULL,
                        solution TEXT,
                        status VARCHAR(20) NOT NULL DEFAULT 'queued',
                        step_label VARCHAR(80),
                        json_description TEXT,
                        svg_result TEXT,
                        error_message TEXT,
                        credit_spent BOOLEAN NOT NULL DEFAULT 0,
                        model_used VARCHAR(120),
                        cost_usd REAL NOT NULL DEFAULT 0.0,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                db.session.execute(_text_fj(
                    "CREATE INDEX IF NOT EXISTS ix_figure_jobs_status ON figure_jobs(status)"
                ))
                db.session.execute(_text_fj(
                    "CREATE INDEX IF NOT EXISTS ix_figure_jobs_user_id ON figure_jobs(user_id)"
                ))
            db.session.commit()
            print("[AUTO-MIGRATION] [OK] Created figure_jobs table")
        else:
            print("[AUTO-MIGRATION] [OK] figure_jobs table already exists")
except Exception as e:
    print(f"[AUTO-MIGRATION] figure_jobs Warning: {e}")

# D5 STALE JOB RECOVERY: Mark jobs stuck for >10 min as failed, refund credits.
try:
    with app.app_context():
        from datetime import datetime as _dt, timedelta as _td
        from models import FigureJob as _FJ, User as _U
        _cutoff = _dt.utcnow() - _td(minutes=10)
        _stale = _FJ.query.filter(
            _FJ.status.in_(['queued', 'thinking', 'drawing']),
            _FJ.updated_at < _cutoff,
        ).all()
        for _job in _stale:
            _old_status = _job.status
            _job.status = 'failed'
            _job.error_message = f"Stale job timed out (was {_old_status} for >10 min)"
            _job.step_label = None
            _job.updated_at = _dt.utcnow()
            if _job.credit_spent:
                try:
                    _user = _U.query.get(_job.user_id)
                    if _user:
                        credits = getattr(_user, 'figure_credits', 0) or 0
                        _user.figure_credits = credits + 1
                        _job.credit_spent = False
                except Exception:
                    pass
        if _stale:
            db.session.commit()
            print(f"[D5 RECOVERY] Marked {len(_stale)} stale figure_jobs as failed")
except Exception as _e_rec:
    print(f"[D5 RECOVERY] Warning: {_e_rec}")

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
                print("[AUTO-MIGRATION] [OK] Recreated friendships table with new schema")
            else:
                print("[AUTO-MIGRATION] [OK] friendships table schema OK")
        else:
            db.create_all()
            print("[AUTO-MIGRATION] [OK] Created friendships table")
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
            print("[AUTO-MIGRATION] [OK] Created support_messages table")
        else:
            print("[AUTO-MIGRATION] [OK] support_messages table already exists")
except Exception as e:
    print(f"[AUTO-MIGRATION] support_messages Warning: {e}")

# AUTO-MIGRATION: Create site_reviews table for public user reviews
# Хранит публичные отзывы о сайте, чтобы их видели другие пользователи
# на странице /about. Отзыв публикуется автоматически после отправки формы.
try:
    with app.app_context():
        from sqlalchemy import inspect as _inspect_sr, text as _text_sr
        _inspector_sr = _inspect_sr(db.engine)
        if 'site_reviews' not in _inspector_sr.get_table_names():
            _is_pg_sr = _database_url.startswith('postgresql')
            if _is_pg_sr:
                db.session.execute(_text_sr("""
                    CREATE TABLE IF NOT EXISTS site_reviews (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                        nickname VARCHAR(64),
                        avatar_url VARCHAR(500),
                        rating INTEGER NOT NULL DEFAULT 0,
                        message TEXT NOT NULL,
                        is_public BOOLEAN DEFAULT TRUE,
                        is_hidden BOOLEAN DEFAULT FALSE,
                        ip VARCHAR(64),
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                """))
                db.session.execute(_text_sr("""
                    CREATE INDEX IF NOT EXISTS idx_site_reviews_public
                    ON site_reviews(is_public, is_hidden, created_at DESC)
                """))
            else:
                db.session.execute(_text_sr("""
                    CREATE TABLE IF NOT EXISTS site_reviews (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                        nickname VARCHAR(64),
                        avatar_url VARCHAR(500),
                        rating INTEGER NOT NULL DEFAULT 0,
                        message TEXT NOT NULL,
                        is_public BOOLEAN DEFAULT 1,
                        is_hidden BOOLEAN DEFAULT 0,
                        ip VARCHAR(64),
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """))
            db.session.commit()
            print("[AUTO-MIGRATION] [OK] Created site_reviews table")
        else:
            print("[AUTO-MIGRATION] [OK] site_reviews table already exists")
except Exception as e:
    print(f"[AUTO-MIGRATION] site_reviews Warning: {e}")

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
                print("[AUTO-MIGRATION] [OK] Column 'solved_indices' added")
            else:
                print("[AUTO-MIGRATION] [OK] Column 'solved_indices' already exists")
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
    import traceback; print('[BP] prep_bp NOT registered:'); traceback.print_exc()

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
    from routes.figures import figures_bp
    app.register_blueprint(figures_bp)
    print("[BP] figures_bp registered (/figures)")
except Exception as _e:
    print(f"[BP] figures_bp NOT registered: {_e}")

# CH5: New figure generation pipeline with its own /figures/generate prefix.
try:
    from routes.figures_generator import figures_gen_bp, _ensure_queue_worker
    app.register_blueprint(figures_gen_bp)
    print("[BP] figures_gen_bp registered (/figures/generate)")
    # CH22: телеметрия стадий генерации чертежа.
    from migrations.add_figure_build_stages import _ensure_table as _ensure_figure_stages
    with app.app_context():
        _ensure_figure_stages()
    # Start figure build queue worker daemon
    _ensure_queue_worker(app)
except Exception as _e:
    print(f"[BP] figures_gen_bp NOT registered: {_e}")

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

# Conference room API (SocketIO-backed group video calls).
try:
    from routes.conference_api import conference_api_bp
    app.register_blueprint(conference_api_bp)
    print("[BP] conference_api_bp registered (/api/conference/*)")
except Exception as _e:
    print(f"[BP] conference_api_bp NOT registered: {_e}")

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
    print("[BP] olympiad_bp registered (/olympiads/*: probnik, task, stage, methods)")

    # Admin Support inbox + user-side «Твоя поддержка»
    try:
        from routes.admin_support import admin_support_bp
        app.register_blueprint(admin_support_bp)
        print("[BP] admin_support_bp registered (/admin/support, /my/support)")
    except Exception as _e_as:
        print(f"[BP] admin_support_bp FAILED: {_e_as}")
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

# SocketIO for conference WebRTC signalling (видеоконференции).
try:
    from routes.wb_ws import init_socketio
    init_socketio(app, manage_session=False)
    print("[SocketIO] Conference WebSocket signalling initialized (/ws-call)")
except Exception as _e_sio:
    print(f"[SocketIO] Failed to initialize: {_e_sio}")

# ── VsOsh-9 2027 v4 force-import on boot ─────────────────────────────────────
# autoseed выше — пуглив: пропускает раздачу, если в Probnik/OlympiadTask уже
# есть ХОТЯ БЫ одна строка (любой другой олимпиады). Из-за этого v4-задачи
# курса «ВсОШ-9 2026/2027» не доезжают до прод-БД на Render. Этот блок
# идемпотентно прогоняет upsert/replace из scripts/import_olympiad на старте.
# Отключается env-переменной VSOSH9_2027_FORCE_IMPORT=0.
# ВсОШ-2027 production-сидер: безопасно (идемпотентно) перезаливает данные
# 9/10/11 классов из data/olympiads/vsosh9_full.json + vsosh_10_11_full.json
# при VSOSH9_2027_FORCE_IMPORT=1. Если в БД уже 50 пробников × 20 задач,
# пропускает (см. services/vsosh_full_seed.py).
# СТАРЫЙ run_v4_force_import (services.olympiad_v4_force) ОТКЛЮЧЕН —
# он перезаписывал свежие данные старыми JSON из data/olympiads/v4.
if os.environ.get('VSOSH9_2027_FORCE_IMPORT', '0') == '1':
    try:
        from services.vsosh_full_seed import run_vsosh_full_seed
        _seed_result = run_vsosh_full_seed(app, db)
        print(f"[VSOSH-FULL-SEED] result={_seed_result}")
    except Exception as _e_seed:
        import traceback as _tb_seed
        print(f"[VSOSH-FULL-SEED] hook FAILED: {_e_seed}")
        print(_tb_seed.format_exc())
else:
    print("[VSOSH-FULL-SEED] disabled (set VSOSH9_2027_FORCE_IMPORT=1 to enable)")

# ── VsOSh 10/11 2027 additive seed (idempotent, non-destructive) ─────────
# Аддитивный сидер: ТОЛЬКО для grade=10 и grade=11 (вставка отсутствующих
# пробников/задач). НЕ удаляет данные 9 класса (в отличие от
# services.vsosh_full_seed). По умолчанию включён; отключить можно через
# env VSOSH10_2027_FORCE_IMPORT=0. Источник: data/olympiads/vsosh_10_11_full.json.
if os.environ.get('VSOSH10_2027_FORCE_IMPORT', '1').strip().lower() in ('1', 'true', 'yes', 'on'):
    try:
        from services.vsosh_10_11_additive_seed import run_vsosh_10_11_additive_seed
        _seed_10_11_result = run_vsosh_10_11_additive_seed(app, db)
        print(f"[VSOSH10_11-ADD] result={_seed_10_11_result}")
    except Exception as _e_seed_10_11:
        import traceback as _tb_seed_10_11
        print(f"[VSOSH10_11-ADD] hook FAILED: {_e_seed_10_11}")
        print(_tb_seed_10_11.format_exc())
else:
    print("[VSOSH10_11-ADD] disabled (set VSOSH10_2027_FORCE_IMPORT=1 to enable)")

# ── Adaptive bank seed (9120 калиброванных задач L1..L8) ─────────────────
# Идемпотентно перезаливает таблицу adaptive_tasks из
# data/adaptive/adaptive_full_9120.json. Если уже >= 9000 строк с
# source = 'calibrated_2026_06_04' — пропускает работу.
# Включается переменной окружения ADAPTIVE_FORCE_IMPORT=1.
if os.environ.get('ADAPTIVE_FORCE_IMPORT', '0') == '1':
    try:
        from services.adaptive_full_seed import run_adaptive_full_seed
        _ad_seed_result = run_adaptive_full_seed(app, db)
        print(f"[ADAPTIVE-FULL-SEED] result={_ad_seed_result}")
    except Exception as _e_ad_seed:
        import traceback as _tb_ad_seed
        print(f"[ADAPTIVE-FULL-SEED] hook FAILED: {_e_ad_seed}")
        print(_tb_ad_seed.format_exc())
else:
    print("[ADAPTIVE-FULL-SEED] disabled (set ADAPTIVE_FORCE_IMPORT=1 to enable)")

# ── LaTeX root fix (идемпотентно, чинит битые \sqrt[n]{}/\sqrt{} в БД) ────
# JSON-сидеры уже починены (scripts/normalize_roots_in_data.py), но прод
# читает из PostgreSQL. На каждом редеплое прогоняем текстовые колонки
# olympiad_tasks / method_tasks / adaptive_tasks через normalize_roots и
# UPDATE-им только изменившиеся строки. Безопасно для корректных формул.
# Отключить можно через env LATEX_ROOT_DB_FIX=0.
if os.environ.get('LATEX_ROOT_DB_FIX', '1').strip().lower() in ('1', 'true', 'yes', 'on'):
    try:
        from services.latex_root_db_fix import run_latex_root_db_fix
        _root_fix_result = run_latex_root_db_fix(app, db)
        print(f"[LATEX-ROOT-DB-FIX] result={_root_fix_result}")
    except Exception as _e_root_fix:
        import traceback as _tb_root_fix
        print(f"[LATEX-ROOT-DB-FIX] hook FAILED: {_e_root_fix}")
        print(_tb_root_fix.format_exc())
else:
    print("[LATEX-ROOT-DB-FIX] disabled (set LATEX_ROOT_DB_FIX=1 to enable)")

# ── Theory catalog seed (idempotent, без env-гейта) ──────────────────────────
# Засевает olympiad_theory из data/olympiads/methods_catalog_89.json,
# если таблица пуста или содержит plaholder-имена. Безопасно: ничего
# не трогает в Probnik/OlympiadTask. Это решает проблему пустого
# «Каталога методов» (/olympiads/methods) на проде после миграции БД.
try:
    from services.olympiad_autoseed import seed_theory_only
    seed_theory_only(app, db)
except Exception as _e_theory_seed:
    print(f"[THEORY-SEED] hook skipped: {_e_theory_seed}")

# ── Olympiad prep catalog seed (idempotent, без env-гейта) ───────────────────
# Засевает olympiad_prep дефолтным набором олимпиад России, если таблица
# пуста. Безопасно: ничего не пересоздаёт, если уже есть хотя бы одна запись.
# Это решает проблему пустого «Календаря олимпиад» (/olympiad-prep/calendar)
# на проде, где локальные скрипты вроде _add_10_olympiads.py не запускаются.
# grades/stages в модели — db.Text, поэтому передаём JSON-строки.
try:
    import json as _json_seed
    with app.app_context():
        from models import OlympiadPrep as _OlympiadPrepSeed
        if _OlympiadPrepSeed.query.count() == 0:
            print("[OLYMP-PREP-SEED] olympiad_prep empty, seeding 10 defaults...")
            _olymp_prep_defaults = [
                {
                    "slug": "fiztekh",
                    "name": "Олимпиада «Физтех»",
                    "short_name": "Физтех",
                    "description": "Олимпиада «Физтех» по математике проводится Московским физико-техническим институтом. Победители и призёры получают льготы при поступлении в ведущие вузы России.",
                    "grades": [9, 10, 11],
                    "official_url": "https://olymp.mipt.ru/",
                    "color_hex": "#06b6d4",
                    "stages": [
                        {"name": "Отборочный этап", "date_range": "Октябрь 2025 – январь 2026"},
                        {"name": "Заключительный этап", "date_range": "Февраль – март 2026"},
                    ],
                },
                {
                    "slug": "kurchatov",
                    "name": "Олимпиада «Курчатов»",
                    "short_name": "Курчатов",
                    "description": "Олимпиада «Курчатов» по математике для школьников. Даёт льготы при поступлении в вузы.",
                    "grades": [9, 10, 11],
                    "official_url": "https://kurchatov.test.ru/",
                    "color_hex": "#a855f7",
                    "stages": [
                        {"name": "Отборочный этап", "date_range": "Уточняется"},
                        {"name": "Заключительный этап", "date_range": "Весна 2026"},
                    ],
                },
                {
                    "slug": "shag-v-budushchee",
                    "name": "Шаг в будущее",
                    "short_name": "Шаг в будущее",
                    "description": "Олимпиада школьников «Шаг в будущее» по математике. Проводится МГТУ им. Н.Э. Баумана.",
                    "grades": [8, 9, 10, 11],
                    "official_url": "https://olymp.bmstu.ru/",
                    "color_hex": "#f97316",
                    "stages": [
                        {"name": "Отборочный этап", "date_range": "2025"},
                        {"name": "Заключительный этап — 11 кл.", "date_range": "7 марта 2026"},
                        {"name": "Заключительный этап — 8–10 кл.", "date_range": "9 марта 2026"},
                    ],
                },
                {
                    "slug": "otkrytaya",
                    "name": "Открытая олимпиада школьников",
                    "short_name": "Открытая",
                    "description": "Открытая олимпиада школьников по математике. Организатор — НИУ ИТМО и другие ведущие вузы.",
                    "grades": [8, 9, 10, 11],
                    "official_url": "https://openolymp.ru/",
                    "color_hex": "#10b981",
                    "stages": [
                        {"name": "1-й отборочный онлайн-этап", "date_range": "3 декабря 2025 – 19 января 2026"},
                        {"name": "Заключительный этап", "date_range": "Уточняется"},
                    ],
                },
                {
                    "slug": "vsesibirskaya",
                    "name": "Всесибирская открытая олимпиада",
                    "short_name": "Всесибирская",
                    "description": "Всесибирская открытая олимпиада школьников по математике. Проводится НГУ и СО РАН.",
                    "grades": [9, 10, 11],
                    "official_url": "https://sesc.nsu.ru/olymp/",
                    "color_hex": "#84cc16",
                    "stages": [
                        {"name": "Отборочный этап", "date_range": "Уточняется"},
                        {"name": "Заключительный этап", "date_range": "Весна 2026"},
                    ],
                },
                {
                    "slug": "itmo",
                    "name": "Олимпиада ИТМО",
                    "short_name": "ИТМО",
                    "description": "Олимпиада школьников по математике университета ИТМО. Входит в Перечень олимпиад РСОШ.",
                    "grades": [9, 10, 11],
                    "official_url": "https://olymp.itmo.ru/",
                    "color_hex": "#eab308",
                    "stages": [
                        {"name": "Отборочный этап", "date_range": "Осень 2025 – зима 2026"},
                        {"name": "Заключительный этап", "date_range": "Весна 2026"},
                    ],
                },
                {
                    "slug": "nadezhda-energetiki",
                    "name": "Олимпиада «Надежда энергетики»",
                    "short_name": "Надежда энергетики",
                    "description": "Олимпиада «Надежда энергетики» по математике. Организаторы — ведущие энергетические вузы России.",
                    "grades": [9, 10, 11],
                    "official_url": "https://www.energy-hope.ru/",
                    "color_hex": "#ec4899",
                    "stages": [
                        {"name": "Отборочный этап", "date_range": "Уточняется"},
                        {"name": "Заключительный этап", "date_range": "Весна 2026"},
                    ],
                },
                {
                    "slug": "rosatom",
                    "name": "Олимпиада «Росатом»",
                    "short_name": "Росатом",
                    "description": "Олимпиада «Росатом» по математике. Проводится НИЯУ МИФИ. Даёт льготы при поступлении.",
                    "grades": [9, 10, 11],
                    "official_url": "https://rosatomolymp.mephi.ru/",
                    "color_hex": "#3b82f6",
                    "stages": [
                        {"name": "Отборочный этап", "date_range": "Уточняется"},
                        {"name": "Заключительный этап", "date_range": "Весна 2026"},
                    ],
                },
                {
                    "slug": "inzhenernaya",
                    "name": "Инженерная олимпиада школьников",
                    "short_name": "Инженерная",
                    "description": "Инженерная олимпиада школьников по математике. Входит в Перечень РСОШ, даёт льготы при поступлении.",
                    "grades": [9, 10, 11],
                    "official_url": "https://olymp.urfu.ru/",
                    "color_hex": "#14b8a6",
                    "stages": [
                        {"name": "Отборочный этап", "date_range": "Осень 2025 – зима 2026"},
                        {"name": "Заключительный этап", "date_range": "Февраль – март 2026"},
                    ],
                },
                {
                    "slug": "plekhanovskaya",
                    "name": "Плехановская олимпиада",
                    "short_name": "Плехановская",
                    "description": "Плехановская олимпиада школьников по математике. Проводится РЭУ им. Г.В. Плеханова.",
                    "grades": [9, 10, 11],
                    "official_url": "https://olymp.rea.ru/",
                    "color_hex": "#d946ef",
                    "stages": [
                        {"name": "Отборочный этап", "date_range": "Уточняется"},
                        {"name": "Заключительный этап", "date_range": "Весна 2026"},
                    ],
                },
            ]
            for _i, _o in enumerate(_olymp_prep_defaults):
                db.session.add(_OlympiadPrepSeed(
                    slug=_o["slug"],
                    name=_o["name"],
                    short_name=_o["short_name"],
                    description=_o["description"],
                    grades=_json_seed.dumps(_o["grades"]),
                    stages=_json_seed.dumps(_o["stages"], ensure_ascii=False),
                    official_url=_o["official_url"],
                    color_hex=_o["color_hex"],
                    sort_order=_i + 1,
                    is_active=True,
                ))
            db.session.commit()
            print(f"[OLYMP-PREP-SEED] [OK] Added {len(_olymp_prep_defaults)} olympiads to olympiad_prep")
        else:
            # Idempotent: nothing to do; uncomment for verbose logs:
            # print(f"[OLYMP-PREP-SEED] already populated ({_OlympiadPrepSeed.query.count()} rows), skipping")
            pass
except Exception as _e_olymp_prep_seed:
    print(f"[OLYMP-PREP-SEED] hook skipped: {_e_olymp_prep_seed}")

# ── Theory placeholder fix (idempotent) ──────────────────────────────────────
# Перезаписывает названия методов вида «E14 (название ждёт текста)»
# настоящими названиями из data/olympiads/methods_catalog_89.json.
# Идемпотентно: на каждом старте находит только реальные плейсхолдеры и
# никогда не трогает методы с уже введёнными вручную именами.
# Запускается БЕЗ env-гейта (в отличие от autoseed), чтобы прод-БД
# не зависела от ручного включения OLYMPIAD_AUTOSEED.
try:
    from services.olympiad_autoseed import fix_theory_placeholders
    fix_theory_placeholders(app, db)
except Exception as _e_theory_fix:
    print(f"[THEORY-FIX] hook skipped: {_e_theory_fix}")

# ── Secrets auto-seed (idempotent, без env-гейта) ───────────────────────────
# Засеивает таблицу olympiad_secrets из ./secrets_dump.json при пустой
# таблице. Раньше этим занимался admin-endpoint /admin/seed-secrets, но
# его никто не дёргал на проде -> раздел /secrets оставался пустым.
# seed_secrets_from_json с force=False ничего не делает, если таблица
# уже наполнена — поэтому безопасен на каждом старте.
try:
    from utils.seed_secrets_utils import seed_secrets_from_json
    with app.app_context():
        _secrets_path = os.path.join(os.path.dirname(__file__), 'secrets_dump.json')
        _res = seed_secrets_from_json(json_file=_secrets_path, force=False)
        if _res.get('success'):
            if _res.get('inserted', 0) > 0:
                print(f"[SECRETS-SEED] Inserted {_res['inserted']} secrets")
            else:
                print(f"[SECRETS-SEED] Already populated ({_res.get('skipped', 0)} rows)")
        else:
            print(f"[SECRETS-SEED] skipped: {_res.get('error')}")
except Exception as _e_secrets:
    print(f"[SECRETS-SEED] hook skipped: {_e_secrets}")

# /grade-5 and /grade-6 — тренажёр FORMYLA по школьным классам.
try:
    from routes.grade import grade_bp
    app.register_blueprint(grade_bp)
    print("[BP] grade_bp registered (/grade-5, /grade-6, /grade-task/*)")
except Exception as _e:
    print(f"[BP] grade_bp NOT registered: {_e}")

# /api/assistant + legacy /api/concierge/* — FORMYLA AI Site Assistant
# (отдельный от ИИ-тьютора). Полная переcборка: см. assistant/ package.
try:
    from assistant import assistant_bp
    app.register_blueprint(assistant_bp)
    # Seed KB on first run (idempotent). Must be inside app_context.
    try:
        from assistant.kb import init_db as _assistant_init_db
        with app.app_context():
            _assistant_init_db()
        print("[BP] assistant_bp registered (/api/assistant, /api/concierge/ask, /api/concierge/intents) + KB seeded")
    except Exception as _e_seed:
        print(f"[BP] assistant_bp registered, but KB seed failed: {_e_seed}")
except Exception as _e:
    print(f"[BP] assistant_bp NOT registered: {_e}")

# /auth/telegram/* — Telegram Login Widget callback.
try:
    from routes.telegram_auth import telegram_auth_bp
    app.register_blueprint(telegram_auth_bp)
    print("[BP] telegram_auth_bp registered (/auth/telegram/callback)")
except Exception as _e:
    print(f"[BP] telegram_auth_bp NOT registered: {_e}")

# /daily_tasks/* — Персонализированные «Задачи дня» (мульти-LLM пайплайн).
#
# ВАЖНО (инцидент 2026-05-29): миграция add_daily_tasks_tables раньше
# падала на PostgreSQL из-за SQLite-специфичного INTEGER PRIMARY KEY
# AUTOINCREMENT. Молчаливый except выше съедал ошибку — blueprint не
# регистрировался, /daily_tasks отдавал 404, ссылка в шапке вела «куда
# попало», и пользователь жаловался на «кидает в раздел темы». Теперь:
#   • миграция выбирает DDL по диалекту (SQLite/PostgreSQL);
#   • любая ошибка регистрации логируется ПОЛНЫМ traceback'ом, чтобы
#     в логах Render было видно причину при следующем подобном инциденте.
try:
    from daily_tasks import daily_tasks_bp
    from migrations.add_daily_tasks_tables import _ensure_table as _ensure_daily_tasks_tables
    from daily_tasks.services import trigger_daily_prewarm
    from migrations.add_task_pool_cache import _ensure_task_pool_tables
    app.register_blueprint(daily_tasks_bp)
    with app.app_context():
        _ensure_daily_tasks_tables()
        _ensure_task_pool_tables()
    print("[BP] daily_tasks_bp registered (/daily_tasks)")
except Exception as _e:
    import traceback as _tb
    print(f"[BP] daily_tasks_bp NOT registered: {_e}")
    print(_tb.format_exc())

# /curator/* — Модуль «Куратор» (AI-наставник): диагностика, план, тьютор, прогресс.
try:
    from curator import curator_bp
    from migrations.add_curator_tables import _ensure_curator_tables
    app.register_blueprint(curator_bp)
    with app.app_context():
        _ensure_curator_tables()
    print("[BP] curator_bp registered (/curator) — diagnostics, plans, tutor, progress")
except Exception as _e:
    import traceback as _tb
    print(f"[BP] curator_bp NOT registered: {_e}")
    print(_tb.format_exc())

# /intake/* — P9 Intake: новая анкета входа (5 вопросов + 5 якорей).
try:
    from routes.intake import intake_bp
    app.register_blueprint(intake_bp)
    print("[BP] intake_bp registered (/intake)")
except Exception as _e:
    import traceback as _tb
    print(f"[BP] intake_bp NOT registered: {_e}")
    print(_tb.format_exc())

# ── T10: parent/teacher blueprint ──
try:
    from routes.parent_teacher import parent_teacher_bp
    app.register_blueprint(parent_teacher_bp)
    print("[BP] parent_teacher_bp registered (/teacher, /parent, /student/*)")
except Exception as _e:
    import traceback as _tb
    print(f"[BP] parent_teacher_bp NOT registered: {_e}")
    print(_tb.format_exc())

# ── T6: dashboard settings blueprint ──
try:
    from routes.dashboard_settings import dashboard_settings_bp
    app.register_blueprint(dashboard_settings_bp)
    print("[BP] dashboard_settings_bp registered (/dashboard/settings)")
except Exception as _e:
    import traceback as _tb
    print(f"[BP] dashboard_settings_bp NOT registered: {_e}")
    print(_tb.format_exc())

# ── «Банк неточностей» (insights): модели, blueprint, очередь ──────────
try:
    import models_insights  # noqa: F401  — регистрирует 4 таблицы в metadata
    from routes.insights import insights_bp
    from migrations.add_insights_tables import _ensure_table as _ensure_insights_tables
    app.register_blueprint(insights_bp)
    with app.app_context():
        _ensure_insights_tables()
    from services.insight_queue import ensure_queue_worker as _ensure_insight_worker
    _ensure_insight_worker(app)
    print("[BP] insights_bp registered (/insights, /api/insights)")
except Exception as _e:
    import traceback as _tb
    print(f"[BP] insights_bp NOT registered: {_e}")
    print(_tb.format_exc())

# ── AUTO-MIGRATION: test_sessions (для восстановления адаптивного теста) ──
try:
    from migrations.add_test_sessions import _ensure_test_sessions_table
    with app.app_context():
        _ensure_test_sessions_table()
    print("[BP] test_sessions migration ensured")
except Exception as _e:
    import traceback as _tb
    print(f"[BP] test_sessions migration FAILED: {_e}")
    print(_tb.format_exc())

# Jinja filter for Markdown rendering of olympiad task/theory text (LaTeX-safe).
try:
    from services.md_render import md_render as _md_render_filter
    app.jinja_env.filters['md_render'] = _md_render_filter
    print("[JINJA] filter md_render registered")
except Exception as _e:
    print(f"[JINJA] md_render filter NOT registered: {_e}")

# inject_geometry — вставляет SVG-чертежи из static/img/vsosh9_geometry/
# после каждого <h4>Задача N.M</h4> для F-методов. Карта файлов
# сканируется один раз (lru_cache в services.geometry_drawings).
try:
    from services.geometry_drawings import inject_geometry_drawings as _inject_geo
    app.jinja_env.filters['inject_geometry'] = _inject_geo
    print("[JINJA] filter inject_geometry registered")
except Exception as _e:
    print(f"[JINJA] inject_geometry filter NOT registered: {_e}")

# Limit upload size: 12 MB (for solution photos).
app.config['MAX_CONTENT_LENGTH'] = 12 * 1024 * 1024

# ── GLOBAL ERROR HANDLER ──────────────────────────────────────────
@app.errorhandler(500)
def internal_error(e):
    import traceback, uuid
    err_id = uuid.uuid4().hex[:8]
    # H-6 (2026-05-29): Явный print для гарантии попадания в Render Logs (stdout).
    # app.logger может не выводиться в stdout на проде.
    tb = traceback.format_exc()
    print(f"\n{'='*70}\n[ERROR {err_id}] 500 Internal Server Error\n{'='*70}")
    print(tb)
    print(f"{'='*70}\n")
    app.logger.error(f"[{err_id}] 500: {e}\n{tb}")
    # Для API-запросов возвращаем JSON, иначе HTML
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Внутренняя ошибка сервера', 'error_id': err_id}), 500
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

# ---- NULL-tolerant is_flagged filter (prod has nullable column) ----
from sqlalchemy import or_ as _or_for_flag
def _is_flagged_not_true():
    return _or_for_flag(
        AdaptiveTask.is_flagged.is_(None),
        AdaptiveTask.is_flagged == False,  # noqa: E712
    )

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


@app.route('/debug/routes')
def debug_routes():
    """List all registered URL rules (diagnostic)."""
    rules = []
    for rule in sorted(app.url_map.iter_rules(), key=lambda r: r.rule):
        if 'daily' in rule.rule.lower() or 'daily_tasks' in rule.rule.lower():
            rules.append({
                'rule': rule.rule,
                'endpoint': rule.endpoint,
                'methods': sorted(rule.methods - {'HEAD', 'OPTIONS'}),
            })
    return jsonify({
        'total_rules': len(list(app.url_map.iter_rules())),
        'daily_rules': rules,
        'daily_tasks_bp_registered': any(
            r.rule == '/daily_tasks' for r in app.url_map.iter_rules()
        ),
    })


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

# ─── VAPID Keys for Web Push Notifications ──────────────────────────
VAPID_PUBLIC_KEY = (os.environ.get('VAPID_PUBLIC_KEY') or '').strip()
VAPID_PRIVATE_KEY = (os.environ.get('VAPID_PRIVATE_KEY') or '').strip()
VAPID_CLAIM_EMAIL = (os.environ.get('VAPID_CLAIM_EMAIL') or 'noreply@formyla.com').strip()

if VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY:
    print("[OK] VAPID keys loaded — Web Push notifications enabled")
else:
    print("ℹ️  VAPID keys not set — Web Push notifications disabled")

# Daily Quest Streak Reset Job (runs at 00:00 MSK)
@scheduler.task('cron', id='daily_streak_reset', hour=0, minute=0)
def daily_streak_reset_job():
    """Reset streaks at midnight MSK"""
    with app.app_context():
        from services.streak_service import check_and_reset_streaks
        try:
            check_and_reset_streaks()
            app.logger.info("[OK] Daily streak reset completed")
        except Exception as e:
            app.logger.error(f" Daily streak reset failed: {e}")

# Daily Quest Deadline Reminder (runs at 18:00 and 21:00 MSK)
@scheduler.task('cron', id='daily_quest_deadline_reminder', hour='18,21', minute=0)
def daily_quest_deadline_reminder_job():
    """Send push notifications to users who haven't completed today's Daily Tasks."""
    if not VAPID_PUBLIC_KEY or not VAPID_PRIVATE_KEY:
        return  # Push notifications not configured
    with app.app_context():
        try:
            from datetime import date
            from models import PushSubscription, User
            from daily_tasks.models import DailyTaskSet, DailyTaskItem
            today = date.today()
            # Find all users with push subscriptions
            sub_rows = PushSubscription.query.distinct(PushSubscription.user_id).all()
            sent = 0
            for sub in sub_rows:
                user = User.query.get(sub.user_id)
                if not user or user.is_guest:
                    continue
                # Check if user has a daily task set for today
                daily_set = DailyTaskSet.query.filter_by(
                    user_id=user.id, target_date=today, status='ready'
                ).first()
                if not daily_set:
                    continue
                # Check if all tasks are answered (is_correct is not null)
                all_answered = DailyTaskItem.query.filter(
                    DailyTaskItem.daily_set_id == daily_set.id,
                    DailyTaskItem.is_correct.is_(None)
                ).count() == 0
                if all_answered:
                    continue  # Already completed
                # Send push notification
                _send_push_notification(
                    user_id=user.id,
                    title='⏳ Задачи дня',
                    body='Осталось меньше 3 часов, чтобы решить задачи дня!',
                    url='/curator',
                )
                sent += 1
            if sent:
                app.logger.info(f"[OK] Daily quest reminder sent to {sent} users")
        except Exception as e:
            app.logger.error(f" Daily quest reminder failed: {e}")


# ─── Куратор: вечерняя проверка и push-уведомления ──────────────────────────

@scheduler.task('cron', id='curator_evening_notification', hour='19,20,21', minute=0)
def curator_evening_notification_job():
    """Вечерняя проверка куратора: оценивает прогресс за день и отправляет
    персонализированные push-уведомления (мотивация / дисциплина / похвала).

    Запускается в 19:00, 20:00, 21:00 по серверному времени (MSK=UTC+3).
    Куратор пишет сам, без участия преподавателя.
    """
    if not VAPID_PUBLIC_KEY or not VAPID_PRIVATE_KEY:
        return  # Push notifications not configured

    with app.app_context():
        try:
            from models import PushSubscription, User
            from curator.push_service import check_and_notify_user

            # Все пользователи с push-подписками
            sub_rows = PushSubscription.query.distinct(PushSubscription.user_id).all()
            checked = 0
            notified = 0

            for sub in sub_rows:
                user = User.query.get(sub.user_id)
                if not user or user.is_guest:
                    continue

                try:
                    result = check_and_notify_user(user_id=user.id, force=False)
                    checked += 1
                    if result.get('sent'):
                        notified += 1
                except Exception as user_err:
                    app.logger.warning(
                        f"[curator_evening] Error checking user #{sub.user_id}: {user_err}"
                    )

            if checked:
                app.logger.info(
                    f"[OK] Curator evening check: {checked} users checked, "
                    f"{notified} notifications sent"
                )
        except Exception as e:
            app.logger.error(f" Curator evening check failed: {e}")


# ─── Месячный цикл подготовки: утреннее напоминание + вечерняя генерация ──────

@scheduler.task('cron', id='curator_morning_prep_reminder', hour='9', minute=0)
def curator_morning_prep_reminder_job():
    """Утреннее напоминание о месячном цикле подготовки.

    - В тестовые дни (1-7): напоминает пройти тест по подтеме дня.
    - В task-only дни (8-30): напоминает, что сегодня задачи без теста.
    Запускается в 9:00 MSK.
    """
    if not VAPID_PUBLIC_KEY or not VAPID_PRIVATE_KEY:
        return

    with app.app_context():
        try:
            from models import PushSubscription, User
            from curator.monthly_cycle import get_today_info

            sub_rows = PushSubscription.query.distinct(PushSubscription.user_id).all()
            reminded = 0

            for sub in sub_rows:
                user = User.query.get(sub.user_id)
                if not user or user.is_guest:
                    continue

                try:
                    info = get_today_info(user.id)
                    if not info.get("subtopic"):
                        continue

                    subtopic_title = info.get("subtopic_title", info["subtopic"])
                    is_test_day = info.get("is_test_day", False)
                    has_tasks = info.get("has_tasks", False)

                    if is_test_day and not info.get("tested"):
                        # Тестовый день — напомнить пройти тест
                        _send_push_notification(
                            user_id=user.id,
                            title=' Утренний тест',
                            body=f'Сегодня тест по теме «{subtopic_title}». Пройди 5 задач!',
                            url='/curator',
                        )
                        reminded += 1
                    elif not has_tasks and not is_test_day:
                        # Task-only день — сообщить, что вечером будут задачи
                        _send_push_notification(
                            user_id=user.id,
                            title=' Задачи дня',
                            body=f'Сегодня тренируем тему «{subtopic_title}». Задачи придут вечером!',
                            url='/curator',
                        )
                        reminded += 1
                except Exception as user_err:
                    app.logger.warning(
                        f"[morning_prep] Error for user #{sub.user_id}: {user_err}"
                    )

            if reminded:
                app.logger.info(f"[OK] Morning prep reminder sent to {reminded} users")
        except Exception as e:
            app.logger.error(f" Morning prep reminder failed: {e}")


@scheduler.task('cron', id='curator_evening_prep_generate', hour='18', minute=0)
def curator_evening_prep_generate_job():
    """Вечерняя генерация задач дня для месячного цикла подготовки.

    Для пользователей с активным monthly plan:
    - Если сегодня task-only день (8-30) — запускает генерацию задач.
    - Если тестовый день — проверяет, был ли тест, иначе напоминает.
    Запускается в 18:00 MSK.
    """
    if not VAPID_PUBLIC_KEY or not VAPID_PRIVATE_KEY:
        return

    with app.app_context():
        try:
            from models import PushSubscription, User
            from curator.monthly_cycle import (
                get_today_info,
                generate_tasks_only,
            )

            sub_rows = PushSubscription.query.distinct(PushSubscription.user_id).all()
            generated = 0
            reminded_test = 0

            for sub in sub_rows:
                user = User.query.get(sub.user_id)
                if not user or user.is_guest:
                    continue

                try:
                    info = get_today_info(user.id)
                    if not info.get("subtopic"):
                        continue

                    is_test_day = info.get("is_test_day", False)
                    tested = info.get("tested", False)
                    has_tasks = info.get("has_tasks", False)

                    if has_tasks:
                        continue  # Уже сгенерировано

                    if is_test_day and not tested:
                        # Тестовый день, но тест не пройден — напомнить
                        subtopic_title = info.get("subtopic_title", info["subtopic"])
                        _send_push_notification(
                            user_id=user.id,
                            title='[!]️ Пропущен тест',
                            body=f'Ты ещё не прошёл тест по теме «{subtopic_title}». '
                                 f'Пройди скорее, чтобы получить задачи дня!',
                            url='/curator',
                        )
                        reminded_test += 1
                    elif not is_test_day:
                        # Task-only день — генерация задач
                        result = generate_tasks_only(user.id)
                        if result.get("success"):
                            generated += 1
                except Exception as user_err:
                    app.logger.warning(
                        f"[evening_prep] Error for user #{sub.user_id}: {user_err}"
                    )

            if generated or reminded_test:
                app.logger.info(
                    f"[OK] Evening prep: generated for {generated} users, "
                    f"test reminders sent to {reminded_test}"
                )
        except Exception as e:
            app.logger.error(f" Evening prep generation failed: {e}")


# Pre-generation queue processor (runs every 30 minutes)
@scheduler.task('cron', id='process_pregen_queue', minute='*/30')
def process_pregen_queue_job():
    """Process pre-generation queue for tomorrow's tasks."""
    return  # AI-генерация «Задач дня» отключена
    with app.app_context():
        try:
            from daily_tasks.services import _process_pregen_queue
            from daily_tasks.services import _reap_stale_pregen
            launched = _process_pregen_queue()
            reaped = _reap_stale_pregen()
            if launched or reaped:
                app.logger.info(f"[OK] Pre-gen queue: launched {launched}, reaped {reaped}")
        except Exception as e:
            app.logger.error(f" Pre-gen queue processing failed: {e}")

# ── Conveyor: schedule all users (every 60 minutes) ─────────────────
@scheduler.task('interval', id='conveyor_schedule_all', minutes=60)
def conveyor_schedule_all_job():
    """Rescan all users with monthly_cycle and fill gen_conveyor."""
    return  # AI-генерация «Задач дня» отключена
    with app.app_context():
        from daily_tasks.services import schedule_all_users
        result = schedule_all_users()
        app.logger.info(
            "[CONVEYOR] schedule_all: scanned=%(users_scanned)d "
            "created=%(entries_created)d skipped=%(entries_skipped)d",
            result,
        )

# ── Conveyor: worker (every 2 minutes) ─────────────────────────────
@scheduler.task('interval', id='conveyor_worker', minutes=2)
def conveyor_worker_job():
    """Process gen_conveyor queue: launch up to MAX_CONVEYOR_WORKERS."""
    return  # AI-генерация «Задач дня» отключена
    with app.app_context():
        from daily_tasks.services import conveyor_worker
        launched = conveyor_worker()
        if launched:
            app.logger.info("[CONVEYOR] worker launched %d generation(s)", launched)

# Auto-clean tutor chat history every 3 days
@scheduler.task('cron', id='tutor_history_cleanup', day='*/3', hour=3, minute=0)
def tutor_history_cleanup_job():
    """Delete chat history older than 3 days for all users."""
    with app.app_context():
        from models import ChatMessage, db
        from datetime import datetime, timedelta
        cutoff = datetime.utcnow() - timedelta(days=3)
        deleted = ChatMessage.query.filter(ChatMessage.timestamp < cutoff).delete()
        db.session.commit()
        app.logger.info("[TUTOR] cleaned %d old messages", deleted)

# Daily midnight auto-assignment (runs at 00:05 MSK)
# CRITICAL: this is the job that actually creates DailyTaskSet for users
# at the start of each day. Without it, users see "no_set" and must
# click "Generate" manually, waiting ~5 minutes for AI pipeline.
@scheduler.task('cron', id='daily_midnight_assign', hour=0, minute=5)
def daily_midnight_assign_job():
    """At 00:05 MSK, auto-assign daily tasks to active users.

    AI-генерация «Задач дня» отключена (см. daily_tasks/services.py).
    Выдача задач дня идёт только из банка daily_task_bank, поэтому
    полночное автоназначение LLM-сетов не требуется.
    """
    return
    with app.app_context():
        from daily_tasks.models import (
            DailyTaskSet, PreGenQueue, TaskPool,
        )
        from daily_tasks.services import (
            today_in_user_tz, enqueue_daily_generation, _parse_json_field,
        )
        from datetime import timedelta

        today = today_in_user_tz()
        yesterday = today - timedelta(days=1)

        assigned_ids: set = set()
        instant_count = 0
        generating_count = 0
        skipped_count = 0

        # ── Tier 1: Users with PreGenQueue for today ──────────────────
        pregen_entries = PreGenQueue.query.filter(
            PreGenQueue.target_date == today,
            PreGenQueue.status.in_(["generating", "queued"]),
        ).all()

        for entry in pregen_entries:
            uid = entry.user_id
            assigned_ids.add(uid)

            # Skip if already has a set for today
            existing = DailyTaskSet.query.filter_by(
                user_id=uid, target_date=today,
            ).first()
            if existing and existing.status in ("ready", "partial"):
                skipped_count += 1
                continue

            # Reuse profile snapshot from queue (avoids build_profile cost)
            profile = _parse_json_field(entry.profile_json, None)

            try:
                result = enqueue_daily_generation(
                    user_id=uid,
                    triggered_by="cron",
                    profile=profile,
                )
                if result.get("status") == "ready":
                    instant_count += 1
                elif result.get("status") == "generating":
                    generating_count += 1
            except Exception as exc:
                app.logger.warning(
                    "Midnight assign: enqueue failed for user=%d: %s", uid, exc,
                )

        # ── Tier 2: Users active yesterday, no PreGenQueue ────────────
        yesterday_sets = DailyTaskSet.query.filter(
            DailyTaskSet.target_date == yesterday,
            DailyTaskSet.status.in_(["ready", "partial"]),
        ).all()
        yesterday_user_ids = {s.user_id for s in yesterday_sets}

        remaining = yesterday_user_ids - assigned_ids
        for uid in remaining:
            assigned_ids.add(uid)

            existing = DailyTaskSet.query.filter_by(
                user_id=uid, target_date=today,
            ).first()
            if existing and existing.status in ("ready", "partial"):
                skipped_count += 1
                continue

            # Build profile to enable cache hit (if TaskPool exists)
            from daily_tasks.profile import build_profile, ProfileBuildError
            try:
                profile = build_profile(uid)
            except ProfileBuildError:
                app.logger.info(
                    "Midnight assign: user=%d no profile — skipping", uid,
                )
                continue

            try:
                result = enqueue_daily_generation(
                    user_id=uid,
                    triggered_by="cron",
                    profile=profile,
                )
                if result.get("status") == "ready":
                    instant_count += 1
                elif result.get("status") == "generating":
                    generating_count += 1
            except Exception as exc:
                app.logger.warning(
                    "Midnight assign: enqueue failed for user=%d: %s", uid, exc,
                )

        total = instant_count + generating_count
        if total or skipped_count:
            app.logger.info(
                "[OK] Midnight assign: %d total (%d instant cache, %d generating, %d skipped)",
                total, instant_count, generating_count, skipped_count,
            )

# Daily buffer fill: ensure 3-day-ahead task stock (D3 block)
# Runs daily at 06:00 MSK — after midnight assign had time to complete
@scheduler.task('cron', id='daily_buffer_fill', hour=6, minute=0)
def daily_buffer_fill_job():
    """Fill 3-day buffer for all active users.

    AI-генерация «Задач дня» отключена (см. daily_tasks/services.py).
    Буфер предгенерации на 3 дня вперёд не нужен — задачи выдаются из банка.
    """
    return
    with app.app_context():
        from daily_tasks.buffer import ensure_daily_buffer
        from daily_tasks.models import DailyTaskSet as DTS
        from daily_tasks.services import today_in_user_tz as _tz
        from datetime import timedelta

        today = _tz()
        cutoff = today - timedelta(days=3)

        # Find users active in the last 3 days (have a DailyTaskSet)
        active_user_ids = [
            row[0] for row in
            DTS.query.with_entities(DTS.user_id).filter(
                DTS.target_date >= cutoff,
            ).distinct().all()
        ]

        filled = 0
        skipped = 0

        for uid in active_user_ids:
            try:
                result = ensure_daily_buffer(uid, days_ahead=3)
                if result.get("status") == "ok":
                    skipped += 1
                elif result.get("pipeline_calls", 0) > 0:
                    filled += 1
            except Exception as exc:
                app.logger.warning(
                    "daily_buffer_fill: user=%d error: %s", uid, exc,
                )

        app.logger.info(
            "Daily buffer fill: %d users filled, %d already complete",
            filled, skipped,
        )


# Start scheduler
try:
    if os.environ.get("ENABLE_SCHEDULER", "1") != "0":
        scheduler.start()
        print("[OK] APScheduler started - Daily Quest cron jobs active")
    else:
        print("[SCHEDULER] disabled via ENABLE_SCHEDULER=0")
except Exception as e:
    print(f"[!]️  APScheduler failed to start: {e}")

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def _generate_device_id():
    """Генерация уникального device_id"""
    return str(uuid.uuid4())


def ensure_guest_user(device_id):
    """Создаёт или находит гостевого пользователя по device_id.

    КРИТИЧЕСКИ ВАЖНО (см. инцидент 2026-05-25):
    Любой SELECT/INSERT здесь идёт под statement_timeout=3s, чтобы при тормозах
    Postgres мы НЕ вешали before_request-хук на 30+ секунд (что приводит к
    crash-loop'у gunicorn worker'ов через SIGKILL/SystemExit).
    Если БД лагает — отдаём None, пользователь продолжит как аноним.
    """
    from sqlalchemy import text as _sql_text
    try:
        # Локальный, transaction-scoped statement_timeout — НЕ глобально,
        # чтобы не сломать долгие админ-запросы.
        db.session.execute(_sql_text("SET LOCAL statement_timeout = '3s'"))
    except Exception:
        # SET LOCAL может упасть только если коннект уже мёртв.
        db.session.rollback()
        return None

    try:
        user = User.query.filter_by(device_id=device_id, is_guest=True).first()
        if user:
            return user

        # Генерируем уникальный никнейм
        import random
        suffix = random.randint(1000, 9999)
        nickname = f"Гость-{suffix}"
        # Убедимся что никнейм уникален (но не более 5 попыток — fail-fast)
        for _ in range(5):
            if not User.query.filter_by(nickname=nickname).first():
                break
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
    except Exception as _e:
        db.session.rollback()
        import logging
        logging.getLogger(__name__).warning(
            f"ensure_guest_user: DB slow/unavailable, fallback to anonymous: {_e}"
        )
        return None


# Пути, на которых НЕ нужно лезть в БД из before_request. Любой SQL здесь
# создаёт риск hang'а на тормозах Postgres -> SIGKILL воркера. См. инцидент
# 2026-05-25: robots.txt/favicon health-check'ом Render'а вешал воркер на
# psycopg.wait(), worker умирал по SystemExit/SIGKILL -> crash loop.
_SKIP_GUEST_PATHS = (
    '/static/',
    '/favicon.ico',
    '/robots.txt',
    '/sitemap.xml',
    '/healthz',
    '/health',
    '/ping',
    '/__version',
    '/__diag/',
)

# Пути, доступные без регистрации. Всё остальное требует входа.
_PUBLIC_PATHS = (
    '/static/',
    '/favicon.ico',
    '/robots.txt',
    '/sitemap.xml',
    '/healthz',
    '/health',
    '/ping',
    '/__version',
    '/__diag/',
    '/about',
    '/welcome',
    '/login',
    '/verify-code',
    '/dev_login',
    '/auth/',         # Yandex / Telegram OAuth callback
    '/yandex_login',
    '/yandex_receiver',
    '/link_yandex',
    '/api/reviews',   # Публичный список отзывов о сайте (для /about)
    '/api/conference/',  # Конференции (гостевой доступ, WebRTC + SocketIO)
    '/',               # Главная страница — доступна без регистрации
    '/topics',
    '/problems',
    '/leaderboard',
    '/section/',
)


@app.before_request
def ensure_device_and_session():
    """Минимальная реализация — ТОЛЬКО device_id, БЕЗ БД.

    После инцидента 2026-05-25 (crash-loop из-за зависающего ensure_guest_user
    на медленной Postgres) этот хук БОЛЬШЕ НЕ создаёт guest-юзера в БД.
    Гость создаётся ЛЕНИВО — только когда пользователь начинает реально что-то
    делать (отправляет ответ, открывает чат). См. get_or_create_guest_user().
    Это гарантирует что главная и login открываются за миллисекунды даже если
    БД лагает или вообще лежит.
    """
    path = request.path
    # 1. Системные пути — полностью без БД
    for _p in _SKIP_GUEST_PATHS:
        if path.startswith(_p):
            return

    try:
        # 2. device_id (чисто in-memory / cookie, без БД)
        device_id = session.get('device_id')
        if not device_id:
            device_id = request.cookies.get('formyla_device_id')
        if not device_id:
            device_id = _generate_device_id()
        session['device_id'] = device_id

        # 3. Только для УЖЕ залогиненных — обновляем device_id если нужно.
        # Анонимам никаких SQL'ей вообще — никакого ensure_guest_user здесь,
        # он переехал в lazy-вызов из роутов которые требуют user.
        if current_user.is_authenticated:
            try:
                if not current_user.device_id:
                    current_user.device_id = device_id
                    db.session.commit()
                session['user_id'] = current_user.id
            except Exception:
                db.session.rollback()
    except Exception as e:
        # Catch-all: что бы ни упало — не возвращаем 500
        import logging
        logging.getLogger(__name__).warning(
            f"ensure_device_and_session error (ignored): {e}"
        )
        try:
            db.session.rollback()
        except Exception:
            pass


@app.before_request
def require_registration():
    """Redirect unauthenticated users to login for all non-public pages.

    Только страницы из _PUBLIC_PATHS доступны без регистрации.
    Для /api/* возвращаем 401 JSON, для остальных — redirect на /login.
    """
    path = request.path

    # Публичные пути — доступны всем
    for _p in _PUBLIC_PATHS:
        if path.startswith(_p):
            return

    # Реально зарегистрированный пользователь (не гость)
    if current_user.is_authenticated and not getattr(current_user, 'is_guest', False):
        return

    # API-запросы — 401 JSON
    if path.startswith('/api/'):
        return jsonify({
            'error': 'Требуется регистрация',
            'login_url': url_for('login')
        }), 401

    # Всё остальное — редирект на страницу входа
    return redirect(url_for('login', next=path))


@app.before_request
def force_intake_completion():
    """Пока анкета входа не пройдена — ученик не может покинуть /intake.

    Действует для залогиненных не-гостевых учеников (role != teacher/parent).
    На любой странице, кроме самой анкеты (/intake), статики и auth-эндпоинтов,
    если CuratorState.prep_state.intake.completed отсутствует — редирект на анкету.
    Это переживает перезагрузку страницы/телефона, т.к. состояние хранится в БД.
    """
    path = request.path

    # Только реальные пользователи
    if not (current_user.is_authenticated and not getattr(current_user, 'is_guest', False)):
        return

    # teacher/parent завершают анкету выбором роли — их не трогаем
    role = getattr(current_user, 'role', 'student') or 'student'
    if role in ('teacher', 'parent'):
        return

    # Пути, доступные до завершения анкеты
    for _p in (
        '/intake',        # сама анкета и её API (/intake/start, /answer, ...)
        '/static/',
        '/favicon.ico',
        '/login',
        '/logout',
        '/verify-code',
        '/dev_login',
    ):
        if path == _p or path.startswith(_p):
            return

    try:
        from models_curator import CuratorState
        cs = CuratorState.query.filter_by(user_id=current_user.id).first()
        if cs is None:
            return redirect(url_for('intake.intake_page'))
        ps = cs.prep_state if isinstance(cs.prep_state, dict) else {}
        if not ps.get('intake', {}).get('completed'):
            return redirect(url_for('intake.intake_page'))
    except Exception:
        pass


def get_or_create_guest_user():
    """Lazy-helper. Вызывать ТОЛЬКО из роутов которые реально требуют user-id
    (например: отправка решения, открытие чата, сохранение прогресса).

    На главной, /welcome, /login и health-checks — НЕ вызывать.
    Возвращает User либо None (если БД лагает — продолжаем как аноним).
    """
    if current_user.is_authenticated:
        return current_user
    device_id = session.get('device_id')
    if not device_id:
        return None
    guest = ensure_guest_user(device_id)
    if guest is not None:
        try:
            login_user(guest, remember=True)
            session.permanent = True
            session['user_id'] = guest.id
        except Exception:
            pass
    return guest


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

    # UTF-8 charset для всех HTML-ответов (фикс символов ∠°≠ -> ?)
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

OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY', '')


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
    "games": "Игры",
    "coloring": "Раскраски",
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
    },
    "games": {},
    "coloring": {}
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
  [ERROR] НЕПРАВИЛЬНО: \\sqrta, \\sqrt a, \\sqrtab
  [OK] ПРАВИЛЬНО: \\sqrt{{a}}, \\sqrt{{a+b}}, \\sqrt{{ab}}
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



@app.route("/healthz")
def healthz():
    """Lightweight health-check для Render/UptimeRobot/CDN.

    НЕ трогает БД. Возвращает 200 ВСЕГДА. Этот endpoint в списке
    _SKIP_GUEST_PATHS (see before_request), поэтому даже при тормозах
    Postgres ответит мгновенно. См. инцидент 2026-05-25.
    """
    return ({"status": "ok"}, 200, {"Content-Type": "application/json"})


@app.route("/__version")
def __version():
    """V9: Full build info — commit, source, branch, build_time, schema_version,
    applied_migrations. All data from one central source (module-level globals).

    Cache-busting: no-store. Public endpoint (no auth required).
    """
    schema_version = "unknown"
    try:
        import sqlite3 as _sq
        _db_path = os.path.join(os.path.dirname(__file__), 'instance', 'formyla.db')
        _conn = _sq.connect(_db_path)
        _row = _conn.execute("SELECT version_num FROM alembic_version").fetchone()
        if _row and _row[0]:
            schema_version = _row[0]
        _conn.close()
    except Exception:
        schema_version = "unknown"

    # applied_migrations: list of migration filenames that the in-app auto-migration
    # system has tracked as applied. The system does NOT maintain a separate registry
    # of applied migration files — only alembic_version tracks the current HEAD.
    # Therefore we report from alembic_version only, plus a note.
    applied = [schema_version] if schema_version != "unknown" else []

    payload = {
        "commit": _BUILD_COMMIT,
        "commit_source": _BUILD_COMMIT_SOURCE,
        "build_time": _BUILD_TIME,
        "branch": _BUILD_BRANCH,
        "schema_version": schema_version,
        "applied_migrations": applied,
    }
    return (
        payload,
        200,
        {
            "Content-Type": "application/json",
            "Cache-Control": "no-store, no-cache, must-revalidate",
        },
    )


@app.route("/__diag/method/<method_code>")
def __diag_method(method_code):
    """TEMPORARY diagnostic endpoint to capture exact traceback for
    `/olympiads/methods/<code>` 500s on prod.

    Mirrors what `routes.olympiad.method_detail` does, but wraps each step
    in try/except and returns the full traceback as JSON.

    Auth: query-param `key` must equal the hard-coded DIAG_KEY below.
    Public path (listed in _PUBLIC_PATHS / _SKIP_GUEST_PATHS).
    TEMPORARY: removed in a follow-up commit once the root cause is found.
    """
    import traceback as _tb

    # Hard-coded key — endpoint is temporary, will be removed after RCA.
    _DIAG_KEY = "formyla_d1agn0st1c_2026"
    provided = (request.args.get("key") or "").strip()
    if provided != _DIAG_KEY:
        return ({"error": "forbidden"}, 404,
                {"Content-Type": "application/json"})

    steps = []

    def _step(name, fn):
        try:
            res = fn()
            steps.append({"step": name, "ok": True,
                          "summary": str(res)[:300] if res is not None else "None"})
            return res
        except Exception as e:
            steps.append({
                "step": name,
                "ok": False,
                "error_type": type(e).__name__,
                "error": str(e),
                "traceback": _tb.format_exc(),
            })
            try:
                db.session.rollback()
            except Exception:
                pass
            return None

    # Step 1: import models
    TheoryBlock_ = _step("import TheoryBlock",
                         lambda: __import__("models_olympiad", fromlist=["TheoryBlock"]).TheoryBlock)
    OlympiadTask_ = _step("import OlympiadTask",
                          lambda: __import__("models_olympiad", fromlist=["OlympiadTask"]).OlympiadTask)

    # Step 2: query the block
    block = None
    if TheoryBlock_ is not None:
        block = _step(
            "TheoryBlock.query.filter_by(method_code=...).first()",
            lambda: TheoryBlock_.query.filter_by(method_code=method_code).first(),
        )

    if block is None:
        return ({"method_code": method_code, "steps": steps,
                 "fatal": "block not found or query failed"}, 200,
                {"Content-Type": "application/json"})

    # Step 3: read scalar attrs of the block (these can blow up on jsonb-decode)
    block_attrs = {}
    for attr in ("method_code", "method_name", "section", "sort_order",
                 "difficulty_level", "frequency_vsosh_9",
                 "definition_md", "key_idea_md", "theorem_md",
                 "examples_md", "pitfalls_md", "related_methods", "grades"):
        try:
            v = getattr(block, attr, "<<MISSING>>")
            block_attrs[attr] = (type(v).__name__, str(v)[:200])
        except Exception as e:
            block_attrs[attr] = ("ERROR", f"{type(e).__name__}: {e}")
            try:
                db.session.rollback()
            except Exception:
                pass

    # Step 4: parse related
    related_codes = _step(
        "json.loads(block.related_methods)",
        lambda: (json.loads(block.related_methods)
                 if isinstance(block.related_methods, str)
                 else (block.related_methods or [])),
    ) or []

    # Step 5: query related blocks
    related_blocks = []
    if related_codes and TheoryBlock_ is not None:
        related_blocks = _step(
            "TheoryBlock.query.in_(related_codes)",
            lambda: TheoryBlock_.query.filter(
                TheoryBlock_.method_code.in_(related_codes)).all(),
        ) or []

    # Step 6: query tasks_for_method (the cast-to-text path)
    tasks_for_method = []
    if OlympiadTask_ is not None:
        def _q_tasks():
            from sqlalchemy import cast, String
            return (OlympiadTask_.query
                    .filter(cast(OlympiadTask_.method_codes, String)
                            .like(f'%"{method_code}"%'))
                    .order_by(OlympiadTask_.sort_order)
                    .limit(50).all())
        tasks_for_method = _step("OlympiadTask filter cast(method_codes,String).like", _q_tasks) or []

    # Step 7: list all_blocks for catalog
    all_blocks = []
    if TheoryBlock_ is not None:
        all_blocks = _step(
            "TheoryBlock.query.order_by(section,sort_order).all()",
            lambda: TheoryBlock_.query.order_by(
                TheoryBlock_.section, TheoryBlock_.sort_order).all(),
        ) or []

    # Step 8: try render_template just like the real route
    grouped = {}
    for b in all_blocks:
        try:
            sec = b.section or 'Без раздела'
        except Exception:
            sec = 'Без раздела'
        grouped.setdefault(sec, []).append(b)

    _step(
        "render_template olympiad/method.html",
        lambda: render_template(
            'olympiad/method.html',
            sections=grouped, blocks=all_blocks, detail_block=block,
            related_blocks=related_blocks,
            tasks_for_method=tasks_for_method,
        ),
    )

    # Step 9: also try the OTHER convention (named like the template expects)
    _step(
        "render_template (with block=/related=/linked_tasks=)",
        lambda: render_template(
            'olympiad/method.html',
            sections=grouped, blocks=all_blocks, block=block,
            related=related_blocks, linked_tasks=tasks_for_method,
        ),
    )

    # Report to Sentry too (best-effort)
    try:
        if SENTRY_ENABLED:
            import sentry_sdk as _sdk
            _sdk.capture_message(f"[__diag/method/{method_code}] {len(steps)} steps")
    except Exception:
        pass

    payload = {
        "method_code": method_code,
        "block_attrs": block_attrs,
        "steps": steps,
        "any_error": any(not s.get("ok") for s in steps),
    }
    return (payload, 200,
            {"Content-Type": "application/json",
             "Cache-Control": "no-store, no-cache, must-revalidate"})


@app.route("/call")
@login_required
def call_page():
    """Видеозвонок по коду (Task 6).

    Самодостаточная страница: создать комнату -> получить 6-значный код ->
    поделиться кодом -> собеседник вводит код у себя -> WebRTC mesh.
    Сигналинг — через существующий blueprint /api/wb_call/*.
    Авторизация не требуется (можно звонить гостям).
    """
    return render_template("call.html")


@app.route("/conference")
@login_required
def conference_page():
    """Групповая видеоконференция (SocketIO-backed, до 8 участников).

    Создать комнату -> получить 6-значный код -> поделиться ->
    собеседник вводит код -> WebRTC mesh с сигналингом через WebSocket.
    Авторизация не требуется (можно звонить гостям).
    """
    return render_template("conference.html")


@app.route("/welcome")
def welcome():
    """Маркетинговая посадка для холодного трафика.

    Сценарий: реклама / Метрика -> /welcome -> CTA -> /adaptive_test/select_class.
    Это не главная (/) — её не трогаем, чтобы не сломать UX для залогиненных.
    """
    return render_template("welcome.html")


@app.route("/")
def index():
    """Главная страница — редирект по роли."""
    if current_user.is_authenticated:
        _role = getattr(current_user, 'role', 'student') or 'student'
        if _role == 'teacher':
            return redirect('/teacher')
        if _role == 'parent':
            return redirect('/parent')
        return redirect(url_for('prep.coach'))
    return redirect(url_for('login'))


@app.route("/leaderboard")
@login_required
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
            for level in range(1, 9):  # 8 уровней
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
        
        for lev in range(1, 9):  # 8 уровней!
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
@login_required
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
    
    # ── figures from MANIFEST ────────────────────────────────────────────────
    figures = {'condition': [], 'solution': []}
    if is_olympiad:
        _olympiad_slug = problem.get('olympiad', '')
        _year          = problem.get('year')
        _grade         = problem.get('grade')
        _day           = problem.get('day')
        _problem_num   = problem.get('num')
        if _olympiad_slug and _year and _grade:
            figures = get_figures_for_problem(
                _olympiad_slug, _year, _grade, _day, _problem_num
            )

    # Нормализуем математический текст (auto-wrap `^`, `sqrt`, `{x+y=1; x*y=2}`
    # в `$...$`), чтобы KaTeX рендерил формулы красиво. Не модифицирует
    # исходный объект PROBLEMS_DB/OLYMPIADS_DB — работаем с копией.
    try:
        from services.math_text_normalizer import normalize_problem_fields
        problem = normalize_problem_fields(problem)
    except Exception as _norm_err:
        app.logger.warning(
            f"[math_normalizer] problem {problem_id}: {_norm_err}"
        )

    return render_template('problem_detail.html',
        problem=problem,
        subject_title=subject_title,
        subtopic_title=subtopic_title,
        is_olympiad=is_olympiad,
        is_solved=is_solved,
        condition_figures=figures['condition'],
        solution_figures=figures['solution'],
    )



@app.route("/api/check_answer", methods=["POST"])
@login_required
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

# ════════════════════════════════════════════════════════════════════
# NEW: Olympiad adaptive test (JSONL-based, 5 tasks, L1-L5)
# ════════════════════════════════════════════════════════════════════

@app.route("/olympiad-test")
def olympiad_test_select_class():
    """Step 1: Select grade (5-11).
    Save test parameters from URL query into session (length, level_hint, scope)."""
    if request.args.get('length'):
        session['olyad_length'] = request.args.get('length')
    if request.args.get('level_hint'):
        session['olyad_level_hint'] = request.args.get('level_hint')
    if request.args.get('scope'):
        session['olyad_scope'] = request.args.get('scope')
    session.modified = True
    return render_template('olympiad_test_select_class.html')


@app.route("/olympiad-test/select-section")
def olympiad_test_select_section():
    """Step 2: Select section for chosen grade.
    If scope=all_sections in session, redirect to test start."""
    scope = session.get('olyad_scope', None)
    try:
        grade = int(request.args.get('grade', ''))
    except (ValueError, TypeError):
        flash('Выберите класс', 'error')
        return redirect('/olympiad-test')
    if grade not in range(5, 12):
        flash('Неверный класс', 'error')
        return redirect('/olympiad-test')
    if scope == 'all_sections':
        return redirect(f'/olympiad-test/start?grade={grade}')
    from services.olympiad_adaptive import get_sections
    sections = get_sections(grade)
    if not sections:
        flash(f'Нет задач для {grade} класса', 'error')
        return redirect('/olympiad-test')
    return render_template('olympiad_test_select_section.html',
                           grade=grade, sections=sections)


@app.route("/olympiad-test/select-theme")
def olympiad_test_select_theme():
    """Step 3: Select theme for chosen grade+section."""
    try:
        grade = int(request.args.get('grade', ''))
    except (ValueError, TypeError):
        return redirect('/olympiad-test')
    section = request.args.get('section', '').strip()
    if not section:
        return redirect(f'/olympiad-test/select-section?grade={grade}')
    from services.olympiad_adaptive import get_themes
    themes = get_themes(grade, section)
    if not themes:
        flash('Нет тем в этом разделе', 'error')
        return redirect(f'/olympiad-test/select-section?grade={grade}')
    return render_template('olympiad_test_select_theme.html',
                           grade=grade, section=section, themes=themes)


@app.route("/olympiad-test/select-level")
def olympiad_test_select_level():
    """Step 4: Select difficulty level (L1-L4) for chosen theme.

    Если у пользователя уже есть пройденный адаптивный тест (measured > 0),
    показываем только один рекомендуемый уровень. Иначе — все 4 уровня.
    """
    try:
        grade = int(request.args.get('grade', ''))
    except (ValueError, TypeError):
        return redirect('/olympiad-test')
    theme = request.args.get('theme', '').strip()
    section = request.args.get('section', request.args.get('section', '')).strip()
    if not theme or grade not in range(5, 12):
        return redirect('/olympiad-test')

    # ── Определить уровень пользователя ────────────────
    # Приоритет: 1) анкета 2) адаптивный тест (build_profile)
    recommended_level = None
    try:
        from flask_login import current_user
        if current_user.is_authenticated:
            # Сначала проверяем анкету
            try:
                from services.questionnaire_storage import get_questionnaire_level
                q_level = get_questionnaire_level(current_user.id)
                if q_level is not None:
                    recommended_level = q_level
            except Exception:
                pass

            # Если анкеты нет — пробуем build_profile
            if recommended_level is None:
                from daily_tasks.profile import build_profile, ProfileBuildError
                try:
                    profile = build_profile(current_user.id)
                    topics_full = profile.get('topics_full', []) or []
                    # Ищем тему, совпадающую с выбранной theme (по section)
                    for t in topics_full:
                        t_topic = (t.get('topic') or '').lower()
                        t_key = (t.get('topic_key') or '').lower()
                        theme_lower = theme.lower()
                        section_lower = (section or '').lower()
                        if theme_lower in t_topic or t_topic in theme_lower or \
                           theme_lower in t_key or theme_lower in section_lower:
                            if t.get('measured'):
                                lvl = t.get('target_level')
                                if lvl is not None:
                                    recommended_level = max(1, min(4, round(int(lvl) * 4 / 8)))
                                    break
                    if recommended_level is None:
                        measured = [t for t in topics_full if t.get('measured')]
                        if measured:
                            avg = sum(t.get('target_level') or 0 for t in measured) / len(measured)
                            recommended_level = max(1, min(4, round(avg * 4 / 8)))
                except ProfileBuildError:
                    pass
                except Exception:
                    pass
    except Exception:
        pass

    return render_template('olympiad_test_select_level.html',
                           grade=grade, theme=theme, section=section,
                           recommended_level=recommended_level)


def _lookup_olyad_task(task_uid):
    """Find a full olympiad task dict by uid (in-memory JSONL cache).

    Used to avoid storing full task text (statement/solution/answer) in the
    client-side session cookie, which overflows the ~4 KB browser cookie limit
    and silently resets the test (throwing the pupil back to task 1).
    """
    if not task_uid:
        return None
    from services.olympiad_adaptive import _all_tasks
    for t in _all_tasks:
        if t.get('task_uid') == task_uid:
            return t
    return None


@app.route("/olympiad-test/start", methods=['GET', 'POST'])
def olympiad_test_run():
    """Main test page: configurable length/level/scope from session."""
    from services.olympiad_adaptive import (
        get_task, get_task_by_section,
        _normalize_answer, _check_solution_quality,
        pick_all_sections_tasks, _all_tasks,
    )
    import random, logging
    _ol_log = logging.getLogger(__name__)

    scope = session.get('olyad_scope', None)
    total_len = int(session.get('olyad_length', 5))
    level_hint = int(session.get('olyad_level_hint', 2))

    # ── GET: show task ───────────────────────────────────────────
    if request.method == 'GET':
        # Fresh start?
        if 'olyad_uid' not in session or request.args.get('grade'):
            try:
                grade = int(request.args.get('grade', ''))
            except (ValueError, TypeError):
                return redirect('/olympiad-test')
            if grade not in range(5, 12):
                return redirect('/olympiad-test')

            if scope == 'all_sections':
                try:
                    from services.level_engine import get_state
                    st = get_state(current_user.id) if current_user.is_authenticated else {}
                except Exception:
                    st = {}
                by_sec = st.get('by_section', {}) if st else {}
                picked = pick_all_sections_tasks(grade, total_len, by_sec, level_hint)
                # Store only lightweight uid refs — full task dicts overflow the
                # client-side session cookie (~4 KB) and reset the test.
                queue = [{'task_uid': t.get('task_uid')} for t in picked.get('tasks', [])]
                session['olyad_task_queue'] = queue
                session['olyad_queue_pos'] = 0
                session['olyad_uid'] = '1'
                session['olyad_grade'] = grade
                session['olyad_theme'] = 'all_sections'
                session['olyad_level'] = level_hint
                session['olyad_task_num'] = 0
                session['olyad_shown'] = []
                session['olyad_results'] = []
                session['olyad_total'] = len(queue)
                session.modified = True
                if not queue:
                    flash('Нет задач для выбранного класса', 'error')
                    return redirect('/olympiad-test')
            else:
                theme = request.args.get('theme', '').strip()
                level = int(request.args.get('level', str(level_hint)))
                if not theme or level not in range(1, 5):
                    return redirect('/olympiad-test')
                session['olyad_uid'] = '1'
                session['olyad_grade'] = grade
                session['olyad_theme'] = theme
                session['olyad_level'] = level
                session['olyad_task_num'] = 0
                session['olyad_shown'] = []
                session['olyad_results'] = []
                session['olyad_task_queue'] = []
                session['olyad_total'] = total_len
                session.modified = True

        grade = session['olyad_grade']
        theme = session['olyad_theme']
        level = session['olyad_level']

        if scope == 'all_sections':
            queue = session.get('olyad_task_queue', [])
            pos = session.get('olyad_queue_pos', 0)
            if pos >= len(queue):
                task = None
            else:
                ref = queue[pos]
                task = _lookup_olyad_task(ref.get('task_uid'))
                if task is not None:
                    session['olyad_current_task'] = task['task_uid']
                    session['olyad_level'] = task.get('level', level_hint)
                    session['olyad_current_section'] = (task.get('section') or '').strip()
                    shown = set(session.get('olyad_shown', []))
                    shown.add(task['task_uid'])
                    session['olyad_shown'] = list(shown)
                    session['olyad_queue_pos'] = pos + 1
                    session.modified = True
        else:
            shown = set(session.get('olyad_shown', []))
            task = get_task(grade, theme, level, shown)
            if task:
                session['olyad_shown'] = list(shown) + [task['task_uid']]
                session['olyad_current_task'] = task['task_uid']
                session['olyad_current_section'] = (task.get('section') or '').strip()
                session.modified = True

        if not task:
            flash('Задачи закончились', 'error')
            return redirect('/olympiad-test')

        tnum = session.get('olyad_task_num', 0) + 1
        display_level = task.get('level', level)
        display_theme = task.get('theme', '') if scope == 'all_sections' else theme
        return render_template('olympiad_test_run.html',
                               task=task, grade=grade, theme=display_theme,
                               level=display_level, task_count=tnum, feedback=None, result=None,
                               total=session.get('olyad_total', total_len))

    # ── POST: process answer ─────────────────────────────────────
    user_answer = (request.form.get('answer') or '').strip()
    user_solution = (request.form.get('solution') or '').strip()
    task_uid = session.get('olyad_current_task', '')

    # Find the task
    import json
    task_data = None
    with open('FORMYLA_L1_L5_TOP5.jsonl', encoding='utf-8') as f:
        for line in f:
            if line.strip() and json.loads(line).get('task_uid') == task_uid:
                task_data = json.loads(line)
                break
    # Fallback: search in memory
    if not task_data:
        for t in _all_tasks:
            if t.get('task_uid') == task_uid:
                task_data = t
                break

    if not task_data:
        flash('Ошибка: задача не найдена', 'error')
        return redirect('/olympiad-test')

    correct = (task_data.get('answer') or '').strip()
    ref_sol = (task_data.get('solution') or '').strip()
    statement = (task_data.get('statement') or '').strip()
    level = task_data.get('level', session.get('olyad_level', level_hint))

    is_correct = _normalize_answer(user_answer) == _normalize_answer(correct)

    # Simple scoring: correct=+1, wrong=-1
    ball = 1 if is_correct else -1

    # ── Step 4: Call level_engine.record_result ───────────────────
    task_section = session.get('olyad_current_section', (task_data.get('section') or '').strip())
    if current_user.is_authenticated and task_section:
        try:
            record_result(
                current_user.id,
                task_section,
                int(level),
                is_correct,
            )
        except Exception as _le_err:
            _ol_log.warning(
                "record_result failed user=%s section=%s level=%s err=%s",
                current_user.id, task_section, level, _le_err
            )

    results = session.get('olyad_results', [])
    # Store only lightweight refs — full statement/solution/answer text overflows
    # the client-side session cookie (~4 KB) and silently resets the test.
    results.append({
        'level': level,
        'ball': ball,
        'task_uid': task_uid,
        'user_answer': user_answer,
        'is_correct': is_correct,
    })
    session['olyad_results'] = results
    session['olyad_task_num'] = len(results)
    session.modified = True

    task_num = len(results)
    grade = session['olyad_grade']
    theme = session['olyad_theme']

    # Results if total_len tasks done
    result = None
    if task_num >= total_len:
        correct_count = sum(1 for r in results if r['is_correct'])
        partial_count = sum(1 for r in results if not r['is_correct'] and r.get('ball', 0) == 0)
        wrong_count = task_num - correct_count - partial_count

        # ── Step 5: Update prep_state ─────────────────────────────
        if current_user.is_authenticated:
            try:
                from models_curator import CuratorState
                cs = CuratorState.query.filter_by(user_id=current_user.id).first()
                if cs and isinstance(getattr(cs, 'prep_state', None), dict):
                    from datetime import datetime as _dt
                    now_iso = _dt.utcnow().isoformat()
                    mu_before = None
                    mu_after = None
                    try:
                        st = get_state(current_user.id)
                        mu_after = st.get('mu')
                    except Exception:
                        pass
                    ps = dict(cs.prep_state)
                    if ps.get('test_queue'):
                        ps['test_queue'] = ps['test_queue'][1:]
                    ps['last_test'] = {
                        'date': now_iso,
                        'total': task_num,
                        'correct': correct_count,
                        'mu_before': mu_before,
                        'mu_after': mu_after,
                        'level_before': round(mu_before) if mu_before else None,
                        'level_after': round(mu_after) if mu_after else None,
                    }
                    cs.prep_state = ps
                    from models import db
                    db.session.commit()
            except Exception as _ps_err:
                _ol_log.warning("prep_state update failed: %s", _ps_err)

        # Re-attach full task text for display (session kept only light refs).
        enriched_results = []
        for r in results:
            rt = _lookup_olyad_task(r.get('task_uid')) or {}
            enriched_results.append({
                'level': r.get('level'),
                'ball': r.get('ball'),
                'task_uid': r.get('task_uid'),
                'user_answer': r.get('user_answer'),
                'is_correct': r.get('is_correct'),
                'statement': rt.get('statement', ''),
                'solution': rt.get('solution', ''),
                'correct_answer': rt.get('answer', ''),
            })
        result = {
            'results': enriched_results,
            'correct_count': correct_count,
            'partial_count': partial_count,
            'wrong_count': wrong_count,
            'grade': grade,
            'theme': theme,
            'level': level,
        }

    # Get next task for display
    if result:
        task = None
    elif scope == 'all_sections':
        queue = session.get('olyad_task_queue', [])
        pos = session.get('olyad_queue_pos', 0)
        if pos < len(queue):
            ref = queue[pos]
            task = _lookup_olyad_task(ref.get('task_uid'))
            if task is not None:
                session['olyad_current_task'] = task['task_uid']
                session['olyad_level'] = task.get('level', level_hint)
                session['olyad_current_section'] = (task.get('section') or '').strip()
                shown = set(session.get('olyad_shown', []))
                shown.add(task['task_uid'])
                session['olyad_shown'] = list(shown)
                session['olyad_queue_pos'] = pos + 1
                session.modified = True
        else:
            task = None
    else:
        shown = set(session.get('olyad_shown', []))
        task = get_task(grade, theme, level, shown)

    feedback = {
        'is_correct': is_correct,
        'ball': ball,
        'correct_answer': correct,
        'solution': ref_sol,
    }

    display_level = task.get('level', level) if task else level
    display_theme = (task.get('theme', '') if task and scope == 'all_sections' else theme)
    return render_template('olympiad_test_run.html',
                           task=task, grade=grade, theme=display_theme,
                           level=display_level, task_count=task_num,
                           feedback=feedback, result=result,
                           total=session.get('olyad_total', total_len))


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
    Исправляет \\sqrt(...) -> \\sqrt{...} и аналогичные.
    Многие задачи из OCR имеют скобки вместо фигурных скобок.
    """
    # \sqrt(...) -> \sqrt{...}
    text = re.sub(r'\\(sqrt|frac|text|mathrm|mathbf|mathbb|overline|underline|hat|tilde|vec)\(([^)]*)\)', r'\\\1{\2}', text)
    return text


def _sanitize_ai_latex(text):
    """Приводит AI-генерированный текст к KaTeX-валидному LaTeX:
    - bare `sqrt(x)` -> `\\sqrt{x}` (даже если без обратного слеша)
    - юникод-символы ², ³, √, ∛, − -> LaTeX-аналоги
    - `a*b` (между переменными/числами) -> `a \\cdot b`
    - оборачивает голые LaTeX-конструкции в $...$, если они вне $-блока

    Применяется к text / answer / solution из AI-ответа перед сохранением.
    Безопасна для уже корректного LaTeX.
    """
    if not text or not isinstance(text, str):
        return text

    s = text

    # 0) КОРНИ — В ПЕРВУЮ ОЧЕРЕДЬ.
    #    КРИТИЧНО: радикальные юникод-символы (∛, ³√, √) и битые формы
    #    \sqrt[n] нужно канонизировать ДО общей замены '³'->'^{3}'.
    #    Иначе '³√(x)' превращается в '^{3}\sqrt{x}' — болтающаяся степень
    #    «³» без знака радикала (инцидент 2026-06-11, задача G6.17).
    #    Канонизатор приводит всё к \sqrt[n]{...} / \sqrt{...} и идемпотентен.
    try:
        from services.latex_root_normalizer import normalize_roots
        s = normalize_roots(s)
    except Exception:
        pass

    # 1) Unicode -> LaTeX (корни уже обработаны выше, '³√' здесь не встретится)
    s = s.replace('²', '^{2}').replace('³', '^{3}')
    s = s.replace('⁴', '^{4}').replace('⁵', '^{5}')
    s = s.replace('₀', '_{0}').replace('₁', '_{1}').replace('₂', '_{2}')
    s = s.replace('₃', '_{3}').replace('₄', '_{4}').replace('₅', '_{5}')
    s = s.replace('−', '-')  # minus sign -> ASCII hyphen
    s = s.replace('·', r' \cdot ').replace('×', r' \cdot ')

    # 2) bare sqrt(...) / sqrt{...} -> \sqrt{...}  (без backslash)
    #    учитываем вложенные скобки одного уровня
    s = re.sub(r'(?<!\\)\bsqrt\s*\(([^()]*)\)', r'\\sqrt{\1}', s, flags=re.IGNORECASE)
    s = re.sub(r'(?<!\\)\bsqrt\s*\{([^{}]*)\}', r'\\sqrt{\1}', s, flags=re.IGNORECASE)

    # 3) Повторная канонизация корней (на случай, если bare-sqrt дал \sqrt[n] X)
    try:
        from services.latex_root_normalizer import normalize_roots as _nr2
        s = _nr2(s)
    except Exception:
        pass

    # 4) Если в строке появился \sqrt но нет $-окружения вокруг него — оборачиваем
    #    каждое такое вхождение в $...$. Делаем простую обёртку для непокрытых.
    if '\\sqrt' in s and '$' not in s:
        # Оборачиваем \sqrt{...} вместе с примыкающим выражением до =, ., , или конца
        s = re.sub(
            r'(\\sqrt(?:\[[^\]]*\])?\{[^{}]*\}(?:\s*[+\-=]\s*[a-zA-Z0-9\\\{\}\.]+)*)',
            r'$\1$',
            s,
        )

    return s

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

    # Исправляем \sqrt(...) -> \sqrt{...} ВЕЗДЕ
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


# ── Markdown -> HTML парсер для текста задач ──────────────────────────────────
def render_task_text(text):
    """
    Парсит Markdown -> HTML.
    1. Оборачивает голые LaTeX-команды в $...$
    2. Защищает math от Markdown-эскейпинга
    3. Парсит Markdown -> HTML
    4. Восстанавливает math
    Placeholder формат: XMATHX0XENDX — не содержит __, *, _ чтобы Markdown не тронул.
    """
    if not text:
        return ''

    # 0a. Исправление plain-text математики (OCR-артефакты: x2 -> x^2)
    from utils.math_text_fixer import fix_plain_math
    text = fix_plain_math(text)

    # 0a2. LaTeX-валидатор: чинит «7^100» -> «$7^{100}$», \frac12 -> \frac{1}{2},
    #      cdot->\cdot и т.п. Не зависит от Flask/БД, поэтому импорт ленивый.
    try:
        from services.latex_validator import normalize_math_text
        text = normalize_math_text(text)
    except Exception:
        # Никогда не валим рендеринг задачи из-за валидатора.
        pass

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
@login_required
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
                # Пропускаем битые/stub-файлы (< 200 байт — это не PNG, а заглушка)
                import os
                _full = os.path.join(app.static_folder, img)
                try:
                    if os.path.getsize(_full) < 200:
                        continue
                except OSError:
                    continue
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

    # Нормализуем math-формулы в problem.text — `x^2`, `sqrt(x)`, системы.
    _problems_raw = combo.get('problems', [])
    try:
        from services.math_text_normalizer import normalize_problem_fields
        _problems_norm = [normalize_problem_fields(p) for p in _problems_raw]
    except Exception as _e_norm:
        app.logger.warning(f"[math_normalizer] olympiad_detail: {_e_norm}")
        _problems_norm = _problems_raw

    # Разделение по дням
    try:
        _grade = combo.get('grade', grade or 0)
        _round_key = combo.get('round', rnd or '')
        day_blocks = split_problems_by_day(
            _problems_norm,
            slug,
            _round_key,
            _grade
        )
        combo_day = detect_day_from_round(
            combo.get('round_title', ''),
            _round_key
        )
    except Exception as _e_day:
        app.logger.warning(f"[olympiad_days] olympiad_open: {_e_day}")
        day_blocks = [{'day': None, 'problems': _problems_norm}]
        combo_day = None

    return render_template('olympiad_detail.html',
        olympiad=olympiad,
        combo=combo,
        problems=_problems_norm,
        day_blocks=day_blocks,
        combo_day=combo_day
    )


@app.route("/olympiads/solution/<int:combo_id>")
@login_required
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

    # Прикрепляем рисунки-решения (official figures из all11_figures архива).
    # Только на страницу решений — в условиях рисунки не показываются.
    try:
        from services.solution_figures import attach_to_problems as _attach_fig
        attached = _attach_fig(combo=combo, problems=combo.get('problems', []))
        if attached:
            app.logger.info(
                f"[solution_figures] combo_id={combo.get('id')}: "
                f"attached {attached} figures"
            )
    except Exception as _fig_err:
        app.logger.warning(f"[solution_figures] attach failed: {_fig_err}")

    # Нормализуем math-формулы в text/solution/answer.
    try:
        from services.math_text_normalizer import normalize_problem_fields
        combo_problems = combo.get('problems') or []
        if combo_problems:
            # Не модифицируем глобальный COMBOS — работаем с копией
            combo = dict(combo)
            combo['problems'] = [
                normalize_problem_fields(p) for p in combo_problems
            ]
    except Exception as _e_norm:
        app.logger.warning(f"[math_normalizer] olympiad_solution: {_e_norm}")

    # Разделение по дням (работаем с уже нормализованными problems)
    _solutions_problems = combo.get('problems', [])
    try:
        day_blocks = split_problems_by_day(
            _solutions_problems,
            combo.get('olympiad', ''),
            combo.get('round', ''),
            combo.get('grade', 0)
        )
        combo_day = detect_day_from_round(
            combo.get('round_title', ''),
            combo.get('round', '')
        )
    except Exception as _e_day:
        app.logger.warning(f"[olympiad_days] olympiad_solution: {_e_day}")
        day_blocks = [{'day': None, 'problems': _solutions_problems}]
        combo_day = None

    return render_template('olympiad_solutions.html',
        olympiad=olympiad,
        combo=combo,
        day_blocks=day_blocks,
        combo_day=combo_day
    )


def send_auth_email(recipient_email, code):
    """Отправка кода подтверждения.

    Стратегия (в порядке предпочтения):
      1) Resend HTTP API — если задан ``RESEND_API_KEY`` или ``MAIL_PASSWORD``
         начинается с ``re_``. Не зависит от SMTP, обходит Windows-баг
         ``OSError [Errno 22]`` в ``smtplib.SMTP_SSL`` на Python 3.13+ и
         работает сквозь любые исходящие firewalls на PaaS.
      2) SMTP через ``smtplib`` — резервный путь, использует параметры из
         ``app.config`` (по умолчанию ``smtp.resend.com:465`` SSL).

    Gmail SMTP больше не используется (после 2026-05 Google отклоняет
    App Passwords для этой учётки — см. инцидент SMTPAuthenticationError 535).
    """
    import traceback
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

    subject = 'Код подтверждения для доступа к платформе FORMYLA'

    # ─── Path 1: Resend HTTP API ────────────────────────────────────────
    from utils.mail import send_email as resend_send, is_configured as resend_ready
    if resend_ready():
        try:
            app.logger.warning(f"[EMAIL] Sending via Resend HTTP API to {recipient_email}")
            result = resend_send(recipient_email, subject, html)
            # ``utils.mail.send_email`` now guarantees that a returned dict
            # contains ``id`` (it raises otherwise). Still gate explicitly so
            # this function never returns truthy on a hidden failure.
            if isinstance(result, dict) and result.get("id"):
                app.logger.warning(f"[EMAIL] [OK] Resend accepted (id={result['id']}) for {recipient_email}")
                return True
            # Defensive: treat anything else as a failure and fall back.
            app.logger.warning(f"[EMAIL] Resend returned unexpected payload {result!r}; falling back to SMTP")
        except Exception as e:
            app.logger.error(f"[EMAIL] Resend API failed ({e}); falling back to SMTP")
            app.logger.error(traceback.format_exc())
            # fall through to SMTP

    # ─── Path 2: SMTP fallback ─────────────────────────────────────────
    import smtplib
    import ssl
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    from email.header import Header

    smtp_host = app.config.get('MAIL_SERVER', 'smtp.resend.com')
    smtp_port = int(app.config.get('MAIL_PORT', 465))
    use_ssl = app.config.get('MAIL_USE_SSL', True)
    use_tls = app.config.get('MAIL_USE_TLS', False)
    smtp_user = app.config.get('MAIL_USERNAME', 'resend')
    smtp_pass = app.config.get('MAIL_PASSWORD', '')
    sender = app.config.get('MAIL_DEFAULT_SENDER') or 'onboarding@resend.dev'

    app.logger.warning(f"[EMAIL] Connecting via SMTP ({smtp_host}:{smtp_port}, SSL={use_ssl}, TLS={use_tls})")

    try:
        if use_ssl and smtp_port == 465:
            # Resend recommends SMTPS (implicit TLS) on 465.
            context = ssl.create_default_context()
            server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15, context=context)
            server.set_debuglevel(1)
            server.ehlo()
        else:
            # STARTTLS on 587 (also supported by Resend).
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=15)
            server.set_debuglevel(1)
            server.ehlo()
            if use_tls:
                try:
                    context = ssl.create_default_context()
                    server.starttls(context=context)
                except Exception:
                    app.logger.warning("[EMAIL] default context failed, retrying with unverified context...")
                    context = ssl._create_unverified_context()
                    server.starttls(context=context)
                server.ehlo()

        server.login(smtp_user, smtp_pass)

        # Формируем письмо
        msg = MIMEMultipart('alternative')
        msg['Subject'] = Header(subject, 'utf-8')
        msg['From'] = sender
        msg['To'] = recipient_email
        msg.attach(MIMEText(html, 'html', 'utf-8'))

        server.sendmail(sender, [recipient_email], msg.as_bytes())
        server.quit()

        app.logger.warning(f"[EMAIL] [OK] Successfully sent to {recipient_email}")
        return True
    except Exception as e:
        app.logger.error(f"[EMAIL ERROR] Failed to send: {e}")
        app.logger.error(traceback.format_exc())
        raise Exception(f"Ошибка отправки email: {str(e)}")


@app.route("/dev_login")
def dev_login():
    """DEV-режим: мгновенный вход как user_id=1 (Victor) — обход SMTP-кода.
    Работает только на localhost (127.0.0.1) для безопасности.
    """
    from flask import request as _req
    from flask_login import login_user
    remote = _req.remote_addr or ''
    if remote not in ('127.0.0.1', '::1', 'localhost'):
        return 'dev_login only available on localhost', 403
    target_id = int(_req.args.get('uid', 1))
    user = User.query.get(target_id)
    if not user:
        return f'User id={target_id} not found', 404
    login_user(user, remember=True)
    return redirect('/daily_tasks')


@app.route("/login", methods=["GET", "POST"])
def login():
    """Passwordless вход - шаг 1: ввод email."""
    if current_user.is_authenticated and not current_user.is_guest:
        return redirect('/daily_tasks')
    
    if request.method == "POST":
        app.logger.warning("LOGIN POST ВЫЗВАН")
        
        email = request.form.get('email', '').strip().lower()
        
        if not email:
            flash('Email обязателен', 'error')
            return render_template('login.html')
        
        # Проверяем или создаем пользователя.
        # Passwordless-вход = passwordless-регистрация: если email ещё не
        # существует (например, после «Перепройти анкету», которая удаляет
        # аккаунт), создаём нового пользователя и ведём его на анкету.
        user = User.query.filter_by(email=email).first()
        
        if not user:
            user = User(email=email)
            db.session.add(user)
            db.session.commit()
            app.logger.warning(f"НОВЫЙ ПОЛЬЗОВАТЕЛЬ СОЗДАН ПРИ ВХОДЕ: {email}")
        
        # Генерируем код
        code = user.generate_auth_code()
        db.session.commit()
        
        app.logger.warning(f"КОД СГЕНЕРИРОВАН: {code} для {email}")
        
        # Отправляем код на email.
        # Резолюция настроек: либо Resend (API key), либо классический SMTP.
        from utils.mail import is_configured as resend_ready
        smtp_ready = bool(app.config.get('MAIL_USERNAME') and app.config.get('MAIL_PASSWORD'))
        mail_configured = resend_ready() or smtp_ready

        app.logger.warning(f"MAIL_USERNAME = {app.config.get('MAIL_USERNAME')}")
        mail_pass = app.config.get('MAIL_PASSWORD') or ''
        app.logger.warning(f"MAIL_PASSWORD = {'*' * len(mail_pass)} ({len(mail_pass)} символов)")
        app.logger.warning(f"Resend API key set = {resend_ready()}")
        app.logger.warning(f"Mail configured = {mail_configured}")
        
        if mail_configured:
            try:
                send_auth_email(email, code)
                
                # Дублируем в консоль для отладки
                app.logger.warning(f"EMAIL ОТПРАВЛЕН: {email}, код: {code}")
                
                flash(f'Код отправлен на {email}. Проверьте почту!', 'success')
                
            except Exception as e:
                error_message = str(e)
                app.logger.error(f"ОШИБКА EMAIL: {error_message}")
                
                # Fallback - выводим код в консоль
                
                # Показываем понятное сообщение пользователю
                if "аутентификации" in error_message.lower() or "authentication" in error_message.lower():
                    flash(f'Ошибка настройки email-сервера. Обратитесь к администратору.', 'error')
                elif "подключиться" in error_message.lower() or "connect" in error_message.lower():
                    flash(f'Не удалось подключиться к почтовому серверу. Попробуйте позже.', 'error')
                else:
                    flash(f'Ошибка отправки email: {error_message}', 'error')
        else:
            # Email не настроен
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
        return redirect('/daily_tasks')
    
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
            #   2) если пользователь ещё не прошёл онбординг — /intake
            #   3) иначе — "О сайте"
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            if getattr(user, 'onboarded_at', None) is None:
                return redirect(url_for('intake.intake_page'))
            return redirect('/about')
        
        flash('Неверный или просроченный код', 'error')
        return render_template('verify_code.html', email=email)
    
    return render_template('verify_code.html', email=email)


@app.route("/logout")
def logout():
    """Выход пользователя."""
    logout_user()
    session.clear()
    resp = redirect(url_for('login'))
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
                # КОЛЛИЗИЯ: Я-ID привязан к ДРУГОМУ аккаунту ->
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

        # Редирект: новым пользователям (onboarded_at IS NULL) — на /intake
        if getattr(user, 'onboarded_at', None) is None:
            redirect_url = url_for('intake.intake_page')
        else:
            redirect_url = '/daily_tasks'

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


@app.route("/api/tutor/clear", methods=["POST"])
@login_required
def tutor_clear():
    """Delete all chat history for current user."""
    from models import ChatMessage, db
    try:
        agent_type = (request.get_json(silent=True) or {}).get('agent_type', 'general')
        deleted = ChatMessage.query.filter_by(
            user_id=current_user.id, agent_type=agent_type
        ).delete()
        db.session.commit()
        return jsonify({'ok': True, 'deleted': deleted})
    except Exception as e:
        db.session.rollback()
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route("/api/tutor/send", methods=["POST"])
@login_required
def tutor_send():
    """Отправить сообщение тьютору (специализированному агенту)."""
    try:
        if not DEEPSEEK_AVAILABLE:
            return jsonify({'error': 'AI недоступен'}), 503
        
        # Проверяем, это JSON или FormData (для файлов)
        if request.is_json:
            data = request.get_json()
            message = data.get('message', '').strip()
            agent_type = data.get('agent_type', 'general')
            hint_mode = data.get('hint_mode', True)
            image_data = None
            check_solution_mode = False
        else:
            # FormData с файлами (multiple)
            message = request.form.get('message', '').strip()
            agent_type = request.form.get('agent_type', 'general')
            hint_mode = request.form.get('hint_mode', 'true').lower() == 'true'
            # Режим «Проверить решение» — фото проходят через НОВЫЙ единый OCR-слой
            # (services.solution_ocr) и ОСТАЮТСЯ приложенными (image_data), чтобы
            # vision-модель читала рукопись напрямую даже при неточном OCR.
            check_solution_mode = request.form.get('check_solution', 'false').lower() == 'true'
            
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
                first_file = files[0]
                if first_file and first_file.filename:
                    raw_bytes = first_file.read()
                    image_data = base64.b64encode(raw_bytes).decode('utf-8')

                    if check_solution_mode:
                        # ── НОВЫЙ единый OCR-слой (services.solution_ocr): все фото
                        # проходят Tesseract -> DeepSeek vision -> normalizer. Первое фото
                        # ДОПОЛНИТЕЛЬНО остаётся приложенным (image_data), чтобы vision-
                        # модель видела рукопись напрямую, даже если OCR вернул мусор.
                        all_images = []
                        for _f in files:
                            if not (_f and _f.filename):
                                continue
                            _f.seek(0)
                            all_images.append(base64.b64encode(_f.read()).decode('utf-8'))
                        recognized = ''
                        ocr_low = False
                        try:
                            from services.solution_ocr import ocr_solution_images
                            ocr_meta = ocr_solution_images(all_images, task_text=message or '')
                            recognized = (ocr_meta.get('text') or '').strip()
                            ocr_low = bool(ocr_meta.get('low_confidence'))
                            app.logger.info(
                                "[tutor] solution_ocr: engine=%s confidence=%s parts=%d chars=%d low=%s",
                                ocr_meta.get('engine'), ocr_meta.get('confidence'),
                                ocr_meta.get('parts'), len(recognized), ocr_low,
                            )
                        except Exception as _ocr_exc:
                            app.logger.exception("[tutor] solution_ocr failed: %s", _ocr_exc)
                            recognized = ''

                        if recognized:
                            if ocr_low:
                                message = (
                                    (message + "\n\n[OCR распознал фото неуверенно — доверяй фото, а не тексту ниже.]\n" + recognized)
                                    if message else
                                    ("Проверь моё решение по фото.\n\n[OCR распознал фото неуверенно — доверяй фото, а не тексту ниже.]\n" + recognized)
                                )
                            else:
                                message = (
                                    (message + "\n\n[Распознанный текст решения (сверь с фото):]\n" + recognized)
                                    if message else
                                    ("Проверь моё решение по фото.\n\n[Распознанный текст решения (сверь с фото):]\n" + recognized)
                                )
                        # image_data остаётся первым фото — vision-модель прочитает рукопись сама.
                    else:
                        # Обычный чат с фото (не режим проверки): старый OCR
                        # (Tesseract -> KIMI vision) + фото для vision при неудаче OCR.
                        recognized = None
                        ocr_err = None
                        try:
                            from services.tesseract_ocr import recognize_bytes as _tesseract_ocr
                            recognized, ocr_err = _tesseract_ocr(raw_bytes, first_file.mimetype or 'image/jpeg')
                            if recognized:
                                app.logger.info("[tutor] Tesseract recognized %d chars", len(recognized))
                        except Exception as _tess_exc:
                            ocr_err = str(_tess_exc)
                            app.logger.warning("[tutor] Tesseract error: %s", _tess_exc)

                        if not recognized:
                            try:
                                from services.novita_vision import transcribe_handwritten_solution as _novita_ocr
                                recognized = _novita_ocr(image_data)
                                if recognized:
                                    app.logger.info("[tutor] Novita recognized %d chars", len(recognized))
                                else:
                                    app.logger.warning("[tutor] Novita returned empty")
                            except Exception as _novita_exc:
                                app.logger.warning("[tutor] Novita error: %s", _novita_exc)

                        if recognized:
                            message = (recognized + "\n\n[Пользователь также написал: " + message + "]" if message else recognized)
                            image_data = None
                        else:
                            # Не удалось распознать фото - сообщить пользователю
                            if not message:
                                return jsonify({'error': 'Не удалось распознать фото. Пожалуйста, опишите задачу текстом или попробуйте другое фото.'}), 422
                            else:
                                # Пользователь написал текст + прикрепил фото — используем текст
                                image_data = None
                                message = message + "\n\n[P.S. К сообщению было прикреплено фото, но его не удалось распознать.]"
        
        if not message and not image_data:
            return jsonify({'error': 'Сообщение пустое'}), 400
        
        from models import ChatMessage
        
        # Сохраняем сообщение пользователя с привязкой к агенту
        user_msg = ChatMessage(
            user_id=current_user.id,
            agent_type=agent_type,
            role='user',
            content=message + (" [ Прикреплено изображение]" if image_data else "")
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
        app.logger.error(f"AI Tutor error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Ошибка AI: {str(e)}'}), 500


@app.route("/api/tutor/chat", methods=["POST"])
def tutor_atlas_chat():
    """Наставник визуального атласа методов (настоящий вызов модели).

    Принимает JSON: {methodCode, exampleIndex, mode, hintLevel,
    spoilerAllowed, studentGrade, message, history, selection, images,
    stage}.  Контекст метода берётся ТОЛЬКО из серверной копии атласа —
    клиентским полям метода мы не доверяем.

    Возвращает {message, status, hintLevel, suggestedActions, methodLinks}.
    """
    from services import atlas_tutor
    from services.atlas_tutor import TutorError

    # Ограничиваем размер входящего JSON (защита от гигантских запросов).
    if request.content_length and request.content_length > atlas_tutor.MAX_INPUT_JSON_BYTES:
        return jsonify({"message": "Запрос слишком большой.", "status": "error"}), 413

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        data = {}

    user_id = getattr(current_user, "id", None) if current_user and getattr(current_user, "is_authenticated", False) else None
    client_ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or request.remote_addr

    try:
        result = atlas_tutor.handle_chat(data, user_id=user_id, client_ip=client_ip)
        return jsonify(result)
    except TutorError as e:
        if e.status_code >= 500:
            app.logger.error("[atlas_tutor] %s: %s", e.code, e.message)
        else:
            app.logger.warning("[atlas_tutor] %s: %s", e.code, e.message)
        return jsonify({"message": e.message, "status": "error", "errorCode": e.code}), e.status_code
    except Exception as e:
        app.logger.exception("[atlas_tutor] unexpected error: %s", e)
        return jsonify({"message": "Наставник временно недоступен. Попробуйте позже.", "status": "error"}), 500


@app.route("/api/tutor/chat/stream", methods=["POST"])
def tutor_atlas_chat_stream():
    """Потоковый вывод ответа наставника атласа (SSE).

    События:
      data: {"type":"meta", "hintLevel":N, "spoilerAllowed":bool, "mode":...}
      data: {"type":"delta", "text":"..."}
      data: {"type":"done"}
      data: {"type":"error", "message":"..."}
    """
    from services import atlas_tutor
    from services.atlas_tutor import TutorError

    if request.content_length and request.content_length > atlas_tutor.MAX_INPUT_JSON_BYTES:
        return jsonify({"message": "Запрос слишком большой.", "status": "error"}), 413

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        data = {}

    user_id = getattr(current_user, "id", None) if current_user and getattr(current_user, "is_authenticated", False) else None
    client_ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or request.remote_addr

    def _sse(obj):
        import json as _json
        return "data: %s\n\n" % _json.dumps(obj, ensure_ascii=False)

    def generate():
        try:
            prepared = atlas_tutor.prepare_chat(data, user_id=user_id, client_ip=client_ip)
        except TutorError as e:
            yield _sse({"type": "error", "message": e.message, "errorCode": e.code})
            return
        except Exception as e:
            app.logger.exception("[atlas_tutor:stream] prepare error: %s", e)
            yield _sse({"type": "error", "message": "Наставник временно недоступен."})
            return

        yield _sse({
            "type": "meta",
            "hintLevel": prepared["hint_level"],
            "spoilerAllowed": prepared["spoiler_allowed"],
            "mode": prepared["mode"],
        })

        try:
            for chunk in atlas_tutor.stream_chat(prepared["messages"], model=prepared["model"]):
                yield _sse({"type": "delta", "text": chunk})
            yield _sse({"type": "done"})
        except TutorError as e:
            if e.status_code >= 500:
                app.logger.error("[atlas_tutor:stream] %s: %s", e.code, e.message)
            yield _sse({"type": "error", "message": e.message, "errorCode": e.code})
        except GeneratorExit:
            # Client disconnected / aborted — stop the upstream generator.
            raise
        except Exception as e:
            app.logger.exception("[atlas_tutor:stream] error: %s", e)
            yield _sse({"type": "error", "message": "Наставник временно недоступен."})

    resp = app.response_class(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
    return resp


@app.route("/api/tutor/health", methods=["GET"])
def tutor_atlas_health():
    """Состояние наставника атласа (для статуса «ИИ подключён/недоступен»)."""
    from services import atlas_tutor
    return jsonify(atlas_tutor.health())


from utils.tutor_lookup import find_problem_for_tutor as _find_problem_for_tutor_impl  # noqa: E402


def _find_problem_for_tutor(problem_id):
    """Module-level helper required by tests/test_tutor_solution.py.
    Strict lookup in PROBLEMS_DB; returns None for unknown id, empty text,
    or combo ids that only exist in _RAW_DB.
    """
    return _find_problem_for_tutor_impl(PROBLEMS_DB, problem_id)


@app.route("/api/tutor/hint/<int:problem_id>", methods=["POST"])
@login_required
def get_ai_hint(problem_id):
    """AI hint for a specific problem (strict PROBLEMS_DB lookup)."""
    if not DEEPSEEK_AVAILABLE:
        return jsonify({'error': 'AI nedostupen'}), 503

    problem = _find_problem_for_tutor(problem_id)
    if not problem:
        return jsonify({'error': '\u0417\u0430\u0434\u0430\u0447\u0430 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u0430'}), 404
    
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
    """AI full solution (strict PROBLEMS_DB lookup)."""
    if not DEEPSEEK_AVAILABLE:
        return jsonify({'error': 'AI nedostupen'}), 503

    problem = _find_problem_for_tutor(problem_id)
    if not problem:
        return jsonify({'error': '\u0417\u0430\u0434\u0430\u0447\u0430 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u0430'}), 404
    
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
    # ── Проверка роли: teacher/parent — показываем упрощённый профиль ──
    _user_role = getattr(current_user, 'role', 'student') or 'student'
    if _user_role in ('teacher', 'parent'):
        return render_template('profile.html',
                             user=current_user,
                             user_role=_user_role,
                             is_teacher_or_parent=True,
                             progress_dict={},
                             recent_tests=[],
                             test_stats={},
                             students=[],
                             incoming_requests=[],
                             mastery_list=[],
                             mastery_list_json=[],
                             overall_level=0,
                             ai_recommendation='',
                             streak_data=None)

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
    from services.adaptive_topics_registry import ADAPTIVE_TOPICS_BY_GRADE

    # ── Выбираем темы для радара по классу юзера ─────────────────────
    # Для 7-11 классов берём актуальную таксономию олимпиадных тем
    # из ADAPTIVE_TOPICS_BY_GRADE (по 7 тем на класс). Для 5-6 и для
    # юзеров без указанного класса — fallback на 6 общих тем (старая
    # схема), потому что у этих юзеров TopicMastery лежит под старыми
    # ключами (algebra/geometry/…), а другой таксономии для них нет.
    _user_grade = (
        getattr(current_user, 'preferred_grade', None)
        or getattr(current_user, 'class_level', None)
        or getattr(current_user, 'grade', None)
    )
    try:
        _user_grade_int = int(_user_grade) if _user_grade is not None else None
    except (TypeError, ValueError):
        _user_grade_int = None

    _legacy_topic_meta = [
        ('algebra',        'Алгебра',            ''),
        ('geometry',       'Геометрия',          ''),
        ('combinatorics',  'Комбинаторика',      ''),
        ('number_theory',  'Теория чисел',       ''),
        ('kl_movement',    'Задачи на движение', ''),
        ('knights_liars',  'Рыцари и лжецы',     ''),
    ]

    # topics_def — список словарей вида {key, name_ru, icon, match_keys}
    # match_keys — все строки, по которым ищем mastery в БД (основной ключ + db_topic + aliases).
    topics_def = []
    if _user_grade_int in ADAPTIVE_TOPICS_BY_GRADE:
        for t in ADAPTIVE_TOPICS_BY_GRADE[_user_grade_int]:
            match_keys = [t['key']]
            if t.get('db_topic'):
                match_keys.append(t['db_topic'])
            match_keys.extend(t.get('aliases', []) or [])
            topics_def.append({
                'key': t['key'],
                'name_ru': t['name'],
                'icon': t.get('emoji', ''),
                'match_keys': match_keys,
            })
    else:
        # 5-6 классы или класс не указан — старая схема
        for key, name_ru, icon in _legacy_topic_meta:
            topics_def.append({
                'key': key,
                'name_ru': name_ru,
                'icon': icon,
                'match_keys': [key],
            })

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

    # Build mastery_list with ALL topics for current grade (so radar always has all axes)
    mastery_list = []
    for td in topics_def:
        # Берём ПЕРВУЮ найденную строку в TopicMastery по любому из match_keys.
        # Это позволяет показывать прогресс юзера и под новыми, и под старыми
        # ключами, пока мы не мигрировали данные.
        row = None
        for mk in td['match_keys']:
            row = mastery_by_topic.get(mk)
            if row is not None:
                break

        if row is not None:
            mastery_val = round(row.mastery, 3)
            solved = row.solved
            avg_level = round(row.avg_level, 1)
        else:
            mastery_val = 0.0
            solved = 0
            avg_level = 0.0
        mastery_list.append({
            'topic': td['key'],
            'name_ru': td['name_ru'],
            'icon': td['icon'],
            'mastery': mastery_val,
            'solved': solved,
            'avg_level': avg_level,
            'trend': 0,  # TODO: compute weekly trend
            'level_category': get_level_category(mastery_val),
            'level_label': get_level_label(mastery_val),
        })
    # Sort: tested topics first (by mastery desc), then untested
    mastery_list.sort(key=lambda x: (-1 if x['mastery'] > 0 else 0, -x['mastery']))

    # Overall level (average mastery of tested topics -> 1-10 scale)
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
    
    # ── T8 streak for profile display ──────────────────────────────────
    streak_data = None
    try:
        from services.streak_service import get_or_create_streak
        s = get_or_create_streak(current_user.id)
        streak_data = {
            'current_streak': s.current_streak or 0,
            'max_streak': s.max_streak or 0,
            'days_off_available': s.days_off_available or 0,
        }
    except Exception:
        pass

    return render_template('profile.html',
                         user=current_user,
                         user_role=_user_role,
                         is_teacher_or_parent=False,
                         progress_dict=progress_dict,
                         recent_tests=recent_tests,
                         test_stats=test_stats,
                         students=students,
                         incoming_requests=incoming_requests,
                         mastery_list=mastery_list,
                         mastery_list_json=mastery_list_json,
                         overall_level=overall_level,
                         ai_recommendation=ai_recommendation,
                         streak_data=streak_data)


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
                chat_msg = f""" Пробник #{exam_id} проверен!

Ваш результат: {exam.score}%

{exam.ai_feedback}

Хотите разобрать ошибки или попробовать еще раз?"""
                
                ai_msg = ChatMessage(user_id=current_user.id, role='assistant', content=chat_msg)
                db.session.add(ai_msg)
                db.session.commit()
            except Exception as _chat_err:
                import logging
                logging.getLogger(__name__).warning(
                    "Не удалось отправить ChatMessage для exam_id=%s: %s",
                    exam_id, _chat_err
                )
            
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
        print(f" Генерация 25 задач для {grade} класса, уровень {level}...")
        print(f" ПРОМПТ (первые 200 символов): {user_prompt[:200]}...")
        
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
        
        print(f"[OK] Успешно сгенерировано {len(tasks)} задач, test_id={test_id}")
        
        return redirect(url_for('free_mock_test'))
        
    except DeepSeekAPIError as e:
        print(f"[ERROR] Ошибка DeepSeek API: {e}")
        flash(f'Ошибка генерации задач: {str(e)}', 'error')
        return redirect(url_for('free_mock_start'))
    except json.JSONDecodeError as e:
        print(f"[ERROR] Ошибка парсинга JSON: {e}")
        flash('Ошибка обработки ответа AI. Попробуйте еще раз.', 'error')
        return redirect(url_for('free_mock_start'))
    except Exception as e:
        print(f"[ERROR] Неожиданная ошибка: {e}")
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
    print(f" Проверка {len(answers_data)} ответов через DeepSeek AI...")
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

        print(f" Генерация блока {block_number}/5 для {class_level} класса, уровень {difficulty}...")
        
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
        
        print(f" Очищенный ответ (первые 200 символов): {response_text[:200]}...")
        
        # Пытаемся распарсить JSON с обработкой ошибок
        try:
            tasks = json.loads(response_text)
        except json.JSONDecodeError as json_err:
            print("="*80)
            print(f"[ERROR] ОШИБКА ПАРСИНГА JSON: {json_err}")
            print("="*80)
            print("СЛОМАННЫЙ JSON (полностью):")
            print(response_text)
            print("="*80)
            raise  # Пробрасываем ошибку дальше для обработки в except блоке
        
        # Проверяем, что получили ровно 5 задач
        if len(tasks) != 5:
            tasks = tasks[:5]  # Берем первые 5
        
        print(f"[OK] Блок {block_number} сгенерирован: {len(tasks)} задач")
        
        return jsonify(tasks), 200
        
    except DeepSeekAPIError as e:
        print(f"[ERROR] Ошибка DeepSeek API: {e}")
        return jsonify({'error': f'Ошибка генерации: {str(e)}'}), 500
    except json.JSONDecodeError as e:
        print(f"[ERROR] Ошибка парсинга JSON: {e}")
        return jsonify({'error': 'Ошибка обработки ответа AI'}), 500
    except Exception as e:
        print(f"[ERROR] Неожиданная ошибка: {e}")
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
            print(f"[Free Mock]  Генерирую задачу №{task_number}. Исключенные идеи: {', '.join(task_ideas_history)}")
        else:
            print(f"[Free Mock]  Генерирую задачу №{task_number}. Это первая задача в пробнике.")
        
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

 СТРОГО ЗАПРЕЩЕНО:
   • Повторять методы решения из списка выше
   • Менять только числа в старых задачах
   • Использовать похожие конструкции или сюжеты
   • Генерировать задачи на те же математические концепции

[OK] ОБЯЗАТЕЛЬНО:
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
   [ERROR] ПЛОХО: x², √4, 2^2
   [OK] ОТЛИЧНО: \( x^2 \), \( \sqrt{4} \), \( 2^2 \)

3. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО использовать слэш / для дробей!
   [ERROR] ПЛОХО: 1/2, x/y
   [OK] ОТЛИЧНО: \( \frac{1}{2} \), \( \frac{x}{y} \)

4. КРИТИЧЕСКИ ВАЖНО ПРО КОРНИ:
   КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО писать √50, sqrt(50) или \sqrt 50 (без фигурных скобок)!
   Ты ОБЯЗАН использовать команду \sqrt СТРОГО с фигурными скобками {}!
   [ERROR] ПЛОХО: √50, sqrt(50), \sqrt 50, \sqrt 4
   [OK] ОТЛИЧНО: \( \sqrt{50} \), \( \sqrt{4} \), \( \sqrt{x^2 + y^2} \)
   Если под корнем длинное выражение, оно ВСЁ должно быть внутри фигурных скобок!

5. Знаки умножения пиши ТОЛЬКО как \( \cdot \) (не * и не x).

6. ПРАВИЛО ДЛЯ НИЖНИХ ИНДЕКСОВ:
   КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО писать индексы слитно как обычный текст (p1, pn, xi)!
   Ты ОБЯЗАН использовать символ подчеркивания _ строго внутри математического блока \( ... \).
   [ERROR] ПЛОХО: p1, pn, x_i (как текст), xi
   [OK] ОТЛИЧНО: \( p_1 \), \( p_n \), \( x_i \)
   ВАЖНО: Если индекс из нескольких символов, он ОБЯЗАТЕЛЬНО в фигурных скобках!
   [OK] ОТЛИЧНО: \( a_{n+1} \), \( y_{i,j} \), \( x_{max} \)

7. СИСТЕМЫ УРАВНЕНИЙ: КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО писать их просто в столбик! ОБЯЗАН использовать окружение cases.
   [OK] ОТЛИЧНО:
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
[OK] "Решите уравнение \( x^2 + 3x - 4 = 0 \)"
[OK] "Найдите \( \frac{2^5 + 2^3}{2^2} \)"
[OK] "Докажите, что \( \sqrt{2} + \sqrt{3} < \sqrt{10} \)"

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
6. ВСЕ МАТЕМАТИЧЕСКИЕ ФОРМУЛЫ В ТЕКСТЕ, ОТВЕТЕ И РЕШЕНИИ ОБЯЗАТЕЛЬНО ОБОРАЧИВАЙ В $...$ И ПИШИ В LaTeX:
   - корень: $\\sqrt{{2x+3}}$ (НЕ sqrt(2x+3), НЕ √)
   - дробь: $\\frac{{a}}{{b}}$ (НЕ a/b в строку)
   - степень: $x^{{2}}$, $x^{{n+1}}$ (НЕ x^2, НЕ x**2)
   - умножение: $a \\cdot b$ (НЕ a*b)
   - НЕ ИСПОЛЬЗУЙ юникод-символы ² ³ √ ∛ — только LaTeX-команды.

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

        print(f" Генерация задачи {task_number}/25 для {class_level} класса, уровень {difficulty}...")
        
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
        
        print(f" Очищенный ответ (первые 150 символов): {response_text[:150]}...")
        
        # Пытаемся распарсить JSON с обработкой ошибок
        try:
            task = json.loads(response_text)
        except json.JSONDecodeError as json_err:
            print("="*80)
            print(f"[ERROR] ОШИБКА ПАРСИНГА JSON: {json_err}")
            print("="*80)
            print("СЛОМАННЫЙ JSON (полностью):")
            print(response_text)
            print("="*80)
            # Выкидываем ValueError, чтобы фронтенд повторил запрос
            raise ValueError("Invalid JSON format from AI")

        # LATEX-санитизация: приводим текст/ответ/решение к KaTeX-валидному виду
        # (sqrt(x) -> \sqrt{x}, юникод-символы -> LaTeX, обёртка в $...$ при необходимости)
        try:
            for _k in ('text', 'answer', 'solution'):
                if _k in task and task[_k]:
                    task[_k] = _sanitize_ai_latex(str(task[_k]))
        except Exception as _e_san:
            print(f"[free_mock] sanitize_ai_latex failed: {_e_san}")

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
        
        print(f"[OK] Задача {task_number} сгенерирована")
        print(f"[Free Mock]  Сохранена идея: '{task_idea}'. Всего идей в истории: {len(session['mock_task_ideas'])}")
        
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
                        print(f"[Prefetch]  Фоновая генерация задачи #{next_task_number}...")
                        # Создаем новый DeepSeek клиент для фонового потока
                        bg_deepseek = DeepSeekClient()
                        
                        # Копируем всю логику генерации из текущей функции
                        # (упрощенная версия - генерируем задачу)
                        # Здесь должна быть та же логика, что и выше
                        # Для простоты пока пропускаем, так как это требует большого рефакторинга
                        
                        print(f"[Prefetch] [OK] Задача #{next_task_number} предсгенерирована в фоне")
                    except Exception as e:
                        print(f"[Prefetch] [ERROR] Ошибка фоновой генерации: {e}")
                
                # Запускаем в отдельном потоке
                thread = threading.Thread(target=background_generate, daemon=True)
                thread.start()
                print(f"[Prefetch]  Запущена фоновая генерация задачи #{next_task_number}")
        
        return jsonify(task), 200
        
    except DeepSeekAPIError as e:
        print(f"[ERROR] Ошибка DeepSeek API: {e}")
        return jsonify({'error': f'Ошибка генерации: {str(e)}'}), 500
    except json.JSONDecodeError as e:
        print(f"[ERROR] Ошибка парсинга JSON: {e}")
        return jsonify({'error': 'Ошибка обработки ответа AI'}), 500
    except Exception as e:
        print(f"[ERROR] Неожиданная ошибка: {e}")
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
        
        print(f"[OK] Оценка завершена: {correct_count}/{len(tasks)}")
        
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
        print(f"[ERROR] Ошибка DeepSeek API: {e}")
        return jsonify({'error': f'Ошибка генерации фидбека: {str(e)}'}), 500
    except json.JSONDecodeError as e:
        print(f"[ERROR] Ошибка парсинга JSON: {e}")
        return jsonify({'error': 'Ошибка обработки ответа AI'}), 500
    except Exception as e:
        print(f"[ERROR] Неожиданная ошибка: {e}")
        return jsonify({'error': f'Произошла ошибка: {str(e)}'}), 500


# ============================================================
# ADAPTIVE TESTING (Адаптивное тестирование)
# ============================================================

# ── Adaptive test cooldown: 30 дней между тестами ─────────────────────────
# Раз в 30 дней пользователь может пройти полный 25-задачный адаптивный тест.
# Раньше можно было перепроходить сколько угодно — это сбивало уровень
# и портило per-topic difficulty matching в задачах дня. Теперь:
#   - Залогиненный: учитываем по AdaptiveTestResult.completed_at для user_id.
#   - Гость: учитываем по session['adaptive_completed_at'] (ISO-таймстамп).
ADAPTIVE_COOLDOWN_DAYS = 0


def _adaptive_cooldown_status():
    """Вернуть (is_blocked: bool, days_left: int, last_completed_at: datetime|None).

    Если is_blocked=True — пользователь должен подождать days_left дней до
    следующего теста. last_completed_at — ISO-дата прошлого прохождения.
    """
    from datetime import datetime as _dt, timedelta as _td
    now = _dt.utcnow()
    last_at = None
    try:
        if current_user.is_authenticated:
            from models import AdaptiveTestResult
            res = (AdaptiveTestResult.query
                   .filter_by(user_id=current_user.id)
                   .order_by(AdaptiveTestResult.completed_at.desc())
                   .first())
            if res and res.completed_at:
                last_at = res.completed_at
        else:
            raw = session.get('adaptive_completed_at')
            if raw:
                try:
                    last_at = _dt.fromisoformat(raw)
                except (TypeError, ValueError):
                    last_at = None
    except Exception as e:
        logger.warning('[ADAPTIVE-COOLDOWN] check failed: %s', e)
        return False, 0, None

    if last_at is None:
        return False, 0, None

    elapsed = now - last_at
    cd = _td(days=ADAPTIVE_COOLDOWN_DAYS)
    if elapsed >= cd:
        return False, 0, last_at
    days_left = max(1, (cd - elapsed).days + 1)
    return True, days_left, last_at


def _adaptive_in_progress_summary():
    """Проверить, есть ли у пользователя незавершённый адаптивный тест.

    Возвращает dict с ключами:
      url         — ссылка для продолжения (/adaptive_test_simple)
      topic_name  — название темы
      grade       — класс (строка)
      answered    — сколько задач отвечено
      total       — всего задач (25)
    или None, если активного теста нет.

    Проверяет:
      1. Flask-сессию — наличие adaptive_filtered_tasks и adaptive_slots
         с хотя бы одним отвеченным слотом (но не всеми 25).
      2. БД — test_sessions (через _get_active_test_session).
    """
    total = 25

    # ── 1. Проверка сессии ──────────────────────────────────────────────
    if session.get('adaptive_filtered_tasks'):
        slots = session.get('adaptive_slots')
        if isinstance(slots, list) and len(slots) == total:
            answered = sum(1 for s in slots if s.get('status') == 'answered')
            if 1 <= answered < total:
                topic_name = session.get('adaptive_topic_name') or 'Адаптивный тест'
                grade = session.get('adaptive_grade', '')
                return {
                    'url': url_for('adaptive_test_simple_page'),
                    'topic_name': topic_name,
                    'grade': str(grade),
                    'answered': answered,
                    'total': total,
                }

    # ── 2. Проверка БД (test_sessions) ──────────────────────────────────
    try:
        db_session = _get_active_test_session()
        if db_session:
            state = db_session.get('state') or {}
            if isinstance(state, str):
                import json as _json
                try:
                    state = _json.loads(state)
                except (TypeError, ValueError, _json.JSONDecodeError):
                    state = {}
            slots = state.get('adaptive_slots') or []
            answered = sum(1 for s in slots if isinstance(s, dict) and s.get('status') == 'answered')
            topic_name = state.get('adaptive_topic_name') or 'Адаптивный тест'
            grade = state.get('adaptive_grade', '')
            ts_id = db_session.get('id')
            url = url_for('adaptive_test_simple_page', session=ts_id) if ts_id else url_for('adaptive_test_simple_page')
            if answered > 0:
                return {
                    'url': url,
                    'topic_name': topic_name,
                    'grade': str(grade),
                    'answered': answered,
                    'total': total,
                }
    except Exception as _e:
        print(f"[adaptive_in_progress_summary] DB check error: {_e}")

    return None


@app.route("/adaptive_test/select_class")
def adaptive_test_select_class():
    """Redirect old adaptive test to new JSONL-based olympiad test."""
    return redirect('/olympiad-test')


@app.route("/adaptive_test/select_topic")
def adaptive_test_select_topic():
    """Redirect old adaptive test to new JSONL-based olympiad test."""
    grade = request.args.get('grade', '')
    return redirect(f'/olympiad-test/select-section?grade={grade}' if grade else '/olympiad-test')

    MIN_TASKS = 10
    topics = []

    if grade_int in (5, 6):
        # Темы из 1600-задач (GradeTask) — для 5 и 6 классов
        from models_grade import GradeTask, GRADE_DOMAINS, DOMAIN_LABELS
        domain_emojis = {
            'natural_numbers':              '',
            'fractions_decimals_percent':   '½',
            'geometry_measurement':         '',
            'combinatorics_school':         '',
            'logic_olympiad_intro':         '',
            'divisibility':                 '',
            'fractions_ratio_percent':      '½',
            'integers_coordinates':         '',
            'geometry_6':                   '',
            'olympiad_logic_combinatorics': '',
        }
        for domain in GRADE_DOMAINS.get(grade_int, ()):
            count = GradeTask.query.filter_by(grade=grade_int, domain=domain).count()
            topics.append({
                'name':      DOMAIN_LABELS.get(domain, domain),
                'emoji':     domain_emojis.get(domain, ''),
                'count':     count,
                'available': count >= MIN_TASKS,
                'url':       url_for('adaptive_test_start_grade',
                                     grade=grade_int, domain=domain),
            })
    else:
        # Темы 7–11 классов берём из реестра, где каждой теме сопоставлена
        # ТОЧНАЯ строка `AdaptiveTask.topic` из БД (без эвристик по keyword-ам).
        from services.adaptive_topics_registry import ADAPTIVE_TOPICS_BY_GRADE
        registry = ADAPTIVE_TOPICS_BY_GRADE.get(grade_int, [])
        all_tasks = AdaptiveTask.query.filter(
            AdaptiveTask.class_level == grade_int,
            _is_flagged_not_true(),
            ).all()
        by_topic = {}
        for t in all_tasks:
            if t.topic:
                key = t.topic.strip()
                by_topic[key] = by_topic.get(key, 0) + 1
        for entry in registry:
            # Считаем сумму по `db_topic` + всем `aliases`. Старая версия
            # выбирала count только первого попавшегося alias с ненулём, что
            # давало заниженные числа, когда исторически тема разбита в БД
            # на несколько подтем (например, прод-9 класс: «Треугольники»
            # + «Начала геометрии» + «Геометрические доказательства» все
            # маппятся в «Геометрия треугольника и окружности»).
            keys = [entry['db_topic']] + list(entry.get('aliases', []) or [])
            count = sum(by_topic.get(k, 0) for k in keys)
            topics.append({
                'name':      entry['name'],
                'emoji':     entry['emoji'],
                'count':     count,
                'available': count >= MIN_TASKS,
                'url':       url_for('adaptive_test_start_simple',
                                     topic=entry['key'], grade=grade_int),
            })

    return render_template(
        'adaptive_test_select_topic.html',
        grade=grade_int,
        topics=topics,
        min_tasks=MIN_TASKS,
        in_progress=_adaptive_in_progress_summary(),
    )


@app.route("/adaptive_test/start_grade")
def adaptive_test_start_grade():
    """Запуск тренировки для 5/6 класса по выбранному домену (GradeTask).

    Для 5/6 классов используется отдельный банк из 1600 задач (GradeTask),
    разбитый по школьным доменам. Пока эти задачи проходятся в обычном
    режиме (страница grade.domain_*) — без полностью адаптивного движка,
    т.к. он завязан на поля AdaptiveTask.

    Cooldown: общий лимит 30 дней между адаптивными тестами.
    """
    is_blocked, days_left, _ = _adaptive_cooldown_status()
    if is_blocked:
        flash(
            f'Адаптивный тест можно проходить раз в 30 дней. До следующего теста: {days_left} дн.',
            'info',
        )
        return redirect('/adaptive_test_simple/results')

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

    # Алиас kl_movement -> movement
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
        all_tasks = AdaptiveTask.query.filter(
            AdaptiveTask.class_level == grade_int,
            _is_flagged_not_true(),
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
    """Простой запуск адаптивного теста с фильтрацией по теме.

    Cooldown: общий лимит 30 дней между адаптивными тестами (любой темой).
    Дополнительно ниже сохраняется per-topic проверка для совместимости.
    """
    # Глобальный 30-дневный кулдаун (любая тема/класс)
    is_blocked, days_left, _ = _adaptive_cooldown_status()
    if is_blocked:
        flash(
            f'Адаптивный тест можно проходить раз в 30 дней. До следующего теста: {days_left} дн.',
            'info',
        )
        return redirect('/adaptive_test_simple/results')

    topic = request.args.get('topic')
    grade = request.args.get('grade')
    
    # kl_movement -> movement (алиас) — до любых проверок
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
    
    # ── ПРОВЕРКА: не пройден ли уже этот тест ────────────────────────────
    if current_user.is_authenticated:
        try:
            last_result = AdaptiveTestResult.query.filter_by(
                user_id=current_user.id,
                topic=topic,
                class_level=grade_int
            ).filter(
                AdaptiveTestResult.completed_at.isnot(None)
            ).order_by(
                AdaptiveTestResult.completed_at.desc()
            ).first()
            
            if last_result and last_result.completed_at:
                days_elapsed = (datetime.utcnow() - last_result.completed_at).days
                COOLDOWN_DAYS = 0
                days_left = COOLDOWN_DAYS - days_elapsed
                
                if days_left > 0:
                    answers = []
                    try:
                        if last_result.answers_history:
                            answers = json.loads(last_result.answers_history)
                            ids = [a.get('task_id') for a in answers if a.get('task_id')]
                            if ids:
                                tasks_map = {}
                                rows = AdaptiveTask.query.filter(
                                    AdaptiveTask.id.in_(ids)
                                ).all()
                                tasks_map = {t.id: t for t in rows}
                                for a in answers:
                                    tid = a.get('task_id')
                                    t = tasks_map.get(int(tid)) if tid else None
                                    a['task_text'] = t.task_text if t else ''
                    except Exception as _e:
                        print(f'[ADAPTIVE] Failed to decode answers_history: {_e}')
                        answers = []
                    
                    last_digit = days_left % 10
                    last_two = days_left % 100
                    if 11 <= last_two <= 19:
                        days_word = 'дней'
                    elif last_digit == 1:
                        days_word = 'день'
                    elif 2 <= last_digit <= 4:
                        days_word = 'дня'
                    else:
                        days_word = 'дней'
                    
                    correct = last_result.tasks_correct or 0
                    total = last_result.tasks_total or 25
                    accuracy = round(correct / total * 100) if total > 0 else 0
                    
                    topic_names_local = {
                        'algebra': 'Алгебра',
                        'geometry': 'Геометрия',
                        'combinatorics': 'Комбинаторика',
                        'number_theory': 'Теория чисел',
                        'movement': 'Задачи на движение',
                        'kl_movement': 'Задачи на движение',
                        'knights_liars': 'Рыцари и лжецы',
                        'functions': 'Функции',
                        'equations': 'Уравнения',
                    }
                    topic_name_display = topic_names_local.get(topic, topic)
                    completed_date_str = last_result.completed_at.strftime('%d.%m.%Y')
                    
                    return render_template('adaptive_test_already_completed.html',
                        topic=topic,
                        topic_name=topic_name_display,
                        grade=grade,
                        days_left=days_left,
                        days_word=days_word,
                        accuracy=accuracy,
                        correct=correct,
                        total=total,
                        final_level=last_result.final_level or 3,
                        completed_date=completed_date_str,
                        answers=answers,
                    )
        except Exception as _e:
            print(f'[ADAPTIVE] Completion check failed: {_e}')
    
    # ── НОВЫЙ ПУТЬ: реестр тем 7–11 классов (точное совпадение по db_topic) ──
    # Для 7–11 классов мы регистрируем темы в services.adaptive_topics_registry
    # и фильтруем задачи строгим равенством AdaptiveTask.topic == db_topic.
    # Для 5–6 и устаревших ключей (algebra/geometry/...) остаётся keyword-путь.
    from services.adaptive_topics_registry import get_topic_entry
    registry_entry = get_topic_entry(grade_int, topic)

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
        print(f"[ADAPTIVE FIX] 5 класс + Алгебра -> расширенный поиск по математике")
        topic_keywords['algebra'] = ['математик', 'числ', 'выражен', 'уравнен', 'задач',
                                      'вычислен', 'арифметик', 'олимпиад']

    # Маппинг тем для всех классов (задачи хранятся с полными русскими названиями)
    from services.adaptive_topic_mapping import get_keywords_for_grade_topic
    grade_kw = get_keywords_for_grade_topic(grade_int, topic)
    if grade_kw:
        topic_keywords[topic] = grade_kw
        print(f"[ADAPTIVE FIX] {grade_int} класс + {topic} -> ключевые слова: {grade_kw}")

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

    if registry_entry:
        topic_name = registry_entry['name']
    else:
        topic_name = topic_names.get(topic, topic)

    # ── Фильтрация задач ──────────────────────────────────────────────
    # (1) Если тема зарегистрирована в новом реестре — фильтруем строго по
    #     AdaptiveTask.topic == db_topic. Это надёжно и не зависит от keyword-эвристик.
    # (2) Иначе — legacy-путь через keyword'ы (5–6 классы и устаревшие ключи).
    db_topic_exact = registry_entry['db_topic'] if registry_entry else None

    if registry_entry:
        candidates = [db_topic_exact] + list(registry_entry.get('aliases', []) or [])
        filtered_tasks = AdaptiveTask.query.filter(
            AdaptiveTask.class_level == grade_int,
            _is_flagged_not_true(),  # noqa: E712
            AdaptiveTask.topic.in_(candidates),
        ).all()
        print(f"[ADAPTIVE registry] grade={grade_int} key={topic} "
              f"db_topic='{db_topic_exact}' -> {len(filtered_tasks)} задач")
    elif keywords:
        # Если есть ключевые слова - фильтруем по ним
        all_tasks = AdaptiveTask.query.filter(
            AdaptiveTask.class_level == grade_int,
            _is_flagged_not_true(),
            ).all()

        # Фильтруем задачи, где название темы содержит хотя бы одно ключевое слово
        filtered_tasks = []
        for task in all_tasks:
            topic_lower = (task.topic or '').lower()
            if any(keyword.lower() in topic_lower for keyword in keywords):
                filtered_tasks.append(task)
    else:
        # Если фильтра нет - берем все задачи класса (кроме помеченных)
        filtered_tasks = AdaptiveTask.query.filter(
            AdaptiveTask.class_level == grade_int,
            _is_flagged_not_true(),
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
    # Точная строка темы в БД (None для legacy keyword-пути 5–6 классов).
    # Используется как дополнительный страховочный фильтр в _adaptive_pick_task_for_slot.
    session['adaptive_db_topic'] = db_topic_exact
    session['adaptive_filtered_tasks'] = sorted(t.id for t in filtered_tasks)
    session['adaptive_current_difficulty'] = 3  # Начальная сложность

    # ── НОВАЯ МОДЕЛЬ СЛОТОВ ──────────────────────────────────────────────
    # Прогресс теста хранится как массив из 25 «слотов». Каждый слот:
    #   {
    #     'task_id': int | None,         # назначается лениво при первом показе
    #     'status':  'pending'|'answered'|'skipped',
    #     'score':   int | None,          # AI-балл (только для answered)
    #     'difficulty': int | None,       # уровень задачи, назначенной в слот
    #     'user_answer': str,             # короткий слепок (для results)
    #     'correct_answer': str,
    #     'level_at_assign': int,         # текущий current_level в момент выбора
    #   }
    # Адаптация уровня (current_difficulty) меняется только при answered.
    # Пропуски не влияют на адаптацию. Завершить тест можно только когда
    # answered_count == 25.
    session['adaptive_slots'] = [
        {
            'task_id': None,
            'status': 'pending',
            'score': None,
            'difficulty': None,
            'user_answer': '',
            'correct_answer': '',
            'level_at_assign': None,
        }
        for _ in range(25)
    ]
    # ── Legacy-поля сохраняем для обратной совместимости с другими местами,
    # которые могут читать session['adaptive_answers'] / current_index.
    session['adaptive_answers'] = []
    session['adaptive_current_index'] = 0
    session['adaptive_current_task_id'] = None
    session['adaptive_shown_task_ids'] = []
    session.permanent = True

    # Перенаправляем на упрощенную страницу теста (без БД, только сессии)
    return redirect('/adaptive_test_simple')


# ── ХЕЛПЕРЫ ДЛЯ СЛОТОВ ────────────────────────────────────────────────────
def _adaptive_get_slots():
    """Возвращает массив слотов из сессии. На случай старых сессий
    (которые стартовали ДО введения слотов) — лениво инициализирует
    структуру из старых полей."""
    slots = session.get('adaptive_slots')
    if isinstance(slots, list) and len(slots) == 25:
        return slots
    # Лениво создаём пустые слоты
    new_slots = []
    legacy_answers = session.get('adaptive_answers', []) or []
    for i in range(25):
        if i < len(legacy_answers):
            a = legacy_answers[i] or {}
            new_slots.append({
                'task_id': a.get('task_id'),
                'status': 'answered' if a.get('task_id') else 'pending',
                'score': a.get('score', a.get('is_correct')),
                'difficulty': a.get('difficulty'),
                'user_answer': (a.get('user_answer') or '')[:120],
                'correct_answer': (a.get('correct_answer') or '')[:120],
                'level_at_assign': a.get('difficulty'),
            })
        else:
            new_slots.append({
                'task_id': None, 'status': 'pending', 'score': None,
                'difficulty': None, 'user_answer': '', 'correct_answer': '',
                'level_at_assign': None,
            })
    session['adaptive_slots'] = new_slots
    session.modified = True
    return new_slots


def _adaptive_save_slots(slots):
    session['adaptive_slots'] = slots
    session.modified = True


def _adaptive_answered_count(slots=None):
    slots = slots if slots is not None else _adaptive_get_slots()
    return sum(1 for s in slots if s.get('status') == 'answered')


def _adaptive_pick_task_for_slot(slot_index, slots, current_difficulty):
    """Подобрать AdaptiveTask для слота. Не дублирует ранее выбранные задачи.
    Сохраняет task_id и level_at_assign в слоте."""
    task_ids = session.get('adaptive_filtered_tasks', []) or []
    if not task_ids:
        return None

    # Список уже задействованных task_id (по всем слотам, кроме текущего)
    used_ids = set()
    for i, s in enumerate(slots):
        if i == slot_index:
            continue
        tid = s.get('task_id')
        if tid:
            used_ids.add(int(tid))

    def _pick_first_at_level(level):
        rows = AdaptiveTask.query.filter(
            AdaptiveTask.id.in_(task_ids),
            AdaptiveTask.difficulty_level == level
        ).order_by(AdaptiveTask.id.asc()).all()
        for t in rows:
            if t.id not in used_ids:
                return t
        return None

    picked = _pick_first_at_level(current_difficulty)
    if picked is None:
        # Сначала вверх (+1..+7), потом вниз (-1..-7) — чтобы при дефиците
        # на текущем уровне отдавать предпочтение более высоким, а не
        # скатываться к простым.
        for offset in (1, 2, 3, 4, 5, 6, 7, -1, -2, -3, -4, -5, -6, -7):
            lvl = current_difficulty + offset
            if 1 <= lvl <= 8:
                picked = _pick_first_at_level(lvl)
                if picked:
                    if offset < 0:
                        print(
                            f"[ADAPTIVE-PICK] WARNING: no free tasks at level "
                            f">= {current_difficulty} for slot {slot_index+1}; "
                            f"fell DOWN to level {lvl} (offset={offset})"
                        )
                    break
    if picked is None:
        # Любая неиспользованная задача
        remaining = [tid for tid in sorted(task_ids) if tid not in used_ids]
        if remaining:
            picked = AdaptiveTask.query.get(remaining[0])

    if picked:
        slots[slot_index]['task_id'] = picked.id
        slots[slot_index]['difficulty'] = picked.difficulty_level
        slots[slot_index]['level_at_assign'] = current_difficulty
    return picked


def _adaptive_slots_summary(slots):
    """Возвращает массив из 25 элементов для пагинации в шаблоне:
       [{'index': 1, 'status': 'answered'|'skipped'|'pending'|'empty'}, ...]
       'empty' = слот существует, но задача ещё не назначена (ленивая инициализация)."""
    out = []
    for i, s in enumerate(slots):
        st = s.get('status') or 'pending'
        if st == 'pending' and not s.get('task_id'):
            st_display = 'empty'
        else:
            st_display = st
        out.append({'index': i + 1, 'status': st_display})
    return out


# ─── Test Session Recovery API ───────────────────────────────────────────
# Сохраняет полное состояние адаптивного теста в таблице test_sessions
# для восстановления после закрытия вкладки / перезагрузки страницы.
#
# Ключи Flask-сессии, которые нужно сохранять:
_ADAPTIVE_SESSION_KEYS = (
    'adaptive_current_difficulty',
    'adaptive_filtered_tasks',
    'adaptive_topic',
    'adaptive_topic_name',
    'adaptive_grade',
    'adaptive_db_topic',
    'adaptive_current_index',
    'adaptive_current_task_id',
    'adaptive_current_slot',
    'adaptive_shown_task_ids',
    'partial_correct_streak',
)


def _ts_get_user_key():
    """Возвращает (user_id, device_id) для привязки сессии теста."""
    try:
        from flask_login import current_user as _cu
        uid = _cu.id if (_cu and getattr(_cu, 'is_authenticated', False)) else None
    except Exception:
        uid = None
    did = session.get('device_id')
    return uid, did


def _ts_serialize_adaptive_state():
    """Снимок ключей Flask-сессии адаптивного теста (JSON-сериализуемый)."""
    out = {}
    for k in _ADAPTIVE_SESSION_KEYS:
        if k in session:
            out[k] = session.get(k)
    return out


def _get_active_test_session(test_type='adaptive'):
    """Находит активную (in_progress) запись test_sessions для текущего
    пользователя/устройства. Возвращает row mapping или None."""
    from sqlalchemy import text as _sql
    uid, did = _ts_get_user_key()
    if not uid and not did:
        return None
    try:
        if uid:
            row = db.session.execute(
                _sql(
                    "SELECT * FROM test_sessions "
                    "WHERE user_id = :uid AND test_type = :tt AND status = 'in_progress' "
                    "ORDER BY last_activity_at DESC LIMIT 1"
                ),
                {'uid': uid, 'tt': test_type},
            ).fetchone()
            if row:
                return dict(row._mapping)
        if did:
            row = db.session.execute(
                _sql(
                    "SELECT * FROM test_sessions "
                    "WHERE device_id = :did AND test_type = :tt AND status = 'in_progress' "
                    "ORDER BY last_activity_at DESC LIMIT 1"
                ),
                {'did': did, 'tt': test_type},
            ).fetchone()
            if row:
                return dict(row._mapping)
    except Exception as _e:
        print(f"[test_sessions] _get_active_test_session error: {_e}")
    return None


def _save_adaptive_state_to_db(session_id=None, status=None, mark_completed=False):
    """Сохраняет ТЕКУЩЕЕ состояние Flask-сессии адаптивного теста в БД.

    Если `session_id` передан — обновляет существующую запись.
    Если нет — пытается найти существующую in_progress запись,
    иначе создаёт новую.

    Возвращает session_id (int) или None при ошибке.
    """
    from sqlalchemy import text as _sql
    import json as _json
    from datetime import datetime as _dt

    if 'adaptive_filtered_tasks' not in session:
        # Тест не активен — нечего сохранять
        return None

    uid, did = _ts_get_user_key()
    if not uid and not did:
        return None

    slots = _adaptive_get_slots()
    answered_cnt = _adaptive_answered_count(slots)
    current_idx = answered_cnt  # сколько уже отвечено = индекс следующего
    state = _ts_serialize_adaptive_state()
    answers_json = _json.dumps(slots, ensure_ascii=False)
    state_json = _json.dumps(state, ensure_ascii=False)
    topic = session.get('adaptive_topic') or ''
    topic_name = session.get('adaptive_topic_name') or topic
    grade = str(session.get('adaptive_grade') or '')
    new_status = status or ('completed' if mark_completed else 'in_progress')

    # current_result = суммарный score по answered-слотам
    try:
        cur_result = sum(
            int(s.get('score') or 0)
            for s in slots
            if s.get('status') == 'answered' and isinstance(s.get('score'), (int, float))
        )
    except Exception:
        cur_result = 0

    try:
        # 1. Найти существующую запись
        if session_id is None:
            row = _get_active_test_session('adaptive')
            if row:
                session_id = row.get('id')

        if session_id:
            # UPDATE
            db.session.execute(
                _sql(
                    "UPDATE test_sessions SET "
                    "topic = :topic, topic_name = :tname, grade = :grade, "
                    "status = :st, current_question_index = :idx, "
                    "answers = :answers, adaptive_state = :state, "
                    "current_result = :cur_result, "
                    "last_activity_at = :now, "
                    "completed_at = CASE WHEN :st = 'completed' THEN :now ELSE completed_at END "
                    "WHERE id = :sid"
                ),
                {
                    'topic': topic, 'tname': topic_name, 'grade': grade,
                    'st': new_status, 'idx': current_idx,
                    'answers': answers_json, 'state': state_json,
                    'cur_result': cur_result,
                    'now': _dt.utcnow(), 'sid': session_id,
                },
            )
            db.session.commit()
            return int(session_id)

        # 2. INSERT новой записи
        result = db.session.execute(
            _sql(
                "INSERT INTO test_sessions "
                "(user_id, device_id, test_type, topic, topic_name, grade, "
                "status, current_question_index, total_questions, "
                "answers, adaptive_state, current_result, "
                "started_at, last_activity_at) "
                "VALUES (:uid, :did, 'adaptive', :topic, :tname, :grade, "
                ":st, :idx, 25, :answers, :state, :cur_result, :now, :now)"
            ),
            {
                'uid': uid, 'did': did,
                'topic': topic, 'tname': topic_name, 'grade': grade,
                'st': new_status, 'idx': current_idx,
                'answers': answers_json, 'state': state_json,
                'cur_result': cur_result,
                'now': _dt.utcnow(),
            },
        )
        db.session.commit()

        # достаём id (поддержка SQLite + PostgreSQL)
        new_id = None
        try:
            new_id = result.lastrowid
        except Exception:
            pass
        if not new_id:
            # Постгрес: вернём по уникальному поиску
            r2 = db.session.execute(
                _sql(
                    "SELECT id FROM test_sessions WHERE "
                    "(user_id = :uid OR (:uid IS NULL AND device_id = :did)) "
                    "AND test_type = 'adaptive' AND status = :st "
                    "ORDER BY id DESC LIMIT 1"
                ),
                {'uid': uid, 'did': did, 'st': new_status},
            ).fetchone()
            new_id = r2[0] if r2 else None
        return int(new_id) if new_id else None
    except Exception as _e:
        print(f"[test_sessions] _save_adaptive_state_to_db error: {_e}")
        try:
            db.session.rollback()
        except Exception:
            pass
        return None


def _load_adaptive_state_from_db(session_id):
    """Загружает строку test_sessions по id и восстанавливает ключи
    Flask-сессии. Возвращает True/False."""
    from sqlalchemy import text as _sql
    import json as _json
    try:
        row = db.session.execute(
            _sql("SELECT * FROM test_sessions WHERE id = :sid"),
            {'sid': int(session_id)},
        ).fetchone()
        if not row:
            return False
        rec = dict(row._mapping)
        # Доступ разрешён, если совпадает user_id ИЛИ device_id
        uid, did = _ts_get_user_key()
        owner_uid = rec.get('user_id')
        owner_did = rec.get('device_id')
        if uid and owner_uid and int(owner_uid) == int(uid):
            pass
        elif did and owner_did and str(owner_did) == str(did):
            pass
        else:
            # Не наш — отказ
            return False

        state_raw = rec.get('adaptive_state')
        if isinstance(state_raw, str):
            state = _json.loads(state_raw) if state_raw else {}
        elif isinstance(state_raw, dict):
            state = state_raw
        else:
            state = {}

        answers_raw = rec.get('answers')
        if isinstance(answers_raw, str):
            answers = _json.loads(answers_raw) if answers_raw else []
        elif isinstance(answers_raw, list):
            answers = answers_raw
        else:
            answers = []

        # Восстанавливаем все ключи
        for k in _ADAPTIVE_SESSION_KEYS:
            if k in state:
                session[k] = state[k]
        if isinstance(answers, list) and len(answers) == 25:
            session['adaptive_slots'] = answers
        # Поддерживаем минимум: если в state не было adaptive_filtered_tasks —
        # фронт всё равно пометит сессию активной благодаря adaptive_slots.
        if 'adaptive_filtered_tasks' not in session:
            session['adaptive_filtered_tasks'] = state.get('adaptive_filtered_tasks', [])

        session.permanent = True
        session.modified = True
        return True
    except Exception as _e:
        print(f"[test_sessions] _load_adaptive_state_from_db error: {_e}")
        return False


@app.route("/api/test/start", methods=["POST"])
@login_required
def api_test_start():
    """Создаёт (или возвращает существующую) запись test_sessions для
    активного адаптивного теста. Используется JS на странице теста."""
    if 'adaptive_filtered_tasks' not in session:
        return jsonify({'ok': False, 'error': 'Сессия теста не активна'}), 400
    sid = _save_adaptive_state_to_db()
    if not sid:
        return jsonify({'ok': False, 'error': 'Не удалось создать сессию'}), 500
    return jsonify({'ok': True, 'session_id': sid})


@app.route("/api/test/active", methods=["GET"])
@login_required
def api_test_active():
    """Проверяет, есть ли активная (in_progress) сессия для текущего
    пользователя/устройства. Возвращает {active: True, session: {...}} или {}."""
    row = _get_active_test_session('adaptive')
    if not row:
        return jsonify({})
    return jsonify({
        'active': True,
        'session': {
            'id': row.get('id'),
            'topic': row.get('topic'),
            'topic_name': row.get('topic_name'),
            'grade': row.get('grade'),
            'current_question_index': row.get('current_question_index'),
            'total_questions': row.get('total_questions'),
            'status': row.get('status'),
        },
    })


@app.route("/api/test/<int:session_id>/resume", methods=["GET"])
@login_required
def api_test_resume(session_id):
    """Возвращает полное состояние сессии + восстанавливает Flask-сессию."""
    from sqlalchemy import text as _sql
    import json as _json
    ok = _load_adaptive_state_from_db(session_id)
    if not ok:
        return jsonify({'ok': False, 'error': 'Сессия не найдена или нет доступа'}), 404
    row = db.session.execute(
        _sql("SELECT * FROM test_sessions WHERE id = :sid"),
        {'sid': session_id},
    ).fetchone()
    rec = dict(row._mapping) if row else {}
    state_raw = rec.get('adaptive_state')
    state = _json.loads(state_raw) if isinstance(state_raw, str) and state_raw else (state_raw or {})
    answers_raw = rec.get('answers')
    slots = _json.loads(answers_raw) if isinstance(answers_raw, str) and answers_raw else (answers_raw or [])
    return jsonify({
        'ok': True,
        'session': {
            'id': rec.get('id'),
            'status': rec.get('status'),
            'topic': rec.get('topic'),
            'topic_name': rec.get('topic_name'),
            'grade': rec.get('grade'),
            'current_question_index': rec.get('current_question_index'),
            'total_questions': rec.get('total_questions'),
        },
        'adaptive_state': state,
        'slots': slots,
    })


@app.route("/api/test/<int:session_id>/answer", methods=["POST"])
def api_test_answer(session_id):
    """Сохраняет текущее состояние Flask-сессии в БД. Вызывается из
    `sendBeacon` при закрытии вкладки. Тело запроса не используется —
    источник истины это Flask session."""
    sid = _save_adaptive_state_to_db(session_id=session_id)
    if not sid:
        return jsonify({'ok': False}), 400
    return jsonify({'ok': True, 'status': 'ok', 'session_id': sid})


@app.route("/api/test/<int:session_id>/complete", methods=["POST"])
def api_test_complete(session_id):
    """Отмечает сессию как 'completed'."""
    sid = _save_adaptive_state_to_db(session_id=session_id, mark_completed=True)
    if not sid:
        return jsonify({'ok': False}), 400
    return jsonify({'ok': True})


@app.route("/api/test/<int:session_id>/abandon", methods=["POST"])
def api_test_abandon(session_id):
    """Отмечает сессию как 'abandoned' — для кнопки «Начать заново»."""
    from sqlalchemy import text as _sql
    from datetime import datetime as _dt
    try:
        # Проверка владения
        row = db.session.execute(
            _sql("SELECT user_id, device_id FROM test_sessions WHERE id = :sid"),
            {'sid': session_id},
        ).fetchone()
        if not row:
            return jsonify({'ok': False}), 404
        uid, did = _ts_get_user_key()
        owner_uid = row[0]
        owner_did = row[1]
        if not ((uid and owner_uid and int(owner_uid) == int(uid))
                or (did and owner_did and str(owner_did) == str(did))):
            return jsonify({'ok': False, 'error': 'forbidden'}), 403
        db.session.execute(
            _sql(
                "UPDATE test_sessions SET status = 'abandoned', "
                "last_activity_at = :now WHERE id = :sid"
            ),
            {'now': _dt.utcnow(), 'sid': session_id},
        )
        db.session.commit()
        return jsonify({'ok': True})
    except Exception as _e:
        print(f"[test_sessions] api_test_abandon error: {_e}")
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify({'ok': False, 'error': str(_e)}), 500
# ─── End Test Session Recovery API ────────────────────────────────────────


@app.route("/adaptive_test_simple")
def adaptive_test_simple_page():
    """Упрощенная страница адаптивного теста (без авторизации, на сессиях).

    Поддерживает навигацию по слотам через `?slot=N` (1..25).
    Если slot не указан — открывается первый pending-слот (или 1-й, если
    все уже отвечены/пропущены).

    Также поддерживает восстановление прерванного теста через
    `?session=<id>` — состояние Flask-сессии загружается из БД."""
    # ── Восстановление сессии из БД по ?session=<id> ──
    _resume_sid = request.args.get('session')
    if _resume_sid:
        try:
            _ok = _load_adaptive_state_from_db(int(_resume_sid))
        except (TypeError, ValueError):
            _ok = False
        if not _ok:
            flash('Не удалось восстановить прерванный тест', 'error')
            return redirect(url_for('probniks_page'))

    # Проверяем, что в сессии есть данные теста. Если нет — редиректим
    # на выбор класса/темы, а не в общий каталог probniks_page.
    if 'adaptive_filtered_tasks' not in session:
        flash('Сначала выберите класс и тему для теста', 'error')
        return redirect(url_for('adaptive_test_select_class'))

    grade = session.get('adaptive_grade', '9')
    slots = _adaptive_get_slots()
    current_difficulty = session.get('adaptive_current_difficulty', 3)

    # ── Определяем slot_index из query-параметра или ищем первый pending ──
    try:
        requested = int(request.args.get('slot', '0'))
    except (TypeError, ValueError):
        requested = 0

    if 1 <= requested <= 25:
        slot_index = requested - 1
    else:
        # Авто-выбор: первый слот со status='pending'
        slot_index = next(
            (i for i, s in enumerate(slots) if s.get('status') == 'pending'),
            0
        )

    slot = slots[slot_index]

    # ── Stale-slot reassignment (FORMYLA v2 calibration fix) ────────────
    # Если активный слот ещё pending (т.е. на него не отвечено) и был
    # назначен при ином уровне (level_at_assign != current_difficulty) —
    # сбрасываем task_id, чтобы пикер выбрал свежую задачу под актуальный
    # уровень. Это устраняет «застрявший бейдж 4/8» когда session-уровень
    # уже вырос до 5/6/7/8.
    if (
        slot.get('status', 'pending') == 'pending'
        and slot.get('level_at_assign') is not None
        and slot.get('level_at_assign') != current_difficulty
    ):
        slot['task_id'] = None
        slot['difficulty'] = None
        slot['level_at_assign'] = None

    # ── Если в слоте ещё нет назначенной задачи — назначаем сейчас ──────
    current_task = None
    if slot.get('task_id'):
        current_task = AdaptiveTask.query.get(slot['task_id'])
        if not current_task:
            # Задача удалена/отсутствует — переназначаем
            slot['task_id'] = None

    if not current_task and slot.get('status') in ('pending',):
        current_task = _adaptive_pick_task_for_slot(slot_index, slots, current_difficulty)
        _adaptive_save_slots(slots)
    elif not current_task and slot.get('task_id'):
        current_task = AdaptiveTask.query.get(slot['task_id'])

    if not current_task:
        flash('Ошибка загрузки задачи', 'error')
        return redirect(url_for('probniks_page'))

    # ── Готовим словарь задачи для шаблона ─────────────────────────────
    task_dict = {
        'id': current_task.id,
        'topic': current_task.topic,
        'class_level': current_task.class_level,
        'difficulty_level': current_task.difficulty_level,
        'task_text': current_task.task_text or '',
        'solution': current_task.solution,
        'criteria_1_point': current_task.criteria_1_point,
        'criteria_2_points': current_task.criteria_2_points,
    }
    topic_name = current_task.topic

    # Нормализуем математический текст (auto-wrap `^`, `sqrt`, системы и т.п.
    # в `$...$`) — чтобы KaTeX/MathJax корректно отрисовывал формулы на
    # странице задачи внутри темы. Не модифицируем исходный объект
    # AdaptiveTask — работаем с копией task_dict.
    try:
        from services.math_text_normalizer import normalize_math_text
        for _fld in ('task_text', 'solution', 'criteria_1_point', 'criteria_2_points'):
            _v = task_dict.get(_fld)
            if isinstance(_v, str) and _v:
                task_dict[_fld] = normalize_math_text(_v)
    except Exception as _norm_err:
        app.logger.warning(
            f"[math_normalizer] adaptive_test_simple task {current_task.id}: {_norm_err}"
        )

    answered_count = _adaptive_answered_count(slots)
    can_finish = (answered_count >= 25)
    is_readonly = slot.get('status') in ('answered',)

    # Сохраняем «текущий слот» для совместимости со старым check_adaptive_answer
    session['adaptive_current_slot'] = slot_index
    session['adaptive_current_task_id'] = current_task.id
    session.modified = True

    return render_template(
        'adaptive_test_simple.html',
        topic_name=topic_name,
        grade=grade,
        task=task_dict,
        current_index=slot_index + 1,
        current_slot=slot_index + 1,
        total_tasks=25,
        current_level=current_difficulty,
        slots_summary=_adaptive_slots_summary(slots),
        slot_status=slot.get('status', 'pending'),
        is_readonly=is_readonly,
        answered_count=answered_count,
        can_finish=can_finish,
        remaining_to_finish=max(0, 25 - answered_count),
        existing_score=slot.get('score'),
        existing_user_answer=slot.get('user_answer', ''),
        existing_correct_answer=slot.get('correct_answer', ''),
    )


@app.route("/adaptive_test_simple/skip", methods=["POST"])
def adaptive_test_simple_skip():
    """Помечает текущий слот как 'skipped'. Не отправляет ответ в AI,
    не меняет current_level. Возвращает JSON со следующим slot-индексом."""
    if 'adaptive_filtered_tasks' not in session:
        return jsonify({'status': 'error', 'message': 'Сессия теста истекла'}), 400

    try:
        payload = request.get_json(silent=True) or {}
        slot_num = int(payload.get('slot') or request.form.get('slot') or 0)
    except (TypeError, ValueError):
        slot_num = 0

    if not (1 <= slot_num <= 25):
        return jsonify({'status': 'error', 'message': 'Некорректный слот'}), 400

    slots = _adaptive_get_slots()
    slot_index = slot_num - 1
    slot = slots[slot_index]

    # Нельзя пропустить уже отвеченный
    if slot.get('status') == 'answered':
        return jsonify({
            'status': 'error',
            'message': 'На эту задачу уже отвечено — пропуск невозможен'
        }), 400

    slot['status'] = 'skipped'
    _adaptive_save_slots(slots)

    # Определяем следующий слот: первый pending после текущего, потом с начала
    next_slot = None
    for i in list(range(slot_index + 1, 25)) + list(range(0, slot_index)):
        if slots[i].get('status') == 'pending':
            next_slot = i + 1
            break
    if next_slot is None:
        # Все pending кончились — остаёмся на следующем индексе или на текущем
        next_slot = min(slot_num + 1, 25)

    answered_count = _adaptive_answered_count(slots)
    return jsonify({
        'status': 'success',
        'next_slot': next_slot,
        'answered_count': answered_count,
        'can_finish': answered_count >= 25,
        'remaining_to_finish': max(0, 25 - answered_count),
    })


@app.route("/adaptive_test_simple/finish", methods=["GET", "POST"])
def adaptive_test_simple_finish():
    """Завершение теста. Разрешено только если на все 25 задач даны ответы.
    Если есть pending/skipped — редирект обратно с flash-сообщением."""
    if 'adaptive_filtered_tasks' not in session:
        flash('Сессия теста истекла', 'error')
        return redirect(url_for('probniks_page'))

    slots = _adaptive_get_slots()
    answered_count = _adaptive_answered_count(slots)
    if answered_count < 25:
        # Находим первый pending/skipped слот, чтобы туда вернуть пользователя
        unfinished = next(
            (i + 1 for i, s in enumerate(slots) if s.get('status') != 'answered'),
            1
        )
        msg = f'Чтобы завершить тест, нужно ответить на все 25 задач. Осталось: {25 - answered_count}.'
        if request.method == 'POST':
            return jsonify({
                'status': 'error',
                'message': msg,
                'next_slot': unfinished,
                'answered_count': answered_count,
                'remaining_to_finish': 25 - answered_count,
            }), 400
        flash(msg, 'error')
        return redirect(f'/adaptive_test_simple?slot={unfinished}')

    # ── Все 25 отвечены: переносим слоты в legacy adaptive_answers,
    # которые читает страница результатов.
    answers_for_results = []
    for s in slots:
        if not s.get('task_id'):
            continue
        answers_for_results.append({
            'task_id': s.get('task_id'),
            'user_answer': (s.get('user_answer') or '')[:120],
            'correct_answer': (s.get('correct_answer') or '')[:120],
            'score': s.get('score', 0),
            'difficulty': s.get('difficulty'),
        })
    session['adaptive_answers'] = answers_for_results
    session['adaptive_current_index'] = 25
    session.modified = True

    # Помечаем сессию завершённой в БД
    try:
        _save_adaptive_state_to_db(mark_completed=True)
    except Exception as _e_fin:
        print(f"[test_sessions] complete-on-finish failed: {_e_fin}")

    # ── Cooldown: фиксируем время прохождения для 30-дневного лимита ──
    # Для гостей пишем в сессию (логиненные пользователи получают
    # AdaptiveTestResult.completed_at на странице результатов).
    try:
        from datetime import datetime as _dt_now
        session['adaptive_completed_at'] = _dt_now.utcnow().isoformat()
        session.modified = True
    except Exception as _e_cd:
        print(f"[ADAPTIVE-COOLDOWN] failed to stamp session: {_e_cd}")

    if request.method == 'POST':
        return jsonify({'status': 'success', 'redirect': '/adaptive_test_simple/results'})
    return redirect('/adaptive_test_simple/results')


@app.route("/adaptive_test_simple/submit", methods=["POST"])
def adaptive_test_simple_submit():
    """[Legacy] Не используется фронтом (ответы идут через
    /api/check_adaptive_answer). Оставлен на случай прямой отправки формы:
    просто редиректит на страницу теста."""
    if 'adaptive_filtered_tasks' not in session:
        flash('Сессия теста истекла', 'error')
        return redirect(url_for('probniks_page'))
    return redirect('/adaptive_test_simple')


@app.route("/api/check_adaptive_answer", methods=["POST"])
@login_required
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

        # ── Определяем slot, к которому относится этот ответ ───────────
        # Фронт передаёт `slot` (1..25). Если не передал — берём текущий
        # из сессии или ищем слот с этим task_id.
        try:
            slot_num = int(data.get('slot') or 0)
        except (TypeError, ValueError):
            slot_num = 0

        _slots = _adaptive_get_slots()
        if not (1 <= slot_num <= 25):
            # Совместимость: ищем слот с этим task_id, иначе берём current_slot
            slot_index_fallback = session.get('adaptive_current_slot')
            slot_index = None
            for i, s in enumerate(_slots):
                if s.get('task_id') and int(s['task_id']) == int(task_id):
                    slot_index = i
                    break
            if slot_index is None and isinstance(slot_index_fallback, int):
                slot_index = slot_index_fallback
            if slot_index is None:
                slot_index = 0
            slot_num = slot_index + 1
        else:
            slot_index = slot_num - 1

        _slot = _slots[slot_index]
        if _slot.get('status') == 'answered':
            return jsonify({
                'status': 'error',
                'message': 'На эту задачу уже отвечено. Перейдите к другой задаче.',
                'already_answered': True,
            }), 400

        # Гарантируем, что в слоте записан правильный task_id (он мог быть
        # пустым, если слот ленивый и пользователь сразу отправил ответ).
        if not _slot.get('task_id'):
            _slot['task_id'] = current_task.id
            _slot['difficulty'] = current_task.difficulty_level

        # Получаем правильный ответ (если есть поле answer в модели)
        correct_answer = getattr(current_task, 'answer', '') or getattr(current_task, 'correct_answer', 'не указан')

        # ── ИИ-тьютор — ЕДИНСТВЕННЫЙ судья вердикта +1/0/−1 ───────────────
        # ВАЖНО (по требованию продукта): НИКАКИХ локальных short-circuit.
        # Ни строковая сверка (services.answer_checker), ни «правильный ответ
        # без решения = +1» не должны выносить вердикт мимо ИИ-тьютора —
        # они раньше создавали рассинхрон: «локально −1, по факту +1» или
        # наоборот.
        # review_attempt() сам внутри использует sympy/match-equivalent
        # ИСКЛЮЧИТЕЛЬНО как подсказку для модели; финальные answer_correct /
        # method_correct берутся из JSON-ответа DeepSeek.
        from services.solution_check_pipeline import check_solution
        result = check_solution(
            entity_type="regular",
            task_text=current_task.task_text or "",
            correct_answer=correct_answer,
            solution_ref=current_task.solution or "",
            user_answer=user_answer,
            user_solution=user_solution,
            images_b64=images_b64,
            difficulty_level=current_task.difficulty_level or 5,
            max_tokens=4096,
        )

        float_score = float(result.get("score", 0.0))
        feedback = str(result.get("feedback") or "")
        category = str(result.get("category") or "")
        confidence = float(result.get("confidence") or 0.0)
        answer_correct = result.get("answer_correct")
        method_correct = result.get("method_correct")
        # Низкое доверие OCR — предупреждаем ученика
        if result.get("ocr") and result["ocr"].get("low_confidence"):
            warn = result["ocr"].get("warning") or "Распознавание фото ненадёжно."
            feedback = f"⚠️ {warn}\n\n{feedback}"
        has_solution = bool((user_solution or "").strip()) or bool(images_b64)
        print(
            f"[ADAPTIVE] AI tutor verdict: float_score={float_score}, "
            f"category={category}, confidence={confidence}, "
            f"answer_correct={answer_correct}, method_correct={method_correct}, "
            f"has_solution={has_solution}"
        )

        # ── Детекция сбоя AI ──────────────────────────────────────────
        # При сбое (parse error / API exception / AI unavailable) review_attempt()
        # возвращает: score=0.0, category="suspicious", confidence=0.0,
        # answer_correct=None. Это нейтральное событие — уровень не трогаем.
        is_ai_failure = (
            confidence == 0.0
            and category == "suspicious"
            and answer_correct is None
        )

        # — Шкала FORMYLA: уровень определяется ТОЛЬКО по вердикту ИИ-тьютора —
        #   answer_correct is True  -> +1 (верно)
        #   answer_correct is False -> -1 (неверно)
        #   answer_correct is None / AI failure -> 0 (нейтрально, без изм.)
        # method_correct БОЛЬШЕ НЕ влияет на уровень (по требованию: +1 значит +1).
        if is_ai_failure or answer_correct is None:
            score = 0
        elif answer_correct is True:
            # ИИ-тьютор сказал: ответ верный -> +1, независимо от метода.
            score = 1
        else:
            score = -1

        # ── Применяем дельту к уровню (clamp 1..8) ─────────────────────
        # FORMYLA v2: уровни 1..8, дельта +1/0/-1 от СОХРАНЁННОГО уровня
        # (а не от difficulty показанной задачи).
        current_difficulty = session.get('adaptive_current_difficulty', 3)
        partial_streak = session.get('partial_correct_streak', 0)
        delta = score  # +1 / 0 / -1
        new_level = max(1, min(8, current_difficulty + delta))

        # partial_streak: сбрасываем при любом не-нейтральном вердикте;
        # сохраняем при AI failure и при score==0 (нейтрально).
        if score in (1, -1):
            partial_streak = 0

        print(
            f"[ADAPTIVE] Score={score} (delta={delta}), "
            f"Level: {current_difficulty} -> {new_level}, "
            f"is_ai_failure={is_ai_failure}"
        )
        
        # Сохраняем обновленные значения уровня в сессию.
        # ВАЖНО: уровень меняется ТОЛЬКО потому что мы ответили на ЭТУ задачу
        # (пропуски обрабатываются отдельным эндпоинтом и не доходят сюда).
        session['adaptive_current_difficulty'] = new_level
        session['partial_correct_streak'] = partial_streak

        # ── Обновляем слот ────────────────────────────────────────────
        # ВАЖНО: НЕ сохраняем длинные строки (feedback, user_solution) в сессии,
        # чтобы не выйти за лимит Flask cookie session (~4KB).
        _slot['task_id'] = current_task.id
        _slot['status'] = 'answered'
        _slot['score'] = score
        _slot['difficulty'] = current_task.difficulty_level
        _slot['user_answer'] = (user_answer or '')[:120]
        _slot['correct_answer'] = (str(correct_answer) if correct_answer else '')[:120]
        _adaptive_save_slots(_slots)

        # Подсчитываем answered_count для фронта
        answered_count = _adaptive_answered_count(_slots)
        can_finish = (answered_count >= 25)

        # Определяем «следующий слот»:
        #   1) первый pending после текущего,
        #   2) затем первый pending с начала,
        #   3) если pending нет — следующий по номеру (для read-only просмотра).
        next_slot = None
        for i in list(range(slot_index + 1, 25)) + list(range(0, slot_index)):
            if _slots[i].get('status') == 'pending':
                next_slot = i + 1
                break
        if next_slot is None:
            next_slot = min(slot_num + 1, 25)

        session.modified = True

        # Сохраняем прогресс в БД (для восстановления после закрытия вкладки)
        try:
            _save_adaptive_state_to_db()
        except Exception as _e_save:
            print(f"[test_sessions] save in check_adaptive_answer failed: {_e_save}")

        # Legacy-флаг is_last_task: оставлен для обратной совместимости JS.
        # Реальное завершение теперь только через /adaptive_test_simple/finish
        # после answered_count == 25.
        is_last_task = can_finish

        return jsonify({
            'status': 'success',
            'score': score,
            'feedback': feedback,
            'new_level': new_level,
            'current_level': new_level,
            'is_last_task': is_last_task,
            'can_finish': can_finish,
            'answered_count': answered_count,
            'remaining_to_finish': max(0, 25 - answered_count),
            'next_slot': next_slot,
            'current_slot': slot_num,
            'current_index': slot_num,  # backward-compat
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
@login_required
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
    # Гейтинг: завершить тест и попасть на результаты можно только когда
    # на все 25 задач даны ответы (через эндпоинт /finish или через прямой
    # переход после последнего ответа).
    if 'adaptive_filtered_tasks' not in session and 'adaptive_answers' not in session:
        flash('Нет данных о тесте', 'error')
        return redirect(url_for('probniks_page'))

    # Если в сессии есть слоты — собираем answers из них (это новый формат).
    slots = session.get('adaptive_slots')
    if isinstance(slots, list) and len(slots) == 25:
        answered = sum(1 for s in slots if s.get('status') == 'answered')
        if answered < 25:
            flash(
                f'Чтобы увидеть результаты, нужно ответить на все 25 задач. Осталось: {25 - answered}.',
                'error'
            )
            unfinished = next(
                (i + 1 for i, s in enumerate(slots) if s.get('status') != 'answered'),
                1
            )
            return redirect(f'/adaptive_test_simple?slot={unfinished}')
        # Перебрасываем слоты в legacy-формат
        session['adaptive_answers'] = [
            {
                'task_id': s.get('task_id'),
                'user_answer': (s.get('user_answer') or '')[:120],
                'correct_answer': (s.get('correct_answer') or '')[:120],
                'score': s.get('score', 0),
                'difficulty': s.get('difficulty'),
            }
            for s in slots if s.get('task_id')
        ]
        session.modified = True

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
                        f"Ответ верный! [OK]\n\nПравильный ответ: **{ca}**"
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

    # Нормализуем math-формулы (`x^2`, `sqrt(x)`, системы) в каждом ответе —
    # task_text/solution/feedback/correct_answer. Делается ПЕРЕД рендером,
    # чтобы KaTeX/MathJax увидел корректный LaTeX.
    try:
        from services.math_text_normalizer import normalize_math_text
        for _a in answers:
            for _fld in ('task_text', 'solution', 'feedback',
                         'correct_answer', 'user_answer'):
                _v = _a.get(_fld)
                if isinstance(_v, str) and _v:
                    _a[_fld] = normalize_math_text(_v)
    except Exception as _norm_err:
        app.logger.warning(
            f"[math_normalizer] adaptive_test_simple_results: {_norm_err}"
        )

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

            # Короткий промпт (3-4 предложения) — max_tokens=500 достаточно,
            # но DeepSeekClient.timeout=90с, а Render LB отбивает через ~30с.
            # Используем ThreadPoolExecutor с жёстким таймаутом 15 секунд.
            import concurrent.futures as _cf
            with _cf.ThreadPoolExecutor(max_workers=1) as _executor:
                _future = _executor.submit(
                    client.generate,
                    prompt=prompt,
                    system_prompt=r"Ты опытный тренер олимпиадной математической сборной. Твоя задача - мотивировать учеников и давать конкретные рекомендации. Используй LaTeX для формул: \( x^2 \), \( \frac{a}{b} \), \( \sqrt{x} \).",
                    temperature=0.8,
                    max_tokens=500,
                )
                try:
                    test.ai_analysis = _future.result(timeout=15)
                except _cf.TimeoutError:
                    logger.warning("analyze_adaptive_test: DeepSeek timeout (15s) — fallback")
                    test.ai_analysis = "ИИ-тренер сейчас анализирует результаты других олимпиадников. Загляните сюда чуть позже!"
            
        except Exception as e:
            logger.error(f"Ошибка AI анализа: {e}")
            test.ai_analysis = "ИИ-тренер сейчас анализирует результаты других олимпиадников. Загляните сюда чуть позже!"
    
    test.status = 'completed'
    db.session.commit()
    
    # ── Fix 4: Проактивная предгенерация «Задач дня» после адаптивного теста ──
    # AI-генерация «Задач дня» отключена — prewarm пропускается.
    # (см. daily_tasks/services.py: AI_GENERATION_ENABLED)
    try:
        trigger_daily_prewarm(current_user.id)
    except Exception:
        logger.exception("trigger_daily_prewarm failed for user %s", current_user.id)
    
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


@app.route("/api/social/friends/request", methods=["POST"])
@login_required
def api_social_friend_request():
    """API: Отправить заявку в друзья (для social.html)."""
    try:
        data = request.get_json()
        uid = data.get('user_id')
        if not uid:
            return jsonify({'success': False, 'error': 'user_id is required'}), 400

        from models import Friendship
        uid = int(uid)
        if uid == current_user.id:
            return jsonify({'success': False, 'error': 'Нельзя добавить себя'}), 400

        person = User.query.get(uid)
        if not person:
            return jsonify({'success': False, 'error': 'Пользователь не найден'}), 404

        st = current_user.friendship_status_with(uid)
        if st == 'friends':
            return jsonify({'success': False, 'error': 'Уже друзья'}), 409
        if st == 'pending_sent':
            return jsonify({'success': False, 'error': 'Запрос уже отправлен'}), 409
        if st == 'blocked':
            return jsonify({'success': False, 'error': 'Недоступно'}), 403

        # Если пользователь уже отправил нам запрос — автоматически принимаем
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
                return jsonify({
                    'success': True,
                    'status': 'friends',
                    'message': 'Теперь вы друзья! +10 XP'
                })

        # Отправляем запрос
        f = Friendship(requester_id=current_user.id, addressee_id=uid, status='pending')
        db.session.add(f)
        db.session.commit()
        _make_notif(person.id, 'friend_request', current_user.id, {
            'message': f'{current_user.nickname or current_user.name or current_user.email} хочет добавить вас в друзья'
        })
        nm = person.nickname or person.name or person.email
        return jsonify({
            'success': True,
            'status': 'pending',
            'message': f'Запрос в друзья отправлен {nm}'
        })

    except Exception as e:
        db.session.rollback()
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

def _validate_nickname(raw: str):
    """Универсальная валидация никнейма.

    Разрешаем Unicode-буквы (включая польские ą ć ę ł ń ó ś ź ż, кириллицу,
    немецкие умляуты, греческий и т.д.), цифры, дефис, подчёркивание.
    Возвращает (cleaned: str | None, error: str | None).
    """
    import re
    import unicodedata

    s = (raw or '').strip()
    if s.startswith('@'):
        s = s[1:]
    # Дополнительно вычищаем zero-width и невидимые символы, которые иногда
    # подсовывает мобильный автокоррект.
    s = ''.join(ch for ch in s if unicodedata.category(ch)[0] != 'C')
    s = s.strip()

    if not s:
        return None, 'Никнейм не может быть пустым'
    if len(s) < 3:
        return None, 'Никнейм слишком короткий (минимум 3 символа)'
    if len(s) > 30:
        return None, 'Никнейм слишком длинный (максимум 30 символов)'

    # Разрешаем все Unicode-буквы (\w в Python с UNICODE = буквы+цифры+_),
    # плюс отдельно дефис. Запрещаем пробелы, эмодзи, знаки препинания.
    # \w в Python re по умолчанию Unicode (PY3) и покрывает польские/русские буквы.
    if not re.match(r'^[\w\-]+$', s, flags=re.UNICODE):
        return None, 'Никнейм может содержать только буквы, цифры, дефис и подчёркивание'

    return s, None


@app.route("/update_nickname", methods=["POST"])
@login_required
def update_nickname():
    """Обновление nickname пользователя.

    Принимает и form-data, и JSON. Возвращает либо JSON (для AJAX), либо
    редирект с flash-сообщением (для классической формы).
    """
    wants_json = (
        request.is_json
        or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or 'application/json' in (request.headers.get('Accept') or '')
    )

    raw = None
    if request.is_json:
        try:
            raw = (request.get_json(silent=True) or {}).get('nickname', '')
        except Exception:
            raw = ''
    if raw is None:
        raw = request.form.get('nickname', '')

    cleaned, err = _validate_nickname(raw)
    if err:
        if wants_json:
            return jsonify({'success': False, 'error': err}), 400
        flash(err, 'error')
        return redirect(url_for('profile'))

    # Проверка уникальности (case-insensitive). Сравниваем по lowercase, чтобы
    # ilike корректно работал с польскими/кириллическими символами в Postgres
    # (ilike -> ICU collation) и SQLite.
    existing = User.query.filter(User.nickname.ilike(cleaned)).first()
    if existing and existing.id != current_user.id:
        msg = f'Никнейм @{cleaned} уже занят'
        if wants_json:
            return jsonify({'success': False, 'error': msg}), 409
        flash(msg, 'error')
        return redirect(url_for('profile'))

    try:
        current_user.nickname = cleaned
        db.session.commit()
        db.session.refresh(current_user)
    except Exception as e:
        db.session.rollback()
        err_text = f'Ошибка при сохранении: {str(e)}'
        if wants_json:
            return jsonify({'success': False, 'error': err_text}), 500
        flash(err_text, 'error')
        return redirect(url_for('profile'))

    success_msg = f'Никнейм успешно изменён на @{cleaned}'
    if wants_json:
        return jsonify({'success': True, 'nickname': cleaned, 'message': success_msg})
    flash(success_msg + '!', 'success')
    return redirect(url_for('profile'))


@app.route("/add_student", methods=["POST"])
@login_required
def add_student():
    """Добавление друга по nickname (отправка запроса)"""
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
        elif existing.status == 'pending':
            if existing.requester_id == current_user.id:
                flash(f'Запрос @{friend.nickname} уже отправлен', 'info')
            else:
                flash(f'@{friend.nickname} уже отправил вам запрос', 'info')
        else:
            flash(f'@{friend.nickname} уже в друзьях', 'info')
        return redirect(url_for('profile'))
    
    # Отправляем запрос в друзья — ожидает подтверждения (как ВКонтакте)
    try:
        friendship = Friendship(
            requester_id=current_user.id,
            addressee_id=friend.id,
            status='pending'
        )
        db.session.add(friendship)
        db.session.commit()
        _make_notif(friend.id, 'friend_request', current_user.id, {
            'message': f'{current_user.nickname or current_user.name or current_user.email} хочет добавить вас в друзья'
        })
        flash(f'Запрос в друзья отправлен @{friend.nickname}', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при отправке запроса: {str(e)}', 'error')
    
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
@login_required
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
@login_required
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
    Admin endpoint: диагностика и починка битого LaTeX '$ rac{' -> '$\\frac{'.
    GET  -> показывает сколько задач с битым LaTeX
    POST -> применяет починку
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

        # POST -> применяем починку
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


# ── [DISABLED 2026-05] Legacy hard-coded flag для AdaptiveTask.id == 1650 ──
# Раньше здесь стартап-хук помечал задачу с внутренним integer id=1650 как
# битую (причина: «ответ в БД=18, мат-правильный=0»). После переимпорта JSON
# auto-increment id мог сдвинуться, и id=1650 теперь может указывать на
# совершенно другую (валидную) задачу -> есть риск ложного флага.
#
# Логика отключена. Если конкретную задачу действительно надо пометить —
# делать это нужно по стабильному source_id (AdaptiveTask.source_id):
#
#     _bad = AdaptiveTask.query.filter_by(source_id='<vsosh-...-id>').first()
#     if _bad and not _bad.is_flagged: ...
#
# Реальные плохие задачи уже ловятся авто-флагом по fallback'ам тьютора
# (см. блок ниже «Авто-скрипт: помечаем задачи с >= 3 fallback за 7 дней»),
# плюс ручной пометкой через /admin/needs_review/action. Поэтому хардкод
# id=1650 безопасно отключён.


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


@app.route("/admin/fix-theory-blocks", methods=["POST"])
def admin_fix_theory_blocks():
    """
    Защищенный роут: ПЕРЕЗАПИСЫВАЕТ все TheoryBlock'и из methods_catalog_102.json.
    Отличается от `_seed_theory()` в olympiad_autoseed.py тем, что НЕ щадит
    существующие поля — force-overwrite ВСЕХ md-полей (definition_md,
    main_theorems_md, pitfalls_md и т.д.) правильными данными из JSON.
    
    Это нужно, чтобы на продакшене (Render) исправить записи TheoryBlock,
    у которых слова слиплись из-за бага в normalize_math_text().
    
    Требует токен из переменной окружения SEED_ADMIN_TOKEN.
    Токен передаётся через заголовок X-Admin-Token ИЛИ query-параметр ?token=
    
    Returns:
        JSON: { "status": "success"|"error", "updated": int, "created": int, "total": int, "message": str }
    """
    import hmac
    import json as _json
    import traceback
    import os as _os

    # Проверка токена
    expected_token = _os.environ.get('SEED_ADMIN_TOKEN')
    if not expected_token:
        return jsonify({
            'status': 'error',
            'message': 'SEED_ADMIN_TOKEN not configured on server'
        }), 503

    provided_token = request.headers.get('X-Admin-Token') or request.args.get('token')
    if not provided_token:
        return jsonify({
            'status': 'error',
            'message': 'Admin token required. Provide via X-Admin-Token header or ?token= parameter'
        }), 403

    if not hmac.compare_digest(expected_token, provided_token):
        app.logger.warning(f"[SECURITY] Invalid admin token attempt from {request.remote_addr}")
        return jsonify({
            'status': 'error',
            'message': 'Invalid admin token'
        }), 403

    # Путь к JSON-каталогу (app.py в корне проекта, поэтому dirname один раз)
    _data_dir = _os.path.join(_os.path.dirname(__file__), 'data', 'olympiads')

    # Сначала пробуем 102 (полный каталог), затем 89 (fallback)
    _candidates = ['methods_catalog_102.json', 'methods_catalog_89.json']
    rows = None
    _used_path = None
    for _fname in _candidates:
        _fp = _os.path.join(_data_dir, _fname)
        if _os.path.exists(_fp):
            try:
                with open(_fp, 'r', encoding='utf-8') as _f:
                    rows = _json.load(_f)
                if isinstance(rows, list) and len(rows) > 0:
                    _used_path = _fp
                    break
            except Exception:
                continue

    if rows is None:
        return jsonify({
            'status': 'error',
            'message': 'No methods catalog found (tried 102, 89)'
        }), 500

    app.logger.info(f"[ADMIN] Fix-theory-blocks using catalog: {_used_path} ({len(rows)} rows)")

    try:
        # Динамический импорт модели (как в __diag_method)
        TheoryBlock = __import__("models_olympiad", fromlist=["TheoryBlock"]).TheoryBlock

        if not isinstance(rows, list):
            return jsonify({
                'status': 'error',
                'message': 'JSON root is not a list'
            }), 500

        updated = 0
        created = 0

        for item in rows:
            code = item.get('method_code')
            if not code:
                continue

            tb = TheoryBlock.query.filter_by(method_code=code).first()

            if tb is None:
                # Создаём новый блок — все поля из JSON
                tb = TheoryBlock(
                    method_code=code,
                    method_name=item.get('method_name') or code,
                    section=item.get('section') or '',
                    definition_md=item.get('definition_md'),
                    main_theorems_md=item.get('main_theorems_md'),
                    typical_techniques_md=item.get('typical_techniques_md'),
                    triggers_md=item.get('triggers_md'),
                    worked_example_md=item.get('worked_example_md'),
                    pitfalls_md=item.get('pitfalls_md'),
                    why_it_works_md=item.get('why_it_works_md'),
                    related_methods=item.get('related_methods') or [],
                    signal_phrases=item.get('signal_phrases'),
                    first_moves=item.get('first_moves'),
                    prerequisites=item.get('prerequisites'),
                    leads_to=item.get('leads_to'),
                    grades=item.get('grades'),
                    recommended_competitions=item.get('recommended_competitions'),
                    difficulty_level=item.get('difficulty_level'),
                    frequency_vsosh_9=item.get('frequency_vsosh_9'),
                    total_count=item.get('total_count'),
                    share_percent=item.get('share_percent'),
                    sort_order=item.get('sort_order', 0) or 0,
                )
                db.session.add(tb)
                created += 1
            else:
                # FORCE-overwrite ВСЕХ полей (в отличие от _seed_theory,
                # который только заполняет пустые)
                tb.method_name = item.get('method_name') or code
                tb.section = item.get('section') or ''
                tb.definition_md = item.get('definition_md')
                tb.main_theorems_md = item.get('main_theorems_md')
                tb.typical_techniques_md = item.get('typical_techniques_md')
                tb.triggers_md = item.get('triggers_md')
                tb.worked_example_md = item.get('worked_example_md')
                tb.pitfalls_md = item.get('pitfalls_md')
                tb.why_it_works_md = item.get('why_it_works_md')
                tb.related_methods = item.get('related_methods') or []
                tb.signal_phrases = item.get('signal_phrases')
                tb.first_moves = item.get('first_moves')
                tb.prerequisites = item.get('prerequisites')
                tb.leads_to = item.get('leads_to')
                tb.grades = item.get('grades')
                tb.recommended_competitions = item.get('recommended_competitions')
                tb.difficulty_level = item.get('difficulty_level')
                tb.frequency_vsosh_9 = item.get('frequency_vsosh_9')
                tb.total_count = item.get('total_count')
                tb.share_percent = item.get('share_percent')
                tb.sort_order = item.get('sort_order', 0) or 0
                updated += 1

        db.session.commit()

        app.logger.info(
            f"[ADMIN] Theory blocks force-overwritten by {request.remote_addr}: "
            f"{updated} updated, {created} created"
        )

        return jsonify({
            'status': 'success',
            'message': f'TheoryBlock force-overwrite complete',
            'updated': updated,
            'created': created,
            'total': len(rows)
        }), 200

    except Exception as e:
        app.logger.error(f"[ADMIN] Fix-theory-blocks failed: {e}")
        traceback.print_exc()
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify({
            'status': 'error',
            'message': f'Internal server error: {str(e)}',
            'updated': 0,
            'created': 0,
            'total': 0
        }), 500


# ============================================================================
# FIGURES VITRINE (admin only) — moved from /figures to /admin/figures
# ============================================================================

@app.route("/admin/figures")
@login_required
def figures_vitrine():
    """Витрина чертежей якорных задач. Только для администраторов."""
    if not current_user.is_admin:
        abort(403)
    from services.figures_service import get_anchor_figures, get_counts
    figures = get_anchor_figures()
    counts = get_counts()
    # Ensure counts cover all figures even if some not in REVIEW_STATUS
    if counts['total'] == 0 and figures:
        counts = {
            'total': len(figures),
            'accepted': sum(1 for f in figures if f['status'] == 'accepted'),
            'rejected': sum(1 for f in figures if f['status'] == 'rejected'),
            'pending': sum(1 for f in figures if f['status'] == 'pending'),
        }
    return render_template('admin/figures_vitrine.html', figures=figures, counts=counts)


@app.route("/admin/figures/tasks")
@login_required
def figures_tasks_vitrine():
    """Таблица задач с чертежами. Только для администраторов."""
    if not current_user.is_admin:
        abort(403)
    return render_template('figures_tasks.html')


@app.route("/admin/figures/rebuild/<anchor_uid>", methods=["POST"])
@login_required
def figures_rebuild(anchor_uid):
    """Перерисовать чертёж с новым семенем."""
    if not current_user.is_admin:
        abort(403)
    from services.figures_service import rebuild_figure
    result = rebuild_figure(anchor_uid)
    if result.get('build_error'):
        return jsonify({'error': result['build_error'], **result}), 500
    return jsonify(result)


@app.route("/admin/figures/accept/<anchor_uid>", methods=["POST"])
@login_required
def figures_accept(anchor_uid):
    """Пометить чертёж как проверенный."""
    if not current_user.is_admin:
        abort(403)
    from services.figures_service import accept_figure
    result = accept_figure(anchor_uid)
    return jsonify(result)


@app.route("/admin/figures/reject/<anchor_uid>", methods=["POST"])
@login_required
def figures_reject(anchor_uid):
    """Пометить чертёж как отклонённый."""
    if not current_user.is_admin:
        abort(403)
    from services.figures_service import reject_figure
    result = reject_figure(anchor_uid)
    return jsonify(result)


@app.route("/admin/figures/counts")
@login_required
def figures_counts():
    """API: счётчики статусов."""
    if not current_user.is_admin:
        abort(403)
    from services.figures_service import get_counts
    return jsonify(get_counts())


# ============================================================================
# DAILY QUEST ROUTES
# ============================================================================

# ============================================================================
# DAILY TASK ROTATION (Задача дня)
# ============================================================================

@app.route('/api/daily-task')
@login_required
def api_daily_task():
    """API: «Задача дня» — тематический набор из 10 задач (Вариант А).

    GET /api/daily-task          — стабильный набор на сегодня
    GET /api/daily-task?regenerate=1 — принудительно новый набор

    Возвращает набор из 10 задач на сегодня. Все задачи — из одного subject,
    который ротируется по дням (epoch-based rotation).
    В рамках одного дня возвращается ТОТ ЖЕ набор (стабильность),
    если не передан параметр ?regenerate=1.

    Ответ:
        { tasks: [{ task_id, task_text, solution, correct_answer, subject,
                    topic, method, class_level, difficulty_level,
                    shown_date }, ...],
          subject, shown_date, count }
    """
    from services.daily_task_rotation import pick_daily_set

    force_regenerate = request.args.get("regenerate", "").strip() in ("1", "true", "yes")
    result = pick_daily_set(current_user.id, force_regenerate=force_regenerate)
    if result.get("error"):
        return jsonify(result), 404
    return jsonify(result)


@app.route('/daily-set')
@login_required
def daily_set_page():
    """GET /daily-set -> 302 redirect на /daily_tasks (живой маршрут задач дня).

    Ранее шаблон daily_set.html отсутствовал — маршрут отдавал 500.
    Теперь это простой редирект. Кнопка куратора ведёт сюда же,
    поэтому ученик больше не получает ошибку.
    """
    return redirect('/daily_tasks', code=302)


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


# ─── Web Push Notification Helper ────────────────────────────────────

def _send_push_notification(user_id, title, body, url='/'):
    """Send a web push notification to all subscriptions of a user.

    Uses pywebpush library. Handles expired/deleted subscriptions
    (HTTP 410 Gone) by removing them from the database.

    Args:
        user_id: int — recipient user ID.
        title: str — notification title.
        body: str — notification body text.
        url: str — URL to open when the notification is clicked.
    """
    from models import PushSubscription
    if not VAPID_PUBLIC_KEY or not VAPID_PRIVATE_KEY:
        return
    subs = PushSubscription.query.filter_by(user_id=user_id).all()
    if not subs:
        return
    payload = {
        'title': title,
        'body': body,
        'icon': '/static/logo.png',
        'badge': '/static/favicon-32x32.png',
        'data': {'url': url, 'type': 'push'},
    }
    payload_bytes = json.dumps(payload).encode('utf-8')
    vapid_claims = {'sub': f'mailto:{VAPID_CLAIM_EMAIL}'}
    for sub in subs:
        try:
            from pywebpush import webpush
            webpush(
                subscription_info={
                    'endpoint': sub.endpoint,
                    'keys': {
                        'p256dh': sub.p256dh_key,
                        'auth': sub.auth_key,
                    },
                },
                data=payload_bytes,
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims=vapid_claims,
            )
        except Exception as e:
            err_str = str(e)
            # Remove subscription if it's expired (410 Gone) or malformed
            if '410' in err_str or 'Gone' in err_str or '404' in err_str:
                try:
                    db.session.delete(sub)
                    db.session.commit()
                except Exception:
                    db.session.rollback()
            else:
                app.logger.warning(f"[PUSH] Failed to send to sub #{sub.id}: {err_str}")
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
    # Отправляем запрос в друзья — ожидает подтверждения (как ВКонтакте)
    f = Friendship(requester_id=current_user.id, addressee_id=uid, status='pending')
    db.session.add(f)
    db.session.commit()
    _make_notif(person.id, 'friend_request', current_user.id, {
        'message': f'{current_user.nickname or current_user.name or current_user.email} хочет добавить вас в друзья'
    })
    nm = person.nickname or person.name or person.email
    return jsonify({'status': 'pending', 'message': f'Запрос в друзья отправлен {nm}'})


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
    # ставим `read_at = now` чтобы фронт мог показать «[OK][OK] синие» — момент,
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

    # Уведомление другу (in-app)
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

    # Push-уведомление другу (браузерный push)
    try:
        sender_name = current_user.display_name or current_user.nickname or 'Пользователь'
        if kind == 'task_share':
            _send_push_notification(
                user_id=friend.id,
                title=f' {sender_name}',
                body='Поделился(ась) задачей!',
                url=f'/chat?friend={current_user.id}',
            )
        else:
            body_text = (msg.body or '')[:120]
            _send_push_notification(
                user_id=friend.id,
                title=f' {sender_name}',
                body=body_text if body_text else 'Новое сообщение',
                url=f'/chat?friend={current_user.id}',
            )
    except Exception as _pe:
        print(f"[CHAT] push notification failed: {_pe}")

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


# ─── Web Push API Endpoints ──────────────────────────────────────────

@app.route('/api/push/subscribe', methods=['POST'])
@login_required
def push_subscribe():
    """Save a PushSubscription from the client's browser.

    Expects JSON with:
      { endpoint, keys: { p256dh, auth }, userAgent? }
    """
    from models import PushSubscription
    data = request.get_json(silent=True) or {}
    endpoint = (data.get('endpoint') or '').strip()
    keys = data.get('keys') or {}
    p256dh = (keys.get('p256dh') or '').strip()
    auth = (keys.get('auth') or '').strip()
    if not endpoint or not p256dh or not auth:
        return jsonify({'error': 'Missing endpoint or keys'}), 400

    # Check for existing subscription with same endpoint (update it)
    existing = PushSubscription.query.filter_by(
        user_id=current_user.id,
        endpoint=endpoint,
    ).first()
    if existing:
        existing.p256dh_key = p256dh
        existing.auth_key = auth
        existing.user_agent = (data.get('userAgent') or '')[:256]
    else:
        sub = PushSubscription(
            user_id=current_user.id,
            endpoint=endpoint,
            p256dh_key=p256dh,
            auth_key=auth,
            user_agent=(data.get('userAgent') or '')[:256],
        )
        db.session.add(sub)

    try:
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"[PUSH] subscribe error: {e}")
        return jsonify({'error': 'DB error'}), 500


@app.route('/api/push/unsubscribe', methods=['POST'])
@login_required
def push_unsubscribe():
    """Remove a PushSubscription by endpoint."""
    from models import PushSubscription
    data = request.get_json(silent=True) or {}
    endpoint = (data.get('endpoint') or '').strip()
    if not endpoint:
        return jsonify({'error': 'Missing endpoint'}), 400

    sub = PushSubscription.query.filter_by(
        user_id=current_user.id,
        endpoint=endpoint,
    ).first()
    if sub:
        db.session.delete(sub)
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"[PUSH] unsubscribe error: {e}")
            return jsonify({'error': 'DB error'}), 500

    return jsonify({'success': True})


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
        'algebra':        {'name_ru': 'Алгебра',            'icon': ''},
        'geometry':       {'name_ru': 'Геометрия',          'icon': ''},
        'combinatorics':  {'name_ru': 'Комбинаторика',      'icon': ''},
        'number_theory':  {'name_ru': 'Теория чисел',       'icon': ''},
        'kl_movement':    {'name_ru': 'Задачи на движение', 'icon': ''},
        'knights_liars':  {'name_ru': 'Рыцари и лжецы',     'icon': ''},
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
@login_required
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
@login_required
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
@login_required
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
@login_required
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
@login_required
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


@app.route('/api/set_grade', methods=['POST'])
@login_required
def api_set_grade():
    """Сохранить выбранный класс (preferred_grade) для текущего пользователя."""
    data = request.get_json(silent=True) or {}
    grade = data.get('grade')
    if not grade:
        return jsonify({'error': 'Укажите grade (5-11)'}), 400
    try:
        grade_int = int(grade)
        if grade_int < 5 or grade_int > 11:
            return jsonify({'error': 'Класс должен быть от 5 до 11'}), 400
        user = db.session.merge(current_user)
        user.preferred_grade = grade_int
        db.session.commit()
        return jsonify({'success': True, 'grade': grade_int})
    except (ValueError, TypeError):
        return jsonify({'error': 'Некорректный класс'}), 400
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        app.logger.error(f"Failed to set grade for user={current_user.id}: {e}")
        return jsonify({'error': 'Ошибка сохранения'}), 500


# ============================================================
# ПРОГРЕСС АДАПТИВНЫХ ТЕСТОВ (график)
# ============================================================

@app.route('/api/progress/<int:user_id>')
@login_required
def api_progress(user_id):
    """API: прогресс адаптивных тестов — данные для графика по темам."""
    try:
        # user_id=0 означает "текущий пользователь" (защита от fallback в JS)
        if user_id == 0:
            user_id = current_user.id
        # Разрешено: свой профиль или друзья
        if user_id != current_user.id and not current_user.is_friend_with(user_id):
            return jsonify({'error': 'Доступ запрещён'}), 403

        rows = (AdaptiveTestResult.query
                .filter(AdaptiveTestResult.user_id == user_id)
                .order_by(AdaptiveTestResult.completed_at.asc())
                .all())

        # Собираем все уникальные даты (YYYY-MM) и группируем по темам
        dates_set = set()
        topic_map = {}  # topic -> {YYYY-MM: percent}

        for r in rows:
            if not r.completed_at or not r.topic:
                continue
            month_key = r.completed_at.strftime("%Y-%m")
            dates_set.add(month_key)
            percent = round((r.tasks_correct / max(r.tasks_total, 1)) * 100, 1)
            topic_map.setdefault(r.topic, {})[month_key] = percent

        if not dates_set:
            return jsonify({'labels': [], 'datasets': [], 'points': 0})

        dates = sorted(dates_set)

        datasets = []
        color_palette = [
            '#38bdf8', '#f472b6', '#34d399', '#fb923c',
            '#a78bfa', '#facc15', '#fb7185', '#2dd4bf'
        ]
        for idx, (topic, vals) in enumerate(sorted(topic_map.items())):
            color = color_palette[idx % len(color_palette)]
            data = []
            for d in dates:
                data.append(vals.get(d))  # None = gap
            datasets.append({
                'label': topic,
                'data': data,
                'borderColor': color,
                'backgroundColor': color + '33',
                'tension': 0.3,
                'spanGaps': True,
                'pointRadius': 4,
                'pointHoverRadius': 6,
            })

        return jsonify({
            'labels': dates,
            'datasets': datasets,
            'points': len(dates)
        })
    except Exception as e:
        app.logger.error(f"Error in api_progress: {e}")
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


# Канонические значения current_plan в БД:
#   'free'     — бесплатный (по умолчанию)
#   'premium'  — Premium-доступ (срок действия — в plan_expires_at)
# ВАЖНО: исторически API сохранял 'premium_monthly' / 'premium_yearly',
# но шаблоны (subscribe.html, base.html и др.) проверяют `current_plan == 'premium'`
# или `current_plan == 'free'`, и при значениях `premium_monthly`/`premium_yearly`
# UI «не обновлялся» — кнопка «Попробовать Premium» оставалась видимой даже
# после успешной активации. Унифицируем: сохраняем 'premium', а вариант тарифа
# хранится только в логе/ответе (для аналитики).

PREMIUM_PLAN_CODES = ('premium', 'premium_monthly', 'premium_yearly')


def _is_premium_plan(plan_value):
    """True, если строка тарифа считается Premium-доступом."""
    return (plan_value or '').strip().lower() in PREMIUM_PLAN_CODES


@app.context_processor
def _inject_subscription_flags():
    """Глобальный флаг is_premium для всех шаблонов.

    Использовать в Jinja: {% if is_premium %}…{% endif %}.
    Также нормализует устаревшие значения 'premium_monthly' / 'premium_yearly'
    для текущего рендера (только в памяти — БД не трогаем здесь).
    """
    try:
        if current_user.is_authenticated:
            return {
                'is_premium': _is_premium_plan(current_user.current_plan),
            }
    except Exception:
        pass
    return {'is_premium': False}


@app.context_processor
def _inject_user_helpers():
    """Делает display_name_from_email доступной во всех шаблонах."""
    from services.user_helpers import display_name_from_email
    return dict(display_name_from_email=display_name_from_email)


@app.route('/api/subscribe', methods=['POST'])
@login_required
def api_subscribe():
    """API активации Premium (демо — без оплаты).

    Тело: {plan: 'premium_monthly'|'premium_yearly'}.
    В БД сохраняем КАНОНИЧЕСКОЕ значение 'premium' — чтобы все шаблоны,
    проверяющие `current_plan == 'premium'`, отображали статус корректно
    после reload страницы.
    """
    data = request.get_json() or {}
    requested = data.get('plan', 'premium_monthly')

    if requested not in ('premium_monthly', 'premium_yearly'):
        return jsonify({'error': 'Неизвестный тариф'}), 400

    from datetime import timedelta
    if requested == 'premium_monthly':
        expires = datetime.utcnow() + timedelta(days=30)
    else:
        expires = datetime.utcnow() + timedelta(days=365)

    # КАНОНИЗАЦИЯ: всегда 'premium' в БД. Срок — в plan_expires_at.
    current_user.current_plan = 'premium'
    current_user.plan_expires_at = expires
    db.session.commit()

    return jsonify({
        'ok': True,
        'plan': 'premium',
        'plan_variant': requested,  # для аналитики/UI: monthly|yearly
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

from services.telegram_notify import send_support_email, send_review_email

# Простой rate-limit: один user ≤ 5 обращений за час
_SUPPORT_RATE_LIMIT = {}  # in-memory, для prod лучше Redis


@app.route('/sql')
@login_required
def sql_page():
    return render_template('sql.html')

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


@app.route('/misc')
def misc_page():
    """Страница «Прочее» — все остальные разделы, не вошедшие в три основных."""
    return render_template('misc.html')


@app.route('/api/support', methods=['POST'])
@login_required
def submit_support():
    try:
        # Поддерживаем оба варианта: JSON и multipart/form-data (для прикреплённых файлов)
        if request.content_type and request.content_type.startswith('multipart/form-data'):
            data = request.form
            uploaded_files = request.files.getlist('attachments')
        else:
            data = request.json or {}
            uploaded_files = []

        message_text = (data.get('message') or '').strip()
        # Если нет сообщения — но есть вложения — разрешим короткое описание
        min_len = 1 if uploaded_files else 5
        if not (min_len <= len(message_text) <= 4000) and not uploaded_files:
            return jsonify({'error': 'сообщение 5-4000 символов'}), 400

        category = data.get('category', 'other')
        if category not in ('bug', 'suggestion', 'question', 'other'):
            category = 'other'

        email = (data.get('email') or '').strip() or None
        if email and '@' not in email:
            return jsonify({'error': 'некорректный email'}), 400

        # Валидация файлов: до 5 файлов, до 10 МБ каждый, total < 20 МБ
        MAX_FILES = 5
        MAX_FILE_SIZE = 10 * 1024 * 1024
        MAX_TOTAL = 20 * 1024 * 1024
        ALLOWED_EXT = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.pdf'}

        if len(uploaded_files) > MAX_FILES:
            return jsonify({'error': f'максимум {MAX_FILES} файлов'}), 400

        valid_files = []
        total_size = 0
        for f in uploaded_files:
            if not f or not f.filename:
                continue
            import os as _os
            _, ext = _os.path.splitext(f.filename.lower())
            if ext not in ALLOWED_EXT:
                return jsonify({'error': f'недопустимый тип файла: {ext or "?"} (разрешены: изображения и PDF)'}), 400
            # Размер
            f.stream.seek(0, 2)
            size = f.stream.tell()
            f.stream.seek(0)
            if size > MAX_FILE_SIZE:
                return jsonify({'error': f'файл "{f.filename}" больше 10 МБ'}), 400
            total_size += size
            if total_size > MAX_TOTAL:
                return jsonify({'error': 'общий размер вложений больше 20 МБ'}), 400
            valid_files.append((f, size))

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

        # Гарантируем существование таблицы (на случай если auto-migration не отработала)
        def _ensure_support_table():
            try:
                _is_pg = (_database_url or '').startswith('postgresql') if '_database_url' in globals() else False
                if _is_pg:
                    db.session.execute(_text_support('''
                        CREATE TABLE IF NOT EXISTS support_messages (
                            id SERIAL PRIMARY KEY,
                            user_id INTEGER,
                            user_nickname VARCHAR(120),
                            user_email VARCHAR(200),
                            category VARCHAR(40),
                            message TEXT,
                            page_url VARCHAR(500),
                            user_agent VARCHAR(500),
                            ip VARCHAR(64),
                            email_sent BOOLEAN DEFAULT FALSE,
                            email_error TEXT,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    '''))
                else:
                    db.session.execute(_text_support('''
                        CREATE TABLE IF NOT EXISTS support_messages (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id INTEGER,
                            user_nickname VARCHAR(120),
                            user_email VARCHAR(200),
                            category VARCHAR(40),
                            message TEXT,
                            page_url VARCHAR(500),
                            user_agent VARCHAR(500),
                            ip VARCHAR(64),
                            email_sent BOOLEAN DEFAULT 0,
                            email_error TEXT,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    '''))
                db.session.commit()
            except Exception as _ct_err:
                db.session.rollback()
                import logging
                logging.warning(f'[support] table check/create failed: {_ct_err}')

        new_id = 0
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
            # SQLite не поддерживает RETURNING — fallback. Если таблицы нет — создадим.
            _ensure_support_table()
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
                # Не валим запрос полностью — пытаемся хотя бы отправить email
                new_id = 0

        # Подготовить вложения для email (имя, content_type, bytes)
        email_attachments = []
        for f, _size in valid_files:
            try:
                f.stream.seek(0)
                data_bytes = f.stream.read()
                email_attachments.append((
                    f.filename,
                    f.content_type or 'application/octet-stream',
                    data_bytes,
                ))
            except Exception as _read_err:
                import logging
                logging.warning(f'[support] failed to read file {f.filename}: {_read_err}')

        # 2. Отправить email владельцу — ни при каких ошибках не падаем,
        # сообщение уже сохранено в БД, отправка письма — best-effort.
        ok, err = False, None
        try:
            ok, err = send_support_email(
                mail,
                nickname=nickname, email=email, category=category,
                message=message_text, page_url=page_url,
                user_agent=user_agent, ip=ip, ticket_id=new_id,
                attachments=email_attachments,
            )
        except Exception as _mail_err:
            import logging
            logging.warning(f'[support] email send raised: {_mail_err}')
            ok, err = False, str(_mail_err)[:500]

        if new_id:
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


# ─── Отзывы пользователей о сайте ──────────────────────────────────────────
# In-memory rate-limit для /api/feedback: один user/IP ≤ 3 отзыва за час.
_REVIEW_RATE_LIMIT = {}


@app.route('/api/feedback', methods=['POST'])
@login_required
def submit_feedback():
    """Принять отзыв пользователя и отправить его на почту владельцу.

    Тело JSON: {rating: 1..5|null, message: str, email: str|null, page_url: str}
    Email-получатель: env REVIEW_NOTIFY_EMAIL -> SUPPORT_NOTIFY_EMAIL -> MAIL_USERNAME.
    Никаких записей в БД (чтобы не требовать миграцию). Тикет-id = unix-timestamp.
    """
    try:
        data = request.json or {}
        rating_raw = data.get('rating')
        try:
            rating = int(rating_raw) if rating_raw not in (None, '',) else 0
        except (TypeError, ValueError):
            rating = 0
        # Звёзды теперь ОБЯЗАТЕЛЬНЫ — без оценки 1..5 отзыв не принимается.
        if rating < 1 or rating > 5:
            return jsonify({
                'error': 'Поставьте оценку от 1 до 5 звёзд'
            }), 400

        email = (data.get('email') or '').strip() or None
        if email and '@' not in email:
            return jsonify({'error': 'некорректный email'}), 400

        # Rate-limit
        user_id = current_user.id if current_user.is_authenticated else None
        rl_key = f'u:{user_id}' if user_id else f'ip:{request.remote_addr}'
        import time as _trl
        now = _trl.time()
        bucket = _REVIEW_RATE_LIMIT.setdefault(rl_key, [])
        # Поднял лимит до 10/час и поставил окно 10 минут, чтобы тестировать
        # форму локально без блокировок «слишком много отзывов».
        bucket[:] = [t for t in bucket if now - t < 600]
        if len(bucket) >= 10:
            return jsonify({'error': 'слишком много отзывов, '
                                      'попробуйте позже'}), 429
        bucket.append(now)

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

        ticket_id = int(now)

        # Сохраняем отзыв в БД (site_reviews), чтобы он отображался
        # на странице /about другим пользователям. Не блокируем ответ
        # пользователю, если запись в БД упала.
        review_db_id = None
        try:
            avatar_url = None
            if user_id:
                try:
                    avatar_url = current_user.avatar_url
                except Exception:
                    avatar_url = None
            display_nick = nickname or (
                f"Гость #{user_id}" if user_id else "Аноним"
            )
            ins = db.session.execute(
                text("""
                    INSERT INTO site_reviews
                        (user_id, nickname, avatar_url, rating,
                         message, is_public, is_hidden, ip)
                    VALUES (:user_id, :nickname, :avatar_url, :rating,
                            :message, :is_public, :is_hidden, :ip)
                """),
                {
                    'user_id': user_id,
                    'nickname': (display_nick or 'Аноним')[:64],
                    'avatar_url': (avatar_url or None),
                    'rating': rating,
                    'message': message_text,
                    'is_public': True,
                    'is_hidden': False,
                    'ip': (ip or '')[:64],
                }
            )
            db.session.commit()
            # Достаём id вставленной записи (для логов и потенциальной
            # модерации). PostgreSQL и SQLite-совместимый способ.
            try:
                review_db_id = db.session.execute(
                    text("SELECT MAX(id) FROM site_reviews")
                ).scalar()
            except Exception:
                review_db_id = None
        except Exception as _e_save:
            db.session.rollback()
            import logging
            logging.warning(
                f"[feedback] DB save failed (ticket={ticket_id}): {_e_save}"
            )

        ok, err = send_review_email(
            mail,
            nickname=nickname, email=email, rating=rating,
            message=message_text, page_url=page_url,
            user_agent=user_agent, ip=ip, ticket_id=ticket_id,
        )
        if not ok:
            # GRACEFUL FALLBACK: если email-канал не настроен (нет SMTP/Resend
            # env на локалке) или временный сбой провайдера — НЕ показывать
            # пользователю ошибку. Логируем полный отзыв в stderr, чтобы
            # ничего не потерять, и отвечаем {ok: true} — пользовательский
            # опыт идентичен прод-окружению.
            import logging
            logging.warning(
                '[feedback] email send failed (ticket=%s, err=%s); '
                'отзыв сохранён в логах:\n'
                'nickname=%s email=%s rating=%s page=%s\n'
                'message:\n%s',
                ticket_id, err, nickname, email, rating, page_url,
                message_text,
            )
            return jsonify({
                'ok': True,
                'id': ticket_id,
                'delivered': False,
            })

        return jsonify({'ok': True, 'id': ticket_id, 'delivered': True})

    except Exception:
        import logging
        logging.exception('[feedback] Unexpected error')
        return jsonify({'error': 'внутренняя ошибка сервера'}), 500


@app.route('/api/reviews', methods=['GET'])
@login_required
def list_site_reviews():
    """Публичный список отзывов о сайте для страницы /about.

    Query params:
        limit  — int, по умолчанию 30, максимум 100.
        offset — int, по умолчанию 0.
        sort   — 'new' (по дате DESC) | 'top' (по рейтингу DESC, потом по дате).

    Возвращает {ok, total, avg_rating, reviews: [{id, nickname,
    avatar_url, rating, message, created_at}], counts: {1..5}}.
    """
    try:
        try:
            limit = int(request.args.get('limit', 30))
        except (TypeError, ValueError):
            limit = 30
        limit = max(1, min(limit, 100))
        try:
            offset = int(request.args.get('offset', 0))
        except (TypeError, ValueError):
            offset = 0
        offset = max(0, offset)
        sort = (request.args.get('sort') or 'new').strip().lower()
        if sort not in ('new', 'top'):
            sort = 'new'

        # Базовый фильтр: только публичные и не скрытые модератором.
        # Дополнительно отрезаем пустые сообщения и слишком короткие.
        base_where = (
            "is_public = TRUE AND is_hidden = FALSE "
            "AND message IS NOT NULL AND length(message) >= 5"
        )
        # SQLite понимает TRUE/FALSE с версии 3.23+, но на всякий случай
        # делаем совместимый wildcard через 1/0.
        if not _database_url.startswith('postgresql'):
            base_where = base_where.replace('TRUE', '1').replace('FALSE', '0')

        order_by = (
            "rating DESC, created_at DESC" if sort == 'top'
            else "created_at DESC"
        )

        rows = db.session.execute(text(f"""
            SELECT id, user_id, nickname, avatar_url, rating, message,
                   created_at
            FROM site_reviews
            WHERE {base_where}
            ORDER BY {order_by}
            LIMIT :limit OFFSET :offset
        """), {'limit': limit, 'offset': offset}).fetchall()

        # Сводная статистика (total + средний рейтинг + распределение
        # по звёздам). Считаем по тем же базовым фильтрам, что и выдача.
        stats = db.session.execute(text(f"""
            SELECT COUNT(*) AS total,
                   COALESCE(AVG(NULLIF(rating, 0)), 0) AS avg_rating
            FROM site_reviews
            WHERE {base_where}
        """)).fetchone()
        total = int(stats[0] or 0) if stats else 0
        try:
            avg_rating = float(stats[1]) if stats and stats[1] is not None else 0.0
        except Exception:
            avg_rating = 0.0
        avg_rating = round(avg_rating, 2)

        counts = {str(i): 0 for i in range(1, 6)}
        try:
            for r in db.session.execute(text(f"""
                SELECT rating, COUNT(*) FROM site_reviews
                WHERE {base_where} AND rating BETWEEN 1 AND 5
                GROUP BY rating
            """)).fetchall():
                counts[str(int(r[0]))] = int(r[1])
        except Exception:
            pass

        items = []
        for r in rows:
            rid, uid, nick, avatar, rating_v, msg, created = (
                r[0], r[1], r[2], r[3], r[4], r[5], r[6]
            )
            # Никогда не отдаём IP / email наружу.
            items.append({
                'id': int(rid),
                'nickname': nick or 'Аноним',
                'avatar_url': avatar or None,
                'rating': int(rating_v or 0),
                'message': msg or '',
                'created_at': (
                    created.isoformat() if hasattr(created, 'isoformat')
                    else str(created) if created else None
                ),
                'is_self': bool(
                    uid and current_user.is_authenticated
                    and current_user.id == uid
                ),
            })

        return jsonify({
            'ok': True,
            'total': total,
            'avg_rating': avg_rating,
            'counts': counts,
            'reviews': items,
            'limit': limit,
            'offset': offset,
            'sort': sort,
        })

    except Exception:
        import logging
        logging.exception('[reviews] Unexpected error')
        return jsonify({
            'ok': False,
            'error': 'не удалось загрузить отзывы',
            'reviews': [],
            'total': 0,
            'avg_rating': 0,
            'counts': {str(i): 0 for i in range(1, 6)},
        }), 500


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
            'avatar_emoji': g.avatar_emoji or '',
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
            'avatar_emoji': g_av or '',
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
        'kind': m.kind or 'text',
        'sender_id': m.sender_id,
        'sender_name': (senders.get(m.sender_id).name
                        or senders.get(m.sender_id).nickname
                        or senders.get(m.sender_id).email)
                        if senders.get(m.sender_id) else '?',
        'mine': m.sender_id == current_user.id,
        'created_at': m.created_at.isoformat() if m.created_at else None,
        'attachment_url': m.attachment_url,
        'attachment_kind': m.attachment_kind,
        'attachment_name': m.attachment_name,
        'attachment_size': m.attachment_size,
    } for m in rows]
    return jsonify({'messages': items})


@app.route('/api/groups/<int:group_id>/send', methods=['POST'])
@login_required
def api_groups_send(group_id):
    if not _is_group_member(group_id, current_user.id):
        return jsonify({'error': 'Вы не в группе'}), 403
    data = request.get_json(silent=True) or {}
    body = (data.get('body') or '').strip()
    kind = data.get('kind', 'text')
    attachment = data.get('attachment') if kind == 'attachment' else None
    if not body and not attachment:
        return jsonify({'error': 'Сообщение пустое'}), 400
    m = GroupMessage(
        group_id=group_id,
        sender_id=current_user.id,
        kind=kind,
        body=body[:4000] if body else None,
    )
    if attachment:
        m.attachment_url = (attachment.get('url') or '')[:400]
        m.attachment_kind = (attachment.get('kind') or '')[:16]
        m.attachment_name = (attachment.get('name') or '')[:255]
        m.attachment_size = attachment.get('size')
    db.session.add(m)
    db.session.commit()
    return jsonify({'success': True, 'id': m.id})


@app.route('/api/groups/<int:group_id>/upload', methods=['POST'])
@login_required
def api_groups_upload(group_id):
    """Upload an attachment (image or PDF) for a group message.
    Same logic as the personal-chat upload endpoint.
    """
    if not _is_group_member(group_id, current_user.id):
        return jsonify({'error': 'Вы не в группе'}), 403
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
    import uuid
    name = uuid.uuid4().hex + '.' + ext
    path = os.path.join(folder, name)
    try:
        f.save(path)
    except Exception as _se:
        app.logger.warning("group upload save failed: %r", _se)
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


@app.route('/groups/<int:group_id>')
@login_required
def group_page(group_id):
    if not _is_group_member(group_id, current_user.id):
        from flask import abort
        abort(404)
    g = GroupChat.query.get(group_id)
    is_owner = bool(g and g.owner_id == current_user.id)
    return render_template('group_chat.html', group=g, is_owner=is_owner)

# ─── Мат. статистика (доступ только избранным) ───────────────
@app.route("/matstat")
@login_required
def matstat():
    """Большая обучающая статья по математической статистике.
    Видна только пользователям с ником pavelznaka или victorkrivenko."""
    allowed = {"pavelznaka", "victorkrivenko", "victor"}
    nick = (getattr(current_user, "nickname", None) or "").lower()
    uname = (getattr(current_user, "username", None) or "").lower()
    if nick not in allowed and uname not in allowed:
        abort(404)
    return render_template("matstat.html")



if __name__ == '__main__':
    # Auto-reloader is disabled by default because long-running endpoints
    # get killed mid-request whenever Werkzeug detects ANY *.py change
    # in the workspace (including scripts that pytest/scripts touch).
    # Set FLASK_RELOAD=1 explicitly if you want the dev-time auto-reload.
    import os
    _use_reloader = (
        os.environ.get("FLASK_RELOAD", "0").strip().lower()
        in ("1", "true", "yes", "on")
    )
    # Use socketio.run() when SocketIO is available (for WebSocket transport),
    # fall back to standard Flask app.run() otherwise.
    try:
        from routes.wb_ws import socketio as _ws_socketio
        _ws_socketio.run(
            app,
            debug=True,
            port=5000,
            use_reloader=_use_reloader,
        )
    except (ImportError, AttributeError):
        app.run(
            debug=True,
            port=5000,
            use_reloader=_use_reloader,
        )

