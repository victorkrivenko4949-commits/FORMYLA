-- ─────────────────────────────────────────────────────────────────────────
-- HOT-FIX (без деплоя): размораживает «зомби»-job, из-за которого
-- «Задачи дня» вечно показывают «🪐 Генерируем… прошло X:XX».
--
-- ПРИЧИНА (см. diagnostic в diff коммита b/main 2026-06-12):
--   DailyGenerationJob со state='running' и DailyTaskSet со status='generating'
--   остались от убитого daemon=True потока (рестарт gunicorn, OOM, deploy).
--   Guard в enqueue_daily_generation() видит существующий 'generating'-сет
--   → отказывает в новой генерации → POST /regenerate даже не вызывается.
--
-- ВЫПОЛНЯТЬ ВРУЧНУЮ на проде:
--   Render Dashboard → formyla-db → Connect → External Database URL → psql
--   ИЛИ Render Dashboard → formyla-com → Shell → flask shell ниже.
-- ─────────────────────────────────────────────────────────────────────────

-- ── Шаг 1. SELECT — какие jobs в state='running' дольше 10 минут? ──────
SELECT
    id,
    user_id,
    target_date,
    state,
    current_step,
    progress_pct,
    started_at,
    NOW() - started_at AS age,
    daily_set_id,
    LEFT(COALESCE(error_message, ''), 80) AS error_preview
FROM daily_generation_jobs
WHERE state = 'running'
  AND started_at < NOW() - INTERVAL '10 minutes'
ORDER BY started_at DESC
LIMIT 50;
-- ОЖИДАЕМ: 1-N строк, current_step='gpt_audit' / 'opus_generate' / etc.
-- Если результат пустой — зомби нет, проблема в другом, не запускайте Шаг 3.


-- ── Шаг 2. SELECT — связанные DailyTaskSets в 'generating' ─────────────
SELECT
    s.id AS set_id,
    s.user_id,
    s.target_date,
    s.status,
    s.generated_at,
    j.id AS job_id,
    j.state AS job_state,
    j.started_at,
    j.current_step
FROM daily_task_sets s
LEFT JOIN daily_generation_jobs j ON j.daily_set_id = s.id
WHERE s.status = 'generating'
  AND (j.started_at IS NULL OR j.started_at < NOW() - INTERVAL '10 minutes')
ORDER BY s.generated_at DESC NULLS LAST
LIMIT 50;


-- ── Шаг 3. UPDATE — помечаем зомби как failed (в транзакции!) ──────────
-- Это разморозит UI: пользователь увидит failed-баннер + Retry-кнопку
-- (UI уже умеет это показывать, см. static/js/daily_tasks.js, case 'failed').
BEGIN;

  -- 3a. Помечаем jobs как failed
  UPDATE daily_generation_jobs
  SET
    state         = 'failed',
    error_message = LEFT(
        'Авто-помечен failed (zombie cleanup ' || NOW()::TEXT ||
        '): фоновый поток умер до завершения (вероятно рестарт worker).',
        500
    ),
    finished_at   = NOW()
  WHERE state = 'running'
    AND started_at < NOW() - INTERVAL '10 minutes';
  -- ↑ Запомните, сколько строк затронуто (psql: "UPDATE N").

  -- 3b. Размораживаем связанные DailyTaskSets
  UPDATE daily_task_sets s
  SET
    status         = 'failed',
    reason_summary = '❌ Генерация прервана — попробуйте ещё раз',
    generated_at   = COALESCE(s.generated_at, NOW())
  WHERE s.status = 'generating'
    AND s.id IN (
      SELECT j.daily_set_id
      FROM daily_generation_jobs j
      WHERE j.daily_set_id IS NOT NULL
        AND j.state = 'failed'
        AND j.error_message LIKE 'Авто-помечен failed (zombie cleanup%'
    );

  -- 3c. (Опционально) Размораживаем зависшие TaskPool'ы с истёкшим expires_at.
  UPDATE task_pool
  SET
    status     = 'failed',
    expires_at = NOW() - INTERVAL '1 second'
  WHERE status = 'generating'
    AND expires_at IS NOT NULL
    AND expires_at < NOW();

-- Если числа правдоподобны — COMMIT, иначе ROLLBACK:
-- COMMIT;
ROLLBACK;


-- ── Шаг 4. После COMMIT — verify ───────────────────────────────────────
SELECT
    COUNT(*) FILTER (WHERE state='running'   AND started_at < NOW() - INTERVAL '10 minutes') AS stale_running_jobs,
    COUNT(*) FILTER (WHERE state='running')                                                  AS all_running_jobs
FROM daily_generation_jobs;
-- ОЖИДАЕМ: stale_running_jobs = 0.

SELECT COUNT(*) AS stale_generating_sets
FROM daily_task_sets
WHERE status = 'generating'
  AND (
    generated_at IS NULL
    OR generated_at < NOW() - INTERVAL '10 minutes'
  );
-- ОЖИДАЕМ: 0.


-- ── Шаг 5. (По желанию) Полная инвалидация на сегодня для конкретного user ─
-- Если пользователь хочет «начать сегодня с чистого листа» вообще,
-- замените 123 на свой user_id, '2026-06-12' на нужную дату МСК.
-- BEGIN;
--   DELETE FROM daily_generation_jobs WHERE user_id=123 AND target_date='2026-06-12';
--   DELETE FROM daily_task_items
--     WHERE daily_set_id IN (SELECT id FROM daily_task_sets WHERE user_id=123 AND target_date='2026-06-12');
--   DELETE FROM daily_task_sets WHERE user_id=123 AND target_date='2026-06-12';
-- COMMIT;
