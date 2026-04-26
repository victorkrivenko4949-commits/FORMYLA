-- ROLLBACK: Otkat rekalibratsii 6 klassa
-- Sozdan: 2026-04-26T12:11:53.892535
-- Bekap: backups\formyla_before_apply_recalib_grade6_20260426_121153.db

BEGIN TRANSACTION;

UPDATE adaptive_tasks
SET class_level = original_grade
WHERE original_grade = 6 AND original_grade IS NOT NULL;

UPDATE adaptive_tasks
SET difficulty_level = original_difficulty
WHERE original_grade = 6 AND original_difficulty IS NOT NULL;

UPDATE adaptive_tasks
SET needs_reclassification = 0
WHERE original_grade = 6 AND needs_reclassification = 1;

COMMIT;
