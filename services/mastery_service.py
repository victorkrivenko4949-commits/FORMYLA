# -*- coding: utf-8 -*-
"""
Topic Mastery Service for FORMYLA
Calculates user mastery level for each topic based on adaptive test history
"""

import json
from typing import Dict, List, Tuple
from datetime import datetime, timedelta
from models import db, TopicMastery, AdaptiveTestResult, AdaptiveTestProblem
import logging

logger = logging.getLogger(__name__)


def calculate_topic_mastery(user_id: int) -> Dict[str, Dict]:
    """
    Рассчитать мастерство пользователя по всем темам на основе истории адаптивных тестов.
    
    Args:
        user_id: ID пользователя
        
    Returns:
        Dict с темами и их параметрами: {
            'topic_name': {
                'mastery': 0.0-1.0,
                'solved': int,
                'attempts': int,
                'avg_level': float,
                'grade': int
            }
        }
    """
    # Получаем все результаты адаптивных тестов пользователя
    test_results = AdaptiveTestResult.query.filter_by(user_id=user_id).all()
    
    if not test_results:
        logger.info(f"No adaptive test results found for user {user_id}")
        return {}
    
    # Агрегируем данные по темам
    topic_stats = {}
    
    for result in test_results:
        topic = result.topic
        grade = result.class_level
        
        if not topic:
            continue
        
        key = f"{topic}_{grade}"
        
        if key not in topic_stats:
            topic_stats[key] = {
                'topic': topic,
                'grade': grade,
                'solved': 0,
                'attempts': 0,
                'total_level': 0.0,
                'final_levels': []
            }
        
        # Добавляем статистику
        topic_stats[key]['solved'] += result.tasks_correct or 0
        topic_stats[key]['attempts'] += result.tasks_total or 0
        topic_stats[key]['final_levels'].append(result.final_level or 3)
    
    # Рассчитываем mastery для каждой темы
    mastery_data = {}
    
    for key, stats in topic_stats.items():
        topic = stats['topic']
        grade = stats['grade']
        
        # Средний уровень IRT (1-7)
        avg_level = sum(stats['final_levels']) / len(stats['final_levels']) if stats['final_levels'] else 3.0
        
        # Процент правильных ответов
        accuracy = stats['solved'] / stats['attempts'] if stats['attempts'] > 0 else 0.0
        
        # Mastery = комбинация точности и уровня
        # Формула: (accuracy * 0.6) + ((avg_level - 1) / 6 * 0.4)
        # Точность важнее (60%), но уровень тоже учитывается (40%)
        mastery = (accuracy * 0.6) + ((avg_level - 1) / 6 * 0.4)
        mastery = max(0.0, min(1.0, mastery))  # Ограничиваем 0-1
        
        mastery_data[topic] = {
            'mastery': round(mastery, 3),
            'solved': stats['solved'],
            'attempts': stats['attempts'],
            'avg_level': round(avg_level, 2),
            'grade': grade
        }
        
        # Обновляем или создаём запись в БД
        topic_mastery = TopicMastery.query.filter_by(
            user_id=user_id,
            topic=topic,
            grade=grade
        ).first()
        
        if topic_mastery:
            topic_mastery.solved = stats['solved']
            topic_mastery.attempts = stats['attempts']
            topic_mastery.avg_level = avg_level
            topic_mastery.mastery = mastery
            topic_mastery.updated_at = datetime.utcnow()
        else:
            topic_mastery = TopicMastery(
                user_id=user_id,
                topic=topic,
                grade=grade,
                solved=stats['solved'],
                attempts=stats['attempts'],
                avg_level=avg_level,
                mastery=mastery
            )
            db.session.add(topic_mastery)
    
    try:
        db.session.commit()
        logger.info(f"Updated mastery for {len(mastery_data)} topics for user {user_id}")
    except Exception as e:
        logger.error(f"Error updating mastery: {e}")
        db.session.rollback()
    
    return mastery_data


def get_user_mastery(user_id: int) -> List[Dict]:
    """
    Получить текущее мастерство пользователя по всем темам из БД.
    
    Args:
        user_id: ID пользователя
        
    Returns:
        List of dicts с данными мастерства
    """
    masteries = TopicMastery.query.filter_by(user_id=user_id).all()
    
    return [{
        'topic': m.topic,
        'grade': m.grade,
        'mastery': m.mastery,
        'solved': m.solved,
        'attempts': m.attempts,
        'avg_level': m.avg_level,
        'updated_at': m.updated_at.isoformat() if m.updated_at else None
    } for m in masteries]


def get_weak_topics(user_id: int, threshold: float = 0.6, limit: int = 5) -> List[Tuple[str, int, float]]:
    """
    Получить слабые темы пользователя (mastery < threshold).
    
    Args:
        user_id: ID пользователя
        threshold: Порог мастерства (по умолчанию 0.6)
        limit: Максимальное количество тем
        
    Returns:
        List of tuples: (topic, grade, mastery)
    """
    weak_topics = TopicMastery.query.filter(
        TopicMastery.user_id == user_id,
        TopicMastery.mastery < threshold
    ).order_by(TopicMastery.mastery.asc()).limit(limit).all()
    
    return [(t.topic, t.grade, t.mastery) for t in weak_topics]


def get_medium_topics(user_id: int, min_mastery: float = 0.6, max_mastery: float = 0.8, limit: int = 3) -> List[Tuple[str, int, float]]:
    """
    Получить темы среднего уровня.
    
    Args:
        user_id: ID пользователя
        min_mastery: Минимальный порог
        max_mastery: Максимальный порог
        limit: Максимальное количество тем
        
    Returns:
        List of tuples: (topic, grade, mastery)
    """
    medium_topics = TopicMastery.query.filter(
        TopicMastery.user_id == user_id,
        TopicMastery.mastery >= min_mastery,
        TopicMastery.mastery <= max_mastery
    ).order_by(TopicMastery.mastery.asc()).limit(limit).all()
    
    return [(t.topic, t.grade, t.mastery) for t in medium_topics]


def get_strong_topics(user_id: int, threshold: float = 0.8, limit: int = 3) -> List[Tuple[str, int, float]]:
    """
    Получить сильные темы пользователя (mastery > threshold).
    
    Args:
        user_id: ID пользователя
        threshold: Порог мастерства (по умолчанию 0.8)
        limit: Максимальное количество тем
        
    Returns:
        List of tuples: (topic, grade, mastery)
    """
    strong_topics = TopicMastery.query.filter(
        TopicMastery.user_id == user_id,
        TopicMastery.mastery > threshold
    ).order_by(TopicMastery.mastery.desc()).limit(limit).all()
    
    return [(t.topic, t.grade, t.mastery) for t in strong_topics]


def update_mastery_after_task(user_id: int, topic: str, grade: int, is_correct: bool, difficulty: int):
    """
    Обновить мастерство после решения одной задачи (для Daily Quest).
    
    Args:
        user_id: ID пользователя
        topic: Тема задачи
        grade: Класс
        is_correct: Правильно ли решена
        difficulty: Уровень сложности (1-7)
    """
    mastery = TopicMastery.query.filter_by(
        user_id=user_id,
        topic=topic,
        grade=grade
    ).first()
    
    if not mastery:
        # Создаём новую запись
        mastery = TopicMastery(
            user_id=user_id,
            topic=topic,
            grade=grade,
            solved=1 if is_correct else 0,
            attempts=1,
            avg_level=float(difficulty),
            mastery=0.5  # Начальное значение
        )
        db.session.add(mastery)
    else:
        # Обновляем существующую
        mastery.attempts += 1
        if is_correct:
            mastery.solved += 1
        
        # Обновляем средний уровень (скользящее среднее)
        mastery.avg_level = (mastery.avg_level * (mastery.attempts - 1) + difficulty) / mastery.attempts
        
        # Пересчитываем mastery
        accuracy = mastery.solved / mastery.attempts if mastery.attempts > 0 else 0.0
        mastery.mastery = (accuracy * 0.6) + ((mastery.avg_level - 1) / 6 * 0.4)
        mastery.mastery = max(0.0, min(1.0, mastery.mastery))
        
        mastery.updated_at = datetime.utcnow()
    
    try:
        db.session.commit()
        logger.info(f"Updated mastery for user {user_id}, topic {topic}: {mastery.mastery:.3f}")
    except Exception as e:
        logger.error(f"Error updating mastery after task: {e}")
        db.session.rollback()
