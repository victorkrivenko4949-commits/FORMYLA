# -*- coding: utf-8 -*-
"""
Blueprint: Account management (/account)

Endpoints:
  POST /account/delete       - full account deletion with cascade
  POST /account/ml-consent   - toggle ML training consent
"""
import hashlib
import logging
from datetime import datetime

from flask import Blueprint, jsonify, request, render_template
from flask_login import current_user, login_required, logout_user

from models import db, User, PrepPlan, TaskSolution

logger = logging.getLogger(__name__)

account_bp = Blueprint('account', __name__, url_prefix='/account')


@account_bp.route('/privacy')
@login_required
def privacy_page():
    """Privacy settings page."""
    stats = {
        'solutions_count': TaskSolution.query.filter_by(user_id=current_user.id).count(),
        'photos_count': TaskSolution.query.filter(
            TaskSolution.user_id == current_user.id,
            TaskSolution.original_photo_url.isnot(None)
        ).count(),
        'plans_count': PrepPlan.query.filter_by(user_id=current_user.id).count(),
    }
    return render_template('account/privacy.html', stats=stats)


@account_bp.route('/delete', methods=['POST'])
@login_required
def delete_account():
    """
    Full account deletion with cascade.
    Requires JSON body: {"confirm": "DELETE"}
    """
    data = request.get_json(silent=True) or {}
    if data.get('confirm') != 'DELETE':
        return jsonify(error='Send {"confirm": "DELETE"} to confirm'), 400

    user_id = current_user.id
    email = current_user.email or ''
    email_hash = hashlib.sha256(email.encode()).hexdigest()

    logger.warning(f"Account deletion requested: user_id={user_id}")

    try:
        # 1. Delete photos from R2/local + TaskSolution records
        try:
            from services.storage import delete_all_solutions
            delete_all_solutions(user_id)
        except Exception as e:
            logger.error(f"Error deleting solutions: {e}")

        # 2. Delete prep plans (cascade deletes prep_days)
        PrepPlan.query.filter_by(user_id=user_id).delete()
        db.session.flush()

        # 3. Delete other related records
        _delete_related_records(user_id)

        # 4. Audit log
        _log_deletion_audit(user_id, email_hash)

        # 5. Delete user
        user = db.session.get(User, user_id)
        if user:
            db.session.delete(user)

        db.session.commit()
        logout_user()

        logger.warning(f"Account deleted: user_id={user_id}")
        return jsonify(status='deleted', message='Account permanently deleted')

    except Exception as e:
        db.session.rollback()
        logger.error(f"Account deletion failed: {e}")
        return jsonify(error='Deletion failed. Contact support.'), 500


@account_bp.route('/ml-consent', methods=['POST'])
@login_required
def toggle_ml_consent():
    """Toggle ML training consent for current user."""
    data = request.get_json(silent=True) or {}
    consent = bool(data.get('consent', False))

    current_user.ml_training_consent = consent
    db.session.commit()

    # Update consent on existing solutions
    TaskSolution.query.filter_by(user_id=current_user.id).update(
        {'consent_for_training': consent}
    )
    db.session.commit()

    return jsonify(status='ok', ml_training_consent=consent)


def _delete_related_records(user_id):
    """Delete all user-related records from auxiliary tables."""
    from sqlalchemy import text

    tables_with_user_id = [
        'chat_messages', 'adaptive_tests', 'adaptive_test_results',
        'user_topic_progress', 'daily_quests', 'user_streaks',
        'topic_mastery', 'notifications', 'test_results_detail',
        'user_progress', 'mock_exams',
    ]

    for table in tables_with_user_id:
        try:
            db.session.execute(
                text(f"DELETE FROM {table} WHERE user_id = :uid"),
                {'uid': user_id}
            )
        except Exception as e:
            logger.warning(f"Could not clean {table}: {e}")

    # Friendships (both directions)
    try:
        db.session.execute(
            text("DELETE FROM friendships WHERE user_id = :uid OR friend_id = :uid"),
            {'uid': user_id}
        )
    except Exception:
        pass

    # Mentorships
    try:
        db.session.execute(
            text("DELETE FROM mentorships WHERE teacher_id = :uid OR student_id = :uid"),
            {'uid': user_id}
        )
    except Exception:
        pass

    # OAuth accounts
    try:
        db.session.execute(
            text("DELETE FROM oauth_accounts WHERE user_id = :uid"),
            {'uid': user_id}
        )
    except Exception:
        pass

    db.session.flush()


def _log_deletion_audit(user_id, email_hash):
    """Log account deletion for audit trail."""
    from sqlalchemy import text

    try:
        # Create audit table if not exists
        db.session.execute(text("""
            CREATE TABLE IF NOT EXISTS deleted_users_audit (
                id INTEGER PRIMARY KEY,
                original_user_id INTEGER NOT NULL,
                email_hash VARCHAR(64) NOT NULL,
                deleted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        db.session.execute(
            text("INSERT INTO deleted_users_audit (original_user_id, email_hash, deleted_at) VALUES (:uid, :eh, :dt)"),
            {'uid': user_id, 'eh': email_hash, 'dt': datetime.utcnow()}
        )
        db.session.flush()
    except Exception as e:
        logger.warning(f"Audit log failed: {e}")
