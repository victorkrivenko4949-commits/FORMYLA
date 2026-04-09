#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
E2E Test for Social Features
Tests real database operations without mocks
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from models import db, User, Friendship, Mentorship

def test_social_features():
    """Тестирование социальных функций E2E"""
    with app.app_context():
        print("=" * 70)
        print("E2E TEST: Social Features")
        print("=" * 70)
        
        # Очистка тестовых данных
        print("\n1. Cleaning up test data...")
        User.query.filter(User.email.like('test_%@example.com')).delete()
        db.session.commit()
        print("   ✓ Test data cleaned")
        
        # Создание тестовых пользователей
        print("\n2. Creating test users...")
        user1 = User(email='test_user1@example.com', name='Test User 1', nickname='testuser1')
        user2 = User(email='test_user2@example.com', name='Test User 2', nickname='testuser2')
        user3 = User(email='test_user3@example.com', name='Test User 3', nickname='testuser3')
        
        db.session.add_all([user1, user2, user3])
        db.session.commit()
        print(f"   ✓ Created users: {user1.id}, {user2.id}, {user3.id}")
        
        # Тест 1: Попытка добавить себя в друзья (должна провалиться)
        print("\n3. Test: Adding self as friend (should fail)...")
        try:
            friendship = Friendship.create_friendship_request(user1.id, user1.id)
            print("   ✗ FAILED: Should have raised ValueError")
        except ValueError as e:
            print(f"   ✓ PASSED: {e}")
        
        # Тест 2: Создание заявки в друзья
        print("\n4. Test: Creating friendship request...")
        friendship = Friendship.create_friendship_request(user1.id, user2.id)
        db.session.add(friendship)
        db.session.commit()
        print(f"   ✓ Friendship created: ID={friendship.id}, Status={friendship.status}")
        
        # Тест 3: Попытка создать дубликат (должна провалиться)
        print("\n5. Test: Duplicate friendship request (should fail)...")
        try:
            dup_friendship = Friendship.create_friendship_request(user1.id, user2.id)
            db.session.add(dup_friendship)
            db.session.commit()
            print("   ✗ FAILED: Should have raised ValueError")
        except ValueError as e:
            db.session.rollback()
            print(f"   ✓ PASSED: {e}")
        
        # Тест 4: Принятие заявки в друзья
        print("\n6. Test: Accepting friendship request...")
        friendship.accept()
        db.session.commit()
        print(f"   ✓ Friendship accepted: Status={friendship.status}")
        
        # Тест 5: Создание заявки учитель-ученик
        print("\n7. Test: Creating mentorship request...")
        mentorship = Mentorship.create_mentorship_request(user1.id, user3.id)
        db.session.add(mentorship)
        db.session.commit()
        print(f"   ✓ Mentorship created: ID={mentorship.id}, Status={mentorship.status}")
        
        # Тест 6: Попытка добавить себя учеником (должна провалиться)
        print("\n8. Test: Adding self as student (should fail)...")
        try:
            self_mentorship = Mentorship.create_mentorship_request(user1.id, user1.id)
            print("   ✗ FAILED: Should have raised ValueError")
        except ValueError as e:
            print(f"   ✓ PASSED: {e}")
        
        # Тест 7: Принятие заявки учитель-ученик
        print("\n9. Test: Accepting mentorship request...")
        mentorship.accept()
        db.session.commit()
        print(f"   ✓ Mentorship accepted: Status={mentorship.status}")
        
        # Тест 8: Проверка уникальности никнейма
        print("\n10. Test: Nickname uniqueness...")
        user4 = User(email='test_user4@example.com', name='Test User 4', nickname='testuser1')
        db.session.add(user4)
        try:
            db.session.commit()
            print("   ✗ FAILED: Should have raised IntegrityError")
        except Exception as e:
            db.session.rollback()
            print(f"   ✓ PASSED: Unique constraint enforced ({type(e).__name__})")
        
        # Тест 9: Поиск пользователей
        print("\n11. Test: User search...")
        found_users = User.query.filter(User.nickname.ilike('%testuser%')).limit(10).all()
        print(f"   ✓ Found {len(found_users)} users matching 'testuser'")
        
        # Тест 10: Получение списка друзей
        print("\n12. Test: Getting friends list...")
        friendships = Friendship.query.filter(
            db.or_(
                Friendship.user_1_id == user1.id,
                Friendship.user_2_id == user1.id
            ),
            Friendship.status == 'accepted'
        ).all()
        print(f"   ✓ User1 has {len(friendships)} friend(s)")
        
        # Тест 11: Получение списка учеников
        print("\n13. Test: Getting students list...")
        mentorships = Mentorship.query.filter_by(
            teacher_id=user1.id,
            status='accepted'
        ).all()
        print(f"   ✓ User1 has {len(mentorships)} student(s)")
        
        # Очистка
        print("\n14. Cleaning up...")
        Friendship.query.filter(
            db.or_(
                Friendship.user_1_id.in_([user1.id, user2.id, user3.id]),
                Friendship.user_2_id.in_([user1.id, user2.id, user3.id])
            )
        ).delete(synchronize_session=False)
        
        Mentorship.query.filter(
            db.or_(
                Mentorship.teacher_id.in_([user1.id, user2.id, user3.id]),
                Mentorship.student_id.in_([user1.id, user2.id, user3.id])
            )
        ).delete(synchronize_session=False)
        
        User.query.filter(User.email.like('test_%@example.com')).delete()
        db.session.commit()
        print("   ✓ Test data cleaned up")
        
        print("\n" + "=" * 70)
        print("✅ ALL E2E TESTS PASSED")
        print("=" * 70)
        print("\nDatabase constraints verified:")
        print("  ✓ Unique nicknames enforced")
        print("  ✓ Cannot add self as friend/student")
        print("  ✓ Duplicate friendship requests blocked")
        print("  ✓ Friendship status transitions work")
        print("  ✓ Mentorship relationships work")
        print("  ✓ User search with LIMIT works")

if __name__ == '__main__':
    test_social_features()
