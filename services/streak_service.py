# -*- coding: utf-8 -*-
"""
Streak Service for FORMYLA
Manages user streaks (like Duolingo) with freeze functionality
"""

from datetime import datetime, date, timedelta
from models import db, UserStreak, DailyQuest, User
from typing import Optional, Dict
import logging

logger = logging.getLogger(__name__)


def get_or_create_streak(user_id: int) -> UserStreak:
    """
    Получить или создать streak для пользователя.
    
    Args:
        user_id: ID пользователя
        
    Returns:
        UserStreak объект
    """
    streak = UserStreak.query.filter_by(user_id=user_id).first()
    
    if not streak:
        streak = UserStreak(user_id=user_id)
        db.session.add(streak)
        try:
            db.session.commit()
            logger.info(f"Created new streak for user {user_id}")
        except Exception as e:
            logger.error(f"Error creating streak: {e}")
            db.session.rollback()
    
    return streak


def update_streak_after_quest(user_id: int):
    """
    Обновить streak после завершения Daily Quest.
    
    Args:
        user_id: ID пользователя
    """
    streak = get_or_create_streak(user_id)
    today = date.today()
    
    # Проверяем, завершён ли квест на сегодня
    quest = DailyQuest.query.filter_by(
        user_id=user_id,
        date=today
    ).first()
    
    if not quest or quest.completed_count < quest.total_count:
        logger.info(f"Quest not completed for user {user_id}, streak not updated")
        return
    
    # Обновляем streak
    if streak.last_active_date is None:
        # Первый день
        streak.current_streak = 1
        streak.longest_streak = 1
        streak.last_active_date = today
    elif streak.last_active_date == today:
        # Уже обновлено сегодня
        logger.info(f"Streak already updated today for user {user_id}")
        return
    elif streak.last_active_date == today - timedelta(days=1):
        # Продолжение streak
        streak.current_streak += 1
        streak.last_active_date = today
        
        # Обновляем рекорд
        if streak.current_streak > streak.longest_streak:
            streak.longest_streak = streak.current_streak
    else:
        # Streak прервался (но это не должно происходить здесь, обрабатывается в daily_reset)
        logger.warning(f"Streak gap detected for user {user_id}")
        streak.current_streak = 1
        streak.last_active_date = today
    
    try:
        db.session.commit()
        logger.info(f"Updated streak for user {user_id}: {streak.current_streak} days")
    except Exception as e:
        logger.error(f"Error updating streak: {e}")
        db.session.rollback()


def check_and_reset_streaks():
    """
    Проверить и сбросить streak для всех пользователей (вызывается в 00:00 MSK).
    
    Логика:
    - Если last_active_date == вчера → всё ок, streak продолжается
    - Если last_active_date == позавчера или раньше:
      - Если freeze_available > 0 → используем freeze
      - Иначе → сбрасываем streak
    """
    today = date.today()
    yesterday = today - timedelta(days=1)
    day_before_yesterday = today - timedelta(days=2)
    
    all_streaks = UserStreak.query.all()
    
    for streak in all_streaks:
        if not streak.last_active_date:
            continue
        
        # Если активность была вчера - всё ок
        if streak.last_active_date == yesterday:
            logger.info(f"User {streak.user_id} was active yesterday, streak continues")
            continue
        
        # Если активность была позавчера или раньше
        if streak.last_active_date <= day_before_yesterday:
            # Проверяем freeze
            if streak.freeze_available > 0:
                # Используем freeze
                streak.freeze_available -= 1
                streak.freeze_used_at = today
                logger.info(f"Used freeze for user {streak.user_id}, streak preserved: {streak.current_streak}")
            else:
                # Сбрасываем streak
                logger.info(f"Resetting streak for user {streak.user_id} from {streak.current_streak} to 0")
                streak.current_streak = 0
    
    # Восстанавливаем freeze раз в месяц
    for streak in all_streaks:
        if streak.freeze_used_at:
            days_since_freeze = (today - streak.freeze_used_at).days
            if days_since_freeze >= 30:
                streak.freeze_available = 1
                streak.freeze_used_at = None
                logger.info(f"Restored freeze for user {streak.user_id}")
    
    try:
        db.session.commit()
        logger.info(f"Streak reset completed for {len(all_streaks)} users")
    except Exception as e:
        logger.error(f"Error in streak reset: {e}")
        db.session.rollback()


def get_streak_stats(user_id: int) -> Dict:
    """
    Получить статистику streak для пользователя.
    
    Args:
        user_id: ID пользователя
        
    Returns:
        Dict со статистикой
    """
    streak = get_or_create_streak(user_id)
    today = date.today()
    
    # Проверяем, завершён ли квест на сегодня
    quest = DailyQuest.query.filter_by(
        user_id=user_id,
        date=today
    ).first()
    
    quest_completed_today = False
    if quest and quest.completed_count >= quest.total_count:
        quest_completed_today = True
    
    return {
        'current_streak': streak.current_streak,
        'longest_streak': streak.longest_streak,
        'last_active_date': streak.last_active_date.isoformat() if streak.last_active_date else None,
        'freeze_available': streak.freeze_available,
        'freeze_used_at': streak.freeze_used_at.isoformat() if streak.freeze_used_at else None,
        'quest_completed_today': quest_completed_today
    }


def get_streak_achievements(current_streak: int) -> list:
    """
    Получить достижения streak.
    
    Args:
        current_streak: Текущий streak
        
    Returns:
        List достижений
    """
    achievements = []
    milestones = [
        (7, '🔥 Неделя подряд!', 'bronze'),
        (30, '🏆 Месяц подряд!', 'silver'),
        (100, '💎 100 дней подряд!', 'gold'),
        (365, '👑 Год подряд!', 'platinum')
    ]
    
    for days, title, badge in milestones:
        if current_streak >= days:
            achievements.append({
                'days': days,
                'title': title,
                'badge': badge,
                'unlocked': True
            })
        else:
            achievements.append({
                'days': days,
                'title': title,
                'badge': badge,
                'unlocked': False,
                'progress': current_streak / days
            })
    
    return achievements
