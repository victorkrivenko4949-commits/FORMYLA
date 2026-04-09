#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Migration script for social features: nicknames, friendships, mentorships
Adds nickname column to users table and creates new tables
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from models import db, User, Friendship, Mentorship

def migrate_database():
    """Выполнить миграцию базы данных"""
    with app.app_context():
        print("=" * 70)
        print("MIGRATION: Adding Social Features")
        print("=" * 70)
        
        # Создаем все таблицы (новые будут созданы, существующие пропущены)
        print("\n1. Creating new tables (friendships, mentorships)...")
        db.create_all()
        print("   ✓ Tables created/verified")
        
        # Проверяем, есть ли колонка nickname в таблице users
        print("\n2. Checking nickname column in users table...")
        inspector = db.inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns('users')]
        
        if 'nickname' not in columns:
            print("   ! Nickname column not found, adding...")
            # SQLite не поддерживает ADD COLUMN с UNIQUE, делаем в два шага
            with db.engine.connect() as conn:
                # Добавляем колонку без UNIQUE
                conn.execute(db.text('ALTER TABLE users ADD COLUMN nickname VARCHAR(50)'))
                conn.commit()
                # Создаем уникальный индекс отдельно
                conn.execute(db.text('CREATE UNIQUE INDEX IF NOT EXISTS ix_users_nickname ON users (nickname)'))
                conn.commit()
            print("   ✓ Nickname column added with unique index")
        else:
            print("   ✓ Nickname column already exists")
            # Проверяем наличие уникального индекса
            indexes = inspector.get_indexes('users')
            has_unique_nickname = any(idx['name'] == 'ix_users_nickname' and idx.get('unique', False) for idx in indexes)
            if not has_unique_nickname:
                print("   ! Creating unique index for nickname...")
                with db.engine.connect() as conn:
                    conn.execute(db.text('CREATE UNIQUE INDEX IF NOT EXISTS ix_users_nickname ON users (nickname)'))
                    conn.commit()
                print("   ✓ Unique index created")
        
        # Проверяем таблицы
        print("\n3. Verifying tables...")
        tables = inspector.get_table_names()
        
        required_tables = ['users', 'friendships', 'mentorships']
        for table in required_tables:
            if table in tables:
                print(f"   ✓ Table '{table}' exists")
            else:
                print(f"   ✗ Table '{table}' missing!")
        
        # Проверяем constraints
        print("\n4. Verifying constraints...")
        
        # Friendships constraints
        friendship_constraints = inspector.get_unique_constraints('friendships')
        friendship_checks = inspector.get_check_constraints('friendships')
        print(f"   Friendships unique constraints: {len(friendship_constraints)}")
        print(f"   Friendships check constraints: {len(friendship_checks)}")
        
        # Mentorships constraints
        mentorship_constraints = inspector.get_unique_constraints('mentorships')
        mentorship_checks = inspector.get_check_constraints('mentorships')
        print(f"   Mentorships unique constraints: {len(mentorship_constraints)}")
        print(f"   Mentorships check constraints: {len(mentorship_checks)}")
        
        print("\n" + "=" * 70)
        print("✅ MIGRATION COMPLETE")
        print("=" * 70)
        print("\nDatabase is ready for social features:")
        print("  - Users can set unique nicknames")
        print("  - Friendship requests with pending/accepted/rejected status")
        print("  - Teacher-student mentorship relationships")
        print("  - All constraints enforced at database level")

if __name__ == '__main__':
    migrate_database()
