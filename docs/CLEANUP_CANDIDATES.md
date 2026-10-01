# FORMYLA — кандидаты на чистку (перепроверка перед переносом)

> Ветка: ai-edits. Ничего не удаляется насовсем — всё переносится в `_archive/`
> скриптом `scripts/archive_unused.py`. Git-история остаётся страховкой.

## Как получен список

Граф подключения построен чтением `app.py` (точка входа, 576 КБ) и проверкой
всех `register_blueprint(...)`. Файлы ниже НЕ импортируются из живого кода
и НЕ регистрируются как blueprint.

---

## 1. Мёртвый код — 100% уверенность

### 1.1. figures_archive/ — отключено с сайта
В `app.py` явно указано: генерация чертежей отключена, код сохранён отдельно.

```
figures_archive/  (вся папка целиком)
```

### 1.2. Незарегистрированные route-файлы (9 шт.)
Сверено со всеми `register_blueprint` в `app.py`. Их там нет, и в живых
модулях (`daily_tasks/routes.py`, `routes/prep.py`) они не импортируются.

```
routes/admin_daily_pool.py
routes/admin_daily_tasks_stats.py
routes/admin_olympiads.py
routes/concierge.py          # заменён пакетом assistant/ (app.py: «legacy /api/concierge/*»)
routes/figures.py            # витрина фигур — отключена
routes/figures_generator.py  # генерация фигур — отключена
routes/friends.py            # дубль friends_backup
routes/friends_backup.py
routes/handwriting.py
```

> НЕ трогать: `routes/room_state.py` — импортируется из `routes/wb_ws.py` (WebSocket).

### 1.3. scripts/ — одноразовые утилиты (не рантайм)
Не участвуют в работе сайта. Это импортёры/сидеры/аудиты/диагностика.

```
scripts/_lvlegn_tst.py
scripts/_proof_cycle.py
scripts/_proof_run.py
scripts/exhaustive_proof.py
scripts/proof_*.py
scripts/final_rehearsal*.py
scripts/ch19_*.py … ch27*.py
scripts/stage1*.py
scripts/figures_*.py
scripts/batch_draw.py
scripts/import_*.py
scripts/migrate_*.py
scripts/*_migration.py
scripts/audit_*.py
scripts/smoke_*.py
scripts/test_*.py
scripts/http_smoke_test.py
scripts/regression_night.py
scripts/diag*.py
scripts/chk_*.py
scripts/dump_*.py
scripts/reset_me.py
scripts/show_student_state.py
scripts/batch/  out/  recon/  verify/   (папки)
```

---

## 2. Корневой мусор — высокая уверенность (по шаблону имени)

Корень забит артефактами. Точный полный список даёт `git ls-files`,
но по шаблонам это мусор:

```
# файлы без расширения (артефакты shell-команд)
$null  '2026-08-31  '2026-09-03  .coverage  .migrated
1  20  5  148  Get-ChildItem  Select-String  VICTOR2.0

# бэкапы и дампы
*.bak  *.zip  *.jsonl.bak*

# отчёты (можно оставить в docs/, из корня — в архив)
EVIDENCE_*.md  *_FINAL_REPORT.md  PATCH_SUMMARY.md  TASK_LIST.md  DEPLOY_CHECK.md

# временные скрипты/файлы
_*.py  _*.txt  _*.json  _*.html
diag_*.py  diag_*.txt  chk_*.py  dump_*.py
FORMYLA_AUDIT_FIX_FINAL.py

# папки-артефакты
_6figs/  _deliverables/  _bak_before_e21/  _bak_before_e8e11/
```

---

## 3. НЕ ТРОГАТЬ без отдельной проверки (данные/конфиг)

```
FORMYLA_BANK.jsonl
FORMYLA_L1_L3_FINAL_v3.jsonl.txt
FORMYLA_SREZ*.jsonl*
secrets_dump.json
.env.example
.gitignore
requirements.txt
Procfile (если есть)
app.py, models*.py, wsgi.py, run.py
```

---

## 4. Что осталось непроверенным (честно)

1. **services/ (110 файлов)** — точный граф «кто кого импортирует» требует
   полного AST-анализа. Делается скриптом `scripts/find_unused.py`:
   ```bash
   python scripts/find_unused.py
   ```
2. **Полный список корня** — `list_files` API обрезает большие папки.
   ```bash
   git ls-files > docs/ALL_FILES.txt
   ```

После запуска этих двух команд список можно закрыть на 100%.
