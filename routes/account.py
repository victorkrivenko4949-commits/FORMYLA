# -*- coding: utf-8 -*-
"""
Blueprint: Account management (/account)

Endpoints:
  POST /account/delete         - full account deletion with cascade
  POST /account/ml-consent     - toggle ML training consent
  GET  /account/merge_preview  - preview merge of two accounts (uses session)
  POST /account/merge          - perform the merge
"""
import hashlib
import logging
from datetime import datetime

from flask import Blueprint, jsonify, request, render_template, session, url_for, redirect, flash
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


@account_bp.route('/reintake', methods=['POST'])
@login_required
def reintake_account():
    """Временная кнопка «Перепройти анкету»: удаляет текущий аккаунт
    и возвращает пользователя на страницу входа/анкеты.

    Требует JSON: {"confirm": "DELETE"} — фронт показывает предупреждение
    о том, что аккаунт будет удалён безвозвратно.
    """
    data = request.get_json(silent=True) or {}
    if data.get('confirm') != 'DELETE':
        return jsonify(error='Send {"confirm": "DELETE"} to confirm'), 400

    user_id = current_user.id
    email = current_user.email or ''
    email_hash = hashlib.sha256(email.encode()).hexdigest()

    logger.warning(f"Account re-intake deletion requested: user_id={user_id}")

    try:
        # 1. Delete photos from R2/local + TaskSolution records
        try:
            from services.storage import delete_all_solutions
            delete_all_solutions(user_id)
        except Exception as e:
            logger.error(f"Error deleting solutions: {e}")

        # 2. Delete prep plans
        PrepPlan.query.filter_by(user_id=user_id).delete()
        db.session.flush()

        # 3. Delete other related records
        _delete_related_records(user_id)

        # 4. Audit log
        _log_deletion_audit(user_id, email_hash)

        # 5. Delete user (raw SQL — обходим ORM-nullify, который ломается
        #    на NOT NULL FK-колонках без ON DELETE CASCADE).
        _delete_user_row(user_id)

        db.session.commit()
        logout_user()

        logger.warning(f"Account deleted via re-intake: user_id={user_id}")
        return jsonify(status='deleted', redirect_url=url_for('login'))

    except Exception as e:
        db.session.rollback()
        logger.error(f"Re-intake deletion failed: {e}")
        return jsonify(error='Deletion failed. Contact support.'), 500


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

        # 5. Delete user (raw SQL — обходим ORM-nullify).
        _delete_user_row(user_id)

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


def _delete_user_row(user_id):
    """Удалить строку пользователя напрямую через raw SQL.

    Используем raw DELETE вместо ORM `db.session.delete(user)`, потому что
    SQLAlchemy при удалении родителя пытается "отвязать" зависимые записи
    (выставить FK в NULL) для колонок без ON DELETE CASCADE — а если колонка
    NOT NULL, это падает с IntegrityError (например figure_build_jobs.user_id,
    progress_log.user_id). Мы заранее чистим всё в _delete_related_records,
    поэтому raw DELETE безопасен.
    """
    from sqlalchemy import text
    db.session.execute(text("DELETE FROM users WHERE id = :uid"), {'uid': user_id})


def _delete_related_records(user_id):
    """Delete all user-related records from auxiliary tables."""
    from sqlalchemy import text

    tables_with_user_id = [
        'chat_messages', 'adaptive_tests', 'adaptive_test_results',
        'user_topic_progress', 'daily_quests', 'user_streaks',
        'topic_mastery', 'notifications', 'test_results_detail',
        'user_progress', 'mock_exams',
        # ── Curator module (NOT NULL user_id — удаляем до удаления юзера) ──
        'student_diagnostics', 'learning_plans', 'task_attempts',
        'progress_log', 'curator_state', 'subtopic_progress',
        # ── Daily tasks module ──
        'daily_task_sets', 'user_task_assignments', 'thematic_day_sets',
        'pre_gen_queue', 'gen_conveyor', 'bank_issues',
        # ── Прочее (прямая привязка к пользователю) ──
        'streak_records', 'user_subtopic_assignments',
        'user_dashboard_items', 'solution_attempts', 'task_solutions',
        'task_assignment_history', 'photo_recognize_requests',
        'olympiad_generation_log',
        # ── Чертежи / фигуры (NOT NULL user_id без ON DELETE CASCADE) ──
        'figure_jobs', 'figure_build_jobs', 'figure_credit_transactions',
        'figure_generations', 'drawing_generations',
        # ── Группы (колонка user_id) ──
        'group_members', 'teacher_group_members',
    ]

    for table in tables_with_user_id:
        try:
            db.session.execute(
                text(f"DELETE FROM {table} WHERE user_id = :uid"),
                {'uid': user_id}
            )
        except Exception as e:
            logger.warning(f"Could not clean {table}: {e}")

    # Дочерние таблицы без user_id (FK к родительскому daily_task_sets):
    # удаляем до daily_task_sets, иначе FK-каскад может не сработать.
    try:
        db.session.execute(
            text("DELETE FROM daily_task_items WHERE daily_set_id IN "
                 "(SELECT id FROM daily_task_sets WHERE user_id = :uid)"),
            {'uid': user_id}
        )
    except Exception as e:
        logger.warning(f"Could not clean daily_task_items: {e}")

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


# ─── Account merge endpoints ───────────────────────────────────────────────


@account_bp.route('/merge_preview')
@login_required
def merge_preview():
    src_id = session.get('merge_candidate_source_id')
    if not src_id:
        flash('Нет ожидающего слияния аккаунтов.', 'warning')
        return redirect(url_for('profile'))
    source = db.session.get(User, int(src_id))
    if source is None:
        session.pop('merge_candidate_source_id', None)
        flash('Аккаунт-источник не найден.', 'error')
        return redirect(url_for('profile'))
    try:
        from services.account_merge import get_merge_preview
        preview = get_merge_preview(target_user_id=current_user.id, source_user_id=source.id)
    except Exception as e:
        logger.error(f"merge_preview failed: {e}")
        preview = None
    return render_template(
        'account/merge_preview.html',
        target=current_user,
        source=source,
        preview=preview,
    )


@account_bp.route('/merge', methods=['POST'])
@login_required
def merge_accounts():
    data = request.get_json(silent=True) or {}
    if data.get('confirm') != 'MERGE':
        return jsonify(error='Send confirm=MERGE to proceed'), 400
    src_id = session.get('merge_candidate_source_id')
    if not src_id:
        return jsonify(error='No pending merge in session'), 400
    if int(src_id) == current_user.id:
        session.pop('merge_candidate_source_id', None)
        return jsonify(error='Cannot merge account into itself'), 400
    try:
        from services.account_merge import merge_users
        summary = merge_users(target_user_id=current_user.id, source_user_id=int(src_id))
    except Exception as e:
        logger.exception('merge_accounts failed')
        return jsonify(error=str(e)), 500
    session.pop('merge_candidate_source_id', None)
    return jsonify(status='ok', summary=summary, redirect_url=url_for('profile'))


@account_bp.route('/merge/cancel', methods=['POST'])
@login_required
def merge_cancel():
    session.pop('merge_candidate_source_id', None)
    return jsonify(status='cancelled', redirect_url=url_for('profile'))
