# -*- coding: utf-8 -*-
# Анализ LaTeX-проблем в адаптивных задачах FORMYLA.
# Проверяет поле task_text таблицы adaptive_tasks по 7 типам проблем.
# НЕ МЕНЯЕТ ДАННЫЕ - только читает и создает отчет.
#
# Использование:
#     python scripts/analyze_latex_issues.py

import sqlite3
import re
import json
import os
from datetime import datetime
from collections import defaultdict

DB_PATH = 'instance/formyla.db'
REPORT_DIR = 'data/audit'
SAMPLES_LIMIT = 5


# ============================================================
# Вспомогательные функции
# ============================================================

def find_math_regions(text):
    """Находит все регионы math-режима в тексте.
    Возвращает список (start, end) для $...$ и $$...$$."""
    regions = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] == '\\' and i + 1 < n and text[i + 1] == '$':
            # Экранированный доллар - пропускаем
            i += 2
            continue
        if i < n - 1 and text[i] == '$' and text[i + 1] == '$':
            # Display math $$...$$
            start = i
            i += 2
            # Ищем закрывающий $$
            while i < n - 1:
                if text[i] == '$' and text[i + 1] == '$':
                    regions.append((start, i + 2))
                    i += 2
                    break
                i += 1
            else:
                # Не нашли закрывающий $$
                i = start + 2
            continue
        if text[i] == '$':
            # Inline math $...$
            start = i
            i += 1
            while i < n:
                if text[i] == '\\' and i + 1 < n and text[i + 1] == '$':
                    i += 2
                    continue
                if text[i] == '$':
                    regions.append((start, i + 1))
                    i += 1
                    break
                i += 1
            else:
                # Не нашли закрывающий $
                i = start + 1
            continue
        i += 1
    return regions


def is_in_math(pos, regions):
    """Проверяет, находится ли позиция внутри math-региона."""
    for start, end in regions:
        if start <= pos < end:
            return True
    return False


# ============================================================
# Проверки по 7 типам проблем
# ============================================================

def check_literal_backslash_n(text):
    # A) Литеральное \n в тексте (двойное экранирование).
    # В БД хранится как два символа: \{
