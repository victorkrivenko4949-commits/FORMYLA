#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Утилиты для сидирования таблицы OlympiadSecret
Используется как локально, так и через защищенный админ-роут
"""

import json
import os
from models import db, OlympiadSecret


def seed_secrets_from_json(json_file='secrets_dump.json', force=False):
    """
    Импортирует статьи из JSON файла в таблицу olympiad_secrets.
    
    Args:
        json_file: Путь к JSON файлу с данными
        force: Если True, очищает таблицу перед импортом
    
    Returns:
        dict: {
            'success': bool,
            'inserted': int,
            'skipped': int,
            'total': int,
            'error': str (если success=False)
        }
    """
    try:
        # Проверка наличия файла
        if not os.path.exists(json_file):
            return {
                'success': False,
                'inserted': 0,
                'skipped': 0,
                'total': 0,
                'error': f'File {json_file} not found'
            }
        
        # Проверяем, есть ли уже статьи
        existing_count = OlympiadSecret.query.count()

        # Если force=True, очищаем таблицу
        if force and existing_count > 0:
            OlympiadSecret.query.delete()
            db.session.commit()

        # Читаем JSON
        with open(json_file, 'r', encoding='utf-8') as f:
            secrets_data = json.load(f)

        # UPSERT по title: новые — INSERT, существующие — обновляем content,
        # если он изменился (например, добавлена галерея чертежей).
        # Раньше при force=False ничего не делали, что блокировало накат
        # обновлений content на прод. Теперь idempotent и безопасно.
        inserted = 0
        updated = 0
        skipped = 0

        for secret_dict in secrets_data:
            try:
                existing = OlympiadSecret.query.filter_by(
                    title=secret_dict['title']
                ).first()

                new_content = secret_dict.get('content') or ''

                if existing:
                    # Обновляем content/topic/difficulty при изменении
                    changed = False
                    if (existing.content or '') != new_content:
                        existing.content = new_content
                        changed = True
                    if existing.topic != secret_dict.get('topic'):
                        existing.topic = secret_dict.get('topic')
                        changed = True
                    new_diff = secret_dict.get('difficulty_level')
                    if new_diff is not None and existing.difficulty_level != new_diff:
                        existing.difficulty_level = new_diff
                        changed = True
                    if changed:
                        updated += 1
                    else:
                        skipped += 1
                    continue

                # Новая статья
                secret = OlympiadSecret(
                    topic=secret_dict['topic'],
                    title=secret_dict['title'],
                    content=new_content,
                    difficulty_level=secret_dict['difficulty_level']
                )
                db.session.add(secret)
                inserted += 1

            except Exception as e:
                print(f"[ERROR] Failed to import secret '{secret_dict.get('title', 'Unknown')}': {e}")
                skipped += 1

        # Сохраняем в БД
        db.session.commit()

        return {
            'success': True,
            'inserted': inserted,
            'updated': updated,
            'skipped': skipped,
            'total': inserted + updated + skipped,
            'message': (
                f'Successfully imported {inserted} new, '
                f'updated {updated} existing, skipped {skipped} unchanged'
            )
        }
        
    except Exception as e:
        db.session.rollback()
        return {
            'success': False,
            'inserted': 0,
            'skipped': 0,
            'total': 0,
            'error': str(e)
        }


def get_secrets_stats():
    """
    Возвращает статистику по таблице olympiad_secrets.
    
    Returns:
        dict: {
            'total': int,
            'by_topic': dict,
            'by_difficulty': dict
        }
    """
    try:
        total = OlympiadSecret.query.count()
        
        # Статистика по темам
        topics = db.session.query(
            OlympiadSecret.topic,
            db.func.count(OlympiadSecret.id)
        ).group_by(OlympiadSecret.topic).all()
        
        by_topic = {topic: count for topic, count in topics}
        
        # Статистика по сложности
        difficulties = db.session.query(
            OlympiadSecret.difficulty_level,
            db.func.count(OlympiadSecret.id)
        ).group_by(OlympiadSecret.difficulty_level).all()
        
        by_difficulty = {level: count for level, count in difficulties}
        
        return {
            'total': total,
            'by_topic': by_topic,
            'by_difficulty': by_difficulty
        }
        
    except Exception as e:
        return {
            'total': 0,
            'by_topic': {},
            'by_difficulty': {},
            'error': str(e)
        }
