# -*- coding: utf-8 -*-
"""
Migration: Replace one-directional friendship with bidirectional (requester/addressee)
Also adds Notification table.
"""
from app import app, db
from sqlalchemy import text, inspect


def migrate():
    with app.app_context():
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        print("Existing tables:", tables)

        # Check if old schema exists
        if 'friendships' in tables:
            cols = [c['name'] for c in inspector.get_columns('friendships')]
            print("Friendship columns:", cols)
            if 'user_1_id' in cols:
                print("Old schema detected - migrating...")
                with db.engine.connect() as conn:
                    conn.execute(text('ALTER TABLE friendships RENAME TO friendships_old'))
                    conn.commit()
                print("Old table renamed to friendships_old")

        # Create all new tables
        db.create_all()
        print("New tables created (friendships v2, notifications)")

        # Migrate old pending requests if old table exists
        tables_after = inspect(db.engine).get_table_names()
        if 'friendships_old' in tables_after:
            with db.engine.connect() as conn:
                old_rows = conn.execute(text('SELECT * FROM friendships_old')).fetchall()
                print(f"Found {len(old_rows)} old friendship records to migrate")
                for row in old_rows:
                    # Old schema: id, user_1_id, user_2_id, status, created_at, updated_at
                    conn.execute(text(
                        'INSERT OR IGNORE INTO friendships (requester_id, addressee_id, status, created_at) '
                        'VALUES (:r, :a, :s, :c)'
                    ), {'r': row[1], 'a': row[2], 's': row[3], 'c': row[4]})
                conn.commit()
                print("Migration of old records complete")

        print("Migration done!")


if __name__ == '__main__':
    migrate()
