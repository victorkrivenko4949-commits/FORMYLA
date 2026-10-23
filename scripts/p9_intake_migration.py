#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/p9_intake_migration.py — Idempotent migration P9 Intake.

Sets default values in CuratorState.prep_state.intake for existing students
so nothing breaks.

Default values:
  - class_level: from User.preferred_grade or CuratorState.grade
  - goal: "just_grow"
  - goal_auto: True
  - experience: "none"
  - daily_tasks: 10
  - weak_sections: []
  - weak_priority: False
  - prior_mu: from existing onboarding or 2.0
  - prior_sigma: from existing or 1.5

V11: Uses schema_migration_log for idempotent re-runs.
Run: python scripts/p9_intake_migration.py
"""

import os
import sys
import logging
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

MIGRATION_NAME = 'p9_intake_migration.py'


def run():
    """Execute migration."""
    from app import app
    from models import db, User
    from models_curator import CuratorState

    with app.app_context():
        # V11: Check migration log first
        from services.migration_log import is_migration_applied, register_migration
        if is_migration_applied(MIGRATION_NAME):
            logger.info("%s already recorded, skipping", MIGRATION_NAME)
            return

        # Get all students with CuratorState
        all_cs = CuratorState.query.all()
        updated = 0
        skipped = 0

        for cs in all_cs:
            prep_state = dict(cs.prep_state) if isinstance(cs.prep_state, dict) else {}

            # Already has intake -> skip
            if prep_state.get('intake', {}).get('completed'):
                skipped += 1
                continue

            # Get grade
            grade = cs.grade
            if not grade:
                user = db.session.get(User, cs.user_id)
                if user:
                    try:
                        grade = int(user.preferred_grade) if user.preferred_grade else None
                    except (TypeError, ValueError):
                        grade = None

            if not grade or grade < 5 or grade > 11:
                grade = 9

            # Get prior from existing onboarding if present
            prior_mu = 2.0
            prior_sigma = 1.5
            ol = prep_state.get('onboarding', {}) or {}
            if ol.get('prior_mu'):
                prior_mu = float(ol['prior_mu'])
            if ol.get('prior_sigma'):
                prior_sigma = float(ol['prior_sigma'])

            # Build default intake
            prep_state['intake'] = {
                'completed': True,
                'completed_at': datetime.utcnow().isoformat(),
                'class_level': int(grade),
                'goal': 'just_grow',
                'goal_auto': True,
                'experience': 'none',
                'daily_tasks': 10,
                'weak_sections': [],
                'weak_priority': False,
                'prior_mu': round(prior_mu, 2),
                'prior_sigma': round(prior_sigma, 2),
                'answers': {
                    'class': str(grade),
                    'goal': 'dont_know',
                    'experience': 'none',
                    'time': 'm30',
                    'weak_sections': 'dont_know',
                },
                'anchor_results': [],
            }

            cs.prep_state = prep_state
            cs.onboarding_done = True
            updated += 1

        db.session.commit()
        register_migration(MIGRATION_NAME)
        logger.info("Migration done: %d updated, %d skipped (already have intake)", updated, skipped)

        # Statistics
        total = CuratorState.query.count()
        with_intake = sum(
            1 for cs in all_cs
            if isinstance(cs.prep_state, dict) and cs.prep_state.get('intake', {}).get('completed')
        )
        logger.info("Total CuratorState rows: %d, with intake: %d", total, with_intake)
        print(f"\nRows affected: {updated}")
        print(f"Rows skipped (already migrated): {skipped}")
        print(f"Total with intake: {with_intake} / {total}")


if __name__ == "__main__":
    run()
