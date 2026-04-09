#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для скачивания архивов олимпиадных заданий и извлечения изображений из PDF
"""

import os
import requests
from bs4 import BeautifulSoup
import fitz  # PyMuPDF
from pathlib import Path
import time

# Настройки
OUTPUT_DIR = Path("static/images/problems")
TEMP_DIR = Path("temp_pdfs")
YEARS = range(2018, 2025)  # 2018-2024

# Создаем директории
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# User-Agent для обхода защиты
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}


def download_file(url, output_path):
    """Скачать файл по URL"""
    try:
        print(f"Скачиваю: {url}")
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        
        with open(output_path, 'wb') as f:
            f.write(response.content)
        
        print(f"✓ Сохранено: {output_path}")
        return True
    except Exception as e:
        print(f"✗ Ошибка скачивания {url}: {e}")
        return False


def extract_images_from_pdf(pdf_path, olympiad_name, year, grade=None):
    """Извлечь все изображения из PDF"""
    images_extracted = 0
    
    try:
        doc = fitz.open(pdf_path)
        print(f"Обрабатываю PDF: {pdf_path} ({len(doc)} страниц)")
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            image_list = page.get_images()
            
            for img_index, img in enumerate(image_list):
                xref = img[0]
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                image_ext = base_image["ext"]
                
                # Формируем имя файла
                grade_str = f"_g{grade}" if grade else ""
                filename = f"{olympiad_name}_{year}{grade_str}_page{page_num+1}_img{img_index+1}.{image_ext}"
                output_path = OUTPUT_DIR / filename
                
                # Сохраняем изображение
                with open(output_path, "wb") as img_file:
                    img_file.write(image_bytes)
                
                images_extracted += 1
                print(f"  ✓ Извлечено: {filename}")
        
        doc.close()
        print(f"Всего извлечено изображений: {images_extracted}")
        return images_extracted
        
    except Exception as e:
        print(f"✗ Ошибка обработки PDF {pdf_path}: {e}")
        return 0


def parse_formula_unity():
    """Парсинг архива Формулы Единства"""
    print("\n" + "="*60)
    print("ФОРМУЛА ЕДИНСТВА (formulo.org)")
    print("="*60)
    
    base_url = "https://formulo.org"
    archive_url = f"{base_url}/ru/archive/"
    
    try:
        # Получаем страницу архива
        response = requests.get(archive_url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Ищем ссылки на PDF
        pdf_links = []
        for link in soup.find_all('a', href=True):
            href = link['href']
            if '.pdf' in href.lower():
                # Проверяем год
                for year in YEARS:
                    if str(year) in href or str(year-1) in href:  # Учитываем учебный год
                        full_url = href if href.startswith('http') else base_url + href
                        pdf_links.append((full_url, year))
                        break
        
        print(f"Найдено PDF-файлов: {len(pdf_links)}")
        
        # Скачиваем и обрабатываем
        total_images = 0
        for url, year in pdf_links:
            filename = f"formula_unity_{year}.pdf"
            pdf_path = TEMP_DIR / filename
            
            if download_file(url, pdf_path):
                time.sleep(1)  # Пауза между запросами
                images = extract_images_from_pdf(pdf_path, "fu", year)
                total_images += images
        
        print(f"\nИтого извлечено изображений: {total_images}")
        return total_images
        
    except Exception as e:
        print(f"✗ Ошибка парсинга Формулы Единства: {e}")
        return 0


def parse_lomonosov():
    """Парсинг архива олимпиады Ломоносова"""
    print("\n" + "="*60)
    print("ОЛИМПИАДА ЛОМОНОСОВА")
    print("="*60)
    
    # TODO: Реализовать парсинг сайта олимпиады Ломоносова
    # Обычно архивы лежат на olymp.msu.ru
    print("⚠ Парсинг Ломоносова пока не реализован")
    return 0


def parse_pvg():
    """Парсинг архива Покори Воробьевы горы"""
    print("\n" + "="*60)
    print("ПОКОРИ ВОРОБЬЕВЫ ГОРЫ")
    print("="*60)
    
    # TODO: Реализовать парсинг сайта ПВГ
    print("⚠ Парсинг ПВГ пока не реализован")
    return 0


def main():
    """Главная функция"""
    print("="*60)
    print("СКАЧИВАНИЕ И ИЗВЛЕЧЕНИЕ ИЗОБРАЖЕНИЙ ИЗ ОЛИМПИАДНЫХ PDF")
    print("="*60)
    
    total = 0
    
    # Формула Единства
    total += parse_formula_unity()
    
    # Ломоносов
    total += parse_lomonosov()
    
    # ПВГ
    total += parse_pvg()
    
    print("\n" + "="*60)
    print(f"ИТОГО ИЗВЛЕЧЕНО ИЗОБРАЖЕНИЙ: {total}")
    print("="*60)


if __name__ == "__main__":
    main()
