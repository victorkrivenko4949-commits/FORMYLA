#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для скачивания PDF олимпиад и извлечения изображений
Использует прямые ссылки на PDF-файлы
"""

import os
import requests
import fitz  # PyMuPDF
from pathlib import Path
import time

# Настройки
OUTPUT_DIR = Path("static/images/problems")
TEMP_DIR = Path("temp_pdfs")

# Создаем директории
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

# Прямые ссылки на PDF олимпиад
# Формат: (URL, олимпиада, год, класс)
PDF_SOURCES = [
    # Формула Единства - известные URL
    ("https://formulo.org/data/2022/final/5.pdf", "fu", 2022, 5),
    ("https://formulo.org/data/2022/final/6.pdf", "fu", 2022, 6),
    ("https://formulo.org/data/2022/final/7.pdf", "fu", 2022, 7),
    ("https://formulo.org/data/2023/final/5.pdf", "fu", 2023, 5),
    ("https://formulo.org/data/2023/final/6.pdf", "fu", 2023, 6),
    
    # Альтернативные URL
    ("https://www.formulo.org/data/2022/final/5.pdf", "fu", 2022, 5),
    ("https://www.formulo.org/data/2022/final/6.pdf", "fu", 2022, 6),
]


def download_file(url, output_path):
    """Скачать файл"""
    try:
        print(f"Скачиваю: {url}")
        response = requests.get(url, headers=HEADERS, timeout=30, allow_redirects=True)
        
        if response.status_code == 404:
            print(f"  [X] 404 Not Found")
            return False
            
        response.raise_for_status()
        
        with open(output_path, 'wb') as f:
            f.write(response.content)
        
        file_size = os.path.getsize(output_path)
        print(f"  [OK] Сохранено: {output_path} ({file_size} bytes)")
        return True
    except Exception as e:
        print(f"  [ERROR] Ошибка: {e}")
        return False


def extract_images_from_pdf(pdf_path, olympiad, year, grade):
    """Извлечь изображения из PDF"""
    images_extracted = 0
    
    try:
        doc = fitz.open(pdf_path)
        print(f"  Обрабатываю PDF: {len(doc)} страниц")
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            image_list = page.get_images()
            
            for img_index, img in enumerate(image_list):
                try:
                    xref = img[0]
                    base_image = doc.extract_image(xref)
                    image_bytes = base_image["image"]
                    image_ext = base_image["ext"]
                    
                    # Имя файла
                    filename = f"{olympiad}_{year}_g{grade}_p{page_num+1}_i{img_index+1}.{image_ext}"
                    output_path = OUTPUT_DIR / filename
                    
                    # Сохраняем
                    with open(output_path, "wb") as img_file:
                        img_file.write(image_bytes)
                    
                    images_extracted += 1
                    print(f"    [OK] {filename}")
                except Exception as e:
                    print(f"    [ERROR] Ошибка извлечения: {e}")
        
        doc.close()
        print(f"  Извлечено: {images_extracted} изображений")
        return images_extracted
        
    except Exception as e:
        print(f"  [ERROR] Ошибка PDF: {e}")
        return 0


def main():
    """Главная функция"""
    print("="*70)
    print("СКАЧИВАНИЕ PDF И ИЗВЛЕЧЕНИЕ ИЗОБРАЖЕНИЙ")
    print("="*70)
    
    total_pdfs = 0
    total_images = 0
    
    for url, olympiad, year, grade in PDF_SOURCES:
        filename = f"{olympiad}_{year}_g{grade}.pdf"
        pdf_path = TEMP_DIR / filename
        
        if download_file(url, pdf_path):
            total_pdfs += 1
            images = extract_images_from_pdf(pdf_path, olympiad, year, grade)
            total_images += images
            time.sleep(0.5)  # Пауза между запросами
    
    print("\n" + "="*70)
    print(f"ИТОГО:")
    print(f"  Скачано PDF: {total_pdfs}")
    print(f"  Извлечено изображений: {total_images}")
    print(f"  Папка с изображениями: {OUTPUT_DIR.absolute()}")
    print("="*70)


if __name__ == "__main__":
    main()
