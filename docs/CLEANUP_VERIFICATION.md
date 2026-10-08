# FORMYLA: перепроверка cleanup PR #101

Дата: 08.10.2026. Отчёт заменяет прежнее утверждение «compileall без ошибок,
ссылок на перемещённые файлы нет». Проверки выполнены в изолированной среде,
без production-БД и настоящих ключей внешних API.

## Исправления

- Восстановлены `_svg_to_png.py` и `tools/`: первый импортируется
  `services/figure_completeness_audit.py`, второй нужен `test_methods_atlas_visuals.py`.
  Один только обход импортов от `app.py` не выявил эти зависимости.
- Восстановлен `regression_night.py`, который вызывают три сценария в `scripts/`.
- Восстановлены пять `audit_*.json`, читаемых существующими служебными сценариями.
  Они сохранены ради обратной совместимости, не объявлены production-банком.
- Удалено `!archive/**` из `.gitignore`. Уже tracked материалы не требуют исключения,
  а новые `.env` и Python-кэши теперь игнорируются и в архиве.
- Удалён глобальный запрет `*.png`; целевые правила для скриншотов сохранены.
- Добавлены 18 regression-проверок зависимостей и правил игнорирования.
- README переписан по результатам реального запуска, добавлен
  `config/local.env.example` без API-ключей.

В корне теперь **30 tracked-файлов**, включая скрытые. Старое число «21» не учитывало
скрытые файлы, а число «23» относилось к слишком агрессивной первоначальной очистке.
Порог 40 файлов всё ещё соблюдён.

## Что реально проверено

| Проверка | Результат |
|---|---|
| Python | 3.12.7, соответствует `runtime.txt` |
| Установка всего `requirements.txt` в новый venv | Успешна |
| Старт из отдельного checkout без старой БД | Успешен |
| `.env` | Скопирован из нового `config/local.env.example`, production-ключей нет |
| Настоящий HTTP `/healthz`, `/__version`, `/login` | 200 |
| `/`, `/teacher`, `/daily_tasks` без входа | 302, как в исходной версии |
| Карта URL и endpoints до/после | Полностью совпала: 369 правил, 19 blueprints |
| Целевые тесты, включая новую защиту cleanup | 99 passed, 2 subtests passed |
| Тот же набор в чистом checkout | 99 passed, 2 subtests passed |
| `git diff --check` | Без ошибок |

Команда целевых тестов:

```bash
python -m pytest tests/test_cleanup_integrity.py tests/test_methods_atlas_visuals.py \
  tests/test_engine.py tests/test_condition_coverage.py tests/test_prep_tasks.py \
  -q --timeout=10
```

Чистый checkout создан из индекса git без ранее созданных runtime-файлов.
Среда зависимостей новая; она одинакова для сравнения исходной версии и PR.
Команды Linux проверены. Команды PowerShell приведены как эквивалент, но на Windows
не исполнялись. ИИ-запросы, email, авторизация внешних провайдеров и платежи не проверены.

## Полный pytest не зелёный

Полные прогоны исходной версии `b4818288` и исправляемого PR ограничены 480 секундами
с `--timeout=15` на тест. Оба завершены внешним timeout, код 124; полного итогового
счёта нет. Эти прогоны нельзя считать успешными.

Повторное сравнение с `--maxfail=8 --timeout=3` дало одинаковый результат:
**8 failed, 62 passed** в каждой версии. Совпали все восемь первых ошибок:

```text
tests/test_ai_tutor_review.py::test_sympy_correct_with_solution
tests/test_ai_tutor_review.py::test_sympy_correct_no_solution_high_level
tests/test_ai_tutor_review.py::test_sympy_wrong_ai_unavailable
tests/test_ai_tutor_review.py::TestPickCategory::test_correct_no_justification
tests/test_anchors.py::TestAnchorLoading::test_load_anchors_creates_correct_count
tests/test_atlas_tutor.py::test_system_prompt_contains_no_html_instruction
tests/test_aux_pipeline.py::test_validate_quote_no_action_stem
tests/test_aux_pipeline.py::test_usefulness_harmful_too_many_points
```

Это отделяет выявленные старые ошибки от cleanup, но не доказывает отсутствие
всех регрессий во всём приложении.

Статический синтаксический разбор живых каталогов выявил одинаковые ошибки до/после:

- `routes/friends_backup.py:94`: SyntaxError в обрезанном резервном файле.
- `services/daily_pool/generator.py:203`: IndentationError.

Их исправление не включено в чистку, чтобы не смешивать переносы и изменение
существующей бизнес-логики. Прежнее сообщение «compileall exit 0» было недостоверным:
код возврата pipeline с `head` не отражал реальный результат compileall.

## Блокирующие вопросы деплоя

На исходной версии и ветке одинаково воспроизведено:

```text
python -m flask --app app db upgrade --directory alembic_migrations
Error: No such command 'db'.
exit code: 2
```

Flask-Migrate не зарегистрирован в `app.py`; дополнительно
`v11_schema_migration_log` ссылается на отсутствующую ревизию `7bcac3b72db9`.
Именно неработающая команда указана перед Gunicorn в `render.yaml`.
Регистрировать расширение или выполнять `stamp head` без восстановления цепочки
и понимания production-схемы небезопасно. Это отдельный blocker, не устранённый PR.

Read-only проверка действующего сайта: `/healthz` вернул `{"status":"ok"}`;
`/__version` сообщил `main`, коммит `e1915ed8a58170992aeb7a3c853e64284fbbbf19`,
`applied_migrations: []`, `schema_version: "unknown"`.
Проверялся уже существующий production, а не деплой cleanup. Фактическая Start Command
в Render Dashboard не установлена; активный сайт сам по себе не подтверждает
работоспособность команды из `render.yaml`.

Публичные endpoints проверки:
https://formyla.net/healthz
https://formyla.net/__version

Дополнительные условия до merge:

1. Установить фактическую Start Command и стратегию миграций Render.
2. Подтвердить persistent storage/резервную копию пользовательских `uploads/`.
   Снятие фото с git не гарантирует сохранность файлов при новом деплое.
3. Отозвать раскрытые ключи и пароль БД. Здесь ротация не выполнялась;
   удаление значений из HEAD не делает историю безопасной.
4. После разрешённого merge проверить новый commit на `/__version`, health check
   и авторизованные сценарии. Без этого критерий «деплой зелёный» не закрыт.

## Приёмка задач

- **0.3.2:** исправления подготовлены и локально проверены; ожидает решения по
  blockers и приёмки production. Быстрый клон этим PR не доказан.
- **0.3.3:** инструкция Linux воспроизведена в чистой копии; ограничения явно
  записаны, неработающая команда больше не предлагается как успешный шаг установки.
- **main:** изменений этой перепроверкой не вносилось. История не переписывалась.

Архив остаётся tracked: переносы не уменьшают ни историю, ни суммарный объём
рабочего дерева. Ранее обещанное уменьшение checkout до 200 МБ не подтверждено.
