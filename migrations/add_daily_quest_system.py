# -*- coding: utf-8 -*-
"""
Миграция: Добавление системы Daily Quest
Создаёт таблицы: daily_quests, user_streaks, topic_mastery
"""
from models import db, DailyQuest, UserStreak, TopicMastery
from app import app


def migrate():
    """Выполнить миграцию"""
    with app.app_context():
        print("🔄 Начинаем миграцию Daily Quest системы...")
        
        # Создаём новые таблицы
        try:
            db.create_all()
            print("✅ Таблицы созданы:")
            print("   - daily_quests")
            print("   - user_streaks")
            print("   - topic_mastery")
            
            # Инициализируем streak для существующих пользователей
            from models import User
            users = User.query.all()
            
            for user in users:
                # Проверяем, есть ли уже streak
                existing_streak = UserStreak.query.filter_by(user_id=user.id).first()
                if not existing_streak:
                    streak = UserStreak(user_id=user.id)
                    db.session.add(streak)
            
            db.session.commit()
            print(f"✅ Инициализированы streak для {len(users)} пользователей")
            
            print("✅ Миграция завершена успешно!")
            
        except Exception as e:
            print(f"❌ Ошибка миграции: {e}")
            db.session.rollback()
            raise


if __name__ == '__main__':
    migrate()
