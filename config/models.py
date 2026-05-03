# -*- coding: utf-8 -*-
"""
Central model configuration for Daily Olympiad Pool pipeline.

All model IDs are env-overridable. Change one line here to swap any model.

Cost estimates (per variant, 5 problems):
  Analyzer:   ~$0.02 (cached 30 days, amortized ~$0.001)
  Generator:  ~$0.05 x 5 = $0.25
  Solver:     ~$0.02 x 5 = $0.10
  Critic:     ~$0.02 x 5 = $0.10
  Polisher:   ~$0.01 x 5 = $0.05
  Meta Review: ~$0.02
  Embedder:   ~$0.001 x 5 = $0.005
  TOTAL:      ~$0.44 per variant
"""
import os

# ─── Pipeline Models ───────────────────────────────────────────────────────────

ANALYZER_MODEL = os.getenv("ANALYZER_MODEL", "anthropic/claude-sonnet-4.5")
ANALYZER_TEMPERATURE = 0.3

GENERATOR_MODEL = os.getenv("GENERATOR_MODEL", "deepseek/deepseek-chat")
GENERATOR_TEMPERATURE = 0.8

SOLVER_MODEL = os.getenv("SOLVER_MODEL", "openai/o4-mini")
SOLVER_TEMPERATURE = 0.1

CRITIC_MODEL = os.getenv("CRITIC_MODEL", "anthropic/claude-sonnet-4.5")
CRITIC_TEMPERATURE = 0.2

POLISHER_MODEL = os.getenv("POLISHER_MODEL", "deepseek/deepseek-chat")
POLISHER_TEMPERATURE = 0.2

META_REVIEWER_MODEL = os.getenv("META_REVIEWER_MODEL", "anthropic/claude-sonnet-4.5")
META_REVIEWER_TEMPERATURE = 0.2

EMBEDDER_MODEL = os.getenv("EMBEDDER_MODEL", "openai/text-embedding-3-large")

# ─── MVP Scope ─────────────────────────────────────────────────────────────────

AVAILABLE_OLYMPIADS = ["vsosh"]

# Pre-generated nightly (cron): most popular combos
# NOTE: Archive only has vsosh grades 9-11 (school/municipal/regional/final)
# Grades 5-8 will be added when archive data is available
TIER_PREGEN = [
    (9, "regional"),
    (10, "regional"),
    (11, "regional"),
    (9, "municipal"),
    (10, "municipal"),
    (11, "municipal"),
]

# Generated on-demand via /api/olympiad/daily (remaining combos)
TIER_LAZY = [
    (9, "school"),
    (10, "school"),
    (11, "school"),
    (9, "final"),
    (10, "final"),
    (11, "final"),
]

# ─── Budget Controls ───────────────────────────────────────────────────────────

MONTHLY_BUDGET_TARGET = float(os.getenv("POOL_BUDGET_TARGET", "200"))
MONTHLY_BUDGET_ALERT = float(os.getenv("POOL_BUDGET_ALERT", "400"))
MONTHLY_BUDGET_HARD_STOP = float(os.getenv("POOL_BUDGET_HARD_STOP", "500"))

# ─── Pipeline Settings ─────────────────────────────────────────────────────────

MAX_GENERATE_RETRIES = 3
MAX_META_RETRIES = 2
SIMILARITY_THRESHOLD = 0.85
LOOKBACK_DAYS = 365
ANALYSIS_CACHE_DAYS = 30

# Default stack (kept for future A/B experiments, always 'A' for now)
DEFAULT_STACK = "A"
