"""Полная очистка адаптивного теста: БД + файлы.

ЗАПУСКАТЬ ОСТОРОЖНО — данные не восстанавливаются!
Перед запуском сделай бэкап БД: copy database.db database.db.bak_adaptive
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

# ── 1. Очистка БД ──────────────────────────────────────────────────────

print("=" * 60)
print("ШАГ 1: Очистка таблиц адаптивного теста в БД")
print("=" * 60)

# Загружаем .env
from dotenv import load_dotenv
load_dotenv()
db_url = os.environ.get("DATABASE_URL", "").strip()

if db_url:
    print(f"Тип БД: {'PostgreSQL' if 'postgresql' in db_url else 'SQLite'}")
    print(f"DATABASE_URL найден — работаем с production БД")
    
    from app import app as flask_app
    from models import db
    
    with flask_app.app_context():
        from sqlalchemy import text
        
        # Порядок важен: сначала дочерние таблицы с FK, потом родительские
        tables = [
            "task_solutions",         # FK → adaptive_tasks
            "curator_state",          # FK → adaptive_test_results
            "adaptive_test_problems", # FK → adaptive_tests
            "adaptive_tests",
            "adaptive_test_results",
            "adaptive_tasks",
            "user_topic_progress",
            "test_results_detail",
            "subtopic_progress",
            "subtopics",
            # Дополнительно: кэш черновиков ответов
            "diagnostic_draft_answers",
            "questionnaire_state",
        ]
        
        for table in tables:
            try:
                result = db.session.execute(text(f"DELETE FROM {table}"))
                db.session.commit()
                count = result.rowcount
                print(f"  ✓ {table}: удалено {count} строк")
            except Exception as e:
                db.session.rollback()
                # Пропускаем таблицы, которых может не быть
                err_msg = str(e)
                if "does not exist" in err_msg.lower() or "no such table" in err_msg.lower():
                    print(f"  - {table}: таблица не существует, пропускаем")
                else:
                    print(f"  ✗ {table}: ОШИБКА — {e}")
        
        # Для PostgreSQL: сбрасываем sequences
        if "postgresql" in db_url:
            seqs = [
                "adaptive_tasks_id_seq",
                "adaptive_tests_id_seq",
                "adaptive_test_problems_id_seq",
                "adaptive_test_results_id_seq",
                "user_topic_progress_id_seq",
                "test_results_detail_id_seq",
                "subtopic_progress_id_seq",
                "subtopics_id_seq",
                "task_solutions_id_seq",
            ]
            for seq in seqs:
                try:
                    db.session.execute(text(f"ALTER SEQUENCE {seq} RESTART WITH 1"))
                    db.session.commit()
                    print(f"  ✓ sequence {seq} сброшен")
                except Exception:
                    db.session.rollback()
else:
    print("DATABASE_URL не найден в .env — работаем с SQLite (database.db)")
    
    from app import app as flask_app
    from models import db
    
    with flask_app.app_context():
        from sqlalchemy import text
        
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
        ]
        
        for table in tables:
            try:
                result = db.session.execute(text(f"DELETE FROM {table}"))
                db.session.commit()
                count = result.rowcount
                print(f"  ✓ {table}: удалено {count} строк")
            except Exception as e:
                db.session.rollback()
                if "no such table" in str(e).lower():
                    print(f"  - {table}: не существует, пропускаем")
                else:
                    print(f"  ✗ {table}: ОШИБКА — {e}")

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
