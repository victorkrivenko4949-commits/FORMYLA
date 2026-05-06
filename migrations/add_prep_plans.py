# -*- coding: utf-8 -*-
"""
Миграция: Создание таблиц prep_plans и prep_days
для модуля «Персональная подготовка к олимпиадам».
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import db, PrepPlan, PrepDay
from app import app


def migrate():
    """Выполнить миграцию — создать таблицы prep_plans и prep_days."""
    with app.app_context():
        print("🔄 Миграция: создание таблиц prep_plans, prep_days...")
        try:
            db.create_all()
            print("✅ Таблицы prep_plans и prep_days созданы (или уже существуют).")
        except Exception as e:
            print(f"❌ Ошибка миграции: {e}")
            db.session.rollback()
            raise


if __name__ == '__main__':
    migrate()
