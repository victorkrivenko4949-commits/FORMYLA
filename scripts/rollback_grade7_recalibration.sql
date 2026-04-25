-- ROLLBACK: Otkat rekalibratsii 7 klassa
-- Sozdan: 2026-04-26T02:44:02.377715
-- Bekap: backups\formyla_before_apply_recalib_20260426_024402.db

BEGIN TRANSACTION;

-- Vosstanovit' class_level iz original_grade
UPDATE adaptive_tasks
SET class_level = original_grade
WHERE original_grade = 7
  AND original_grade IS NOT NULL;

-- Vosstanovit' difficulty_level iz original_difficulty
UPDATE adaptive_tasks
SET difficulty_level = original_difficulty
WHERE original_grade = 7
  AND original_difficulty IS NOT NULL;

-- Snyat' flag needs_reclassification
UPDATE adaptive_tasks
SET needs_reclassification = 0
WHERE original_grade = 7
  AND needs_reclassification = 1;

-- Proverka
SELECT class_level, COUNT(*) FROM adaptive_tasks
WHERE original_grade = 7
GROUP BY class_level;

COMMIT;

-- Posle otkata: SELECT COUNT(*) FROM adaptive_tasks WHERE class_level=7;
-- Dolzhno byt' ~993 (vse original grade=7 zadachi)
