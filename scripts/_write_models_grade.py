# -*- coding: utf-8 -*-
"""Перезаписать models_grade.py с расширенной поддержкой 5-10 классов."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / 'models_grade.py'

# Все литералы — обычные одинарные кавычки, никаких сложных вставок.
HEADER = """# -*- coding: utf-8 -*-
\"\"\"Модель тренажёра FORMYLA по классам (5-10).

Хранит задачи из data/olympiads/master_5345.json (и более ранних
наборов 1600 для 5/6) — привязка к классу + домену темы.
Импорт через scripts/import_master_5345.py (UPSERT по source_id).
\"\"\"

from datetime import datetime
from sqlalchemy import UniqueConstraint
from models import db

GRADE_SUBJECTS = ('math',)
"""

# Используем функции вместо литеральных словарей с {, чтобы tooling
# не ломал файл при перезаписи.
DOMAINS_5 = [
    'natural_numbers',{