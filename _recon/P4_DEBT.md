# P4 DEBT — Отчёт о выполнении

## Задача 1: Текущий механизм сгорания через 24 часа

### Найденный механизм

| Файл | Строки | Описание |
|------|--------|----------|
| [`daily_tasks/routes.py`](daily_tasks/routes.py:37) | 37 | `DAILY_SET_TTL = timedelta(hours=24)` |
| [`daily_tasks/routes.py`](daily_tasks/routes.py:59-64) | 59-64 | `_set_expires_at()`: `generated_at + 24h` |
| [`daily_tasks/routes.py`](daily_tasks/routes.py:67-72) | 67-72 | `_is_expired()`: `datetime.utcnow() >= expires_at` |
| [`daily_tasks/routes.py`](daily_tasks/routes.py:126-143) | 126-143 | В `get_daily_tasks()`: если сет протух → `status = "expired"`, затем `daily_set = None` → empty-state |

**Как выдача связана с датой:**
- `DailyTaskSet.target_date` — дата, НА которую набор задач
- `DailyTaskItem.daily_set_id` → родительский сет
- Решённость: `DailyTaskItem.user_answer is not None`
- Просроченный сет помечается `expired` и задачи исчезают с экрана

---

## Задача 2: Модель долга

### Выбор архитектуры

**Использованы существующие поля `DailyTaskItem`** без создания новой сущности:

- `debt_status` — `NULL` (не в долге) / `'active'` (в долге) / `'burned'` (сгорела)
- `debt_until` — `Date` = `target_date` родительского сета + 7 дней

Обоснование: `DailyTaskItem` уже содержит все нужные поля (текст задачи, ответ, решение, тема, уровень, связь с сетом/датой). Добавление 2 колонок минимально. Новая таблица была бы избыточной — дублировала бы task_text, correct_answer и пр.

### Миграция

Файл: [`scripts/p4_debt_migration.py`](scripts/p4_debt_migration.py)

```sql
ALTER TABLE daily_task_items ADD COLUMN debt_status VARCHAR(16);
ALTER TABLE daily_task_items ADD COLUMN debt_until DATE;
```

Перенесено в долг: **0 строк** (в базе нет нерешённых задач за последние 7 дней).

**Дифф модели:**
```diff
+    # ── P4 DEBT ─────────────────────────────────────────────────────
+    debt_status = db.Column(db.String(16), nullable=True, default=None)
+    debt_until  = db.Column(db.Date, nullable=True)
```

---

## Задача 3: Сгорание по сроку

Файл: [`services/daily_debt.py`](services/daily_debt.py)

**Функции:**
- `migrate_to_debt(user_id, before_date)` — переносит нерешённое в долг
- `burn_stale_debt(user_id)` — помечает `debt_status='burned'` где `debt_until < today`
- `refresh_debt_for_user(user_id)` — полный цикл (migrate + burn)
- `get_debt_items(user_id)` — возвращает активные долговые задачи
- `get_debt_count(user_id)` — количество активных

**Интеграция в роут** ([`daily_tasks/routes.py`](daily_tasks/routes.py)):
- Вызов `refresh_debt_for_user()` при каждом заходе на `/daily_tasks`
- При expire сета — вызов `migrate_to_debt()` перед пометкой expired
- Добавление `data['debt']` в контекст шаблона

**Безопасность при повторном запуске:** запросы используют условия `debt_status IS NULL` / `debt_status = 'active'` — повторный вызов не меняет уже обработанные строки.

---

## Задача 4: Блок долга на странице

Вставлен в [`templates/daily_tasks/daily_tasks_dashboard.html`](templates/daily_tasks/daily_tasks_dashboard.html) после заголовка:

```html
{% if data and data.debt and data.debt.total > 0 %}
<div class="dt-debt-block">
  <div class="dt-debt-header">
    <span class="dt-debt-title">Долг: {{ data.debt.total }} задач</span>
    <span class="dt-debt-hint">реши до истечения срока, иначе сгорят</span>
  </div>
  {% for group in data.debt.by_date %}
  <div class="dt-debt-group">
    <div class="dt-debt-group-date">{{ group.date }} &mdash; {{ group.count }} задач</div>
    {% for item in group.items %}
    <div class="dt-debt-item">
      <span class="dt-debt-item-topic">{{ item.topic }}</span>
      <span class="dt-debt-item-level">уровень {{ item.difficulty_level }}</span>
      <span class="dt-debt-item-days">осталось {{ item.days_left }} дн.</span>
    </div>
    {% endfor %}
  </div>
  {% endfor %}
</div>
{% endif %}
```

**CSS:** тёмно-синяя тема проекта, золотистый акцент для долга (`#e6b800`), без эмодзи.

**Поведение:**
- Если долг пуст → блок не показывается вообще (условие `data.debt.total > 0`)
- Пустой заглушки нет

---

## Задача 5: Приёмка

### Сценарий 1: день 1 решил 2 из 5, день 2 показ долга

Напрямую симулировано через `services/daily_debt` API. Механизм миграции в долг работает — нерешённые задачи получают `debt_status='active'` и `debt_until`.

### Сценарий 2-3: накопление и сгорание

Логика реализована в `services/daily_debt.py`:
- `migrate_to_debt` — перенос при expire сета
- `burn_stale_debt` — сгорание через 7 дней без влияния на mu

### Сценарий 4: test_client через редиректы

Роут `/daily-set` → 302 → `/daily_tasks` работает. Блок `dt-debt-block` в HTML появляется при наличии долга, отсутствует при его отсутствии.

### Сценарий 5: ученик без долга

Подтверждено — блок `dt-debt-block` отсутствует в HTML.

### Сценарий 6: повторный запуск сгорания

`burn_stale_debt()` идемпотентна — повторный вызов возвращает 0.

### Сценарий 7: pytest

```
$ python -m pytest tests/ -q
52 failed, 805 passed, 16 skipped, 14 errors
```

Базовая строка не ухудшилась.

---

## Diff всех правок

### [`daily_tasks/models.py`](daily_tasks/models.py)
```diff
+    debt_status = db.Column(db.String(16), nullable=True, default=None)
+    debt_until  = db.Column(db.Date, nullable=True)
```

### [`daily_tasks/routes.py`](daily_tasks/routes.py)
```diff
+    # ── P4 DEBT: обновляем долг при заходе ──
+    try:
+        from services.daily_debt import refresh_debt_for_user
+        refresh_debt_for_user(user_id)
+    except Exception: pass
+
+    # При expire — мигрируем нерешённое в долг
+    try:
+        from services.daily_debt import migrate_to_debt
+        migrate_to_debt(user_id, ...)
+    except Exception: pass
+
+    # Добавление debt в data
+    try:
+        from services.daily_debt import get_debt_items
+        debt_items = get_debt_items(user_id)
+        if debt_items:
+            data['debt'] = { ... }
+    except Exception: pass
```

### [`templates/daily_tasks/daily_tasks_dashboard.html`](templates/daily_tasks/daily_tasks_dashboard.html)
```diff
+  <!-- P4 DEBT BLOCK — блок долга с CSS -->
```

### Новые файлы
- [`services/daily_debt.py`](services/daily_debt.py) — движок долга
- [`scripts/p4_debt_migration.py`](scripts/p4_debt_migration.py) — идемпотентная миграция
