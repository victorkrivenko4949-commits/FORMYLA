#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Миграция для создания таблицы olympiad_secrets
"""

from app import app
from models import db

def migrate():
    """Создать таблицу olympiad_secrets"""
    with app.app_context():
        # Создаём все таблицы (включая новую olympiad_secrets)
        db.create_all()
        print("✅ Таблица olympiad_secrets создана успешно!")

if __name__ == "__main__":
    migrate()
