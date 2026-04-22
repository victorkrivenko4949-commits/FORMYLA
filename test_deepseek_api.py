#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тестовый скрипт для проверки DeepSeek API
Запустите этот скрипт, чтобы убедиться, что API работает корректно
"""

import os
import sys
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Добавляем путь к модулям
sys.path.insert(0, os.path.dirname(__file__))

from ai.deepseek_client import DeepSeekClient

def test_simple_request():
    """Тест простого запроса"""
    print("\n" + "="*70)
    print("ТЕСТ 1: Простой запрос")
    print("="*70)
    
    try:
        client = DeepSeekClient()
        response = client.generate(
            prompt="Привет! Ответь одним словом: работает ли API?",
            temperature=0.3,
            max_tokens=50
        )
        print(f"✅ API работает!")
        print(f"Ответ: {response}")
        return True
    except Exception as e:
        print(f"❌ Ошибка: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_json_response():
    """Тест JSON ответа (как в AI-тьюторе)"""
    print("\n" + "="*70)
    print("ТЕСТ 2: JSON ответ с оценкой задачи")
    print("="*70)
    
    try:
        client = DeepSeekClient()
        
        system_prompt = """Ты AI-тьютор. Оцени ответ ученика и верни JSON:
{
  "score": 2,
  "feedback": "Ответ правильный! Молодец!"
}"""
        
        user_prompt = """Задача: Сколько будет 2+2?
Правильный ответ: 4
Ответ ученика: 4

Оцени ответ и верни JSON."""
        
        response = client.generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.3,
            max_tokens=500
        )
        
        print(f"✅ Получен ответ от API")
        print(f"Ответ (первые 500 символов):\n{response[:500]}")
        
        # Пробуем распарсить JSON
        import json
        import re
        
        cleaned = response.strip()
        cleaned = re.sub(r'```json\s*', '', cleaned)
        cleaned = re.sub(r'```\s*', '', cleaned)
        cleaned = cleaned.strip()
        
        data = json.loads(cleaned)
        print(f"\n✅ JSON успешно распарсен!")
        print(f"Score: {data.get('score')}")
        print(f"Feedback: {data.get('feedback')}")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_latex_response():
    """Тест ответа с LaTeX формулами"""
    print("\n" + "="*70)
    print("ТЕСТ 3: Ответ с LaTeX формулами")
    print("="*70)
    
    try:
        client = DeepSeekClient()
        
        system_prompt = """Ты AI-тьютор. Используй LaTeX для формул: \\( формула \\) для inline, \\[ формула \\] для display.
Верни JSON с feedback, содержащим LaTeX."""
        
        user_prompt = """Задача: Решите уравнение x^2 = 16
Правильный ответ: 4 и -4
Ответ ученика: 4

Оцени ответ и дай feedback с LaTeX. Верни JSON."""
        
        response = client.generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.3,
            max_tokens=800
        )
        
        print(f"✅ Получен ответ с LaTeX")
        print(f"Ответ:\n{response}")
        
        # Проверяем наличие LaTeX
        if '\\(' in response or '\\[' in response:
            print(f"\n✅ LaTeX формулы найдены в ответе!")
        else:
            print(f"\n⚠️  LaTeX формулы не найдены (возможно, модель не использовала их)")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Запуск всех тестов"""
    print("\n" + "="*70)
    print("ТЕСТИРОВАНИЕ DEEPSEEK API")
    print("="*70)
    
    # Проверка API ключа
    api_key = os.getenv('DEEPSEEK_API_KEY')
    if not api_key:
        print("\n❌ ОШИБКА: DEEPSEEK_API_KEY не найден в .env файле!")
        print("Создайте файл .env и добавьте:")
        print("DEEPSEEK_API_KEY=your_api_key_here")
        return
    
    print(f"\n✅ API ключ найден (длина: {len(api_key)} символов)")
    
    # Запуск тестов
    results = []
    results.append(("Простой запрос", test_simple_request()))
    results.append(("JSON ответ", test_json_response()))
    results.append(("LaTeX формулы", test_latex_response()))
    
    # Итоги
    print("\n" + "="*70)
    print("ИТОГИ ТЕСТИРОВАНИЯ")
    print("="*70)
    
    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{test_name}: {status}")
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    print(f"\nПройдено тестов: {passed}/{total}")
    
    if passed == total:
        print("\n🎉 Все тесты пройдены! API работает корректно.")
    else:
        print("\n⚠️  Некоторые тесты не прошли. Проверьте ошибки выше.")

if __name__ == "__main__":
    main()
