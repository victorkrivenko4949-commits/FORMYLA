# -*- coding: utf-8 -*-
"""
Account merging service.

Use case: User A (current account, no Yandex linked) tries to link a Yandex ID
that's already attached to User B (legacy account). Instead of rejecting,
we offer to merge B's data INTO A — then delete B.

Strategy:
    - target_user (A) is the SURVIVOR (kept, becomes owner of all data)
    - source_user (B) is the DONOR  (data migrated to A, then deleted)

What gets migrated (FK reassignment):
    - OAuthAccount        (B's Yandex link -> A)
    - PrepPlan            -> A
    - PrepDay (cascade via plan)
    - TaskSolution        -> A
    - AdaptiveTest        -> A
    - AdaptiveTestProblem (cascade via test)
    - AdaptiveTestResult  -> A
    - ChatMessage         -> A
    - DailyQuest          -> A
    - UserStreak          -> A
    - TopicMastery        -> A
    - TestResult          -> A
    - UserProgress        -> A
    - UserTopicProgress   -> A
    - MockExam            -> A
    - Notification        -> A (both as recipient and sender)
    - Friendship          -> A (both sides)
    - Mentorship          -> A (as teacher and student)
    - SupportMessage      -> A

Fields preferred from source if target is empty:
    - User.name, User.avatar_url, User.preferred_grade, User.nickname (only if A has none)
"""
import logging
from datetime import datetime
from sqlalchemy import text

from models import db, User

logger = logging.getLogger(__name__)


# Tables to reassign user_id from source to target.
# Each entry: (table_name, user_id_column_name)
# These are kept simple raw-SQL UPDATEs to handle any user-related table without
# needing to keep model imports in sync.
_USER_FK_TABLES = [
    ('oauth_accounts', 'user_id'),
    ('prep_plans', 'user_id'),
    ('task_solutions', 'user_id'),
    ('adaptive_tests', 'user_id'),
    ('adaptive_test_results', 'user_id'),
    ('chat_messages', 'user_id'),
    ('daily_quests', 'user_id'),
    ('user_streaks', 'user_id'),
    ('topic_mastery', 'user_id'),
    ('test_results', 'user_id'),
    ('user_progress', 'user_id'),
    ('user_topic_progress', 'user_id'),
    ('mock_exams', 'user_id'),
    ('notifications', 'user_id'),
    ('notifications', 'sender_id'),
    ('friendships', 'user_a_id'),
    ('friendships', 'user_b_id'),
    ('friendships', 'requester_id'),
    ('mentorships', 'teacher_id'),
    ('mentorships', 'student_id'),
    ('support_messages', 'user_id'),
    ('olympiad_variants', 'user_id'),
    ('olympiad_task_attempts', 'user_id'),
    ('tutor_calls', 'user_id'),
]


def merge_users(target_user_id: int, source_user_id: int, dry_run: bool = False):
    """
    Merge source_user INTO target_user.

    target_user_id: int — the SURVIVOR. Will keep its id, email, etc., and
                          will gain all data from source.
    source_user_id: int — the DONOR. Will be DELETED after migration.
    dry_run: bool       — if True, only count rows that would be moved, do not commit.

    Returns: dict {table_name.column: rows_moved, ...} + 'source_deleted': True/False

    Raises:
        ValueError if either user does not exist, or they're the same user.
    """
    if target_user_id == source_user_id:
        raise ValueError(f"Cannot merge user into itself (id={target_user_id})")

    target = db.session.get(User, target_user_id)
    if target is None:
        raise ValueError(f"target user id={target_user_id} not found")

    source = db.session.get(User, source_user_id)
    if source is None:
        raise ValueError(f"source user id={source_user_id} not found")

    summary = {'_target_id': target_user_id, '_source_id': source_user_id, 'tables': {}}
    total_moved = 0

    try:
        # 1) Reassign FK columns from source -> target on every related table.
        for table, col in _USER_FK_TABLES:
            try:
                # First check if table & column exist (defensive, schemas drift)
                # We use raw SQL for portability between SQLite and Postgres.
                update_sql = text(f"UPDATE {table} SET {col} = :tgt WHERE {col} = :src")
                if dry_run:
                    count_sql = text(f"SELECT COUNT(*) FROM {table} WHERE {col} = :src")
                    n = db.session.execute(count_sql, {'src': source_user_id}).scalar() or 0
                else:
                    res = db.session.execute(update_sql, {'tgt': target_user_id, 'src': source_user_id})
                    n = res.rowcount or 0
                summary['tables'][f'{table}.{col}'] = n
                total_moved += n
            except Exception as e:
                # Table or column may not exist in this deployment — skip silently
                msg = str(e)
                summary['tables'][f'{table}.{col}'] = f'SKIPPED: {msg[:80]}'
                logger.info(f"merge: skipping {table}.{col}: {msg[:120]}")
                # Need to rollback the failed statement so the next UPDATE works
                try:
                    db.session.rollback()
                except Exception:
                    pass

        # 2) Backfill missing fields on target from source.
        if not target.name and source.name:
            target.name = source.name
        if not target.avatar_url and source.avatar_url:
            target.avatar_url = source.avatar_url
        if not target.preferred_grade and source.preferred_grade:
            target.preferred_grade = source.preferred_grade
        if not target.nickname and source.nickname:
            # Only carry over nickname if it doesn't conflict (UNIQUE constraint).
            # Check if any OTHER user (not source) already has this nickname.
            from sqlalchemy import or_
            conflict = User.query.filter(
                User.nickname == source.nickname,
                User.id != source_user_id,
                User.id != target_user_id,
            ).first()
            if not conflict:
                target.nickname = source.nickname
        # Sum streaks
        if hasattr(target, 'streak_days') and hasattr(source, 'streak_days'):
            try:
                target.streak_days = max(target.streak_days or 0, source.streak_days or 0)
            except Exception:
                pass
        # Stats: take max
        for fld in ('total_problems_solved', 'total_correct_answers', 'total_xp'):
            if hasattr(target, fld) and hasattr(source, fld):
                try:
                    a = getattr(target, fld) or 0
                    b = getattr(source, fld) or 0
                    setattr(target, fld, max(a, b))
                except Exception:
                    pass
        # ML consent: OR (если хоть кто-то согласился)
        try:
            target.ml_training_consent = bool(target.ml_training_consent) or bool(source.ml_training_consent)
        except Exception:
            pass

        if dry_run:
            db.session.rollback()
            summary['source_deleted'] = False
            summary['_dry_run'] = True
            summary['_total_rows_moved'] = total_moved
            return summary

        # 3) Delete the source user.
        # By now, all FKs pointing to source_user should be reassigned.
        # Any cascade-delete relationships on User will also trigger; that's OK
        # since we already moved the data we cared about.
        db.session.delete(source)
        db.session.commit()

        summary['source_deleted'] = True
        summary['_total_rows_moved'] = total_moved
        logger.info(f"[OK] merge_users: source={source_user_id} -> target={target_user_id}, "
                    f"moved {total_moved} rows across {len(summary['tables'])} table.column pairs")
        return summary

    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        logger.exception(f"merge_users FAILED: target={target_user_id} source={source_user_id}")
        raise


def get_merge_preview(target_user_id: int, source_user_id: int) -> dict:
    """
    Same as merge_users(dry_run=True) — returns counts of rows that would be moved.
    Convenient name for UI preview.
    """
    return merge_users(target_user_id, source_user_id, dry_run=True)
