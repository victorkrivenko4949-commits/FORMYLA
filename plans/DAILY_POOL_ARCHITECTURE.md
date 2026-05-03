# Daily Olympiad Pool — Architecture Plan

## 1. Overview

**Goal**: Generate 5 premium-quality math problems per day for every (olympiad, grade, round) combination, 30 days ahead.

**Scale**:
- 97 unique combinations (from current OLYMPIADS_DB normalization → ~65-97 after cleanup)
- 30 days = 2,910–4,850 variants = 14,550–24,250 problems
- Priority: day+1 for ALL combos first, then day+2, etc.

---

## 2. Normalization (Step 0)

### 2.1 Round Normalization Map

| Raw value | Normalized enum |
|-----------|----------------|
| `qualifying` | `selection` |
| `final` | `final` |
| `regional` | `regional` |
| `municipal` | `municipal` |
| `school` | `school` |
| `distance` | `distance` |
| `spring_hard` | `spring_hard` |
| `spring_base`, `spring_basic` | `spring_basic` |
| `autumn_hard`, `fall_hard` | `autumn_hard` |
| `autumn_base`, `fall_basic` | `autumn_basic` |
| `1`, `2` | `selection` (numbered rounds → selection) |

### 2.2 Olympiad Title Normalization

| Raw slug | Canonical title |
|----------|----------------|
| `euler` | Олимпиада Эйлера |
| `formula_unity` | Формула Единства |
| `kurchatov` | Курчатов |
| `lomonosov` | Ломоносов |
| `phystech` | МФТИ |
| `pvg` | Покори Воробьёвы горы |
| `spbgu` | СПбГУ |
| `turgor` | Турнир городов |
| `vsosh` | ВсОШ |
| `vysshaya_proba` | Высшая проба |

### 2.3 Archive Import

All 798 combos (~4000+ problems) loaded into `problems_archive` table for Analyzer context.

---

## 3. File Structure (new files only)

```
feature/daily-olympiad-fullscale/
├── migrations/
│   └── add_daily_pool_tables.py          # pgvector + new tables
├── models/
│   └── daily_pool.py                     # SQLAlchemy models
├── prompts/
│   ├── analyzer.md                       # Opus 4.1 — analyze combo style
│   ├── generator.md                      # GPT-5 — generate problem
│   ├── solver.md                         # o1-pro — solve & verify
│   ├── critic.md                         # Opus 4.1 — quality score
│   ├── polisher.md                       # GPT-4o — final polish
│   └── meta_reviewer.md                  # Opus 4.1 — variant coherence
├── services/
│   ├── openrouter_client.py              # Rate-limited OpenRouter wrapper
│   ├── daily_pool/
│   │   ├── __init__.py
│   │   ├── normalizer.py                 # Step 0: normalize OLYMPIADS_DB
│   │   ├── analyzer.py                   # Stage A: analyze combo
│   │   ├── generator.py                  # Stage B: generate problem
│   │   ├── solver.py                     # Stage C: solve & verify
│   │   ├── critic.py                     # Stage D: quality critique
│   │   ├── embedder.py                   # Stage E: embed + dedup
│   │   ├── polisher.py                   # Stage F: final polish
│   │   └── meta_reviewer.py             # Variant-level review
├── tasks/
│   ├── __init__.py
│   ├── celery_app.py                     # Celery config
│   └── daily_pool.py                     # Celery tasks
├── scripts/
│   ├── run_full_pool.py                  # CLI orchestrator
│   └── import_archive.py                 # Import OLYMPIADS_DB → problems_archive
├── routes/
│   └── admin_daily_pool.py              # Admin panel routes
├── templates/
│   └── admin/
│       ├── daily_pool.html              # Tree view
│       └── daily_pool_task.html         # Single task detail
├── celeryconfig.py                       # Celery settings
└── README_FULLSCALE.md                   # Documentation
```

---

## 4. Database Schema

### 4.1 New Tables

```sql
-- Archive of real problems (from olympiads.py)
CREATE TABLE problems_archive (
    id              SERIAL PRIMARY KEY,
    olympiad_slug   VARCHAR(50) NOT NULL,
    olympiad_title  VARCHAR(200),
    grade           INTEGER NOT NULL,
    round           VARCHAR(30) NOT NULL,
    year            INTEGER,
    num             INTEGER,
    text            TEXT NOT NULL,
    answer          TEXT,
    solution        TEXT,
    source          VARCHAR(50) DEFAULT 'olympiads.py',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX ix_archive_combo ON problems_archive(olympiad_slug, grade, round);

-- Analysis cache (1 per combo, valid 30 days)
CREATE TABLE olympiad_analysis (
    id              SERIAL PRIMARY KEY,
    olympiad_slug   VARCHAR(50) NOT NULL,
    grade           INTEGER NOT NULL,
    round           VARCHAR(30) NOT NULL,
    analysis_json   JSONB NOT NULL,       -- themes, style, difficulty curve, etc.
    model_used      VARCHAR(100),
    tokens_used     INTEGER,
    cost_usd        NUMERIC(8,4),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    expires_at      TIMESTAMPTZ,
    UNIQUE(olympiad_slug, grade, round)
);

-- Daily variants (5 problems each)
CREATE TABLE daily_variants (
    id              SERIAL PRIMARY KEY,
    olympiad_slug   VARCHAR(50) NOT NULL,
    grade           INTEGER NOT NULL,
    round           VARCHAR(30) NOT NULL,
    variant_date    DATE NOT NULL,
    status          VARCHAR(20) DEFAULT 'pending',  -- pending/generating/approved/rejected
    quality_report  JSONB,
    meta_review     JSONB,
    total_cost_usd  NUMERIC(8,4) DEFAULT 0,
    total_tokens    INTEGER DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    approved_at     TIMESTAMPTZ,
    UNIQUE(olympiad_slug, grade, round, variant_date)
);
CREATE INDEX ix_daily_variants_date ON daily_variants(variant_date);
CREATE INDEX ix_daily_variants_status ON daily_variants(status);

-- Individual problems in a variant
CREATE TABLE daily_problems (
    id              SERIAL PRIMARY KEY,
    variant_id      INTEGER NOT NULL REFERENCES daily_variants(id) ON DELETE CASCADE,
    position        INTEGER NOT NULL,     -- 1-5
    text            TEXT NOT NULL,
    solution        TEXT,
    answer          TEXT,
    topic           VARCHAR(100),
    difficulty      INTEGER,              -- 1-10
    quality_scores  JSONB,                -- {originality, difficulty_match, style, solvability, avg}
    generation_log  JSONB,                -- {attempts, models_used, tokens, cost}
    status          VARCHAR(20) DEFAULT 'pending',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(variant_id, position)
);

-- Embeddings for deduplication (pgvector)
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE problem_embeddings (
    id              SERIAL PRIMARY KEY,
    problem_id      INTEGER REFERENCES daily_problems(id) ON DELETE CASCADE,
    archive_id      INTEGER REFERENCES problems_archive(id),
    olympiad_slug   VARCHAR(50) NOT NULL,
    grade           INTEGER NOT NULL,
    round           VARCHAR(30) NOT NULL,
    embedding       VECTOR(3072) NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX ix_embeddings_combo ON problem_embeddings(olympiad_slug, grade, round);
-- IVFFlat index for fast cosine similarity search
CREATE INDEX ix_embeddings_vector ON problem_embeddings 
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- User attempts on daily variants
CREATE TABLE user_daily_attempts (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id),
    variant_id      INTEGER NOT NULL REFERENCES daily_variants(id),
    problem_id      INTEGER NOT NULL REFERENCES daily_problems(id),
    user_answer     TEXT,
    is_correct      BOOLEAN,
    time_spent_sec  INTEGER,
    attempted_at    TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX ix_attempts_user ON user_daily_attempts(user_id, variant_id);

-- Generation cost tracking
CREATE TABLE generation_costs (
    id              SERIAL PRIMARY KEY,
    task_type       VARCHAR(50) NOT NULL,  -- analyze/generate/solve/critique/embed/polish/meta
    model           VARCHAR(100) NOT NULL,
    input_tokens    INTEGER DEFAULT 0,
    output_tokens   INTEGER DEFAULT 0,
    cost_usd        NUMERIC(8,6) NOT NULL,
    variant_id      INTEGER REFERENCES daily_variants(id),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX ix_costs_date ON generation_costs(created_at);
```

### 4.2 Existing Tables (untouched)
- `users`, `problems`, `adaptive_tests`, etc. — NO CHANGES

---

## 5. Models (SQLAlchemy)

File: `models/daily_pool.py`

```python
class ProblemsArchive(db.Model)
class OlympiadAnalysis(db.Model)
class DailyVariant(db.Model)
class DailyProblem(db.Model)
class ProblemEmbedding(db.Model)      # uses pgvector
class UserDailyAttempt(db.Model)
class GenerationCost(db.Model)
```

---

## 6. Services Architecture

### 6.1 OpenRouter Client (`services/openrouter_client.py`)

```
OpenRouterClient
├── __init__(api_key, base_url="https://openrouter.ai/api/v1")
├── chat(model, messages, **kwargs) → dict
├── embed(model, text) → list[float]
├── _rate_limit(model)              # per-model RPM limiter
├── _retry(func, max_retries=5)     # exp backoff
└── _circuit_breaker(model)         # 10 consecutive 5xx → 5min pause

Rate limits (configurable):
  claude-opus-4.1:     20 RPM
  gpt-5:              30 RPM
  o1-pro:             10 RPM
  gpt-4o:             60 RPM
  text-embedding-3-large: 200 RPM
```

### 6.2 Pipeline Services (`services/daily_pool/`)

#### A) Normalizer (`normalizer.py`)
- Load OLYMPIADS_DB
- Normalize rounds, titles
- Group by (olympiad, grade, round)
- Return list of Combo objects with all their problems
- Import into `problems_archive` table

#### B) Analyzer (`analyzer.py`)
- Input: Combo (all problems for one combination)
- Model: `anthropic/claude-opus-4.1`
- Output: JSON analysis (themes, style patterns, difficulty curve, typical answer types)
- Cached in `olympiad_analysis` table for 30 days
- Only 97 calls total (one per combo)

#### C) Generator (`generator.py`)
- Input: analysis_json + position (1-5) + date + previous problems in this variant
- Model: `openai/gpt-5`
- Output: {text, solution, answer, topic, difficulty}
- Prompt includes: analysis, few-shot from archive, constraint "no duplicate themes in variant"

#### D) Solver (`solver.py`)
- Input: problem text only (no solution/answer)
- Model: `openai/o1-pro`
- Output: {solution, answer, confidence}
- Verification: solver's answer must match generator's answer
- If mismatch → problem rejected, retry from Generator

#### E) Critic (`critic.py`)
- Input: problem text + solution + answer + analysis context
- Model: `anthropic/claude-opus-4.1`
- Output: scores {originality: 1-10, difficulty_match: 1-10, style: 1-10, solvability: 1-10, avg}
- Threshold: avg >= 8.5 to pass
- If fail → retry from Generator (max 3 attempts)

#### F) Embedder (`embedder.py`)
- Input: problem text
- Model: `openai/text-embedding-3-large` (3072 dims)
- Dedup: cosine similarity < 0.85 against last 365 days of same combo
- Also checks against archive problems
- Stores in `problem_embeddings` table

#### G) Polisher (`polisher.py`)
- Input: approved problem text + solution
- Model: `openai/gpt-4o`
- Output: final LaTeX-formatted text with \( \) and \[ \]
- Ensures Russian olympiad style, proper formatting

#### H) Meta Reviewer (`meta_reviewer.py`)
- Input: all 5 problems of a variant + analysis
- Model: `anthropic/claude-opus-4.1`
- Checks: no topic duplication, difficulty progression, style consistency
- Can reject individual problems → re-generate those positions

---

## 7. Celery Architecture

### 7.1 Config (`celeryconfig.py`)
```python
broker_url = REDIS_URL
result_backend = REDIS_URL
task_serializer = 'json'
worker_concurrency = 5
task_acks_late = True
task_reject_on_worker_lost = True
worker_prefetch_multiplier = 1
```

### 7.2 Task Hierarchy (`tasks/daily_pool.py`)

```
orchestrate_day(day_offset: int)
  └── for each combo:
        generate_variant_task.delay(combo_key, target_date)

generate_variant_task(combo_key, target_date)
  ├── ensure_analysis(combo_key)        # cached
  ├── for position in 1..5:
  │     generate_single_problem.delay(variant_id, position)
  └── after all 5: meta_review_variant.delay(variant_id)

generate_single_problem(variant_id, position)
  ├── Stage B: generate
  ├── Stage C: solve & verify
  ├── Stage D: critique (threshold 8.5)
  ├── Stage E: embed & dedup (cosine < 0.85)
  ├── Stage F: polish
  └── Save to DB immediately after each stage
      (retry loop: max 3 iterations of B→C→D)

meta_review_variant(variant_id)
  └── If problems rejected → re-queue those positions
```

### 7.3 Idempotency
- `UNIQUE(olympiad_slug, grade, round, variant_date)` prevents duplicates
- Before generating, check if variant already exists with status != 'rejected'
- If variant exists and is complete → skip
- If variant exists but incomplete → resume from last position

---

## 8. Orchestrator Script

`scripts/run_full_pool.py --days 30`

```
Algorithm:
  for day_offset in 1..30:
    for combo in all_combos:
      if variant_exists(combo, today + day_offset):
        skip
      else:
        enqueue generate_variant_task
    wait_for_day_completion(day_offset)  # optional: proceed anyway
```

Priority: ensures day+1 is fully populated before day+2 starts.

---

## 9. Admin Panel

### Routes (`routes/admin_daily_pool.py`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/admin/daily_pool` | GET | Tree view: Olympiad → Grade → Round → Date |
| `/admin/daily_pool/progress` | GET | Live stats JSON |
| `/admin/daily_pool/variant/<id>` | GET | Variant detail |
| `/admin/daily_pool/problem/<id>` | GET | Problem detail + quality report |
| `/admin/daily_pool/problem/<id>/regenerate` | POST | Re-queue problem |
| `/admin/daily_pool/problem/<id>/approve` | POST | Manual approve |
| `/admin/daily_pool/bulk_approve` | POST | Approve all with avg >= 9.0 |

### Progress Endpoint Response
```json
{
  "total_combos": 97,
  "total_days": 30,
  "total_variants_needed": 2910,
  "variants_ready": 1845,
  "variants_generating": 120,
  "variants_failed": 15,
  "total_cost_usd": 342.50,
  "cost_by_model": {...},
  "celery_queue": {"active": 20, "reserved": 150, "failed": 3}
}
```

---

## 10. Monitoring & Alerts

1. **Progress endpoint** `/admin/daily_pool/progress` — polled by frontend every 10s
2. **Telegram bot** — sends alert when:
   - A problem fails after 5 retries (all 3 B→C→D loops exhausted)
   - A model circuit breaker triggers (10 consecutive 5xx)
   - Day N is 100% complete
3. **Cost tracking** — every API call logged to `generation_costs` table
4. **Grafana-compatible** — `/admin/daily_pool/metrics` returns Prometheus-format metrics

---

## 11. Cost Estimation

| Stage | Model | Calls/problem | Tokens (avg) | Cost/call | Total (2910 variants × 5) |
|-------|-------|---------------|--------------|-----------|---------------------------|
| A: Analyze | claude-opus-4.1 | 1 per combo (97) | 50K in + 5K out | ~$1.50 | ~$145 |
| B: Generate | gpt-5 | 1.3× (retries) | 8K in + 2K out | ~$0.15 | ~$2,840 |
| C: Solve | o1-pro | 1.3× | 3K in + 5K out | ~$0.80 | ~$15,120 |
| D: Critique | claude-opus-4.1 | 1.3× | 5K in + 2K out | ~$0.45 | ~$8,505 |
| E: Embed | text-embedding-3-large | 1× | 500 tokens | ~$0.0001 | ~$1.50 |
| F: Polish | gpt-4o | 1× | 3K in + 2K out | ~$0.03 | ~$437 |
| Meta | claude-opus-4.1 | 1 per variant | 10K in + 3K out | ~$0.80 | ~$2,328 |
| **TOTAL** | | | | | **~$29,376** |

> Note: Actual costs depend on OpenRouter pricing. o1-pro is the biggest cost driver.
> With 1.3× retry factor and 97 combos × 30 days × 5 problems = 14,550 problems.

---

## 12. Timeline (estimated)

| Phase | Duration | Output |
|-------|----------|--------|
| Migration + Models | 1 hour | Tables created |
| Prompts (6 files) | 1 hour | prompts/*.md |
| OpenRouter client | 1 hour | Rate limiter + circuit breaker |
| 7 service files | 3 hours | Full pipeline |
| Celery tasks | 2 hours | Task orchestration |
| Orchestrator script | 1 hour | CLI runner |
| Admin panel | 2 hours | Routes + templates |
| Testing (1 combo × 1 day) | 30 min | Validation |
| **Total** | **~11 hours** | Full system |

---

## 13. Key Design Decisions

1. **Immediate persistence**: Each problem saved to DB right after generation — no batch accumulation
2. **Day-first ordering**: All combos get day+1 before any get day+2
3. **Idempotent**: UNIQUE constraint + status check prevents duplicates on re-run
4. **Graceful degradation**: If a model is down, circuit breaker pauses that stage; other stages continue
5. **Cost visibility**: Every API call tracked with model, tokens, cost
6. **No impact on existing system**: Completely separate tables, routes, services
7. **pgvector for dedup**: Efficient cosine similarity search across 365 days of history

---

## 14. Dependencies (new packages)

```
celery[redis]>=5.3
redis>=5.0
pgvector>=0.2
httpx>=0.25          # async HTTP for OpenRouter
tenacity>=8.2        # retry logic
tiktoken>=0.5        # token counting
```

---

## 15. Environment Variables (new)

```env
OPENROUTER_API_KEY=sk-or-...
REDIS_URL=redis://...
CELERY_BROKER_URL=redis://...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
DAILY_POOL_ENABLED=true
```

---

## AWAITING APPROVAL

This plan covers:
- [x] Step 0: Normalization
- [x] Database schema (6 tables + pgvector)
- [x] SQLAlchemy models (7 classes)
- [x] 6 prompts structure
- [x] OpenRouter client with rate limiting
- [x] 7 service files (normalizer + 6 pipeline stages + meta)
- [x] Celery tasks architecture
- [x] Orchestrator script
- [x] Admin panel
- [x] Monitoring & alerts
- [x] Cost estimation
- [x] File structure

**Ready to proceed with implementation upon your "ок".**
