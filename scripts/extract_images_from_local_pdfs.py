#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Извлечение изображений из локальных PDF-файлов
Положите PDF в папку temp_pdfs/ и запустите скрипт
"""

import os
import fitz  # PyMuPDF
from pathlib import Path
import re

# Настройки
OUTPUT_DIR = Path("static/images/problems")
TEMP_DIR = Path("temp_pdfs")

# Создаем директории
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)


def extract_images_from_pdf(pdf_path):
    """Извлечь все изображения из PDF"""
    images_extracted = 0
    
    # Определяем олимпиаду и год из имени файла
    filename = pdf_path.stem
    
    # Пытаемся распарсить имя файла
    olympiad = "unknown"
    year = "0000"
    grade = "0"
    
    # Паттерны для разных форматов имен
    if "formula" in filename.lower() or "fu" in filename.lower():
        olympiad = "fu"
    elif "lomonosov" in filename.lower():
        olympiad = "lomonosov"
    elif "pvg" in filename.lower() or "vorobievy" in filename.lower():
        olympiad = "pvg"
    
    # Ищем год (4 цифры)
    year_match = re.search(r'20\d{2}', filename)
    if year_match:
        year = year_match.group()
    
    # Ищем класс
    grade_match = re.search(r'[_-](\d{1,2})[_-]|class(\d{1,2})|g(\d{1,2})', filename.lower())
    if grade_match:
        grade = grade_match.group(1) or grade_match.group(2) or grade_match.group(3)
    
    try:
        doc = fitz.open(pdf_path)
        print(f"\nОбрабатываю: {pdf_path.name} ({len(doc)} страниц)")
        print(f"  Олимпиада: {olympiad}, Год: {year}, Класс: {grade}")
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            image_list = page.get_images()
            
            if image_list:
                print(f"  Страница {page_num+1}: найдено {len(image_list)} изображений")
            
            for img_index, img in enumerate(image_list):
                try:
                    xref = img[0]
                    base_image = doc.extract_image(xref)
                    image_bytes = base_image["image"]
                    image_ext = base_image["ext"]
                    
                    # Имя файла
                    img_filename = f"{olympiad}_{year}_g{grade}_p{page_num+1}_i{img_index+1}.{image_ext}"
                    output_path = OUTPUT_DIR / img_filename
                    
                    # Сохраняем
                    with open(output_path, "wb") as img_file:
                        img_file.write(image_bytes)
                    
                    images_extracted += 1
                    print(f"    [OK] {img_filename} ({len(image_bytes)} bytes)")
                    
                except Exception as e:
                    print(f"    [ERROR] Ошибка извлечения: {e}")
        
        doc.close()
        print(f"  ИТОГО извлечено: {images_extracted} изображений")
        return images_extracted
        
    except Exception as e:
        print(f"  [ERROR] Ошибка PDF: {e}")
        return 0


def main():
    """Главная функция"""
    print("="*70)
    print("ИЗВЛЕЧЕНИЕ ИЗОБРАЖЕНИЙ ИЗ ЛОКАЛЬНЫХ PDF")
    print("="*70)
    
    # Ищем все PDF в temp_pdfs/
    pdf_files = list(TEMP_DIR.glob("*.pdf"))
    
    if not pdf_files:
        print(f"\n[!] Не найдено PDF-файлов в папке: {TEMP_DIR.absolute()}")
        print(f"[!] Положите PDF-файлы в эту папку и запустите скрипт снова")
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
    print(f"  Папка с изображениями: {OUTPUT_DIR.absolute()}")
    print("="*70)


if __name__ == "__main__":
    main()
