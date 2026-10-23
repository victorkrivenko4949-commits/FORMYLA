#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
scripts/migrate_8to5_scale.py - Idempotent migration: 8-level -> 5-level scale.

Works with SQLAlchemy — compatible with both SQLite and PostgreSQL.
No direct sqlite3 calls, no PRAGMA.

What it does:
  1. Adds difficulty_level_src column (INTEGER) if not exists.
  2. Saves current difficulty_level -> difficulty_level_src for ALL tasks where NULL.
  3. Remaps difficulty_level FROM difficulty_level_src (not from difficulty_level!):
      1->1, 2->1, 3->2, 4->3, 5->3, 6->4, 7->4, 8->5
  4. Re-running is safe: difficulty_level_src never changes, so remap is
     always computed from the same original values.

Rollback:
  UPDATE adaptive_tasks SET difficulty_level = difficulty_level_src
  WHERE difficulty_level_src IS NOT NULL;
"""

import os
import sys
from datetime import datetime

MAPPING = {1: 1, 2: 1, 3: 2, 4: 3, 5: 3, 6: 4, 7: 4, 8: 5}


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    parent = os.path.dirname(script_dir)
    sys.path.insert(0, parent)
    os.chdir(parent)

    from dotenv import load_dotenv
    load_dotenv()

    from app import app as flask_app
    from models import db as _db
    from sqlalchemy import text, inspect

    with flask_app.app_context():
        engine = _db.engine
        inspector = inspect(engine)
        conn = engine.connect()

        try:
            trans = conn.begin()

            print('=' * 60)
            print('MIGRATION: 8-level -> 5-level scale')
            print(f'DB: {engine.url}')
            print(f'Time: {datetime.now().isoformat()}')
            print('=' * 60)

            # Step 1: add column using inspector (no PRAGMA)
            print('\n[1/4] Checking difficulty_level_src column...')
            cols = {c['name'] for c in inspector.get_columns('adaptive_tasks')}
            if 'difficulty_level_src' not in cols:
                print('  Adding difficulty_level_src column...')
                conn.execute(
                    text('ALTER TABLE adaptive_tasks ADD COLUMN IF NOT EXISTS difficulty_level_src INTEGER')
                )
                # SQLite doesn't support IF NOT EXISTS in ALTER TABLE, catch and ignore
                trans.commit()
                trans = conn.begin()
                print('  OK - column added.')
            else:
                print('  OK - column already exists (idempotent).')

            # Step 2: save original values (only where NULL)
            print('\n[2/4] Saving original difficulty_level -> difficulty_level_src...')
            result = conn.execute(
                text('SELECT COUNT(*) FROM adaptive_tasks '
                     'WHERE difficulty_level_src IS NULL')
            )
            null_count = result.scalar()
            print(f'  Tasks with NULL difficulty_level_src: {null_count}')
            if null_count > 0:
                conn.execute(
                    text('UPDATE adaptive_tasks '
                         'SET difficulty_level_src = difficulty_level '
                         'WHERE difficulty_level_src IS NULL')
                )
                trans.commit()
                trans = conn.begin()
                print(f'  OK - saved {null_count} original values.')
            else:
                print('  OK - all already saved (idempotent).')

            # Step 3: current state
            print('\n[3/4] Current distribution:')
            result = conn.execute(
                text('SELECT difficulty_level, COUNT(*) FROM adaptive_tasks '
                     'GROUP BY difficulty_level ORDER BY difficulty_level')
            )
            dist = result.fetchall()
            total = sum(r[1] for r in dist)
            for lvl, cnt in dist:
                print(f'  Level {lvl}: {cnt:>6} ({cnt/total*100:.1f}%)')
            print(f'  TOTAL: {total}')

            # Step 4: remap FROM difficulty_level_src (IDEMPOTENT!)
            print('\n[4/4] Remapping difficulty_level FROM difficulty_level_src...')
            changed = 0
            for old_src, new_val in MAPPING.items():
                result = conn.execute(
                    text('SELECT COUNT(*) FROM adaptive_tasks '
                         'WHERE difficulty_level_src = :src AND difficulty_level != :val'),
                    {'src': old_src, 'val': new_val}
                )
                to_update = result.scalar()
                if to_update > 0:
                    conn.execute(
                        text('UPDATE adaptive_tasks SET difficulty_level = :val '
                             'WHERE difficulty_level_src = :src AND difficulty_level != :val'),
                        {'val': new_val, 'src': old_src}
                    )
                    changed += to_update
                    print(f'  src={old_src} -> {new_val}: {to_update} tasks updated')
                else:
                    result = conn.execute(
                        text('SELECT COUNT(*) FROM adaptive_tasks WHERE difficulty_level_src = :src'),
                        {'src': old_src}
                    )
                    total_src = result.scalar()
                    print(f'  src={old_src} -> {new_val}: {total_src} tasks (already correct)')

            trans.commit()
            print(f'\n  Total tasks remapped: {changed}')

            # Verification
            print('\n=== VERIFICATION ===')
            trans = conn.begin()
            result = conn.execute(
                text('SELECT difficulty_level, COUNT(*) FROM adaptive_tasks '
                     'GROUP BY difficulty_level ORDER BY difficulty_level')
            )
            dist_after = result.fetchall()
            for lvl, cnt in dist_after:
                print(f'  Level {lvl}: {cnt:>6} ({cnt/total*100:.1f}%)')
            result = conn.execute(
                text('SELECT COUNT(*) FROM adaptive_tasks '
                     'WHERE difficulty_level < 1 OR difficulty_level > 5')
            )
            outside = result.scalar()
            if outside == 0:
                print('\n  [OK] No tasks outside 1..5 range.')
            else:
                print(f'\n  [WARN] {outside} tasks outside 1..5 range!')
            result = conn.execute(
                text('SELECT COUNT(*) FROM adaptive_tasks '
                     'WHERE difficulty_level_src IS NOT NULL')
            )
            src = result.scalar()
            print(f'  [OK] {src} tasks have difficulty_level_src preserved.')
            trans.commit()
            print('\n' + '=' * 60)
            print('MIGRATION COMPLETE')
            print('=' * 60)

        except Exception as e:
            trans.rollback()
            print(f'\nERROR: {e}')
            raise
        finally:
            conn.close()


if __name__ == '__main__':
    main()
