#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Импорт статей "Секреты" из JSON файла в БД на продакшене
Запускать на сервере после загрузки secrets_dump.json
"""

import json
import os
from app import app
from models import db, OlympiadSecret

def import_secrets_from_json(filename='secrets_dump.json'):
    """
    Импортирует статьи из JSON файла в таблицу olympiad_secrets
    """
    print("\n" + "="*70)
    print("ИМПОРТ СТАТЕЙ 'СЕКРЕТЫ' В БД")
    print("="*70)
    
    # Проверка наличия файла
    if not os.path.exists(filename):
        print(f"\n[ERROR] Файл {filename} не найден!")
        print("Убедитесь, что вы загрузили файл на сервер")
        return
    
    with app.app_context():
        # Проверяем, есть ли уже статьи
        existing_count = OlympiadSecret.query.count()
        if existing_count > 0:
            print(f"\n[WARN] В БД уже есть {existing_count} статей")
            response = input("Удалить существующие и импортировать заново? (yes/no): ")
            if response.lower() == 'yes':
                OlympiadSecret.query.delete()
                db.session.commit()
                print("[OK] Старые статьи удалены")
            else:
                print("[STOP] Импорт отменен")
                return
        
        # Читаем JSON
        with open(filename, 'r', encoding='utf-8') as f:
            secrets_data = json.load(f)
        
        print(f"\n[INFO] Найдено статей в файле: {len(secrets_data)}")
        
        # Импортируем статьи
        imported = 0
        for secret_dict in secrets_data:
            try:
                secret = OlympiadSecret(
                    topic=secret_dict['topic'],
                    title=secret_dict['title'],
                    content=secret_dict['content'],
                    difficulty_level=secret_dict['difficulty_level']
                )
                db.session.add(secret)
                imported += 1
            except Exception as e:
                print(f"[ERROR] Ошибка при импорте статьи '{secret_dict.get('title', 'Unknown')}': {e}")
        
        # Сохраняем в БД
        db.session.commit()
        
        print(f"\n[OK] Успешно импортировано: {imported} статей")
        
        # Проверка
        total = OlympiadSecret.query.count()
        print(f"[CHECK] Всего статей в БД: {total}")
        
        # Статистика по темам
        topics = db.session.query(
            OlympiadSecret.topic,
            db.func.count(OlympiadSecret.id)
        ).group_by(OlympiadSecret.topic).all()
        
        print("\n[STATS] Распределение по темам:")
        for topic, count in topics:
            print(f"  - {topic}: {count} статей")
        
        print("\n" + "="*70)
        print("ИМПОРТ ЗАВЕРШЕН! Статьи доступны на сайте в разделе 'Секреты'")
        print("="*70 + "\n")

if __name__ == "__main__":
    import_secrets_from_json()
