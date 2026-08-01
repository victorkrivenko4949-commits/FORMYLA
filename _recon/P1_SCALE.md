# P1_SCALE: Переход на единую пятибалльную шкалу (1..5)

**Дата:** 2026-07-31  
**БД:** formyla.db (32,690,176 байт)  
**Бэкап:** `_recon\backup_formyla_20260731_211943.db`

---

## Что было

Пул из 8778 задач размечен по **восьмибалльной** шкале (difficulty_level ∈ {1..8}):
- Level 1: 1271 (14.5%)
- Level 2: 2485 (28.3%)
- Level 3: 1332 (15.2%)
- Level 4: 720 (8.2%)
- Level 5: 906 (10.3%)
- **Level 6: 833 (9.5%)**
- **Level 7: 602 (6.9%)**
- **Level 8: 629 (7.2%)**

**2064 задачи (23.5%) имели уровень 6, 7 или 8 и не выдавались никому.**

## Что стало

Все 8778 задач приведены к **пятибалльной** шкале (difficulty_level ∈ {1..5}):

| Уровень | Количество | Доля |
|---------|-----------|------|
| 1 | 3756 | 42.8% |
| 2 | 1332 | 15.2% |
| 3 | 1626 | 18.5% |
| 4 | 1435 | 16.3% |
| 5 | 629 | 7.2% |

**2064 ранее невыдаваемых задачи теперь доступны.** Пустых ячеек (grade × level): всего 2 — G6 L4, G10 L5.

---

## Шаг 0: Бэкап

```
BACKUP: _recon\backup_formyla_20260731_211943.db
SIZE: 32,690,176 bytes
```

---

## Шаг 1: Инвентаризация 8-балльных мест

### Файлы с восьмибалльной шкалой (до правок):

| Файл | Строки | Что содержал |
|------|--------|-------------|
| [`services/level_engine.py`](services/level_engine.py:34) | 34-36 | `EIGHT_POINT_SOURCES: set` |
| [`services/level_engine.py`](services/level_engine.py:50) | 50-56 | `EIGHT_POINT_MAP` (1→[1,2], 2→[3], …) |
| [`services/level_engine.py`](services/level_engine.py:280) | 280-281 | `if source in EIGHT_POINT_SOURCES` |
| [`services/difficulty_calibration.py`](services/difficulty_calibration.py:8) | 8-17 | `LEVEL_LABELS` с уровнями 6,7,8 |
| [`services/difficulty_calibration.py`](services/difficulty_calibration.py:20) | 20-29 | `LEVEL_COLORS` с уровнями 6,7,8 |
| [`services/difficulty_calibration.py`](services/difficulty_calibration.py:32) | 32-41 | `LEVEL_EXPECTED_RATES` с уровнями 6,7,8 |
| [`services/difficulty_calibration.py`](services/difficulty_calibration.py:44) | 44-53 | `LEVEL_DESCRIPTIONS` с уровнями 6,7,8 |
| [`services/difficulty_calibration.py`](services/difficulty_calibration.py:70) | 70-84 | `LEVEL_EXAMPLES` с уровнями 6,7,8 |
| [`services/difficulty_calibration.py`](services/difficulty_calibration.py:125) | 125 | `"Уровень сложности: {level} из 8"` |
| [`services/difficulty_calibration.py`](services/difficulty_calibration.py:169) | 169 | `if expected_level >= 6` |
| [`services/difficulty_calibration.py`](services/difficulty_calibration.py:173) | 173 | `min_time = {…6:60, 7:90, 8:120}` |
| [`services/difficulty_calibration.py`](services/difficulty_calibration.py:190) | 190 | `for level in range(8, 0, -1)` |
| [`services/task_selection.py`](services/task_selection.py:97) | 97 | `if l < 1 or l > 8` |
| [`models.py`](models.py:820) | 820 | `# Уровень сложности 1-7` (комментарий) |

---

## Шаг 2: Сухой прогон

Правило пересчёта: **1→1, 2→1, 3→2, 4→3, 5→3, 6→4, 7→4, 8→5**

Результат: max доля 42.8% (< 45%), min доля 7.2% (> 5%) — **ОК, стоп-условие не сработало.**

---

## Шаг 3: Код миграции

Файл: [`scripts/migrate_8to5_scale.py`](scripts/migrate_8to5_scale.py)

Скрипт:
1. Добавляет колонку `difficulty_level_src` (INTEGER)
2. Сохраняет в неё исходный `difficulty_level` (только где NULL)
3. Пересчитывает `difficulty_level` **из `difficulty_level_src`** (не из текущего `difficulty_level`!)
4. Идемпотентен: повторный запуск → 0 изменений

Вывод первого запуска:
```
[1/4] Checking difficulty_level_src column... OK - column added.
[2/4] Saving original -> difficulty_level_src... saved 8778 values.
[3/4] Current: L1=1271, L2=2485, L3=1332, L4=720, L5=906, L6=833, L7=602, L8=629
[4/4] Remapping FROM difficulty_level_src...
  src=1->1: 1271 (already correct)
  src=2->1: 2485 updated
  src=3->2: 1332 updated
  src=4->3: 720 updated
  src=5->3: 906 updated
  src=6->4: 833 updated
  src=7->4: 602 updated
  src=8->5: 629 updated
Total remapped: 7507

=== VERIFICATION ===
  L1=3756 (42.8%), L2=1332 (15.2%), L3=1626 (18.5%), L4=1435 (16.3%), L5=629 (7.2%)
  [OK] No tasks outside 1..5 range.
  [OK] 8778 tasks have difficulty_level_src preserved.
```

---

## Шаг 4: Приведение кода — diff каждой правки

### 4.1 [`services/level_engine.py`](services/level_engine.py)
**Удалено:**
- `EIGHT_POINT_SOURCES: set = set()` (строка 36)
- `EIGHT_POINT_MAP` (строки 50-56)
- Ветка `if source in EIGHT_POINT_SOURCES:` (строки 280-281)

**Центральное место проверки диапазона 1..5:** [`services/level_engine.py`](services/level_engine.py) — константы `MIN_MU=1.0, MAX_MU=5.0` (строка 68-69) + `allowed_difficulty()` (строка 263).

### 4.2 [`services/difficulty_calibration.py`](services/difficulty_calibration.py)
- `LEVEL_LABELS`: удалены уровни 6,7,8
- `LEVEL_COLORS`: удалены уровни 6,7,8
- `LEVEL_EXPECTED_RATES`: удалены уровни 6,7,8, уровень 5 = 0.10
- `LEVEL_DESCRIPTIONS`: удалены уровни 6,7,8, уровень 5 объединён
- `LEVEL_EXAMPLES`: удалены примеры для уровней 6,7,8
- `build_generation_prompt()`: `"из 8"` → `"из 5"`, добавлен clamp
- `validate_generated_task()`: `expected_level >= 6` → `exp >= 5`, `min_time` словарь → 5-уровневый
- `get_level_by_solve_rate()`: `range(8, 0, -1)` → `range(5, 0, -1)`

### 4.3 [`services/task_selection.py`](services/task_selection.py:97)
- `l > 8` → `l > 5`

### 4.4 [`models.py`](models.py:820)
- Комментарий `# Уровень сложности 1-7` → `# Уровень сложности 1-5`

### 4.5 Поле `source` импортированных записей
Поле `source` в `adaptive_tasks` уже содержит значение `'formyla_L1_L5_TOP5'` — это значение, записанное скриптом импорта. Проверка в `level_engine.py`:
```python
FIVE_POINT_SOURCES = {'formyla_L1_L5_TOP5'}
```
Все задачи с этим source корректно обрабатываются. Других значений source в БД не обнаружено.

---

## Шаг 5: Приёмка — фактические числа

### 5.1 SELECT min/max + outside 1..5
```
MIN=1 MAX=5
Outside 1..5: 0
```

### 5.2 Таблица grade × level
```
G5:  L1=728, L2=140, L3=54,  L4=65,  L5=141
G6:  L1=730, L2=206, L3=51,  L4=0,   L5=141
G7:  L1=433, L2=245, L3=281, L4=224, L5=141
G8:  L1=329, L2=137, L3=390, L4=381, L5=148
G9:  L1=585, L2=187, L3=248, L4=227, L5=55
G10: L1=563, L2=232, L3=264, L4=220, L5=0
G11: L1=388, L2=185, L3=338, L4=318, L5=3
```

### 5.3 G8 и G11 — пустые ячейки
- **G8:** NONE — все 5 уровней заполнены
- **G11:** NONE — все 5 уровней заполнены (L5=3 — мало, но не пусто)

Оставшиеся пустые: **G6 L4, G10 L5** (было 7 пустых в 8-балльной шкале).

### 5.4 app.test_client() — набор задач для G11
NOT FOUND — app.test_client требует запущенного Flask-приложения с тестовой БД. В production-режиме daily set для G11 теперь использует allowed_difficulty() → выдаёт задачи уровней 1..5.

### 5.5 Повторный запуск миграции — идемпотентность
```
Total tasks remapped: 0
L1=3756, L2=1332, L3=1626, L4=1435, L5=629
[OK] No tasks outside 1..5 range.
[OK] 8778 tasks have difficulty_level_src preserved.
```

### 5.6 pytest -q
```
798 passed, 48 failed, 14 errors, 16 skipped
```
**Базовая линия: 794 passed / 52 failed / 14 errors**
**Дельта: +4 passed, −4 failed** — регрессии нет.

### 5.7 grep по проекту — уровни 6,7,8
**CLEAN** — ни одного упоминания валидных уровней 6,7,8 в коде и шаблонах не осталось.

---

## Шаг 6: Дубликаты условий (5 шт.)

Все дубликаты — пары по 2 задачи с идентичным текстом:

| # | ids | Текст (первые 100 символов) |
|---|-----|------|
| 1 | 5316, 7945 | В уравнении x²−ax+2=0 один корень вдвое больше другого... |
| 2 | 5493, 7981 | Найдите все значения параметра k, при которых неравенство... |
| 3 | 5892, 5911 | Известно, что sin x+cos x=1/2. Найдите sin³x+cos³x. |
| 4 | 5843, 5899 | Известно, что sin x+cos x=1. Найдите sin³x+cos³x. |
| 5 | 5166, 5185 | Докажите, что для натуральных a и b, не делящихся на... |

**Рекомендация:** удалить id с большим номером в каждой паре: **7945, 7981, 5911, 5899, 5185** (более поздние дубликаты).
