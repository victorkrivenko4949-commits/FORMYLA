#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Скрипт для проверки сгенерированных статей в базе данных
"""

from app import app
from models import db, OlympiadSecret

def check_secrets():
    """Проверить содержимое базы данных секретов"""
    with app.app_context():
        # Получаем общую статистику
        total = OlympiadSecret.query.count()
        print(f"\n{'='*80}")
        print(f"📊 СТАТИСТИКА БАЗЫ ЗНАНИЙ")
        print(f"{'='*80}")
        print(f"Всего статей: {total}\n")
        
        if total == 0:
            print("❌ База данных пуста. Запустите seed_secrets.py для генерации контента.")
            return
        
        # Статистика по категориям
        print("📋 Распределение по категориям:")
        topics = db.session.query(
            OlympiadSecret.topic,
            db.func.count(OlympiadSecret.id)
        ).group_by(OlympiadSecret.topic).all()
        
        for topic, count in topics:
            print(f"  • {topic}: {count} статей")
        
        # Статистика по сложности
        print("\n🎯 Распределение по сложности:")
        difficulties = db.session.query(
            OlympiadSecret.difficulty_level,
            db.func.count(OlympiadSecret.id)
        ).group_by(OlympiadSecret.difficulty_level).all()
        
        for level, count in difficulties:
            stars = "⭐" * level
            print(f"  {stars} Уровень {level}: {count} статей")
        
        # Показываем одну статью для проверки LaTeX
        print(f"\n{'='*80}")
        print("📄 ПРИМЕР СТАТЬИ (проверка LaTeX форматирования)")
        print(f"{'='*80}\n")
        
        # Ищем статью "Инварианты" или берём первую доступную
        sample = OlympiadSecret.query.filter_by(title="Инварианты").first()
        if not sample:
            sample = OlympiadSecret.query.first()
        
        if sample:
            print(f"Категория: {sample.topic}")
            print(f"Название: {sample.title}")
            print(f"Сложность: {'⭐' * sample.difficulty_level}")
            print(f"\nКонтент (первые 1500 символов):")
            print("-" * 80)
            print(sample.content[:1500])
            if len(sample.content) > 1500:
                print("\n... (контент обрезан)")
            print("-" * 80)
            
            # Проверяем наличие правильных LaTeX разделителей
            has_inline = "\\(" in sample.content and "\\)" in sample.content
            has_display = "\\[" in sample.content and "\\]" in sample.content
            has_bad_unicode = any(char in sample.content for char in ["²", "³", "√"])
            
            print(f"\n✅ Проверка форматирования:")
            print(f"  • Инлайн LaTeX \\( ... \\): {'✓ Найдено' if has_inline else '✗ Не найдено'}")
            print(f"  • Блочный LaTeX \\[ ... \\]: {'✓ Найдено' if has_display else '✗ Не найдено'}")
            print(f"  • Юникод-символы (плохо): {'✗ НАЙДЕНЫ!' if has_bad_unicode else '✓ Отсутствуют'}")
            
            if has_bad_unicode:
                print("\n⚠️  ВНИМАНИЕ: Обнаружены юникод-символы! Нужно перегенерировать с более строгим промптом.")
        
        print(f"\n{'='*80}\n")

if __name__ == "__main__":
    check_secrets()
