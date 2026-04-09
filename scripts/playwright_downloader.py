#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Мощный Playwright-парсер для скачивания PDF олимпиад
Работает в видимом режиме, обходит защиты, имитирует человека
"""

from playwright.sync_api import sync_playwright
from pathlib import Path
import time
import re

TEMP_DIR = Path("temp_pdfs")
TEMP_DIR.mkdir(parents=True, exist_ok=True)


def download_formula_unity(page):
    """Скачивание PDF Формулы Единства"""
    print("\n" + "="*70)
    print("ФОРМУЛА ЕДИНСТВА")
    print("="*70)
    
    downloaded = 0
    
    try:
        # Заходим на главную
        print("Открываю https://www.formulo.org/ru/")
        page.goto("https://www.formulo.org/ru/", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(2000)
        
        # Ищем ссылки на олимпиаду
        print("Ищу ссылки на олимпиаду...")
        links = page.locator('a').all()
        
        for link in links:
            try:
                text = link.inner_text().lower()
                href = link.get_attribute('href') or ''
                
                if any(word in text for word in ['олимпиад', 'olymp', 'задач', 'архив', 'archive']):
                    print(f"  Найдена ссылка: {text[:50]}... -> {href[:50]}...")
                    
                    if href and not href.startswith('#'):
                        full_url = href if href.startswith('http') else f"https://www.formulo.org{href}"
                        print(f"  Переходжу на: {full_url}")
                        
                        page.goto(full_url, wait_until="networkidle", timeout=30000)
                        page.wait_for_timeout(2000)
                        
                        # Ищем PDF на этой странице
                        pdf_links = page.locator('a[href*=".pdf"]').all()
                        print(f"  Найдено PDF: {len(pdf_links)}")
                        
                        for pdf_link in pdf_links[:5]:  # Ограничиваем для теста
                            try:
                                pdf_href = pdf_link.get_attribute('href')
                                pdf_text = pdf_link.inner_text()
                                
                                # Определяем год
                                year_match = re.search(r'20\d{2}', pdf_href + pdf_text)
                                year = year_match.group() if year_match else "unknown"
                                
                                print(f"    Скачиваю: {pdf_text[:30]}... ({year})")
                                
                                # Скачиваем
                                with page.expect_download(timeout=60000) as download_info:
                                    pdf_link.click()
                                
                                download = download_info.value
                                filename = f"fu_{year}_{download.suggested_filename}"
                                save_path = TEMP_DIR / filename
                                download.save_as(save_path)
                                
                                print(f"      [OK] {filename}")
                                downloaded += 1
                                page.wait_for_timeout(1000)
                                
                            except Exception as e:
                                print(f"      [ERROR] {e}")
                        
                        # Возвращаемся назад
                        page.go_back(wait_until="networkidle")
                        page.wait_for_timeout(1000)
                        
            except Exception as e:
                pass
        
    except Exception as e:
        print(f"[ERROR] {e}")
    
    return downloaded


def download_kurchatov(page):
    """Скачивание PDF Курчатова"""
    print("\n" + "="*70)
    print("КУРЧАТОВ")
    print("="*70)
    
    downloaded = 0
    
    try:
        # Пробуем разные URL
        urls = [
            "https://kurchatov.mephi.ru/",
            "https://olymp.mephi.ru/",
        ]
        
        for url in urls:
            try:
                print(f"Пробую: {url}")
                page.goto(url, wait_until="networkidle", timeout=30000)
                page.wait_for_timeout(2000)
                
                # Ищем архив/задания
                archive_links = page.locator('a').all()
                
                for link in archive_links:
                    try:
                        text = link.inner_text().lower()
                        if any(word in text for word in ['архив', 'задач', 'задани']):
                            print(f"  Найдена ссылка: {text[:40]}...")
                            link.click()
                            page.wait_for_timeout(2000)
                            
                            # Ищем PDF
                            pdf_links = page.locator('a[href*=".pdf"]').all()
                            print(f"  PDF найдено: {len(pdf_links)}")
                            
                            for pdf_link in pdf_links[:10]:
                                try:
                                    pdf_href = pdf_link.get_attribute('href')
                                    pdf_text = pdf_link.inner_text()
                                    
                                    year_match = re.search(r'20\d{2}', pdf_href + pdf_text)
                                    year = year_match.group() if year_match else "unknown"
                                    
                                    print(f"    Скачиваю: {pdf_text[:30]}...")
                                    
                                    with page.expect_download(timeout=60000) as download_info:
                                        pdf_link.click()
                                    
                                    download = download_info.value
                                    filename = f"kurchatov_{year}_{download.suggested_filename}"
                                    save_path = TEMP_DIR / filename
                                    download.save_as(save_path)
                                    
                                    print(f"      [OK] {filename}")
                                    downloaded += 1
                                    page.wait_for_timeout(1000)
                                    
                                except Exception as e:
                                    print(f"      [ERROR] {e}")
                            
                            break
                    except:
                        pass
                
                if downloaded > 0:
                    break
                    
            except Exception as e:
                print(f"  [ERROR] {url}: {e}")
        
    except Exception as e:
        print(f"[ERROR] {e}")
    
    return downloaded


def main():
    """Главная функция"""
    print("="*70)
    print("PLAYWRIGHT DOWNLOADER - АВТОМАТИЧЕСКОЕ СКАЧИВАНИЕ PDF")
    print("="*70)
    
    total = 0
    
    with sync_playwright() as p:
        # Запускаем браузер в ВИДИМОМ режиме
        print("\nЗапускаю браузер Chromium...")
        browser = p.chromium.launch(
            headless=False,  # ВИДИМЫЙ режим
            slow_mo=500,  # Замедление для наблюдения
        )
        
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080}
        )
        
        page = context.new_page()
        
        # Формула Единства
        total += download_formula_unity(page)
        
        # Курчатов
        total += download_kurchatov(page)
        
        print("\nЗакрываю браузер...")
        browser.close()
    
    print("\n" + "="*70)
    print(f"ИТОГО СКАЧАНО PDF: {total}")
    print(f"Папка: {TEMP_DIR.absolute()}")
    print("="*70)
    
    if total > 0:
        print("\nТеперь запустите: python scripts/extract_images.py")
    else:
        print("\n[!] PDF не скачаны. Проверьте доступность сайтов.")


if __name__ == "__main__":
    main()
