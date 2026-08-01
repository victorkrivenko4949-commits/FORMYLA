# -*- coding: utf-8 -*-
"""
P4 DEBT — миграция: добавляет debt_status и debt_until в daily_task_items.

Works with SQLAlchemy — compatible with both SQLite and PostgreSQL.
No direct sqlite3, no PRAGMA, no row_factory.

Запуск: python scripts/p4_debt_migration.py
Идемпотентна: повторный запуск безопасен.
"""
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()


def main():
    from app import app as flask_app
    from models import db as _db
    from sqlalchemy import text, inspect

    with flask_app.app_context():
        engine = _db.engine
        dialect_name = engine.dialect.name
        inspector = inspect(engine)
        conn = engine.connect()

        try:
            trans = conn.begin()

            # ── 1. Добавляем колонки ─────────────────────────────────────────
            cols = {c['name'] for c in inspector.get_columns('daily_task_items')}
            added = []

            if 'debt_status' not in cols:
                if dialect_name == 'postgresql':
                    conn.execute(text(
                        "ALTER TABLE daily_task_items ADD COLUMN IF NOT EXISTS debt_status VARCHAR(16)"
                    ))
                else:
                    try:
                        conn.execute(text(
                            "ALTER TABLE daily_task_items ADD COLUMN debt_status VARCHAR(16)"
                        ))
                    except Exception:
                        pass
                trans.commit()
                trans = conn.begin()
                added.append('debt_status')
                print("  + ADDED  debt_status VARCHAR(16)")
                # Refresh columns after ALTER
                cols = {c['name'] for c in inspector.get_columns('daily_task_items')}

            if 'debt_until' not in cols:
                if dialect_name == 'postgresql':
                    conn.execute(text(
                        "ALTER TABLE daily_task_items ADD COLUMN IF NOT EXISTS debt_until DATE"
                    ))
                else:
                    try:
                        conn.execute(text(
                            "ALTER TABLE daily_task_items ADD COLUMN debt_until DATE"
                        ))
                    except Exception:
                        pass
                trans.commit()
                trans = conn.begin()
                added.append('debt_until')
                print("  + ADDED  debt_until DATE")

            if not added:
                print("  = Обе колонки уже существуют.")

            # ── 2. Переносим нерешённые задачи за 7 дней в долг ──────────────
            today = date.today()
            seven_days_ago = today - timedelta(days=7)
            today_str = today.isoformat()
            seven_days_ago_str = seven_days_ago.isoformat()

            result = conn.execute(text("""
                SELECT dti.id, dts.target_date
                FROM daily_task_items dti
                JOIN daily_task_sets dts ON dts.id = dti.daily_set_id
                WHERE dts.target_date >= :start
                  AND dts.target_date <  :end
                  AND dti.user_answer IS NULL
                  AND dti.debt_status IS NULL
            """), {'start': seven_days_ago_str, 'end': today_str})
            rows = result.fetchall()

            moved = 0
            for r in rows:
                item_id = r[0]
                target_date = r[1]
                if isinstance(target_date, date):
                    debt_until = target_date + timedelta(days=7)
                elif isinstance(target_date, str):
                    debt_until = date.fromisoformat(target_date) + timedelta(days=7)
                else:
                    debt_until = today + timedelta(days=7)
                conn.execute(text(
                    "UPDATE daily_task_items SET debt_status='active', debt_until=:du WHERE id=:id"
                ), {'du': debt_until.isoformat(), 'id': item_id})
                moved += 1

            if moved > 0:
                trans.commit()
                trans = conn.begin()
            print(f"  + Перенесено в долг: {moved} строк")

            # ── 3. Помечаем просроченный долг как сгоревший ─────────────────
            r = conn.execute(text("""
                UPDATE daily_task_items
                SET debt_status = 'burned'
                WHERE debt_status = 'active'
                  AND debt_until < :today
            """), {'today': today_str})
            burned = r.rowcount
            if burned > 0:
                trans.commit()
                trans = conn.begin()
            print(f"  + Помечено как burned: {burned} строк")

            # ── 4. Итоговая статистика ──────────────────────────────────────
            result = conn.execute(text("""
                SELECT debt_status, COUNT(*) as cnt
                FROM daily_task_items
                WHERE debt_status IS NOT NULL
                GROUP BY debt_status
            """))
            stats = result.fetchall()
            print("\n  Статистика долга:")
            for s in stats:
                print(f"    {s[0]}: {s[1]}")

            trans.commit()
        except Exception as e:
            trans.rollback()
            print(f"\nERROR: {e}")
            raise
        finally:
            conn.close()

    print("\n  ГОТОВО.")


if __name__ == '__main__':
    main()
