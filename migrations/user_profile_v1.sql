-- ============================================================
-- MIGRATION: user_profile_v1
-- Persistent user profile system for FORMYLA
-- Created: 2026-04-26
-- ============================================================
-- APPLY:   python scripts/apply_user_profile_migration.py
-- ROLLBACK: python scripts/rollback_user_profile_migration.py
-- ============================================================

-- ============================================================
-- PART 1: ALTER TABLE users
-- Add missing columns (existing: nickname, experience_points,
-- current_level, total_problems_solved, avatar_url, created_at)
-- ============================================================

-- preferences_json: extensible settings without future ALTER TABLE
-- Example: {"theme": "dark", "notifications": true, "grade": 7}
ALTER TABLE users ADD COLUMN preferences_json TEXT DEFAULT '{}';

-- xp_total: cumulative XP (separate from experience_points which may reset)
-- experience_points already exists, we keep it and add xp_total as alias
ALTER TABLE users ADD COLUMN xp_total INTEGER DEFAULT 0;

-- level: olympiad level 1-10 (current_level already exists, keep both)
-- current_level = adaptive test level, level = overall profile level
ALTER TABLE users ADD COLUMN profile_level INTEGER DEFAULT 1;

-- bio: short user description
ALTER TABLE users ADD COLUMN bio VARCHAR(300) DEFAULT NULL;

-- grade: user's school grade (5-11)
ALTER TABLE users ADD COLUMN grade INTEGER DEFAULT NULL;

-- city: optional location
ALTER TABLE users ADD COLUMN city VARCHAR(100) DEFAULT NULL;

-- is_public: profile visibility
ALTER TABLE users ADD COLUMN is_public BOOLEAN DEFAULT 1;

-- updated_at: last profile update
ALTER TABLE users ADD COLUMN updated_at DATETIME DEFAULT NULL;

-- ============================================================
-- PART 2: NEW TABLE user_test_history
-- Detailed history of all tests (adaptive + mock)
-- Replaces/extends adaptive_test_results
-- ============================================================

CREATE TABLE IF NOT EXISTS user_test_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    test_type       VARCHAR(20) NOT NULL,
    -- 'adaptive_simple' | 'adaptive_irt' | 'mock_exam' | 'daily_quest'
    topic           VARCHAR(100),
    grade           INTEGER,
    -- Results
    score           INTEGER DEFAULT 0,       -- correct answers
    total           INTEGER DEFAULT 0,       -- total questions
    accuracy        REAL DEFAULT 0.0,        -- score/total
    difficulty_avg  REAL DEFAULT 0.0,        -- average difficulty
    xp_earned       INTEGER DEFAULT 0,
    -- Timing
    started_at      DATETIME,
    completed_at    DATETIME,
    duration_sec    INTEGER,                 -- seconds spent
    -- Serialized details (JSON array of {task_id, answer, correct, difficulty})
    answers_json    TEXT DEFAULT '[]',
    -- Meta
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_uth_user_completed
    ON user_test_history(user_id, completed_at DESC);

CREATE INDEX IF NOT EXISTS idx_uth_user_topic
    ON user_test_history(user_id, topic);

-- ============================================================
-- PART 3: NEW TABLE user_task_progress
-- Per-task progress: what user has seen, solved, struggled with
-- ============================================================

CREATE TABLE IF NOT EXISTS user_task_progress (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    task_id         INTEGER NOT NULL,        -- FK to adaptive_tasks.id
    -- Counters
    seen_count      INTEGER DEFAULT 0,       -- times shown
    correct_count   INTEGER DEFAULT 0,       -- times answered correctly
    wrong_count     INTEGER DEFAULT 0,       -- times answered wrong
    -- Status
    status          VARCHAR(20) DEFAULT 'unseen',
    -- 'unseen' | 'seen' | 'struggling' | 'mastered'
    last_seen_at    DATETIME,
    last_correct_at DATETIME,
    -- User's best answer (for review)
    best_answer     VARCHAR(500),
    -- Meta
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, task_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (task_id) REFERENCES adaptive_tasks(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_utp_user_status
    ON user_task_progress(user_id, status);

CREATE INDEX IF NOT EXISTS idx_utp_user_task
    ON user_task_progress(user_id, task_id);

-- ============================================================
-- PART 4: NEW TABLE user_achievements
-- Badges and milestones
-- ============================================================

CREATE TABLE IF NOT EXISTS user_achievements (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    achievement_key VARCHAR(50) NOT NULL,
    -- Examples: 'first_test', 'streak_7', 'mastered_algebra',
    --           'solved_100', 'perfect_score', 'grade7_complete'
    title           VARCHAR(100),
    description     VARCHAR(300),
    icon            VARCHAR(10),             -- emoji
    xp_reward       INTEGER DEFAULT 0,
    earned_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, achievement_key),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_ua_user
    ON user_achievements(user_id, earned_at DESC);

-- ============================================================
-- PART 5: NEW TABLE user_xp_log
-- XP transaction log for audit and leaderboard
-- ============================================================

CREATE TABLE IF NOT EXISTS user_xp_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    xp_delta        INTEGER NOT NULL,        -- positive or negative
    reason          VARCHAR(100),
    -- 'test_completed' | 'achievement' | 'streak_bonus' | 'admin'
    reference_id    INTEGER,                 -- e.g. test_history.id
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_uxl_user
    ON user_xp_log(user_id, created_at DESC);

-- ============================================================
-- END OF MIGRATION
-- ============================================================
