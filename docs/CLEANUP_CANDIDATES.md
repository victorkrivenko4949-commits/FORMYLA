# FORMYLA — кандидаты на удаление (перепроверить перед удалением)

Ветка: `ai-edits`. Ничего не удаляется насовсем — переносим в `_archive/`
(или удаляем коммитом, который всегда можно откатить через git-историю).

## Как получить полные списки (одна команда)

```bash
git ls-files > docs/ALL_FILES.txt          # полный список всех файлов
python scripts/find_unused.py              # точный список недостижимых .py
flask routes > docs/ROUTES_BEFORE.txt      # снапшот маршрутов ДО чистки
```

После чистки `flask routes` должен дать ТОТ ЖЕ список — это гарантия,
что ничего работающего не задето.

---

## 1. figures_archive/ — удалить целиком (мёртвый код)

Подтверждено кодом: в `app.py` генерация чертежей отключена
(«FIGURES REMOVED»), код перенесён в эту папку и нигде не импортируется.

```
figures_archive/README.md
figures_archive/figure_plan_schemas.py
figures_archive/figure_plan_validator.py
figures_archive/figure_validator.py
figures_archive/figures.py
figures_archive/figures_generator.py
figures_archive/llm_router.py
figures_archive/engine/          (вся папка)
figures_archive/prompts/         (вся папка)
```

---

## 2. routes/ — 9 неиспользуемых файлов

Подтверждено: эти blueprint'ы НЕ регистрируются в `app.py`
(`register_blueprint`) и не импортируются из живых модулей
(`daily_tasks/routes.py`, `routes/prep.py` проверены).

```
routes/admin_daily_pool.py          # админ-панель задач дня (не подключена)
routes/admin_daily_tasks_stats.py   # админ-статистика задач дня (не подключена)
routes/admin_olympiads.py           # админ-CRUD олимпиад (не подключён)
routes/concierge.py                 # заменён пакетом assistant/
routes/figures.py                   # витрина фигур (фигуры отключены)
routes/figures_generator.py         # генерация фигур (фигуры отключены)
routes/friends.py                   # дубль, blueprint не зарегистрирован
routes/friends_backup.py            # бэкап того же
routes/handwriting.py               # эндпоинт почерка (не подключён)
```

⚠️ **НЕ удалять:** `routes/room_state.py` — живой: импортируется из
`routes/wb_ws.py` (WebSocket-сигналинг видеозвонков).

---

## 3. scripts/ — одноразовые утилиты (не рантайм)

Скрипты импорта/миграции/аудита/диагностики/фигур не участвуют в работе
сайта. Примеры (полный список — `git ls-files scripts/`):

```
scripts/_lvlegn_tst.py
scripts/_proof_cycle.py
scripts/_proof_run.py
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
scripts/diag*.py
scripts/chk_*.py
scripts/dump_*.py
scripts/reset_me.py
scripts/show_student_state.py
scripts/batch/         (папка)
scripts/out/           (папка)
scripts/recon/         (папка)
scripts/verify/        (папка)
```

Оставить: `scripts/find_unused.py` (наш анализатор) и `scripts/__init__.py`.

---

## 4. Корень репозитория — мусор и артефакты

Нужен `git ls-files` для полного списка (через API корень обрезается).
Категории по шаблонам имён:

**Мусор без расширения / от команд:**
```
$null
'2026-08-31
'2026-09-03
.migrated
1, 20, 5, 148, ...
Get-ChildItem
Select-String
VICTOR2.0
```

**Бэкапы и дампы:**
```
*.bak
*.zip
*.jsonl           (кроме банка задач — см. ниже)
*.txt             (кроме конфигов/README — см. ниже)
```

**Отчёты:**
```
EVIDENCE_*.md
*_FINAL_REPORT.md
PATCH_SUMMARY.md
TASK_LIST.md
DEPLOY_CHECK.md
```

**Временные скрипты/файлы:**
```
_*.py
_*.txt
diag_*.py, diag_*.txt
chk_*.py
dump_*.py
_*.json
_*.html
```

**Папки-артефакты:**
```
_6figs/
_deliverables/
_bak_before_*/
```

---

## ⚠️ НЕ удалять без отдельной проверки (данные / банк задач)

```
FORMYLA_BANK.jsonl                      # банк задач
FORMYLA_L1_L3_FINAL_v3.jsonl.txt        # срез задач
FORMYLA_SREZ*.jsonl.bak*                # срез (бэкап)
FORMYLA_SREZ_банк_среза.zip             # срез (архив)
data/figures/                           # промпты движка (связаны с фигурами)
```

---

## Порядок безопасной чистки

1. `git ls-files > docs/ALL_FILES.txt` и `python scripts/find_unused.py`.
2. Сверить `flask routes` ДО и ПОСЛЕ — список маршрутов не должен измениться.
3. Переносить по одной категории (1 → 2 → 3 → 4) отдельными коммитами
   в ветке `ai-edits`, в `_archive/`.
4. Прогнать ключевые страницы: главная, логин, задачи дня, пробник,
   календарь олимпиад, видеозвонок.
