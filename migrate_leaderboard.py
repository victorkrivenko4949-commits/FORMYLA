#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Database Migration Script for Leaderboard Feature
Adds new statistics columns to users table.
"""

import sqlite3
import os
import sys
import io

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

def migrate_database():
    """Add leaderboard statistics columns to users table."""
    db_path = 'instance/formyla.db'
    
    if not os.path.exists(db_path):
        print(f"ERROR: Database file not found: {db_path}")
        print("   The database will be created automatically when you run the app.")
        return
    
    print(f"Migrating database: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # List of new columns to add
    new_columns = [
        ('total_problems_solved', 'INTEGER DEFAULT 0'),
        ('current_level', 'INTEGER DEFAULT 1'),
        ('experience_points', 'INTEGER DEFAULT 0'),
        ('mock_exams_passed', 'INTEGER DEFAULT 0'),
        ('adaptive_tests_completed', 'INTEGER DEFAULT 0'),
        ('highest_difficulty_solved', 'INTEGER DEFAULT 0'),
    ]
    
    # Check existing columns
    cursor.execute("PRAGMA table_info(users)")
    existing_columns = [row[1] for row in cursor.fetchall()]
    
    print(f"\n✅ Found {len(existing_columns)} existing columns in users table")
    
    # Add new columns if they don't exist
    added_count = 0
    for column_name, column_type in new_columns:
        if column_name not in existing_columns:
            try:
                sql = f"ALTER TABLE users ADD COLUMN {column_name} {column_type}"
                cursor.execute(sql)
                print(f"   ✅ Added column: {column_name}")
                added_count += 1
            except sqlite3.OperationalError as e:
                print(f"   ⚠️  Could not add {column_name}: {e}")
        else:
            print(f"   ⏭️  Column already exists: {column_name}")
    
    conn.commit()
    conn.close()
    
    print(f"\n{'='*60}")
    if added_count > 0:
        print(f"✅ Migration complete! Added {added_count} new columns.")
    else:
        print(f"✅ Database is up to date. No changes needed.")
    print(f"{'='*60}")
    print("\n🚀 You can now restart the Flask server.")

if __name__ == '__main__':
    migrate_database()
