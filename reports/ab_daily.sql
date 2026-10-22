-- AB_V1 — ежедневный отчёт по эксперименту лимитов (PostgreSQL, только чтение).
-- Даты по МСК. Анализ — по исходному назначению (ab_cohort): покупка после
-- назначения не переносит человека в другую группу. Знаменатели абсолютные.
-- Эквивалент Python-логики CLI `flask ab-report` (routes/ab.py); SQL удобен
-- для ручного запуска в Render Shell / psql. Замените :experiment_id.
--
-- Справочно: абсолютный DAU не сравнивается с «увидевшими лимит» — это
-- смещённое сравнение (ошибка выжившего).

WITH assigned AS (
    SELECT user_id, cohort,
           (assigned_at AT TIME ZONE 'UTC' AT TIME ZONE 'Europe/Moscow')::date AS assigned_msk
    FROM ab_cohort
    WHERE experiment_id = :experiment_id
),
daily_usage AS (
    -- usage_daily.date — календарный день МСК (см. services/subscription.py)
    SELECT user_id, date AS usage_date, tasks_completed
    FROM usage_daily
    WHERE tasks_completed > 0
),
paid_orders AS (
    SELECT beneficiary_user_id, paid_at
    FROM orders
    WHERE status = 'paid' AND COALESCE(CAST(is_test AS INTEGER), 0) = 0 AND paid_at IS NOT NULL
)
SELECT
    a.cohort,
    a.assigned_msk,
    COUNT(*)                                          AS assigned_n,
    -- активные в 7-дневном окне (абсолютные знаменатели)
    COUNT(*) FILTER (WHERE EXISTS (
        SELECT 1 FROM daily_usage u
        WHERE u.user_id = a.user_id
          AND u.usage_date BETWEEN a.assigned_msk
                                AND LEAST(a.assigned_msk + 7, CURRENT_DATE))) AS active_7d,
    -- задачи на назначенного
    COALESCE(SUM(u.tasks_completed), 0)               AS tasks_total_7d,
    -- конверсия в оплату после назначения (по исходной группе)
    COUNT(*) FILTER (WHERE EXISTS (
        SELECT 1 FROM paid_orders p
        WHERE p.beneficiary_user_id = a.user_id
          AND (p.paid_at AT TIME ZONE 'UTC' AT TIME ZONE 'Europe/Moscow')::date
              >= a.assigned_msk))                     AS paid_after_assignment,
    -- D7: активен на 7-й день; только при полном окне (не выводится иначе)
    COUNT(*) FILTER (WHERE a.assigned_msk + 7 <= CURRENT_DATE
                       AND EXISTS (
        SELECT 1 FROM daily_usage u
        WHERE u.user_id = a.user_id
          AND u.usage_date = a.assigned_msk + 7))     AS d7_retained,
    -- знаменатель D7 (полное окно)
    COUNT(*) FILTER (WHERE a.assigned_msk + 7 <= CURRENT_DATE) AS d7_eligible
FROM assigned a
LEFT JOIN daily_usage u
       ON u.user_id = a.user_id
      AND u.usage_date BETWEEN a.assigned_msk AND LEAST(a.assigned_msk + 7, CURRENT_DATE)
GROUP BY a.cohort, a.assigned_msk
ORDER BY a.cohort, a.assigned_msk;

-- Баланс групп (сводка):
SELECT cohort, COUNT(*) AS n,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct
FROM ab_cohort
WHERE experiment_id = :experiment_id
GROUP BY cohort;
