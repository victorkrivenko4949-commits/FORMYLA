#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MIGRATION: Add agent_type column to chat_messages table
"""
import sqlite3
import os
import sys

def migrate_database():
    """Add agent_type column to existing chat_messages table"""
    
    # Database paths to check
    db_paths = [
        'instance/formyla.db',
        'instance/app.db',
        'app.db',
        'instance/database.db'
    ]
    
    db_path = None
    for path in db_paths:
        if os.path.exists(path):
            db_path = path
            break
    
    if not db_path:
        print("[ERROR] Database not found!")
        print("Checked paths:", db_paths)
        return False
    
    print(f"[INFO] Found database: {db_path}")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if column already exists
        cursor.execute("PRAGMA table_info(chat_messages)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'agent_type' in columns:
            print("[OK] Column 'agent_type' already exists in chat_messages table")
            conn.close()
            return True
        
        print("[INFO] Adding column 'agent_type' to chat_messages table...")
        
        # Add column with default value
        cursor.execute("""
            ALTER TABLE chat_messages 
            ADD COLUMN agent_type VARCHAR(50) DEFAULT 'general' NOT NULL
        """)
        
        conn.commit()
        print("[SUCCESS] Column 'agent_type' added successfully!")
        
        # Create index for optimization
        print("[INFO] Creating index for agent_type...")
        try:
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS ix_chat_messages_agent_type 
                ON chat_messages (agent_type)
            """)
            conn.commit()
            print("[SUCCESS] Index created!")
        except Exception as e:
            print(f"[WARNING] Could not create index (may already exist): {e}")
        
        # Verify result
        cursor.execute("PRAGMA table_info(chat_messages)")
        columns = cursor.fetchall()
        
        print("\n[INFO] Current chat_messages table structure:")
        for col in columns:
            print(f"  - {col[1]} ({col[2]})")
        
        conn.close()
        print("\n[SUCCESS] Migration completed successfully!")
        return True
        
    except sqlite3.OperationalError as e:
        print(f"[ERROR] SQLite error: {e}")
        return False
    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    print("=" * 60)
    print("DATABASE MIGRATION: Adding agent_type column")
    print("=" * 60)
    print()
    
    success = migrate_database()
    
    print()
    print("=" * 60)
    if success:
        print("[SUCCESS] MIGRATION COMPLETED!")
        print("You can now restart the Flask application.")
    else:
        print("[ERROR] MIGRATION FAILED!")
        print("Check the errors above.")
    print("=" * 60)
    
    sys.exit(0 if success else 1)
