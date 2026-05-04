# -*- coding: utf-8 -*-
"""
Daily Quest Service for FORMYLA
Generates personalized daily tasks based on user's topic mastery
"""

import json
import random
from typing import List, Dict, Optional
from datetime import datetime, date, timedelta
from models import db, DailyQuest, User, TopicMastery
from services.mastery_service import (
    calculate_topic_mastery,
    get_weak_topics,
    get_medium_topics,
    get_strong_topics
)
import logging

logger = logging.getLogger(__name__)


def get_tasks_from_db(topic: str, grade: int, difficulty: int, exclude_ids: List[int] = None) -> List[Dict]:
    """
    Получить задачи из базы данных по теме, классу и сложности.
    PROBLEMS_DB — список словарей с полями: id, subject, subtopic, grade, difficulty, text, answer
    
    Args:
        topic: Название темы (subject или subtopic)
        grade: Класс (5-11)
        difficulty: Уровень сложности (1-7)
        exclude_ids: Список ID задач для исключения
        
    Returns:
        List задач
    """
    from app import PROBLEMS_DB
    
    if exclude_ids is None:
        exclude_ids = []
    
    # Нормализуем тему для сравнения
    topic_lower = topic.lower()
    
    # Маппинг русских названий тем → английские subject/subtopic
    TOPIC_MAP = {
        'алгебра': ['algebra'],
        'геометрия': ['geometry'],
        'комбинаторика': ['combinatorics'],
        'теория чисел': ['number_theory', 'number theory'],
        'логика': ['logic'],
        'движение': ['movement', 'kl_movement'],
        'арифметика': ['arithmetic'],
    }
    
    # Получаем английские эквиваленты темы
    english_topics = TOPIC_MAP.get(topic_lower, [topic_lower])
    
    # Фильтруем задачи (PROBLEMS_DB — список)
    matching_tasks = []
    
    for task in PROBLEMS_DB:
        task_id = task.get('id')
        
        # Пропускаем уже решённые
        if task_id in exclude_ids:
            continue
        
        task_subject = task.get('subject', '').lower()
        task_subtopic = task.get('subtopic', '').lower()
        task_grade = task.get('grade', 0)
        task_difficulty = task.get('difficulty', 3)
        
        # Проверяем соответствие класса
        if task_grade != grade:
            continue
        
        # Проверяем соответствие темы (гибкое)
        topic_match = False
        for eng_topic in english_topics:
            if eng_topic in task_subject or eng_topic in task_subtopic:
                topic_match = True
                break
        # Также проверяем прямое вхождение
        if not topic_match:
            if topic_lower in task_subject or topic_lower in task_subtopic:
                topic_match = True
        
        if not topic_match:
            continue
        
        # Допускаем ±1 уровень сложности
        if abs(task_difficulty - difficulty) <= 1:
            matching_tasks.append({
                'id': task_id,
                'topic': task.get('subject', topic),
                'subtopic': task.get('subtopic', ''),
                'grade': task_grade,
                'difficulty': task_difficulty,
                'text': task.get('text', ''),
                'answer': task.get('answer', ''),
                'solution': task.get('solution', '')
            })
    
    return matching_tasks


def _get_olympiad_tasks_for_grade(user_grade: int, count: int = 5) -> List[Dict]:
    """
    Получить олимпиадные задачи из COMBOS для указанного класса.
    Это реальные задачи ВсОШ, Турнира городов, Эйлера — гораздо сложнее PROBLEMS_DB.
    """
    from app import COMBOS
    
    all_problems = []
    for combo in COMBOS:
        combo_grade = combo.get('grade', 0)
        # Берём задачи для класса пользователя ±1
        if abs(int(combo_grade) - user_grade) <= 1:
            for p in combo.get('problems', []):
                text = p.get('text', '')
                if text and len(text) >= 50:
                    all_problems.append({
                        'id': combo.get('id', 0) * 100 + p.get('num', 1),
                        'topic': combo.get('olympiad', 'olympiad'),
                        'subject': combo.get('olympiad_title', 'Олимпиада'),
                        'subtopic': combo.get('round_title', ''),
                        'grade': int(combo_grade),
                        'difficulty': 6,  # Олимпиадный уровень
                        'text': text,
                        'answer': p.get('answer', ''),
                        'solution': p.get('solution', ''),
                        'olympiad_title': combo.get('olympiad_title', ''),
                        'year': combo.get('year', ''),
                    })
    
    if len(all_problems) >= count:
        return random.sample(all_problems, count)
    elif all_problems:
        return random.sample(all_problems, min(count, len(all_problems)))
    return []


def _generate_random_quest(user_id: int, today) -> Optional[DailyQuest]:
    """
    Генерирует квест из ОЛИМПИАДНЫХ задач (COMBOS) — реальные задачи ВсОШ, ТГ, Эйлер.
    Фильтрует по preferred_grade пользователя.
    Если олимпиадных задач нет — fallback на PROBLEMS_DB.
    """
    from app import PROBLEMS_DB
    
    # Получаем preferred_grade пользователя
    user = User.query.get(user_id)
    user_grade = user.preferred_grade if user and user.preferred_grade else 9
    
    # Сначала пробуем олимпиадные задачи (они сложнее!)
    selected = _get_olympiad_tasks_for_grade(user_grade, 5)
    
    if len(selected) >= 3:
        logger.info(f"Olympiad quest for user {user_id}, grade {user_grade}: {len(selected)} tasks")
    else:
        # Fallback на PROBLEMS_DB если олимпиадных мало
        logger.warning(f"Not enough olympiad tasks for grade {user_grade}, using PROBLEMS_DB")
        pool = PROBLEMS_DB
        if user_grade:
            grade_pool = [t for t in pool if t.get('grade') == user_grade]
            if len(grade_pool) >= 5:
                pool = grade_pool
        
        # Берём задачи уровня 5-7 (максимальная сложность)
        hard_tasks = [t for t in pool if t.get('difficulty', 3) >= 5]
        if len(hard_tasks) < 5:
            hard_tasks = [t for t in pool if t.get('difficulty', 3) >= 4]
        if len(hard_tasks) < 5:
            hard_tasks = pool
        
        sample_size = min(5, len(hard_tasks))
        selected = random.sample(hard_tasks, sample_size)
    
    logger.info(f"Quest for user {user_id}: {len(selected)} tasks selected")
    
    task_ids = [t['id'] for t in selected]
    grade_label = f" ({user_grade} класс)" if user_grade else ""
    ai_comment = f"🎯 **Твои олимпиадные задачи на сегодня**{grade_label}\n\n🏆 Подобраны задачи из реальных олимпиад (ВсОШ, Турнир городов, Эйлер). Пиши решение — ИИ-тьютор проверит!\n\nРешай последовательно, и ты получишь **+100 XP** за все 5 задач! 💪"
    
    quest = DailyQuest(
        user_id=user_id,
        date=today,
        task_ids=json.dumps(task_ids),
        completed_count=0,
        total_count=len(task_ids),
        xp_earned=0,
        ai_comment=ai_comment
    )
    
    db.session.add(quest)
    try:
        db.session.commit()
        logger.info(f"Generated random quest for user {user_id} with {len(task_ids)} tasks")
        return quest
    except Exception as e:
        logger.error(f"Error creating random quest: {e}")
        db.session.rollback()
        return None


def generate_daily_quest(user_id: int, force_regenerate: bool = False) -> Optional[DailyQuest]:
    """
    Сгенерировать Daily Quest для пользователя.
    
    Алгоритм:
    - 3 задачи по слабым темам (mastery < 0.6)
    - 1 задача средней сложности (mastery 0.6-0.8)
    - 1 задача-челлендж по сильной теме (mastery > 0.8)
    
    Args:
        user_id: ID пользователя
        force_regenerate: Принудительно пересоздать квест на сегодня
        
    Returns:
        DailyQuest объект или None
    """
    today = date.today()
    
    # Проверяем, есть ли уже квест на сегодня
    existing_quest = DailyQuest.query.filter_by(
        user_id=user_id,
        date=today
    ).first()
    
    if existing_quest and not force_regenerate:
        logger.info(f"Daily quest already exists for user {user_id} on {today}")
        return existing_quest
    
    # Удаляем старый квест если force_regenerate
    if existing_quest and force_regenerate:
        db.session.delete(existing_quest)
        db.session.commit()
    
    # Обновляем мастерство пользователя
    calculate_topic_mastery(user_id)
    
    # Получаем пользователя для определения класса
    user = User.query.get(user_id)
    if not user:
        logger.error(f"User {user_id} not found")
        return None
    
    # Определяем класс пользователя (preferred_grade или по умолчанию 7)
    user_grade = user.preferred_grade if user.preferred_grade else 7
    
    # Получаем темы разного уровня
    weak_topics = get_weak_topics(user_id, threshold=0.6, limit=10)
    medium_topics = get_medium_topics(user_id, min_mastery=0.6, max_mastery=0.8, limit=5)
    strong_topics = get_strong_topics(user_id, threshold=0.8, limit=5)
    
    # Если нет данных о мастерстве, используем случайные задачи из PROBLEMS_DB напрямую
    if not weak_topics and not medium_topics and not strong_topics:
        logger.warning(f"No mastery data for user {user_id}, picking random tasks from PROBLEMS_DB")
        return _generate_random_quest(user_id, today)
    
    # Собираем задачи
    selected_tasks = []
    task_distribution = []
    
    # 1. Три задачи по слабым темам
    for i, (topic, grade, mastery) in enumerate(weak_topics[:3]):
        # Используем preferred_grade пользователя вместо grade из мастерства
        task_grade = user_grade
        mastery_obj = TopicMastery.query.filter_by(
            user_id=user_id,
            topic=topic,
            grade=grade
        ).first()
        
        avg_level = int(mastery_obj.avg_level) if mastery_obj else 3
        tasks = get_tasks_from_db(topic, task_grade, avg_level, exclude_ids=[t['id'] for t in selected_tasks])
        # Fallback: если нет задач для preferred_grade, пробуем оригинальный grade
        if not tasks and task_grade != grade:
            tasks = get_tasks_from_db(topic, grade, avg_level, exclude_ids=[t['id'] for t in selected_tasks])
        
        if tasks:
            task = random.choice(tasks)
            selected_tasks.append(task)
            task_distribution.append({
                'type': 'weak',
                'topic': topic,
                'mastery': mastery,
                'difficulty': avg_level
            })
    
    # 2. Одна задача средней сложности
    if medium_topics:
        topic, grade, mastery = random.choice(medium_topics)
        task_grade = user_grade
        mastery_obj = TopicMastery.query.filter_by(
            user_id=user_id,
            topic=topic,
            grade=grade
        ).first()
        
        avg_level = int(mastery_obj.avg_level) + 1 if mastery_obj else 4
        tasks = get_tasks_from_db(topic, task_grade, avg_level, exclude_ids=[t['id'] for t in selected_tasks])
        if not tasks and task_grade != grade:
            tasks = get_tasks_from_db(topic, grade, avg_level, exclude_ids=[t['id'] for t in selected_tasks])
        
        if tasks:
            task = random.choice(tasks)
            selected_tasks.append(task)
            task_distribution.append({
                'type': 'medium',
                'topic': topic,
                'mastery': mastery,
                'difficulty': avg_level
            })
    
    # 3. Одна задача-челлендж по сильной теме
    if strong_topics:
        topic, grade, mastery = random.choice(strong_topics)
        task_grade = user_grade
        mastery_obj = TopicMastery.query.filter_by(
            user_id=user_id,
            topic=topic,
            grade=grade
        ).first()
        
        avg_level = int(mastery_obj.avg_level) + 1 if mastery_obj else 5
        tasks = get_tasks_from_db(topic, task_grade, avg_level, exclude_ids=[t['id'] for t in selected_tasks])
        if not tasks and task_grade != grade:
            tasks = get_tasks_from_db(topic, grade, avg_level, exclude_ids=[t['id'] for t in selected_tasks])
        
        if tasks:
            task = random.choice(tasks)
            selected_tasks.append(task)
            task_distribution.append({
                'type': 'challenge',
                'topic': topic,
                'mastery': mastery,
                'difficulty': avg_level
            })
    
    # Дополняем до 5 задач если не хватает
    while len(selected_tasks) < 5:
        # Берём случайную тему из слабых
        if weak_topics:
            topic, grade, mastery = random.choice(weak_topics)
            task_grade = user_grade
            mastery_obj = TopicMastery.query.filter_by(
                user_id=user_id,
                topic=topic,
                grade=grade
            ).first()
            
            avg_level = int(mastery_obj.avg_level) if mastery_obj else 3
            tasks = get_tasks_from_db(topic, task_grade, avg_level, exclude_ids=[t['id'] for t in selected_tasks])
            if not tasks and task_grade != grade:
                tasks = get_tasks_from_db(topic, grade, avg_level, exclude_ids=[t['id'] for t in selected_tasks])
            
            if tasks:
                task = random.choice(tasks)
                selected_tasks.append(task)
                task_distribution.append({
                    'type': 'weak',
                    'topic': topic,
                    'mastery': mastery,
                    'difficulty': avg_level
                })
            else:
                break
        else:
            break
    
    if len(selected_tasks) < 5:
        logger.warning(f"Could not generate 5 tasks for user {user_id}, got {len(selected_tasks)}")
        # Можно вернуть None или продолжить с меньшим количеством
    
    # Генерируем AI-комментарий
    ai_comment = generate_ai_intro(task_distribution, user_grade)
    
    # Создаём DailyQuest
    quest = DailyQuest(
        user_id=user_id,
        date=today,
        task_ids=json.dumps([t['id'] for t in selected_tasks]),
        completed_count=0,
        total_count=len(selected_tasks),
        xp_earned=0,
        ai_comment=ai_comment
    )
    
    db.session.add(quest)
    
    try:
        db.session.commit()
        logger.info(f"Generated daily quest for user {user_id} with {len(selected_tasks)} tasks")
        return quest
    except Exception as e:
        logger.error(f"Error creating daily quest: {e}")
        db.session.rollback()
        return None


def generate_ai_intro(task_distribution: List[Dict], user_grade: int = 7) -> str:
    """
    Сгенерировать AI-интро для Daily Quest.
    
    Args:
        task_distribution: Список задач с типами и темами
        user_grade: Класс пользователя (5-11)
        
    Returns:
        Текст комментария
    """
    weak_count = sum(1 for t in task_distribution if t['type'] == 'weak')
    medium_count = sum(1 for t in task_distribution if t['type'] == 'medium')
    challenge_count = sum(1 for t in task_distribution if t['type'] == 'challenge')
    
    intro = f"🎯 **Твои задачи на сегодня** ({user_grade} класс)\n\n"
    
    if weak_count > 0:
        weak_topics = [t['topic'] for t in task_distribution if t['type'] == 'weak']
        intro += f"📚 **{weak_count} задачи** для укрепления слабых мест: {', '.join(set(weak_topics))}.\n\n"
    
    if medium_count > 0:
        medium_topics = [t['topic'] for t in task_distribution if t['type'] == 'medium']
        intro += f"⚡ **{medium_count} задача** среднего уровня для прогресса: {', '.join(set(medium_topics))}.\n\n"
    
    if challenge_count > 0:
        challenge_topics = [t['topic'] for t in task_distribution if t['type'] == 'challenge']
        intro += f"🔥 **{challenge_count} челлендж** по твоей сильной теме: {', '.join(set(challenge_topics))}.\n\n"
    
    intro += "Решай последовательно, и ты получишь **+100 XP** за все 5 задач! 💪"
    
    return intro


def get_today_quest(user_id: int) -> Optional[DailyQuest]:
    """
    Получить квест на сегодня (или создать если нет).
    
    Args:
        user_id: ID пользователя
        
    Returns:
        DailyQuest или None
    """
    today = date.today()
    quest = DailyQuest.query.filter_by(user_id=user_id, date=today).first()
    
    if not quest:
        quest = generate_daily_quest(user_id)
    
    return quest


def get_quest_tasks(quest: DailyQuest) -> List[Dict]:
    """
    Получить полные данные задач для квеста.
    Ищет в PROBLEMS_DB и в COMBOS (олимпиадные задачи).
    
    Args:
        quest: DailyQuest объект
        
    Returns:
        List задач с полными данными
    """
    from app import PROBLEMS_DB, COMBOS
    
    task_ids = json.loads(quest.task_ids)
    
    # Строим индекс id→task для PROBLEMS_DB
    task_index = {task['id']: task for task in PROBLEMS_DB if 'id' in task}
    
    # Строим индекс для олимпиадных задач (combo_id * 100 + num)
    olympiad_index = {}
    for combo in COMBOS:
        combo_id = combo.get('id', 0)
        for p in combo.get('problems', []):
            oid = combo_id * 100 + p.get('num', 1)
            olympiad_index[oid] = {
                'id': oid,
                'topic': combo.get('olympiad', ''),
                'subject': combo.get('olympiad_title', 'Олимпиада'),
                'subtopic': combo.get('round_title', ''),
                'grade': combo.get('grade', 9),
                'difficulty': 6,
                'text': p.get('text', ''),
                'answer': p.get('answer', ''),
                'solution': p.get('solution', ''),
                'olympiad_title': combo.get('olympiad_title', ''),
                'year': combo.get('year', ''),
            }
    
    tasks = []
    for task_id in task_ids:
        if task_id in task_index:
            task = task_index[task_id].copy()
            tasks.append(task)
        elif task_id in olympiad_index:
            tasks.append(olympiad_index[task_id])
    
    return tasks


def complete_quest_task(quest: DailyQuest, task_index: int, is_correct: bool, xp_earned: int = 20):
    """
    Отметить задачу в квесте как выполненную.
    
    Args:
        quest: DailyQuest объект
        task_index: Индекс задачи (0-4)
        is_correct: Правильно ли решена
        xp_earned: Заработано XP за задачу
    """
    if is_correct:
        quest.completed_count += 1
        quest.xp_earned += xp_earned
        
        # Проверяем, завершён ли квест
        if quest.completed_count >= quest.total_count:
            quest.completed_at = datetime.utcnow()
            # Бонус за все 5 задач
            quest.xp_earned += 100
    
    try:
        db.session.commit()
        logger.info(f"Quest task {task_index} completed for quest {quest.id}")
    except Exception as e:
        logger.error(f"Error completing quest task: {e}")
        db.session.rollback()
