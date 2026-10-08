# Задачи 0.6.1 и 0.5.2: проверка реализации

Дата: 08.10.2026. Ветка `refactor/blueprints`, основана на `chore/cleanup`.
Этот документ описывает локальные проверки, не приёмку production.

## Изменения

- `teacher/routes.py`: 7 legacy-маршрутов наставничества и профиля ученика.
- `teacher/groups.py`: ранее существовавший кабинет учителя/родителя, перенос без изменения содержимого.
- `billing/routes.py`: 3 прежних маршрута подписки, флаг шаблонов и нормализация тарифа. Это демо без оплаты, не платёжная система.
- `bank/routes.py`: 3 маршрута базы знаний; `bank/repository.py`: существующий JSONL-репозиторий задач дня.
- `utils/blueprint_compat.py`: build-only aliases для прежнего `url_for`, без второго обработчика HTTP.
- `routes.parent_teacher` и `daily_tasks.formyla_bank`: aliases того же объекта модуля, включая приватные функции и кеш.
- `admin_metrics/`: чтение агрегатов, HTML и JSON; `scripts/export_admin_metrics.py`: выгрузка без импорта монолита.
- `app.py` уменьшился на 339 строк относительно cleanup.

## Фактически проверено

- AST-сравнение: тела всех 15 перенесённых функций совпали с cleanup.
- Файлы кабинета групп и репозитория банка совпали побайтово.
- Все 369 прежних сочетаний URL, endpoint и HTTP-методов присутствуют после переноса.
- Полный Flask app на отдельной SQLite: healthz/version/login 200; teacher/daily_tasks без авторизации 302.
- Метрики в полном app: аноним 302 на вход, обычный пользователь с завершённой анкетой 403, администратор 200 для HTML и JSON.
- Реальный Gunicorn на изолированной БД: healthz 200, `SECTION_STATS_V1: registered via gunicorn.conf.py` в журнале.
- Выбранный регрессионный набор: **187 passed, 2 subtests passed**. Включены новые проверки, cleanup, атлас, геометрия, подготовительные задачи, подписки и задачи дня.
- Расширенная проверка `test_task_bank.py`: 6 падений, воспроизведённых на исходной версии. Они не скрыты и не исправлялись изменением бизнес-логики рефакторинга.
- UI на синтетической БД: фильтр дней, раскрытие методики, JSON; desktop 1360px и mobile 390px, ширина документа на мобильном 390px.
- Read-only exporter запущен на локальной SQLite. Тесты проверяют отсутствие INSERT/UPDATE/DELETE/DDL у коллектора.

## Методика метрик

Дни по Москве; naive DateTime в существующих моделях трактуется как UTC.
Граничные полуночи проверены, включая старые SQLite-строки без микросекунд.

Регистрации: негостевые аккаунты с created_at до конца выбранного дня.
Учителя и Telegram-привязки: текущее состояние, не исторический снимок.
DAU/WAU: уникальные негостевые пользователи с положительным временем в
`site_time_sections`. Это только наблюдаемая активность, не все визиты.

Решения: сохранённые верные записи задач дня, банка, олимпиады, verified checks
и insight practice. Клиентский тренажёр отдельно, distinct(user_id, task_id).
История повторных проверок в некоторых таблицах перезаписывается; сумма по
источникам не обещает глобальной уникальности одной задачи.

Отсутствующая таблица/колонка даёт null с предупреждением, а не 0.
Если отсутствует один из пяти серверных источников, полный итог null.
Демо-Premium не доказывает оплату; подписчики TG-канала не выводятся из привязок.
PostgreSQL-коллектор начинает read-only транзакцию; запросы на PostgreSQL в
production пока не проверены. Нужна отдельная сверка и оценка времени запросов.

## Что ещё не принято

- Полный pytest исходного репозитория не зелёный. Ранее также воспроизводились
  8 других падений и зависания полного прогона. Поэтому критерий «весь pytest
  зелёный» для 0.6.1 не объявлен выполненным.
- Нет merge в main и нет production-деплоя этих изменений.
- Не проверено совпадение показателей с production-БД и покрытие heartbeat.
- Схема БД не менялась; сломанную legacy Alembic-цепочку не штамповали и не исправляли вслепую.
- `/admin/metrics` наследует существующие login/intake gates и политику
  `User.is_admin`; это не новый механизм управления административными правами.
- Строка baseline за 10.10.2026 должна быть выгружена после завершения этого
  дня, а не заполнена тестовыми числами 08.10.

## Воспроизведение

В новой копии без .env с production-ключами, Python 3.12.7:

```bash
export DATABASE_URL=sqlite:////absolute/path/to/isolated-test.db
export SECRET_KEY=local-tests-only
export ENABLE_SCHEDULER=0 OLYMPIAD_AUTOSEED=0
export VSOSH9_2027_FORCE_IMPORT=0 VSOSH10_2027_FORCE_IMPORT=0 ADAPTIVE_FORCE_IMPORT=0
python -m pytest tests/test_admin_metrics.py tests/test_domain_blueprints.py \
  tests/test_cleanup_integrity.py tests/test_methods_atlas_visuals.py \
  tests/test_engine.py tests/test_condition_coverage.py tests/test_prep_tasks.py \
  geoexact/test_coincident_alias.py tests/test_subscriptions.py \
  tests/test_bank_daily.py -q --timeout=10
```

Не направлять тесты на production: `tests/conftest.py` импортирует монолит,
а существующий монолит при старте выполняет создание таблиц и legacy-сидеры.
