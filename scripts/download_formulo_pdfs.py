#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скачивание PDF с сайта Формулы Единства
Использует найденный рабочий URL
"""

import requests
from bs4 import BeautifulSoup
from pathlib import Path
import re
import time

TEMP_DIR = Path("temp_pdfs")
TEMP_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}


def download_pdf(url, filename):
    """Скачать PDF"""
    try:
        print(f"  Скачиваю: {url}")
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        
        filepath = TEMP_DIR / filename
        with open(filepath, 'wb') as f:
            f.write(response.content)
        
        size_mb = len(response.content) / (1024 * 1024)
        print(f"    [OK] {filename} ({size_mb:.2f} MB)")
        return True
    except Exception as e:
        print(f"    [ERROR] {e}")
        return False


def parse_formulo_materials():
    """Парсинг страницы с материалами"""
    print("="*70)
    print("ФОРМУЛА ЕДИНСТВА - СКАЧИВАНИЕ PDF")
    print("="*70)
    
    base_url = "https://www.formulo.org"
    materials_url = f"{base_url}/ru/olymp-materials/3/"
    
    downloaded = 0
    
    try:
        print(f"\nПарсинг: {materials_url}")
        response = requests.get(materials_url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Ищем все ссылки на PDF
        pdf_links = soup.find_all('a', href=re.compile(r'\.pdf$', re.I))
        print(f"Найдено PDF-ссылок: {len(pdf_links)}")
        
        for link in pdf_links:
            href = link.get('href')
            text = link.get_text(strip=True)
            
            # Формируем полный URL
            if href.startswith('http'):
                full_url = href
            elif href.startswith('/'):
                full_url = base_url + href
            else:
                full_url = base_url + '/' + href
            
            # Определяем год и класс из URL или текста
            year_match = re.search(r'20\d{2}', href + text)
            year = year_match.group() if year_match else "unknown"
            
            grade_match = re.search(r'(\d{1,2})[_-]?class|class[_-]?(\d{1,2})|g(\d{1,2})', href + text, re.I)
            grade = (grade_match.group(1) or grade_match.group(2) or grade_match.group(3)) if grade_match else "all"
            
            # Формируем имя файла
            filename = f"fu_{year}_g{grade}.pdf"
            
            print(f"\n[{downloaded+1}] {text[:50]}...")
            print(f"  URL: {full_url}")
            print(f"  Год: {year}, Класс: {grade}")
            
            if download_pdf(full_url, filename):
                downloaded += 1
                time.sleep(0.5)  # Пауза между запросами
        
    except Exception as e:
        print(f"[ERROR] {e}")
    
    return downloaded


def main():
    """Главная функция"""
    total = parse_formulo_materials()
    
    print("\n" + "="*70)
    print(f"ИТОГО СКАЧАНО: {total} PDF")
    print(f"Папка: {TEMP_DIR.absolute()}")
    print("="*70)
    
    if total > 0:
        print("\nТеперь запустите: python scripts/extract_images.py")


if __name__ == "__main__":
    main()
