-- ─────────────────────────────────────────────────────────────────────────
-- Очистка zombie daily_task_items, оставшихся от старого кода до фикса
-- (тех, что были созданы с task_text='' при status='failed' у сета).
--
-- Контекст: до коммита 2327b6a (fix/daily-tasks-generation),
-- _persist_pipeline_result(...) при сбое генерации всё равно создавал
-- 10 пустых DailyTaskItem с task_text='', что порождало пустые карточки
-- в UI и блокировало кнопку «Сгенерировать» (429).
--
-- ЭТОТ СКРИПТ ИСПОЛНЯЕТ ВЛАДЕЛЕЦ ВРУЧНУЮ НА ПРОДЕ — НЕ В CI/CD.
-- ─────────────────────────────────────────────────────────────────────────

-- ── Шаг 1. SELECT COUNT — узнать что собираемся удалять ─────────────────
-- Сначала смотрим объём (БЕЗ удаления).
-- Ожидаем небольшое число — обычно <50 записей даже на проде после месяца.
SELECT
    COUNT(*) AS zombie_items_total,
    COUNT(DISTINCT i.daily_set_id) AS affected_sets,
    MIN(s.target_date) AS oldest_failed_date,
    MAX(s.target_date) AS newest_failed_date
FROM daily_task_items i
JOIN daily_task_sets   s ON s.id = i.daily_set_id
WHERE s.status = 'failed'
  AND (i.task_text IS NULL OR i.task_text = '');


-- ── Шаг 2. SELECT детально — посмотреть, какие конкретно сеты затронуты ─
-- Если хотите убедиться, что не удаляете ничего нужного:
SELECT
    s.id AS set_id,
    s.user_id,
    s.target_date,
    s.status,
    LEFT(COALESCE(s.error_message, ''), 80) AS error_preview,
    COUNT(i.id) AS zombie_count
FROM daily_task_sets s
JOIN daily_task_items i ON i.daily_set_id = s.id
WHERE s.status = 'failed'
  AND (i.task_text IS NULL OR i.task_text = '')
GROUP BY s.id, s.user_id, s.target_date, s.status, s.error_message
ORDER BY s.target_date DESC
LIMIT 100;


-- ── Шаг 3. DELETE в транзакции ──────────────────────────────────────────
-- Узкое условие: только items, у которых:
--   * родительский set имеет status='failed' (точно сбой генерации, не активный)
--   * task_text пуст или NULL (никакого реального текста задачи)
--
-- BEGIN; ... ROLLBACK / COMMIT — в psql / dbeaver — обязательно.
BEGIN;

  DELETE FROM daily_task_items i
  USING daily_task_sets s
  WHERE i.daily_set_id = s.id
    AND s.status = 'failed'
    AND (i.task_text IS NULL OR i.task_text = '');

  -- Проверяем сколько удалили
  -- (в psql: после DELETE будет "DELETE N" — сравните с zombie_items_total из шага 1).

-- Если число совпало — коммитим:
-- COMMIT;

-- Если нет — откатываемся и разбираемся:
ROLLBACK;


-- ── Шаг 4. (опционально) Удалить failed-сеты целиком ───────────────────
-- ВНИМАНИЕ: даёт пользователю заново нажать «Сгенерировать» сегодня без 429.
-- Но логи в pipeline_log / job.error_message при этом потеряются.
-- Рекомендуется НЕ удалять — после фикса logic regenerate уже не блокируется
-- (см. daily_tasks/routes.py:140 в коммите 2327b6a).
--
-- BEGIN;
--   DELETE FROM daily_generation_jobs WHERE daily_set_id IN (
--       SELECT id FROM daily_task_sets WHERE status='failed'
--   );
--   DELETE FROM daily_task_sets WHERE status='failed';
-- ROLLBACK;  -- ← поменять на COMMIT если ОК


-- ── Шаг 5. Проверка после COMMIT ───────────────────────────────────────
SELECT
    COUNT(*) AS items_with_empty_text_remaining
FROM daily_task_items
WHERE task_text IS NULL OR task_text = '';
-- Ожидаем 0.
