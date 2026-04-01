# -*- coding: utf-8 -*-
"""
Добавление таблицы chat_messages без удаления существующих данных
"""
import sys
import os
import codecs

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.platform == 'win32':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

print("="*70)
print("Добавление таблицы chat_messages")
print("="*70)

from app import app, db
from models import ChatMessage

with app.app_context():
    # Создаем только новые таблицы (не удаляя существующие)
    db.create_all()
    print("\n✅ Таблица chat_messages создана!")
    
    # Проверяем
    from sqlalchemy import inspect
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()
    
    print(f"\n📊 Таблицы в БД: {tables}")
    
    if 'chat_messages' in tables:
        columns = [col['name'] for col in inspector.get_columns('chat_messages')]
        print(f"\n📋 Колонки в chat_messages:")
        for col in columns:
            print(f"   ✓ {col}")

print("\n" + "="*70)
print("✅ ГОТОВО!")
print("="*70)
