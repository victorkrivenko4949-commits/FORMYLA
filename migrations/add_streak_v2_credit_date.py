# -*- coding: utf-8 -*-
"""
Миграция STREAK_V2: колонка streak_records.last_credit_date

Новое правило серии: день засчитывается (+1), если пользователь
  а) провёл на сайте больше 20 минут, ИЛИ
  б) правильно решил хотя бы 1 задачу дня.
Колонка last_credit_date гарантирует максимум +1 за день.

Идемпотентна: повторный запуск ничего не ломает.
"""
from models import db
from app import app


def migrate():
    """Выполнить миграцию"""
    with app.app_context():
        print(" Начинаем миграцию STREAK_V2 (last_credit_date)...")

        try:
            # ALTER TABLE ... ADD COLUMN IF NOT EXISTS (Postgres 9.6+)
            db.session.execute(db.text(
                "ALTER TABLE streak_records "
                "ADD COLUMN IF NOT EXISTS last_credit_date DATE"
            ))
            db.session.commit()
            print("[OK] Колонка streak_records.last_credit_date добавлена")
            print("[OK] Миграция завершена успешно!")

        except Exception as e:
            db.session.rollback()
            # SQLite не знает IF NOT EXISTS для ADD COLUMN — пробуем без него
            try:
                db.session.execute(db.text(
                    "ALTER TABLE streak_records ADD COLUMN last_credit_date DATE"
                ))
                db.session.commit()
                print("[OK] Колонка streak_records.last_credit_date добавлена")
                print("[OK] Миграция завершена успешно!")
            except Exception as e2:
                print(f"[ERROR] Ошибка миграции: {e2}")
                db.session.rollback()
                raise


if __name__ == '__main__':
    migrate()
