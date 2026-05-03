# -*- coding: utf-8 -*-
"""
Blueprint: Daily Olympiad ("Написать олимпиаду")

Endpoints:
  GET  /olympiad/write                  - Main page (selection + solving + results)
  GET  /api/olympiad/options            - Available olympiads/grades/rounds
  GET  /api/olympiad/daily              - Get today's variant (start attempt)
  POST /api/olympiad/daily/save_draft   - Autosave user answers
  POST /api/olympiad/daily/finish       - Submit and check answers
  GET  /api/olympiad/daily/history      - User's attempt history
"""

import hashlib
import json
import logging
from datetime import date, datetime, timedelta, timezone
from functools import wraps

from flask import Blueprint, jsonify, render_template, request
from flask_login import current_user, login_required

from models import db

logger = logging.getLogger(__name__)

# Moscow timezone offset
MSK = timezone(timedelta(hours=3))

daily_olympiad_bp = Blueprint(
    'daily_olympiad', __name__,
    template_folder='../templates'
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def get_today_msk():
    """Get current date in Moscow timezone."""
    return datetime.now(MSK).date()


def get_subscription_limit(plan):
    """Return daily olympiad attempts limit by plan."""
    limits = {
        'free': 0,
        'plus': 1,
        'premium': 3,
    }
    return limits.get(plan, 0)


def shuffle_positions(problems, user_id, variant_date):
    """Deterministic shuffle of problem positions based on user_id + date."""
    seed = hashlib.md5(f"{user_id}:{variant_date}".encode()).hexdigest()
    seed_int = int(seed[:8], 16)
    
    indexed = list(enumerate(problems))
    # Fisher-Yates with deterministic seed
    import random
    rng = random.Random(seed_int)
    rng.shuffle(indexed)
    
    return indexed


def require_subscription(f):
    """Decorator: check user has active subscription for daily olympiad."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({'error': 'auth_required', 'message': 'Требуется авторизация'}), 401
        
        plan = getattr(current_user, 'current_plan', 'free') or 'free'
        limit = get_subscription_limit(plan)
        
        if limit == 0:
            return jsonify({
                'error': 'subscription_required',
                'message': 'Раздел доступен только в платной версии',
                'upgrade_url': '/subscribe'
            }), 403
        
        # Check today's attempts count
        today = get_today_msk()
        attempts_today = db.session.execute(
            db.text("""
                SELECT COUNT(*) FROM user_daily_attempts uda
                JOIN daily_variants dv ON uda.variant_id = dv.id
                WHERE uda.user_id = :uid
                AND DATE(uda.attempted_at) = :today
            """),
            {'uid': current_user.id, 'today': today.isoformat()}
        ).scalar() or 0
        
        # Count unique variants started today (not individual problem attempts)
        variants_started = db.session.execute(
            db.text("""
                SELECT COUNT(DISTINCT variant_id) FROM user_daily_attempts
                WHERE user_id = :uid
                AND DATE(attempted_at) = :today
            """),
            {'uid': current_user.id, 'today': today.isoformat()}
        ).scalar() or 0
        
        if variants_started >= limit:
            return jsonify({
                'error': 'limit_reached',
                'message': f'Лимит на сегодня исчерпан ({variants_started}/{limit})',
                'limit': limit,
                'used': variants_started,
                'upgrade_url': '/subscribe'
            }), 403
        
        return f(*args, **kwargs)
    return decorated


# ─── Page Route ───────────────────────────────────────────────────────────────

@daily_olympiad_bp.route('/olympiad/write')
@login_required
def olympiad_write_page():
    """Main page for daily olympiad writing."""
    return render_template('olympiad/write.html')


# ─── API: Options ─────────────────────────────────────────────────────────────

@daily_olympiad_bp.route('/api/olympiad/options')
@login_required
def olympiad_options():
    """
    Returns available olympiad/grade/round combinations from problems_archive.
    Cached response (could add Redis cache later).
    """
    rows = db.session.execute(
        db.text("""
            SELECT DISTINCT olympiad_slug, olympiad_title, grade, round
            FROM problems_archive
            ORDER BY olympiad_slug, grade, round
        """)
    ).fetchall()

    # Build structured response
    olympiads = {}
    for row in rows:
        slug = row[0]
        title = row[1]
        grade = row[2]
        rnd = row[3]

        if slug not in olympiads:
            olympiads[slug] = {
                'slug': slug,
                'title': title,
                'grades': set(),
                'rounds_by_grade': {}
            }

        olympiads[slug]['grades'].add(grade)
        if str(grade) not in olympiads[slug]['rounds_by_grade']:
            olympiads[slug]['rounds_by_grade'][str(grade)] = []
        if rnd not in olympiads[slug]['rounds_by_grade'][str(grade)]:
            olympiads[slug]['rounds_by_grade'][str(grade)].append(rnd)

    # Convert sets to sorted lists
    result = []
    for slug, data in sorted(olympiads.items()):
        data['grades'] = sorted(data['grades'])
        result.append(data)

    return jsonify({'olympiads': result})


# ─── API: Get Daily Variant ───────────────────────────────────────────────────

@daily_olympiad_bp.route('/api/olympiad/daily')
@login_required
@require_subscription
def get_daily_variant():
    """
    Get today's variant for the specified combination.
    
    Query params: olympiad, grade, round
    
    Returns variant with problems (without answers/solutions).
    If user already has an attempt today - returns existing progress.
    """
    olympiad = request.args.get('olympiad', '').strip()
    grade = request.args.get('grade', type=int)
    rnd = request.args.get('round', '').strip()

    if not olympiad or not grade or not rnd:
        return jsonify({'error': 'missing_params', 
                       'message': 'Укажите olympiad, grade и round'}), 400

    today = get_today_msk()
    user_id = current_user.id

    # Check if user already has an attempt for this combo today
    existing_attempt = db.session.execute(
        db.text("""
            SELECT dv.id as variant_id, dv.status as variant_status
            FROM daily_variants dv
            WHERE dv.olympiad_slug = :olympiad
            AND dv.grade = :grade
            AND dv.round = :round
            AND dv.variant_date = :today
            AND dv.status = 'approved'
            LIMIT 1
        """),
        {'olympiad': olympiad, 'grade': grade, 'round': rnd, 'today': today.isoformat()}
    ).fetchone()

    if not existing_attempt:
        # Check if variant exists but not approved yet
        pending = db.session.execute(
            db.text("""
                SELECT status FROM daily_variants
                WHERE olympiad_slug = :olympiad AND grade = :grade
                AND round = :round AND variant_date = :today
                LIMIT 1
            """),
            {'olympiad': olympiad, 'grade': grade, 'round': rnd, 'today': today.isoformat()}
        ).fetchone()

        if pending:
            return jsonify({
                'error': 'variant_not_ready',
                'message': 'Вариант на сегодня ещё готовится, попробуйте через час',
                'status': pending[0]
            }), 503
        else:
            return jsonify({
                'error': 'variant_not_found',
                'message': 'Вариант для этой комбинации ещё не создан. Попробуйте другую олимпиаду или вернитесь позже.'
            }), 503

    variant_id = existing_attempt[0]

    # Get problems for this variant (WITHOUT answers and solutions)
    problems = db.session.execute(
        db.text("""
            SELECT id, position, text, topic, difficulty
            FROM daily_problems
            WHERE variant_id = :vid
            ORDER BY position
        """),
        {'vid': variant_id}
    ).fetchall()

    if not problems:
        return jsonify({
            'error': 'no_problems',
            'message': 'Вариант пуст, попробуйте позже'
        }), 503

    # Check if user already started this variant
    user_answers = db.session.execute(
        db.text("""
            SELECT problem_id, user_answer, is_correct
            FROM user_daily_attempts
            WHERE user_id = :uid AND variant_id = :vid
        """),
        {'uid': user_id, 'vid': variant_id}
    ).fetchall()

    # Determine attempt state
    answers_map = {}
    is_finished = False
    for ans in user_answers:
        answers_map[ans[0]] = {
            'user_answer': ans[1],
            'is_correct': ans[2]
        }
        if ans[2] is not None:  # has been checked = finished
            is_finished = True

    # Shuffle problems deterministically
    problem_list = []
    shuffled = shuffle_positions(problems, user_id, today)
    
    for display_pos, (orig_idx, prob) in enumerate(shuffled, 1):
        p = {
            'id': prob[0],
            'position': display_pos,
            'original_position': prob[1],
            'text': prob[2],
            'topic': prob[3],
            'difficulty': prob[4],
        }
        # Include user's saved answer if exists
        if prob[0] in answers_map:
            p['user_answer'] = answers_map[prob[0]]['user_answer']
            if is_finished:
                p['is_correct'] = answers_map[prob[0]]['is_correct']
        problem_list.append(p)

    return jsonify({
        'variant_id': variant_id,
        'olympiad': olympiad,
        'grade': grade,
        'round': rnd,
        'date': today.isoformat(),
        'problems': problem_list,
        'total_problems': len(problem_list),
        'is_finished': is_finished,
        'filled_count': len(answers_map)
    })


# ─── API: Save Draft ─────────────────────────────────────────────────────────

@daily_olympiad_bp.route('/api/olympiad/daily/save_draft', methods=['POST'])
@login_required
def save_draft():
    """
    Autosave a single problem answer (debounced from frontend).
    
    Body: {variant_id, problem_id, user_answer, user_solution}
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'invalid_json'}), 400

    variant_id = data.get('variant_id')
    problem_id = data.get('problem_id')
    user_answer = data.get('user_answer', '').strip()
    user_solution = data.get('user_solution', '').strip()

    if not variant_id or not problem_id:
        return jsonify({'error': 'missing_params'}), 400

    user_id = current_user.id

    # Verify variant exists and belongs to today
    variant = db.session.execute(
        db.text("""
            SELECT id, variant_date FROM daily_variants
            WHERE id = :vid AND status = 'approved'
        """),
        {'vid': variant_id}
    ).fetchone()

    if not variant:
        return jsonify({'error': 'variant_not_found'}), 404

    # Check if already finished (no edits after finish)
    existing = db.session.execute(
        db.text("""
            SELECT id, is_correct FROM user_daily_attempts
            WHERE user_id = :uid AND variant_id = :vid AND problem_id = :pid
        """),
        {'uid': user_id, 'vid': variant_id, 'pid': problem_id}
    ).fetchone()

    if existing and existing[1] is not None:
        return jsonify({'error': 'already_finished', 
                       'message': 'Вариант уже завершён, редактирование невозможно'}), 403

    # Combine answer + solution into JSON
    answer_data = json.dumps({
        'answer': user_answer,
        'solution': user_solution
    }, ensure_ascii=False)

    if existing:
        # Update existing draft
        db.session.execute(
            db.text("""
                UPDATE user_daily_attempts
                SET user_answer = :answer, attempted_at = :now
                WHERE id = :id
            """),
            {'answer': answer_data, 'now': datetime.now(MSK), 'id': existing[0]}
        )
    else:
        # Insert new draft
        db.session.execute(
            db.text("""
                INSERT INTO user_daily_attempts 
                    (user_id, variant_id, problem_id, user_answer, attempted_at)
                VALUES (:uid, :vid, :pid, :answer, :now)
            """),
            {
                'uid': user_id, 'vid': variant_id, 'pid': problem_id,
                'answer': answer_data, 'now': datetime.now(MSK)
            }
        )

    db.session.commit()
    return jsonify({'status': 'saved', 'problem_id': problem_id})


# ─── API: Finish ──────────────────────────────────────────────────────────────

@daily_olympiad_bp.route('/api/olympiad/daily/finish', methods=['POST'])
@login_required
def finish_variant():
    """
    Submit variant for checking. Compares user answers with correct ones.
    
    Body: {variant_id}
    
    Returns full results with solutions.
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'invalid_json'}), 400

    variant_id = data.get('variant_id')
    if not variant_id:
        return jsonify({'error': 'missing_variant_id'}), 400

    user_id = current_user.id

    # Check not already finished
    already_finished = db.session.execute(
        db.text("""
            SELECT COUNT(*) FROM user_daily_attempts
            WHERE user_id = :uid AND variant_id = :vid AND is_correct IS NOT NULL
        """),
        {'uid': user_id, 'vid': variant_id}
    ).scalar()

    if already_finished > 0:
        return jsonify({'error': 'already_finished',
                       'message': 'Вариант уже проверен'}), 403

    # Get all problems with correct answers
    problems = db.session.execute(
        db.text("""
            SELECT id, position, text, answer, solution, topic, difficulty
            FROM daily_problems
            WHERE variant_id = :vid
            ORDER BY position
        """),
        {'vid': variant_id}
    ).fetchall()

    if not problems:
        return jsonify({'error': 'no_problems'}), 404

    # Get user's saved answers
    user_attempts = db.session.execute(
        db.text("""
            SELECT problem_id, user_answer
            FROM user_daily_attempts
            WHERE user_id = :uid AND variant_id = :vid
        """),
        {'uid': user_id, 'vid': variant_id}
    ).fetchall()

    user_answers_map = {row[0]: row[1] for row in user_attempts}

    # Check each problem
    results = []
    correct_count = 0
    today = get_today_msk()

    for prob in problems:
        prob_id = prob[0]
        correct_answer = (prob[3] or '').strip()
        solution = prob[4] or ''
        
        # Parse user answer from JSON
        raw_user_answer = user_answers_map.get(prob_id, '')
        user_answer = ''
        user_solution = ''
        
        if raw_user_answer:
            try:
                parsed = json.loads(raw_user_answer)
                user_answer = parsed.get('answer', '').strip()
                user_solution = parsed.get('solution', '').strip()
            except (json.JSONDecodeError, AttributeError):
                user_answer = str(raw_user_answer).strip()

        # Simple comparison (normalize whitespace, case-insensitive for text)
        is_correct = _compare_answers(user_answer, correct_answer)
        if is_correct:
            correct_count += 1

        # Update or insert the attempt record with is_correct
        existing = db.session.execute(
            db.text("""
                SELECT id FROM user_daily_attempts
                WHERE user_id = :uid AND variant_id = :vid AND problem_id = :pid
            """),
            {'uid': user_id, 'vid': variant_id, 'pid': prob_id}
        ).fetchone()

        if existing:
            db.session.execute(
                db.text("""
                    UPDATE user_daily_attempts
                    SET is_correct = :correct, attempted_at = :now
                    WHERE id = :id
                """),
                {'correct': is_correct, 'now': datetime.now(MSK), 'id': existing[0]}
            )
        else:
            # User didn't answer this problem
            answer_data = json.dumps({'answer': '', 'solution': ''}, ensure_ascii=False)
            db.session.execute(
                db.text("""
                    INSERT INTO user_daily_attempts
                        (user_id, variant_id, problem_id, user_answer, is_correct, attempted_at)
                    VALUES (:uid, :vid, :pid, :answer, :correct, :now)
                """),
                {
                    'uid': user_id, 'vid': variant_id, 'pid': prob_id,
                    'answer': answer_data, 'correct': False,
                    'now': datetime.now(MSK)
                }
            )

        results.append({
            'problem_id': prob_id,
            'position': prob[1],
            'text': prob[2],
            'correct_answer': correct_answer,
            'user_answer': user_answer,
            'user_solution': user_solution,
            'solution': solution,
            'topic': prob[5],
            'difficulty': prob[6],
            'is_correct': is_correct
        })

    db.session.commit()

    # Shuffle results same way as problems were displayed
    shuffled = shuffle_positions(results, user_id, today)
    shuffled_results = []
    for display_pos, (_, r) in enumerate(shuffled, 1):
        r['display_position'] = display_pos
        shuffled_results.append(r)

    total = len(problems)
    score_percent = round(correct_count / total * 100) if total > 0 else 0

    # Determine score color
    if score_percent == 100:
        score_color = 'gold'
    elif score_percent >= 80:
        score_color = 'green'
    elif score_percent >= 50:
        score_color = 'blue'
    else:
        score_color = 'gray'

    # Update streak (only if score >= 40%)
    streak = 0
    if score_percent >= 40:
        streak = _update_streak(user_id, today)

    return jsonify({
        'status': 'finished',
        'variant_id': variant_id,
        'correct_count': correct_count,
        'total': total,
        'score_percent': score_percent,
        'score_color': score_color,
        'streak': streak,
        'results': shuffled_results,
        'user_id': user_id,
        'date': today.isoformat(),
        'share_text': f'FORMYLA | {_get_variant_title(variant_id)} | {correct_count}/{total} | {today.strftime("%d.%m.%Y")} | ID:{user_id}'
    })


# ─── API: History ─────────────────────────────────────────────────────────────

@daily_olympiad_bp.route('/api/olympiad/daily/history')
@login_required
def attempt_history():
    """
    Returns user's attempt history (last 20 attempts).
    """
    user_id = current_user.id

    rows = db.session.execute(
        db.text("""
            SELECT 
                dv.id,
                dv.olympiad_slug,
                dv.olympiad_title,
                dv.grade,
                dv.round,
                dv.round_title,
                dv.variant_date,
                COUNT(CASE WHEN uda.is_correct = 1 THEN 1 END) as correct,
                COUNT(uda.id) as total,
                MIN(uda.attempted_at) as started_at
            FROM user_daily_attempts uda
            JOIN daily_variants dv ON uda.variant_id = dv.id
            WHERE uda.user_id = :uid AND uda.is_correct IS NOT NULL
            GROUP BY dv.id, dv.olympiad_slug, dv.olympiad_title, 
                     dv.grade, dv.round, dv.round_title, dv.variant_date
            ORDER BY dv.variant_date DESC
            LIMIT 20
        """),
        {'uid': user_id}
    ).fetchall()

    history = []
    for row in rows:
        history.append({
            'variant_id': row[0],
            'olympiad_slug': row[1],
            'olympiad_title': row[2],
            'grade': row[3],
            'round': row[4],
            'round_title': row[5],
            'date': row[6].isoformat() if row[6] else None,
            'correct': row[7],
            'total': row[8],
            'score_percent': round(row[7] / row[8] * 100) if row[8] > 0 else 0,
            'started_at': row[9].isoformat() if row[9] else None
        })

    return jsonify({'history': history, 'total_count': len(history)})


# ─── Internal Helpers ─────────────────────────────────────────────────────────

def _compare_answers(user_answer: str, correct_answer: str) -> bool:
    """
    Compare user answer with correct answer.
    Handles: whitespace normalization, case-insensitive, 
    comma-separated sets, numeric equivalence.
    """
    if not user_answer or not correct_answer:
        return False

    # Normalize
    ua = user_answer.strip().lower().replace(' ', '')
    ca = correct_answer.strip().lower().replace(' ', '')

    # Direct match
    if ua == ca:
        return True

    # Try numeric comparison
    try:
        if abs(float(ua) - float(ca)) < 1e-9:
            return True
    except (ValueError, TypeError):
        pass

    # Try set comparison (for answers like "1,2,3" vs "3,2,1")
    ua_parts = sorted(ua.replace(';', ',').split(','))
    ca_parts = sorted(ca.replace(';', ',').split(','))
    if ua_parts == ca_parts and len(ua_parts) > 1:
        return True

    return False


def _update_streak(user_id: int, today: date) -> int:
    """
    Update user's olympiad streak. Returns current streak count.
    Streak counts consecutive days with score >= 40%.
    """
    # Get last 30 days of attempts
    rows = db.session.execute(
        db.text("""
            SELECT DISTINCT DATE(uda.attempted_at) as attempt_date
            FROM user_daily_attempts uda
            WHERE uda.user_id = :uid AND uda.is_correct IS NOT NULL
            AND DATE(uda.attempted_at) >= :start
            ORDER BY attempt_date DESC
        """),
        {'uid': user_id, 'start': (today - timedelta(days=30)).isoformat()}
    ).fetchall()

    if not rows:
        return 1  # Today counts

    dates = [row[0] for row in rows]
    
    # Count consecutive days from today backwards
    streak = 0
    check_date = today
    
    for d in dates:
        if isinstance(d, str):
            d = date.fromisoformat(d)
        if d == check_date:
            streak += 1
            check_date -= timedelta(days=1)
        elif d < check_date:
            break

    return max(streak, 1)


def _get_variant_title(variant_id: int) -> str:
    """Get human-readable title for a variant."""
    row = db.session.execute(
        db.text("""
            SELECT olympiad_title, grade, round_title, round
            FROM daily_variants WHERE id = :vid
        """),
        {'vid': variant_id}
    ).fetchone()

    if not row:
        return "Unknown"

    title = row[0] or ''
    grade = row[1] or ''
    round_title = row[2] or row[3] or ''
    return f"{title} {grade}kl {round_title}"