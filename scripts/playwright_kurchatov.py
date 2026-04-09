#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Playwright-парсер для скачивания PDF олимпиады Курчатова
Пилотный тест с видимым браузером
"""

from playwright.sync_api import sync_playwright
from pathlib import Path
import time
import re

TEMP_DIR = Path("temp_pdfs")
TEMP_DIR.mkdir(parents=True, exist_ok=True)


def download_kurchatov_pdfs(page):
    """Скачивание PDF Курчатова"""
    print("="*70)
    print("КУРЧАТОВ - СКАЧИВАНИЕ PDF")
    print("="*70)
    
    url = "https://old.olimpiadakurchatov.ru/archive"
    downloaded = 0
    
    try:
        print(f"\nОткрываю: {url}")
        page.goto(url, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(2000)
        
        print("Страница загружена. Ищу PDF...")
        
        # Ищем все ссылки на PDF
        pdf_links = page.locator('a[href*=".pdf"]').all()
        print(f"Найдено PDF-ссылок: {len(pdf_links)}")
        
        for link in pdf_links:
            try:
                href = link.get_attribute('href')
                text = link.inner_text()
                
                # Фильтруем только математику
                if not any(word in text.lower() + href.lower() for word in ['math', 'матем', 'задан', 'услов']):
                    continue
                
                # Определяем год
                year_match = re.search(r'20\d{2}', href + text)
                year = year_match.group() if year_match else "unknown"
                
                # Определяем класс
                grade_match = re.search(r'(\d{1,2})[_-]?класс|класс[_-]?(\d{1,2})|(\d{1,2})[_-]?grade', text.lower())
                grade = (grade_match.group(1) or grade_match.group(2) or grade_match.group(3)) if grade_match else "all"
                
                # Определяем этап
                stage = "final" if any(word in text.lower() for word in ['заключ', 'final', 'финал']) else "qual"
                
                print(f"\n[{downloaded+1}] {text[:50]}...")
                print(f"  Год: {year}, Класс: {grade}, Этап: {stage}")
                
                # Скачиваем
                try:
                    with page.expect_download(timeout=60000) as download_info:
                        link.click()
                    
                    download = download_info.value
                    filename = f"kurchatov_{year}_{stage}_g{grade}.pdf"
                    save_path = TEMP_DIR / filename
                    download.save_as(save_path)
                    
                    print(f"  [OK] {filename}")
                    downloaded += 1
                    page.wait_for_timeout(1000)
                    
                except Exception as e:
                    print(f"  [ERROR] Скачивание: {e}")
                
            except Exception as e:
                print(f"  [ERROR] Обработка ссылки: {e}")
        
    except Exception as e:
        print(f"[ERROR] {e}")
    
    return downloaded


def main():
    """Главная функция"""
    print("="*70)
    print("PLAYWRIGHT PARSER - КУРЧАТОВ (ПИЛОТНЫЙ ТЕСТ)")
    print("="*70)
    
    with sync_playwright() as p:
        print("\nЗапускаю браузер Chromium (видимый режим)...")
        browser = p.chromium.launch(
            headless=False,  # ВИДИМЫЙ режим
            slow_mo=500,  # Замедление для наблюдения
        )
        
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080}
        )
        
        page = context.new_page()
        
        # Скачиваем PDF Курчатова
        total = download_kurchatov_pdfs(page)
        
        print("\nЗакрываю браузер...")
        browser.close()
    
    print("\n" + "="*70)
    print(f"ИТОГО СКАЧАНО: {total} PDF")
    print(f"Папка: {TEMP_DIR.absolute()}")
    print("="*70)
    
    if total > 0:
        print("\nТеперь запустите: python scripts/extract_images.py")


if __name__ == "__main__":
    main()
