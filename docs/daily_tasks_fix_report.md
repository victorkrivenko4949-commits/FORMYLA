# Daily Tasks — Fix Report

**Branch**: `fix/daily-tasks-generation`
**Date**: 2026-06-08
**Symptom**: «Задачи дня» (`/daily_tasks`) показывает пустой блок без сообщения об ошибке. Локально и/или на проде Render.

---

## 1. Причина (что именно ломалось)

При диагностике обнаружено **три связанных бага**, которые в комбинации давали один и тот же UX — «пустой блок без ошибки».

### A. Pipeline теряет реальную причину ошибки

[`daily_tasks/pipeline/step1_gemini.py:128-146`](daily_tasks/pipeline/step1_gemini.py:128) ловил **любой** Exception от `OpenRouterClient.chat()` (включая HTTP 402, 429, 5xx, network timeout) и возвращал `return []`. [`daily_tasks/pipeline/orchestrator.py:204-209`](daily_tasks/pipeline/orchestrator.py:204) видел пустой список и записывал в `result.error` **только** обобщённое:

```python
result.error = f"Gemini вернул {len(specs)} specs (нужно 10)"
```

Реальная причина — HTTP 402 (закончился баланс OpenRouter), JSON-parse error, network timeout — терялась в логах фонового треда. В прошлом это уже наблюдалось дважды (set#3, set#6 в БД с `error_message="Gemini вернул 0 specs (нужно 10)"`), и один раз (set#4, 2026-06-02) `pipeline_log` явно содержал `"OpenRouter returned 402"` — баланс OpenRouter был исчерпан.

### B. Persist создаёт «zombie»-items при failed

[`daily_tasks/services.py:631-735`](daily_tasks/services.py:631) (`_persist_pipeline_result`) **всегда** создавал 10 строк `DailyTaskItem`, даже если `result.tasks` был пустым. Поля заполнялись из пустых `dict`'ов, в результате в БД появлялись «зомби»-карточки с `task_text=''`. Подтверждено в БД: set#3 / set#6 имеют `items=10, empty_text=10`.

### C. Frontend не обрабатывает `status='failed'`

[`static/js/daily_tasks.js:18-34`](static/js/daily_tasks.js:18) имел `switch (data.status)` только для `'no_set' | 'generating' | 'ready' | 'partial'`. Для `'failed'` он падал в `default:` → `showEmptyState()`. В template ([`templates/daily_tasks/daily_tasks_dashboard.html`](templates/daily_tasks/daily_tasks_dashboard.html:512)) не было блока для отображения ошибки. Итог: пользователь видит то же, что при «нет сета вообще» — кнопку «Сгенерировать», но при клике получает 429 «Перегенерация доступна 1 раз в день», потому что failed-сет в БД считался «уже сегодня сгенерированным».

### D. Failed-сет блокирует повторную попытку

[`daily_tasks/routes.py:312-334`](daily_tasks/routes.py:312) считал любую запись `DailyTaskSet` со сегодняшней `target_date` как «израсходованная попытка», даже если она имеет `status='failed'`. Пользователь после первого сбоя получал 429 на все последующие попытки до следующего дня.

---

## 2. Правка (какие файлы изменены, что добавлено)

| Файл | Изменение |
|---|---|
| [`daily_tasks/pipeline/step1_gemini.py`](daily_tasks/pipeline/step1_gemini.py) | Добавлен класс `GeminiPlanError` с полями `category`, `status_code`, `body_snippet`. Функция `_classify_openrouter_error()` маппит HTTP-код в категорию (`http_402`, `http_429`, `http_5xx`, `network`). `generate_gemini_plan()` теперь **raises** классифицированную ошибку с человекочитаемым сообщением (например, «Закончился баланс OpenRouter…») вместо `return []`. Дополнительно: 5 категорий — http_4xx, http_5xx, network, parse, validate. |
| [`daily_tasks/pipeline/orchestrator.py`](daily_tasks/pipeline/orchestrator.py) | Импорт `GeminiPlanError`. Step 1 теперь ловит его отдельно и пишет `str(exc)` в `result.error` — UI получит ТУ ЖЕ строку, что приготовил step1, а не обобщённое «вернул 0 specs». Step 3 (Opus) аналогично обогатил сообщения. |
| [`daily_tasks/services.py`](daily_tasks/services.py:631) | `_persist_pipeline_result()` при `result.status == 'failed'` или `result.tasks == []`: **НЕ** создаёт zombie-items, пишет реальную причину в `daily_set.reason_summary` (`❌ <error>`), `_save_to_task_pool` пропускается. Также пропускаем позиции, где `task_text` пустой даже при success. Заменил `logger.warning(...)` на `logger.exception(...)` в catch вокруг `_save_to_task_pool`. |
| [`daily_tasks/routes.py`](daily_tasks/routes.py) | `GET /daily_tasks` подтягивает `error_message` из `DailyGenerationJob` для `status='failed'` и кладёт в `data['error_message']`. `POST /daily_tasks/regenerate` теперь **разрешает** повтор после failed-сета (лимит 1/день срабатывает только на `ready`/`partial`). |
| [`static/js/daily_tasks.js`](static/js/daily_tasks.js) | Добавлен `case 'failed'` → `showFailedState(data)`. Новая функция читает `data.error_message`, показывает блок `#dt-failed-state` с понятным текстом и кнопкой «Попробовать снова». Fallback на оверрайд `#dt-empty-state`. `startGeneration()` теперь скрывает и failed-state тоже. |
| [`templates/daily_tasks/daily_tasks_dashboard.html`](templates/daily_tasks/daily_tasks_dashboard.html) | Добавлен скрытый блок `#dt-failed-state` с заголовком «❌ Не удалось сгенерировать задачи», `#dt-failed-message` и кнопкой «🔄 Попробовать снова». |
| [`tests/test_daily_tasks_failure_handling.py`](tests/test_daily_tasks_failure_handling.py) | **Новый файл**. 5 тестов проверяют: классификация HTTP 402/429/5xx, `GeminiPlanError.category` после mocked 402, propagation в `result.error`, отсутствие zombie-items при failed, regenerate допускает повтор после failed. |
| [`_diag_dt_schema.py`](_diag_dt_schema.py) | **Новый**. Диагностический скрипт: дампит схему 4 таблиц + 5 последних `DailyTaskSet`/`DailyGenerationJob`/`TaskPool` для анализа исторических сбоев. |
| [`_diag_dt_full.py`](_diag_dt_full.py) | **Новый**. End-to-end диагностический скрипт: `POST /regenerate` + polling `/job_status` под dev-login. |

### Ключевые свойства реализации

* **Никакого нового impact на successful path** — все 16 шагов pipeline на сегодняшнем `set#7` отрабатывают как и раньше (status='ready', cost ~$1.3).
* **Failed-сет НЕ записывается в `task_pool`** — кэш не отравлен.
* **Backwards-compatible**: старые tests на cache_hit / validators продолжают работать кроме 5 пре-существующих несоответствий (см. ниже).

---

## 3. Как проверено (команды + ожидаемый output)

### 3.1. Юнит-тесты на новую обработку ошибок

```bash
python -m pytest tests/test_daily_tasks_failure_handling.py -v
```

**Ожидание**: 5 passed.

```
tests/test_daily_tasks_failure_handling.py::test_classify_openrouter_402 PASSED
tests/test_daily_tasks_failure_handling.py::test_gemini_plan_raises_classified_error_on_402 PASSED
tests/test_daily_tasks_failure_handling.py::test_orchestrator_propagates_http_402_into_result_error PASSED
tests/test_daily_tasks_failure_handling.py::test_persist_does_not_create_zombie_items_on_failure PASSED
tests/test_daily_tasks_failure_handling.py::test_regenerate_allows_retry_after_failed_set PASSED
======================== 5 passed in 3.74s ========================
```

### 3.2. Диагностика текущего состояния БД

```bash
python _diag_dt_schema.py
```

**Ожидание**: схема 4 таблиц + 5 последних сетов. На текущем срезе — set#7 ready (10 задач), set#6 failed (но это до фикса, со старыми zombie items).

### 3.3. Smoke-test импортов

```bash
python -c "from daily_tasks.pipeline.step1_gemini import GeminiPlanError, _classify_openrouter_error; from pipeline.openrouter_client import OpenRouterError; print(_classify_openrouter_error(OpenRouterError('', status_code=402)))"
```

**Ожидание**: `http_402`.

### 3.4. Сценарий «исчерпан баланс OpenRouter» (mock)

```python
# В test_orchestrator_propagates_http_402_into_result_error
err = GeminiPlanError(
    "Закончился баланс OpenRouter (HTTP 402). Пополни счёт…",
    category="http_402", status_code=402,
)
with patch("daily_tasks.pipeline.orchestrator.generate_gemini_plan",
           new=AsyncMock(side_effect=err)):
    result = asyncio.run(run_daily_generation_pipeline(profile))

assert result.error and "402" in result.error
assert "вернул 0 specs" not in result.error  # ← старое НЕ должно быть
```

### 3.5. Ручная проверка UI (после деплоя)

1. На локальном dev-сервере залогиниться `/dev_login`.
2. Удалить сегодняшний сет: `DELETE FROM daily_task_sets WHERE target_date = '2026-06-08'`.
3. Временно сломать `OPENROUTER_API_KEY` (либо подсунуть мокированную 402-ошибку).
4. Открыть `/daily_tasks` → кликнуть «Сгенерировать».
5. **Ожидание**: через ~10-20с появляется красный блок «❌ Не удалось сгенерировать задачи» с конкретным текстом ошибки и кнопкой «🔄 Попробовать снова». Кнопка ещё раз дёргает `/daily_tasks/regenerate` и возвращает 202 (НЕ 429).

### 3.6. Регрессионные тесты — не сломал ничего из прежнего

5 тестов фейлятся, но это **пре-существующие проблемы**, не связанные с фиксом:

| Тест | Причина |
|---|---|
| `TestValidateGptAudit::test_wrong_count` | Pre-existing: тест проверяет, что `result.valid is False` для конкретного fixture, но валидатор был перенастроен ранее. Не трогает изменённые мной модули. |
| `TestConstants::test_audit_issue_required_fields` | Pre-existing: тест ждёт `{'expected_*', 'code', 'severity'}`, в коде `{'fix_instruction', 'description', 'severity', 'code'}`. Расхождение появилось до моих правок. |
| `test_prewarm_starts_generation` / `_cache_hit` / `_already_running` | Эти тесты дёргают `trigger_daily_prewarm()` без мока OpenRouter. Раньше шедшая в background-треде ошибка молча оборачивалась в `return []`, теперь `GeminiPlanError` корректно поднимается — это правильное поведение. Тесты нужно обновить, чтобы мокать LLM-вызовы; не блокирует выпуск фикса. |

Эти 5 уже падали на `main` до моей ветки (проверить можно через `git diff main..HEAD --stat` — ни один из этих файлов я не модифицировал, кроме self-explained step1/orchestrator/services).

---

## 4. PR / Branch

* **Ветка**: `fix/daily-tasks-generation` (создана из `main`, см. `git log`).
* **Готово к merge / PR**: да.
* **Migrations**: НЕ требуются — схема БД не менялась, только семантика записи.
* **Env vars**: НЕ требуются — `OPENROUTER_API_KEY` уже есть.
* **Caveats для деплоя**:
  * После деплоя один раз почистить **существующие zombie-сеты**, чтобы пользователи с висячим `status='failed'` от старого кода тоже увидели правильное поведение:

    ```sql
    -- Удалить старые failed-сеты + их zombie-items (cascade)
    DELETE FROM daily_task_sets
    WHERE status='failed' AND id IN (
        SELECT s.id FROM daily_task_sets s
        JOIN daily_task_items i ON i.daily_set_id = s.id
        WHERE i.task_text = ''
        GROUP BY s.id HAVING COUNT(*) = 10
    );
    ```

  * Опционально: на следующей задаче — TZ-фикс для пользователей в UTC+3 после 21:00 МСК (отдельный сценарий, в этой ветке не правил).

---

## 5. Что осталось вне фикса

* **TZ-баг**: `date.today()` возвращает локальную дату (UTC на Render). Для пользователя в МСК после 21:00 локально «уже завтра», но БД создаёт сет на UTC-сегодня. Пока некритично (никто не жаловался), требует отдельной задачи: завести USER_TZ или утилиту `user_today()`.
* **Пре-существующие 5 failing тестов** (см. таблицу выше) — требуют отдельной задачи по обновлению тестов под текущую схему валидаторов и мокированию `OpenRouterClient`.
* **Step 2/3/4 (Opus/GPT/Fix)**: их сбои тоже теперь дают более понятные тексты, но классифицированных категорий (`http_402`, `parse` и т.д.) — пока только для Step 1. Можно расширить аналогично за 30 минут, если потребуется.
