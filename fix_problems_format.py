#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Исправление формата problems.py"""

import sys
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# Читаем файл как текст
with open('problems.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Проверяем первую строку
first_line = content.split('\n')[0]
print(f"Первая строка: {repr(first_line)}")

# Если это испорченный формат с \\n
if '\\n' in first_line:
    print("Обнаружен испорченный формат с \\\\n")
    # Убираем \\n и исправляем
    content = content.replace('\\n', '\n')
    
    with open('problems.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("✅ Исправлено!")
else:
    print("Формат выглядит нормально")

# Проверяем импорт
try:
    from problems import PROBLEMS_DB
    print(f"✅ Импорт успешен: {len(PROBLEMS_DB)} задач")
except Exception as e:
    print(f"❌ Ошибка импорта: {e}")
