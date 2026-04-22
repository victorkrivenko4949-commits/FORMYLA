#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Экспорт статей "Секреты" из локальной БД в JSON файл
Для последующего импорта на продакшен-сервере
"""

import json
from app import app
from models import db, OlympiadSecret

def export_secrets_to_json(filename='secrets_dump.json'):
    """
    Экспортирует все статьи из таблицы olympiad_secrets в JSON файл
    """
    print("\n" + "="*70)
    print("ЭКСПОРТ СТАТЕЙ 'СЕКРЕТЫ' ИЗ ЛОКАЛЬНОЙ БД")
    print("="*70)
    
    with app.app_context():
        # Получаем все статьи
        secrets = OlympiadSecret.query.all()
        
        if not secrets:
            print("\n[WARN] В локальной БД нет статей для экспорта!")
            print("Возможно, нужно сначала запустить seed_secrets.py локально")
            return
        
        # Конвертируем в список словарей
        secrets_data = []
        for secret in secrets:
            secrets_data.append({
                'topic': secret.topic,
                'title': secret.title,
                'content': secret.content,
                'difficulty_level': secret.difficulty_level
            })
        
        # Сохраняем в JSON
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(secrets_data, f, ensure_ascii=False, indent=2)
        
        print(f"\n[OK] Экспортировано статей: {len(secrets_data)}")
        print(f"[FILE] Файл сохранен: {filename}")
        
        # Статистика по темам
        topics_count = {}
        for secret in secrets_data:
            topic = secret['topic']
            topics_count[topic] = topics_count.get(topic, 0) + 1
        
        print("\n[STATS] Распределение по темам:")
        for topic, count in sorted(topics_count.items()):
            print(f"  - {topic}: {count} статей")
        
        print("\n" + "="*70)
        print("ГОТОВО! Теперь:")
        print("1. Загрузите secrets_dump.json на сервер")
        print("2. Запустите: python import_secrets.py")
        print("="*70 + "\n")

if __name__ == "__main__":
    export_secrets_to_json()
