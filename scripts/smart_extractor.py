#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Smart Extractor - умное извлечение изображений по позиции в PDF
Привязывает изображения к задачам по их расположению относительно номеров задач
"""

import fitz  # PyMuPDF
from pathlib import Path
import re

OUTPUT_DIR = Path("static/images/problems")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def find_task_positions(page):
    """Найти позиции задач на странице"""
    text = page.get_text("dict")
    tasks = []
    
    for block in text["blocks"]:
        if "lines" in block:
            for line in block["lines"]:
                for span in line["spans"]:
                    text_content = span["text"]
                    
                    # Ищем паттерны: "Задача 1", "1.", "№ 1", "Problem 1"
                    patterns = [
                        r'Задача\s+(\d+)',
                        r'^(\d+)\.',
                        r'№\s*(\d+)',
                        r'Problem\s+(\d+)',
                    ]
                    
                    for pattern in patterns:
                        match = re.search(pattern, text_content, re.IGNORECASE)
                        if match:
                            task_num = int(match.group(1))
                            bbox = span["bbox"]  # (x0, y0, x1, y1)
                            tasks.append({
                                'num': task_num,
                                'y_pos': bbox[1],  # Верхняя координата
                                'bbox': bbox
                            })
                            break
    
    return sorted(tasks, key=lambda x: x['y_pos'])


def extract_images_between_tasks(page, task_start_y, task_end_y):
    """Извлечь изображения между двумя задачами"""
    images = []
    
    # Получаем все изображения на странице
    image_list = page.get_images()
    
    for img_index, img in enumerate(image_list):
        try:
            # Получаем позицию изображения
            xref = img[0]
            
            # Извлекаем изображение
            base_image = page.parent.extract_image(xref)
            
            # Проверяем размер (фильтры)
            width = base_image.get("width", 0)
            height = base_image.get("height", 0)
            
            if width < 100 or height < 100:
                continue
            if 100 <= width <= 300 and abs(width - height) < 50:
                continue
            if len(base_image["image"]) < 2048:
                continue
            
            images.append({
                'data': base_image["image"],
                'ext': base_image["ext"],
                'width': width,
                'height': height
            })
            
        except:
            pass
    
    return images


def process_pdf(pdf_path, olympiad_id):
    """Обработать PDF и извлечь изображения с привязкой к задачам"""
    print(f"\n{'='*70}")
    print(f"Обрабатываю: {pdf_path.name}")
    print(f"{'='*70}")
    
    mappings = []
    
    try:
        doc = fitz.open(pdf_path)
        print(f"Страниц: {len(doc)}")
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            
            # Находим позиции задач
            tasks = find_task_positions(page)
            
            if not tasks:
                continue
            
            print(f"\nСтраница {page_num+1}: найдено задач: {len(tasks)}")
            
            # Для каждой задачи ищем изображения
            for i, task in enumerate(tasks):
                task_num = task['num']
                task_y_start = task['y_pos']
                
                # Определяем конец зоны задачи
                if i + 1 < len(tasks):
                    task_y_end = tasks[i + 1]['y_pos']
                else:
                    task_y_end = page.rect.height
                
                # Извлекаем изображения в этой зоне
                images = extract_images_between_tasks(page, task_y_start, task_y_end)
                
                if images:
                    print(f"  Задача {task_num}: найдено {len(images)} изображений")
                    
                    # Сохраняем первое подходящее изображение
                    img = images[0]
                    filename = f"{olympiad_id}_task{task_num}.{img['ext']}"
                    output_path = OUTPUT_DIR / filename
                    
                    with open(output_path, 'wb') as f:
                        f.write(img['data'])
                    
                    print(f"    [OK] {filename} ({img['width']}x{img['height']})")
                    
                    # Добавляем в маппинг
                    mappings.append((task_num, filename))
        
        doc.close()
        
    except Exception as e:
        print(f"[ERROR] {e}")
    
    return mappings


def main():
    """Главная функция"""
    print("="*70)
    print("SMART EXTRACTOR - УМНОЕ ИЗВЛЕЧЕНИЕ ПО ПОЗИЦИИ")
    print("="*70)
    
    # Тестируем на одном PDF
    test_pdf = Path("temp_pdfs/fu_2022_gall.pdf")
    
    if not test_pdf.exists():
        print(f"[ERROR] Файл {test_pdf} не найден")
        return
    
    # Обрабатываем
    mappings = process_pdf(test_pdf, "fu_2022_5")
    
    print(f"\n{'='*70}")
    print(f"ИТОГО ИЗВЛЕЧЕНО: {len(mappings)} изображений")
    print(f"{'='*70}")
    
    if mappings:
        print("\nДобавляю в problem_images.py...")
        # TODO: Нужен combo_id для привязки
        print("[INFO] Для автоматической привязки нужен combo_id")
        print("[INFO] Пока сохранены файлы, привязку добавьте вручную")


if __name__ == "__main__":
    main()
