#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI Vision Linker - автоматическое сопоставление изображений с задачами
Использует Google Gemini Vision API для анализа изображений
"""

import os
import base64
import re
from pathlib import Path
import google.generativeai as genai

# Настройки
IMAGES_DIR = Path("static/images/problems")
SUGGESTIONS_FILE = "SMART_SUGGESTIONS.txt"

# Настройка Gemini API
API_KEY = os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY')

if not API_KEY:
    print("[ERROR] Не найден API ключ!")
    print("Установите переменную окружения GEMINI_API_KEY или GOOGLE_API_KEY")
    print("Получить ключ: https://makersuite.google.com/app/apikey")
    exit(1)

genai.configure(api_key=API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')


def encode_image(image_path):
    """Кодировать изображение в Base64"""
    with open(image_path, 'rb') as f:
        return base64.b64encode(f.read()).decode('utf-8')


def analyze_image_for_task(task_text, image_paths):
    """Использовать Gemini Vision для выбора подходящей картинки"""
    try:
        # Подготавливаем промпт
        prompt = f"""Ты эксперт по математическим олимпиадам. 

ТЕКСТ ЗАДАЧИ:
{task_text}

Я покажу тебе несколько изображений. Выбери ТУ ОДНУ картинку, которая лучше всего подходит к этой задаче (чертеж, схема, график).

ВАЖНО: Верни ТОЛЬКО имя файла подходящей картинки (например, "fu_2022_g5_fig1.png"). 
Если НИ ОДНА картинка не подходит, верни слово "NONE".
"""
        
        # Загружаем изображения
        images = []
        filenames = []
        for img_path in image_paths[:5]:  # Максимум 5 картинок за раз
            try:
                img_file = genai.upload_file(img_path)
                images.append(img_file)
                filenames.append(img_path.name)
            except:
                pass
        
        if not images:
            return None
        
        # Добавляем список файлов в промпт
        prompt += "\n\nФАЙЛЫ:\n" + "\n".join(filenames)
        
        # Отправляем запрос
        response = model.generate_content([prompt] + images)
        result = response.text.strip()
        
        # Очищаем ответ
        result = result.replace('"', '').replace("'", '').strip()
        
        # Проверяем, что это имя файла
        if result in filenames:
            return result
        elif "NONE" in result.upper():
            return None
        else:
            # Пытаемся найти имя файла в ответе
            for filename in filenames:
                if filename in result:
                    return filename
            return None
            
    except Exception as e:
        print(f"    [ERROR] AI Vision: {e}")
        return None


def parse_suggestions():
    """Парсинг файла предложений"""
    with open(SUGGESTIONS_FILE, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Парсим предложения
    suggestions = {}
    current_combo = None
    current_task = None
    
    for line in content.split('\n'):
        if line.startswith('# Combo'):
            match = re.search(r'Combo (\d+):', line)
            if match:
                current_combo = int(match.group(1))
        elif line.startswith('# Задача'):
            match = re.search(r'Задача (\d+):', line)
            if match:
                current_task = int(match.group(1))
                task_text = line.split(':', 2)[2].strip() if ':' in line else ""
                
                if current_combo and current_task:
                    key = (current_combo, current_task)
                    if key not in suggestions:
                        suggestions[key] = {'text': task_text, 'images': []}
        elif line.startswith('IMAGE_MAP'):
            match = re.search(r'"([^"]+)"', line)
            if match and current_combo and current_task:
                filename = match.group(1)
                key = (current_combo, current_task)
                if key in suggestions:
                    suggestions[key]['images'].append(filename)
    
    return suggestions


def main():
    """Главная функция"""
    print("="*70)
    print("AI VISION LINKER - АВТОМАТИЧЕСКОЕ СОПОСТАВЛЕНИЕ")
    print("="*70)
    
    # Парсим предложения
    print("\nПарсинг SMART_SUGGESTIONS.txt...")
    suggestions = parse_suggestions()
    print(f"Найдено задач: {len(suggestions)}")
    
    # Обрабатываем каждую задачу
    matched = 0
    skipped = 0
    new_mappings = []
    
    for (combo_id, prob_num), data in list(suggestions.items())[:10]:  # Первые 10 для теста
        task_text = data['text']
        image_files = data['images']
        
        print(f"\n[{matched+skipped+1}] Combo {combo_id}, Задача {prob_num}")
        print(f"  Текст: {task_text[:60]}...")
        print(f"  Кандидатов: {len(image_files)}")
        
        # Подготавливаем пути к изображениям
        image_paths = [IMAGES_DIR / img for img in image_files if (IMAGES_DIR / img).exists()]
        
        if not image_paths:
            print("  [SKIP] Файлы не найдены")
            skipped += 1
            continue
        
        # Анализируем через AI Vision
        print("  Анализирую через Gemini Vision...")
        best_image = analyze_image_for_task(task_text, image_paths)
        
        if best_image:
            print(f"  [OK] Выбрано: {best_image}")
            new_mappings.append((combo_id, prob_num, best_image))
            matched += 1
        else:
            print("  [SKIP] AI не уверен")
            skipped += 1
    
    # Сохраняем результаты
    if new_mappings:
        print(f"\nДобавляю {len(new_mappings)} привязок в problem_images.py...")
        
        with open('problem_images.py', 'a', encoding='utf-8') as f:
            f.write("\n# AI Vision автопривязка\n")
            for combo_id, prob_num, filename in new_mappings:
                f.write(f"IMAGE_MAP[({combo_id}, {prob_num})] = \"{filename}\"\n")
        
        print("[OK] Привязки добавлены")
    
    print("\n" + "="*70)
    print(f"ИТОГО:")
    print(f"  Распознано и привязано: {matched}")
    print(f"  Пропущено: {skipped}")
    print("="*70)
    
    if matched > 0:
        print("\nПерезапустите Flask-сервер для применения изменений")


if __name__ == "__main__":
    main()
