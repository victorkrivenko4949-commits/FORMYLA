# -*- coding: utf-8 -*-
"""
Пересоздание базы данных с новой структурой
ВНИМАНИЕ: Удаляет все данные пользователей!
"""
import sys
import os
import codecs

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.platform == 'win32':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

print("="*70)
print("Пересоздание базы данных")
print("="*70)

# Находим файл БД
db_files = ['formyla.db', 'instance/formyla.db', 'app.db', 'instance/app.db']
db_path = None

for path in db_files:
    if os.path.exists(path):
        db_path = path
        break

if db_path:
    print(f"\n🗑️  Удаляем старую БД: {db_path}")
    os.remove(db_path)
    print("✅ Старая БД удалена")
else:
    print("\n📝 Старая БД не найдена (создаем новую)")

# Создаем новую БД
print("\n📦 Создаем новую БД с обновленной структурой...")

from app import app, db

with app.app_context():
    db.create_all()
    print("✅ База данных создана!")
    
    # Проверяем таблицы
    from sqlalchemy import inspect
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()
    
    print(f"\n📊 Созданные таблицы: {tables}")
    
    if 'users' in tables:
        columns = [col['name'] for col in inspector.get_columns('users')]
        print(f"📋 Колонки в таблице users:")
        for col in columns:
            print(f"   - {col}")

print("\n" + "="*70)
print("✅ ГОТОВО!")
print("="*70)
print("\nБаза данных пересоздана с новой структурой")
print("Теперь можно тестировать passwordless авторизацию!")
