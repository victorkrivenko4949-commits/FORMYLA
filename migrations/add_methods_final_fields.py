# -*- coding: utf-8 -*-
"""
Миграция: добавление полей из methods_final.json в olympiad_theory.

Новые поля:
- why_it_works_md (TEXT) — почему метод работает
- signal_phrases (JSON) — фразы-сигналы в условии
- first_moves (JSON) — первые ходы решения
- prerequisites (JSON) — method_codes, которые нужно знать
- leads_to (JSON) — method_codes, для которых этот — фундамент

Запуск:
    python migrations/add_methods_final_fields.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from sqlalchemy import text, inspect

NEW_COLUMNS = [
    ('why_it_works_md', 'TEXT'),
    ('signal_phrases', 'TEXT'),  # JSON хранится как TEXT в SQLite
    ('first_moves', 'TEXT'),
    ('prerequisites', 'TEXT'),
    ('leads_to', 'TEXT'),
]

def run_migration():
    with app.app_context():
        inspector = inspect(db.engine)
        existing_columns = {col['name'] for col in inspector.get_columns('olympiad_theory')}
        
        dialect = db.engine.dialect.name
        print(f"[migration] dialect = {dialect}")
        print(f"[migration] existing columns: {len(existing_columns)}")
        
        added = 0
        for col_name, col_type in NEW_COLUMNS:
            if col_name in existing_columns:
                print(f"  [OK] {col_name} already exists")
                continue
            
            # Для PostgreSQL используем JSONB для JSON-полей
            if dialect == 'postgresql' and col_type == 'TEXT' and col_name != 'why_it_works_md':
                col_type = 'JSONB'
            
            sql = f'ALTER TABLE olympiad_theory ADD COLUMN {col_name} {col_type}'
            try:
                db.session.execute(text(sql))
                db.session.commit()
                print(f"  + {col_name} ({col_type}) added")
                added += 1
            except Exception as e:
                db.session.rollback()
                print(f"  ! {col_name} failed: {e}")
        
        print(f"\n[migration] done: {added} columns added")

if __name__ == '__main__':
    run_migration()
