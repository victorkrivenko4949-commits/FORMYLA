#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Массовое скачивание PDF олимпиад по известным URL-паттернам
"""

import requests
from pathlib import Path
import time

TEMP_DIR = Path("temp_pdfs")
TEMP_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

# Известные URL-паттерны для разных олимпиад
URL_PATTERNS = {
    'formula_unity': [
        # Формула Единства - пробуем разные паттерны
        "https://formulo.org/data/{year}/final/{grade}.pdf",
        "https://www.formulo.org/data/{year}/final/{grade}.pdf",
        "https://formulo.org/files/{year}/final/grade{grade}.pdf",
    ],
    'lomonosov': [
        # Ломоносов МГУ
        "https://olymp.msu.ru/media/tasks/{year}/math/{grade}.pdf",
        "https://olymp.msu.ru/media/tasks/{year}/math/grade{grade}.pdf",
    ],
    'pvg': [
        # Покори Воробьевы горы
        "https://pvg.mk.ru/upload/tasks/{year}/math/{grade}.pdf",
    ],
}

YEARS = range(2018, 2025)
GRADES = range(5, 12)


def try_download(url, output_path):
    """Попытка скачать файл"""
    try:
        response = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
        if response.status_code == 200 and len(response.content) > 1000:  # Минимум 1KB
            with open(output_path, 'wb') as f:
                f.write(response.content)
            size_kb = len(response.content) / 1024
            print(f"  [OK] {output_path.name} ({size_kb:.1f} KB)")
            return True
    except:
        pass
    return False


def main():
    """Главная функция"""
    print("="*70)
    print("МАССОВОЕ СКАЧИВАНИЕ PDF ОЛИМПИАД")
    print("="*70)
    
    total_downloaded = 0
    
    for olympiad, patterns in URL_PATTERNS.items():
        print(f"\n{olympiad.upper()}:")
        
        for year in YEARS:
            for grade in GRADES:
                # Пробуем все паттерны
                for pattern in patterns:
                    url = pattern.format(year=year, grade=grade)
                    filename = f"{olympiad}_{year}_g{grade}.pdf"
                    output_path = TEMP_DIR / filename
                    
                    if try_download(url, output_path):
                        total_downloaded += 1
                        time.sleep(0.5)
                        break  # Если скачали, не пробуем другие паттерны
    
    print("\n" + "="*70)
    print(f"ИТОГО СКАЧАНО: {total_downloaded} PDF")
    print(f"Папка: {TEMP_DIR.absolute()}")
    print("="*70)
    
    if total_downloaded > 0:
        print("\nТеперь запустите: python scripts/extract_images.py")


if __name__ == "__main__":
    main()
