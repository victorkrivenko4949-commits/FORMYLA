-- ROLLBACK: Рекалибровка 5 класса
-- Применять ТОЛЬКО если нужно откатить изменения
-- Backup: backups/formyla_before_apply_recalib_grade5_20260426_210428.db

-- 1. Вернуть задачи из 6/7/8 класса обратно в 5 класс
UPDATE adaptive_tasks
SET class_level = 5
WHERE original_grade = 5
  AND class_level IN (6, 7, 8);

-- 2. Восстановить оригинальную сложность
UPDATE adaptive_tasks
SET difficulty_level = original_difficulty
WHERE original_grade = 5
  AND original_difficulty IS NOT NULL;

-- 3. Снять флаг needs_reclassification (только те, что были помечены этим скриптом)
-- (В данном случае 0 задач было помечено, но на всякий случай)
-- UPDATE adaptive_tasks SET needs_reclassification = 0 WHERE original_grade = 5;

-- Проверка после отката:
-- SELECT COUNT(*) FROM adaptive_tasks WHERE class_level = 5;
-- Ожидается: ~949
