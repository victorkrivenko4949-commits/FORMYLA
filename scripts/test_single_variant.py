#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test runner: generate 1 variant synchronously (no Celery/Redis needed).

Usage:
    set OPENROUTER_API_KEY=sk-or-...
    python scripts/test_single_variant.py

Generates: vsosh / grade 9 / regional / 2026-05-05
"""
import json
import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
logger = logging.getLogger("test_variant")

# Check API key
if not os.environ.get("OPENROUTER_API_KEY") or "your_api" in os.environ.get("OPENROUTER_API_KEY", ""):
    print("ERROR: Set OPENROUTER_API_KEY environment variable first!")
    print("  set OPENROUTER_API_KEY=sk-or-v1-...")
    sys.exit(1)

from app import app

OLYMPIAD = "vsosh"
GRADE = 9
ROUND = "regional"
VARIANT_DATE = "2026-05-06"
STACK = "A"


def main():
    start_time = time.time()
    timings = dict()

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
        quality_reports = []

        # Step 1: Analyzer
        t0 = time.time()
        logger.info("Step 1: Analyzing combo...")
        analysis = get_or_create_analysis(OLYMPIAD, GRADE, ROUND)
        timings["analyzer"] = round(time.time() - t0, 1)
        logger.info(f"  Analysis ready ({timings['analyzer']}s)")

        # Step 2: Create variant record
        db.session.execute(
            db.text("""
                INSERT INTO daily_variants
                    (olympiad_slug, grade, round, variant_date, status, generation_stack)
                VALUES (:slug, :grade, :round, :vdate, 'generating', :stack)
            """),
            dict(slug=OLYMPIAD, grade=GRADE, round=ROUND,
                 vdate=VARIANT_DATE, stack=STACK)
        )
        db.session.commit()
        row = db.session.execute(
            db.text("SELECT id FROM daily_variants ORDER BY id DESC LIMIT 1")
        ).fetchone()
        variant_id = row[0]
        logger.info(f"  Variant ID: {variant_id}")

        # v2.4: persistent log of every critic+solver attempt
        # (separate table to avoid touching daily_problems schema)
        db.session.execute(db.text("""
            CREATE TABLE IF NOT EXISTS critic_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                variant_id INTEGER NOT NULL,
                position INTEGER NOT NULL,
                attempt_num INTEGER NOT NULL,
                solver_match INTEGER,
                solver_correct_count INTEGER,
                solver_total INTEGER,
                solver_per_model TEXT,
                critic_avg REAL,
                critic_min REAL,
                critic_verdict TEXT,
                critic_scores TEXT,
                critic_full_json TEXT,
                problem_text TEXT,
                problem_answer TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """))
        db.session.commit()

        # Step 3: Generate 5 problems
        for pos in range(1, 6):
            logger.info(f"\n============================================================")
            logger.info(f"Problem {pos}/5")
            logger.info(f"============================================================")

            report = dict(position=pos, retries=0)
            t_gen = time.time()
            accepted = False
            problem = None

            # v2.3: bumped from 5 -> 10 because validator now triggers
            # programmatic retries on dup-topic / year-spam / latex-dirty / proof.
            for attempt in range(10):
                report["retries"] = attempt

                # Generate
                t0 = time.time()
                try:
                    problem = generate_problem(analysis, pos, problems, variant_date=VARIANT_DATE)
                except (ValueError, Exception) as e:
                    logger.warning(f"  Generator REJECTED (attempt {attempt+1}): {e}")
                    problem = None
                    continue
                if problem is None:
                    logger.warning(f"  Generator returned None (attempt {attempt+1})")
                    continue
                gen_time = round(time.time() - t0, 1)
                gen_cost = problem.get("_cost", 0)
                total_cost += gen_cost
                logger.info(f"  Generated ({gen_time}s, ${gen_cost:.4f})")

                # Solve
                t0 = time.time()
                solver_result = verify_problem(problem["statement"], problem["answer"], STACK)
                solve_time = round(time.time() - t0, 1)
                solve_cost = solver_result.get("_cost", 0)
                total_cost += solve_cost
                report["solver_match"] = solver_result.get("is_correct", False)
                report["solver_confidence"] = solver_result.get("confidence", "?")
                report["cross_verify_status"] = solver_result.get("cross_verify_status")
                logger.info(f"  Solved ({solve_time}s, ${solve_cost:.4f}) match={report['solver_match']} cv={report['cross_verify_status']}")

                if not solver_result.get("is_correct"):
                    logger.warning("  Solver disagrees, retrying...")
                    continue

                # Critic
                t0 = time.time()
                critic_result = review_problem(problem, analysis, pos)
                critic_time = round(time.time() - t0, 1)
                critic_cost = critic_result.get("_cost", 0)
                total_cost += critic_cost
                report["critic_scores"] = critic_result.get("scores", dict())
                report["critic_avg"] = critic_result.get("avg", 0)
                report["critic_min"] = critic_result.get("min", 0)
                report["critic_latex_ok"] = critic_result.get("latex_ok", False)
                report["critic_verdict"] = critic_result.get("verdict", "?")
                logger.info(f"  Critic ({critic_time}s, ${critic_cost:.4f}) avg={report['critic_avg']} verdict={report['critic_verdict']}")

                # v2.4: persist EVERY critic attempt to critic_attempts table
                try:
                    db.session.execute(db.text("""
                        INSERT INTO critic_attempts
                            (variant_id, position, attempt_num,
                             solver_match, solver_correct_count, solver_total,
                             solver_per_model,
                             critic_avg, critic_min, critic_verdict,
                             critic_scores, critic_full_json,
                             problem_text, problem_answer)
                        VALUES (:vid, :pos, :att,
                                :sm, :scc, :st, :spm,
                                :cavg, :cmin, :cv,
                                :cs, :cfj,
                                :pt, :pa)
                    """), dict(
                        vid=variant_id, pos=pos, att=attempt + 1,
                        sm=1 if solver_result.get("is_correct") else 0,
                        scc=solver_result.get("_correct_count"),
                        st=solver_result.get("_total_solvers"),
                        spm=json.dumps(solver_result.get("_solvers", []), ensure_ascii=False),
                        cavg=critic_result.get("avg", 0),
                        cmin=critic_result.get("min", 0),
                        cv=critic_result.get("verdict", "?"),
                        cs=json.dumps(critic_result.get("scores", {}), ensure_ascii=False),
                        cfj=json.dumps({k: v for k, v in critic_result.items()
                                        if k not in ("_usage",)}, ensure_ascii=False, default=str),
                        pt=problem.get("statement", "")[:5000],
                        pa=problem.get("answer", "")[:500],
                    ))
                    db.session.commit()
                except Exception as e:
                    logger.warning(f"  [persist] critic_attempts insert failed: {e}")
                    db.session.rollback()

                if critic_result["verdict"] != "approve":
                    logger.warning("  Critic rejected, retrying...")
                    continue

                # Embedder
                t0 = time.time()
                dedup = check_deduplication(problem["statement"], OLYMPIAD, GRADE, ROUND)
                embed_time = round(time.time() - t0, 1)
                total_cost += 0.001
                report["max_similarity"] = dedup["max_similarity"]
                report["is_duplicate"] = dedup["is_duplicate"]
                logger.info(f"  Embed ({embed_time}s) sim={dedup['max_similarity']:.3f}")

                if dedup["is_duplicate"]:
                    logger.warning("  Duplicate detected, retrying...")
                    continue

                # Polisher
                t0 = time.time()
                polished = polish_problem(problem)
                polish_time = round(time.time() - t0, 1)
                polish_cost = polished.get("_cost", 0)
                total_cost += polish_cost
                report["polisher_changes"] = polished.get("changes_made", [])
                logger.info(f"  Polished ({polish_time}s, ${polish_cost:.4f}) changes={len(report['polisher_changes'])}")

                # Use polished version
                problem["statement"] = polished.get("statement", problem["statement"])
                problem["solution"] = polished.get("solution", problem["solution"])
                problem["answer"] = polished.get("answer", problem["answer"])
                accepted = True
                break

            timings[f"problem_{pos}"] = round(time.time() - t_gen, 1)
            report["accepted"] = accepted
            quality_reports.append(report)

            # NEW (v2.1): if all 5 attempts rejected — keep last problem in DB but mark as 'failed'
            if not accepted:
                logger.error(f"  ❌ Problem {pos}: all 5 attempts rejected, marking as 'failed'")
            # v2.3 fix: ensure problem is a dict for both append and INSERT
            if problem is None:
                problem = {"statement": "[no_problem]", "solution": "", "answer": "", "topic": "", "difficulty": 0}
            problems.append(problem)

            # Save to DB
            problem_status = 'approved' if accepted else 'failed'
            db.session.execute(
                db.text("""
                    INSERT INTO daily_problems
                        (variant_id, position, text, solution, answer,
                         topic, difficulty, status)
                    VALUES (:vid, :pos, :stmt, :sol, :ans,
                            :topic, :diff, :status)
                """),
                dict(
                    vid=variant_id, pos=pos,
                    stmt=problem.get("statement", "[no_problem]"),
                    sol=problem.get("solution", ""),
                    ans=problem.get("answer", ""),
                    topic=problem.get("topic", ""),
                    diff=problem.get("difficulty", 5),
                    status=problem_status,
                )
            )
            db.session.commit()

        # Step 4: Meta review
        logger.info(f"\n============================================================")
        logger.info("META REVIEW")
        t0 = time.time()
        meta_result = review_variant(problems, analysis, VARIANT_DATE)
        timings["meta_review"] = round(time.time() - t0, 1)
        meta_cost = meta_result.get("_cost", 0)
        total_cost += meta_cost
        logger.info(f"  Meta ({timings['meta_review']}s, ${meta_cost:.4f}) verdict={meta_result['verdict']}")

        # Update variant status
        final_status = "approved" if meta_result["verdict"] == "approve" else "needs_review"
        db.session.execute(
            db.text("UPDATE daily_variants SET status = :s, total_cost_usd = :c WHERE id = :v"),
            dict(s=final_status, c=total_cost, v=variant_id)
        )
        db.session.commit()

        total_time = round(time.time() - start_time, 1)
        timings["total"] = total_time

        # ═══════════════════════════════════════════════════════════════
        # FINAL REPORT
        # ═══════════════════════════════════════════════════════════════
        print("\n" + "=" * 70)
        print("TEST VARIANT REPORT")
        print("=" * 70)

        print(f"\nVariant ID: {variant_id}")
        print(f"Status: {final_status}")
        print(f"Total cost: ${total_cost:.4f}")
        print(f"Total time: {total_time}s")

        print("\n--- 5 PROBLEMS ---")
        for i, (p, r) in enumerate(zip(problems, quality_reports), 1):
            print(f"\n[{i}] {p.get('statement','')[:150]}...")
            print(f"    Answer: {p.get('answer','')}")
            print(f"    Topic: {p.get('topic','')} | Difficulty: {p.get('difficulty','?')}/10")
            print(f"    Critic: avg={r.get('critic_avg',0)} min={r.get('critic_min',0)} latex={r.get('critic_latex_ok')}")
            print(f"    Solver match: {r.get('solver_match')} confidence={r.get('solver_confidence')} cross_verify={r.get('cross_verify_status')}")
            print(f"    Similarity: {r.get('max_similarity',0):.3f}")
            print(f"    Polish changes: {r.get('polisher_changes',[])}")
            print(f"    Retries: {r.get('retries',0)}")

        print("\n--- META REVIEW ---")
        print(f"  Verdict: {meta_result.get('verdict')}")
        print(f"  Theme diversity: {meta_result.get('theme_diversity')}")
        print(f"  Difficulty progression: {meta_result.get('difficulty_progression')}")
        print(f"  Reject positions: {meta_result.get('reject_positions', [])}")
        print(f"  Issues: {meta_result.get('issues', [])}")

        print("\n--- TIMINGS ---")
        for k, v in timings.items():
            print(f"  {k}: {v}s")

        print("\n--- COSTS BY MODEL ---")
        cost_rows = db.session.execute(
            db.text("""
                SELECT model, SUM(cost_usd), SUM(input_tokens), SUM(output_tokens)
                FROM generation_costs
                WHERE variant_id = :vid
                GROUP BY model
            """),
            dict(vid=variant_id)
        ).fetchall()
        for row in cost_rows:
            print(f"  {row[0]}: ${row[1]:.4f} (in={row[2]} out={row[3]})")

        print("\n" + "=" * 70)
        print("ACCEPTANCE CRITERIA:")
        ok = True
        if total_cost > 0.60:
            print("  FAIL: cost > $0.60")
            ok = False
        else:
            print(f"  PASS: cost ${total_cost:.4f} < $0.60")

        all_avg_ok = all(r.get("critic_avg", 0) >= 8.5 for r in quality_reports)
        all_min_ok = all(r.get("critic_min", 0) >= 7 for r in quality_reports)
        all_latex = all(r.get("critic_latex_ok", False) for r in quality_reports)
        all_solver = all(r.get("solver_match", False) for r in quality_reports)
        all_dedup = all(r.get("max_similarity", 1) < 0.85 for r in quality_reports)
        topics = [p.get("topic", "") for p in problems]
        unique_topics = len(set(topics)) == 5
        meta_approved = meta_result.get("verdict") == "approve"

        checks = [
            ("avg critic >= 8.5", all_avg_ok),
            ("min critic >= 7", all_min_ok),
            ("all latex_ok", all_latex),
            ("meta approved", meta_approved),
            ("5 unique topics", unique_topics),
            ("all solver match", all_solver),
            ("all sim < 0.85", all_dedup),
        ]
        for name, passed in checks:
            status = "PASS" if passed else "FAIL"
            print(f"  {status}: {name}")
            if not passed:
                ok = False

        overall = 'ALL PASSED' if ok else 'FAILED'
        print(f"\nOVERALL: {overall}")
        print("=" * 70)


if __name__ == "__main__":
    main()
