# -*- coding: utf-8 -*-
"""
Celery tasks for Daily Olympiad Pool generation pipeline.

Main task: generate_variant_task
  - Analyzes combo (cached 30 days)
  - Generates 5 problems sequentially
  - Each problem: generate -> solve -> critic -> embed -> polish
  - Meta review of complete variant
  - Saves to DB with status
"""
import json
import logging
import os
import traceback
from datetime import date, datetime, timezone

from celery import Celery, states

logger = logging.getLogger(__name__)

# Import pipeline config
from config.models import (
    AVAILABLE_OLYMPIADS, TIER_PREGEN, TIER_LAZY,
    MAX_GENERATE_RETRIES, MAX_ATTEMPTS_PER_POSITION, MAX_META_RETRIES,
    MONTHLY_BUDGET_HARD_STOP, DEFAULT_STACK,
)

# Celery app configuration
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
celery_app = Celery("daily_pool", broker=REDIS_URL, backend=REDIS_URL)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_time_limit=600,
    task_soft_time_limit=540,
    worker_prefetch_multiplier=1,
    worker_concurrency=2,
)


def _check_budget():
    """Check if monthly budget allows new generation. Returns (ok, spent)."""
    from app import app
    with app.app_context():
        from models import db
        row = db.session.execute(
            db.text("""
                SELECT COALESCE(SUM(cost_usd), 0) FROM generation_costs
                WHERE created_at >= date('now', 'start of month')
            """)
        ).fetchone()
        spent = float(row[0]) if row else 0.0
        return spent < MONTHLY_BUDGET_HARD_STOP, spent


@celery_app.task(bind=True, name="daily_pool.generate_variant")
def generate_variant_task(self, olympiad_slug: str, grade: int,
                          round_name: str, variant_date: str,
                          stack: str = "A"):
    """
    Generate a complete 5-problem variant for a given combination.

    Args:
        olympiad_slug: must be in AVAILABLE_OLYMPIADS (MVP: vsosh only)
        grade: e.g. 9
        round_name: e.g. "regional"
        variant_date: ISO date string e.g. "2025-06-01"
        stack: always "A" for now (kept for future experiments)

    Returns: dict with variant_id, status, problems, costs
    """
    # Validate olympiad is in scope
    if olympiad_slug not in AVAILABLE_OLYMPIADS:
        raise ValueError(f"Olympiad '{olympiad_slug}' not in AVAILABLE_OLYMPIADS")

    # Budget guard
    budget_ok, spent = _check_budget()
    if not budget_ok:
        raise RuntimeError(
            f"Monthly budget exceeded: ${spent:.2f} >= ${MONTHLY_BUDGET_HARD_STOP}"
        )

    from app import app

    with app.app_context():
        from models import db
        from services.daily_pool.analyzer import get_or_create_analysis
        from services.daily_pool.generator import generate_problem
        from services.daily_pool.solver import verify_problem
        from services.daily_pool.critic import review_problem
        from services.daily_pool.embedder import check_deduplication, save_embedding
        from services.daily_pool.polisher import polish_problem
        from services.daily_pool.meta_reviewer import review_variant

        total_cost = 0.0
        problems = []
        variant_id = None

        try:
            # Step 1: Get or create analysis
            self.update_state(state="PROGRESS", meta=dict(
                step="analyze", progress=5
            ))
            analysis = get_or_create_analysis(olympiad_slug, grade, round_name)
            logger.info(f"[Task] Analysis ready for {olympiad_slug}/{grade}/{round_name}")

            # Step 2: Create variant record
            db.session.execute(
                db.text("""
                    INSERT INTO daily_variants
                        (olympiad_slug, grade, round, variant_date, status, stack)
                    VALUES (:slug, :grade, :round, :vdate, 'generating', :stack)
                """),
                dict(slug=olympiad_slug, grade=grade, round=round_name,
                     vdate=variant_date, stack=stack)
            )
            db.session.commit()

            row = db.session.execute(
                db.text("""
                    SELECT id FROM daily_variants
                    WHERE olympiad_slug = :slug AND grade = :grade
                      AND round = :round AND variant_date = :vdate AND stack = :stack
                    ORDER BY id DESC LIMIT 1
                """),
                dict(slug=olympiad_slug, grade=grade, round=round_name,
                     vdate=variant_date, stack=stack)
            ).fetchone()
            variant_id = row[0]

            # Step 3: Generate 5 problems
            for position in range(1, 6):
                progress = 10 + position * 15
                self.update_state(state="PROGRESS", meta=dict(
                    step=f"generate_p{position}", progress=progress
                ))

                problem = _generate_single_problem(
                    analysis, position, problems, stack,
                    olympiad_slug, grade, round_name
                )
                total_cost += problem.get("_total_cost", 0)
                problems.append(problem)

                # Save problem to DB
                db.session.execute(
                    db.text("""
                        INSERT INTO daily_problems
                            (variant_id, position, statement, solution, answer,
                             topic, difficulty, method, idea_summary, status)
                        VALUES (:vid, :pos, :stmt, :sol, :ans,
                                :topic, :diff, :method, :idea, 'approved')
                    """),
                    dict(
                        vid=variant_id, pos=position,
                        stmt=problem["statement"],
                        sol=problem["solution"],
                        ans=problem["answer"],
                        topic=problem.get("topic", ""),
                        diff=problem.get("difficulty", 5),
                        method=problem.get("method", ""),
                        idea=problem.get("idea_summary", ""),
                    )
                )
                db.session.commit()

            # Step 4: Meta review
            self.update_state(state="PROGRESS", meta=dict(
                step="meta_review", progress=90
            ))
            meta_result = _meta_review_with_retries(
                problems, analysis, variant_date, variant_id, db
            )
            total_cost += meta_result.get("_cost", 0)

            # Step 5: Update variant status
            final_status = "approved" if meta_result["verdict"] == "approve" else "needs_review"
            db.session.execute(
                db.text("""
                    UPDATE daily_variants
                    SET status = :status, total_cost = :cost
                    WHERE id = :vid
                """),
                dict(status=final_status, cost=total_cost, vid=variant_id)
            )
            db.session.commit()

            logger.info(
                f"[Task] Variant {variant_id} complete: "
                f"status={final_status} cost=${total_cost:.4f}"
            )

            return dict(
                variant_id=variant_id,
                status=final_status,
                problems_count=len(problems),
                total_cost=round(total_cost, 4),
                meta_verdict=meta_result["verdict"],
            )

        except Exception as e:
            logger.error(f"[Task] Failed: {e}\n{traceback.format_exc()}")
            if variant_id:
                db.session.execute(
                    db.text("UPDATE daily_variants SET status = 'failed' WHERE id = :vid"),
                    dict(vid=variant_id)
                )
                db.session.commit()
            raise


def _generate_single_problem(analysis, position, existing, stack,
                             olympiad_slug, grade, round_name):
    """Generate, verify, critique, embed, and polish a single problem."""
    from services.daily_pool.generator import generate_problem
    from services.daily_pool.solver import verify_problem
    from services.daily_pool.critic import review_problem
    from services.daily_pool.embedder import check_deduplication, save_embedding
    from services.daily_pool.polisher import polish_problem

    total_cost = 0.0

    for attempt in range(MAX_ATTEMPTS_PER_POSITION):
        # Generate
        problem = generate_problem(analysis, position, existing)
        total_cost += problem.get("_cost", 0)

        # Verify with solver (v2.5: pass generator_solution so the debate
        # tie-breaker has full author context if R1 is below majority).
        solver_result = verify_problem(
            problem["statement"], problem["answer"], stack,
            generator_solution=problem.get("solution", ""),
        )
        total_cost += solver_result.get("_cost", 0)
        if solver_result.get("_debate_triggered"):
            _deb = solver_result.get("_debate") or {}
            logger.info(
                f"[Pipeline] pos={position} debate triggered: "
                f"R1={solver_result.get('_correct_count')}/"
                f"{solver_result.get('_total_solvers')} "
                f"verdict={_deb.get('final_verdict')} "
                f"high_risk={solver_result.get('_high_risk')} "
                f"cost=${float(_deb.get('cost') or 0):.4f}"
            )

        if not solver_result.get("answers_match"):
            logger.warning(
                f"[Pipeline] pos={position} attempt={attempt+1}: "
                f"solver disagrees, retrying"
            )
            continue

        # Critic review
        critic_result = review_problem(problem, analysis, position)
        total_cost += critic_result.get("_cost", 0)

        if critic_result["verdict"] != "approve":
            logger.warning(
                f"[Pipeline] pos={position} attempt={attempt+1}: "
                f"critic rejected (avg={critic_result['avg']}), retrying"
            )
            continue

        # Deduplication check
        dedup = check_deduplication(
            problem["statement"], olympiad_slug, grade, round_name
        )
        total_cost += 0.001  # embedding cost estimate

        if dedup["is_duplicate"]:
            logger.warning(
                f"[Pipeline] pos={position} attempt={attempt+1}: "
                f"duplicate (sim={dedup['max_similarity']:.3f}), retrying"
            )
            continue

        # Polish
        polished = polish_problem(problem)
        total_cost += polished.get("_cost", 0)

        # Use polished version
        problem["statement"] = polished.get("statement", problem["statement"])
        problem["solution"] = polished.get("solution", problem["solution"])
        problem["answer"] = polished.get("answer", problem["answer"])
        problem["_embedding"] = dedup["embedding"]
        problem["_total_cost"] = total_cost
        problem["_attempts"] = attempt + 1

        return problem

    # All retries exhausted - log structured ABANDONED record and force-use
    # the last attempt (kept as best-effort filler so meta-review still has 5
    # positions). Downstream meta-reviewer sees `_forced=True` and can flag.
    logger.error(
        f"[Generator] Position {position} ABANDONED after "
        f"{MAX_ATTEMPTS_PER_POSITION} attempts "
        f"(olympiad={olympiad_slug} grade={grade} round={round_name}); "
        f"using last attempt as filler with _forced=True"
    )
    problem["_total_cost"] = total_cost
    problem["_attempts"] = MAX_ATTEMPTS_PER_POSITION
    problem["_forced"] = True
    problem["_abandoned"] = True
    return problem


def _meta_review_with_retries(problems, analysis, variant_date, variant_id, db):
    """Run meta review with retry logic for rejected positions."""
    from services.daily_pool.meta_reviewer import review_variant

    for meta_attempt in range(MAX_META_RETRIES):
        result = review_variant(problems, analysis, variant_date)

        if result["verdict"] == "approve":
            return result

        # If rejected, log but don't regenerate in pilot mode
        logger.warning(
            f"[MetaReview] Attempt {meta_attempt+1}: rejected, "
            f"positions={result.get('reject_positions', [])}"
        )

    # After all retries, return last result
    return result
