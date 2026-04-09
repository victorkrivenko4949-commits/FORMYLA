#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Тестовый скрипт для проверки нового функционала AI-Тьютора
"""

import os
import sys
import codecs

# Fix Windows console encoding
if sys.platform == 'win32':
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

def test_deepseek_client():
    """Тест DeepSeek клиента с новыми методами."""
    print("=" * 60)
    print("ТЕСТ 1: DeepSeek Client - Новые методы")
    print("=" * 60)
    
    try:
        from ai.deepseek_client import DeepSeekClient, DeepSeekAPIError
        
        # Проверяем наличие API ключа
        api_key = os.environ.get('DEEPSEEK_API_KEY')
        if not api_key:
            print("❌ DEEPSEEK_API_KEY не найден в .env")
            print("   Создайте файл .env и добавьте: DEEPSEEK_API_KEY=sk-xxxxx")
            return False
        
        print(f"✓ API ключ найден: {api_key[:10]}...")
        
        # Инициализируем клиент
        client = DeepSeekClient()
        print("✓ DeepSeek клиент инициализирован")
        
        # Проверяем наличие новых методов
        assert hasattr(client, 'generate_hint'), "Метод generate_hint не найден"
        assert hasattr(client, 'generate_solution'), "Метод generate_solution не найден"
        print("✓ Методы generate_hint и generate_solution найдены")
        
        # Тестовая задача
        test_problem = "Найдите сумму чисел от 1 до 10"
        test_answer = "55"
        
        print("\n--- Тест generate_hint ---")
        print(f"Задача: {test_problem}")
        try:
            hint = client.generate_hint(test_problem, test_answer, difficulty=1)
            print(f"✓ Подсказка получена ({len(hint)} символов)")
            print(f"Первые 100 символов: {hint[:100]}...")
        except DeepSeekAPIError as e:
            print(f"❌ Ошибка API: {e}")
            return False
        except Exception as e:
            print(f"❌ Неожиданная ошибка: {e}")
            return False
        
        print("\n--- Тест generate_solution ---")
        try:
            solution = client.generate_solution(test_problem, test_answer, difficulty=1)
            print(f"✓ Решение получено ({len(solution)} символов)")
            print(f"Первые 100 символов: {solution[:100]}...")
        except DeepSeekAPIError as e:
            print(f"❌ Ошибка API: {e}")
            return False
        except Exception as e:
            print(f"❌ Неожиданная ошибка: {e}")
            return False
        
        print("\n✅ Все тесты DeepSeek клиента пройдены!")
        return True
        
    except ImportError as e:
        print(f"❌ Ошибка импорта: {e}")
        return False
    except Exception as e:
        print(f"❌ Неожиданная ошибка: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_api_endpoints():
    """Тест API эндпоинтов (проверка наличия в app.py)."""
    print("\n" + "=" * 60)
    print("ТЕСТ 2: API Endpoints")
    print("=" * 60)
    
    try:
        with open('app.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Проверяем наличие новых роутов
        endpoints = [
            '/api/tutor/hint/<int:problem_id>',
            '/api/tutor/solution/<int:problem_id>',
            'def get_ai_hint',
            'def get_ai_solution'
        ]
        
        for endpoint in endpoints:
            if endpoint in content:
                print(f"✓ Найден: {endpoint}")
            else:
                print(f"❌ Не найден: {endpoint}")
                return False
        
        print("\n✅ Все API эндпоинты найдены в app.py!")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False


def test_template_updates():
    """Тест обновлений в шаблоне."""
    print("\n" + "=" * 60)
    print("ТЕСТ 3: Template Updates")
    print("=" * 60)
    
    try:
        with open('templates/problem_detail.html', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Проверяем наличие новых элементов
        elements = [
            'getAIHint',
            'getAISolution',
            'ai-hint-',
            'ai-solution-',
            'hint-btn',
            'solution-btn',
            'Получить подсказку от AI',
            'Сгенерировать решение AI'
        ]
        
        for element in elements:
            if element in content:
                print(f"✓ Найден: {element}")
            else:
                print(f"❌ Не найден: {element}")
                return False
        
        print("\n✅ Все обновления шаблона найдены!")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False


def main():
    """Главная функция тестирования."""
    print("\n" + "=" * 60)
    print("ТЕСТИРОВАНИЕ ОБНОВЛЕННОГО AI-ТЬЮТОРА")
    print("=" * 60 + "\n")
    
    results = []
    
    # Тест 1: DeepSeek Client (только если есть API ключ)
    if os.environ.get('DEEPSEEK_API_KEY'):
        results.append(("DeepSeek Client", test_deepseek_client()))
    else:
        print("⚠️  DEEPSEEK_API_KEY не найден - пропускаем тест API")
        print("   Для полного тестирования добавьте ключ в .env файл\n")
    
    # Тест 2: API Endpoints
    results.append(("API Endpoints", test_api_endpoints()))
    
    # Тест 3: Template Updates
    results.append(("Template Updates", test_template_updates()))
    
    # Итоги
    print("\n" + "=" * 60)
    print("ИТОГИ ТЕСТИРОВАНИЯ")
    print("=" * 60)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {name}")
    
    all_passed = all(result for _, result in results)
    
    if all_passed:
        print("\n✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ!")
        print("\nСледующие шаги:")
        print("1. Запустите Flask сервер: python app.py")
        print("2. Откройте любую задачу в браузере")
        print("3. Нажмите кнопки AI-тьютора")
        print("4. Проверьте генерацию подсказок и решений")
    else:
        print("\n❌ НЕКОТОРЫЕ ТЕСТЫ НЕ ПРОШЛИ")
        print("   Проверьте ошибки выше")
    
    return 0 if all_passed else 1


if __name__ == '__main__':
    sys.exit(main())
