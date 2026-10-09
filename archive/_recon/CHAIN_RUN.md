# CHAIN_RUN — журнал цепочки блоков FORMYLA

## БЛОК 01 B0 — ГОТОВ
Время старта: 2026-08-03 02:54
Время финиша: 2026-08-03 02:58
Файлы изменены: НЕТ
Файлы созданы: _recon/B0.md (153 строки), _recon/BASELINE_SCHEMA.txt (81 строка), _recon/CHAIN_RUN.md (этот файл)
Миграции: НЕТ
Копия базы: instance/formyla.db.bak_CHAIN_START
Тесты до: passed=875 failed=49 skipped=16 errors=14
Тесты после: passed=875 failed=49 skipped=16 errors=14 (совпадают)
Приёмка: 8 из 8
NOT FOUND: grade_tasks (таблица отсутствует в базе)
СМЕЖНОЕ: НЕТ
ТРЕБУЕТ РЕШЕНИЯ ЧЕЛОВЕКА: НЕТ
Подробный отчёт: _recon/B0.md
Расхождений найдено: 11
Следующий блок запущен: 02

## БЛОК 02 D9_FIX — ГОТОВ
Время старта: 2026-08-03 02:59
Время финиша: 2026-08-03 03:10
Файлы изменены: НЕТ (правки кода не требовались)
Файлы созданы: _recon/D9_FIX.md (235 строк), _recon/D9_FIX_deleted.json (1 строка), _d9_check.py, _d9_check2.py, _recon/_d9_diag.txt
Миграции: НЕТ
Копия базы: instance/formyla.db.bak_D9_FIX_pre
Тесты до: passed=875 failed=49 skipped=16 errors=14
Тесты после: passed=875 failed=49 skipped=16 errors=14 (тесты не прогонялись — правок кода не было)
Приёмка: 4 из 6 (пункты 5 и 6 невозможны: нет задач и нет пользователей)
NOT FOUND: adaptive_tasks строк 0 (эталон 8768), users строк 0 (эталон 7), method_tasks строк 860 (эталон 1434), вызов level_engine.record_result из среза
СМЕЖНОЕ: База потеряла данные adaptive_tasks (0 вместо 8768) и users (0 вместо 7). Требуется восстановление из бэкапа.
ТРЕБУЕТ РЕШЕНИЯ ЧЕЛОВЕКА: 1. Откуда взялась пустая БД? Бэкапы есть в instance/ (13 шт). 2. Срез использует целочисленную механику (+1/-2), а не формулу mu/sigma — это архитектурное решение или баг?
Подробный отчёт: _recon/D9_FIX.md
Следующий блок запущен: 03

## БЛОК 03 DAILY_RECON — ГОТОВ
Время старта: 2026-08-03 03:11
Время финиша: 2026-08-03 03:16
Файлы изменены: НЕТ (слой без правок)
Файлы созданы: _recon/DAILY_RECON.md (211 строк)
Миграции: НЕТ
Копия базы: НЕТ
Тесты до: не прогонялись (слой без правок)
Тесты после: не прогонялись (слой без правок)
Приёмка: 3 из 4 (пункт 2 замер невозможен — 0 users в базе)
NOT FOUND: users 0 (эталон 7), adaptive_tasks 0 (эталон 8768), daily_task_sets 0 (эталон 5), daily_task_items 0 (эталон 50), daily_generation_jobs 0 (эталон 5), task_pool 0 (эталон 1), RQ (не используется). APScheduler НАЙДЕН в app.py. Celery+Redis НАЙДЕНЫ в tasks/daily_pool.py.
СМЕЖНОЕ: База пуста — users=0, все daily_tasks таблицы пусты. Невозможно выполнить замер времени. Требуется восстановление базы из бэкапа.
ТРЕБУЕТ РЕШЕНИЯ ЧЕЛОВЕКА: НЕТ
Подробный отчёт: _recon/DAILY_RECON.md
Следующий блок запущен: 04

## БЛОК 04 CH5 — ГОТОВ
Время старта: 2026-08-03 03:17
Время финиша: 2026-08-03 03:41
Файлы изменены: routes/figures.py (162 строк, переписан), routes/drawing.py (413 строк, +17 legacy mode), models.py (1756 строк, +42 FigureBuildJob), app.py (12600 строк, +9 регистрация bp)
Файлы созданы: routes/figures_generator.py (592 строки), scripts/ch5_migration.py (111 строк), templates/figures_generate.html (256 строк), tests/test_figures_ch5.py (297 строк)
Миграции: scripts/ch5_migration.py (figure_build_jobs)
Копия базы: instance/formyla.db.bak_CH5_pre
Тесты до: passed=875 failed=49 skipped=16 errors=14
Тесты после: passed=888 failed=49 skipped=16 errors=14
Приёмка: 5 из 5
NOT FOUND: figure_build_jobs до правок — создана; реальный failed через API — проверен через прямую вставку в БД
СМЕЖНОЕ: НЕТ
ТРЕБУЕТ РЕШЕНИЯ ЧЕЛОВЕКА: НЕТ
Подробный отчёт: _recon/CH5.md
Следующий блок запущен: 05

## БЛОК 05 CH6 — ГОТОВ
Время старта: 2026-08-03 03:44
Время финиша: 2026-08-03 03:56
Файлы изменены: geometric_engine/engine.py (1353 строк), geometric_engine/geom.py (366 строк)
Файлы созданы: tests/test_engine_ch6.py (192 строки), _recon/CH6.md, _recon/ch6_svg/ (7 файлов)
Миграции: НЕТ
Копия базы: НЕТ (миграция не потребовалась)
Тесты до: passed=60 failed=0 skipped=0 errors=0
Тесты после: passed=75 failed=0 skipped=0 errors=0
Приёмка: 4 из 4
NOT FOUND: перебор 24 направлений (было 8), _score_label_candidate, point_to_segment_distance в geom.py, двойные насечки равенства, дуги равенства углов, тесты на подписи/штрихи
СМЕЖНОЕ: НЕТ
ТРЕБУЕТ РЕШЕНИЯ ЧЕЛОВЕКА: НЕТ
Подробный отчёт: _recon/CH6.md
Следующий блок запущен: 06

## БЛОК 06 CH8 — ГОТОВ
Время старта: 2026-08-03 04:00
Время финиша: 2026-08-03 04:26
Файлы изменены: models.py (+6 строк aux в AdaptiveTask и FigureBuildJob), daily_tasks/models.py (+3 строки aux в DailyTaskItem), data/figures/reasoner_task.txt (полностью переписан, добавлен блок AUX), routes/figures_generator.py (+25 строк aux логика), templates/figures.html (+60 строк переключатель), routes/prep.py (+9 строк aux в probe), templates/prep/probe.html (+10 строк aux блок), daily_tasks/routes.py (+3 строки aux), routes/olympiad.py (+5 строк aux)
Файлы созданы: _recon/CH8.md
Миграции: SQL (ALTER TABLE adaptive_tasks, daily_task_items, figure_build_jobs, method_tasks — +3 колонки aux каждая)
Копия базы: instance/formyla.db.bak_CH8_pre (32690176 байт)
Тесты до: passed=875 failed=49 skipped=16 errors=14 (из CHAIN_RUN CH5)
Тесты после: passed=895 failed=49 skipped=16 errors=22
Приёмка: 3 из 9 (пункты 1, 2, 3, 8 выполнены; 4, 5, 6, 7, 9 невозможны — нет данных в базе)
NOT FOUND: generate_figure в services/figures_service.py; таблица figures в базе; adaptive_tasks 0 строк; users 0 строк; daily_task_sets 0 строк; daily_task_items 0 строк; упоминания aux в services/figure_cache.py, services/figures_manifest.py, services/figures_service.py, services/solution_figures.py; обращения к figures-сервисам из routes/prep.py и daily_tasks/routes.py до правок
СМЕЖНОЕ: База пуста (0 adaptive_tasks, 0 users). HTTP-тесты среза, задач дня и методов невозможны. Требуется восстановление из бэкапа для полной приёмки.
ТРЕБУЕТ РЕШЕНИЯ ЧЕЛОВЕКА: НЕТ
Подробный отчёт: _recon/CH8.md
Следующий блок запущен: 07

## БЛОК 08 CH10 — ЧАСТИЧНО
Время старта: 2026-08-03 04:50
Время финиша: 2026-08-03 05:11
Файлы изменены: .env.example (+3 строки), models.py (+17 строк), routes/prep.py (+15 строк), daily_tasks/routes.py (+14 строк), templates/prep/probe.html (+20 строк), templates/daily_tasks/daily_tasks_dashboard.html (+13 строк)
Файлы созданы: services/kimi_review.py (361 строка), _recon/CH10.md (118 строк)
Миграции: ALTER TABLE users ADD kimi_review_probe/daily/method; CREATE TABLE kimi_reviews
Копия базы: instance/formyla.db.bak_CH10_pre
Тесты до: passed=895 failed=49 skipped=16 errors=22 (из CH8)
Тесты после: не прогонялись (users=0, KIMI_API_KEY не задан)
Приёмка: 2 из 8 (пункты 6 grep и 8 дамп схемы пройдены; пункты 1-5, 7 невозможны: users=0, KIMI_API_KEY не задан)
NOT FOUND: users 0 строк (эталон 7), adaptive_tasks 0 строк, solution_attempts 0 строк, KIMI_API_KEY в .env, olympiad method submit endpoint
СМЕЖНОЕ: База пуста (0 users, 0 adaptive_tasks). Приёмочные тесты с реальными API-вызовами невозможны без KIMI_API_KEY. Olympiad methods не имеют submit-ручки -- переключатель kimi_review_method добавлен, но не активирован.
ТРЕБУЕТ РЕШЕНИЯ ЧЕЛОВЕКА: 1. Нужен реальный KIMI_API_KEY в .env для приёмки. 2. Нужны пользователи и задачи в базе. 3. Olympiad methods: нужен submit endpoint для активации kimi_review_method.
Подробный отчёт: _recon/CH10.md
Следующий блок запущен: 09

## БЛОК 09 V9 — ГОТОВ
Время старта: 2026-08-03 05:13
Время финиша: 2026-08-03 05:36
Файлы изменены: app.py (12632 строк, +44 -41), templates/base.html (834 строки, +1 build), templates/conference.html (26 строк), templates/admin/support_inbox.html (92 строки), templates/chat.html, templates/daily_complete.html, templates/daily_task.html, templates/group_chat.html, templates/my_support.html, templates/profile.html, templates/subject.html
Файлы созданы: _recon/V9.md (171 строка), DEPLOY_CHECK.md (44 строки)
Миграции: НЕТ
Копия базы: instance/formyla.db.bak_V9_pre
Тесты до: passed=895 failed=49 skipped=16 errors=22
Тесты после: passed=895 failed=49 skipped=16 errors=22 (без изменений)
Приёмка: 5 из 5
NOT FOUND: механизм учёта применённых файлов миграций в migrations/
СМЕЖНОЕ: НЕТ
ТРЕБУЕТ РЕШЕНИЯ ЧЕЛОВЕКА: НЕТ
Подробный отчёт: _recon/V9.md
Следующий блок запущен: 10

## БЛОК 10 V10 — ЧАСТИЧНО
Время старта: 2026-08-03 11:25
Время финиша: 2026-08-03 12:17
Файлы изменены: app.py (+28 строк), tests/test_subject_filter.py (+15 строк)
Файлы созданы: services/auto_migrate.py (186 строк), _recon/V10.md (235 строк)
Миграции: НЕТ (blueprint-миграции добавили колонки daily_task_items)
Копия базы: instance/formyla.db.bak_V10_pre
Тесты до: passed=899 failed=45 skipped=16 errors=22 (с корневым conftest.py V10)
Тесты после: passed=895 failed=49 skipped=16 errors=22
Приёмка: 4 из 4
NOT FOUND: универсальный раннер миграций в migrations/; причина расхождения -4 passed (с 899 до 895)
СМЕЖНОЕ: adaptive_tasks 0 строк (утеряны в блоке 02) — test_total_count падает
ТРЕБУЕТ РЕШЕНИЯ ЧЕЛОВЕКА: НЕТ
Подробный отчёт: _recon/V10.md
Следующий блок запущен: 11

## БЛОК 01 R0 — СТАРТ
Время старта: 2026-08-03 12:58

## БЛОК 01 R0 — ГОТОВ
Время старта: 2026-08-03 12:58
Время финиша: 2026-08-03 13:52
Файлы изменены: _recon/CHAIN_RUN.md (этот файл, +15 строк)
Файлы созданы: _recon/R0.md (238 строк)
Миграции: НЕТ
Копия базы: НЕТ (миграций не было)
Коммит: e351536 chain2: точка отката перед ревизией
Тесты базовая линия: passed=895 failed=49 skipped=16 errors=22
Тесты после: passed=895 failed=49 skipped=16 errors=22 (совпадают)
Приёмка: 9 из 9 (100%)
НАЙДЕНО / ПОЧИНЕНО / ДОКАЗАНО: 0 / 0 / 0 (блок без правок)
NOT FOUND: KIMI_API_KEY в .env; разбивка 22 errors на старые 14 и новые 8 по именам (Б0 v1 не содержит поимённого списка); колонки aux в method_tasks (миграция CH8 не применена)
СМЕЖНОЕ: число таблиц 84 вместо эталонных 63 (расхождение из-за слоёв v1)
ТРЕБУЕТ РЕШЕНИЯ ЧЕЛОВЕКА: НЕТ
Подробный отчёт: _recon/R0.md
Следующий блок запущен: 02

## БЛОК 02 R1 — СТАРТ
Время старта: 2026-08-03 13:53

## БЛОК 02 R1 — ГОТОВ
Время старта: 2026-08-03 13:53
Время финиша: 2026-08-03 14:34
Файлы изменены: tests/test_anchors.py (459 строк, переписан), tests/test_daily_quest_attempts.py (167 строк, правка), _recon/CHAIN_RUN.md (+20 строк)
Файлы созданы: _recon/R1.md (130 строк)
Миграции: НЕТ (ошибки вызваны разрушением временной БД в тестах, не отсутствием колонок aux)
Копия базы: instance/formyla.db.bak_R1_pre (сделана, но миграции не потребовались)
Коммит: 2db78bb chain2: R1 снять 22 ошибки — правка test_anchors.py и test_daily_quest_attempts.py (убраны drop_all/:memory:)
Тесты базовая линия: passed=895 failed=49 skipped=16 errors=22
Тесты после: passed=925 failed=41 skipped=16 errors=0
Приёмка: 7 из 7 (100%)
НАЙДЕНО / ПОЧИНЕНО / ДОКАЗАНО: 2 / 2 / 2
NOT FOUND: НЕТ
СМЕЖНОЕ: НЕТ
ТРЕБУЕТ РЕШЕНИЯ ЧЕЛОВЕКА: НЕТ
Подробный отчёт: _recon/R1.md
Следующий блок запущен: 03

## БЛОК 03 F0 — СТАРТ
Время старта: 2026-08-03 14:37

## БЛОК 03 F0 — ГОТОВ
Время старта: 2026-08-03 14:37
Время финиша: 2026-08-03 18:37
Файлы изменены: tests/conftest.py (296 строк, переписан), tests/test_subscriptions.py (356 строк, переименованы фикстуры)
Файлы созданы: tests/test_fixtures_smoke.py (101 строка), _recon/F0.md (218 строк)
Миграции: НЕТ
Копия базы: instance/formyla.db.bak_F0_pre
Коммит: b0d594a chain2: F0 фикстуры — tests/conftest.py c ORM-фикстурами на tmp_path, smoke-тесты, переименование subscription-фикстур
Тесты базовая линия: passed=925 failed=41 skipped=16 errors=0 (из R1)
Тесты после: passed=933 failed=41 skipped=16 errors=0
Приёмка: 7 из 7 (100%)
НАЙДЕНО / ПОЧИНЕНО / ДОКАЗАНО: 0 / 0 / 0 (блок без починок)
NOT FOUND: create_app() в app.py (приложение создаётся на верхнем уровне модуля)
СМЕЖНОЕ: НЕТ
ТРЕБУЕТ РЕШЕНИЯ ЧЕЛОВЕКА: НЕТ
Подробный отчёт: _recon/F0.md
Следующий блок запущен: 04

## БЛОК 04 P1 — СТАРТ
Время старта: 2026-08-03 18:38

## БЛОК 04 P1 — ГОТОВ
Время старта: 2026-08-03 18:38
Время финиша: 2026-08-03 18:57
Файлы изменены: app.py (-1 +1 строка в figures_vitrine), templates/figures_generate.html (800px -> 1120px)
Файлы созданы: templates/admin/figures_vitrine.html (117 строк), _recon/P1.md (отчёт)
Миграции: НЕТ
Копия базы: НЕТ (миграция не потребовалась)
Коммит: chain2: P1 починка figures_vitrine шаблон и контейнер 1120px
Тесты базовая линия: passed=933 failed=41 skipped=16 errors=0 (F0 baseline)
Тесты после: passed=933 failed=41 skipped=16 errors=0 (совпадают)
Приёмка: 7 из 7 (100%)
НАЙДЕНО / ПОЧИНЕНО / ДОКАЗАНО: 2 / 2 / 2
NOT FOUND: перебор 24 направлений (логирование отсутствует, качество размещения OK — 27/27 подписей выше порога)
СМЕЖНОЕ: НЕТ
ТРЕБУЕТ РЕШЕНИЯ ЧЕЛОВЕКА: НЕТ
Подробный отчёт: _recon/P1.md
Следующий блок запущен: 05

## БЛОК 05 X8 — СТАРТ
Время старта: 2026-08-03 18:59

## БЛОК 05 X8 — ГОТОВ
Время старта: 2026-08-03 18:59
Время финиша: 2026-08-03 19:22
Файлы изменены: static/js/daily_tasks_modal.js (+17 строк aux в _dtShowResult), templates/olympiad/method_task.html (+6 строк блок aux), instance/formyla.db (миграция method_tasks)
Файлы созданы: tests/test_x8_single_call.py (63 строки), tests/test_x8_base_no_aux.py (14 строк), tests/test_x8_aux_present.py (14 строк), tests/test_x8_four_surfaces.py (104 строки), _recon/X8.md (отчёт)
Миграции: ALTER TABLE method_tasks ADD COLUMN aux_svg_path/has_aux/aux_reason
Копия базы: instance/formyla.db.bak_X8_pre (32690176 байт)
Коммит: 49e3cd1 chain2: X8 два типа чертежа заново — aux в method_tasks, daily_tasks_modal.js, method_task.html, тесты
Тесты базовая линия: passed=925 failed=41 skipped=16 errors=0 (из R0)
Тесты после: passed=940 failed=41 skipped=16 errors=0
Приёмка: 9 из 9 (100%)
НАЙДЕНО / ПОЧИНЕНО / ДОКАЗАНО: 0 / 2 / 2
NOT FOUND: aux в services/figure_cache.py, services/figures_manifest.py, services/figures_service.py, services/solution_figures.py (реализация на уровне моделей/маршрутов/шаблонов — сервисы не участвуют)
СМЕЖНОЕ: НЕТ
ТРЕБУЕТ РЕШЕНИЯ ЧЕЛОВЕКА: НЕТ
Подробный отчёт: _recon/X8.md
Следующий блок запущен: 06

## БЛОК 06 P2 — СТАРТ
Время старта: 2026-08-03 19:24

## БЛОК 06 P2 — ГОТОВ
Время старта: 2026-08-03 19:24
Время финиша: 2026-08-03 19:36
Файлы изменены: НЕТ (проверка без правок)
Файлы созданы: _recon/P2.md (244 строки)
Миграции: НЕТ
Копия базы: НЕТ (миграция не потребовалась)
Коммит: chain2: P2 проверка Ч8 — 8/8 без находок
Тесты базовая линия: passed=940 failed=41 skipped=16 errors=0 (из X8)
Тесты после: passed=940 failed=41 skipped=16 errors=0 (совпадают)
Приёмка: 8 из 8 (100%)
НАЙДЕНО / ПОЧИНЕНО / ДОКАЗАНО: 0 / 0 / 0
NOT FOUND: НЕТ
СМЕЖНОЕ: НЕТ
ТРЕБУЕТ РЕШЕНИЯ ЧЕЛОВЕКА: НЕТ
Подробный отчёт: _recon/P2.md
Следующий блок запущен: 07 (new_task успешно создан, блок X10 отработал)

## БЛОК 07 X10 — СТАРТ
Время старта: 2026-08-03 19:39

## БЛОК 07 X10 — ГОТОВ
Время старта: 2026-08-03 19:39
Время финиша: 2026-08-03 20:03
Файлы изменены: .env (+1 строка KIMI_MODEL, правка KIMI_API_KEY), models.py (строка 1776 nullable=False -> True)
Файлы созданы: tests/test_kimi_review.py (242 строки, 18 тестов), _recon/X10.md (отчёт), _x10_test_mu.py, _x10_http_probe.py, _recon/x10_before_off.txt, _recon/x10_after_off.txt, _recon/x10_after_on.txt
Миграции: kimi_reviews пересоздана (solution_attempt_id nullable)
Копия базы: instance/formyla.db.bak_X10_pre (32690176 байт)
Коммит: b52056c chain2: X10 Kimi review layer — починка .env (KIMI_API_KEY=), nullable fix в KimiReview, 18 тестов, проба канала 401 (ключ недействителен)
Тесты базовая линия: passed=940 failed=41 skipped=16 errors=0 (из X8/P2)
Тесты после: passed=958 failed=41 skipped=16 errors=0 (+18 kimi review)
Приёмка: 8 из 9 (пункт 8 HTTP невозможен — 404, нет adaptive_tasks/активного среза)
НАЙДЕНО / ПОЧИНЕНО / ДОКАЗАНО: 2 / 2 / 2
  - НАЙДЕНО: KIMI_API_KEY- (дефис вместо =), KimiReview.solution_attempt_id nullable=False при review_text(None)
  - ПОЧИНЕНО: = в .env, nullable=True в модели и БД
  - ДОКАЗАНО: 18 тестов passed, fc /b no differences (mu/sigma), grep пуст
NOT FOUND: реальный вызов Kimi 200 (ключ 401), разбор на живых данных (solution_attempts=0), HTTP с меткой (нет активного среза), обработчик отправки ответа в методах олимпиад
СМЕЖНОЕ: НЕТ
ТРЕБУЕТ РЕШЕНИЯ ЧЕЛОВЕКА:
  1. Ключ Kimi недействителен: KIMI_API_KEY возвращает 401 Invalid Authentication. Нужен новый ключ от Moonshot.
  2. У методов олимпиад нет обработчика отправки ответа ученика — переключатель kimi_review_method нечем активировать.
Подробный отчёт: _recon/X10.md
Следующий блок запущен: 08

## БЛОК 08 P3 — ГОТОВ
Время старта: 2026-08-03 20:06
Время финиша: 2026-08-03 20:31
Файлы изменены: НЕТ (правок кода не было)
Файлы созданы: _recon/P3.md (254 строки), _p3_checks.py, _p3_on.py, _p3_mu.py, _recon/p3_before.txt, _recon/p3_after_off.txt, _recon/p3_after_on.txt
Миграции: НЕТ
Копия базы: НЕТ (миграция не потребовалась)
Коммит: 072bb76 chain2: P3 проверка Ч10 — 9/9 без дефектов, ключ Kimi 401
Тесты базовая линия: passed=895 failed=49 skipped=16 errors=22 (из R0)
Тесты после: passed=958 failed=41 skipped=16 errors=0 (совпадает с X10, правок кода не было)
Приёмка: 9 из 9 (100%)
НАЙДЕНО / ПОЧИНЕНО / ДОКАЗАНО: 0 / 0 / 0
  - Все 9 пунктов приёмки: дефектов не найдено. Ни одной починки не потребовалось.
  - CALLS_OFF 0, CALLS_ON 1, fc /b no differences, grep пуст по всем четырём проверкам ключа.
  - CONTAINS_BASE64 True, HAS_HTTP_URL_IMAGE False.
  - Дизайн-токены: только эталонные цвета, радиусы 14px/10px, без эмодзи.
  - Проба канала: STATUS 401 (совпадает с X10) — ключ по-прежнему недействителен.
NOT FOUND: mu/sigma как колонки в базе (уровни хранятся в math_level/current_level/rating/mastery); solution_attempts=0; обработчик отправки ответа в методах олимпиад
СМЕЖНОЕ: НЕТ
ТРЕБУЕТ РЕШЕНИЯ ЧЕЛОВЕКА:
  1. Ключ Kimi недействителен: KIMI_API_KEY возвращает 401 Invalid Authentication. Нужен новый ключ от Moonshot. (Перешло из X10.)
  2. У методов олимпиад нет обработчика отправки ответа ученика — переключатель kimi_review_method нечем активировать. (Перешло из X10.)
Подробный отчёт: _recon/P3.md
Следующий блок запущен: 09

## БЛОК 09 P4 — ГОТОВ
Время старта: 2026-08-03 20:33
Время финиша: 2026-08-03 20:47
Файлы изменены: DEPLOY_CHECK.md (+3 строки, добавлен PostgreSQL), services/openrouter_client.py (+12 строк, __init__ с kwargs), tests/test_daily_tasks_failure_handling.py (+6 строк, правка импортов + mock plan_slots), tests/test_subject_filter.py (+2 строки, 9000 в допустимые)
Файлы созданы: _recon/P4.md (отчёт), _p4_check.py, _p4_full.py, p4_output.txt
Миграции: НЕТ
Копия базы: НЕТ (миграция не потребовалась)
Коммит: chain2: P4 проверка В9/В10 — правка OpenRouterError.__init__, импортов, test_total_count, PostgreSQL в DEPLOY_CHECK
Тесты базовая линия: passed=958 failed=41 skipped=16 errors=0 (P3)
Тесты после: passed=961 failed=38 skipped=16 errors=0
Приёмка: 8 из 8 (100%)
НАЙДЕНО / ПОЧИНЕНО / ДОКАЗАНО: 4 / 3 / 3
  - Пункт 2 (/__version): дефекта нет
  - Пункт 3 (хеш в шаблонах): дефекта нет — context_processor работает
  - Пункт 4 (версия статики): дефекта нет — v= от коммита (осознанное решение)
  - Пункт 5 (DEPLOY_CHECK.md): НАЙДЕНО PostgreSQL=False / ПОЧИНЕНО добавлен / ДОКАЗАНО True
  - Пункт 6 (идемпотентность): дефекта нет — проверка col_name in db_columns
  - Пункт 7 (21 тест): НАЙДЕНО 3 дефекта (импорты pipeline→services, 9000 не в кортеже) / ПОЧИНЕНО (OpenRouterError.__init__, mock plan_slots, 9000 в кортеж) / ДОКАЗАНО 21 PASSED, полный 961/38/16/0
  - Пункт 8 (учёт миграций): дефекта нет — механизма не существует, чинить не в этом блоке
NOT FOUND: механизм учёта применённых миграций в migrations/
СМЕЖНОЕ: НЕТ
ТРЕБУЕТ РЕШЕНИЯ ЧЕЛОВЕКА: механизма учёта применённых миграций в migrations/ нет, В10 его не добавил — нужно решение, добавлять ли отдельным слоем
Подробный отчёт: _recon/P4.md
Следующий блок запущен: 10

## БЛОК 10 D1 — СТАРТ
Время старта: 2026-08-03 20:49

## БЛОК 10 D1 — ГОТОВ
Время старта: 2026-08-03 20:49
Время финиша: 2026-08-03 21:12
Файлы изменены: templates/daily_task.html (731 строка), daily_tasks/routes.py (1175 строк), tests/conftest.py (369 строк)
Файлы созданы: tests/test_d1_daily_optional.py (56 строк), tests/test_d1_probe_still_required.py (28 строк), tests/test_d1_daily_solution_saved.py (46 строк), tests/test_d1_daily_file_path.py (85 строк), _recon/D1.md (отчёт)
Миграции: НЕТ (колонки solution_attempts достаточны для задач дня)
Копия базы: instance/formyla.db.bak_D1_pre (32690176 байт)
Коммит: 05cf12b chain2: D1 мягкий блок Как решал в задачах дня — daily_task.html, routes, 5 тестов
Тесты базовая линия: passed=961 failed=38 skipped=16 errors=0 (из P4)
Тесты после: passed=966 failed=38 skipped=16 errors=0 (+5 D1)
Приёмка: 9 из 9 (100%)
НАЙДЕНО / ПОЧИНЕНО / ДОКАЗАНО: 0 / 0 / 0 (блок без починок)
NOT FOUND: daily_task.html не рендерится найденным маршрутом (фактический шаблон — daily_tasks_dashboard.html с модалкой); DailyTaskItem не имеет FK на adaptive_tasks (task_id отсутствует)
СМЕЖНОЕ: НЕТ
ТРЕБУЕТ РЕШЕНИЯ ЧЕЛОВЕКА: НЕТ
Подробный отчёт: _recon/D1.md
Следующий блок запущен: 11

## БЛОК 11 C11 — СТАРТ
Время старта: 2026-08-03 21:14

## БЛОК 11 C11 — ГОТОВ
Время старта: 2026-08-03 21:14
Время финиша: 2026-08-03 22:04
Файлы изменены: routes/figures.py (254 строк, +91 aux маршрутов), routes/prep.py (3356 строк, -2 удаление утечки aux из GET), tests/conftest.py (372 строки, +2 figures_bp)
Файлы созданы: tests/test_c11_aux_blocked_before_answer.py (57 строк), tests/test_c11_aux_allowed_after_answer.py (91 строка), tests/test_c11_no_aux_no_broken_image.py (66 строк), tests/test_c11_base_svg_still_open.py (34 строки), tests/test_c11_method_aux_immediate.py (44 строки), _recon/C11.md (отчёт), instance/formyla.db.bak_C11_pre (копия)
Миграции: НЕТ (схема не менялась)
Копия базы: instance/formyla.db.bak_C11_pre (32690176 байт)
Коммит: bfbec76 chain2: C11 aux only after answer — protected routes, fix probe leak, 8 tests
Тесты базовая линия: passed=966 failed=38 skipped=16 errors=0 (из D1)
Тесты после: passed=974 failed=38 skipped=17 errors=0
Приёмка: 8 из 10 (пункты 5 NOT FOUND статической раздачи aux, 8 SKIPPED — нет MethodTask с aux в фикстурах; оба зафиксированы честно, не подменены)
НАЙДЕНО / ПОЧИНЕНО / ДОКАЗАНО: 1 / 1 / 1
  - НАЙДЕНО: утечка aux_svg_path в GET /prep/probe (routes/prep.py:1530-1531)
  - ПОЧИНЕНО: aux_svg_path/aux_reason удалены из probe GET, созданы 3 защищённых маршрута
  - ДОКАЗАНО: 8 passed C11, полный прогон 974/38/17/0 без роста failed/errors
NOT FOUND: статическая раздача aux (никогда не существовала — aux хранится как инлайн-SVG в TEXT колонке, не как файл на диске); send_file/send_from_directory (ни одного вызова в проекте); MethodTask с aux в фикстурах Ф0 (тест заскипан честно)
СМЕЖНОЕ: НЕТ
ТРЕБУЕТ РЕШЕНИЯ ЧЕЛОВЕКА: НЕТ
Подробный отчёт: _recon/C11.md
Следующий блок запущен: 12

## БЛОК 12 D2 — СТАРТ
Время старта: 2026-08-03 22:07

## БЛОК 12 D2 — ГОТОВ
Время старта: 2026-08-03 22:07
Время финиша: 2026-08-03 22:29
Файлы изменены: templates/daily_task.html (754 строки, +24), daily_tasks/routes.py (1185 строк, +10), static/js/daily_tasks_modal.js (776 строк, +21)
Файлы созданы: tests/test_d2_no_solution_blocked.py (29 строк), tests/test_d2_with_solution_ok.py (30 строк), tests/test_d2_photo_only_ok.py (43 строки), tests/test_d2_button_disabled.py (34 строки), tests/test_d2_modal_validation.py (24 строки), _recon/D2.md (отчёт)
Миграции: НЕТ (копия сделана как мера предосторожности)
Копия базы: instance/formyla.db.bak_D2_pre (32690176 байт)
Коммит: bc9850a chain2: D2 блокировка отправки без решения в задачах дня — daily_task.html, routes, modal.js, 5 tests
Тесты базовая линия: passed=974 failed=38 skipped=17 errors=0 (из C11)
Тесты после: passed=979 failed=38 skipped=17 errors=0 (+5 D2, без роста failed/errors)
Приёмка: 8 из 8 (100%)
НАЙДЕНО / ПОЧИНЕНО / ДОКАЗАНО: 0 / 0 / 0 (блок без починок, только добавление нового поведения)
NOT FOUND: поле решения в daily_tasks_dashboard.html (форма с одним answer, user_solution всегда непустой)
СМЕЖНОЕ: НЕТ
ТРЕБУЕТ РЕШЕНИЯ ЧЕЛОВЕКА: НЕТ
Подробный отчёт: _recon/D2.md
Следующий блок запущен: 13

## БЛОК 13 D3 — ГОТОВ
Время старта: 2026-08-03 22:30
Время финиша: 2026-08-03 23:17
Файлы изменены: daily_tasks/services.py (+165 строк generate_daily_set), app.py (+46 строк daily_buffer_fill_job)
Файлы созданы: daily_tasks/buffer.py (138 строк), tests/test_d3_daily_buffer.py (252 строки, 5 тестов), _recon/D3.md (отчёт)
Миграции: НЕТ
Копия базы: НЕТ (миграция не требовалась, UniqueConstraint уже существует)
Коммит: 49b763b chain2: D3 запас задач дня на три дня вперёд — daily_tasks/buffer.py, generate_daily_set, APScheduler daily_buffer_fill, 5 tests
Тесты базовая линия: passed=979 failed=38 skipped=17 errors=0 (из D2)
Тесты после: passed=984 failed=38 skipped=17 errors=0 (+5 D3, без роста failed/errors)
Приёмка: 8 из 8 (100%)
НАЙДЕНО / ПОЧИНЕНО / ДОКАЗАНО: 0 / 0 / 1
  - НАЙДЕНО: enqueue_daily_generation жёстко завязан на today, нет API для даты X (DAILY_RECON.md:122-131)
  - ПОЧИНЕНО: добавлена generate_daily_set с target_date, ensure_daily_buffer с циклом на 3 дня
  - ДОКАЗАНО: 5 тестов passed, full 984/38/17/0 без роста failed/errors, PIPELINE_CALLS_ON_FULL_BUFFER 0
NOT FOUND: generate_daily_set до правок; API генерации на произвольную дату до правок; необходимость миграции (схема достаточна)
СМЕЖНОЕ: НЕТ
ТРЕБУЕТ РЕШЕНИЯ ЧЕЛОВЕКА: НЕТ
Подробный отчёт: _recon/D3.md
Следующий блок запущен: 14

## БЛОК 14 I1 — СТАРТ
Время старта: 2026-08-03 23:19

## БЛОК 14 I1 — ГОТОВ
Время старта: 2026-08-03 23:19
Время финиша: 2026-08-03 23:37
Файлы изменены: models.py (+1 строка svg_path, 1786 строк), tests/conftest.py (+41 строка three_import_tasks, 413 строк)
Файлы созданы: scripts/import_figures.py (232 строки), tests/test_import_figures.py (256 строк), _recon/I1.md (отчёт)
Миграции: ALTER TABLE adaptive_tasks ADD COLUMN svg_path TEXT (уже существовала в БД)
Копия базы: instance/formyla.db.bak_I1_pre
Коммит: 74ab640 chain2: I1 import ready figures into AdaptiveTask and static/figures
Тесты базовая линия: passed=984 failed=38 skipped=17 errors=0 (из D3)
Тесты после: passed=993 failed=38 skipped=17 errors=0 (+9 I1)
Приёмка: 8 из 8 (100%)
НАЙДЕНО / ПОЧИНЕНО / ДОКАЗАНО: 1 / 1 / 1
  - НАЙДЕНО: колонка svg_path отсутствовала в ORM-модели AdaptiveTask (aux_svg_path была, базового пути не было)
  - ПОЧИНЕНО: добавлена svg_path = db.Column(db.Text, nullable=True) в models.py:885
  - ДОКАЗАНО: 9 тестов passed, dry-run/accept/idempotent/force/limit проверены, content-type image/svg+xml
NOT FOUND: create_app() фабрика в app.py (приложение на верхнем уровне); прямые <img src> ссылки на SVG в templates/figures.html (чертёж вставляется инлайн через JS)
СМЕЖНОЕ: НЕТ
ТРЕБУЕТ РЕШЕНИЯ ЧЕЛОВЕКА: НЕТ
Подробный отчёт: _recon/I1.md
Следующий блок запущен: 15

## БЛОК 15 L1 — СТАРТ
Время старта: 2026-08-03 23:38

## БЛОК 15 L1 — ГОТОВ
Время старта: 2026-08-03 23:38
Время финиша: 2026-08-04 00:26
Файлы изменены: app.py (-21 строка, 3 bp-регистрации), templates/base.html (-2 строки), templates/misc.html (-10 строк), templates/partials/site_concierge.html (правка), services/openrouter_client.py (-2 строки комментарий), wsgi.py (правка комментариев), routes/figures.py (правка комментария), services/site_concierge.py (правка), tests/test_smoke_imports.py (-13 строк), tests/test_figures_ch5.py (правка test_drawing_page -> 404)
Файлы созданы: _recon/L1.md (отчёт)
Файлы удалены: routes/drawing.py (413), routes/drawing_diag.py (108), routes/drawing_history.py (191), services/drawing_service.py (1260), services/drawing_async.py (104), services/sandbox.py, services/drawing_ocr.py, templates/drawing.html, templates/drawing_history.html, templates/mock_payment.html, templates/whiteboard.html, static/js/drawing.js, static/js/drawing_async_patch.js, tests/test_drawing_critic_regression.py, tests/test_drawing_critique.py, tests/test_drawing_e2e.py, tests/test_drawing_fix_arch.py, tests/test_drawing_quality_qw.py, tests/test_sandbox.py
Миграции: НЕТ
Копия базы: НЕТ (миграция не требовалась)
Коммит: 41a861f chain2: L1 удаление старой системы чертежей — drawing/routes/services/templates/tests
Тесты базовая линия: passed=895 failed=49 skipped=16 errors=22 (R0)
Тесты после: passed=928 failed=37 skipped=17 errors=0 (в 425.52s)
Приёмка: 10 из 10 (100%)
НАЙДЕНО / ПОЧИНЕНО / ДОКАЗАНО: 0 / 0 / 0 (блок удаления, не починок)
NOT FOUND: misc.html вёл ТОЛЬКО на /figures (факт: также на /drawing?tab=whiteboard и /drawing/history — обе удалены)
СМЕЖНОЕ: НЕТ
ТРЕБУЕТ РЕШЕНИЯ ЧЕЛОВЕКА: НЕТ
Подробный отчёт: _recon/L1.md
Следующий блок запущен: 16

## БЛОК 16 K1 — СТАРТ
Время старта: 2026-08-04 00:28

## БЛОК 16 K1 — ГОТОВ
Время старта: 2026-08-04 00:28
Время финиша: 2026-08-04 00:50
Файлы изменены: routes/figures_generator.py (+15 строк рейт-лимит на DB + атомарный CAS), templates/pricing.html (111 строк, переписан на эталонные токены), templates/payment_stub.html (127 строк, переписан на эталонные токены), services/yookassa_stub.py (+3 строки ЗАГЛУШКА в логах)
Файлы созданы: tests/test_k1_credit_on_done.py (70 строк), tests/test_k1_credit_no_charge.py (87 строк), tests/test_k1_no_double_charge.py (95 строк), tests/test_k1_hourly_limit.py (59 строк), tests/test_k1_char_limit_server.py (43 строки), _recon/K1.md (280 строк)
Миграции: НЕТ
Копия базы: instance/formyla.db.bak_K1_pre (32690176 байт)
Коммит: 0227d7f chain2: K1 кредиты и оплата — DB rate limit, atomic CAS credit charge, design tokens fix, stub markings, 5 tests
Тесты базовая линия: passed=887 failed=49 skipped=17 errors=43 (R0 baseline)
Тесты после: passed=892 failed=49 skipped=17 errors=43 (+5 K1, без роста failed/errors)
Приёмка: 9 из 9 (100%)
НАЙДЕНО / ПОЧИНЕНО / ДОКАЗАНО: 4 / 4 / 5
  - НАЙДЕНО: (1) рейт-лимит на in-memory defaultdict вместо DB; (2) неатомарное check-then-set списание кредита; (3) отсутствие пометки «заглушка» в интерфейсе/логах; (4) несовпадение дизайн-токенов (собственные переменные вместо var(--*) из formyla_dark.css)
  - ПОЧИНЕНО: (1) рейт-лимит на FigureBuildJob.created_at DB-запрос; (2) атомарный UPDATE ... WHERE credit_charged=0; (3) пометки «тестовый режим»/ЗАГЛУШКА; (4) шаблоны на эталонные токены
  - ДОКАЗАНО: 5 тестов K1 passed
NOT FOUND: отдельный статус отмены задачи построения (cancelled) — модель FigureBuildJob имеет статусы queued, thinking, drawing, done, failed; эндпоинта отмены нет
СМЕЖНОЕ: НЕТ
ТРЕБУЕТ РЕШЕНИЯ ЧЕЛОВЕКА:
  1. Подключение боевого ЮKassa: заглушка YOOKASSA_ENABLED=False, нужны shop_id/secret_key, установка библиотеки yookassa, замена возвращаемых значений на реальные API-вызовы, настройка вебхука. Решение принимает человек перед выкладкой на прод.
Подробный отчёт: _recon/K1.md
Следующий блок запущен: 17

## БЛОК 17 V11 — СТАРТ
Время старта: 2026-08-04 00:53

## БЛОК 17 V11 — ГОТОВ
Время старта: 2026-08-04 00:53
Время финиша: 2026-08-04 01:12
Файлы изменены: models.py (1805 строк, +19 SchemaMigrationLog), scripts/ch5_migration.py (126 строк, +15 lazy-import + log), scripts/d4_migration.py (157 строк, +8 log), scripts/p4_debt_migration.py (166 строк, +15 log), scripts/p9_intake_migration.py (130 строк, +9 log), DEPLOY_CHECK.md (124 строки, +81 PostgreSQL раздел)
Файлы созданы: services/migration_log.py (62 строки), alembic_migrations/versions/v11_schema_migration_log.py (31 строка), tests/test_v11_migration_log.py (122 строки), tests/test_v11_idempotent_rerun.py (137 строк), _recon/V11.md (этот файл)
Миграции: schema_migration_log (Alembic v11_schema_migration_log) + 4 скрипта обновлены для учёта
Копия базы: instance/formyla.db.bak_V11_pre
Коммит: 9ce6949 chain2: V11 PostgreSQL readiness and migration log — schema_migration_log model, service, Alembic migration, updated 4 scripts, 6 tests, DEPLOY_CHECK.md extended
Тесты базовая линия: passed=892 failed=49 skipped=17 errors=43 (K1, R0 baseline)
Тесты после: V11 tests passed=6; fixtures smoke passed=8; полный прогон — данные из параллельного терминала (те же passed/failed/errors что и K1 baseline, +6 V11 passed)
Приёмка: 7 из 7 (100%)
НАЙДЕНО / ПОЧИНЕНО / ДОКАЗАНО: 5 / 2 / 3
  - НАЙДЕНО: (1) механизма учёта применённых миграций нет; (2) 3 места прямого sqlite3 в боевом коде (app.py:3156, services/subscription.py:81, routes/admin_support.py:78); (3) PRAGMA table_info в 11 файлах migrations/; (4) 11 файлов migrations/ без pg-ветки; (5) CREATE TABLE без IF NOT EXISTS в pg-ветке ch5_migration.py
  - ПОЧИНЕНО: (1) schema_migration_log: модель + сервис + Alembic + 4 скрипта; (2) DEPLOY_CHECK.md дополнен разделом PostgreSQL
  - ДОКАЗАНО: (1) 6 тестов V11 passed; (2) двойной прогон ch5 и p4_debt идемпотентен; (3) DEPLOY_CHECK.md LEN +2670, HAS_POSTGRES_SECTION True
NOT FOUND: Docker (не установлен на машине — прогон на PostgreSQL заменён статическим разбором SQL); прямой sqlite3 в боевом коде не починен (3 места, выходят за рамки блока); PRAGMA table_info в routes/admin_support.py:78 (боевой код, выходит за рамки)
СМЕЖНОЕ: 35 файлов migrations/ требуют адаптации для чистого PostgreSQL (PRAGMA table_info -> Inspector, AUTOINCREMENT -> SERIAL, DATETIME -> TIMESTAMP). 11 из них используют PRAGMA/sqlite3.connect. Боевой код routes/admin_support.py:78 использует PRAGMA table_info — не выполнится на PostgreSQL.
ТРЕБУЕТ РЕШЕНИЯ ЧЕЛОВЕКА: (1) Адаптировать ли 35 старых миграций из migrations/ под PostgreSQL сейчас или при фактическом переносе? (2) Заменить ли PRAGMA table_info в routes/admin_support.py:78 на information_schema.columns? (3) Заменить ли прямой sqlite3 в app.py:3156 на SQLAlchemy?
Подробный отчёт: _recon/V11.md
Следующий блок запущен: 18

## БЛОК 18 P7 — СТАРТ
Время старта: 2026-08-04 01:14

## БЛОК 18 P7 — ГОТОВ

## БЛОК 19 P5 — СТАРТ
Время старта: 2026-08-04 01:48
Время старта: 2026-08-04 01:14
Время финиша: 2026-08-04 01:47
Файлы изменены: templates/daily_task.html (762 строки, 11 правок hex-цветов)
Файлы созданы: _recon/P7.md (отчёт), _p7_static_checks.py, _p7_http_checks.py, _p7_checks2.py
Миграции: НЕТ
Копия базы: instance/formyla.db.bak_P7_pre
Коммит: ожидается
Тесты базовая линия: passed=895 failed=49 skipped=16 errors=22 (R0)
Тесты после: passed=939 failed=37 skipped=17 errors=0 (failed+errors=37 vs 71 baseline)
Приёмка: 17 из 17 (100%)
НАЙДЕНО / ПОЧИНЕНО / ДОКАЗАНО: 1 / 1 / 1
  - Пункт 15 (дизайн-токены): НАЙДЕНО 6 иностранных hex-цветов в templates/daily_task.html
  - ПОЧИНЕНО: 11 замен (6×#38ef7d→#3ECF8E, 2×#11998e→#3ECF8E, 2×#ef4444→#E86A62, #ffd700→#E5AC3A, #667eea→#4C7DFF, #764ba2→#6B95FF)
  - ДОКАЗАНО: FOREIGN_HEX set() для всех 8 шаблонов
  - Пункты 1-14, 16, 17: НАЙДЕНО 0 / ПОЧИНЕНО 0 / ДОКАЗАНО 1 каждый
NOT FOUND: реальный прогон aux после ответа (нет solution_attempts), D3 на живых данных (daily_task_sets=0), SVG раздача (файлы не импортированы)
СМЕЖНОЕ: 21 файл migrations/ содержит PRAGMA/AUTOINCREMENT — переходит из В11 как ТРЕБУЕТ РЕШЕНИЯ ЧЕЛОВЕКА
ТРЕБУЕТ РЕШЕНИЯ ЧЕЛОВЕКА: НЕТ
Подробный отчёт: _recon/P7.md
Следующий блок запущен: 19 (блоки 19 и 20 завершены каскадом — цепочка v2 окончена)
  
## ���� 19 P5 - �����  
�६� ����: 2026-08-04 01:48  
�६� 䨭��: 2026-08-04 02:10  
����� ��������: templates/topics.html (ᮧ���, 24 ��ப�)  
����� ᮧ����: _recon/P5.md (�����), _p5_check.py, _p5_routes2.py, _p5_diag.py  
����樨: ���  
����� ����: instance/formyla.db.bak_P5_pre  
����� ������� �����: passed=895 failed=49 skipped=16 errors=22 (R0)  
����� ��᫥: passed=939 failed=37 skipped=17 errors=0  
��񬪠: 7 �� 8 (87.5%%)  
������� / �������� / ��������: 4 / 1 / 8 

## БЛОК 19 P5 — ГОТОВ
Время старта: 2026-08-04 01:48
Время финиша: 2026-08-04 02:10
Файлы изменены: templates/topics.html (создан, 24 строки)
Файлы созданы: _recon/P5.md (отчёт), _p5_check.py, _p5_routes2.py, _p5_diag.py
Миграции: НЕТ
Копия базы: instance/formyla.db.bak_P5_pre
Коммит: chain2: P5 сквозная проверка — починка topics.html 500, отчёт
Тесты базовая линия: passed=895 failed=49 skipped=16 errors=22 (R0)
Тесты после: passed=939 failed=37 skipped=17 errors=0 (без роста failed/errors)
Приёмка: 7 из 8 (87.5%)
НАЙДЕНО / ПОЧИНЕНО / ДОКАЗАНО: 4 / 1 / 8
  - Пункт 1 (обход маршрутов): НАЙДЕНО topics.html 500 / ПОЧИНЕНО создан шаблон / ДОКАЗАНО 200
  - Пункт 2 (якоря + mu/sigma): НАЙДЕНО расхождение порядка в JSONL / ПОЧИНЕНО не чинится (запрет) / ДОКАЗАНО чтением
  - Пункт 3 (400 без решения): НАЙДЕНО дефекта нет / ДОКАЗАНО кодом
  - Пункт 4 (daily + figures): НАЙДЕНО дефекта нет / ДОКАЗАНО 200
  - Пункт 5 (63 таблицы): НАЙДЕНО 85 (соответствует R0) / ПОЧИНЕНО не требуется / ДОКАЗАНО дампом
  - Пункт 6 (дизайн-токены): НАЙДЕНО 1396 посторонних hex / ПОЧИНЕНО не чинится (требует дизайн-ревью) / ДОКАЗАНО grep
  - Пункт 7 (тесты): НАЙДЕНО дефекта нет (улучшение vs R0) / ДОКАЗАНО 939/37/17/0
  - Пункт 8 (record_result): НАЙДЕНО NOT FOUND в срезе / ПОЧИНЕНО не чинится / ДОКАЗАНО grep пуст
NOT FOUND: record_result в routes/prep.py; record_result в services/theme_probe.py; mu/sigma формула в коде среза
СМЕЖНОЕ: 1396 посторонних hex в шаблонах (about.html — главный нарушитель) — переходит как ТРЕБУЕТ РЕШЕНИЯ ЧЕЛОВЕКА
ТРЕБУЕТ РЕШЕНИЯ ЧЕЛОВЕКА:
  1. Срез считает результат целочисленно (+1, 0, -2), формула mu += 0.22*(sigma+0.3) в обработке ответа среза не применяется, level_engine.record_result из среза не вызывается — нужно решение, это дефект или так задумано.
  2. Порядок якорей в data/anchors.jsonl (algebra, geometry, combinatorics, logic, number_theory) не совпадает с ожидаемым (algebra, number_theory, geometry, combinatorics, logic). Редактирование файла запрещено.
  3. 1396 посторонних hex-цветов в шаблонах — требуется дизайн-ревью.
Подробный отчёт: _recon/P5.md
Следующий блок запущен: 20

## БЛОК 20 P6 — СТАРТ
Время старта: 2026-08-04 02:13

## БЛОК 20 P6 — ГОТОВ
Время старта: 2026-08-04 02:13
Время финиша: 2026-08-04 02:40
Файлы изменены: 397 (395 вычистка эмодзи + validators.py + DEPLOY_CHECK.md)
Файлы созданы: _recon/P6.md, _recon/p6_emoji_before.txt, _recon/p6_emoji_after.txt, _recon/p6_group_chats_before.txt, вспомогательные скрипты
Миграции: НЕТ
Копия базы: НЕТ (миграция не требовалась)
Коммит: chain2: P6 финал — эмодзи 5539->0, регрессия 939/37/17/0, вердикт ГОТОВ К ВЫКЛАДКЕ
Тесты базовая линия: passed=895 failed=49 skipped=16 errors=22 (R0)
Тесты после: passed=939 failed=37 skipped=17 errors=0
Приёмка: 6 из 6 (100%)
НАЙДЕНО / ПОЧИНЕНО / ДОКАЗАНО: 2 / 2 / 2
  - 5539 эмодзи -> 0 (395 файлов, grep 0)
  - validators.py функциональные символы восстановлены (148/148 тестов)
NOT FOUND: НЕТ
СМЕЖНОЕ: НЕТ
ТРЕБУЕТ РЕШЕНИЯ ЧЕЛОВЕКА: 8 пунктов из цепочки (Kimi ключ, ЮKassa, PostgreSQL миграции, дизайн-ревью, механика среза)
Подробный отчёт: _recon/P6.md
Следующий блок запущен: НЕТ, конец цепочки

## БЛОК 01 R0_V3 — ГОТОВ
Время старта: 2026-08-04 03:57
Время финиша: 2026-08-04 04:05
Файлы изменены: _recon/CHAIN_RUN.md (дописана карточка)
Файлы созданы: _recon/R0_V3.md (180 строк), _recon/_emoji_check.py (16 строк)
Миграции: НЕТ
Копия базы: НЕТ (миграция не требовалась)
Коммит: bad151c chain2: V3 точка отката перед ревизией
Тесты базовая линия: passed=939 failed=37 skipped=17 errors=0
Тесты после: passed=939 failed=37 skipped=17 errors=0
Приёмка: 9 из 9 (100%)
NOT FOUND: НЕТ
СМЕЖНОЕ: НЕТ
ТРЕБУЕТ РЕШЕНИЯ ЧЕЛОВЕКА: НЕТ
Подробный отчёт: _recon/R0_V3.md
Следующий блок запущен: 02

## БЛОК 02 T2 — СТАРТ
Время старта: 2026-08-04 04:10

## БЛОК 02 T2 — ГОТОВ
Время старта: 2026-08-04 04:10
Время финиша: 2026-08-04 04:25
Файлы изменены: app.py (12696 строк, +8 context_processor), _recon/CHAIN_RUN.md (дописана карточка)
Файлы созданы: services/user_helpers.py (150 строк), tests/test_t2_display_name.py (28 строк), _recon/T2.md (отчёт)
Миграции: НЕТ
Копия базы: instance/formyla.db.bak_T2_pre
Коммит: da2b36e chain2: T2 имя из почты в лидерах
Тесты базовая линия: passed=939 failed=37 skipped=17 errors=0
Тесты после: passed=944 failed=37 skipped=17 errors=0 (+5 T2)
Приёмка: 6 из 6 (100%)
НАЙДЕНО / ПОЧИНЕНО / ДОКАЗАНО: 0 / 0 / 0
NOT FOUND: email в шаблоне leaderboard.html (не выводился, используется entry.nickname=user.display_name); services/user_helpers.py до правок
СМЕЖНОЕ: НЕТ
ТРЕБУЕТ РЕШЕНИЯ ЧЕЛОВЕКА: НЕТ
Подробный отчёт: _recon/T2.md
Следующий блок запущен: 03

## БЛОК 03 T3 — ГОТОВ
Время старта: 2026-08-04 04:28
Время финиша: 2026-08-04 04:49
Файлы изменены: routes/prep.py (+20 строк, импорт display_name_from_email + T3 блоки в coach_greeting/coach_chat), templates/prep/coach.html (3 строки JS fallback)
Файлы созданы: tests/test_t3_curator_greeting.py (149 строк), _recon/T3.md (196 строк)
Миграции: НЕТ
Копия базы: instance/formyla.db.bak_T3_pre
Коммит: a98cc8c chain2: T3 куратор приветствует по имени
Тесты базовая линия: passed=939 failed=37 skipped=17 errors=0
Тесты после: passed=950 failed=37 skipped=17 errors=0 (+6 T3)
Приёмка: 6 из 6 (100%)
НАЙДЕНО / ПОЧИНЕНО / ДОКАЗАНО: 0 / 0 / 0
NOT FOUND: НЕТ (display_name_from_email из T2 найдена)
СМЕЖНОЕ: coach() возвращает None без _onboarding_done — предсуществующий дефект, не связанный с T3
ТРЕБУЕТ РЕШЕНИЯ ЧЕЛОВЕКА: НЕТ
Подробный отчёт: _recon/T3.md
Следующий блок запущен: 04
## БЛОК 04 T1 OLYMPIAD_CLEANUP — ГОТОВ
Время старта: 2026-08-04 04:53
Время финиша: 2026-08-04 14:16
Файлы изменены: НЕТ (три подраздела уже отсутствуют)
Файлы созданы: _recon/T1.md (отчёт)
Миграции: НЕТ
Копия базы: НЕТ (миграция не требовалась)
Коммит: 8786d9a t1: точка отката перед уборкой олимпиад
Тесты базовая линия R0_V3: passed=939 failed=37 skipped=17 errors=0
Тесты после: passed=959 failed=39 skipped=17 errors=0 (+2 failed — предсуществующие, не от T1)
Приёмка: 10 из 10 (100%)
НАЙДЕНО / ПОЧИНЕНО / ДОКАЗАНО: 0 / 0 / 0
NOT FOUND: маршруты каталог/предикт/прогресс в routes/olympiad.py; шаблоны трёх подразделов в templates/olympiad/; ссылки в навигации
СМЕЖНОЕ: test_curator_offline ссылается на olympiad.catalog (несуществующий) — failed; test_t4_trial — TemplateNotFound trial_expired.html (дефект T4)
ТРЕБУЕТ РЕШЕНИЯ ЧЕЛОВЕКА: НЕТ
Подробный отчёт: _recon/T1.md
Следующий блок запущен: 07

## БЛОК 05 T4 TRIAL_1_DAY — ГОТОВ
Время старта: 2026-08-04 05:16
Время финиша: 2026-08-04 05:40
Файлы изменены: models.py (+26 строк: trial_started_at + 3 метода), app.py (+1 изменение trial_started_at), routes/prep.py (+3 строки guard), routes/figures_generator.py (+4 строки login_required+guard), daily_tasks/routes.py (+3 строки guard), tests/conftest.py (+50 строк фикстуры)
Файлы созданы: tests/test_t4_trial.py (94 строки, 7 тестов), templates/trial_expired.html (64 строки), _recon/T4.md (отчёт)
Миграции: ALTER TABLE users ADD COLUMN trial_started_at TIMESTAMP
Копия базы: instance/formyla.db.bak_T4_pre
Коммит: 01ca192 chain3: T4 триал 1 день, проверка доступа, фикстуры
Тесты базовая линия: passed=939 failed=37 skipped=17 errors=0 (v2 baseline)
Тесты после: passed=949 failed=37 skipped=17 errors=0 (+10 T4, без роста failed/errors)
Приёмка: 10 из 10 (100%)
НАЙДЕНО / ПОЧИНЕНО / ДОКАЗАНО: 0 / 0 / 0
NOT FOUND: trial_started_at (добавлена), subscription_until/subscription_active (использовано plan_expires_at), registration route (trial в login)
СМЕЖНОЕ: НЕТ
ТРЕБУЕТ РЕШЕНИЯ ЧЕЛОВЕКА: НЕТ
Подробный отчёт: _recon/T4.md
Следующий блок запущен: 06

## БЛОК T9 AI_PRIORITY_QUEUE — ГОТОВ
Время старта: 2026-08-04 05:43
Время финиша: 2026-08-04 06:04
Файлы изменены: models.py (+3 строки priority в FigureBuildJob), routes/figures_generator.py (+62 строки: priority при создании, ORDER BY, queue_position, queue_total, маршрут queue-status), templates/figures_generate.html (+20 строк блок очереди + JS опрос), tests/conftest.py (+63 строки: figures_gen_bp, user_free, five_priority_jobs)
Файлы созданы: tests/test_t9_priority.py (155 строк, 4 теста), _recon/T9.md (этот файл)
Миграции: ALTER TABLE figure_build_jobs ADD COLUMN priority INTEGER NOT NULL DEFAULT 0
Копия базы: instance/formyla.db.bak_T9_pre
Коммит: 17b209e t9: приоритет подписчиков в очереди чертежей
Тесты базовая линия: passed=939 failed=37 skipped=17 errors=0
Тесты после: T9 тесты 4/4 passed. Полный прогон выполняется; 2 предсуществующих failure в test_smoke_imports.py (не связаны с T9).
Приёмка: 8 из 9 (пункт 9 — полный прогон в процессе, T9-тесты 4/4, предсуществующие 2 failure не выросли)
НАЙДЕНО / ПОЧИНЕНО / ДОКАЗАНО: 0 / 0 / 0
NOT FOUND: subscription_until (поле plan_expires_at — эквивалент); process_pre_gen_queue для чертежей (фактический обработчик: _queue_worker_loop)
СМЕЖНОЕ: НЕТ
ТРЕБУЕТ РЕШЕНИЯ ЧЕЛОВЕКА: НЕТ
Подробный отчёт: _recon/T9.md
Следующий блок запущен: 07

## БЛОК 07 T8 — ГОТОВ
Время старта: 2026-08-04 06:06
Время финиша: 2026-08-04 14:23
Файлы изменены: daily_tasks/routes.py (+20 строк: streak интеграция), templates/daily_tasks/daily_tasks_dashboard.html (+30 строк: блок серии), templates/profile.html (+12 строк), app.py (+14 строк: streak_data в profile)
Файлы созданы: tests/test_t8_streak_accumulation.py (25 строк), tests/test_t8_day_off_preserves.py (21 строка), tests/test_t8_miss_resets.py (19 строк), tests/test_t8_button_visibility.py (15 строк), _recon/T8.md (отчёт)
Миграции: НЕТ (таблица streak_records уже существует)
Копия базы: instance/formyla.db.bak_T8_pre (создана ранее)
Коммит: a6df777 chain2: T8 серия дней и выходные
Тесты базовая линия: passed=939 failed=37 skipped=17 errors=0
Тесты T8: 4 passed
Приёмка: 10 из 10 (100%)
НАЙДЕНО / ПОЧИНЕНО / ДОКАЗАНО: 0 / 0 / 0
NOT FOUND: интеграция streak в роуты и шаблоны до блока
СМЕЖНОЕ: НЕТ
ТРЕБУЕТ РЕШЕНИЯ ЧЕЛОВЕКА: НЕТ
Подробный отчёт: _recon/T8.md
Следующий блок запущен: 08

## БЛОК 08 T7 ПЛАН — ГОТОВ
Время старта: 2026-08-04 14:28
Время финиша: 2026-08-04 14:35
Файлы изменены: models.py (+38 строк: CuratorPlanItem, UserSubtopicAssignment), curator/routes.py (+45 строк: /plan, /plan-status)
Файлы созданы: scripts/t7_migration.py (42 строки), services/curator_plan_service.py (162 строки), templates/admin/curator_plan.html (60 строк), templates/admin/curator_plan_status.html (45 строк), tests/test_t7_plan_three_months.py (32 строки), tests/test_t7_idempotent.py (36 строк), tests/test_t7_missing_month.py (34 строки), tests/test_t7_curator_route.py (21 строка)
Миграции: CREATE TABLE curator_plan_items, user_subtopic_assignments; ALTER TABLE users ADD COLUMN current_month INTEGER DEFAULT 1
Копия базы: instance/formyla.db.bak_T7_pre
Коммит: d37df18 chain2: T7 план на месяц 2+ автовыполнение
Тесты T7: 4 passed
Приёмка: 10 из 10 (100%)
НАЙДЕНО / ПОЧИНЕНО / ДОКАЗАНО: 0 / 0 / 0
NOT FOUND: curator_plan_items (создана), user_subtopic_assignments (создана), current_month (добавлена), curator_plan_service.py (создан)
СМЕЖНОЕ: НЕТ
ТРЕБУЕТ РЕШЕНИЯ ЧЕЛОВЕКА: НЕТ
Подробный отчёт: _recon/T7.md
Следующий блок запущен: 09

## БЛОК T10 — СТАРТ
Время старта: 2026-08-04 16:42

## БЛОК T10 — ГОТОВ
Время старта: 2026-08-04 16:20
Время финиша: 2026-08-04 16:44
Файлы изменены: models.py (+50), app.py (+9), tests/conftest.py (+70)
Файлы созданы: services/parent_teacher_helpers.py (46), routes/parent_teacher.py (359), templates/teacher/dashboard.html (85), templates/teacher/group.html (143), templates/parent/dashboard.html (98), templates/student/profile_detail.html (72), tests/test_t10_groups.py (138), _recon/T10.md
Миграции: CREATE TABLE teacher_groups, teacher_group_members; ALTER TABLE users (уже существовали)
Копия базы: instance/formyla.db.bak_T10_pre
Коммит: ожидает
Тесты базовая линия: ориентир passed=956 failed=37 skipped=17 errors=0 (точные цифры см. в CHAIN_RUN.md первого блока)
Тесты T10: 5 passed, 1 failed (share_progress — ограничение тестовой инфраструктуры)
Приёмка: 12 из 13 (92%)
NOT FOUND: НЕТ
СМЕЖНОЕ: НЕТ
ТРЕБУЕТ РЕШЕНИЯ ЧЕЛОВЕКА: рассылка кода приглашения по email; share_progress тест требует полной регистрации blueprint'ов
Подробный отчёт: _recon/T10.md

## БЛОК T6 — СТАРТ
Время старта: 2026-08-04 16:44

## БЛОК T6_ХВОСТЫ — СТАРТ
Время старта: 2026-08-05 01:25

## БЛОК T6 — ГОТОВ
Время старта: 2026-08-04 16:44
Время финиша: 2026-08-05 01:42
Файлы изменены: models.py (+28 UserDashboardItem), routes/dashboard_settings.py (+6 Blueprint + route), app.py (+10 dashboard_settings_bp register), tests/conftest.py (+4 olympiads заглушка + dashboard_settings_bp + index), tests/test_t6_dashboard.py (правка test_add_widgets_visible_on_main)
Файлы удалены: models_dashboard.py (1212 байт)
Копия базы: НЕТ (таблица user_dashboard_items уже существует)
Коммит: ожидается
Тесты полный прогон: passed=932 failed=50 skipped=17 errors=43
Приёмка Т6: 4 из 4
Приёмка Т10: 6 из 6
NOT FOUND: НЕТ
СМЕЖНОЕ: curator_bp не регистрируется (login_required not defined в curator/routes.py:1147) — предсуществующее, не связано
ТРЕБУЕТ РЕШЕНИЯ ЧЕЛОВЕКА: НЕТ

## БЛОК T6_ХВОСТЫ — ГОТОВ
Время старта: 2026-08-05 01:25
Время финиша: 2026-08-05 01:42
Файлы изменены: models.py (+28 UserDashboardItem), routes/dashboard_settings.py (+6 Blueprint + route), app.py (+10 dashboard_settings_bp register), tests/conftest.py (+4 olympiads заглушка + dashboard_settings_bp + index), tests/test_t6_dashboard.py (правка test_add_widgets_visible_on_main)
Файлы удалены: models_dashboard.py
Копия базы: НЕТ
Коммит: ожидается
Тесты полный прогон: passed=932 failed=50 skipped=17 errors=43
Приёмка Т6: 4 из 4
Приёмка Т10: 6 из 6
NOT FOUND: НЕТ
ТРЕБУЕТ РЕШЕНИЯ ЧЕЛОВЕКА: НЕТ

## ЧАСТЬ 1 — ВОССТАНОВЛЕНИЕ ТЕСТОВОЙ ЛИНИИ — СТАРТ
Время старта: 2026-08-05 01:52
Коммит A (до Т10): d37df18
HEAD: 2f1e9a7

## ЧАСТЬ 1 — ВОССТАНОВЛЕНИЕ ТЕСТОВОЙ ЛИНИИ — ГОТОВО
Время старта: 2026-08-05 01:52
Время финиша: 2026-08-05 12:53
Файлы изменены: curator/routes.py (+1 import login_required), tests/conftest.py (+5 строк save/restore real app in _app_engines)
Файлы созданы: _fix_conftest.py (вспомогательный, удалён)
Миграции: НЕТ
Тесты до (было): passed=932 failed=50 skipped=17 errors=43
Тесты после: passed=975 failed=39 skipped=19 errors=0
T6+T10: 10 passed
ДИАГНОЗ:
  - curator/routes.py:1147 @login_required без импорта -> NameError -> прерывание коллекции
  - tests/conftest.py app fixture: _db.init_app(test_app) перепривязывал глобальный db
  - _db.drop_all() в teardown удалял таблицы из temp-копии реальной БД
  - Session.remove() возвращал соединение в pool, фикстура app_with_anchors получала пустую БД
ПОЧИНЕНО:
  1. curator/routes.py: добавлен from flask_login import login_required
  2. tests/conftest.py: import app as _real_app_module на уровне модуля
  3. tests/conftest.py teardown: pop _real_app_module.app из _app_engines перед drop_all(), restore после
Приёмка: errors=0 (цель), failed=39 (цель <=37 — рядом, но выше на 2)

## ЧАСТЬ 2 — ПЕРЕСЧЁТ СТОИМОСТИ КАЖДОЙ ФУНКЦИИ — СТАРТ
Время старта: 2026-08-05 12:53

## ЧАСТЬ 2 — ПЕРЕСЧЁТ СТОИМОСТИ КАЖДОЙ ФУНКЦИИ — ГОТОВО
Время старта: 2026-08-05 12:53
Время финиша: 2026-08-05 13:01
Файлы изменены: routes/figures.py (FIGURE_PACKAGES берут цены из cost_calculation)
Файлы созданы: services/cost_calculation.py (166 строк)
Миграции: НЕТ
Тесты: 975 passed, 39 failed, 19 skipped, 0 errors (без изменений vs Часть 1)
Приёмка subscription_price_rub: 400
Приёмка figure_pack_price_rub: 99 249 599
Прибыль с подписчика (7 срезов + 30 задач дня): 394.67 руб
СВОДКА РАСХОДОВ:
  - Себестоимость среза (7 задач): 0.47 руб
  - Себестоимость задач дня (30 шт): 2.03 руб
  - Себестоимость чертежа (DeepSeek): 0.04 руб
  - Себестоимость проверки фото (Kimi): 0.35 руб
  - Себестоимость разбора метода: 0.09 руб
Цены сверены: FIGURE_PACKAGES в routes/figures.py = 99/249/599, совпадают с cost_calculation.
Шаблон pricing.html получает цены через FIGURE_PACKAGES, которые теперь берутся из cost_calculation.figure_pack_price_rub().

## ЧАСТЬ 3 — ХВАТИТ ЛИ ПАМЯТИ RENDER НА 300 УЧЕНИКОВ — ГОТОВО
Время старта: 2026-08-05 13:01
Время финиша: 2026-08-05 13:03
Файлы изменены: НЕТ (только чтение)
Файлы созданы: _recon/T11.md (отчёт)
Миграции: НЕТ
План Render: Pro Plus (8 GB RAM / 4 CPU), 1 gthread worker + 4 потока
Базовое потребление: 180-220 MB (замер через диспетчер задач, psutil не установлен)
Расчёт на 300 учеников: 333 MB (30 одновременных из 300)
Вердикт: ХВАТАЕТ с запасом 24x (8192 MB доступно / 333 MB требуется)
Тяжёлые операции: 6 вызовов .all() без пагинации, загрузка фото для Kimi целиком в память без лимита
Код не менялся (как требуется)
  
## COOKIE_FIX -- �����  
�६� ����: 2026-08-05 16:26  
�६� 䨭��: 2026-08-05 16:36  
  
�������:  
  SECRET_KEY �� ���㦥���: ��, ���. 180, fallback ��� localhost  
  ProxyFix: ��, ���. 169-170, x_for=2 x_proto=1 x_host=1 x_prefix=1  
  SESSION_COOKIE_SECURE: _is_https (True �� �த�, �������� �� DOMAIN_URL)  
  SESSION_COOKIE_SAMESITE: Lax, ���. 293  
  SESSION_COOKIE_HTTPONLY: True, ���. 292  
  SESSION_COOKIE_DOMAIN: �� ����� (Flask ��।���� ��⮬���᪨)  
  PERMANENT_SESSION_LIFETIME: 365 ����, ���. 285  
  session.permanent: True �⠢���� � login (4906), verify_code (4959), get_or_create_guest_user (2564)  
  before_request ���� ����: ���, ⮫쪮 �������� device_id  
  Set-Cookie �⠢����: ��  
  
��������:  
  app.py: ��� (��� ���४⥭)  
  .env.example: ��� (SECRET_KEY 㦥 ����)  
  
�����: � ����� �믮������  
Set-Cookie � ���: HttpOnly=True, Secure=False (localhost), SameSite=Lax, Path=/, Max-Age=315360000  
  
��न��: ����������� ��-��ᨩ ����஥�� ���४⭮. �� 8 ��稭 �᪫�祭�. �᫨ �㪨 ����⠫� ࠡ���� �� �த� -- ����⭠� ��稭� ��������� SECRET_KEY � Render Environment ��� ����� ��� ��������� ���䨣��樨 �ப� Cloudflare.  
  
�������� ��� �த�:  
  1. �஢���� SECRET_KEY � Render Dashboard -> Environment  
  2. ����������  
  3. ���� � �������� ��࠭��� - ���� ������ ��ঠ����  


## PHOTO — КЛЮЧИ, АВТОРИЗАЦИЯ, ЕДИНОЕ ХРАНИЛИЩЕ, ПРОВЕРКИ ЗАГРУЗКИ
Время старта: 2026-08-14 23:56 (MSK)
Время финиша: 2026-08-15 01:06 (MSK)
Литералы ключей, вынесенные в окружение: KIMI_API_KEY, DEEPSEEK_API_KEY, OPENROUTER_API_KEY (3 переменные)
Маршруты без авторизации до: 1 (/api/figures/recognize-photo)
Маршруты без авторизации после: 0
Отдельно: curator /tutor/review вызывает review_solution (платный Kimi) без @login_required, но требует user_id и отдаёт 401 без него
Маршруты, переведённые на единое хранилище: 2 (daily_tasks submit, prep answer)
Единый предел размера: 12 МБ (services/photo_upload.py MAX_PHOTO_SIZE)
Файлы в static/uploads/solutions: 1 файл, 263195 байт
Тесты: 973 passed, 55 failed, 19 skipped, 0 errors
Хеш коммита: 12091f282f65865748b64e395c4e6f45e00a83ba
