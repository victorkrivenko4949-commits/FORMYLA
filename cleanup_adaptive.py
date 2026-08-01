"""Полная очистка адаптивного теста: БД + файлы.

ЗАПУСКАТЬ ОСТОРОЖНО — данные не восстанавливаются!
Требуется явно указать путь к базе через CLEANUP_DB_PATH или --db-path.
Без этого скрипт отказывается работать, чтобы случайно не затереть рабочую базу.
"""

import os
import sys
import argparse
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

# ── 0. Mandatory DB path ───────────────────────────────────────────────
parser = argparse.ArgumentParser(description='Cleanup adaptive test data')
parser.add_argument('--db-path', type=str, default=None,
                    help='Path to the database file to clean (REQUIRED)')
args = parser.parse_args()

db_path = args.db_path or os.environ.get('CLEANUP_DB_PATH', '').strip()

if not db_path:
    print("=" * 60)
    print("ОШИБКА: путь к базе не указан!")
    print("=" * 60)
    print()
    print("Этот скрипт удаляет данные. Укажите путь явно:")
    print("  python cleanup_adaptive.py --db-path instance/test_cleanup.db")
    print("  или задайте переменную CLEANUP_DB_PATH")
    print()
    print("Рабочая база (instance/formyla.db) НЕ будет задета.")
    sys.exit(1)

if not os.path.isabs(db_path):
    db_path = os.path.join(BASE_DIR, db_path)

db_path = os.path.abspath(db_path)
print(f"Целевая БД: {db_path}")
print(f"Тип: {'SQLite' if db_path.endswith('.db') else 'определяется по расширению'}")

if not os.path.exists(db_path):
    print(f"ПРЕДУПРЕЖДЕНИЕ: файл {db_path} не существует, работаем с SQLAlchemy SQLite URI")

# ── 1. Resolve SQLAlchemy URI ─────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv()

# Set CLEANUP_DB_PATH as effective database for this run
if db_path.endswith('.db'):
    _effective_uri = 'sqlite:///' + db_path.replace('\\', '/')
    os.environ['CLEANUP_DATABASE_URI'] = _effective_uri
else:
    _effective_uri = db_path  # PostgreSQL URI

print(f"URI: {_effective_uri.split('@')[0] + '@***' if '@' in _effective_uri else _effective_uri}")

# Use Flask app but override DB URI
from app import app as flask_app
from models import db as _db

# Override the URI for this run only
flask_app.config['SQLALCHEMY_DATABASE_URI'] = _effective_uri

print("=" * 60)
print("ШАГ 1: Очистка таблиц адаптивного теста в БД")
print("=" * 60)

with flask_app.app_context():
    from sqlalchemy import text
    # Re-init engine with overridden URI
    _db.engine.dispose()
    
    tables = [
        "task_solutions",
        "curator_state",
        "adaptive_test_problems",
        "adaptive_tests",
        "adaptive_test_results",
        "adaptive_tasks",
        "user_topic_progress",
        "test_results_detail",
        "subtopic_progress",
        "subtopics",
        "diagnostic_draft_answers",
        "questionnaire_state",
    ]
    
    for table in tables:
        try:
            result = _db.session.execute(text(f"DELETE FROM {table}"))
            _db.session.commit()
            count = result.rowcount
            print(f"  ✓ {table}: удалено {count} строк")
        except Exception as e:
            _db.session.rollback()
            err_msg = str(e)
            if "does not exist" in err_msg.lower() or "no such table" in err_msg.lower():
                print(f"  - {table}: таблица не существует, пропускаем")
            else:
                print(f"  ✗ {table}: ОШИБКА — {e}")
    
    # PostgreSQL sequences
    if not db_path.endswith('.db'):
        seqs = [
            "adaptive_tasks_id_seq", "adaptive_tests_id_seq",
            "adaptive_test_problems_id_seq", "adaptive_test_results_id_seq",
            "user_topic_progress_id_seq", "test_results_detail_id_seq",
            "subtopic_progress_id_seq", "subtopics_id_seq",
            "task_solutions_id_seq",
        ]
        for seq in seqs:
            try:
                _db.session.execute(text(f"ALTER SEQUENCE {seq} RESTART WITH 1"))
                _db.session.commit()
                print(f"  ✓ sequence {seq} сброшен")
            except Exception:
                _db.session.rollback()

# ── 2. Очистка файлов ─────────────────────────────────────────────────

print()
print("=" * 60)
print("ШАГ 2: Удаление файлов адаптивного теста")
print("=" * 60)

import shutil

files_to_delete = [
    "adaptive_data.py",
    "adaptive_all_1_8.json",
    "diagnostic_tasks.json",
]

dirs_to_delete = [
    os.path.join("adaptive_data"),
    os.path.join("data", "adaptive"),
]

service_files_to_delete = [
    os.path.join("services", "adaptive_test.py"),
    os.path.join("services", "adaptive_full_seed.py"),
    os.path.join("services", "adaptive_topics_registry.py"),
    os.path.join("services", "adaptive_topic_mapping.py"),
    os.path.join("services", "diagnostic_questionnaire.py"),
    os.path.join("services", "questionnaire_storage.py"),
]

curator_files_to_delete = [
    os.path.join("curator", "diagnostics.py"),
]

template_files_to_delete = [
    os.path.join("templates", "adaptive_test.html"),
    os.path.join("templates", "adaptive_test_already_completed.html"),
    os.path.join("templates", "adaptive_test_results.html"),
    os.path.join("templates", "adaptive_test_select_class.html"),
    os.path.join("templates", "adaptive_test_select_grade.html"),
    os.path.join("templates", "adaptive_test_select_topic.html"),
    os.path.join("templates", "adaptive_test_simple.html"),
    os.path.join("templates", "adaptive_test_simple_results.html"),
]

pycache_dirs = [
    os.path.join("services", "__pycache__"),
    os.path.join("curator", "__pycache__"),
]

all_files = (
    files_to_delete
    + service_files_to_delete
    + curator_files_to_delete
    + template_files_to_delete
)

for f in all_files:
    path = os.path.join(BASE_DIR, f)
    if os.path.isfile(path):
        os.remove(path)
        print(f"  ✓ удалён файл: {f}")
    else:
        print(f"  - не найден: {f}")

for d in dirs_to_delete:
    path = os.path.join(BASE_DIR, d)
    if os.path.isdir(path):
        shutil.rmtree(path)
        print(f"  ✓ удалена папка: {d}")
    else:
        print(f"  - не найдена: {d}")

# Удаляем __pycache__ для затронутых сервисов
for d in pycache_dirs:
    path = os.path.join(BASE_DIR, d)
    if os.path.isdir(path):
        # Удаляем только адаптивные .pyc
        for f in os.listdir(path):
            if any(kw in f.lower() for kw in ["adaptive", "diagnostic", "questionnaire"]):
                fp = os.path.join(path, f)
                if os.path.isfile(fp):
                    os.remove(fp)
                    print(f"  ✓ удалён __pycache__: {os.path.relpath(fp, BASE_DIR)}")

print()
print("=" * 60)
print("ОЧИСТКА ЗАВЕРШЕНА")
print("=" * 60)
print()
print("⚠️  НЕ ЗАБУДЬ:")
print("1. Удалить импорты adaptive_data/adaptive_test из app.py")
print("2. Удалить @app.route эндпоинты адаптивного теста")
print("3. Удалить import adaptive_data из __init__.py если есть")
print("4. Перезапустить сервер")
