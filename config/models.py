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

# v2.3: switched from deepseek-chat → claude-opus-4.7 (quality > cost).
# Fallback chain on 404/"No endpoints found" (probed and verified 2026-05-06):
#   primary: claude-opus-4.7  (claude-opus-latest is NOT a valid ID on OpenRouter,
#                              substituted with claude-opus-4.1 as fallback 1)
GENERATOR_MODEL = os.getenv("GENERATOR_MODEL", "anthropic/claude-opus-4.7")
GENERATOR_FALLBACKS = [
    "anthropic/claude-opus-4.1",
    "anthropic/claude-sonnet-4.5",
]
GENERATOR_TEMPERATURE = 0.8

# Switched from openai/o4-mini → anthropic/claude-sonnet-4.5 (RU IP block 403 on OpenAI).
# v2.3: dual solver — independent verification with majority vote (>= 1 of 2 agreeing).
# v2.4: triple solver — added deepseek-chat as third independent voice.
#       Majority logic in solver.py uses MAJORITY_THRESHOLD (>= 2 of 3 agreeing).
SOLVER_MODEL = os.getenv("SOLVER_MODEL", "anthropic/claude-sonnet-4.5")
SOLVER_MODELS = [
    "anthropic/claude-sonnet-4.5",
    "google/gemini-2.5-pro",
    "deepseek/deepseek-chat",
]
# Number of solvers that must agree with the generator's answer for is_correct=True.
# v2.3 used "any_match" (>=1). v2.4 raises bar to majority (>=2).
SOLVER_MAJORITY_THRESHOLD = 2
SOLVER_TEMPERATURE = 0.1

# ─── Debate (v2.5 tie-breaker) ─────────────────────────────────────────────────
# When R1 majority is NOT reached (correct_count < SOLVER_MAJORITY_THRESHOLD),
# the solver triggers a debate round (R2 with peer context) followed by an
# arbiter that first solves the problem independently (anti-anchoring), then
# compares its own answer to the generator's. The arbiter's verdict is final.
ARBITER_MODEL = os.getenv("ARBITER_MODEL", "anthropic/claude-opus-4.7")
ARBITER_FALLBACK = "anthropic/claude-opus-4.1"
ARBITER_TEMPERATURE = 0.0
DEBATE_ENABLED = os.getenv("DEBATE_ENABLED", "1") not in ("0", "false", "False", "")
DEBATE_R2_TEMPERATURE = 0.1
DEBATE_MAX_TOKENS = 12000

CRITIC_MODEL = os.getenv("CRITIC_MODEL", "anthropic/claude-sonnet-4.5")
CRITIC_TEMPERATURE = 0.2

POLISHER_MODEL = os.getenv("POLISHER_MODEL", "deepseek/deepseek-chat")
POLISHER_TEMPERATURE = 0.2

META_REVIEWER_MODEL = os.getenv("META_REVIEWER_MODEL", "anthropic/claude-sonnet-4.5")
META_REVIEWER_TEMPERATURE = 0.2

EMBEDDER_MODEL = os.getenv("EMBEDDER_MODEL", "openai/text-embedding-3-large")

# ─── MVP Scope ─────────────────────────────────────────────────────────────────

AVAILABLE_OLYMPIADS = ["vsosh"]

# Pre-generated nightly (cron): combos with 100+ archived problems
# 6 combos x 30 days = 180 variants/month
TIER_PREGEN = [
    (9, "regional"),
    (9, "final"),
    (10, "regional"),
    (10, "final"),
    (11, "regional"),
    (11, "final"),
]

# Generated on-demand via /api/olympiad/daily (55-65 archived problems each)
TIER_LAZY = [
    (9, "municipal"),
    (10, "municipal"),
    (11, "municipal"),
]

# Not enough data for generation (20 problems each) - show "coming soon"
TIER_DISABLED = [
    (9, "school"),
    (10, "school"),
    (11, "school"),
]

# Grades 5-8: exist in olympiads.py (253 problems) but have olympiad_slug=None
# Need manual tagging before enabling. Show "coming soon" in UI.
GRADES_DISABLED = [5, 6, 7, 8]

# ─── Budget Controls ───────────────────────────────────────────────────────────

MONTHLY_BUDGET_TARGET = float(os.getenv("POOL_BUDGET_TARGET", "200"))
MONTHLY_BUDGET_ALERT = float(os.getenv("POOL_BUDGET_ALERT", "400"))
MONTHLY_BUDGET_HARD_STOP = float(os.getenv("POOL_BUDGET_HARD_STOP", "500"))

# ─── Pipeline Settings ─────────────────────────────────────────────────────────

MAX_GENERATE_RETRIES = 3
# v2.5 hotfix B1: hard cap on TOTAL attempts per position (generator + critic
# loop). Previously test_single_variant.py used range(10) and tasks/daily_pool
# used MAX_GENERATE_RETRIES=3 inconsistently. This single knob is now used by
# BOTH paths.  After exhausting the cap on the primary topic, the pipeline
# logs a structured ABANDONED record and either (in tasks/daily_pool) inserts
# a sentinel "[no_problem]" row, or (in test_single_variant) marks accepted=False.
MAX_ATTEMPTS_PER_POSITION = int(os.getenv("MAX_ATTEMPTS_PER_POSITION", "4"))
MAX_META_RETRIES = 2
SIMILARITY_THRESHOLD = 0.85
LOOKBACK_DAYS = 365
ANALYSIS_CACHE_DAYS = 30

# Default stack (kept for future A/B experiments, always 'A' for now)
DEFAULT_STACK = "A"
