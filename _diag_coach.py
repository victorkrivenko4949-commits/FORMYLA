#!/usr/bin/env python3
"""Диагностика страницы куратора: проверяет greeting endpoint и сериализацию."""
import sys
import os
import json

# Добавляем корень проекта в путь
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)
os.chdir(project_root)

from app import app
from flask import session

# Тестовый user_id (предполагаем что user=1 существует)
TEST_USER_ID = 1

with app.test_client() as client:
    with client.session_transaction() as sess:
        sess['user_id'] = TEST_USER_ID
        sess['_user_id'] = str(TEST_USER_ID)
        sess['_fresh'] = True

    # Шаг 1: Проверяем страницу /prep/coach
    print("=" * 60)
    print("ШАГ 1: GET /prep/coach")
    print("=" * 60)
    resp = client.get('/prep/coach', follow_redirects=True)
    print(f"Статус: {resp.status_code}")
    print(f"Размер HTML: {len(resp.data)} байт")
    
    # Проверяем наличие ключевых элементов
    html = resp.data.decode('utf-8')
    checks = [
        ('masteryRadar canvas', 'id="masteryRadar"' in html),
        ('greetingMsg div', 'id="greetingMsg"' in html),
        ('ctaRow div', 'id="ctaRow"' in html),
        ('chatLog div', 'id="chatLog"' in html),
        ('chatForm', 'id="chatForm"' in html),
        ('chatInput', 'id="chatInput"' in html),
        ('mastery_radar.js script', 'mastery_radar.js' in html),
        ('data-mastery attr', 'data-mastery=' in html),
        ('greeting fetch URL', 'coach_greeting' in html),
        ('onboarding_test scenario JS', 'onboarding_test' in html),
        ('test_in_progress scenario JS', 'test_in_progress' in html),
        ('fallback scenario JS', 'fallback' in html),
        ('thinking indicator', 'Куратор думает' in html),
        ('addMsg returns div', 'return div' in html),
        ('addMsg returns null', 'return null' in html),
    ]
    print("\nПроверки HTML:")
    for name, ok in checks:
        status = "[OK]" if ok else "[ERROR]"
        print(f"  {status} {name}")

    # Шаг 2: Проверяем greeting endpoint
    print("\n" + "=" * 60)
    print("ШАГ 2: GET /prep/coach/greeting")
    print("=" * 60)
    resp2 = client.get('/prep/coach/greeting', follow_redirects=True)
    print(f"Статус: {resp2.status_code}")
    print(f"Content-Type: {resp2.content_type}")
    print(f"Размер: {len(resp2.data)} байт")
    
    try:
        data = json.loads(resp2.data.decode('utf-8'))
        print(f"\nОтвет (pretty):")
        print(json.dumps(data, ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"ОШИБКА парсинга JSON: {e}")
        print(f"Сырой ответ: {resp2.data[:500]}")

    # Шаг 3: Проверяем session coach_test
    print("\n" + "=" * 60)
    print("ШАГ 3: Проверка размера session cookie")
    print("=" * 60)
    with app.app_context():
        test_data = {
            'active': True,
            'task_ids': list(range(1, 22)),
            'current_index': 10,
            'answers': {str(i): f"Ответ на задачу {i} с подробным решением" for i in range(1, 22)},
            'awaiting_difficulty_for': None,
            'difficulty_ratings': {str(i): 5 for i in range(1, 22)},
        }
        test_data_str = json.dumps(test_data, ensure_ascii=False)
        print(f"Размер coach_test данных (полный тест): {len(test_data_str)} байт")
        print(f"Максимальный размер cookie (типичный): ~4096 байт")
        if len(test_data_str) > 4000:
            print("[ERROR] Данные сессии ПРЕВЫШАЮТ лимит cookie!")
        else:
            print("[OK] Данные сессии в пределах лимита")
        
        # Проверка размера с пустыми ответами (только что начатый тест)
        empty_data = {
            'active': True,
            'task_ids': list(range(1, 22)),
            'current_index': 0,
            'answers': {},
            'awaiting_difficulty_for': None,
            'difficulty_ratings': {},
        }
        empty_data_str = json.dumps(empty_data, ensure_ascii=False)
        print(f"Размер coach_test данных (только начат): {len(empty_data_str)} байт")

    # Шаг 4: Проверяем serialize radar data
    print("\n" + "=" * 60)
    print("ШАГ 4: Проверка сериализации радара")
    print("=" * 60)
    # Ищем data-mastery в HTML
    import re
    match = re.search(r'data-mastery=\'([^\']+)\'', html)
    if match:
        raw = match.group(1)
        print(f"Сырые данные (первые 200 символов): {raw[:200]}")
        try:
            parsed = json.loads(raw)
            print(f"Парсинг JSON: [OK] ({len(parsed)} элементов)")
            for item in parsed[:3]:
                print(f"  {item}")
        except Exception as e:
            print(f"[ERROR] Ошибка парсинга JSON: {e}")
    else:
        print("[ERROR] data-mastery не найден в HTML")

print("\n" + "=" * 60)
print("ДИАГНОСТИКА ЗАВЕРШЕНА")
print("=" * 60)
