# -*- coding: utf-8 -*-
"""
Миграция: Создание таблицы olympiad_prep
для раздела «Подготовка к олимпиадам».
"""
from models import db, OlympiadPrep
from app import app


def migrate():
    """Выполнить миграцию — создать таблицу olympiad_prep."""
    with app.app_context():
        print(" Миграция: создание таблицы olympiad_prep...")
        try:
            db.create_all()
            print("[OK] Таблица olympiad_prep создана (или уже существует).")
        except Exception as e:
            print(f"[ERROR] Ошибка миграции: {e}")
            db.session.rollback()
            raise


if __name__ == '__main__':
    migrate()
