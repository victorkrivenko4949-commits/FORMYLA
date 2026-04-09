#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Migration script: Add agent_type column to chat_messages table"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from models import db

def migrate():
    """Add agent_type column to existing chat_messages table"""
    with app.app_context():
        try:
            # Check if column already exists
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            columns = [col['name'] for col in inspector.get_columns('chat_messages')]
            
            if 'agent_type' in columns:
                print("✓ Column 'agent_type' already exists in chat_messages table")
                return
            
            # Add column with default value
            print("Adding 'agent_type' column to chat_messages table...")
            db.engine.execute(
                "ALTER TABLE chat_messages ADD COLUMN agent_type VARCHAR(50) NOT NULL DEFAULT 'general'"
            )
            
            # Create index for better performance
            print("Creating index on agent_type column...")
            db.engine.execute(
                "CREATE INDEX ix_chat_messages_agent_type ON chat_messages (agent_type)"
            )
            
            print("✅ Migration completed successfully!")
            print("   - Added 'agent_type' column")
            print("   - Set default value to 'general' for existing records")
            print("   - Created index for performance")
            
        except Exception as e:
            print(f"❌ Migration failed: {e}")
            raise

if __name__ == '__main__':
    migrate()
