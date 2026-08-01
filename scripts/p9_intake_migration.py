#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/p9_intake_migration.py — Идемпотентная миграция P9 Intake.

Существующим ученикам проставляет значения по умолчанию в CuratorState.prep_state.intake
так, чтобы ничего не сломалось.

Значения по умолчанию:
  - class_level: из User.preferred_grade или CuratorState.grade
  - goal: "just_grow" (регулярно решать и расти)
  - goal_auto: True (назначено миграцией)
  - experience: "none" (не участвовал)
  - daily_tasks: 10 (норма по умолчанию)
  - weak_sections: [] (приоритет не применяется)
  - weak_priority: False
  - prior_mu: берётся из существующего onboarding или ставится 2.0
  - prior_sigma: берётся из существующего или ставится 1.5

Запуск:
    python scripts/p9_intake_migration.py
"""

import os
import sys
import logging
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def run():
    """Выполнить миграцию."""
    from app import app
    from models import db, User
    from models_curator import CuratorState

    with app.app_context():
        # Получаем всех учеников с CuratorState
        all_cs = CuratorState.query.all()
        updated = 0
        skipped = 0

        for cs in all_cs:
            prep_state = dict(cs.prep_state) if isinstance(cs.prep_state, dict) else {}

            # Уже есть intake → пропускаем
            if prep_state.get('intake', {}).get('completed'):
                skipped += 1
                continue

            # Берём grade
            grade = cs.grade
            if not grade:
                user = db.session.get(User, cs.user_id)
                if user:
                    try:
                        grade = int(user.preferred_grade) if user.preferred_grade else None
                    except (TypeError, ValueError):
                        grade = None

            if not grade or grade < 5 or grade > 11:
                # Нет класса — ставим 9 как безопасный default
                grade = 9

            # Берём prior из существующего onboarding если есть
            prior_mu = 2.0
            prior_sigma = 1.5
            ol = prep_state.get('onboarding', {}) or {}
            if ol.get('prior_mu'):
                prior_mu = float(ol['prior_mu'])
            if ol.get('prior_sigma'):
                prior_sigma = float(ol['prior_sigma'])

            # Собираем intake по умолчанию
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
        logger.info(f"Migration done: {updated} updated, {skipped} skipped (already have intake)")

        # Статистика
        total = CuratorState.query.count()
        with_intake = sum(
            1 for cs in all_cs
            if isinstance(cs.prep_state, dict) and cs.prep_state.get('intake', {}).get('completed')
        )
        logger.info(f"Total CuratorState rows: {total}, with intake: {with_intake}")
        print(f"\nRows affected: {updated}")
        print(f"Rows skipped (already migrated): {skipped}")
        print(f"Total with intake: {with_intake} / {total}")


if __name__ == "__main__":
    run()
