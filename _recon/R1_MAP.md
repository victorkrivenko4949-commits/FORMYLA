# R1\_MAP — Полная карта проекта FORMYLA

Дата сбора: 2026-07-31 18:45 MSK.  
Собрано через: чтение кода, запуск app.url_map, прямые запросы в SQLite.

---

## 1. СТРУКТУРА

### 1.1. Дерево проекта (3 уровня, без `__pycache__`, `venv`, `node_modules`, `.git`)

```
.
├── _recon/                          (разведочные файлы — созданы сейчас)
├── ai/                              (DeepSeek + Gemini клиенты)
│   ├── deepseek_client.py           (417 строк)
│   └── gemini_client.py             (171 строка)
├── alembic_migrations/              (Alembic-миграции версий)
│   └── versions/                    (файлы миграций)
├── assistant/                       (FORMYLA AI Site Assistant)
│   ├── deepseek_client.py           (112 строк)
│   └── kb/                          (база знаний ассистента)
├── backups/                         (бекап-файлы olympiads.py)
├── config/                          (не найдено .py файлов)
├── curator/                         (модуль «Куратор» AI-наставника)
│   ├── monthly_cycle.py
│   └── push_service.py
├── daily_tasks/                     (Задачи дня — мульти-LLM пайплайн)
│   ├── models.py                    (301 строка, 7 моделей)
│   ├── services.py                  (2643 строки)
│   ├── profile.py                   (профилирование ученика)
│   ├── pipeline/                    (step1..step4 генерации)
│   │   ├── step2_opus.py            (113748 байт)
│   │   ├── step3_gpt_audit.py
│   │   ├── step4_opus_fix.py
│   │   └── diversity_catalog.py     (1831 строка)
│   └── routes.py
├── data/                            (JSON/JSONL данные)
│   ├── olympiads/
│   │   ├── methods_catalog_105.json  (102 метода)
│   │   ├── theory_65_methods.json
│   │   ├── theory_24_methods.json
│   │   ├── vsosh9_full.json
│   │   └── vsosh_10_11_full.json
│   └── adaptive/
│       └── adaptive_full_9120.json
├── docs/                            (документация)
├── instance/                        (Flask instance folder)
├── l1_l3_generation/               (генерация L1-L3)
├── l4_l5_completion_work/          (доработка L4-L5)
├── l4_l5_finalization/             (финализация L4-L5)
│   ├── stage7_debug_snapshot/
│   └── taxonomy_reconstruction/
├── logs/                            (app.log)
├── migrations/                      (кастомные миграции)
├── routes/                          (блюпринты Flask)
│   ├── prep.py                      (3021 строка)
│   ├── olympiad.py
│   ├── olympiad_prep.py
│   ├── account.py
│   ├── drawing.py
│   ├── drawing_diag.py
│   ├── drawing_history.py
│   ├── wb_call.py
│   ├── wb_meet.py
│   ├── wb_ws.py
│   ├── conference_api.py
│   ├── chat_presence.py
│   ├── admin_support.py
│   ├── grade.py
│   └── telegram_auth.py
├── scripts/                         (вспомогательные скрипты)
├── services/                        (сервисный слой)
│   ├── openrouter_client.py         (417 строк, httpx)
│   ├── drawing_service.py           (1375 строк)
│   ├── notifications.py             (web-push)
│   ├── md_render.py
│   ├── security.py
│   ├── olympiad_autoseed.py
│   ├── vsosh_full_seed.py
│   ├── vsosh_10_11_additive_seed.py
│   ├── adaptive_full_seed.py
│   ├── latex_root_db_fix.py
│   ├── latex_root_normalizer.py
│   ├── level_engine.py
│   ├── geometry_drawings.py
│   ├── figures_manifest.py
│   ├── math_text_normalizer.py
│   ├── olympiad_adaptive.py
│   └── pipeline/
│       └── uniqueness_search.py
├── static/                          (CSS, JS, картинки)
│   ├── css/
│   ├── js/
│   └── img/
├── templates/                       (Jinja2 шаблоны)
│   ├── base.html                    (981 строка)
│   ├── tutor_widget.html            (920 строк)
│   ├── chat.html                    (2342 строки)
│   ├── daily_tasks/
│   │   └── daily_tasks_dashboard.html (1368 строк)
│   ├── olympiad/
│   │   └── task.html                (1018 строк)
│   ├── prep/
│   │   ├── coach.html               (1152 строки)
│   │   └── onboarding.html          (607 строк)
│   └── ...
├── tests/                           (pytest)
├── app.py                           (12260 строк — ГЛАВНЫЙ ФАЙЛ)
├── models.py                        (1533 строки — все ORM-модели)
├── models_curator.py                (57 строк)
├── models_grade.py                  (140 строк)
├── models_olympiad.py               (519 строк)
├── olympiads.py                     (~19847 строк, 5267 задач)
├── problems.py                      (19847 строк)
├── olympiads.db                     (SQLite БД олимпиад)
├── formyla.db                       (основная SQLite БД)
├── database.db                      (дополнительная БД)
├── .env                             (переменные окружения локально)
├── .env.example
├── requirements.txt
├── runtime.txt
├── render.yaml
└── docker-compose.livekit.yml
```

### 1.2. Число строк .py файлов (выборка)

| Строк  | Файл |
|--------|------|
| 80796  | olympiads_backup_before_retry.py |
| 80788  | olympiads_backup_before_prob9.py |
| 80780  | olympiads_backup_g10v2_fix.py |
| 80751  | olympiads_backup_grade11_v7.py |
| 80705  | olympiads_fixed.py |
| 80661  | olympiads_backup_grades_9_10.py |
| 80616  | olympiads_backup.py |
| 80616  | olympiads_backup_day2.py |
| 80616  | olympiads_backup_grade11_v8.py |
| 19847  | problems.py |
| **12260** | **app.py** |
| 3021   | routes/prep.py |
| 2643   | daily_tasks/services.py |
| 2137   | _fill_l4_l5_pipeline.py |
| 1831   | daily_tasks/pipeline/diversity_catalog.py |
| 1601   | l4_l5_finalization/taxonomy_reconstruction/_taxonomy_reconstruct.py |
| **1533** | **models.py** |
| 1520   | run_selection_1080_pipeline.py |
| 1375   | services/drawing_service.py |
| 1363   | l4_l5_finalization/_07_stage7_verify.py |

**Топ-20 самых больших .py файлов**: строки выше (первые 9 — бекапы olympiads.py ~80k строк каждый, исключая их — app.py 12260, problems.py 19847, routes/prep.py 3021, daily_tasks/services.py 2643, models.py 1533).

### 1.3. Шаблоны — число строк (все >100 строк)

| Строк | Шаблон |
|-------|--------|
| 2342 | templates/chat.html |
| 1781 | templates/about.html |
| 1674 | templates/adaptive_test_simple.html |
| 1368 | templates/daily_tasks/daily_tasks_dashboard.html |
| 1152 | templates/prep/coach.html |
| 1063 | templates/profile.html |
| 1018 | templates/olympiad/task.html |
| 981  | templates/base.html |
| 920  | templates/tutor_widget.html |
| 794  | templates/free_mock.html |
| 685  | templates/subscribe.html |
| 644  | templates/call.html |
| 607  | templates/prep/onboarding.html |
| 595  | templates/whiteboard.html |
| 580  | templates/group_chat.html |
| 570  | templates/daily_task.html |
| 524  | templates/problem_detail.html |
| 476  | templates/drawing.html |
| 475  | templates/olympiads.html |
| 436  | templates/olympiad_prep/detail.html |

---

## 2. ТОЧКА ВХОДА

Файл [`app.py`](app.py:1) — 12260 строк, монолитный Flask-application.

### 2.1. Зарегистрированные блюпринты

Все регистрируются в [`app.py`](app.py:987-1461):

| Префикс | Блюпринт | Модуль | Строки регистрации |
|---------|----------|--------|-------------------|
| `/prep` | `prep_bp` | [`routes/prep.py`](routes/prep.py:1) | [app.py:992-996](app.py:992) |
| `/olympiad-prep` | `olympiad_prep_bp` | [`routes/olympiad_prep.py`](routes/olympiad_prep.py:1) | [app.py:998-1003](app.py:998) |
| `/account` | `account_bp` | [`routes/account.py`](routes/account.py:1) | [app.py:1005-1010](app.py:1005) |
| `/drawing` + `/api/drawing` | `drawing_bp` | [`routes/drawing.py`](routes/drawing.py:1) | [app.py:1012-1017](app.py:1012) |
| `/api/drawing/diag` | `drawing_diag_bp` | [`routes/drawing_diag.py`](routes/drawing_diag.py:1) | [app.py:1019-1024](app.py:1019) |
| `/api/drawing/history` | `drawing_history_bp` | [`routes/drawing_history.py`](routes/drawing_history.py:1) | [app.py:1026-1031](app.py:1026) |
| `/api/wb_call/*` | `wb_call_bp` | [`routes/wb_call.py`](routes/wb_call.py:1) | [app.py:1034-1039](app.py:1034) |
| `/api/wb_meet/*` | `wb_meet_bp` | [`routes/wb_meet.py`](routes/wb_meet.py:1) | [app.py:1043-1048](app.py:1043) |
| `/api/conference/*` | `conference_api_bp` | [`routes/conference_api.py`](routes/conference_api.py:1) | [app.py:1051-1056](app.py:1051) |
| `/api/chat/*/presence` | `chat_presence_bp` | [`routes/chat_presence.py`](routes/chat_presence.py:1) | [app.py:1058-1065](app.py:1058) |
| `/olympiads/*` | `olympiad_bp` | [`routes/olympiad.py`](routes/olympiad.py:1) | [app.py:1069-1082](app.py:1069) |
| `/admin/support`, `/my/support` | `admin_support_bp` | [`routes/admin_support.py`](routes/admin_support.py:1) | [app.py:1075-1080](app.py:1075) |
| `/grade-5`, `/grade-6`, `/grade-task/*` | `grade_bp` | [`routes/grade.py`](routes/grade.py:1) | [app.py:1392-1398](app.py:1392) |
| `/api/assistant`, `/api/concierge/*` | `assistant_bp` | [`assistant/__init__.py`](assistant/__init__.py:1) | [app.py:1402-1414](app.py:1402) |
| `/auth/telegram/*` | `telegram_auth_bp` | [`routes/telegram_auth.py`](routes/telegram_auth.py:1) | [app.py:1417-1422](app.py:1417) |
| `/daily_tasks` | `daily_tasks_bp` | [`daily_tasks/__init__.py`](daily_tasks/__init__.py:1) | [app.py:1434-1447](app.py:1434) |
| `/curator` | `curator_bp` | [`curator/__init__.py`](curator/__init__.py:1) | [app.py:1450-1460](app.py:1450) |

### 2.2. Расширения

| Расширение | Где инициализируется |
|------------|---------------------|
| `flask_sqlalchemy.SQLAlchemy` | [`models.py:10`](models.py:10) — `db = SQLAlchemy()` |
| `flask_login.LoginManager` | [`app.py:980-983`](app.py:980) |
| `flask_mail.Mail` | [`app.py:985`](app.py:985) |
| `flask_apscheduler.APScheduler` | [`app.py:1604-1613`](app.py:1604) |
| `sentry_sdk` (Sentry) | [`app.py:71-92`](app.py:71) — при наличии SENTRY_DSN |
| `werkzeug.middleware.proxy_fix.ProxyFix` | [`app.py:121-126`](app.py:121) |

### 2.3. Все переменные окружения, читаемые в app.py

Перечислены в порядке появления в коде:

| Имя | Назначение | Строки |
|-----|-----------|--------|
| `SENTRY_DSN` | Sentry DSN для отлова ошибок | [app.py:71](app.py:71) |
| `SENTRY_TRACES_SAMPLE_RATE` | Частота трейсинга Sentry | [app.py:81](app.py:81) |
| `SENTRY_PROFILES_SAMPLE_RATE` | Частота профилирования Sentry | [app.py:82](app.py:82) |
| `FLASK_ENV` | Окружение (production/development) | [app.py:84](app.py:84) |
| `RENDER_GIT_COMMIT` | SHA коммита на Render | [app.py:85](app.py:85) |
| `SECRET_KEY` | Ключ подписи сессий Flask | [app.py:133](app.py:133) |
| `RENDER` | Флаг продакшена (Render) | [app.py:134](app.py:134) |
| `DATABASE_URL` | Строка подключения к БД | [app.py:178](app.py:178) |
| `DOMAIN_URL` | URL сайта | [app.py:209](app.py:209) |
| `MAIL_SERVER` | SMTP-сервер | [app.py:222](app.py:222) |
| `MAIL_PORT` | Порт SMTP | [app.py:223](app.py:223) |
| `MAIL_USE_TLS` | Флаг TLS | [app.py:225](app.py:225) |
| `MAIL_USE_SSL` | Флаг SSL | [app.py:226](app.py:226) |
| `MAIL_USERNAME` | Логин SMTP | [app.py:227](app.py:227) |
| `MAIL_PASSWORD` | Пароль SMTP | [app.py:228](app.py:228) |
| `RESEND_API_KEY` | API-ключ Resend (альтернатива паролю) | [app.py:228](app.py:228) |
| `MAIL_DEFAULT_SENDER` | Адрес отправителя | [app.py:231-234](app.py:231) |
| `YANDEX_CLIENT_ID` | OAuth Yandex | [app.py:248](app.py:248) |
| `YANDEX_CLIENT_SECRET` | OAuth Yandex secret | [app.py:249](app.py:249) |
| `TELEGRAM_BOT_USERNAME` | Имя бота Telegram | [app.py:253](app.py:253) |
| `PLAUSIBLE_DOMAIN` | Домен в Plausible Analytics | [app.py:255](app.py:255) |
| `YANDEX_METRIKA_ID` | ID счётчика Яндекс.Метрики | [app.py:257](app.py:257) |
| `OPENROUTER_API_KEY` | Ключ OpenRouter | [app.py:2360](app.py:2360) |
| `VAPID_PUBLIC_KEY` | VAPID public key для Web Push | [app.py:1616](app.py:1616) |
| `VAPID_PRIVATE_KEY` | VAPID private key | [app.py:1617](app.py:1617) |
| `VAPID_CLAIM_EMAIL` | Email для VAPID claims | [app.py:1618](app.py:1618) |
| `ENABLE_SCHEDULER` | Вкл/выкл APScheduler | [app.py:2000](app.py:2000) |
| `OLYMPIAD_AUTOSEED` | Автосид олимпиадного раздела | [app.py:1087](app.py:1087) |
| `VSOSH9_2027_FORCE_IMPORT` | Force-import ВсОШ-9 2027 | [app.py:1116](app.py:1116) |
| `VSOSH10_2027_FORCE_IMPORT` | Force-import ВсОШ 10/11 2027 | [app.py:1133](app.py:1133) |
| `ADAPTIVE_FORCE_IMPORT` | Force-import adaptive bank | [app.py:1150](app.py:1150) |
| `LATEX_ROOT_DB_FIX` | Автофикс LaTeX-корней в БД | [app.py:1168](app.py:1168) |
| `GIT_COMMIT` | SHA коммита (ручной) | [app.py:2828](app.py:2828) |

### 2.4. ENABLE_SCHEDULER

[`app.py:2000`](app.py:2000): `if os.environ.get("ENABLE_SCHEDULER", "1") != "0": scheduler.start()`.  
По умолчанию — **включен** (значение `"1"`). При `ENABLE_SCHEDULER=0` планировщик не запускается.  
Под его управлением 7 cron-задач ([`app.py:1626-1997`](app.py:1626)):

| ID задачи | Расписание | Назначение |
|-----------|-----------|------------|
| `daily_streak_reset` | 00:00 MSK | Сброс streak'ов |
| `daily_quest_deadline_reminder` | 18:00, 21:00 MSK | Напоминание о задачах дня |
| `curator_evening_notification` | 19:00, 20:00, 21:00 MSK | Вечерняя проверка куратора |
| `curator_morning_prep_reminder` | 09:00 MSK | Утреннее напоминание о цикле подготовки |
| `curator_evening_prep_generate` | 18:00 MSK | Вечерняя генерация задач цикла |
| `process_pregen_queue` | Каждые 30 мин | Обработка очереди предгенерации |
| `daily_midnight_assign` | 00:05 MSK | Автоназначение задач дня |

---

## 3. МАРШРУТЫ

### 3.1. Полный вывод url\_map

Выполнена команда `python -c "from app import app; ..."` — вывод (443 правила) сохранён в [`cmd-1785512581143.txt`].  
**Примечание**: в выводе присутствуют 443 правила, включая статические `/static/<path:filename>` и `/scheduler/*` (APScheduler API). Суммарно ~440 URL-правил.

### 3.2. Группировка маршрутов по разделам

#### Задачи дня
- `GET /daily-set` → `daily_set_page`
- `GET /daily_tasks/` → `daily_tasks.get_daily_tasks`
- `GET /daily_tasks/<int:item_id>/hint` → `daily_tasks.get_hint`
- `POST /daily_tasks/<int:item_id>/solve` → `daily_tasks.solve_task_preview`
- `POST /daily_tasks/<int:item_id>/submit` → `daily_tasks.submit_answer`
- `POST /daily_tasks/<int:item_id>/submit_ai` → `daily_tasks.submit_answer_ai`
- `GET /daily_tasks/calendar` → `daily_tasks.calendar_stats`
- `GET /daily_tasks/day_history/<date_iso>` → `daily_tasks.day_history`
- `GET /daily_tasks/job_status` → `daily_tasks.job_status`
- `POST /daily_tasks/regenerate` → `daily_tasks.regenerate`
- `GET /daily_tasks/static/<path:filename>` → `daily_tasks.static`
- `GET /daily_tasks/status` → `daily_tasks.daily_tasks_pool_status`

#### Олимпиады (старый раздел)
- `GET /olympiads` → `olympiads`
- `POST /olympiads/open` → `olympiad_open`
- `GET /olympiads/solution/<int:combo_id>` → `olympiad_solution`

#### Олимпиады (новый раздел `/olympiads/*`)
- `GET /olympiads/` → `olympiad.catalog_index`
- `GET /olympiads/course-probnik` → `olympiad.course_probnik`
- `GET /olympiads/course-probnik/10` → `olympiad.course_probnik_10`
- `GET /olympiads/course-probnik/11` → `olympiad.course_probnik_11`
- `GET /olympiads/course/<int:grade>` → `olympiad.vsosh_course`
- `GET /olympiads/courses` → `olympiad.catalog`
- `GET /olympiads/methods` → `olympiad.methods`
- `GET /olympiads/methods/<method_code>` → `olympiad.method_detail`
- `GET /olympiads/methods/section/<int:grade>/<section_name>` → `olympiad.method_section`
- `GET /olympiads/methods/task/<method_task_id>` → `olympiad.method_task`
- `GET /olympiads/my-progress` → `olympiad.my_progress`
- `GET /olympiads/predict-methods` → `olympiad.predict_methods`
- `GET /olympiads/probnik/<code>` → `olympiad.probnik`
- `GET /olympiads/probnik/<code>/active` → `olympiad.stage_active`
- `POST /olympiads/probnik/<code>/start` → `olympiad.stage_start`
- `GET,POST /olympiads/probnik/<code>/submit` → `olympiad.stage_submit`
- `GET /olympiads/task/<int:task_id>` → `olympiad.task`
- `POST /olympiads/task/<int:task_id>/attempt` → `olympiad.task_attempt`
- `POST /olympiads/task/<int:task_id>/submit` → `olympiad.task_submit`

#### Куратор подготовки
- `GET /prep/` → `prep.dashboard`
- `GET /prep/<int:plan_id>` → `prep.plan_detail`
- `DELETE /prep/<int:plan_id>` → `prep.delete_plan`
- `GET /prep/<int:plan_id>/day/<int:day_id>` → `prep.day_detail`
- `POST /prep/<int:plan_id>/pause` → `prep.pause_plan`
- `POST /prep/<int:plan_id>/resume` → `prep.resume_plan`
- `GET /prep/<int:plan_id>/today` → `prep.today_problems`
- `POST /prep/<int:plan_id>/today/complete/<int:problem_id>` → `prep.complete_problem`
- `POST /prep/<int:plan_id>/today/upload_photo/<int:problem_id>` → `prep.upload_solution_photo`
- `GET /prep/coach` → `prep.coach`
- `POST /prep/coach/chat` → `prep.coach_chat`
- `POST /prep/coach/daily/submit` → `prep.coach_daily_submit`
- `POST /prep/coach/day/complete` → `prep.coach_day_complete`
- `GET /prep/coach/greeting` → `prep.coach_greeting`
- `GET /prep/coach/history` → `prep.coach_history`
- `POST /prep/coach/history/delete` → `prep.coach_history_delete`
- `POST /prep/coach/onboarding/submit` → `prep.coach_onboarding_submit`
- `POST /prep/coach/prep/submit_test` → `prep.coach_prep_submit_test`
- `POST /prep/coach/questionnaire/answer` → `prep.coach_questionnaire_answer_redirect`
- `POST /prep/coach/questionnaire/start` → `prep.coach_questionnaire_start_redirect`
- `POST /prep/coach/set_grade` → `prep.coach_set_grade`
- `POST /prep/coach/test/start` → `prep.coach_test_start`
- `GET /prep/new` → `prep.new_plan_form`
- `POST /prep/new` → `prep.create_plan`
- `GET /prep/onboarding` → `prep.onboarding_page`
- `POST /prep/onboarding/anchor` → `prep.onboarding_anchor`
- `POST /prep/onboarding/answer` → `prep.onboarding_answer`
- `GET /prep/probe` → `prep.morning_probe`
- `POST /prep/probe/submit` → `prep.probe_submit`

#### Анкета / Онбординг
- `GET /prep/onboarding` → `prep.onboarding_page`
- `POST /prep/onboarding/anchor` → `prep.onboarding_anchor`
- `POST /prep/onboarding/answer` → `prep.onboarding_answer`
- `POST /prep/coach/onboarding/submit` → `prep.coach_onboarding_submit`
- `POST /prep/coach/questionnaire/start` → `prep.coach_questionnaire_start_redirect`
- `POST /prep/coach/questionnaire/answer` → `prep.coach_questionnaire_answer_redirect`
- `POST /prep/coach/set_grade` → `prep.coach_set_grade`
- `POST /curator/onboarding` → `curator.api_onboarding`

#### Сообщество
- `GET /social` → `social_page`
- `GET /friends` → `friends_page`
- `POST /friends/accept/<int:rid>` → `accept_friend_request`
- `POST /friends/cancel/<int:rid>` → `cancel_friend_request`
- `POST /friends/decline/<int:rid>` → `decline_friend_request`
- `POST /friends/remove/<int:uid>` → `remove_friend`
- `POST /friends/request/<int:uid>` → `send_friend_request`
- `GET /chat` → `chat_page`
- `GET /chat/<int:friend_id>` → `chat_page`
- `GET /leaderboard` → `leaderboard`
- `GET /notifications` → `notifications_page`
- `GET /user/<int:user_id>` → `public_profile`
- `GET /u/<nickname>` → `profile_by_nickname`
- `GET /groups/<int:group_id>` → `group_page`

#### Доска / Чертежи
- `GET /drawing` → `drawing.drawing_page`
- `GET /drawing/history` → `drawing_history.history_page`
- `GET /whiteboard` → `drawing.whiteboard_page`
- `GET /call` → `call_page`
- `GET /conference` → `conference_page`
- `POST /api/drawing/generate` → `drawing.api_drawing_generate`

#### Профиль
- `GET /profile` → `profile`
- `POST /update_nickname` → `update_nickname`
- `GET /student/<int:student_id>` → `student_profile`
- `POST /api/social/set-nickname` → `set_nickname`
- `POST /api/set_nickname` → `api_set_nickname`
- `GET /api/profile` → `api_get_profile`
- `GET /api/profile/<nickname>` → `api_profile_view`
- `GET /account/privacy` → `account.privacy_page`
- `POST /account/delete` → `account.delete_account`
- `POST /account/merge` → `account.merge_accounts`
- `POST /account/merge/cancel` → `account.merge_cancel`
- `GET /account/merge_preview` → `account.merge_preview`
- `POST /account/ml-consent` → `account.toggle_ml_consent`

#### Авторизация
- `GET,POST /login` → `login`
- `GET,POST /verify-code` → `verify_code`
- `GET /logout` → `logout`
- `GET /dev_login` → `dev_login`
- `GET /yandex_login` → `yandex_login_start`
- `GET /yandex_receiver` → `yandex_receiver`
- `POST /auth/yandex/login` → `yandex_login`
- `GET /link_yandex` → `link_yandex`
- `GET,POST /auth/telegram/callback` → `telegram_auth.telegram_callback`
- `POST /auth/telegram/unlink` → `telegram_auth.telegram_unlink`

#### Служебные
- `GET /health` → `health_check`
- `GET /healthz` → `healthz`
- `GET /debug/routes` → `debug_routes`
- `GET /debug-sentry` → `trigger_error_for_sentry`
- `GET /__version` → `__version`
- `GET /__diag/method/<method_code>` → `__diag_method`
- `GET /scheduler` → `scheduler.get_scheduler_info`
- `GET /scheduler/jobs` → `scheduler.get_jobs`
- `...` (14 эндпоинтов APScheduler)
- `GET /matstat` → `matstat` (только для whitelist-пользователей)
- `GET /sql` → `sql_page`
- `GET /subscribe` → `subscribe_page`
- `GET /admin/support` → `admin_support.admin_support_inbox`
- `POST /admin/seed-secrets` → `admin_seed_secrets`
- `POST /admin/toggle_task_flag/<int:task_id>` → `admin_toggle_task_flag`
- `POST /admin/fix-theory-blocks` → `admin_fix_theory_blocks`
- `GET,POST /admin/fix_latex_rac` → `admin_fix_latex_rac`
- `GET /admin/needs_review` → `admin_needs_review`
- `POST /admin/needs_review/action/<int:task_id>` → `admin_needs_review_action`
- `GET /admin/tutor_stats` → `admin_tutor_stats`

#### Маршруты без ссылок в шаблонах (вероятно неиспользуемые)

- `GET /matstat` — ссылка только в выпадающем меню «Тренировка» для whitelist-пользователей (pavelznaka/victorkrivenko/victor) [`templates/base.html:203`](templates/base.html:203)
- `GET /sql` — NOT FOUND в шаблонах (нет ссылок)
- `GET /daily-set` — NOT FOUND в шаблонах (перенаправляет на `/daily_tasks/`)
- `GET /api/concierge/ask` (legacy) — скорее всего только через JS
- `GET /api/concierge/intents` (legacy) — скорее всего только через JS
- Адаптивные тесты (`/adaptive_test/*`, `/olympiad-test/*`) — ссылки есть в лендинге `/welcome`

---

## 4. МОДЕЛИ БД

### 4.1. Все модели

#### Из [`models.py`](models.py:1) (основной файл, 1533 строки)

| Класс | Таблица | Ключевые поля | Связи |
|-------|---------|--------------|-------|
| `User` | `users` | `id(PK)`, `email(unique,index)`, `nickname(unique,index)`, `name`, `avatar_url`, `auth_code`, `code_expires`, `math_level`, `ai_report`, `recommended_topics`, `onboarding_completed(bool)`, `total_problems_solved`, `current_level`, `experience_points`, `mock_exams_passed`, `adaptive_tests_completed`, `highest_difficulty_solved`, `current_plan(default='free')`, `plan_expires_at`, `generation_count_today`, `generation_reset_date`, `gens_extra_purchased`, `gens_unlimited`, `is_guest(bool)`, `device_id(index)`, `preferred_grade`, `ml_training_consent`, `created_at`, `last_login`, `onboarded_at`, `telegram_id(unique,index)`, `telegram_username`, `questionnaire_state` | → `UserTopicProgress`, `AdaptiveTestResult`, `CuratorState`(1:1) |
| `OAuthAccount` | `oauth_accounts` | `id(PK)`, `user_id(FK→users)`, `provider`, `provider_user_id`; unique(provider, provider_user_id) | → `User` |
| `ChatMessage` | `chat_messages` | `id(PK)`, `user_id(FK)`, `agent_type(index)`, `role`, `content`, `timestamp(index)` | → `User` |
| `MockExam` | `mock_exams` | `id(PK)`, `user_id(FK)`, `status`, `ai_feedback`, `score` | → `User` |
| `MockExamTask` | `mock_exam_tasks` | `id(PK)`, `exam_id(FK)`, `problem_id`, `user_answer`, `is_correct`, `ai_comment` | → `MockExam` |
| `SecretTopic` | `secret_topics` | `id(PK)`, `slug(unique)`, `title`, `content` | — |
| `AdaptiveTest` | `adaptive_tests` | `id(PK)`, `user_id(FK)`, `subject`, `grade`, `num_problems`, `initial_ability`, `current_ability`, `status`, `final_ability`, `accuracy`, `ai_analysis` | → `User`, `AdaptiveTestProblem` |
| `AdaptiveTestProblem` | `adaptive_test_problems` | `id(PK)`, `test_id(FK)`, `problem_id`, `sequence_number`, `user_ability_before`, `problem_difficulty`, `user_answer`, `is_correct`, `ai_feedback` | → `AdaptiveTest` |
| `Friendship` | `friendships` | `id(PK)`, `requester_id(FK→users,index)`, `addressee_id(FK→users,index)`, `status`; unique(requester,addressee) | → `User`(2 стороны) |
| `DirectMessage` | `direct_messages` | `id(PK)`, `sender_id(FK,index)`, `recipient_id(FK,index)`, `kind`, `body`, `task_id(index)`, `reply_to_id(index)`, `edited_at`, `deleted_at`, `forwarded_from_id(index)`, `delivered_at`, `read_at`, `is_read(index)`, attachment_*, `created_at(index)` | → `User`(sender+recipient) |
| `Notification` | `notifications` | `id(PK)`, `user_id(FK,index)`, `type`, `from_user_id(FK)`, `data`, `read(index)`, `created_at(index)` | → `User` |
| `PushSubscription` | `push_subscriptions` | `id(PK)`, `user_id(FK,index)`, `endpoint`, `p256dh_key`, `auth_key`, `user_agent`, `created_at`, `updated_at` | → `User` |
| `UserPresence` | `user_presence` | `user_id(PK/FK)`, `last_seen(index)`, `typing_to_id(FK)`, `typing_at` | → `User` |
| `MessageReaction` | `message_reactions` | `id(PK)`, `message_id(FK→direct_messages,index)`, `user_id(FK,index)`, `emoji`; unique(message,user,emoji) | → `DirectMessage`, `User` |
| `Mentorship` | `mentorships` | `id(PK)`, `teacher_id(FK,index)`, `student_id(FK,index)`, `status`; unique(teacher,student), check(teacher≠student) | → `User`(teacher+student) |
| `OlympiadSecret` | `olympiad_secrets` | `id(PK)`, `topic(index)`, `title`, `content`, `difficulty_level` | — |
| **`AdaptiveTask`** | `adaptive_tasks` | см. раздел 4.3 | — |
| `UserTopicProgress` | `user_topic_progress` | `id(PK)`, `user_id(FK)`, `topic(index)`, `topic_name_ru`, `current_level`, `tasks_attempted`, `tasks_correct` | → `User` |
| `AdaptiveTestResult` | `adaptive_test_results` | `id(PK)`, `user_id(FK)`, `topic`, `class_level`, `final_level`, `tasks_correct`, `tasks_total`, `answers_history`, `started_at`, `completed_at` | → `User` |
| `DailyQuest` | `daily_quests` | `id(PK)`, `user_id(FK)`, `date(index)`, `task_ids(TEXT)`, `completed_count`, `total_count(default=10)`, `xp_earned`, `ai_comment`, `solved_indices(TEXT)`, `attempts_map(TEXT)`, `failed_indices(JSON)`, `last_regenerated_at`, `created_at`, `completed_at`; unique(user,date) | → `User` |
| `UserStreak` | `user_streaks` | `id(PK)`, `user_id(FK,unique)`, `current_streak`, `longest_streak`, `last_active_date`, `freeze_available`, `freeze_used_at` | → `User`(1:1) |
| `TopicMastery` | `topic_mastery` | `id(PK)`, `user_id(FK)`, `topic`, `grade`, `solved`, `attempts`, `avg_level`, `mastery`; unique(user,topic,grade) | → `User` |
| `OlympiadGenerationLog` | `olympiad_generation_log` | `id(PK)`, `olympiad_slug`, `round_key`, `class_level`, `attempts`, `success`, `errors_json`, `user_id(FK)` | → `User` |
| `TestResult` | `test_results_detail` | `id(PK)`, `user_id(FK,index)`, `device_id`, `test_type`, `class_level`, `topic`, `task_id`, `difficulty`, `is_correct`, `user_answer`, `time_spent_sec`, `rating_delta`, `rating_after`, `created_at(index)` | → `User` |
| `UserProgress` | `user_progress` | `user_id(FK)`, `topic`, `class_level` — составной PK, `rating`, `tasks_solved`, `tasks_attempted`, `current_difficulty`, `last_activity` | → `User` |
| `OlympiadPrep` | `olympiad_prep` | `id(PK)`, `slug(unique,index)`, `name`, `short_name`, `description`, `grades(TEXT/JSON)`, `stages(TEXT/JSON)`, `official_url`, `logo_path`, `color_hex`, `sort_order(index)`, `is_active` | — |
| `PrepPlan` | `prep_plans` | `id(PK)`, `user_id(FK,index)`, `olympiad_id(FK→olympiad_prep,index)`, `target_stage`, `target_grade`, `start_date`, `target_date`, `baseline_radar(TEXT)`, `current_radar(TEXT)`, `daily_task_count(default=5)`, `status(index)`, `current_streak`, `longest_streak` | → `User`, `OlympiadPrep`, `PrepDay` |
| `PrepDay` | `prep_days` | `id(PK)`, `plan_id(FK→prep_plans,index)`, `date(index)`, `target_topics(TEXT)`, `problem_ids(TEXT)`, `completed_problem_ids(TEXT)`, `day_score`, `status(index)` | → `PrepPlan` |
| `BrokenTaskLog` | `broken_task_log` | `id(PK)`, `task_id(index)`, `surface(index)`, `reasons`, `hits`, `detected_at(index)` | — |
| `TaskSolution` | `task_solutions` | `id(PK)`, `user_id(FK,index)`, `task_id(FK→adaptive_tasks,index)`, `plan_id(FK,index)`, `day_id(FK,index)`, `user_answer`, `user_solution`, `original_photo_url`, `photo_hash(index)`, `ocr_raw_output`, `ocr_corrected`, `was_corrected`, `is_correct`, `feedback_json`, `consent_for_training`, `quality_score`, `created_at(index)` | → `User`, `AdaptiveTask`, `PrepPlan`, `PrepDay` |
| `DrawingGeneration` | `drawing_generations` | `id(PK)`, `user_id(FK,index)`, `problem_sha256(index)`, `problem`, `generated_code`, `model`, `status(index)`, `error`, `repair_iters`, `render_ms`, `cost_usd`, `image_path`, `image_size`, critique_*, `created_at(index)` | → `User` |
| `GroupChat` | `group_chats` | `id(PK)`, `name`, `avatar_emoji`, `owner_id(FK,index)`, `created_at` | → `User` |
| `GroupMember` | `group_members` | `id(PK)`, `group_id(FK,index)`, `user_id(FK,index)`, `role`, `joined_at`; unique(group,user) | → `GroupChat`, `User` |
| `GroupMessage` | `group_messages` | `id(PK)`, `group_id(FK,index)`, `sender_id(FK,index)`, `kind`, `body`, attachment_*, `created_at(index)` | → `GroupChat`, `User` |

#### Из [`models_curator.py`](models_curator.py:1) (57 строк)

| Класс | Таблица | Ключевые поля |
|-------|---------|--------------|
| `CuratorState` | `curator_state` | `id(PK)`, `user_id(FK→users,unique,index)`, `target_olympiads(JSON)`, `grade`, `goal_text`, `prep_plan(JSON)`, `prep_state(JSON)`, `level_mu(Float)`, `level_sigma(Float)`, `level_by_section(TEXT)`, `level_by_theme(TEXT)`, `probe_json(TEXT)`, `level_updated_at(TEXT)`, `onboarding_done(bool)`, `last_diagnostic_id(FK→adaptive_test_results)`, `summary`, `created_at`, `updated_at` |
| `Subtopic` | `subtopics` | `id(PK)`, `slug(unique,index)`, `title`, `parent_topic(index)`, `olympiad_weights(JSON)`, `is_active` |
| `SubtopicProgress` | `subtopic_progress` | `id(PK)`, `user_id(FK,index)`, `subtopic_id(FK,index)`, `mastery(Float)`, `attempts`, `correct`, `last_seen_at`, `updated_at`; unique(user,subtopic) |

#### Из [`models_grade.py`](models_grade.py:1) (140 строк)

| Класс | Таблица | Ключевые поля |
|-------|---------|--------------|
| `GradeTask` | `grade_tasks` | `id(PK)`, `source_id(unique,index)`, `grade(index)`, `domain(index)`, `subject`, `level(index)`, `topic`, `statement`, `answer`, `solution`, `status`, `tags(JSON)`, `created_at` |

#### Из [`models_olympiad.py`](models_olympiad.py:1) (519 строк)

| Класс | Таблица | Ключевые поля |
|-------|---------|--------------|
| `Probnik` | `olympiad_probniks` | `id(PK)`, `code(unique,index)`, `type(Enum:topic/stage)`, `number`, `title`, `description`, `competition`, `grade`, `season_year`, `duration_minutes`, `max_score`, `threshold_prize`, `threshold_winner`, `sort_order`, `is_published`, `created_at`; unique(competition,grade,season_year,type,number) |
| `OlympiadTask` | `olympiad_tasks` | `id(PK)`, `probnik_id(FK→olympiad_probniks,index)`, `number`, `sort_order`, `difficulty(Enum:green/yellow/orange/red)`, `method_primary`, `method_secondary`, `condition_md`, `idea_md`, `solution_md`, `answer`, `source_prototype`, `estimated_minutes`, `max_score`, `method_codes(JSON)`, `year(index)`, `stage(index)`; unique(probnik,number) |
| `TheoryBlock` | `olympiad_theory` | `id(PK)`, `method_code(unique,index)`, `method_name`, `section(Enum:A-H)`, `definition_md`, `main_theorems_md`, `typical_techniques_md`, `triggers_md`, `worked_example_md`, `pitfalls_md`, `why_it_works_md`, `related_methods(JSON)`, `signal_phrases(JSON)`, `first_moves(JSON)`, `prerequisites(JSON)`, `leads_to(JSON)`, `grades(JSON)`, `recommended_competitions(JSON)`, `difficulty_level(index)`, `frequency_vsosh_9(index)`, `total_count(index)`, `share_percent`, `sort_order`, `created_at` |
| `ProbnikTheory` | `olympiad_probnik_theory` | `probnik_id(PK/FK)`, `theory_block_id(PK/FK)`, `display_order` |
| `TaskAttempt` | `olympiad_task_attempts` | `id(PK)`, `user_id(FK,index)`, `task_id(FK→olympiad_tasks,index)`, `status(String)`, `self_score`, `time_spent_seconds`, `note`, `started_at`, `finished_at`; unique(user,task) |
| `StageAttempt` | `olympiad_stage_attempts` | `id(PK)`, `user_id(FK,index)`, `probnik_id(FK,index)`, `started_at`, `finished_at`, `total_score`, `result(Enum:participant/prize/winner)`, `task_scores(JSON)`, `report_md` |

#### Из [`daily_tasks/models.py`](daily_tasks/models.py:1) (301 строка)

| Класс | Таблица | Ключевые поля |
|-------|---------|--------------|
| `DailyTaskSet` | `daily_task_sets` | `id(PK)`, `user_id(FK,index)`, `target_date(index)`, `class_level`, `status(pending/generating/ready/failed/expired)`, `generated_at`, `triggered_by`, `reason_summary`, `pipeline_log`, `total_cost_usd`; unique(user,date) |
| `DailyTaskItem` | `daily_task_items` | `id(PK)`, `daily_set_id(FK→daily_task_sets,index)`, `position(1..10)`, `slot_kind`, `subject`, `topic`, `subtopic`, `difficulty_level`, `weakness_score`, `reason`, `is_calibration(bool)`, `task_text`, `correct_answer`, `solution`, `hints(TEXT/JSON)`, `gemini_spec_json`, `opus_iterations`, `gpt_audit_json`, `is_flagged`, `flag_reason`, `status(pending/approved/flagged/skipped)`, `user_answer`, `is_correct`, `answered_at`, `time_spent_seconds` |
| `DailyGenerationJob` | `daily_generation_jobs` | `id(PK)`, `user_id(FK,index)`, `target_date(index)`, `daily_set_id(FK)`, `state(queued/running/completed/failed)`, `current_step`, `progress_pct`, `error_message`, `started_at`, `finished_at`, `created_at`; unique(user,date) |
| `TaskPool` | `task_pool` | `id(PK)`, `cache_key(unique)`, `subject`, `grade`, `profile_snapshot(TEXT)`, `tasks(TEXT/JSON)`, `specs(TEXT/JSON)`, `status`, `valid_count`, `created_at`, `used_count`, `expires_at` |
| `UserTaskAssignment` | `user_task_assignments` | `id(PK)`, `user_id(FK,index)`, `pool_id(FK→task_pool,index)`, `task_positions(TEXT/JSON)`, `assigned_at` |
| `ThematicDaySet` | `thematic_day_sets` | `id(PK)`, `user_id(FK,index)`, `target_date(index)`, `subject`, `class_level`, `status(generating/ready/failed)`, `triggered_by`, `current_step`, `progress_pct`, `tasks_json`, `pipeline_log`, `error_message`, `total_cost_usd`, timing fields; unique(user,date) |
| `PreGenQueue` | `pre_gen_queue` | `id(PK)`, `user_id(FK,index)`, `target_date(index)`, `cache_key(index)`, `pool_id(FK→task_pool,index)`, `status(queued→generating→ready/failed→consumed)`, `profile_json`, `release_at`, `expires_at`, `created_at`, `updated_at`; unique(user,date) |

### 4.2. Поля онбординга

| Модель | Поле | Тип | Назначение | Строки |
|--------|------|-----|-----------|--------|
| `User` | `onboarding_completed` | `Boolean` | Флаг завершения AI-онбординга | [models.py:31](models.py:31) |
| `User` | `math_level` | `String(20)` | Уровень: beginner/intermediate/advanced | [models.py:28](models.py:28) |
| `User` | `ai_report` | `Text` | Персональный отчёт от AI | [models.py:29](models.py:29) |
| `User` | `recommended_topics` | `String(200)` | JSON-строка с темами | [models.py:30](models.py:30) |
| `User` | `onboarded_at` | `DateTime` | Timestamp первого визита /about?onboarding=1 | [models.py:71](models.py:71) |
| `User` | `questionnaire_state` | `Text` | Состояние диагностической анкеты (JSON) | [models.py:78](models.py:78) |
| `User` | `preferred_grade` | `Integer` | Выбранный класс для Daily Quest | [models.py:55-56](models.py:55) |
| `CuratorState` | `onboarding_done` | `Boolean` | Флаг завершения кураторского онбординга | [models_curator.py:26](models_curator.py:26) |
| `CuratorState` | `prep_state` | `JSON` | Состояние онбординга куратора (test_queue, last_test, …) | [models_curator.py:19](models_curator.py:19) |

### 4.3. Поля уровня mu/sigma

| Модель | Поле | Тип | Назначение | Строки |
|--------|------|-----|-----------|--------|
| `CuratorState` | `level_mu` | `Float` | Точечная оценка уровня (IRT) | [models_curator.py:20](models_curator.py:20) |
| `CuratorState` | `level_sigma` | `Float` | Неопределённость оценки уровня | [models_curator.py:21](models_curator.py:21) |
| `CuratorState` | `level_by_section` | `Text` | Уровни по разделам (JSON) | [models_curator.py:22](models_curator.py:22) |
| `CuratorState` | `level_updated_at` | `Text` | Timestamp обновления уровня | [models_curator.py:25](models_curator.py:25) |
| `AdaptiveTest` | `current_ability` | `Float` | Текущая способность (IRT θ) | [models.py:368](models.py:368) |

### 4.4. Поля задач дня

| Модель | Поле | Назначение |
|--------|------|-----------|
| `DailyTaskSet` | `target_date` | На какую дату задачи |
| `DailyTaskSet` | `class_level` | Класс ученика |
| `DailyTaskSet` | `status` | pending → generating → ready / failed / expired |
| `DailyTaskItem` | `position` | 1..10 — порядок в сете |
| `DailyTaskItem` | `slot_kind` | Тип слота: weakness/review/new_topic/mixed/calibration |
| `DailyTaskItem` | `task_text`, `correct_answer`, `solution`, `hints` | Контент задачи |
| `DailyTaskItem` | `user_answer`, `is_correct`, `answered_at` | Ответ пользователя |
| `DailyTaskItem` | `status` | pending → approved / flagged / skipped |

### 4.5. Поля среза / дня цикла / целей ученика / настройки числа задач

| Модель | Поле | Назначение | Строки |
|--------|------|-----------|--------|
| `PrepPlan` | `daily_task_count` | Число задач в день (default=5) | [models.py:1202](models.py:1202) |
| `PrepPlan` | `target_grade` | Целевой класс ученика | [models.py:1197](models.py:1197) |
| `PrepPlan` | `target_stage` | Целевой этап олимпиады | [models.py:1196](models.py:1196) |
| `PrepPlan` | `baseline_radar` | JSON-радар начального среза | [models.py:1200](models.py:1200) |
| `PrepPlan` | `current_radar` | JSON-радар текущего среза | [models.py:1201](models.py:1201) |
| `PrepDay` | `date` | Дата дня цикла | [models.py:1291](models.py:1291) |
| `PrepDay` | `status` | upcoming/today/completed/missed | [models.py:1296](models.py:1296) |
| `CuratorState` | `goal_text` | Текстовая цель ученика | [models_curator.py:17](models_curator.py:17) |
| `CuratorState` | `target_olympiads` | JSON-список целевых олимпиад | [models_curator.py:14](models_curator.py:14) |
| `CuratorState` | `prep_plan` | JSON-план подготовки | [models_curator.py:18](models_curator.py:18) |

### 4.6. Поля AdaptiveTask

[`models.py:814-883`](models.py:814):

| Поле | Тип | Назначение |
|------|-----|-----------|
| `id` | `Integer PK` | |
| `class_level` | `Integer, index` | Класс (5-11) |
| `difficulty_level` | `Integer, index` | Уровень сложности 1-7 (также есть записи с 8) |
| `topic` | `String(200), index` | Тема из матрицы 25 тем |
| `subtopic` | `String(100), index` | Подтема |
| `task_text` | `Text` | Условие задачи (LaTeX) |
| `solution` | `Text` | Полное авторское решение |
| `correct_answer` | `Text` | Правильный ответ |
| `criteria_1_point` | `Text` | Критерий на 1 балл |
| `criteria_2_points` | `Text` | Критерий на 2 балла |
| `is_flagged` | `Boolean, index` | Помечена как некорректная |
| `reports_count` | `Integer` | Количество жалоб |
| `flagged_reason` | `Text` | Причина пометки |
| `attempts_count` | `Integer` | Всего попыток решения |
| `solves_count` | `Integer` | Успешных решений |
| `actual_solve_rate` | `Float` | Реальный % решивших |
| `suggested_level` | `Integer` | Предложенный уровень |
| `needs_reclassification` | `Boolean, index` | Требует переклассификации |
| `last_calibrated_at` | `DateTime` | Последняя калибровка |
| `subject` | `String(20), index` | Предмет (algebra/geometry/…) |
| `source_id` | `String(120), index` | Стабильный ID из датасета |
| `task_type` | `Text` | Тип задачи |
| `source` | `Text, index` | Источник датасета |
| `origin` | `String(16)` | 'generated' / 'olympiad' |
| `methods_json` | `Text` | JSON методов решения |
| `theme_id` | `String(50), index` | ID темы |
| `theme_title` | `String(300)` | Человеческое название темы |
| `needs_review` | `Boolean, index` | Флаг AI-тьютор self-check |
| `llm_suggested_answer` | `Text` | Предложенный LLM ответ |
| `llm_suggested_solution` | `Text` | Предложенное LLM решение |
| `review_reason` | `Text` | Причина ревью |
| `review_flagged_at` | `DateTime` | Когда помечено на ревью |
| `created_at` | `DateTime` | |

---

## 5. НАВИГАЦИЯ

### 5.1. Главное меню

Задаётся в [`templates/base.html`](templates/base.html:152-331), строки 152-331 (desktop header) и строки 348-502 (mobile drawer).  
Два представления: десктопный `<header class="header">` (строка 152) и мобильный `<aside class="mobile-drawer">` (строка 349).

**Полный список пунктов десктопного меню:**

| # | Пункт | URL | Тип | Строки |
|---|-------|-----|-----|--------|
| 1 | Логотип FORMYLA | `/olympiads/methods` | `<a>` | [base.html:153](templates/base.html:153) |
| 2 | 🔥 Задачи дня | `/daily_tasks/` | nav-pill | [base.html:179](templates/base.html:179) |
| 3 | 📚 Тренировка ▾ | dropdown | dropdown | [base.html:195](templates/base.html:195) |
| 3a | └ 📐 Темы | `/` | | [base.html:200](templates/base.html:200) |
| 3b | └ 📊 Тест по темам | `/probniks` | | [base.html:201](templates/base.html:201) |
| 3c | └ 🗝️ Секреты | `/secrets` | | [base.html:202](templates/base.html:202) |
| 3d | └ 📊 Мат.статистика | `/matstat` | whitelist only | [base.html:203](templates/base.html:203) |
| 4 | 🏆 Олимпиады ▾ | dropdown | dropdown | [base.html:208](templates/base.html:208) |
| 4a | └ 📖 Каталог | `/olympiads` | | [base.html:213](templates/base.html:213) |
| 4b | └ 🆕 Курсы (ВсОШ-2027) | `/olympiads/courses` | | [base.html:214](templates/base.html:214) |
| 4c | └ 📚 Каталог методов (102) | `/olympiads/methods` | | [base.html:215](templates/base.html:215) |
| 4d | └ 📅 Календарь олимпиад | `/olympiad-prep/calendar` | | [base.html:216](templates/base.html:216) |
| 4e | └ 📈 Мой прогресс | `/olympiads/my-progress` | только для auth | [base.html:218](templates/base.html:218) |
| 5 | 🧭 Куратор подготовки ▾ | dropdown | dropdown | [base.html:224](templates/base.html:224) |
| 5a | └ 🧭 Чат-куратор | `/prep/coach` | | [base.html:229](templates/base.html:229) |
| 6 | 🎨 Доска ▾ | dropdown | dropdown | [base.html:234](templates/base.html:234) |
| 6a | └ 📐 ИИ-чертёж по задаче | `/drawing` | | [base.html:239](templates/base.html:239) |
| 6b | └ 🖍️ Доска и встреча | `/drawing?tab=whiteboard` | | [base.html:240](templates/base.html:240) |
| 6c | └ 🗂️ История чертежей | `/drawing/history` | auth only | [base.html:242](templates/base.html:242) |
| 7 | 💬 Тьютор | `javascript:void(0)` плавающий виджет | плоская ссылка | [base.html:249](templates/base.html:249) |
| 8 | 👥 Сообщество ▾ | dropdown | dropdown | [base.html:257](templates/base.html:257) |
| 8a | └ 🏆 Лидеры | `/leaderboard` | | [base.html:262](templates/base.html:262) |
| 8b | └ 🤝 Друзья | `/friends` | | [base.html:263](templates/base.html:263) |
| 8c | └ 💬 Чат | `/chat` | | [base.html:264](templates/base.html:264) |
| 9 | ℹ️ О сайте | `/about` | плоская ссылка | [base.html:269](templates/base.html:269) |
| 10 | ✍️ Написать отзыв | `/about#review-form` | плоская ссылка | [base.html:270](templates/base.html:270) |
| 11 | 🔍 Поиск | `/problems?q=...` | `<form>` | [base.html:274](templates/base.html:274) |
| 12 | 👤 Профиль | `/profile` | auth only, кнопка | [base.html:308](templates/base.html:308) |
| 13 | 🚀 Начать | `/login` | не-auth, кнопка | [base.html:323](templates/base.html:323) |

### 5.2. Ссылки на сообщество, доску, профиль

#### Сообщество (`/social`, `/friends`, `/chat`, `/leaderboard`):
- [`templates/base.html:257-266`](templates/base.html:257) — десктопное меню
- [`templates/base.html:447-459`](templates/base.html:447) — мобильное меню
- [`templates/base.html:524-537`](templates/base.html:524) — мобильная нижняя панель

#### Доска (`/drawing`, `/whiteboard`):
- Десктоп: [`templates/base.html:234-245`](templates/base.html:234)
- Мобильное: [`templates/base.html:440-444`](templates/base.html:440)
- Нижняя панель: NOT FOUND (нет ссылки на доску в bottom nav)

#### Профиль (`/profile`):
- Десктоп: [`templates/base.html:308-313`](templates/base.html:308)
- Мобильное: [`templates/base.html:480-484`](templates/base.html:480)
- Нижняя панель: [`templates/base.html:540-543`](templates/base.html:540)

---

## 6. МЕТОДЫ (102 олимпиадных метода)

### 6.1. Файл

[`data/olympiads/methods_catalog_105.json`](data/olympiads/methods_catalog_105.json:1) — 102 записи.

### 6.2. Формат

Каждая запись — JSON-объект с полями: `method_code`, `method_name`, `section`, `grades`, `recommended_competitions`, `difficulty_level`, `frequency_vsosh_9`, `sort_order`, `definition_md`, `main_theorems_md`, `typical_techniques_md`, `triggers_md`, `worked_example_md`, `pitfalls_md`, `why_it_works_md`, `signal_phrases`, `first_moves`, `prerequisites`, `leads_to`, `related_methods`.

### 6.3. Разбивка по секциям

| Секция | Число методов |
|--------|-------------|
| A | 5 |
| B | 7 |
| C | 14 |
| D | 15 |
| E | 27 |
| F | 21 |
| G | 8 |
| H | 5 |
| **Итого** | **102** |

### 6.4. Пример записи

```json
{
  "method_code": "A1",
  "method_name": "Метод подстановки и исключения",
  "section": "A",
  "grades": [5, 6, 7, 8, 9],
  "recommended_competitions": ["ВсОШ", "Ломоносов", "Физтех"],
  "difficulty_level": 1,
  "frequency_vsosh_9": 5,
  "sort_order": 1,
  ...
}
```

### 6.5. Связь метод ↔ подтема ↔ раздел

**Связи метод ↔ подтема в коде НЕТ.**  
Модель `TheoryBlock` (таблица `olympiad_theory`) содержит поле `section` (Enum: A-H), но **не содержит** поля `subtopic`. Поле `method_code` используется в `OlympiadTask.method_primary` и `OlympiadTask.method_secondary` ([`models_olympiad.py:152-153`](models_olympiad.py:152)) для привязки задачи к методу, но связки «метод → подтема» не существует ни в JSON-файле, ни в модели.

Разделы `A`-`H` — это классификация самих методов, а не привязка к школьным темам. В JSON нет поля `subtopic` или `subtopic_id`. В коде нет ни одной таблицы/связи, соединяющей `method_code` с `subtopic`.

---

## 7. ЗАДАЧИ

### 7.1. Задачи дня (DailyTaskSet / DailyTaskItem)

**Хранятся в БД** (SQLite `formyla.db`):

| Таблица | Строк | Поля |
|---------|-------|------|
| `daily_task_sets` | **5** (статусы: 3 ready, 2 failed) | `id`, `user_id`, `target_date`, `class_level`, `status`, `generated_at`, `triggered_by`, `reason_summary`, `pipeline_log`, `total_cost_usd` |
| `daily_task_items` | **50** (10 задач × 5 сетов) | `id`, `daily_set_id`, `position(1..10)`, `slot_kind`, `subject`, `topic`, `subtopic`, `difficulty_level`, `weakness_score`, `reason`, `is_calibration`, `task_text`, `correct_answer`, `solution`, `hints`, `gemini_spec_json`, `opus_iterations`, `gpt_audit_json`, `is_flagged`, `flag_reason`, `status`, `user_answer`, `is_correct`, `answered_at`, `time_spent_seconds` |
| `daily_generation_jobs` | (не запрошено) | состояние генерации |
| `task_pool` | **1** | кэш сгенерированных задач |
| `pre_gen_queue` | (не запрошено) | очередь предгенерации |

**Статусы DailyTaskSet**: `pending` → `generating` → `ready` / `failed` / `expired` ([`daily_tasks/models.py:27-28`](daily_tasks/models.py:27)).

**Статусы DailyTaskItem**: `pending` → `approved` / `flagged` / `skipped` ([`daily_tasks/models.py:103-104`](daily_tasks/models.py:103)).

### 7.2. Пул AdaptiveTask

**Таблица `adaptive_tasks`** — всего **8778 записей**.

**Разбивка по source**:

| Source | Количество |
|--------|-----------|
| `None` (NULL) | **8778** |

Значение `source = 'formyla_L1_L5_TOP5'` **не найдено** ни в одной записи. Все 8778 записей имеют `source IS NULL`. Вероятно, данные были загружены до добавления колонки `source` или через сидер, который не заполняет это поле.

**Разбивка по классам**:

| Класс | Записей |
|-------|---------|
| 5 | 1128 |
| 6 | 1128 |
| 7 | 1324 |
| 8 | 1385 |
| 9 | 1302 |
| 10 | 1279 |
| 11 | 1232 |

**Разбивка по уровням сложности**:

| Уровень | Записей |
|---------|---------|
| 1 | 1271 |
| 2 | 2485 |
| 3 | 1332 |
| 4 | 720 |
| 5 | 906 |
| 6 | 833 |
| 7 | 602 |
| 8 | 629 |

Примечание: в коде заявлены уровни 1-7 ([`app.py:2419-2422`](app.py:2419)), но в БД есть 629 записей с `difficulty_level = 8`.

### 7.3. Старый DailyQuest

Таблица `daily_quests` (старая модель, [`models.py:940-993`](models.py:940)) — количество записей не запрошено. Поля: `task_ids` (JSON), `completed_count`, `total_count`, `xp_earned`, `ai_comment`, `solved_indices`, `attempts_map`, `failed_indices`, `last_regenerated_at`.

---

## 8. КОНФИГ

### 8.1. База данных

**Локально**: SQLite, файл `formyla.db` в корне проекта.  
Строка подключения: `sqlite:///formyla.db` ([`app.py:178`](app.py:178) — значение по умолчанию `DATABASE_URL`).

**В проде (Render)**: PostgreSQL.  
Строка подключения: из переменной окружения `DATABASE_URL` (Render предоставляет `postgres://...`).  
Код: [`app.py:178-184`](app.py:178) — `_database_url = os.environ.get('DATABASE_URL', 'sqlite:///formyla.db')`.  
Без пароля: `postgresql+psycopg://user@host:port/dbname`.

### 8.2. Хранение ключей

Все ключи и секреты — в файле [`.env`](.env:1) (локально) и в Environment Variables на Render (прод).

Локальный `.env` содержит (без паролей — перечислены только имена):
- `SECRET_KEY`
- `OPENROUTER_API_KEY`
- `DEEPSEEK_API_KEY`
- `MAIL_USERNAME` / `MAIL_PASSWORD`
- `YANDEX_CLIENT_ID` / `YANDEX_CLIENT_SECRET`
- `DOMAIN_URL`
- `RESEND_API_KEY`
- `VAPID_PUBLIC_KEY` / `VAPID_PRIVATE_KEY` / `VAPID_CLAIM_EMAIL`

### 8.3. Куда ходит куратор

Куратор (`/prep/coach`, `/curator/*`) использует AI-клиенты из:
- [`ai/deepseek_client.py`](ai/deepseek_client.py:1) — `requests.post` к `https://api.deepseek.com/v1/chat/completions` (строки 107, 236, 811, 997)
- [`services/openrouter_client.py`](services/openrouter_client.py:1) — `httpx.post` к `https://openrouter.ai/api/v1/chat/completions`

### 8.4. Все внешние HTTP-вызовы из кода приложения

**Из production-кода (app.py, services/, routes/, curator/, daily_tasks/):**

| Файл:строка | Метод | URL/сервис | Назначение |
|-------------|-------|-----------|------------|
| [`app.py:2694`](app.py:2694) | `requests.post` | `https://openrouter.ai/api/v1/chat/completions` | AI-модификация олимпиадных задач |
| [`app.py:4698`](app.py:4698) | `requests.get` | `https://api.deepseek.com/...` (проверка баланса?) | NOT FULLY VERIFIED — требуется дочитать app.py после строки 4000 |
| [`ai/deepseek_client.py:107`](ai/deepseek_client.py:107) | `requests.post` | `https://api.deepseek.com/v1/chat/completions` | DeepSeek API |
| [`ai/deepseek_client.py:811`](ai/deepseek_client.py:811) | `requests.post` | `https://api.deepseek.com/v1/chat/completions` | DeepSeek API |
| [`ai/gemini_client.py:72`](ai/gemini_client.py:72) | `requests.post` | `https://generativelanguage.googleapis.com/v1beta/models/gemini-...` | Gemini API |
| [`services/notifications.py:38`](services/notifications.py:38) | `requests.post` | Web Push endpoint (браузерный) | Отправка push-уведомлений |
| [`services/openrouter_client.py:93`](services/openrouter_client.py:93) | `httpx.post` | `https://openrouter.ai/api/v1/chat/completions` | OpenRouter API |
| [`services/pipeline/uniqueness_search.py:53`](services/pipeline/uniqueness_search.py:53) | `requests.post` | `https://api.deepseek.com/v1/chat/completions` | Проверка уникальности задач |
| [`utils/answer_evaluator.py:74,178`](utils/answer_evaluator.py:74) | `requests.post` | `https://api.deepseek.com/v1/chat/completions` | AI-проверка ответов |
| [`utils/mail.py:161`](utils/mail.py:161) | `requests.post` | `https://api.resend.com/emails` | Отправка email через Resend API |

**Примечание**: полный список требует дочитывания app.py после строки 4000 (файл 12260 строк, прочитано ~4000). Возможны дополнительные вызовы `requests` во второй половине файла.

---

## 9. НЕ РАЗОБРАЛСЯ

1. **app.py строки 4000-12260**: не прочитаны из-за ограничения по времени. Там могут быть дополнительные роуты, `requests`-вызовы, логика. Вопрос: нужно ли дочитывать остаток app.py для полноты карты?

2. **`source = 'formyla_L1_L5_TOP5'`**: упомянуто в задании как фильтр для AdaptiveTask. В БД все 8778 записей имеют `source IS NULL`. Откуда взялось это значение? Возможно, оно было в проде (PostgreSQL), а локальная БД заполнена другим сидером.

3. **`difficulty_level = 8`**: в коде заявлены уровни 1-7, но в `adaptive_tasks` 629 записей имеют `difficulty_level = 8`. Это баг или фича?

4. **Связь method_code ↔ subtopic**: в коде не найдена. Но в задании спрашивается «есть ли в коде связь метод ↔ подтема ↔ раздел». Ответ: связи метод↔подтема нет. Подтверждение: ни в JSON, ни в моделях нет поля subtopic у TheoryBlock.

5. **Таблица `method_tasks` (3337 строк)**: упоминается в логах `LATEX-ROOT-DB-FIX` но не найдена как модель. Где она определена? В [`models_olympiad.py`](models_olympiad.py:1) такой модели нет.

6. **`/api/concierge/*` (legacy)**: эндпоинты зарегистрированы в `assistant_bp`, но используются ли они из JS на каких-то страницах? Нужно проверить статику.

7. **`/sql`**: эндпоинт существует в url_map, но не найден в шаблонах. Админский? Отладочный?

8. **Отсутствует файл `adaptive_data.py`**: лог `ВНИМАНИЕ: Файл adaptive_data.py не найден или пуст` при каждом запуске. Это норма для локальной разработки или должен существовать?

9. **Логотип ведёт на `/olympiads/methods`**, а не на `/`: [`templates/base.html:153`](templates/base.html:153) — `href="{{ url_for('olympiad.methods') }}"`. Это намеренно или баг?
