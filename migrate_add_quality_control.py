"""
Миграция: Добавление колонок системы контроля качества в таблицу adaptive_tasks
"""

import sqlite3
import os
import sys

# Устанавливаем UTF-8 для вывода
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Путь к базе данных
db_path = 'instance/formyla.db'

# Проверяем существование файла БД
if not os.path.exists(db_path):
    print(f"ERROR: Database file '{db_path}' not found!")
    print("Possible locations:")
    print("  - formyla.db")
    print("  - instance/formyla.db")
    print("  - app.db")
    exit(1)

print(f"Connecting to database: {db_path}")

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("\nAdding quality control columns...")
    
    # Пытаемся добавить колонку is_flagged
    try:
        cursor.execute("ALTER TABLE adaptive_tasks ADD COLUMN is_flagged BOOLEAN DEFAULT 0;")
        print("[OK] Column is_flagged added.")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print("[SKIP] Column is_flagged already exists.")
        else:
            print(f"[ERROR] Failed to add is_flagged: {e}")

    # Пытаемся добавить колонку reports_count
    try:
        cursor.execute("ALTER TABLE adaptive_tasks ADD COLUMN reports_count INTEGER DEFAULT 0;")
        print("[OK] Column reports_count added.")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print("[SKIP] Column reports_count already exists.")
        else:
            print(f"[ERROR] Failed to add reports_count: {e}")
        
    # Пытаемся добавить колонку flagged_reason
    try:
        cursor.execute("ALTER TABLE adaptive_tasks ADD COLUMN flagged_reason TEXT;")
        print("[OK] Column flagged_reason added.")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print("[SKIP] Column flagged_reason already exists.")
        else:
            print(f"[ERROR] Failed to add flagged_reason: {e}")

    # Создаем индекс для быстрой фильтрации
    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_adaptive_tasks_is_flagged ON adaptive_tasks(is_flagged);")
        print("[OK] Index idx_adaptive_tasks_is_flagged created.")
    except sqlite3.OperationalError as e:
        print(f"[SKIP] Index already exists or error: {e}")

    conn.commit()
    
    # Проверяем результат
    cursor.execute("PRAGMA table_info(adaptive_tasks);")
    columns = cursor.fetchall()
    
    print("\nCurrent table structure (adaptive_tasks):")
    for col in columns:
        print(f"   - {col[1]} ({col[2]})")
    
    # Проверяем наличие новых колонок
    column_names = [col[1] for col in columns]
    required_columns = ['is_flagged', 'reports_count', 'flagged_reason']
    
    print("\nVerifying new columns:")
    all_present = True
    for col in required_columns:
        if col in column_names:
            print(f"   [OK] {col} - present")
        else:
            print(f"   [MISSING] {col} - NOT FOUND!")
            all_present = False
    
    conn.close()
    
    if all_present:
        print("\n=== MIGRATION COMPLETED SUCCESSFULLY ===")
        print("You can now restart the Flask application.")
    else:
        print("\n=== MIGRATION COMPLETED WITH WARNINGS ===")
        print("Check errors above.")
        
except Exception as e:
    print(f"\nCRITICAL ERROR: {e}")
    import traceback
    traceback.print_exc()
