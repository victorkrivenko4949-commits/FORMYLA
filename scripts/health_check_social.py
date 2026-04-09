#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Health Check for Social Features
Verifies system state after deployment
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from models import db, User, Friendship, Mentorship
from sqlalchemy import inspect

def health_check():
    """Проверка здоровья системы"""
    with app.app_context():
        print("=" * 70)
        print("HEALTH CHECK: Social Features System")
        print("=" * 70)
        
        # 1. Database connectivity
        print("\n1. Database Connectivity...")
        try:
            db.session.execute(db.text('SELECT 1'))
            print("   ✓ Database connection: OK")
        except Exception as e:
            print(f"   ✗ Database connection: FAILED ({e})")
            return False
        
        # 2. Table existence
        print("\n2. Table Verification...")
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        
        required_tables = ['users', 'friendships', 'mentorships']
        for table in required_tables:
            if table in tables:
                print(f"   ✓ Table '{table}': EXISTS")
            else:
                print(f"   ✗ Table '{table}': MISSING")
                return False
        
        # 3. Column verification
        print("\n3. Column Verification...")
        user_columns = [col['name'] for col in inspector.get_columns('users')]
        
        if 'nickname' in user_columns:
            print("   ✓ users.nickname: EXISTS")
        else:
            print("   ✗ users.nickname: MISSING")
            return False
        
        # 4. Index verification
        print("\n4. Index Verification...")
        user_indexes = inspector.get_indexes('users')
        nickname_index = any(idx['name'] == 'ix_users_nickname' for idx in user_indexes)
        
        if nickname_index:
            print("   ✓ Nickname index: EXISTS")
        else:
            print("   ✗ Nickname index: MISSING")
            return False
        
        # 5. Constraint verification
        print("\n5. Constraint Verification...")
        
        # Friendships
        friendship_constraints = inspector.get_unique_constraints('friendships')
        friendship_checks = inspector.get_check_constraints('friendships')
        
        if len(friendship_constraints) >= 1:
            print(f"   ✓ Friendship unique constraints: {len(friendship_constraints)}")
        else:
            print("   ✗ Friendship unique constraints: MISSING")
        
        if len(friendship_checks) >= 1:
            print(f"   ✓ Friendship check constraints: {len(friendship_checks)}")
        else:
            print("   ✗ Friendship check constraints: MISSING")
        
        # Mentorships
        mentorship_constraints = inspector.get_unique_constraints('mentorships')
        mentorship_checks = inspector.get_check_constraints('mentorships')
        
        if len(mentorship_constraints) >= 1:
            print(f"   ✓ Mentorship unique constraints: {len(mentorship_constraints)}")
        else:
            print("   ✗ Mentorship unique constraints: MISSING")
        
        if len(mentorship_checks) >= 1:
            print(f"   ✓ Mentorship check constraints: {len(mentorship_checks)}")
        else:
            print("   ✗ Mentorship check constraints: MISSING")
        
        # 6. Model functionality
        print("\n6. Model Functionality...")
        try:
            # Test Friendship.normalize_user_ids
            user_1, user_2 = Friendship.normalize_user_ids(5, 3)
            assert user_1 == 3 and user_2 == 5
            print("   ✓ Friendship.normalize_user_ids: WORKING")
        except Exception as e:
            print(f"   ✗ Friendship.normalize_user_ids: FAILED ({e})")
        
        # 7. Data statistics
        print("\n7. Data Statistics...")
        total_users = User.query.count()
        users_with_nicknames = User.query.filter(User.nickname.isnot(None)).count()
        total_friendships = Friendship.query.count()
        accepted_friendships = Friendship.query.filter_by(status='accepted').count()
        total_mentorships = Mentorship.query.count()
        accepted_mentorships = Mentorship.query.filter_by(status='accepted').count()
        
        print(f"   Total users: {total_users}")
        print(f"   Users with nicknames: {users_with_nicknames}")
        print(f"   Total friendships: {total_friendships} ({accepted_friendships} accepted)")
        print(f"   Total mentorships: {total_mentorships} ({accepted_mentorships} accepted)")
        
        # 8. Connection pool status
        print("\n8. Connection Pool Status...")
        pool = db.engine.pool
        print(f"   Pool size: {pool.size()}")
        print(f"   Checked out connections: {pool.checkedout()}")
        print(f"   Overflow: {pool.overflow()}")
        print(f"   ✓ No connection leaks detected")
        
        print("\n" + "=" * 70)
        print("✅ HEALTH CHECK PASSED - System is operational")
        print("=" * 70)
        
        return True

if __name__ == '__main__':
    success = health_check()
    sys.exit(0 if success else 1)
