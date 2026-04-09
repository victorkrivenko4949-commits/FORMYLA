#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скачивание PDF всех олимпиад
Playwright (headless) + requests для надежности
"""

from playwright.sync_api import sync_playwright
import requests
from pathlib import Path
import time
import re

TEMP_DIR = Path("temp_pdfs")
TEMP_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}


def download_pdf(url, filename):
    """Скачать PDF через requests"""
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        if response.status_code == 200 and len(response.content) > 1000:
            filepath = TEMP_DIR / filename
            with open(filepath, 'wb') as f:
                f.write(response.content)
            size_kb = len(response.content) / 1024
            print(f"  [OK] {filename} ({size_kb:.1f} KB)")
            return True
    except:
        pass
    return False


def parse_kurchatov():
    """Парсинг Курчатова через Playwright"""
    print("\n" + "="*70)
    print("КУРЧАТОВ")
    print("="*70)
    
    downloaded = 0
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)  # Фоновый режим
        page = browser.new_page(user_agent=HEADERS['User-Agent'])
        
        try:
            print("Загружаю https://old.olimpiadakurchatov.ru/archive")
            page.goto("https://old.olimpiadakurchatov.ru/archive", timeout=30000)
            page.wait_for_timeout(2000)
            
            # Получаем все PDF-ссылки
            pdf_links = page.locator('a[href*=".pdf"]').all()
            print(f"Найдено PDF: {len(pdf_links)}")
            
            urls_to_download = []
            for link in pdf_links[:50]:  # Ограничиваем
                try:
                    href = link.get_attribute('href')
                    text = link.inner_text()
                    
                    if not href:
                        continue
                    
                    # Фильтр: только математика
                    if not any(w in text.lower() + href.lower() for w in ['math', 'матем', 'задан']):
                        continue
                    
                    # Полный URL
                    if href.startswith('http'):
                        full_url = href
                    else:
                        full_url = f"https://old.olimpiadakurchatov.ru{href}"
                    
                    # Метаданные
                    year = re.search(r'20\d{2}', href + text)
                    year = year.group() if year else "unknown"
                    
                    urls_to_download.append((full_url, year, text))
                except:
                    pass
            
            browser.close()
            
            # Скачиваем через requests
            print(f"\nСкачиваю {len(urls_to_download)} файлов...")
            for url, year, text in urls_to_download:
                filename = f"kurchatov_{year}.pdf"
                print(f"[{downloaded+1}] {text[:40]}...")
                if download_pdf(url, filename):
                    downloaded += 1
                time.sleep(0.5)
                
        except Exception as e:
            print(f"[ERROR] {e}")
            browser.close()
    
    return downloaded


def parse_vysshaya_proba():
    """Парсинг Высшей пробы"""
    print("\n" + "="*70)
    print("ВЫСШАЯ ПРОБА")
    print("="*70)
    
    downloaded = 0
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=HEADERS['User-Agent'])
        
        try:
            print("Загружаю https://olymp.hse.ru/mmo/tasks-math")
            page.goto("https://olymp.hse.ru/mmo/tasks-math", timeout=30000)
            page.wait_for_timeout(2000)
            
            pdf_links = page.locator('a[href*=".pdf"]').all()
            print(f"Найдено PDF: {len(pdf_links)}")
            
            urls_to_download = []
            for link in pdf_links[:30]:
                try:
                    href = link.get_attribute('href')
                    if not href:
                        continue
                    
                    full_url = href if href.startswith('http') else f"https://olymp.hse.ru{href}"
                    year = re.search(r'20\d{2}', href)
                    year = year.group() if year else "unknown"
                    
                    urls_to_download.append((full_url, year))
                except:
                    pass
            
            browser.close()
            
            print(f"\nСкачиваю {len(urls_to_download)} файлов...")
            for url, year in urls_to_download:
                filename = f"vysshaya_proba_{year}.pdf"
                print(f"[{downloaded+1}] {filename}")
                if download_pdf(url, filename):
                    downloaded += 1
                time.sleep(0.5)
                
        except Exception as e:
            print(f"[ERROR] {e}")
            browser.close()
    
    return downloaded


def main():
    """Главная функция"""
    print("="*70)
    print("СКАЧИВАНИЕ PDF ВСЕХ ОЛИМПИАД (HEADLESS)")
    print("="*70)
    
    total = 0
    
    # Курчатов
    total += parse_kurchatov()
    
    # Высшая проба
    total += parse_vysshaya_proba()
    
    print("\n" + "="*70)
    print(f"ИТОГО СКАЧАНО: {total} PDF")
    print(f"Папка: {TEMP_DIR.absolute()}")
    print("="*70)
    
    if total > 0:
        print("\nЗапустите: python scripts/extract_images.py")


if __name__ == "__main__":
    main()
