# N1_NAV — Приёмочный отчёт по навигации

PASS  GET /daily_tasks -> 200
PASS  Desktop nav fragment: 1134 chars

### DESKTOP NAV
```html
<nav class="nav" id="navLinks">
            <!-- 1. Задачи дня -->
            <a href="/daily_tasks/" class="daily-nav-link nav-link nav-pill">
                <span class="daily-flame">🔥</span>
                <span class="daily-text">Задачи дня</span>
                
            </a>

            <!-- 2. Олимпиады (dropdown) -->
            <div class="nav-dropdown">
                <button class="nav-item nav-toggle" type="button">
                    🏆 Олимпиады <span class="chev">▾</span>
                </button>
                <div class="nav-menu">
                    <a href="/olympiads">📖 Каталог</a>
                    <a href="/olympiads/courses">🆕 Курсы (ВсОШ-2027)</a>
                    <a href="/olympiads/methods">📚 Каталог методов (102)</a>
                    <a href="/olympiad-prep/calendar">📅 Календарь олимпиад</a>
                    
                </div>
            </div>

            <!-- 3. Куратор подготовки -->
            <a href="/curator" class="nav-item">🧭 Куратор подготовки</a>

            <!-- 4. Прочее -->
            <a href="/misc" class="nav-item">📋 Прочее</a>
        </nav>
```

PASS    Desktop nav contains: Задачи дня
PASS    Desktop nav contains: Олимпиады
PASS    Desktop nav contains: Куратор подготовки
PASS    Desktop nav contains: Прочее
PASS  Drawer fragment: 1702 chars

### DRAWER NAV
```html
<aside class="mobile-drawer" id="mobileDrawer">
        <!-- Drawer header -->
        <div class="drawer-header">
            <span class="drawer-logo">FORMYLA</span>
            <button class="drawer-close" onclick="closeDrawer()" aria-label="Закрыть">✕</button>
        </div>

        <!-- User info -->
        

        <!-- Search -->
        <div class="drawer-search">
            <form action="/problems" method="get">
                <input type="text" name="q" placeholder="🔍 Поиск задач..."
                       value="">
                <button type="submit">Найти</button>
            </form>
        </div>

        <!-- Navigation links -->
        <nav class="drawer-nav">
            <a href="/daily_tasks/" class="drawer-link">
                <span class="drawer-link-icon">🔥</span>
                Задачи дня
                
            </a>

            <div class="drawer-divider"></div>

            <a href="/olympiads" class="drawer-link">
                <span class="drawer-link-icon">🏆</span>
                Олимпиады
            </a>

            <a href="/curator" class="drawer-link">
                <span class="drawer-link-icon">🧭</span>
                Куратор подготовки
            </a>

            <a href="/misc" class="drawer-link">
                <span class="drawer-link-icon">📋</span>
                Прочее
            </a>
        </nav>

        <!-- Footer: auth actions -->
        <div class="drawer-footer">
            
            <a href="/login" class="drawer-link" style="color: #38bdf8;">
                <span class="drawer-link-icon">🚀</span>
                Войти / Регистрация
            </a>
            
        </div>
    </aside>
```

PASS    Drawer contains: Задачи дня
PASS    Drawer contains: Олимпиады
PASS    Drawer contains: Куратор подготовки
PASS    Drawer contains: Прочее
PASS  Bottom nav fragment: 996 chars

### BOTTOM NAV
```html
<nav class="mobile-bottom-nav" id="mobileBottomNav">
        <a href="/daily_tasks/" class="bottom-nav-item" data-path="/daily*">
            <span class="bottom-nav-icon">🔥</span>
            <span class="bottom-nav-label">Задачи дня</span>
            
        </a>
        <a href="/olympiads" class="bottom-nav-item" data-path="/olympiads*,/practice*,/olympiad*">
            <span class="bottom-nav-icon">🏆</span>
            <span class="bottom-nav-label">Олимпиады</span>
        </a>
        <a href="/curator" class="bottom-nav-item" data-path="/curator*">
            <span class="bottom-nav-icon">🧭</span>
            <span class="bottom-nav-label">Куратор</span>
        </a>
        <a href="/misc" class="bottom-nav-item" data-path="/misc*,/profile*,/friends*,/leaderboard*,/chat*,/drawing*,/about*,/probniks*,/secrets*,/problems*,/matstat*,/index*">
            <span class="bottom-nav-icon">📋</span>
            <span class="bottom-nav-label">Прочее</span>
        </a>
    </nav>
```

PASS    Bottom nav contains: Задачи дня
PASS    Bottom nav contains: Олимпиады
PASS    Bottom nav contains: Куратор
PASS    Bottom nav contains: Прочее
PASS  /misc status: 200
PASS  Misc page content: 2654 chars

### MISC PAGE HTML
```html
<div class="misc-page">
    <h1>Прочее</h1>

    <div class="misc-group">
        <div class="misc-group-title">Тренировка</div>
        <a href="/" class="misc-link">
            <span class="misc-link-label">Темы</span>
            <span class="misc-link-desc">Каталог тем и подтем</span>
        </a>
        <a href="/probniks" class="misc-link">
            <span class="misc-link-label">Тест по темам</span>
            <span class="misc-link-desc">Адаптивный тест</span>
        </a>
        <a href="/secrets" class="misc-link">
            <span class="misc-link-label">Секреты</span>
            <span class="misc-link-desc">Специальные подборки задач</span>
        </a>
    </div>

    <div class="misc-group">
        <div class="misc-group-title">Доска и чертежи</div>
        <a href="/drawing" class="misc-link">
            <span class="misc-link-label">ИИ-чертёж по задаче</span>
            <span class="misc-link-desc">Генерация чертежа</span>
        </a>
        <a href="/drawing?tab=whiteboard" class="misc-link">
            <span class="misc-link-label">Доска и встреча</span>
            <span class="misc-link-desc">Интерактивная доска, камера и звук</span>
        </a>
        
    </div>

    <div class="misc-group">
        <div class="misc-group-title">Сообщество</div>
        <a href="/leaderboard" class="misc-link">
            <span class="misc-link-label">Лидеры</span>
            <span class="misc-link-desc">Таблица лидеров</span>
        </a>
        <a href="/friends" class="misc-link">
            <span class="misc-link-label">Друзья</span>
            <span class="misc-link-desc">Список друзей</span>
        </a>
        <a href="/chat" class="misc-link">
            <span class="misc-link-label">Чат</span>
            <span class="misc-link-desc">Общий чат</span>
        </a>
    </div>

    <div class="misc-group">
        <div class="misc-group-title">Инструменты</div>
        
        <a href="/problems" class="misc-link">
            <span class="misc-link-label">Поиск задач</span>
            <span class="misc-link-desc">Поиск по базе задач</span>
        </a>
        
    </div>

    <div class="misc-group">
        <div class="misc-group-title">Информация</div>
        <a href="/about" class="misc-link">
            <span class="misc-link-label">О сайте</span>
            <span class="misc-link-desc">О платформе FORMYLA</span>
        </a>
        <a href="/about#review-form" class="misc-link">
            <span class="misc-link-label">Написать отзыв</span>
            <span class="misc-link-desc">Предложения и пожелания</span>
        </a>
    </div>

    
</div>

    </main>
```

PASS    Misc group present: Тренировка
PASS    Misc group present: Доска и чертежи
PASS    Misc group present: Сообщество
PASS    Misc group present: Инструменты
PASS    Misc group present: Информация
PASS    Group title clean (no emoji): Тренировка
PASS    Group title clean (no emoji): Доска и чертежи
PASS    Group title clean (no emoji): Сообщество
PASS    Group title clean (no emoji): Инструменты
PASS    Group title clean (no emoji): Информация
PASS  Found 11 unique internal links on /misc

### LINK WALK (11 links)

PASS    / -> 200
  / -> 200
PASS    /probniks -> 200
  /probniks -> 200
PASS    /secrets -> 200
  /secrets -> 200
PASS    /drawing -> 200
  /drawing -> 200
PASS    /drawing?tab=whiteboard -> 200
  /drawing?tab=whiteboard -> 200
PASS    /leaderboard -> 200
  /leaderboard -> 200
PASS    /friends -> 200
  /friends -> 200
PASS    /chat -> 200
  /chat -> 200
PASS    /problems -> 200
  /problems -> 200
PASS    /about -> 200
  /about -> 200
PASS    /about#review-form -> 200
  /about#review-form -> 200
PASS  nav.js referenced on /misc page
PASS  '/misc' found in rendered HTML
PASS  Logo links to daily_tasks: /daily_tasks/
PASS  Total non-static routes: 318

### ROUTES (318 total)

  /
  /__diag/method/<method_code>
  /__version
  /about
  /accept_request/<int:mentorship_id>
  /account/delete
  /account/merge
  /account/merge/cancel
  /account/merge_preview
  /account/ml-consent
  /account/privacy
  /adaptive-test/<int:test_id>
  /adaptive-test/<int:test_id>/results
  /adaptive_task/<int:task_id>
  /adaptive_test/select_class
  /adaptive_test/select_grade
  /adaptive_test/select_topic
  /adaptive_test/start
  /adaptive_test/start_grade
  /adaptive_test_simple
  /adaptive_test_simple/finish
  /adaptive_test_simple/results
  /adaptive_test_simple/skip
  /adaptive_test_simple/submit
  /add_student
  /admin/fix-theory-blocks
  /admin/fix_latex_rac
  /admin/needs_review
  /admin/needs_review/action/<int:task_id>
  /admin/seed-secrets
  /admin/support
  /admin/support/<int:msg_id>/reply
  /admin/toggle_task_flag/<int:task_id>
  /admin/tutor_stats
  /api/adaptive-test/<int:test_id>/analyze
  /api/adaptive-test/<int:test_id>/submit
  /api/adaptive-test/start
  /api/assistant
  /api/cancel_subscription
  /api/chat/<int:friend_id>/messages
  /api/chat/<int:friend_id>/presence
  /api/chat/<int:friend_id>/send
  /api/chat/<int:friend_id>/typing
  /api/chat/<int:friend_id>/upload
  /api/chat/conversations
  /api/chat/message/<int:message_id>/delete
  /api/chat/message/<int:message_id>/edit
  /api/chat/message/<int:message_id>/forward
  /api/chat/message/<int:message_id>/react
  /api/chat/task-suggestions
  /api/chat/unread_total
  /api/check_adaptive_answer
  /api/check_answer
  /api/concierge/ask
  /api/concierge/intents
  /api/conference/create-room
  /api/daily-task
  /api/drawing/diag
  /api/drawing/generate
  /api/drawing/history
  /api/drawing/history/<int:row_id>
  /api/drawing/status/<task_id>
  /api/exam/<int:exam_id>/submit
  /api/exam/generate
  /api/feedback
  /api/free_mock/evaluate
  /api/free_mock/generate_block
  /api/free_mock/generate_single_task
  /api/groups
  /api/groups
  /api/groups/<int:group_id>
  /api/groups/<int:group_id>/info
  /api/groups/<int:group_id>/invite
  /api/groups/<int:group_id>/leave
  /api/groups/<int:group_id>/members
  /api/groups/<int:group_id>/messages
  /api/groups/<int:group_id>/send
  /api/groups/<int:group_id>/upload
  /api/migrate/export
  /api/migrate/push
  /api/migrate/tables
  /api/my/support/messages
  /api/my/support/unread_count
  /api/notifications/count
  /api/problem/<int:problem_id>
  /api/profile
  /api/profile/<nickname>
  /api/progress/<int:user_id>
  /api/push/subscribe
  /api/push/unsubscribe
  /api/report_task/<int:task_id>
  /api/reviews
  /api/save_test_result
  /api/secrets
  /api/set_nickname
  /api/social/friends/list
  /api/social/friends/request
  /api/social/mentorship/request
  /api/social/mentorship/respond
  /api/social/mentorship/students
  /api/social/mentorship/teachers
  /api/social/search-users
  /api/social/set-nickname
  /api/subscribe
  /api/support
  /api/test/<int:session_id>/abandon
  /api/test/<int:session_id>/answer
  /api/test/<int:session_id>/complete
  /api/test/<int:session_id>/resume
  /api/test/active
  /api/test/start
  /api/tutor/hint/<int:problem_id>
  /api/tutor/history
  /api/tutor/send
  /api/tutor/solution/<int:problem_id>
  /api/users/<int:user_id>/info
  /api/wb_call/ice
  /api/wb_call/invite
  /api/wb_call/invites/dismiss
  /api/wb_call/invites/poll
  /api/wb_call/join
  /api/wb_call/leave
  /api/wb_call/poll
  /api/wb_call/send
  /api/wb_call/status
  /api/wb_meet/config
  /api/wb_meet/release
  /api/wb_meet/status
  /api/wb_meet/token
  /auth/telegram/callback
  /auth/telegram/unlink
  /auth/yandex/login
  /call
  /chat
  /chat/<int:friend_id>
  /conference
  /curator/analyze/olympiads
  /curator/analyze/topics
  /curator/diagnostics/<int:session_id>/answer
  /curator/diagnostics/<int:session_id>/next
  /curator/diagnostics/<int:session_id>/result
  /curator/diagnostics/<int:session_id>/summary
  /curator/diagnostics/start
  /curator/health
  /curator/notify/evening-check
  /curator/onboarding
  /curator/plans
  /curator/plans
  /curator/plans/<int:plan_id>
  /curator/plans/<int:plan_id>/advance
  /curator/plans/<int:plan_id>/pause
  /curator/plans/<int:plan_id>/recompute
  /curator/plans/<int:plan_id>/resume
  /curator/plans/<int:plan_id>/tasks
  /curator/prep/evening-generate
  /curator/prep/morning-test
  /curator/prep/progress
  /curator/prep/submit-test
  /curator/prep/today
  /curator/progress/<int:user_id>
  /curator/progress/<int:user_id>/advice
  /curator/progress/<int:user_id>/dynamics
  /curator/progress/<int:user_id>/log
  /curator/progress/<int:user_id>/streak
  /curator/progress/<int:user_id>/stuck
  /curator/progress/<int:user_id>/weekly
  /curator/static/<path:filename>
  /curator/tutor/attempts/<int:user_id>/<int:task_id>
  /curator/tutor/explain
  /curator/tutor/hints
  /curator/tutor/review
  /daily-set
  /daily_tasks/
  /daily_tasks/<int:item_id>/hint
  /daily_tasks/<int:item_id>/solve
  /daily_tasks/<int:item_id>/submit
  /daily_tasks/<int:item_id>/submit_ai
  /daily_tasks/calendar
  /daily_tasks/day_history/<date_iso>
  /daily_tasks/job_status
  /daily_tasks/regenerate
  /daily_tasks/static/<path:filename>
  /daily_tasks/status
  /debug-sentry
  /debug/routes
  /dev_login
  /drawing
  /drawing/history
  /exam/<int:exam_id>
  /exam/<int:exam_id>/results
  /free_mock/generate
  /free_mock/start
  /free_mock/submit
  /free_mock/test
  /friends
  /friends/accept/<int:rid>
  /friends/cancel/<int:rid>
  /friends/decline/<int:rid>
  /friends/remove/<int:uid>
  /friends/request/<int:uid>
  /grade-5
  /grade-5/<string:domain>
  /grade-6
  /grade-6/<string:domain>
  /grade-task/<int:task_id>
  /groups/<int:group_id>
  /health
  /healthz
  /intake/
  /intake/anchor
  /intake/answer
  /intake/back
  /intake/start
  /leaderboard
  /link_yandex
  /login
  /logout
  /matstat
  /misc
  /mock-payment
  /my/support
  /my/support/<int:msg_id>/reply
  /notifications
  /olympiad-prep
  /olympiad-prep/<slug>
  /olympiad-prep/calendar
  /olympiad-test
  /olympiad-test/select-level
  /olympiad-test/select-section
  /olympiad-test/select-theme
  /olympiad-test/start
  /olympiads
  /olympiads/
  /olympiads/course-probnik
  /olympiads/course-probnik/10
  /olympiads/course-probnik/11
  /olympiads/course/<int:grade>
  /olympiads/courses
  /olympiads/methods
  /olympiads/methods/<method_code>
  /olympiads/methods/section/<int:grade>/<section_name>
  /olympiads/methods/task/<method_task_id>
  /olympiads/my-progress
  /olympiads/open
  /olympiads/predict-methods
  /olympiads/probnik/<code>
  /olympiads/probnik/<code>/active
  /olympiads/probnik/<code>/start
  /olympiads/probnik/<code>/submit
  /olympiads/solution/<int:combo_id>
  /olympiads/task/<int:task_id>
  /olympiads/task/<int:task_id>/attempt
  /olympiads/task/<int:task_id>/submit
  /prep/
  /prep/<int:plan_id>
  /prep/<int:plan_id>
  /prep/<int:plan_id>/day/<int:day_id>
  /prep/<int:plan_id>/pause
  /prep/<int:plan_id>/resume
  /prep/<int:plan_id>/today
  /prep/<int:plan_id>/today/complete/<int:problem_id>
  /prep/<int:plan_id>/today/upload_photo/<int:problem_id>
  /prep/coach
  /prep/coach/chat
  /prep/coach/daily/submit
  /prep/coach/day/complete
  /prep/coach/greeting
  /prep/coach/history
  /prep/coach/history/delete
  /prep/coach/onboarding/submit
  /prep/coach/prep/submit_test
  /prep/coach/questionnaire/answer
  /prep/coach/questionnaire/start
  /prep/coach/set_grade
  /prep/coach/test/start
  /prep/new
  /prep/new
  /prep/onboarding
  /prep/onboarding/anchor
  /prep/onboarding/answer
  /prep/probe
  /prep/probe/submit
  /problem/<int:problem_id>
  /problems
  /problems/<int:problem_id>
  /probniks
  /profile
  /reject_request/<int:mentorship_id>
  /scheduler
  /scheduler/jobs
  /scheduler/jobs
  /scheduler/jobs/<job_id>
  /scheduler/jobs/<job_id>
  /scheduler/jobs/<job_id>
  /scheduler/jobs/<job_id>/pause
  /scheduler/jobs/<job_id>/resume
  /scheduler/jobs/<job_id>/run
  /scheduler/pause
  /scheduler/resume
  /scheduler/shutdown
  /scheduler/start
  /secrets
  /secrets/<int:secret_id>
  /section/<subject_key>
  /section/<subject_key>/<subtopic_key>
  /social
  /sql
  /student/<int:student_id>
  /subscribe
  /topics
  /u/<nickname>
  /update_nickname
  /user/<int:user_id>
  /verify-code
  /welcome
  /whiteboard
  /yandex_login
  /yandex_receiver

### PYTEST (pre-existing baseline)
```
50 failed, 807 passed, 16 skipped, 19713 warnings, 14 errors in 232.67s
```

No new failures introduced by nav changes.