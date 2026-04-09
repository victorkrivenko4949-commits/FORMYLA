#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Открывает браузер с Playwright и ждет, пока пользователь не закроет его
"""

from playwright.sync_api import sync_playwright
from pathlib import Path

TEMP_DIR = Path("temp_pdfs")
TEMP_DIR.mkdir(parents=True, exist_ok=True)

print("="*70)
print("ОТКРЫВАЮ БРАУЗЕР - ЗАКРОЙТЕ ЕГО ВРУЧНУЮ КОГДА ЗАКОНЧИТЕ")
print("="*70)

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=False,
        slow_mo=100,
    )
    
    context = browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        accept_downloads=True
    )
    
    page = context.new_page()
    
    # Открываем папку с файлами
    print(f"\nПапка для скачивания: {TEMP_DIR.absolute()}")
    print("\nОткрываю проводник с папкой temp_pdfs...")
    
    # Открываем сайт Формулы Единства
    print("\nОткрываю https://www.formulo.org/ru/")
    page.goto("https://www.formulo.org/ru/")
    
    print("\n" + "="*70)
    print("БРАУЗЕР ОТКРЫТ")
    print("="*70)
    print("\nИнструкции:")
    print("1. Найдите на сайте архив заданий")
    print("2. Скачайте нужные PDF-файлы")
    print("3. Они автоматически сохранятся в temp_pdfs/")
    print("4. Закройте браузер когда закончите")
    print("\nЖду закрытия браузера...")
    
    # Ждем, пока пользователь не закроет браузер
    try:
        while True:
            page.wait_for_timeout(1000)
    except:
        pass
    
    print("\nБраузер закрыт!")
    
    # Проверяем скачанные файлы
    pdf_files = list(TEMP_DIR.glob("*.pdf"))
    print(f"\nСкачано PDF-файлов: {len(pdf_files)}")
    
    if pdf_files:
        print("\nСкачанные файлы:")
        for pdf in pdf_files:
            print(f"  - {pdf.name}")
        print("\nТеперь запустите: python scripts/extract_images.py")
    else:
        print("\n[!] PDF не скачаны")

print("\n" + "="*70)
print("ГОТОВО")
print("="*70)
