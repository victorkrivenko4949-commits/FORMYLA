#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Парсинг архивов олимпиад с помощью Playwright
Скачивание PDF-файлов заданий
"""

from playwright.sync_api import sync_playwright
from pathlib import Path
import time
import re

# Настройки
TEMP_DIR = Path("temp_pdfs")
TEMP_DIR.mkdir(parents=True, exist_ok=True)

YEARS = range(2018, 2025)
GRADES = range(5, 12)


def download_formula_unity(page, download_dir):
    """Скачивание PDF с сайта Формулы Единства"""
    print("\n" + "="*70)
    print("ФОРМУЛА ЕДИНСТВА")
    print("="*70)
    
    urls_to_try = [
        "https://www.formulo.org/ru/olymp/math-olymp/math-archive/",
        "https://www.formulo.org/ru/olimpiady/",
        "https://www.formulo.org/ru/olymp-materials/",
    ]
    
    downloaded = 0
    
    for url in urls_to_try:
        try:
            print(f"\nПробую URL: {url}")
            page.goto(url, wait_until="networkidle", timeout=30000)
            time.sleep(2)
            
            # Ищем ссылки на PDF
            pdf_links = page.locator('a[href*=".pdf"]').all()
            print(f"Найдено PDF-ссылок: {len(pdf_links)}")
            
            for link in pdf_links:
                try:
                    href = link.get_attribute('href')
                    text = link.inner_text()
                    
                    # Проверяем год
                    year_match = re.search(r'20\d{2}', href + text)
                    if not year_match:
                        continue
                    
                    year = year_match.group()
                    if int(year) not in YEARS:
                        continue
                    
                    print(f"  Скачиваю: {text[:50]}... ({year})")
                    
                    # Скачиваем файл
                    with page.expect_download(timeout=60000) as download_info:
                        link.click()
                    
                    download = download_info.value
                    filename = f"fu_{year}_{download.suggested_filename}"
                    save_path = download_dir / filename
                    download.save_as(save_path)
                    
                    print(f"    [OK] Сохранено: {filename}")
                    downloaded += 1
                    time.sleep(1)
                    
                except Exception as e:
                    print(f"    [ERROR] {e}")
            
            if downloaded > 0:
                break  # Если нашли PDF, не пробуем другие URL
                
        except Exception as e:
            print(f"  [ERROR] Не удалось загрузить {url}: {e}")
    
    return downloaded


def download_lomonosov(page, download_dir):
    """Скачивание PDF олимпиады Ломоносова"""
    print("\n" + "="*70)
    print("ОЛИМПИАДА ЛОМОНОСОВА")
    print("="*70)
    
    urls_to_try = [
        "https://olymp.msu.ru/rus/archive/",
        "https://olymp.msu.ru/archive/",
    ]
    
    downloaded = 0
    
    for url in urls_to_try:
        try:
            print(f"\nПробую URL: {url}")
            page.goto(url, wait_until="networkidle", timeout=30000)
            time.sleep(2)
            
            # Ищем ссылки на PDF
            pdf_links = page.locator('a[href*=".pdf"]').all()
            print(f"Найдено PDF-ссылок: {len(pdf_links)}")
            
            for link in pdf_links[:10]:  # Ограничиваем для теста
                try:
                    href = link.get_attribute('href')
                    text = link.inner_text()
                    
                    print(f"  Скачиваю: {text[:50]}...")
                    
                    with page.expect_download(timeout=60000) as download_info:
                        link.click()
                    
                    download = download_info.value
                    filename = f"lomonosov_{download.suggested_filename}"
                    save_path = download_dir / filename
                    download.save_as(save_path)
                    
                    print(f"    [OK] Сохранено: {filename}")
                    downloaded += 1
                    time.sleep(1)
                    
                except Exception as e:
                    print(f"    [ERROR] {e}")
            
            if downloaded > 0:
                break
                
        except Exception as e:
            print(f"  [ERROR] Не удалось загрузить {url}: {e}")
    
    return downloaded


def main():
    """Главная функция"""
    print("="*70)
    print("PLAYWRIGHT PARSER - СКАЧИВАНИЕ PDF ОЛИМПИАД")
    print("="*70)
    
    total_downloaded = 0
    
    with sync_playwright() as p:
        # Запускаем браузер в видимом режиме
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        page = context.new_page()
        
        # Формула Единства
        total_downloaded += download_formula_unity(page, TEMP_DIR)
        
        # Ломоносов
        total_downloaded += download_lomonosov(page, TEMP_DIR)
        
        browser.close()
    
    print("\n" + "="*70)
    print(f"ИТОГО СКАЧАНО PDF: {total_downloaded}")
    print(f"Папка: {TEMP_DIR.absolute()}")
    print("="*70)


if __name__ == "__main__":
    main()
