# -*- coding: utf-8 -*-
"""
ЖЕСТКИЙ СБРОС БАЗЫ ДАННЫХ
Удаляет старую БД и создает новую с обновленной структурой
"""
import sys
import os
import codecs
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.platform == 'win32':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

print("="*70)
print("ЖЕСТКИЙ СБРОС БАЗЫ ДАННЫХ")
print("="*70)

# Ищем файл БД
db_paths = [
    'formyla.db',
    'instance/formyla.db',
    'instance/app.db',
    'app.db'
]

deleted = False
for db_path in db_paths:
    if os.path.exists(db_path):
        print(f"\n🗑️  Найдена БД: {db_path}")
        try:
            os.remove(db_path)
            print(f"✅ Удалена: {db_path}")
            deleted = True
        except PermissionError:
            print(f"❌ ОШИБКА: Файл заблокирован!")
            print(f"   Остановите сервер Flask (Ctrl+C в Terminal 1)")
            print(f"   И запустите скрипт снова")
            sys.exit(1)
        except Exception as e:
            print(f"❌ Ошибка удаления: {e}")
            sys.exit(1)

if not deleted:
    print("\n📝 Старая БД не найдена")

# Создаем директорию instance если нужно
os.makedirs('instance', exist_ok=True)

# Создаем новую БД
print("\n📦 Создаем новую БД...")

from app import app, db
from models import User

with app.app_context():
    # Создаем все таблицы
    db.create_all()
    print("✅ Таблицы созданы!")
    
    # Проверяем структуру
    from sqlalchemy import inspect
    inspector = inspect(db.engine)
    
    if 'users' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('users')]
        print(f"\n📋 Колонки в таблице users:")
        for col in columns:
            print(f"   ✓ {col}")
        
        # Проверяем наличие новых колонок
        required_cols = ['auth_code', 'code_expires', 'math_level', 'ai_report']
        missing = [c for c in required_cols if c not in columns]
        
        if missing:
            print(f"\n❌ ОШИБКА: Отсутствуют колонки: {missing}")
            sys.exit(1)
        else:
            print(f"\n✅ Все необходимые колонки присутствуют!")

print("\n" + "="*70)
print("✅ БАЗА ДАННЫХ ГОТОВА!")
print("="*70)
print("\nТеперь можно запустить сервер: python app.py")
print("И протестировать passwordless авторизацию!")
