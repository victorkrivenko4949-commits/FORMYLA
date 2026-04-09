#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Извлечение изображений из PDF-файлов олимпиад
"""

import fitz  # PyMuPDF
from pathlib import Path
import re

# Настройки
OUTPUT_DIR = Path("static/images/problems")
TEMP_DIR = Path("temp_pdfs")

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def parse_filename(filename):
    """Извлечь метаданные из имени файла"""
    olympiad = "unknown"
    year = "0000"
    grade = "0"
    
    # Определяем олимпиаду
    if "formula" in filename.lower() or "fu_" in filename.lower():
        olympiad = "fu"
    elif "lomonosov" in filename.lower() or "lom_" in filename.lower():
        olympiad = "lomonosov"
    elif "pvg" in filename.lower() or "vorobievy" in filename.lower():
        olympiad = "pvg"
    elif "euler" in filename.lower():
        olympiad = "euler"
    elif "kurchatov" in filename.lower():
        olympiad = "kurchatov"
    
    # Ищем год (4 цифры)
    year_match = re.search(r'20\d{2}', filename)
    if year_match:
        year = year_match.group()
    
    # Ищем класс
    grade_patterns = [
        r'[_-](\d{1,2})[_-]',
        r'class[_-]?(\d{1,2})',
        r'g(\d{1,2})',
        r'(\d{1,2})[_-]?class',
    ]
    for pattern in grade_patterns:
        match = re.search(pattern, filename.lower())
        if match:
            grade = match.group(1)
            break
    
    return olympiad, year, grade


def extract_images_from_pdf(pdf_path):
    """Извлечь все изображения из PDF"""
    olympiad, year, grade = parse_filename(pdf_path.stem)
    images_extracted = 0
    
    try:
        doc = fitz.open(pdf_path)
        print(f"\n[PDF] {pdf_path.name}")
        print(f"  Страниц: {len(doc)}")
        print(f"  Олимпиада: {olympiad}, Год: {year}, Класс: {grade}")
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            image_list = page.get_images()
            
            if image_list:
                print(f"  Страница {page_num+1}: {len(image_list)} изображений")
            
            for img_index, img in enumerate(image_list):
                try:
                    xref = img[0]
                    base_image = doc.extract_image(xref)
                    image_bytes = base_image["image"]
                    image_ext = base_image["ext"]
                    width = base_image.get("width", 0)
                    height = base_image.get("height", 0)
                    
                    # УМНЫЕ ФИЛЬТРЫ для отсеивания мусора
                    # Фильтр 1: Слишком маленькие (иконки, мелкий мусор)
                    if width < 100 or height < 100:
                        continue
                    
                    # Фильтр 2: QR-коды (квадратные, небольшие)
                    if 100 <= width <= 300 and 100 <= height <= 300 and abs(width - height) < 50:
                        continue
                    
                    # Фильтр 3: Слишком узкие/длинные (колонтитулы, разделители)
                    aspect_ratio = width / height if height > 0 else 0
                    if aspect_ratio > 10 or aspect_ratio < 0.1:
                        continue
                    
                    # Фильтр 4: Слишком маленький размер файла (< 2KB) - вероятно мусор
                    if len(image_bytes) < 2048:
                        continue
                    
                    # Формируем имя файла
                    img_filename = f"{olympiad}_{year}_g{grade}_p{page_num+1}_i{img_index+1}.{image_ext}"
                    output_path = OUTPUT_DIR / img_filename
                    
                    # Сохраняем
                    with open(output_path, "wb") as img_file:
                        img_file.write(image_bytes)
                    
                    images_extracted += 1
                    size_kb = len(image_bytes) / 1024
                    print(f"    [OK] {img_filename} ({width}x{height}, {size_kb:.1f} KB)")
                    
                except Exception as e:
                    print(f"    [ERROR] Ошибка извлечения: {e}")
        
        doc.close()
        print(f"  ИТОГО: {images_extracted} изображений")
        return images_extracted
        
    except Exception as e:
        print(f"  [ERROR] Ошибка PDF: {e}")
        return 0


def main():
    """Главная функция"""
    print("="*70)
    print("ИЗВЛЕЧЕНИЕ ИЗОБРАЖЕНИЙ ИЗ PDF")
    print("="*70)
    
    # Ищем все PDF
    pdf_files = list(TEMP_DIR.glob("*.pdf"))
    
    if not pdf_files:
        print(f"\n[!] Не найдено PDF-файлов в: {TEMP_DIR.absolute()}")
        print(f"[!] Сначала запустите playwright_parser.py для скачивания PDF")
        print(f"[!] Или положите PDF вручную в папку temp_pdfs/")
        return
    
    print(f"\nНайдено PDF-файлов: {len(pdf_files)}")
    
    total_images = 0
    for pdf_path in pdf_files:
        images = extract_images_from_pdf(pdf_path)
        total_images += images
    
    print("\n" + "="*70)
    print(f"ИТОГО:")
    print(f"  Обработано PDF: {len(pdf_files)}")
    print(f"  Извлечено изображений: {total_images}")
    print(f"  Папка: {OUTPUT_DIR.absolute()}")
    print("="*70)


if __name__ == "__main__":
    main()
