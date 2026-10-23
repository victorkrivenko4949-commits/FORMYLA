#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Миграция: Добавление поля grade в таблицу adaptive_test_results (если нужно)

ВНИМАНИЕ: НЕ ПРИМЕНЯТЬ АВТОМАТИЧЕСКИ!
Сначала проверьте структуру таблицы:
    python -c "from app import app; from models import db, AdaptiveTestResult; 
    with app.app_context(): print(AdaptiveTestResult.__table__.columns.keys())"

Если поле class_level уже существует - миграция не нужна.
"""

from app import app
from models import db
from sqlalchemy import text


def check_column_exists():
    """Проверяет, существует ли поле class_level."""
    with app.app_context():
        inspector = db.inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns('adaptive_test_results')]
        return 'class_level' in columns


def add_grade_column():
    """
    Добавляет поле class_level в таблицу adaptive_test_results.
    
    ВНИМАНИЕ: Запускайте только если поле отсутствует!
    """
    with app.app_context():
        # Проверяем наличие поля
        if check_column_exists():
            print("[INFO] Поле class_level уже существует. Миграция не требуется.")
            return
        
        print("[INFO] Добавление поля class_level...")
        
        # SQLite синтаксис
        try:
            db.session.execute(text(
                "ALTER TABLE adaptive_test_results ADD COLUMN class_level INTEGER"
            ))
            db.session.commit()
            print("[OK] Поле class_level успешно добавлено")
        except Exception as e:
            print(f"[ERROR] Ошибка при добавлении поля: {e}")
            db.session.rollback()
            raise


if __name__ == "__main__":
    print("\n" + "="*70)
    print("МИГРАЦИЯ: Добавление поля grade в adaptive_test_results")
    print("="*70)
    
    # Проверка
    if check_column_exists():
        print("\n[OK] Поле class_level уже существует в таблице.")
        print("Миграция не требуется.")
    else:
        print("\n[WARN] Поле class_level отсутствует!")
        response = input("Применить миграцию? (yes/no): ")
        
        if response.lower() == 'yes':
            add_grade_column()
            print("\n[OK] Миграция применена успешно!")
        else:
            print("\n[STOP] Миграция отменена")
    
    print("="*70 + "\n")
