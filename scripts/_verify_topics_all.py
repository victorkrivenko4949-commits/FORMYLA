# -*- coding: utf-8 -*-
"""Smoke-test для всех классов 7-11 (через реестр) и 5-6 (через GradeTask)."""
import sys
sys.path.insert(0, '.')

from app import app
from models import AdaptiveTask
from services.adaptive_topics_registry import ADAPTIVE_TOPICS_BY_GRADE


def main():
    with app.app_context():
        print("\n=== Темы 7-11 классов через реестр ===")
        all_ok = True
        for g in (7, 8, 9, 10, 11):
            rows = AdaptiveTask.query.filter_by(class_level=g, is_flagged=False).all()
            by = {}
            for t in rows:
                if t.topic:
                    by[t.topic.strip()] = by.get(t.topic.strip(), 0) + 1
            print(f"\n--- Grade {g} ({len(rows)} задач, {len(by)} тем в БД) ---")
            grade_ok = True
            for e in ADAPTIVE_TOPICS_BY_GRADE.get(g, []):
                c = by.get(e['db_topic'], 0)
                mark = '✅' if c >= 10 else '❌'
                if c < 10:
                    grade_ok = False
                    all_ok = False
                print(f"  {mark} {e['emoji']} {e['name'][:55]:55s} → {c}")
            print(f"  Итог по классу {g}: {'OK' if grade_ok else 'FAIL'}")

        print("\n=== Темы 5-6 классов через GradeTask ===")
        from models_grade import GRADE_DOMAINS, DOMAIN_LABELS, GradeTask
        for g in (5, 6):
            print(f"\n--- Grade {g} ---")
            for d in GRADE_DOMAINS.get(g, ()):
                c = GradeTask.query.filter_by(grade=g, domain=d).count()
                mark = '✅' if c >= 10 else '❌'
                print(f"  {mark} {DOMAIN_LABELS.get(d, d):55s} → {c}")

        print("\n" + ("✅ ВСЕ КЛАССЫ 7-11 OK" if all_ok else "❌ ЕСТЬ ПРОБЛЕМЫ"))
        return 0 if all_ok else 1


if __name__ == '__main__':
    sys.exit(main())
else:
    main()
