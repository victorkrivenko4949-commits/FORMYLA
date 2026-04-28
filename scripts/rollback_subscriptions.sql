-- ============================================================
-- ROLLBACK: Миграция 002 — Система подписок Free/Premium
-- ============================================================
-- ВНИМАНИЕ: Запускать только если нужно полностью откатить миграцию!
-- Перед запуском убедитесь что есть бэкап в папке backups/
--
-- Запуск (Windows):
--   sqlite3 formyla.db < scripts/rollback_subscriptions.sql
--
-- Запуск (Python):
--   python migrations/002_add_subscriptions.py --rollback
-- ============================================================

-- 1. Удаляем таблицу дневного использования
DROP TABLE IF EXISTS usage_daily;

-- 2. Удаляем таблицу подписок
DROP TABLE IF EXISTS subscriptions;

-- 3. Обнуляем добавленные колонки в users
--    (SQLite < 3.35 не поддерживает DROP COLUMN)
--    Колонки остаются в схеме, но значения сбрасываются.
UPDATE users SET current_plan = NULL;
UPDATE users SET plan_expires_at = NULL;

-- ============================================================
-- Если нужно полностью удалить колонки (SQLite >= 3.35):
--   ALTER TABLE users DROP COLUMN current_plan;
--   ALTER TABLE users DROP COLUMN plan_expires_at;
-- ============================================================
