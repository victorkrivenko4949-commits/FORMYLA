# -*- coding: utf-8 -*-
"""
Admin pages for Daily Pool management.

Routes:
  GET /admin/daily_pool   - Variant tree with mass approval
  GET /admin/budget       - Cost tracking and forecast
"""
import json
import logging
from datetime import date, datetime, timedelta

from flask import Blueprint, jsonify, render_template, request
from flask_login import current_user, login_required
from models import db

logger = logging.getLogger(__name__)

admin_pool_bp = Blueprint('admin_pool', __name__)


def admin_required(f):
    """Simple admin check — user_id == 1 or email in whitelist."""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({'error': 'unauthorized'}), 401
        # Simple admin check: user_id 1 or specific emails
        if current_user.id != 1:
            return jsonify({'error': 'forbidden'}), 403
        return f(*args, **kwargs)
    return decorated


@admin_pool_bp.route('/admin/daily_pool')
@login_required
@admin_required
def daily_pool_admin():
    """Admin page: variant tree with mass approval."""
    # Get date range
    start = request.args.get('start', (date.today() - timedelta(days=7)).isoformat())
    end = request.args.get('end', (date.today() + timedelta(days=7)).isoformat())

    variants = db.session.execute(
        db.text("""
            SELECT id, olympiad_slug, grade, round, variant_date, status,
                   total_cost_usd, generation_stack, created_at
            FROM daily_variants
            WHERE variant_date BETWEEN :s AND :e
            ORDER BY variant_date DESC, grade, round
        """),
        dict(s=start, e=end)
    ).fetchall()

    # Build tree: date -> grade -> round -> variant
    tree = {}
    for v in variants:
        d = str(v[4])
        if d not in tree:
            tree[d] = {}
        key = f"{v[2]}кл {v[3]}"
        tree[d][key] = {
            'id': v[0],
            'slug': v[1],
            'grade': v[2],
            'round': v[3],
            'status': v[5],
            'cost': round(v[6] or 0, 4),
            'stack': v[7],
            'created': str(v[8]) if v[8] else '',
        }

    # Get problems for each variant
    variant_ids = [v[0] for v in variants]
    problems = {}
    if variant_ids:
        placeholders = ','.join(str(vid) for vid in variant_ids)
        probs = db.session.execute(
            db.text(f"""
                SELECT variant_id, position, topic, difficulty, answer, status,
                       quality_scores
                FROM daily_problems
                WHERE variant_id IN ({placeholders})
                ORDER BY variant_id, position
            """)
        ).fetchall()
        for p in probs:
            vid = p[0]
            if vid not in problems:
                problems[vid] = []
            problems[vid].append({
                'position': p[1],
                'topic': p[2],
                'difficulty': p[3],
                'answer': p[4][:50] if p[4] else '',
                'status': p[5],
                'scores': p[6][:80] if p[6] else '',
            })

    # Counts
    total = len(variants)
    approved = sum(1 for v in variants if v[5] == 'approved')
    needs_review = sum(1 for v in variants if v[5] == 'needs_review')
    generating = sum(1 for v in variants if v[5] == 'generating')

    return render_template('admin/daily_pool.html',
        tree=tree,
        problems=problems,
        total=total,
        approved=approved,
        needs_review=needs_review,
        generating=generating,
        start=start,
        end=end,
    )


@admin_pool_bp.route('/admin/daily_pool/approve', methods=['POST'])
@login_required
@admin_required
def approve_variants():
    """Mass approve variants."""
    data = request.get_json() or {}
    variant_ids = data.get('variant_ids', [])

    if not variant_ids:
        return jsonify({'error': 'no variant_ids'}), 400

    count = 0
    for vid in variant_ids:
        db.session.execute(
            db.text("""
                UPDATE daily_variants
                SET status = 'approved', approved_at = CURRENT_TIMESTAMP
                WHERE id = :vid AND status = 'needs_review'
            """),
            dict(vid=vid)
        )
        count += 1

    db.session.commit()
    return jsonify({'approved': count})


@admin_pool_bp.route('/admin/budget')
@login_required
@admin_required
def budget_admin():
    """Admin page: budget tracking and forecast."""
    from config.models import MONTHLY_BUDGET_TARGET, MONTHLY_BUDGET_ALERT, MONTHLY_BUDGET_HARD_STOP

    # Current month costs
    now = datetime.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    costs_by_model = db.session.execute(
        db.text("""
            SELECT model, task_type,
                   SUM(cost_usd) as total_cost,
                   SUM(input_tokens) as total_in,
                   SUM(output_tokens) as total_out,
                   COUNT(*) as calls
            FROM generation_costs
            WHERE created_at >= :start
            GROUP BY model, task_type
            ORDER BY total_cost DESC
        """),
        dict(start=month_start.isoformat())
    ).fetchall()

    total_spent = sum(row[2] for row in costs_by_model) if costs_by_model else 0

    # Daily costs for chart
    daily_costs = db.session.execute(
        db.text("""
            SELECT DATE(created_at) as day, SUM(cost_usd)
            FROM generation_costs
            WHERE created_at >= :start
            GROUP BY DATE(created_at)
            ORDER BY day
        """),
        dict(start=month_start.isoformat())
    ).fetchall()

    # Forecast
    days_elapsed = max((now - month_start).days, 1)
    days_in_month = 30
    daily_rate = total_spent / days_elapsed
    forecast = daily_rate * days_in_month

    # Variant counts this month
    variant_count = db.session.execute(
        db.text("""
            SELECT COUNT(*) FROM daily_variants
            WHERE created_at >= :start
        """),
        dict(start=month_start.isoformat())
    ).fetchone()[0]

    cost_per_variant = total_spent / variant_count if variant_count > 0 else 0

    # Waitlist stats
    waitlist_count = db.session.execute(
        db.text("SELECT COUNT(*) FROM olympiad_waitlist")
    ).fetchone()[0]

    return render_template('admin/budget.html',
        costs_by_model=costs_by_model,
        total_spent=round(total_spent, 4),
        daily_costs=daily_costs,
        forecast=round(forecast, 2),
        daily_rate=round(daily_rate, 4),
        variant_count=variant_count,
        cost_per_variant=round(cost_per_variant, 4),
        budget_target=MONTHLY_BUDGET_TARGET,
        budget_alert=MONTHLY_BUDGET_ALERT,
        budget_hard_stop=MONTHLY_BUDGET_HARD_STOP,
        waitlist_count=waitlist_count,
        month_name=now.strftime('%B %Y'),
    )
