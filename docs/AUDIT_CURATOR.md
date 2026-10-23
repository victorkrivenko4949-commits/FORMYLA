# AUDIT REPORT: Curator / Daily Tasks / Adaptive Test Subsystems

**Date:** 2026-07-26
**Scope:** Curator module, daily tasks pipeline, adaptive test system, concierge
**Methodology:** Read-only code analysis; no files modified.

---

## 1. Route Registry

### 1.1 All Flask Routes

> **Note:** app.py alone registers ~160 routes. Below is a consolidated table covering the three target subsystems plus concierge.

| Method | URL | Function | File:Line | Login? | Returns |
|--------|-----|----------|-----------|--------|---------|
| **Curator subsystem** |||||
| GET | `/prep/coach` | `coach()` | [`routes/prep.py:914`](routes/prep.py:914) | yes | html |
| GET | `/prep/coach/greeting` | `coach_greeting()` | [`routes/prep.py:1091`](routes/prep.py:1091) | yes | json |
| POST | `/prep/coach/chat` | `coach_chat()` | [`routes/prep.py:2180`](routes/prep.py:2180) | yes | json |
| POST | `/prep/coach/test/start` | `coach_test_start()` | [`routes/prep.py:1468`](routes/prep.py:1468) | yes | json |
| POST | `/prep/coach/onboarding/submit` | `coach_onboarding_submit()` | [`routes/prep.py:1560`](routes/prep.py:1560) | yes | json |
| POST | `/prep/coach/daily/submit` | `coach_daily_submit()` | [`routes/prep.py:1680`](routes/prep.py:1680) | yes | json |
| POST | `/prep/coach/prep/submit_test` | `coach_prep_submit_test()` | [`routes/prep.py:1796`](routes/prep.py:1796) | yes | json |
| POST | `/prep/coach/day/complete` | `coach_day_complete()` | [`routes/prep.py:1853`](routes/prep.py:1853) | yes | json |
| GET | `/prep/coach/history` | `coach_history()` | [`routes/prep.py:1941`](routes/prep.py:1941) | yes | json |
| POST | `/prep/coach/history/delete` | `coach_history_delete()` | [`routes/prep.py:1955`](routes/prep.py:1955) | yes | json |
| POST | `/prep/coach/set_grade` | `coach_set_grade()` | [`routes/prep.py:1974`](routes/prep.py:1974) | yes | json |
| POST | `/prep/coach/questionnaire/start` | `coach_questionnaire_start()` | [`routes/prep.py:2005`](routes/prep.py:2005) | yes | json |
| POST | `/prep/coach/questionnaire/answer` | `coach_questionnaire_answer()` | [`routes/prep.py:2030`](routes/prep.py:2030) | yes | json |
| POST | `/curator/diagnostics/start` | `api_diagnostics_start()` | [`curator/routes.py:166`](curator/routes.py:166) | no | json |
| GET | `/curator/diagnostics/<id>/next` | `api_diagnostics_next()` | [`curator/routes.py:190`](curator/routes.py:190) | no | json |
| POST | `/curator/diagnostics/<id>/answer` | `api_diagnostics_answer()` | [`curator/routes.py:219`](curator/routes.py:219) | no | json |
| GET | `/curator/diagnostics/<id>/result` | `api_diagnostics_result()` | [`curator/routes.py:252`](curator/routes.py:252) | no | json |
| POST | `/curator/diagnostics/<id>/summary` | `api_diagnostics_summary()` | [`curator/routes.py:270`](curator/routes.py:270) | no | json |
| POST | `/curator/plans` | `api_plans_create()` | [`curator/routes.py:294`](curator/routes.py:294) | no | json |
| GET | `/curator/plans` | `api_plans_list()` | [`curator/routes.py:343`](curator/routes.py:343) | no | json |
| GET | `/curator/plans/<id>` | `api_plans_detail()` | [`curator/routes.py:377`](curator/routes.py:377) | no | json |
| POST | `/curator/plans/<id>/recompute` | `api_plans_recompute()` | [`curator/routes.py:395`](curator/routes.py:395) | no | json |
| POST | `/curator/plans/<id>/advance` | `api_plans_advance()` | [`curator/routes.py:413`](curator/routes.py:413) | no | json |
| POST | `/curator/plans/<id>/pause` | `api_plans_pause()` | [`curator/routes.py:438`](curator/routes.py:438) | no | json |
| POST | `/curator/plans/<id>/resume` | `api_plans_resume()` | [`curator/routes.py:455`](curator/routes.py:455) | no | json |
| GET | `/curator/plans/<id>/tasks` | `api_plans_tasks()` | [`curator/routes.py:472`](curator/routes.py:472) | no | json |
| POST | `/curator/tutor/hints` | `api_tutor_hints()` | [`curator/routes.py:494`](curator/routes.py:494) | no | json |
| POST | `/curator/tutor/review` | `api_tutor_review()` | [`curator/routes.py:532`](curator/routes.py:532) | no | json |
| POST | `/curator/tutor/explain` | `api_tutor_explain()` | [`curator/routes.py:590`](curator/routes.py:590) | no | json |
| GET | `/curator/tutor/attempts/<user_id>/<task_id>` | `api_tutor_attempts()` | [`curator/routes.py:620`](curator/routes.py:620) | no | json |
| GET | `/curator/progress/<user_id>` | `api_progress_summary()` | [`curator/routes.py:643`](curator/routes.py:643) | no | json |
| GET | `/curator/progress/<user_id>/streak` | `api_progress_streak()` | [`curator/routes.py:662`](curator/routes.py:662) | no | json |
| GET | `/curator/progress/<user_id>/stuck` | `api_progress_stuck()` | [`curator/routes.py:676`](curator/routes.py:676) | no | json |
| GET | `/curator/progress/<user_id>/weekly` | `api_progress_weekly()` | [`curator/routes.py:691`](curator/routes.py:691) | no | json |
| POST | `/curator/progress/<user_id>/advice` | `api_progress_advice()` | [`curator/routes.py:706`](curator/routes.py:706) | no | json |
| GET | `/curator/progress/<user_id>/dynamics` | `api_progress_dynamics()` | [`curator/routes.py:727`](curator/routes.py:727) | no | json |
| POST | `/curator/progress/<user_id>/log` | `api_progress_log()` | [`curator/routes.py:748`](curator/routes.py:748) | no | json |
| POST | `/curator/onboarding` | `api_onboarding()` | [`curator/routes.py:787`](curator/routes.py:787) | no | json |
| POST | `/curator/analyze/topics` | `api_analyze_topics()` | [`curator/routes.py:846`](curator/routes.py:846) | no | json |
| POST | `/curator/analyze/olympiads` | `api_analyze_olympiads()` | [`curator/routes.py:872`](curator/routes.py:872) | no | json |
| GET | `/curator/prep/today` | `api_prep_today()` | [`curator/routes.py:903`](curator/routes.py:903) | no | json |
| GET | `/curator/prep/morning-test` | `api_prep_morning_test()` | [`curator/routes.py:933`](curator/routes.py:933) | no | json |
| POST | `/curator/prep/submit-test` | `api_prep_submit_test()` | [`curator/routes.py:955`](curator/routes.py:955) | no | json |
| POST | `/curator/prep/evening-generate` | `api_prep_evening_generate()` | [`curator/routes.py:999`](curator/routes.py:999) | no | json |
| GET | `/curator/prep/progress` | `api_prep_progress()` | [`curator/routes.py:1031`](curator/routes.py:1031) | no | json |
| POST | `/curator/notify/evening-check` | `api_curator_evening_check()` | [`curator/routes.py:1064`](curator/routes.py:1064) | no | json |
| GET | `/curator/health` | `api_curator_health()` | [`curator/routes.py:1107`](curator/routes.py:1107) | no | json |
| **Daily tasks subsystem** |||||
| GET | `/prep/` | `dashboard()` | [`routes/prep.py:159`](routes/prep.py:159) | yes | html/json |
| GET | `/prep/new` | `new_plan_form()` | [`routes/prep.py:186`](routes/prep.py:186) | yes | html/json |
| POST | `/prep/new` | `create_plan()` | [`routes/prep.py:216`](routes/prep.py:216) | yes | json |
| GET | `/prep/<plan_id>` | `plan_detail()` | [`routes/prep.py:286`](routes/prep.py:286) | yes | html/json |
| GET | `/prep/<plan_id>/day/<day_id>` | `day_detail()` | [`routes/prep.py:333`](routes/prep.py:333) | yes | json |
| GET | `/prep/<plan_id>/today` | `today_problems()` | [`routes/prep.py:370`](routes/prep.py:370) | yes | html/json |
| POST | `/prep/<plan_id>/today/complete/<problem_id>` | `complete_problem()` | [`routes/prep.py:405`](routes/prep.py:405) | yes | json |
| POST | `/prep/<plan_id>/pause` | `pause_plan()` | [`routes/prep.py:624`](routes/prep.py:624) | yes | json |
| POST | `/prep/<plan_id>/resume` | `resume_plan()` | [`routes/prep.py:636`](routes/prep.py:636) | yes | json |
| DELETE | `/prep/<plan_id>` | `delete_plan()` | [`routes/prep.py:650`](routes/prep.py:650) | yes | 204 |
| POST | `/prep/<plan_id>/today/upload_photo/<problem_id>` | `upload_solution_photo()` | [`routes/prep.py:660`](routes/prep.py:660) | yes | json |
| GET | `/api/daily-task` | (anon lambda) | [`app.py:9590`](app.py:9590) | yes | json |
| GET | `/daily-set` | (anon lambda) | [`app.py:9618`](app.py:9618) | yes | html/redirect |
| **Adaptive test subsystem** |||||
| GET | `/adaptive_test/select_class` | (anon lambda) | [`app.py:6271`](app.py:6271) | no | html |
| GET | `/adaptive_test/select_topic` | (anon lambda) | [`app.py:6277`](app.py:6277) | no | html |
| GET | `/adaptive_test/start_grade` | (anon lambda) | [`app.py:6352`](app.py:6352) | no | html |
| GET | `/adaptive_test/select_grade` | (anon lambda) | [`app.py:6391`](app.py:6391) | no | html |
| GET | `/adaptive_test/start` | (anon lambda) | [`app.py:6460`](app.py:6460) | no | html |
| POST | `/api/test/start` | (anon lambda) | [`app.py:7111`](app.py:7111) | no | json |
| GET | `/api/test/active` | (anon lambda) | [`app.py:7123`](app.py:7123) | no | json |
| GET | `/api/test/<session_id>/resume` | (anon lambda) | [`app.py:7144`](app.py:7144) | no | json |
| POST | `/api/test/<session_id>/answer` | (anon lambda) | [`app.py:7177`](app.py:7177) | no | json |
| POST | `/api/test/<session_id>/complete` | (anon lambda) | [`app.py:7188`](app.py:7188) | no | json |
| POST | `/api/test/<session_id>/abandon` | (anon lambda) | [`app.py:7197`](app.py:7197) | no | json |
| GET | `/adaptive_test_simple` | (anon lambda) | [`app.py:7235`](app.py:7235) | no | html |
| POST | `/adaptive_test_simple/skip` | (anon lambda) | [`app.py:7374`](app.py:7374) | no | json |
| GET/POST | `/adaptive_test_simple/finish` | (anon lambda) | [`app.py:7424`](app.py:7424) | no | json |
| POST | `/adaptive_test_simple/submit` | (anon lambda) | [`app.py:7490`](app.py:7490) | no | json |
| POST | `/api/check_adaptive_answer` | (anon lambda) | [`app.py:7501`](app.py:7501) | no | json |
| POST | `/api/report_task/<task_id>` | (anon lambda) | [`app.py:7748`](app.py:7748) | no | json |
| GET | `/adaptive_test_simple/results` | (anon lambda) | [`app.py:7789`](app.py:7789) | no | html |
| POST | `/api/adaptive-test/start` | (anon lambda) | [`app.py:7978`](app.py:7978) | no | json |
| GET | `/api/problem/<problem_id>` | (anon lambda) | [`app.py:8055`](app.py:8055) | no | json |
| POST | `/api/adaptive-test/<test_id>/submit` | (anon lambda) | [`app.py:8065`](app.py:8065) | no | json |
| POST | `/api/adaptive-test/<test_id>/analyze` | (anon lambda) | [`app.py:8176`](app.py:8176) | no | json |
| GET | `/adaptive-test/<test_id>` | (anon lambda) | [`app.py:8307`](app.py:8307) | no | html |
| GET | `/adaptive-test/<test_id>/results` | (anon lambda) | [`app.py:8324`](app.py:8324) | no | html |
| **Concierge subsystem** |||||
| POST | `/api/concierge/ask` | `ask()` | [`routes/concierge.py:73`](routes/concierge.py:73) | no | json |
| GET | `/api/concierge/intents` | `list_intents()` | [`routes/concierge.py:66`](routes/concierge.py:66) | no | json |

### 1.2 Route Inventory by Subsystem

| Subsystem | Count | Key files |
|-----------|-------|-----------|
| Curator (coach page) | 14 routes | [`routes/prep.py`](routes/prep.py:741) — all under `/prep/coach/` |
| Curator (API) | 31 routes | [`curator/routes.py`](curator/routes.py) — under `/curator/` |
| Daily tasks (PrepPlan) | 12 routes | [`routes/prep.py`](routes/prep.py:16) — under `/prep/` (non-coach) |
| Adaptive test | 22 routes | [`app.py`](app.py:6271) — `/adaptive_test*`, `/api/test/*`, `/api/adaptive-test/*` |
| Concierge | 2 routes | [`routes/concierge.py`](routes/concierge.py:65) — `/api/concierge/*` |

---

## 2. Database Models

### 2.1 models.py (lines 1–1528)

| Model | Table | Key Fields + Types | FK | Unique Indexes |
|-------|-------|--------------------|-----|---------------|
| `User` | `users` | `id` Integer PK, `email` String(120) unique, `name` String(200), `nickname` String(50) unique, `avatar_url` String(500), `auth_code` String(6), `code_expires` DateTime, `math_level` String(20), `ai_report` Text, `recommended_topics` String(200), `onboarding_completed` Boolean, `total_problems_solved` Integer, `current_level` Integer, `experience_points` Integer, `mock_exams_passed` Integer, `adaptive_tests_completed` Integer, `highest_difficulty_solved` Integer, `current_plan` Text, `plan_expires_at` DateTime, `generation_count_today` Integer, `generation_reset_date` Date, `gens_extra_purchased` Integer, `gens_unlimited` Boolean, `is_guest` Boolean, `device_id` String(64), `preferred_grade` Integer, `ml_training_consent` Boolean, `created_at` DateTime, `last_login` DateTime, `onboarded_at` DateTime, `telegram_id` String(64) unique, `telegram_username` String(64), `questionnaire_state` Text | — | `email`, `nickname`, `telegram_id` |
| `OAuthAccount` | `oauth_accounts` | `id` Integer PK, `user_id` FK→users, `provider` String(50), `provider_user_id` String(200) | `user_id` | `(provider, provider_user_id)` |
| `ChatMessage` | `chat_messages` | `id` Integer PK, `user_id` FK→users, `agent_type` String(50), `role` String(20), `content` Text, `timestamp` DateTime | `user_id` | — |
| `MockExam` | `mock_exams` | `id` Integer PK, `user_id` FK→users, `created_at` DateTime, `status` String(20), `ai_feedback` Text, `score` Integer | `user_id` | — |
| `MockExamTask` | `mock_exam_tasks` | `id` Integer PK, `exam_id` FK→mock_exams, `problem_id` Integer, `user_answer` String(500), `user_solution_text` Text, `is_correct` Boolean, `ai_comment` Text | `exam_id` | — |
| `SecretTopic` | `secret_topics` | `id` Integer PK, `slug` String(100) unique, `title` String(200), `content` Text, `created_at` DateTime | — | `slug` |
| `AdaptiveTest` | `adaptive_tests` | `id` Integer PK, `user_id` FK→users, `subject` String(50), `grade` Integer, `num_problems` Integer, `initial_ability` Float, `current_ability` Float, `status` String(20), `created_at` DateTime, `completed_at` DateTime, `final_ability` Float, `total_correct` Integer, `accuracy` Float, `ai_analysis` Text | `user_id` | — |
| `AdaptiveTestProblem` | `adaptive_test_problems` | `id` Integer PK, `test_id` FK→adaptive_tests, `problem_id` Integer, `sequence_number` Integer, `user_ability_before` Float, `problem_difficulty` Float, `user_answer` String(500), `user_solution_text` Text, `is_correct` Boolean, `answered_at` DateTime, `user_ability_after` Float, `ai_feedback` Text | `test_id` | — |
| `Friendship` | `friendships` | `id` Integer PK, `requester_id` FK→users, `addressee_id` FK→users, `status` String(20), `created_at` DateTime, `accepted_at` DateTime | `requester_id`, `addressee_id` | `(requester_id, addressee_id)` |
| `DirectMessage` | `direct_messages` | `id` Integer PK, `sender_id` FK→users, `recipient_id` FK→users, `kind` String(20), `body` Text, `task_id` Integer, `task_topic` String(120), `task_grade` Integer, `task_difficulty` Integer, `task_source` String(40), `task_url` String(400), `task_preview` Text, `attachment_url` String(400), `attachment_kind` String(16), `attachment_name` String(255), `attachment_size` Integer, `reply_to_id` Integer, `edited_at` DateTime, `deleted_at` DateTime, `forwarded_from_id` Integer, `delivered_at` DateTime, `read_at` DateTime, `is_read` Boolean, `created_at` DateTime | `sender_id`, `recipient_id` | — |
| `Notification` | `notifications` | `id` Integer PK, `user_id` FK→users, `type` String(50), `from_user_id` FK→users, `data` Text, `read` Boolean, `created_at` DateTime | `user_id`, `from_user_id` | — |
| `PushSubscription` | `push_subscriptions` | `id` Integer PK, `user_id` FK→users, `endpoint` Text, `p256dh_key` String(256), `auth_key` String(64), `user_agent` String(256), `created_at` DateTime, `updated_at` DateTime | `user_id` | — |
| `UserPresence` | `user_presence` | `user_id` FK→users PK, `last_seen` DateTime, `typing_to_id` FK→users, `typing_at` DateTime | `user_id`, `typing_to_id` | — |
| `MessageReaction` | `message_reactions` | `id` Integer PK, `message_id` FK→direct_messages, `user_id` FK→users, `emoji` String(16), `created_at` DateTime | `message_id`, `user_id` | `(message_id, user_id, emoji)` |
| `Mentorship` | `mentorships` | `id` Integer PK, `teacher_id` FK→users, `student_id` FK→users, `status` String(20), `created_at` DateTime, `updated_at` DateTime | `teacher_id`, `student_id` | `(teacher_id, student_id)` + CHECK `teacher_id != student_id` |
| `OlympiadSecret` | `olympiad_secrets` | `id` Integer PK, `topic` String(100), `title` String(200), `content` Text, `difficulty_level` Integer, `created_at` DateTime | — | — |
| `AdaptiveTask` | `adaptive_tasks` | `id` Integer PK, `class_level` Integer, `difficulty_level` Integer, `topic` String(200), `subtopic` String(100), `task_text` Text, `solution` Text, `criteria_1_point` Text, `criteria_2_points` Text, `created_at` DateTime, `correct_answer` Text, `is_flagged` Boolean, `reports_count` Integer, `flagged_reason` Text, `attempts_count` Integer, `solves_count` Integer, `actual_solve_rate` Float, `suggested_level` Integer, `needs_reclassification` Boolean, `last_calibrated_at` DateTime, `subject` String(20), `source_id` String(120), `task_type` Text, `source` Text, `needs_review` Boolean, `llm_suggested_answer` Text, `llm_suggested_solution` Text, `review_reason` Text, `review_flagged_at` DateTime | — | — |
| `UserTopicProgress` | `user_topic_progress` | `id` Integer PK, `user_id` FK→users, `topic` String(50), `topic_name_ru` String(100), `current_level` Integer, `tasks_attempted` Integer, `tasks_correct` Integer, `last_test_date` DateTime, `created_at` DateTime, `updated_at` DateTime | `user_id` | — |
| `AdaptiveTestResult` | `adaptive_test_results` | `id` Integer PK, `user_id` FK→users, `topic` String(50), `class_level` Integer, `final_level` Integer, `tasks_correct` Integer, `tasks_total` Integer, `answers_history` Text, `started_at` DateTime, `completed_at` DateTime | `user_id` | — |
| `DailyQuest` | `daily_quests` | `id` Integer PK, `user_id` FK→users, `date` Date, `task_ids` Text (JSON), `completed_count` Integer, `total_count` Integer, `xp_earned` Integer, `ai_comment` Text, `solved_indices` Text (JSON), `attempts_map` Text (JSON), `failed_indices` JSON, `last_regenerated_at` DateTime, `created_at` DateTime, `completed_at` DateTime | `user_id` | `(user_id, date)` |
| `UserStreak` | `user_streaks` | `id` Integer PK, `user_id` FK→users unique, `current_streak` Integer, `longest_streak` Integer, `last_active_date` Date, `freeze_available` Integer, `freeze_used_at` Date, `created_at` DateTime, `updated_at` DateTime | `user_id` | — |
| `TopicMastery` | `topic_mastery` | `id` Integer PK, `user_id` FK→users, `topic` String(100), `grade` Integer, `solved` Integer, `attempts` Integer, `avg_level` Float, `mastery` Float, `updated_at` DateTime | `user_id` | `(user_id, topic, grade)` |
| `OlympiadGenerationLog` | `olympiad_generation_log` | `id` Integer PK, `olympiad_slug` String(100), `round_key` String(100), `class_level` Integer, `attempts` Integer, `success` Integer, `errors_json` Text, `user_id` FK→users, `created_at` DateTime | `user_id` | — |
| `TestResult` | `test_results_detail` | `id` Integer PK, `user_id` FK→users, `device_id` String(64), `test_type` String(50), `class_level` Integer, `topic` String(200), `task_id` Integer, `difficulty` Integer, `is_correct` Boolean, `user_answer` Text, `time_spent_sec` Integer, `rating_delta` Float, `rating_after` Float, `created_at` DateTime | `user_id` | — |
| `UserProgress` | `user_progress` | `user_id` FK→users, `topic` String(200), `class_level` Integer, `rating` Float, `tasks_solved` Integer, `tasks_attempted` Integer, `current_difficulty` Integer, `last_activity` DateTime | `user_id` | PK `(user_id, topic, class_level)` |
| `OlympiadPrep` | `olympiad_prep` | `id` Integer PK, `slug` String(100) unique, `name` String(200), `short_name` String(50), `description` Text, `grades` Text (JSON), `stages` Text (JSON), `official_url` String(500), `logo_path` String(500), `color_hex` String(20), `sort_order` Integer, `is_active` Boolean, `created_at` DateTime | — | `slug` |
| `PrepPlan` | `prep_plans` | `id` Integer PK, `user_id` FK→users, `olympiad_id` FK→olympiad_prep, `target_stage` String(100), `target_grade` Integer, `start_date` Date, `target_date` Date, `baseline_radar` Text (JSON), `current_radar` Text (JSON), `daily_task_count` Integer, `status` String(20), `current_streak` Integer, `longest_streak` Integer, `created_at` DateTime | `user_id`, `olympiad_id` | — |
| `PrepDay` | `prep_days` | `id` Integer PK, `plan_id` FK→prep_plans, `date` Date, `target_topics` Text (JSON), `problem_ids` Text (JSON), `completed_problem_ids` Text (JSON), `day_score` Integer, `status` String(20), `created_at` DateTime | `plan_id` | — |
| `BrokenTaskLog` | `broken_task_log` | `id` Integer PK, `task_id` Integer, `surface` String(50), `reasons` Text, `hits` Integer, `detected_at` DateTime | — | — |
| `TaskSolution` | `task_solutions` | `id` Integer PK, `user_id` FK→users, `task_id` FK→adaptive_tasks, `plan_id` FK→prep_plans, `day_id` FK→prep_days, `user_answer` Text, `user_solution` Text, `original_photo_url` String(500), `photo_hash` String(64), `ocr_raw_output` Text, `ocr_corrected` Text, `was_corrected` Boolean, `is_correct` Boolean, `feedback_json` Text, `consent_for_training` Boolean, `quality_score` Float, `created_at` DateTime | `user_id`, `task_id`, `plan_id`, `day_id` | — |
| `DrawingGeneration` | `drawing_generations` | `id` Integer PK, `user_id` FK→users, `problem_sha256` String(64), `problem` Text, `generated_code` Text, `model` String(120), `status` String(20), `error` Text, `repair_iters` Integer, `render_ms` Integer, `cost_usd` Float, `image_path` String(500), `image_size` Integer, `critique_rounds` Integer, `critique_accepted` Integer, `critique_rejected` Integer, `critique_findings_json` Text, `created_at` DateTime | `user_id` | — |
| `GroupChat` | `group_chats` | `id` Integer PK, `name` String(120), `avatar_emoji` String(8), `owner_id` FK→users, `created_at` DateTime | `owner_id` | — |
| `GroupMember` | `group_members` | `id` Integer PK, `group_id` FK→group_chats, `user_id` FK→users, `role` String(16), `joined_at` DateTime | `group_id`, `user_id` | `(group_id, user_id)` |
| `GroupMessage` | `group_messages` | `id` Integer PK, `group_id` FK→group_chats, `sender_id` FK→users, `kind` String(20), `body` Text, `attachment_url` String(400), `attachment_kind` String(16), `attachment_name` String(255), `attachment_size` Integer, `created_at` DateTime | `group_id`, `sender_id` | — |

### 2.2 models_curator.py (lines 1–51)

| Model | Table | Key Fields | FK | Unique |
|-------|-------|-----------|-----|--------|
| `CuratorState` | `curator_state` | `id` Integer PK, `user_id` FK→users unique, `target_olympiads` JSON, `grade` Integer, `goal_text` Text, `prep_plan` JSON, `prep_state` JSON, `onboarding_done` Boolean, `last_diagnostic_id` FK→adaptive_test_results, `summary` Text, `created_at` DateTime, `updated_at` DateTime | `user_id`, `last_diagnostic_id` | `user_id` |
| `Subtopic` | `subtopics` | `id` Integer PK, `slug` String(100) unique, `title` String(200), `parent_topic` String(50), `olympiad_weights` JSON, `is_active` Boolean, `created_at` DateTime | — | `slug` |
| `SubtopicProgress` | `subtopic_progress` | `id` Integer PK, `user_id` FK→users, `subtopic_id` FK→subtopics, `mastery` Float, `attempts` Integer, `correct` Integer, `last_seen_at` DateTime, `updated_at` DateTime | `user_id`, `subtopic_id` | `(user_id, subtopic_id)` |

### 2.3 curator/models.py (lines 1–370)

| Model | Table | Key Fields | FK | Unique |
|-------|-------|-----------|-----|--------|
| `StudentDiagnostic` | `student_diagnostics` | `id` Integer PK, `user_id` FK→users, `session_id` String(64), `grade` Integer, `status` String(32), `profile_json` Text (JSON), `overall_pct` Integer, `total_questions` Integer, `correct_answers` Integer, `started_at` DateTime, `completed_at` DateTime, `question_log` Text (JSON), `ai_summary` Text, `created_at` DateTime | `user_id` | — |
| `LearningPlan` | `learning_plans` | `id` Integer PK, `user_id` FK→users, `title` String(255), `goal` Text, `plan_type` String(32), `baseline_profile` Text (JSON), `start_date` Date, `target_date` Date, `target_olympiad` String(255), `target_stage` String(64), `status` String(32), `roadmap_json` Text (JSON), `current_profile` Text (JSON), `total_weeks` Integer, `current_week` Integer, `topic_priorities` Text (JSON), `created_at` DateTime, `updated_at` DateTime | `user_id` | — |
| `CuratorTaskAttempt` | `task_attempts` | `id` Integer PK, `user_id` FK→users, `task_id` Integer, `task_source` String(32), `task_type` String(32), `plan_id` FK→learning_plans, `topic` String(100), `difficulty` Integer, `user_answer` Text, `correct_answer` Text, `is_correct` Boolean, `attempts_count` Integer, `time_spent_sec` Integer, `used_hints` Boolean, `hints_shown` Integer, `hints_used` Integer, `ai_feedback` Text (JSON), `method_score` Float, `attempted_at` DateTime | `user_id`, `plan_id` | — |
| `ProgressLog` | `progress_log` | `id` Integer PK, `user_id` FK→users, `plan_id` FK→learning_plans, `log_date` Date, `log_type` String(16), `profile_snapshot` Text (JSON), `tasks_solved` Integer, `tasks_total` Integer, `accuracy_pct` Float, `minutes_spent` Float, `streak_days` Integer, `max_streak` Integer, `plan_week` Integer, `is_stuck` Boolean, `ai_advice` Text, `created_at` DateTime | `user_id`, `plan_id` | `(user_id, log_date, log_type)` |

### 2.4 Table Usage Audit (grep by class name)

| Model | Declared in | Used in code? | Key consumers |
|-------|------------|---------------|---------------|
| `CuratorState` | [`models_curator.py:10`](models_curator.py:10) | **YES** | `routes/prep.py`, `curator/monthly_cycle.py`, `curator/routes.py` |
| `Subtopic` | [`models_curator.py:28`](models_curator.py:28) | **NOT FOUND** — declared but never queried in any route/service | — |
| `SubtopicProgress` | [`models_curator.py:39`](models_curator.py:39) | **NOT FOUND** — declared but never queried in any route/service | — |
| `CuratorTaskAttempt` | [`curator/models.py:216`](curator/models.py:216) | **YES** | `curator/routes.py:579` (post-review profile update) |
| `ProgressLog` | [`curator/models.py:291`](curator/models.py:291) | **YES** | `curator/routes.py:1109` (health check), `curator/progress.py` |
| `StudentDiagnostic` | [`curator/models.py:15`](curator/models.py:15) | **YES** | `curator/routes.py`, `curator/diagnostics.py` |
| `LearningPlan` | [`curator/models.py:95`](curator/models.py:95) | **YES** | `curator/routes.py`, `curator/planner.py` |
| `TaskBank` | [`curator/task_bank.py`](curator/task_bank.py) | **YES** | `curator/diagnostics.py:414` |
| `AdaptiveTask` | [`models.py:814`](models.py:814) | **YES** | Nearly everywhere: `routes/prep.py`, `daily_tasks/profile.py`, `app.py` |
| `DailyQuest` | [`models.py:934`](models.py:934) | **YES** | `routes/prep.py`, `app.py` |
| `PrepPlan` | [`models.py:1183`](models.py:1183) | **YES** | `routes/prep.py`, `services/prep_planner.py` |
| `TopicMastery` | [`models.py:1017`](models.py:1017) | **YES** | `routes/prep.py:969` (coach page radar) |

---

## 3. Migration System

### 3.1 Dual Migration Strategy

The project uses **TWO** migration systems simultaneously:

**A. Alembic (alembic_migrations/)**
- Directory: [`alembic_migrations/`](alembic_migrations/)
- Env file: [`alembic_migrations/env.py`](alembic_migrations/env.py:1) — uses Flask-Migrate (`current_app.extensions['migrate']`)
- Config: [`alembic_migrations/alembic.ini`](alembic_migrations/alembic.ini)
- Versions directory: `alembic_migrations/versions/` — **empty** (NOT FOUND — no revision files exist)
- Latest revision: **NOT FOUND** (no migration files in alembic)

**B. Manual migration scripts (migrations/)**
- Directory: [`migrations/`](migrations/) — contains ~50 standalone `.py` scripts
- Examples: `add_curator_tables.py`, `add_daily_tasks_tables.py`, `add_prep_plans.py`, `add_pregen_queue.py`, `add_friendships_v2.py`, `add_telegram_id_to_user.py`, `add_olympiad_prep.py`, etc.
- Format: Each script is a standalone Python file that calls `ALTER TABLE` or `CREATE TABLE` via `db.session.execute(text(...))`.

**C. Auto-migration (app.py startup)**
- [`app.py:275`](app.py:275): On every startup, `app.py` inspects table schemas and adds missing columns via raw SQL `ALTER TABLE ADD COLUMN`.
- **This is how `adaptive_tasks` gets columns like `subtopic`, `attempts_count`, `solves_count`, `actual_solve_rate`, `suggested_level`, `needs_reclassification`, `task_type`, `source`.**
- [`app.py:327`](app.py:327): Adds `is_calibration` to `daily_task_items`.
- [`app.py:349`](app.py:349): Adds `prep_state` to `curator_state`.
- [`app.py:370`](app.py:370): Creates `tutor_calls` table if missing.

**D. Schema creation**
- [`models.py:1498`](models.py:1498): `init_db()` calls `db.create_all()` — this is the fallback for missing tables.
- **Production command:** NOT FOUND — no documented production migration command. Schema evolves through auto-migration ALTER TABLE on each app restart.

---

## 4. Adaptive Test

### 4.1 IRT Engine

The "IRT engine" in this project is **NOT** a standalone IRT library. It is a home-grown adaptive algorithm with two variants:

**Variant A: Session-based adaptive test (`/adaptive_test_simple`)**
- Location: [`app.py:7235`](app.py:7235) → `adaptive_test_simple()` route
- Session state: `session['adaptive_slots']` — list of difficulty slots, 25 items
- Starting level: `session['adaptive_current_difficulty'] = 3` (hardcoded) — [`app.py` line near `adaptive_current_difficulty` assignment]
- Number of tasks: **25** — set via `session['adaptive_slots']` with 25 elements
- Task selection: from `AdaptiveTask` table filtered by `class_level`, `topic`, and `difficulty_level` matching `session['adaptive_current_difficulty']`, excluding `session['adaptive_shown_task_ids']`
- Level recalculation: `session['adaptive_current_difficulty'] = new_level` after each answer; new_level is adjusted up/down by ±1 based on correctness
- Result writing: results saved to [`AdaptiveTestResult`](models.py:907) via [`app.py:10830`](app.py:10830) `/api/save_test_result`
- Function signatures are inline lambdas within app.py, not named utility functions — see lines 7235–7789

**Variant B: Profile-based system (daily_tasks/profile.py)**
- `percent_to_level(pct)` — [`daily_tasks/profile.py:140`](daily_tasks/profile.py:140): converts pct (0–100) → level (1–5)
- `score_to_target_level(correct, total, final_level)` — [`daily_tasks/profile.py:245`](daily_tasks/profile.py:245): full IRT-like level 1–8 with pull-down for weak topics
- `build_profile(user_id)` — [`daily_tasks/profile.py:667`](daily_tasks/profile.py:667): complete profile builder
- Starting level for unmeasured topics: `CALIBRATION_START_LEVEL = 2` — [`daily_tasks/profile.py:92`](daily_tasks/profile.py:92)
- Result reading: from `AdaptiveTestResult` table (client code creates rows directly)
- Result writing: profile writes to `AdaptiveTestResult` rows; level stored in `final_level` (Integer 1–7)

**Variant C: Curator diagnostic (curator/diagnostics.py)**
- `get_next_question(session_id)` — [`curator/diagnostics.py:65`](curator/diagnostics.py:65): selects next task via TaskBank
- `submit_answer(session_id, task_id, answer, time_spent_sec)` — [`curator/diagnostics.py:142`](curator/diagnostics.py:142): updates topic profile inside StudentDiagnostic
- Starting level: `START_DIFFICULTY = 4` — [`curator/config.py:31`](curator/config.py:31)
- Task count: `TOTAL_QUESTIONS_TARGET = 15` — [`curator/config.py:28`](curator/config.py:28)
- Reads `topic_stats` from `StudentDiagnostic.profile_json`
- Writes results to `StudentDiagnostic.profile_json` and `question_log`

### 4.2 Total Tasks in Test

| System | Task Count | Defined at |
|--------|-----------|------------|
| `/adaptive_test_simple` | 25 | `session['adaptive_slots']` init in [`app.py`] |
| Curator diagnostic | 15 | [`curator/config.py:28`](curator/config.py:28) `TOTAL_QUESTIONS_TARGET` |
| Morning prep test | 5 | [`curator/monthly_cycle.py:389`](curator/monthly_cycle.py:389) `get_subtopic_test(..., count=5)` |
| Onboarding inline test | 21 | [`routes/prep.py:1512`](routes/prep.py:1512) `get_onboarding_tasks(grade, limit=21)` |

---

## 5. Task Source

### 5.1 How Tasks Enter AdaptiveTask

**Primary mechanism: auto-migration populates columns; actual data likely from formyla_dataset JSON import.**

- The `import/` directory exists but is **empty** ([`import/`](import/)).
- The file `adaptive_data.py` is imported in [`app.py:30`](app.py:30) — if it exists, `ADAPTIVE_DB` is populated from it. **No `adaptive_data.py` file was found in the workspace.**
- [`app.py:33`](app.py:33): `print("ВНИМАНИЕ: Файл adaptive_data.py не найден или пуст.")` — confirms this fallback triggers.
- The database file `formyla.db` exists at workspace root, suggesting tasks were imported via a script now deleted or run ad-hoc.
- Files like `curated_bank_L1_L5_fixed.json`, `formyla_dataset_slightly_fixed.json`, `FORMLYA_L1_L5_TOP5.jsonl` exist in workspace — likely import sources for a now-gone or ad-hoc import script.

**Import scripts found:**
- `services/vsosh_full_seed.py` — VsesОШ full seed (olympiad tasks, not adaptive)
- `services/olympiad_autoseed.py` — olympiad auto-seed
- `scripts/` directory — **NOT FOUND** in workspace listing
- `_seed_102.py`, `_reseed_secrets.py` — secrets/102 data seeding, not adaptive tasks

**Conclusion: No import script for AdaptiveTask was found. Tasks were likely imported via a one-off script that is no longer in the repository.**

### 5.2 AdaptiveTask Fields

Full field list from [`models.py:814`](models.py:814):

| # | Field | Type | Filled? |
|---|-------|------|---------|
| 1 | `id` | Integer PK | Always |
| 2 | `class_level` | Integer | Always |
| 3 | `difficulty_level` | Integer | Always |
| 4 | `topic` | String(200) | Always |
| 5 | `subtopic` | String(100) | NOT FOUND (added via auto-migration, likely NULL for most) |
| 6 | `task_text` | Text | Always |
| 7 | `solution` | Text | Always |
| 8 | `criteria_1_point` | Text | Always |
| 9 | `criteria_2_points` | Text | Always |
| 10 | `created_at` | DateTime | Auto |
| 11 | `correct_answer` | Text | NOT FOUND |
| 12 | `is_flagged` | Boolean | Default False |
| 13 | `reports_count` | Integer | Default 0 |
| 14 | `flagged_reason` | Text | NOT FOUND |
| 15 | `attempts_count` | Integer | Auto-migration, likely NULL or 0 |
| 16 | `solves_count` | Integer | Auto-migration, likely NULL or 0 |
| 17 | `actual_solve_rate` | Float | Auto-migration, likely NULL |
| 18 | `suggested_level` | Integer | Auto-migration, likely NULL |
| 19 | `needs_reclassification` | Boolean | Auto-migration, default False |
| 20 | `last_calibrated_at` | DateTime | Auto-migration, likely NULL |
| 21 | `subject` | String(20) | Auto-migration, likely NULL |
| 22 | `source_id` | String(120) | Auto-migration, likely NULL |
| 23 | `task_type` | Text | Auto-migration, likely NULL |
| 24 | `source` | Text | Auto-migration, likely NULL |
| 25 | `needs_review` | Boolean | Default False |
| 26 | `llm_suggested_answer` | Text | NOT FOUND |
| 27 | `llm_suggested_solution` | Text | NOT FOUND |
| 28 | `review_reason` | Text | NOT FOUND |
| 29 | `review_flagged_at` | DateTime | NOT FOUND |

**DB access:** DB is accessible (app is running). Counters: NOT FOUND (no DB query was run for this audit).

### 5.3 Image Storage

- **Table for images:** NOT FOUND as a dedicated model. Images are stored in `DrawingGeneration.image_path` ([`models.py:1415`](models.py:1415)).
- `IMAGE_MAP` is imported from `problem_images` in [`app.py:35`](app.py:35) — maps problem IDs to image paths.
- [`app.py:39`](app.py:39): `services.figures_manifest.get_figures_for_problem()` serves figures.
- **Static file serving:** NOT FOUND as an explicit route. The project serves static files via Flask's default `/static/` prefix.
- **Image URL prefix:** NOT FOUND — no explicit image-serving blueprint. Images are likely served from `/static/` or an external R2/CDN.

---

## 6. Curator Decision Points

### 6.1 coach_greeting() — Branch Analysis

Function: [`routes/prep.py:1089`](routes/prep.py:1089) `coach_greeting()`

Branches in order of check:

| # | Condition | Scenario | Return line |
|---|-----------|----------|-------------|
| 1 | `action == 'onboarding_tasks'` (query param) | JSON with tasks list | [`routes/prep.py:1115`](routes/prep.py:1115) |
| 2 | `action == 'prep_test_tasks'` (query param) | JSON with tasks + subtopic | [`routes/prep.py:1122`](routes/prep.py:1122) |
| 3 | `action == 'subtopic_test'` (query param) | JSON with tasks | [`routes/prep.py:1133`](routes/prep.py:1133) |
| 4 | `not grade` (no class selected) | `need_grade` | [`routes/prep.py:1136`](routes/prep.py:1136) |
| 5 | `session['coach_test']` exists and active | `test_in_progress` | [`routes/prep.py:1164`](routes/prep.py:1164) |
| 6 | `measured_count == 0 and questionnaire_done` | `open_url` → `/olympiad-test` | [`routes/prep.py:1192`](routes/prep.py:1192) |
| 7 | `measured_count == 0 and not questionnaire_done` | `open_url` → `/olympiad-test` | [`routes/prep.py:1203`](routes/prep.py:1203) |
| 8 | `daily_quest exists and completed_at is None` | `daily_tasks_ready` | [`routes/prep.py:1225`](routes/prep.py:1225) |
| 9 | `daily_quest exists and completed_at is not None` | `day_summary` | [`routes/prep.py:1262`](routes/prep.py:1262) |
| 10 | `_has_prep and month_completed` | `prep_month_complete` | [`routes/prep.py:1313`](routes/prep.py:1313) |
| 11 | `_has_prep and is_test_day and not tested` | `prep_morning_test` | [`routes/prep.py:1338`](routes/prep.py:1338) |
| 12 | `_has_prep and is_test_day and tested` | `prep_test_taken` | [`routes/prep.py:1363`](routes/prep.py:1363) |
| 13 | `_has_prep and not is_test_day and has_tasks` | `prep_tasks_ready` | [`routes/prep.py:1389`](routes/prep.py:1389) |
| 14 | `_has_prep and not is_test_day and not has_tasks` | `prep_task_day` | [`routes/prep.py:1412`](routes/prep.py:1412) |
| 15 | (fallback: no quest, profile exists) | `daily_test` | [`routes/prep.py:1443`](routes/prep.py:1443) |
| 16 | (exception safety net) | `fallback` | [`routes/prep.py:1454`](routes/prep.py:1454) |

### 6.2 coach_chat() — Branch Analysis

Function: [`routes/prep.py:2178`](routes/prep.py:2178) `coach_chat()`

Branches in order:

| # | Condition | Action | Line |
|---|-----------|--------|------|
| 1 | `not message` (empty input) | 400 error | [`routes/prep.py:2192`](routes/prep.py:2192) |
| 2 | `q_state.active` (questionnaire in progress, not last question) | Return next questionnaire question | [`routes/prep.py:2213`](routes/prep.py:2213) |
| 3 | `q_state.active` (questionnaire last question) | Compute level, save, return summary, set `questionnaire_done=True` | [`routes/prep.py:2222`](routes/prep.py:2222) |
| 4 | `session['coach_test'].active` AND `awaiting_difficulty_for` AND valid difficulty (1-5) AND all tasks done | Submit onboarding results | [`routes/prep.py:2266`](routes/prep.py:2266) |
| 5 | `session['coach_test'].active` AND `awaiting_difficulty_for` AND valid difficulty AND more tasks remain | Show next task | [`routes/prep.py:2274`](routes/prep.py:2274) |
| 6 | `session['coach_test'].active` AND `awaiting_difficulty_for` AND invalid difficulty | Ask again for difficulty rating | [`routes/prep.py:2296`](routes/prep.py:2296) |
| 7 | `session['coach_test'].active` AND `current_index < total` (task answer) | Evaluate via AI, show result + ask difficulty | [`routes/prep.py:2301`](routes/prep.py:2301) |
| 8 | (fallback: no special state) | Free-form chat via DeepSeek | [`routes/prep.py:2438`](routes/prep.py:2438) |

---

## 7. Flask Session Keys

### 7.1 All Session Keys

| Key | Written in | Read in | Cleared? |
|-----|-----------|---------|----------|
| `device_id` | [`app.py`] (guest auth) | [`app.py`] | NO — never cleared |
| `user_id` | [`app.py`] (login) | [`app.py`] | NO — persists as login state |
| `solved_problems` | [`app.py`] | [`app.py`] | NO |
| `olyad_grade` | [`app.py`], [`services/olympiad_adaptive.py`] | [`app.py`] | NO |
| `olyad_theme` | [`app.py`], [`services/olympiad_adaptive.py`] | [`app.py`] | NO |
| `olyad_level` | [`app.py`] | [`app.py`] | NO |
| `olyad_task_num` | [`app.py`] | [`app.py`] | NO |
| `olyad_shown` | [`app.py`] | — | NO |
| `olyad_results` | [`app.py`] | [`app.py`] | NO |
| `olyad_current_task` | [`app.py`] | — | NO |
| `olyad_current_level` | [`services/olympiad_adaptive.py`] | [`services/olympiad_adaptive.py`] | NO |
| `olyad_task_count` | [`services/olympiad_adaptive.py`] | [`services/olympiad_adaptive.py`] | NO |
| `olyad_shown_uids` | [`services/olympiad_adaptive.py`] | [`services/olympiad_adaptive.py`] | NO |
| `verify_email` | [`app.py`] | — | NO |
| `linking_mode` | [`app.py`] | — | NO |
| `mock_task_ideas` | [`app.py`] | [`app.py`] | NO |
| `mock_task_texts` | [`app.py`] | [`app.py`] | NO |
| `mock_task_subtopics` | [`app.py`] | — | NO |
| `free_mock_test_id` | [`app.py`] | — | NO |
| `free_mock_grade` | [`app.py`] | — | NO |
| `free_mock_level` | [`app.py`] | — | NO |
| `adaptive_topic` | [`app.py`] | [`app.py`] | NO |
| `adaptive_topic_name` | [`app.py`] | — | NO |
| `adaptive_grade` | [`app.py`] | [`app.py`] | NO |
| `adaptive_db_topic` | [`app.py`] | — | NO |
| `adaptive_filtered_tasks` | [`app.py`] | [`app.py`] | NO |
| `adaptive_current_difficulty` | [`app.py`] | [`app.py`], [`tests/test_check_adaptive_answer.py`] | NO |
| `adaptive_slots` | [`app.py`] | [`app.py`] | NO |
| `adaptive_answers` | [`app.py`] | [`app.py`] | NO |
| `adaptive_current_index` | [`app.py`] | — | NO |
| `adaptive_current_task_id` | [`app.py`] | — | NO |
| `adaptive_shown_task_ids` | [`app.py`] | — | NO |
| `adaptive_current_slot` | [`app.py`] | — | NO |
| `adaptive_completed_at` | [`app.py`] | [`app.py`] | NO |
| `partial_correct_streak` | [`app.py`] | — | NO |
| `coach_test` | [`routes/prep.py:1519`](routes/prep.py:1519) | [`routes/prep.py:1154,2248`](routes/prep.py:1154) | YES — [`routes/prep.py:2267`](routes/prep.py:2267) `session.pop('coach_test', None)` |
| `questionnaire` | [`services/questionnaire_storage.py`] | [`services/questionnaire_storage.py`] | NO — never cleared explicitly |
| `_csrf_token` | [`services/security.py`] | [`services/security.py`] | NO |

### 7.2 Keys Written But Never Cleared

All olympiad-related keys (`olyad_*`), all mock exam keys (`mock_*`, `free_mock_*`), all adaptive test keys (`adaptive_*`), `device_id`, `verify_email`, `linking_mode`, `questionnaire`, `_csrf_token`. This is **36+ keys** that accumulate in session permanently.

Only `coach_test` is properly cleaned up via `session.pop('coach_test', None)`.

---

## 8. Background Tasks

### 8.1 APScheduler Cron Jobs

All defined in [`app.py`](app.py:1588):

| # | Job ID | Schedule (MSK) | Function | File:Line | Description |
|---|--------|---------------|----------|-----------|-------------|
| 1 | `daily_streak_reset` | 00:00 | `daily_streak_reset_job()` | [`app.py:1589`](app.py:1589) | Reset streaks at midnight |
| 2 | `daily_quest_deadline_reminder` | 18:00, 21:00 | `daily_quest_deadline_reminder_job()` | [`app.py:1601`](app.py:1601) | Push notify users who haven't completed daily tasks |
| 3 | `curator_evening_notification` | 19:00, 20:00, 21:00 | `curator_evening_notification_job()` | [`app.py:1648`](app.py:1648) | Evening curator check + push (motivation/discipline/praise) |
| 4 | `curator_morning_prep_reminder` | 09:00 | `curator_morning_prep_reminder_job()` | [`app.py:1695`](app.py:1695) | Morning prep cycle reminder (test day or task-only day) |
| 5 | `curator_evening_prep_generate` | 18:00 | `curator_evening_prep_generate_job()` | [`app.py:1757`](app.py:1757) | Evening task generation for monthly prep cycle |
| 6 | `process_pregen_queue` | Every 30 min | (anon lambda) | [`app.py:1828`](app.py:1828) | Process pre-generation queue |
| 7 | `daily_midnight_assign` | 00:05 | (anon lambda) | [`app.py:1846`](app.py:1846) | Midnight daily task assignment |

**Scheduler framework:** `flask_apscheduler` — [`app.py:1541`](app.py:1541) `from flask_apscheduler import APScheduler`
**Startup:** [`app.py`] `scheduler.start()` called after app initialization.

---

## 9. LLM Calls

### 9.1 All LLM Call Sites

| # | Location | Client | Model | Max Tokens | Timeout | Retry | Error Handling |
|---|----------|--------|-------|------------|---------|-------|----------------|
| 1 | [`routes/prep.py:526`](routes/prep.py:526) | `DeepSeekClient` (direct API) | `deepseek-chat` | 500 | 90s (default) | 2 retries | Fallback to simple string comparison |
| 2 | [`routes/prep.py:2439`](routes/prep.py:2439) | `DeepSeekClient.generate_with_reasoning()` | `deepseek-reasoner` | 2000 | 300s | 4 retries (reasoner) | Fallback text with weak topic names |
| 3 | [`curator/diagnostics.py:291`](curator/diagnostics.py:291) | `OpenRouterClient (openrouter)` | `deepseek/deepseek-chat` | 1024 | 300s | 5 retries | Fallback to template-based summary |
| 4 | [`services/openrouter_client.py:158`](services/openrouter_client.py:158) | `OpenRouterClient.chat()` | Any (param) | 4096 (default) | 300s | 5 retries + circuit breaker | Raises `OpenRouterError` |
| 5 | [`ai/deepseek_client.py:63`](ai/deepseek_client.py:63) | `DeepSeekClient.generate()` | `deepseek-chat` | param | 90s | 2 retries | Raises `DeepSeekAPIError` |
| 6 | [`ai/deepseek_client.py:175`](ai/deepseek_client.py:175) | `DeepSeekClient.generate_with_reasoning()` | `deepseek-reasoner` | 2000 | 300s | 4 retries | Raises `DeepSeekAPIError` |

### 9.2 API Keys

| Key | Env Var | Read at |
|-----|---------|---------|
| DeepSeek direct | `DEEPSEEK_API_KEY` | [`ai/deepseek_client.py:48`](ai/deepseek_client.py:48) |
| OpenRouter | `OPENROUTER_API_KEY` | [`services/openrouter_client.py:151`](services/openrouter_client.py:151) |

### 9.3 OpenRouter Client Details
- Retries: `MAX_RETRIES = 5` — [`services/openrouter_client.py:66`](services/openrouter_client.py:66)
- Circuit breaker: 10 consecutive failures → 300s pause — [`services/openrouter_client.py:64`](services/openrouter_client.py:64)
- Rate limiter: per-model token bucket — [`services/openrouter_client.py:70`](services/openrouter_client.py:70)
- Cost tracking: logged to `generation_costs` table — [`services/openrouter_client.py:285`](services/openrouter_client.py:285)

---

## 10. Frontend: templates/prep/coach.html

### 10.1 Fetch Calls

| # | URL | Trigger | Lines |
|---|-----|---------|-------|
| 1 | `{{ url_for("prep.coach_greeting") }}` | Page load (DOMContentLoaded) | [`coach.html:510`](templates/prep/coach.html:510) |
| 2 | `{{ url_for("prep.coach_set_grade") }}` | Grade button click | [`coach.html:536`](templates/prep/coach.html:536) |
| 3 | `/prep/coach/questionnaire/start` | After grade set / onboarding flow | [`coach.html:547`](templates/prep/coach.html:547), [`coach.html:580`](templates/prep/coach.html:580), [`coach.html:877`](templates/prep/coach.html:877) |
| 4 | `{{ url_for("prep.coach_greeting") }}?action=subtopic_test&subtopic_key=...` | "Пройти тест по теме" CTA click | [`coach.html:600`](templates/prep/coach.html:600) |
| 5 | `{{ url_for("prep.coach_daily_submit") }}` | "Завершить тест" in daily test | [`coach.html:626`](templates/prep/coach.html:626) |
| 6 | `{{ url_for("prep.coach_greeting") }}?action=prep_test_tasks` | "Начать тест" for monthly prep | [`coach.html:680`](templates/prep/coach.html:680) |
| 7 | `{{ url_for("prep.coach_prep_submit_test") }}` | "Завершить тест" for monthly prep | [`coach.html:709`](templates/prep/coach.html:709) |
| 8 | `{{ url_for("prep.coach_history") }}` | Page load | [`coach.html:783`](templates/prep/coach.html:783) |
| 9 | `{{ url_for("prep.coach_chat") }}` | Chat form submit | [`coach.html:823`](templates/prep/coach.html:823) |
| 10 | `{{ url_for("prep.coach_history_delete") }}` | "Очистить историю" click | [`coach.html:854`](templates/prep/coach.html:854) |

### 10.2 Scenario Handlers

Handled in the greeting fetch `.then()` chain starting at [`coach.html:512`](templates/prep/coach.html:512):

| Scenario | Handler | Line |
|----------|---------|------|
| `start_questionnaire` | Calls `startQuestionnaire()` | [`coach.html:517`](templates/prep/coach.html:517) |
| `need_grade` | Renders grade buttons (5-11) inline | [`coach.html:518`](templates/prep/coach.html:518) |
| `test_in_progress` | Hides greeting, focuses input | [`coach.html:570`](templates/prep/coach.html:570) |
| `onboarding_test` | Fetches `/prep/coach/questionnaire/start` | [`coach.html:576`](templates/prep/coach.html:576) |
| `daily_test` | Renders subtopic test with task cards + CTA | [`coach.html:593`](templates/prep/coach.html:593) |
| `daily_tasks_ready` | CTA → `/daily-tasks` | [`coach.html:650`](templates/prep/coach.html:650) |
| `day_summary` | CTA buttons from data | [`coach.html:655`](templates/prep/coach.html:655) |
| `recommend_olympiad` / `need_test` | Legacy CTA buttons | [`coach.html:660`](templates/prep/coach.html:660) |
| `prep_morning_test` | Inline 5-task test with correctness toggle | [`coach.html:672`](templates/prep/coach.html:672) |
| `prep_test_taken` | CTA to daily tasks + adaptive test link | [`coach.html:744`](templates/prep/coach.html:744) |
| `prep_tasks_ready` | CTA to daily tasks + adaptive test link | [`coach.html:751`](templates/prep/coach.html:751) |
| `prep_task_day` | CTA to theory review + adaptive test link | [`coach.html:758`](templates/prep/coach.html:758) |
| `prep_month_complete` | CTA to start new month + adaptive test link | [`coach.html:765`](templates/prep/coach.html:765) |

**Missing handler:** `open_url` scenario is returned by backend (lines 1195, 1205 of prep.py) but the frontend has **no branch** for `scenario === 'open_url'`. The greeting text includes `cta_url` and `cta_text` but no handler renders them when scenario is `open_url`.

### 10.3 HTML Assembled in JS

1. [`coach.html:522-527`](templates/prep/coach.html:522): Grade buttons (5–11) built as HTML string and injected into `greetingEl`.
2. [`coach.html:604-614`](templates/prep/coach.html:604): Daily test task cards with ✅/❌ buttons built as HTML string.
3. [`coach.html:684-695`](templates/prep/coach.html:684): Monthly prep test task cards with correctness toggle built as HTML string.
4. [`coach.html:717-727`](templates/prep/coach.html:717): Prep test results message built as HTML string.

### 10.4 Math Rendering

- **KaTeX** is used for math rendering — referenced in [`coach.html:19`](templates/prep/coach.html:19) (`.chat-msg .katex` CSS) and via `reRenderMath()` function calls at [`coach.html:811,832`](templates/prep/coach.html:811).
- **Initialization:** `reRenderMath` is called per-message after DOM insertion (not globally). The function itself is defined in `base.html` or an external script (not in coach.html).
- **Chart.js** for radar chart: loaded from CDN at [`coach.html:1034`](templates/prep/coach.html:1034).

---

## 11. Defects Found

### 11.1 Dead Code / Unused Models

1. **`Subtopic` model** ([`models_curator.py:28`](models_curator.py:28)) — declared, imported in [`app.py:269`](app.py:269), but **never queried** in any route, service, or view. The code uses `daily_tasks.monthly_plan.subtopic_title()` and `_ordered_subtopics_for_grade()` instead.

2. **`SubtopicProgress` model** ([`models_curator.py:39`](models_curator.py:39)) — declared, imported, but **never queried**. Progress is tracked via `AdaptiveTestResult`, `DailyQuest`, and `TopicMastery` instead.

3. **`UserTopicProgress` model** ([`models.py:880`](models.py:880)) — declared with relationship to `User` ([`models.py:62`](models.py:62)), but **never queried** in any route. Profile logic uses `AdaptiveTestResult` + `TaskSolution` instead.

4. **`UserProgress` model** ([`models.py:1110`](models.py:1110)) — declared, but **never queried** in any route. Analytics uses `TestResult` and `TopicMastery` instead.

### 11.2 Unreachable Branches

5. **`coach_greeting` `open_url` scenario** — backend returns scenario `'open_url'` at [`routes/prep.py:1195,1205`](routes/prep.py:1195) with `cta_url` and `cta_text`, but the frontend has **no handler** for this scenario. The greeting text contains the URL as text, but no clickable CTA is rendered. The user sees a plain-text URL.

### 11.3 Frontend/Backend Desync

6. **`coach_greeting` returns `recommend_olympiad` in `day_summary`** at [`routes/prep.py:1265`](routes/prep.py:1265), but the frontend `day_summary` handler at [`coach.html:655`](templates/prep/coach.html:655) **does not render `data.recommended_olympiad`** — it only renders `cta_url`/`cta_text`.

7. **`coach_greeting` scenario `need_test`** is handled in frontend ([`coach.html:660`](templates/prep/coach.html:660)) but **never returned** by the backend. The backend has no scenario named `need_test` — this is dead frontend code.

8. **`coach_chat` questionnaire flow** — when `questionnaire_done=true`, the frontend does `window.location.reload()` after 1.5s ([`coach.html:838`](templates/prep/coach.html:838)), but the backend has already committed `ChatMessage` rows with the summary ([`routes/prep.py:2237`](routes/prep.py:2237)). On reload, the greeting fetch runs again, but the chatbot history fetch may show duplicate messages.

### 11.4 Missing Error Handling

9. **`_evaluate_solution` DeepSeek fallback** — at [`routes/prep.py:580`](routes/prep.py:580), the except block catches all exceptions and falls back to simple answer comparison. However, if `correct_answer` is also empty/null, it returns `{'verdict': 'error', ...}` with a generic message. The frontend does not handle `verdict == 'error'` — it will display the error message as if it were a normal evaluation.

10. **`coach_chat` free-form chat** — at [`routes/prep.py:2444`](routes/prep.py:2444), if DeepSeek throws, the fallback message is saved to history. But if `profile` is `None` (failed to build), `weak_names_str` at line 2399 will be `'нет данных'`, and the fallback reads "Стоит подтянуть: нет данных" — a confusing message.

### 11.5 Session Bloat

11. **36+ session keys never cleared** — all `olyad_*`, `mock_*`, `free_mock_*`, `adaptive_*`, and utility keys persist indefinitely in the Flask session cookie. Only `coach_test` is cleaned up. This causes session cookie size growth and potential 4KB cookie limit issues.

### 11.6 Race Conditions

12. **`coach_greeting` reads `session['coach_test']` without locking** — at [`routes/prep.py:1154`](routes/prep.py:1154). If two tabs are open, the session state can be overwritten between the read and the subsequent `coach_chat` write, causing lost answers or test state corruption.

### 11.7 Data Integrity

13. **`DailyQuest.ai_comment` used as structured data store** — at [`routes/prep.py:1893`](routes/prep.py:1893), `coach_day_complete()` parses `ai_comment` with string splitting to extract the level: `for part in quest.ai_comment.split(','): if 'уровень:' in part: ...`. This is fragile — if the comment format changes, level parsing silently fails (returns default 2).
