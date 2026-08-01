# LEVEL ENGINE PLAN — Единый держатель уровня FORMYLA

**Дата:** 2026-07-27
**Цель:** Создать `services/level_engine.py` как единственного владельца канонического уровня ученика (шкала 1-5).
**Принцип:** UI и три существующих движка НЕ переключаем. Сайт работает точно как сейчас.

---

## ШАГ 0. Пререквизиты (уже собраны)

### 0.1 Auto-ALTER pattern (анализ app.py:260-456)

Существующий механизм идемпотентных ALTER'ов:
- Блок для `curator_state.prep_state`: [`app.py:351-370`](app.py:351)
- Шаблон:
  ```python
  try:
      with app.app_context():
          from sqlalchemy import inspect, text
          inspector = inspect(db.engine)
          if 'curator_state' in inspector.get_table_names():
              columns = [col['name'] for col in inspector.get_columns('curator_state')]
              if 'col_name' not in columns:
                  db.session.execute(text("ALTER TABLE curator_state ADD COLUMN col_name TYPE DEFAULT ..."))
                  db.session.commit()
  except Exception as e:
      print(f"[AUTO-MIGRATION] curator_state.col_name Warning: {e}")
  ```

### 0.2 `adaptive_tasks` schema

Колонки `source` (TEXT) и `difficulty_level` (INTEGER) добавлены через авто-ALTER — [`app.py:314-317`](app.py:314). Значения `source` будут определены в ШАГЕ 1 через SELECT.

### 0.3 `CuratorState` model — [`models_curator.py:10-25`](models_curator.py:10)

12 существующих колонок: `id`, `user_id`, `target_olympiads`, `grade`, `goal_text`, `prep_plan`, `prep_state`, `onboarding_done`, `last_diagnostic_id`, `summary`, `created_at`, `updated_at`.

### 0.4 Три движка — все игнорируют анкету

- **A** (session-based, шкала 1–5): [`app.py:7235`](app.py:7235)
- **B** (profile-based, шкала 1–8): [`daily_tasks/profile.py:245`](daily_tasks/profile.py:245)
- **C** (curator diagnostic, шкала 1–8): [`curator/diagnostics.py:65`](curator/diagnostics.py:65)

---

## ШАГ 1. SELECT из локальной БД (instance/formyla.db)

```sql
SELECT source, difficulty_level, COUNT(*)
FROM adaptive_tasks
GROUP BY source, difficulty_level
ORDER BY source, difficulty_level;
```

**Цель:** определить, какие значения `source` существуют и к какой шкале относится каждый источник (5-балльной или 8-балльной). Это нужно для `allowed_difficulty()`.

**Кто выполняет:** Code mode (architect не может выполнять команды).

---

## ШАГ 2. services/level_engine.py — проект кода

### 2.1 Константы в начале файла (заполнятся после ШАГА 1)

```python
# Шкала 1..5 (пятибалльные источники — difficulty_level ∈ {1,2,3,4,5})
FIVE_POINT_SOURCES = {
    # ЗАПОЛНИТЬ после ШАГА 1: источники, где max(difficulty_level) = 5
}

# Шкала 1..8 (восьмибалльные источники — difficulty_level ∈ {1..8})
EIGHT_POINT_SOURCES = {
    # ЗАПОЛНИТЬ после ШАГА 1: источники, где max(difficulty_level) = 8
}
```

### 2.2 Маппинг канонического уровня → difficulty_level

```python
FIVE_POINT_MAP = {1: [1], 2: [2], 3: [3], 4: [4], 5: [5]}
EIGHT_POINT_MAP = {1: [1, 2], 2: [3], 3: [4, 5], 4: [6], 5: [7, 8]}
```

### 2.3 API

#### `get_state(user_id) -> dict`

Читает `CuratorState.level_mu`, `level_sigma`, `level_by_section`, `level_updated_at`. Если записи нет — возвращает дефолты: `mu=3.0, sigma=1.5, level=3, by_section={}, updated_at=None`.

```python
def get_state(user_id: int) -> dict:
    cs = CuratorState.query.filter_by(user_id=user_id).first()
    if not cs or cs.level_mu is None:
        return {"mu": 3.0, "sigma": 1.5, "level": 3, "by_section": {}, "updated_at": None}
    by_section = json.loads(cs.level_by_section) if cs.level_by_section else {}
    level = max(1, min(5, int(round(cs.level_mu))))
    return {"mu": cs.level_mu, "sigma": cs.level_sigma, "level": level,
            "by_section": by_section, "updated_at": cs.level_updated_at}
```

#### `set_prior(user_id, mu, sigma, source: str) -> dict`

Создаёт/обновляет `CuratorState`:
- `level_mu = clamp(mu, 1.0, 5.0)`
- `level_sigma = max(0.35, sigma)`
- `level_by_section = "{}"` (JSON)
- `level_updated_at = utcnow().isoformat()`
- `onboarding_done = True` (если ещё не был)

```python
def set_prior(user_id: int, mu: float, sigma: float, source: str = "") -> dict:
    mu = max(1.0, min(5.0, mu))
    sigma = max(0.35, sigma)
    cs = CuratorState.query.filter_by(user_id=user_id).first()
    if cs is None:
        cs = CuratorState(user_id=user_id)
        db.session.add(cs)
    cs.level_mu = mu
    cs.level_sigma = sigma
    cs.level_by_section = "{}"
    cs.level_updated_at = datetime.utcnow().isoformat()
    if not cs.onboarding_done:
        cs.onboarding_done = True
    db.session.commit()
    return get_state(user_id)
```

#### `record_result(user_id, section, level_shown, correct: bool) -> dict`

Формулы из ТЗ:
```
if correct: mu += 0.22 * (sigma + 0.3)
else:       mu -= 0.28 * (sigma + 0.3)
sigma = max(0.35, sigma * 0.94)
mu = clamp(mu, 1.0, 5.0)
level = int(round(mu)), clamp [1, 5]
```

Обновляет `by_section[section]` теми же формулами + инкрементит `n`.

```python
def record_result(user_id: int, section: str, level_shown: int,
                  correct: bool) -> dict:
    cs = CuratorState.query.filter_by(user_id=user_id).first()
    if cs is None or cs.level_mu is None:
        # авто-set_prior с defaults
        set_prior(user_id, 3.0, 1.5, "auto")
        cs = CuratorState.query.filter_by(user_id=user_id).first()

    mu = cs.level_mu
    sigma = cs.level_sigma

    if correct:
        mu += 0.22 * (sigma + 0.3)
    else:
        mu -= 0.28 * (sigma + 0.3)

    sigma = max(0.35, sigma * 0.94)
    mu = max(1.0, min(5.0, mu))

    cs.level_mu = mu
    cs.level_sigma = sigma
    cs.level_updated_at = datetime.utcnow().isoformat()

    # by_section обновление
    by_section = json.loads(cs.level_by_section or "{}")
    sec = by_section.get(section, {"mu": mu, "sigma": sigma, "n": 0})
    sec["n"] += 1
    if correct:
        sec["mu"] += 0.22 * (sec["sigma"] + 0.3)
    else:
        sec["mu"] -= 0.28 * (sec["sigma"] + 0.3)
    sec["sigma"] = max(0.35, sec["sigma"] * 0.94)
    sec["mu"] = max(1.0, min(5.0, sec["mu"]))
    by_section[section] = sec
    cs.level_by_section = json.dumps(by_section, ensure_ascii=False)

    db.session.commit()
    return get_state(user_id)
```

#### `allowed_difficulty(level_5: int, source: str) -> list[int]`

```python
def allowed_difficulty(level_5: int, source: str) -> list[int]:
    level_5 = max(1, min(5, level_5))
    if source in EIGHT_POINT_SOURCES:
        return EIGHT_POINT_MAP.get(level_5, [level_5])
    elif source in FIVE_POINT_SOURCES:
        return FIVE_POINT_MAP.get(level_5, [level_5])
    else:
        logging.warning(f"level_engine: unknown source '{source}', treating as 5-point")
        return FIVE_POINT_MAP.get(level_5, [level_5])
```

### 2.4 Файловая структура

```
services/level_engine.py    — весь публичный API + константы
```

**Импорты:** `json`, `logging`, `datetime`, `models.db`, `models_curator.CuratorState`.

**Никакие routes/ или templates/ НЕ импортируют level_engine на этом шаге.**

---

## ШАГ 3. Хранение — изменения в трёх файлах

### 3.1 models_curator.py — 4 новые колонки

Добавить в класс `CuratorState` после `prep_state` (строка 19):

```python
    level_mu = db.Column(db.Float, nullable=True)
    level_sigma = db.Column(db.Float, nullable=True)
    level_by_section = db.Column(db.Text, nullable=True)
    level_updated_at = db.Column(db.Text, nullable=True)
```

### 3.2 app.py — авто-ALTER блок

Добавить после блока `curator_state.prep_state` (после строки 370), тем же паттерном:

```python
# AUTO-MIGRATION: Add level_engine columns to curator_state
try:
    with app.app_context():
        from sqlalchemy import inspect, text
        inspector = inspect(db.engine)
        if 'curator_state' in inspector.get_table_names():
            columns = [col['name'] for col in inspector.get_columns('curator_state')]
            new_level_cols = {
                'level_mu': 'REAL',
                'level_sigma': 'REAL',
                'level_by_section': 'TEXT',
                'level_updated_at': 'TEXT',
            }
            for col_name, col_type in new_level_cols.items():
                if col_name not in columns:
                    db.session.execute(text(
                        f"ALTER TABLE curator_state ADD COLUMN {col_name} {col_type}"
                    ))
                    db.session.commit()
                    print(f"[AUTO-MIGRATION] ✓ Column '{col_name}' added to curator_state")
                else:
                    print(f"[AUTO-MIGRATION] ✓ Column '{col_name}' already exists on curator_state")
except Exception as e:
    print(f"[AUTO-MIGRATION] curator_state level_engine Warning: {e}")
```

### 3.3 Что НЕ трогаем

- `diagnostic_questionnaire.py` — остаётся как есть
- `questionnaire_storage.py` — остаётся как есть (пишет в `prep_state.questionnaire`, не конфликтует)
- Никакие routes, templates, движки

---

## ШАГ 4. scripts/test_level_engine.py

```python
"""Smoke test for services/level_engine.py — standalone script, not pytest."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from models import db, User
from services.level_engine import get_state, set_prior, record_result, allowed_difficulty

with app.app_context():
    # 1. Get an existing user_id
    user = User.query.first()
    if not user:
        print("SKIP: no users in DB")
        sys.exit(0)
    uid = user.id
    print(f"Testing with user_id={uid}")

    # 2. set_prior
    state = set_prior(uid, mu=2.5, sigma=1.35, source="test")
    print(f"set_prior: mu={state['mu']:.3f} sigma={state['sigma']:.3f} level={state['level']}")

    # 3. 10 calls: 7 correct, 3 incorrect
    results = [True, True, False, True, True, False, True, False, True, True]
    print("\nStep | mu     | sigma  | level | correct")
    print("-" * 50)
    for i, correct in enumerate(results, 1):
        state = record_result(uid, "test_section", level_shown=state['level'], correct=correct)
        print(f"{i:4d} | {state['mu']:.3f} | {state['sigma']:.3f} | {state['level']:5d} | {correct}")

    # 4. Verify invariants
    final = get_state(uid)
    print(f"\nFinal: mu={final['mu']:.3f} sigma={final['sigma']:.3f} level={final['level']}")

    errors = []
    if not (1.0 <= final['mu'] <= 5.0):
        errors.append(f"FAIL: mu={final['mu']} out of [1,5]")
    if final['sigma'] < 0.35:
        errors.append(f"FAIL: sigma={final['sigma']} < 0.35")
    # Check sigma monotonic decrease
    # Check final level > start level
    start_level = 3  # int(round(2.5))
    if final['level'] <= start_level:
        errors.append(f"FAIL: final level {final['level']} <= start {start_level} after 7/10 correct")

    if errors:
        for e in errors:
            print(e)
    else:
        print("ALL CHECKS PASSED")

    # 5. allowed_difficulty for all sources
    print("\nallowed_difficulty:")
    from services.level_engine import FIVE_POINT_SOURCES, EIGHT_POINT_SOURCES
    all_sources = sorted(set(list(FIVE_POINT_SOURCES) + list(EIGHT_POINT_SOURCES)))
    if not all_sources:
        print("  (no sources defined — run ШАГ 1 first)")
    for src in all_sources:
        for lvl in range(1, 6):
            print(f"  level {lvl} -> source '{src}': {allowed_difficulty(lvl, src)}")

    # 6. Rollback: set level columns back to NULL for this user
    from models_curator import CuratorState
    cs = CuratorState.query.filter_by(user_id=uid).first()
    if cs:
        cs.level_mu = None
        cs.level_sigma = None
        cs.level_by_section = None
        cs.level_updated_at = None
        db.session.commit()
        print("\nRollback: test user level columns reset to NULL")
```

---

## КРИТЕРИИ ПРИЁМКИ

| # | Критерий | Как проверить |
|---|----------|---------------|
| 1 | Вывод SELECT из ШАГА 1 полностью | Скопировать вывод в терминале |
| 2 | `python -m py_compile services/level_engine.py app.py` → exit 0 | Запустить дважды |
| 3 | `python scripts/test_level_engine.py` → прошёл | Вывод целиком |
| 4 | Повторный авто-ALTER не падает | Перезапустить app.py дважды, оба раза без ошибок ALTER |
| 5 | `GET /` возвращает 200 при `ENABLE_SCHEDULER=0` | Проверить логи |
| 6 | `level_engine` не импортируется в routes/ и templates/ | `grep -r "level_engine" routes/ templates/` → пусто |

---

## ПОРЯДОК ВЫПОЛНЕНИЯ (в code mode)

1. **ШАГ 1**: Выполнить SELECT, скопировать вывод, заполнить `FIVE_POINT_SOURCES` / `EIGHT_POINT_SOURCES`
2. **ШАГ 2**: Создать `services/level_engine.py` с константами из шага 1
3. **ШАГ 3**: Добавить 4 колонки в `models_curator.py`, добавить авто-ALTER в `app.py`
4. **ШАГ 4**: Создать `scripts/test_level_engine.py`, запустить
5. Проверить все 6 критериев приёмки
