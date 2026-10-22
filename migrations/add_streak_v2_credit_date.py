# -*- coding: utf-8 -*-
"""
Миграция STREAK_V2: колонка streak_records.last_credit_date

Новое правило серии: день засчитывается (+1), если пользователь
  а) провёл на сайте больше 20 минут, ИЛИ
  б) правильно решил хотя бы 1 задачу дня.
Колонка last_credit_date гарантирует максимум +1 за день.

Бэкфилл: last_credit_date = last_solved_date — день, уже засчитанный
старой логикой (полный сет на 100%), не будет засчитан повторно после
деплоя. Консервативно: день, покрытый выходным, тоже помечается
как зачтённый.

Идемпотентна: повторный запуск ничего не делает (и на Postgres,
и на SQLite — «duplicate column» считается успехом).
Внимание: ALTER выполняется в отдельном соединении вне сессий.
"""
from models import db
from app import app


def migrate():
    """Выполнить миграцию"""
    with app.app_context():
        print(" Начинаем миграцию STREAK_V2 (last_credit_date)...")

        try:
            with db.engine.connect() as conn:
                exists = conn.execute(db.text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name = 'streak_records' "
                    "AND column_name = 'last_credit_date'"
                )).first()
                if exists is None:
                    conn.execute(db.text(
                        "ALTER TABLE streak_records "
                        "ADD COLUMN last_credit_date DATE"
                    ))
                    conn.execute(db.text(
                        "UPDATE streak_records "
                        "SET last_credit_date = last_solved_date "
                        "WHERE last_solved_date IS NOT NULL "
                        "AND last_credit_date IS NULL"
                    ))
                    conn.commit()
                    print("[OK] Колонка добавлена + бэкфилл last_solved_date")
                else:
                    print("[OK] Колонка уже существует — пропуск")
            print("[OK] Миграция завершена успешно!")
            return

        except Exception:
            pass  # SQLite: нет information_schema — пробуем простой ALTER

        try:
            with db.engine.connect() as conn:
                conn.execute(db.text(
                    "ALTER TABLE streak_records ADD COLUMN last_credit_date DATE"
                ))
                conn.execute(db.text(
                    "UPDATE streak_records "
                    "SET last_credit_date = last_solved_date "
                    "WHERE last_solved_date IS NOT NULL "
                    "AND last_credit_date IS NULL"
                ))
                conn.commit()
            print("[OK] Колонка добавлена (SQLite) + бэкфилл")
            print("[OK] Миграция завершена успешно!")
        except Exception as e:
            if 'duplicate column' in str(e).lower():
                print("[OK] Колонка уже существует — миграция не нужна")
            else:
                print(f"[ERROR] Ошибка миграции: {e}")
                raise


if __name__ == '__main__':
    migrate()
