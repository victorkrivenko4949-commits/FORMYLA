"""Site smoke-test after polished-8394 import.

Uses the Flask app's test_client to exercise the adaptive-test routes
without starting a real HTTP server.
"""
from __future__ import annotations
import os
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def main():
    print("=" * 70)
    print("SITE SMOKE TEST (Flask test_client)")
    print("=" * 70)

    print("\n[setup] importing app ...")
    try:
        from app import app
    except Exception as e:
        print("[FAIL] cannot import app: " + str(e))
        traceback.print_exc()
        sys.exit(2)

    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    client = app.test_client()

    results = []

    def check(name, response, expected_status=200):
        ok = response.status_code == expected_status
        results.append(dict(
            name=name,
            status=response.status_code,
            expected=expected_status,
            ok=ok,
            size=len(response.data) if response.data else 0,
        ))
        print(("  [OK] " if ok else "  [FAIL] ")
              + name + " -> " + str(response.status_code)
              + " (expected " + str(expected_status) + "), "
              + str(len(response.data) if response.data else 0)
              + " bytes")

    # ----- 1) select_class page -----
    print("\n[1] /adaptive_test/select_class ...")
    r = client.get("/adaptive_test/select_class")
    check("select_class", r)

    # ----- 2) select_topic for several grades -----
    print("\n[2] /adaptive_test/select_topic?grade=N ...")
    for g in (5, 6, 7, 8, 9, 10, 11):
        r = client.get("/adaptive_test/select_topic?grade=" + str(g))
        check("select_topic g=" + str(g), r)

    # ----- 3) DB-driven sanity: query AdaptiveTask via the running app -----
    print("\n[3] AdaptiveTask query through ORM ...")
    with app.app_context():
        from models import AdaptiveTask, db
        # 2026-05 cleanup: 8394 -> 8389 (5 broken tasks removed).
        EXPECTED_TOTAL = 8389
        total = AdaptiveTask.query.count()
        print("    AdaptiveTask.query.count(): " + str(total))
        assert total == EXPECTED_TOTAL, (
            "ORM count != " + str(EXPECTED_TOTAL) + " (got " + str(total) + ")"
        )
        results.append(dict(name="ORM_count_expected", ok=True))

        # Filter by subject - must return only that subject
        for sj in ("algebra", "geometry", "combinatorics",
                   "number_theory", "logic"):
            rows = AdaptiveTask.query.filter_by(subject=sj).limit(5).all()
            distinct_subjects = set(r.subject for r in rows)
            ok = distinct_subjects == set([sj]) or not rows
            print("    subject=" + sj + " -> distinct: "
                  + str(distinct_subjects) + (" OK" if ok else " FAIL"))
            results.append(dict(
                name="filter_subject_" + sj,
                ok=ok,
                detail=str(distinct_subjects),
            ))

        # Filter by grade+level - must return only that combination
        rows = AdaptiveTask.query.filter_by(
            class_level=9, difficulty_level=5
        ).limit(10).all()
        for r in rows:
            assert r.class_level == 9 and r.difficulty_level == 5
        print("    grade=9 level=5: " + str(len(rows))
              + " rows, all class_level=9 difficulty_level=5")
        results.append(dict(
            name="filter_grade9_level5",
            ok=True,
            detail=str(len(rows)) + " rows",
        ))

        # ----- 4) Test that services.task_selection.select_tasks works -----
        from services.task_selection import select_tasks, count_tasks
        # algebra, grade 9, level 5
        tasks = select_tasks(subject="algebra", grade=9, level=5)
        all_algebra = all(t.subject == "algebra" for t in tasks)
        all_g9 = all(t.class_level == 9 for t in tasks)
        all_l5 = all(t.difficulty_level == 5 for t in tasks)
        print("    select_tasks(algebra, g9, l5): " + str(len(tasks))
              + " rows, all algebra=" + str(all_algebra)
              + ", all g9=" + str(all_g9) + ", all l5=" + str(all_l5))
        results.append(dict(
            name="select_tasks_algebra_g9_l5",
            ok=(all_algebra and all_g9 and all_l5 and len(tasks) > 0),
            detail=str(len(tasks)) + " rows",
        ))

        # geometry, grade 10, level 3
        tasks = select_tasks(subject="geometry", grade=10, level=3)
        all_geo = all(t.subject == "geometry" for t in tasks)
        all_g10 = all(t.class_level == 10 for t in tasks)
        print("    select_tasks(geometry, g10, l3): " + str(len(tasks))
              + " rows, all geometry=" + str(all_geo)
              + ", all g10=" + str(all_g10))
        results.append(dict(
            name="select_tasks_geometry_g10_l3",
            ok=(all_geo and all_g10 and len(tasks) > 0),
            detail=str(len(tasks)) + " rows",
        ))

        # ----- 5) Cross-subject negative: algebra filter must NOT
        #          return any geometry. -----
        leaks = [
            t for t in
            AdaptiveTask.query.filter_by(subject="algebra").limit(500).all()
            if t.subject != "algebra"
        ]
        print("    cross-subject leak (algebra filter): "
              + str(len(leaks)) + " (expected 0)")
        results.append(dict(
            name="no_algebra_geo_leak",
            ok=(len(leaks) == 0),
        ))

        # ----- 6) Load one F-polished task and verify new solution -----
        # algebra_g9_l3_t15 was in too_short bucket -> expanded.
        t = AdaptiveTask.query.filter_by(
            source_id="algebra_g9_l3_t15"
        ).first()
        if t:
            sol_len = len(t.solution or "")
            print("    F-polished sample (algebra_g9_l3_t15) sol_len="
                  + str(sol_len))
            results.append(dict(
                name="F_polished_solution_loaded",
                ok=(sol_len > 200),
                detail="sol_len=" + str(sol_len),
            ))
        else:
            results.append(dict(
                name="F_polished_solution_loaded",
                ok=False,
                detail="source_id not found",
            ))

        # ----- 7) Load an F-replace task and verify new statement -----
        t = AdaptiveTask.query.filter_by(
            source_id="logic_g10_l5_t16"
        ).first()
        if t:
            stmt_len = len(t.task_text or "")
            print("    F-replace sample (logic_g10_l5_t16) stmt_len="
                  + str(stmt_len))
            results.append(dict(
                name="F_replace_statement_loaded",
                ok=(stmt_len > 100),
                detail="stmt_len=" + str(stmt_len),
            ))
        else:
            results.append(dict(
                name="F_replace_statement_loaded",
                ok=False,
                detail="source_id not found",
            ))

    # ----- summary -----
    print("\n" + "=" * 70)
    n_ok = sum(1 for r in results if r.get("ok"))
    n_total = len(results)
    print("SUMMARY: " + str(n_ok) + "/" + str(n_total) + " checks passed")
    failed = [r for r in results if not r.get("ok")]
    if failed:
        print("FAILURES:")
        for r in failed:
            print("  - " + r["name"] + ": "
                  + str(r.get("detail", "")) + " status="
                  + str(r.get("status", "")))
        sys.exit(1)
    print("ALL SMOKE CHECKS PASSED")
    print("=" * 70)


if __name__ == "__main__":
    main()
