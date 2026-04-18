#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Скрипт для генерации и заполнения базы знаний олимпиадной математики
Использует DeepSeek API для автоматической генерации статей
"""

import os
import sys
from dotenv import load_dotenv
from app import app
from models import db, OlympiadSecret
from ai.deepseek_client import DeepSeekClient, DeepSeekAPIError

# Загрузка переменных окружения
load_dotenv()

# КРИТИЧЕСКИ ВАЖНЫЙ SYSTEM PROMPT для правильного форматирования LaTeX
SYSTEM_PROMPT = """Ты — тренер сборной по олимпиадной математике. Напиши глубокую статью-секрет на заданную тему НА РУССКОМ ЯЗЫКЕ.

ОБЯЗАТЕЛЬНО: Вся статья должна быть написана на РУССКОМ ЯЗЫКЕ для русскоязычных школьников и олимпиадников.

Структура статьи:
1. **Введение** — что это за метод и зачем он нужен
2. **Базовый пример** — простая задача с подробным решением
3. **Олимпиадная задача** — сложная задача с полным решением

ЖЕСТКИЕ ПРАВИЛА ОФОРМЛЕНИЯ МАТЕМАТИКИ (LaTeX):
1. ВЕСЬ математический текст, числа и формулы ОБЯЗАТЕЛЬНО оборачивай в \\( ... \\) (для инлайн) и \\[ ... \\] (для блоков).
2. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО использовать юникод-символы для степеней и корней (никаких ², ³, √ или ^ вне LaTeX).
3. СТЕПЕНИ И ИНДЕКСЫ: Строго используй _ и ^ внутри \\( ... \\). Если индекс/степень сложнее одного символа, используй фигурные скобки (например, \\( x_{n+1} \\), \\( 2^{k-1} \\)).
4. Дроби ТОЛЬКО через \\frac{}{}, корни ТОЛЬКО через \\sqrt{} (с подкоренным выражением в {}).
5. Неравенства, уравнения, все числа в тексте — всё в \\( ... \\).

Примеры ПРАВИЛЬНОГО форматирования:
- "Рассмотрим число \\( n = 2^k - 1 \\)"
- "По теореме Ферма \\( a^{p-1} \\equiv 1 \\pmod{p} \\)"
- "Неравенство \\( \\frac{a+b}{2} \\geq \\sqrt{ab} \\)"
- Блочная формула: \\[ x^2 + y^2 = z^2 \\]

Примеры НЕПРАВИЛЬНОГО форматирования (НЕ ДЕЛАЙ ТАК):
- "2³ = 8" (должно быть \\( 2^3 = 8 \\))
- "√2" (должно быть \\( \\sqrt{2} \\))
- "x² + y²" (должно быть \\( x^2 + y^2 \\))

Верни только текст статьи в Markdown без дополнительных комментариев."""

# База знаний: темы для генерации (20+ мощных олимпиадных методов)
TOPICS_DATABASE = [
    # Теория чисел
    {
        "topic": "Теория чисел",
        "title": "Малая теорема Ферма",
        "difficulty_level": 3,
        "prompt": "Малая теорема Ферма и её применение в олимпиадных задачах на делимость и сравнения"
    },
    {
        "topic": "Теория чисел",
        "title": "Диофантовы уравнения",
        "difficulty_level": 3,
        "prompt": "Методы решения диофантовых уравнений: спуск, параметризация, модульная арифметика"
    },
    {
        "topic": "Теория чисел",
        "title": "НОД и алгоритм Евклида",
        "difficulty_level": 2,
        "prompt": "Алгоритм Евклида, линейное представление НОД и применение в олимпиадных задачах"
    },
    {
        "topic": "Теория чисел",
        "title": "Китайская теорема об остатках",
        "difficulty_level": 3,
        "prompt": "Китайская теорема об остатках и её применение для решения систем сравнений"
    },
    
    # Комбинаторика
    {
        "topic": "Комбинаторика",
        "title": "Принцип Дирихле",
        "difficulty_level": 2,
        "prompt": "Принцип Дирихле (принцип ящиков): формулировки, обобщения и олимпиадные применения"
    },
    {
        "topic": "Комбинаторика",
        "title": "Метод шаров и перегородок",
        "difficulty_level": 2,
        "prompt": "Метод шаров и перегородок для подсчёта числа решений уравнений в натуральных числах"
    },
    {
        "topic": "Комбинаторика",
        "title": "Принцип включений-исключений",
        "difficulty_level": 3,
        "prompt": "Принцип включений-исключений и его применение в комбинаторных задачах"
    },
    {
        "topic": "Комбинаторика",
        "title": "Рекуррентные соотношения",
        "difficulty_level": 2,
        "prompt": "Составление и решение рекуррентных соотношений в комбинаторных задачах"
    },
    
    # Алгебра
    {
        "topic": "Алгебра",
        "title": "Неравенство Коши",
        "difficulty_level": 2,
        "prompt": "Неравенство Коши о средних (AM-GM) и его применение в олимпиадных задачах"
    },
    {
        "topic": "Алгебра",
        "title": "Метод замены переменных",
        "difficulty_level": 2,
        "prompt": "Искусство замены переменных для упрощения алгебраических уравнений и неравенств"
    },
    {
        "topic": "Алгебра",
        "title": "Теорема Виета",
        "difficulty_level": 2,
        "prompt": "Теорема Виета и её применение для решения систем и задач с параметрами"
    },
    {
        "topic": "Алгебра",
        "title": "Метод мажорант",
        "difficulty_level": 3,
        "prompt": "Метод мажорант (оценок) для доказательства неравенств и нахождения экстремумов"
    },
    
    # Геометрия
    {
        "topic": "Геометрия",
        "title": "Метод площадей",
        "difficulty_level": 2,
        "prompt": "Метод площадей в геометрии: вычисление отношений и доказательство теорем"
    },
    {
        "topic": "Геометрия",
        "title": "Теорема Менелая",
        "difficulty_level": 3,
        "prompt": "Теорема Менелая и её применение для доказательства коллинеарности точек"
    },
    {
        "topic": "Геометрия",
        "title": "Теорема Чевы",
        "difficulty_level": 3,
        "prompt": "Теорема Чевы и её применение для доказательства пересечения прямых в одной точке"
    },
    {
        "topic": "Геометрия",
        "title": "Метод координат",
        "difficulty_level": 2,
        "prompt": "Метод координат в планиметрии: когда и как применять для решения олимпиадных задач"
    },
    
    # Логика и инварианты
    {
        "topic": "Логика",
        "title": "Инварианты",
        "difficulty_level": 2,
        "prompt": "Метод инвариантов: поиск величин, не меняющихся при операциях"
    },
    {
        "topic": "Логика",
        "title": "Принцип крайнего",
        "difficulty_level": 2,
        "prompt": "Принцип крайнего: рассмотрение минимального/максимального элемента для доказательств"
    },
    {
        "topic": "Логика",
        "title": "Раскраски",
        "difficulty_level": 2,
        "prompt": "Метод раскрасок в олимпиадных задачах: шахматная раскраска и обобщения"
    },
    {
        "topic": "Логика",
        "title": "Принцип узких мест",
        "difficulty_level": 3,
        "prompt": "Принцип узких мест: анализ критических элементов в конструкциях"
    },
    
    # Графы
    {
        "topic": "Графы",
        "title": "Основы теории графов",
        "difficulty_level": 2,
        "prompt": "Основные понятия теории графов и их применение в олимпиадных задачах"
    },
    {
        "topic": "Графы",
        "title": "Эйлеровы и Гамильтоновы пути",
        "difficulty_level": 3,
        "prompt": "Эйлеровы и Гамильтоновы пути в графах: критерии существования и применение"
    },
    {
        "topic": "Графы",
        "title": "Деревья и их свойства",
        "difficulty_level": 2,
        "prompt": "Деревья в теории графов: определение, свойства и олимпиадные задачи"
    },
]


def generate_article(client: DeepSeekClient, topic_data: dict) -> str:
    """
    Генерирует статью через DeepSeek API
    
    Args:
        client: Инициализированный DeepSeek клиент
        topic_data: Словарь с данными темы
        
    Returns:
        Сгенерированный Markdown контент
    """
    prompt = f"Напиши статью на тему: {topic_data['prompt']}"
    
    try:
        content = client.generate(
            prompt=prompt,
            system_prompt=SYSTEM_PROMPT,
            temperature=0.7,
            max_tokens=4096
        )
        return content.strip()
    except DeepSeekAPIError as e:
        print(f"❌ Ошибка генерации для '{topic_data['title']}': {e}")
        return None


def seed_database():
    """Заполняет базу данных сгенерированными статьями"""
    
    # Проверка API ключа
    if not os.environ.get('DEEPSEEK_API_KEY'):
        print("❌ ОШИБКА: DEEPSEEK_API_KEY не найден в переменных окружения!")
        print("Создайте файл .env и добавьте: DEEPSEEK_API_KEY=your_key_here")
        sys.exit(1)
    
    # Инициализация клиента
    try:
        client = DeepSeekClient()
        print("✅ DeepSeek клиент инициализирован")
    except Exception as e:
        print(f"❌ Ошибка инициализации DeepSeek: {e}")
        sys.exit(1)
    
    # Инициализация базы данных
    with app.app_context():
        # Создаём таблицы если их нет
        db.create_all()
        
        # Проверяем, есть ли уже данные
        existing_count = OlympiadSecret.query.count()
        if existing_count > 0:
            print(f"⚠️  В базе уже есть {existing_count} статей.")
            response = input("Очистить базу и сгенерировать заново? (yes/no): ")
            if response.lower() in ['yes', 'y', 'да', 'д']:
                OlympiadSecret.query.delete()
                db.session.commit()
                print("✅ База очищена")
            else:
                print("❌ Генерация отменена")
                return
        
        print(f"\n🚀 Начинаем генерацию {len(TOPICS_DATABASE)} статей...\n")
        
        generated_count = 0
        failed_count = 0
        
        for i, topic_data in enumerate(TOPICS_DATABASE, 1):
            print(f"[{i}/{len(TOPICS_DATABASE)}] Генерация: {topic_data['title']}...")
            
            # Генерируем контент
            content = generate_article(client, topic_data)
            
            if content:
                # Сохраняем в базу
                secret = OlympiadSecret(
                    topic=topic_data['topic'],
                    title=topic_data['title'],
                    content=content,
                    difficulty_level=topic_data['difficulty_level']
                )
                db.session.add(secret)
                db.session.commit()
                
                generated_count += 1
                print(f"✅ Сохранено: {topic_data['title']}")
                
                # Показываем превью первой статьи для проверки форматирования
                if i == 1:
                    print("\n" + "="*80)
                    print("ПРЕВЬЮ ПЕРВОЙ СТАТЬИ (для проверки LaTeX форматирования):")
                    print("="*80)
                    print(content[:1000] + "..." if len(content) > 1000 else content)
                    print("="*80 + "\n")
            else:
                failed_count += 1
                print(f"❌ Не удалось сгенерировать: {topic_data['title']}")
            
            # Небольшая пауза между запросами
            if i < len(TOPICS_DATABASE):
                import time
                time.sleep(1)
        
        print(f"\n{'='*80}")
        print(f"📊 ИТОГИ ГЕНЕРАЦИИ:")
        print(f"✅ Успешно сгенерировано: {generated_count}")
        print(f"❌ Ошибок: {failed_count}")
        print(f"📚 Всего статей в базе: {OlympiadSecret.query.count()}")
        print(f"{'='*80}\n")
        
        # Показываем статистику по категориям
        print("📋 Статистика по категориям:")
        topics = db.session.query(
            OlympiadSecret.topic,
            db.func.count(OlympiadSecret.id)
        ).group_by(OlympiadSecret.topic).all()
        
        for topic, count in topics:
            print(f"  • {topic}: {count} статей")
        
        # Показываем одну полную статью для проверки
        print(f"\n{'='*80}")
        print("ПОЛНАЯ СТАТЬЯ 'Инварианты' (для проверки форматирования):")
        print("="*80)
        invariants = OlympiadSecret.query.filter_by(title="Инварианты").first()
        if invariants:
            print(invariants.content)
        else:
            # Показываем любую доступную статью
            any_article = OlympiadSecret.query.first()
            if any_article:
                print(f"(Статья 'Инварианты' не найдена, показываем '{any_article.title}')")
                print(any_article.content)
        print("="*80 + "\n")


if __name__ == "__main__":
    seed_database()
