# -*- coding: utf-8 -*-
"""
Admin dashboard for «Задачи дня» (Daily Tasks) pipeline.

Реализует DoD #10 из ТЗ formyla_daily_tasks_TZ_for_roo.md:
> «В админке видна метрика "% flagged за сегодня"»

Routes
------
* ``GET /admin/daily_tasks/stats``      — JSON со статистикой за сегодня + N дней
* ``GET /admin/daily_tasks/dashboard``  — HTML дашборд (минимум, для глаз админа)

Метрики (раздел 12 ТЗ):
  * сегодня сгенерировано наборов (total / ready / partial / failed)
  * средняя стоимость одного набора, $
  * среднее время генерации, сек
  * % задач с is_flagged
  * распределение opus_iterations (с какой попытки задача approved)
  * accuracy учеников на сгенерированных задачах
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from functools import wraps

from flask import Blueprint, current_app, jsonify, render_template_string, request
from flask_login import current_user, login_required

from models import db
from daily_tasks.models import DailyTaskSet, DailyTaskItem, DailyGenerationJob

logger = logging.getLogger(__name__)

admin_daily_stats_bp = Blueprint(
    'admin_daily_stats',
    __name__,
    url_prefix='/admin/daily_tasks',
)


# ──────────────────────────────────────────────────────────────────────
# Access control
# ──────────────────────────────────────────────────────────────────────
def admin_required(f):
    """Простая защита: только user_id == 1 (как в routes/admin_daily_pool.py)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({'error': 'unauthorized'}), 401
        if current_user.id != 1:
            return jsonify({'error': 'forbidden'}), 403
        return f(*args, **kwargs)
    return decorated


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────
def _safe_avg(values: list[float | int | None]) -> float | None:
    """Среднее, игнорирующее None."""
    clean = [v for v in values if v is not None]
    return round(sum(clean) / len(clean), 3) if clean else None


def _stats_for_period(start_date: date, end_date: date) -> dict:
    """Собирает статистику по сетам/задачам/джобам за интервал [start_date..end_date]."""
    # ── 1. Sets ────────────────────────────────────────────────────────
    sets = (
        DailyTaskSet.query
        .filter(DailyTaskSet.target_date >= start_date)
        .filter(DailyTaskSet.target_date <= end_date)
        .all()
    )

    set_status_counts: dict[str, int] = {}
    set_costs: list[float] = []
    for s in sets:
        set_status_counts[s.status] = set_status_counts.get(s.status, 0) + 1
        if s.total_cost_usd is not None:
            set_costs.append(s.total_cost_usd)

    # ── 2. Items ───────────────────────────────────────────────────────
    set_ids = [s.id for s in sets]
    items: list[DailyTaskItem] = []
    if set_ids:
        items = (
            DailyTaskItem.query
            .filter(DailyTaskItem.daily_set_id.in_(set_ids))
            .all()
        )

    flagged_count = sum(1 for it in items if it.is_flagged)
    items_total = len(items)
    flagged_pct = round(100.0 * flagged_count / items_total, 2) if items_total else 0.0

    # Распределение opus_iterations
    iteration_dist: dict[int, int] = {}
    for it in items:
        n = it.opus_iterations or 0
        iteration_dist[n] = iteration_dist.get(n, 0) + 1

    # Accuracy учеников
    answered = [it for it in items if it.status == 'answered' and it.is_correct is not None]
    answered_correct = sum(1 for it in answered if it.is_correct)
    answered_total = len(answered)
    user_accuracy = round(100.0 * answered_correct / answered_total, 2) if answered_total else None

    # Avg time spent на задачу учеником
    times = [it.time_spent_seconds for it in items if it.time_spent_seconds]
    avg_time_spent_sec = _safe_avg(times)

    # ── 3. Jobs ───────────────────────────────────────────────────────
    jobs = (
        DailyGenerationJob.query
        .filter(DailyGenerationJob.target_date >= start_date)
        .filter(DailyGenerationJob.target_date <= end_date)
        .all()
    )

    job_state_counts: dict[str, int] = {}
    job_durations: list[float] = []
    for j in jobs:
        job_state_counts[j.state] = job_state_counts.get(j.state, 0) + 1
        if j.started_at and j.finished_at:
            delta = (j.finished_at - j.started_at).total_seconds()
            if delta >= 0:
                job_durations.append(delta)

    avg_generation_sec = _safe_avg(job_durations)
    p95_generation_sec = None
    if job_durations:
        srt = sorted(job_durations)
        p95_generation_sec = round(srt[int(0.95 * (len(srt) - 1))], 2)

    # ── 4. Breakdown по subject ───────────────────────────────────────
    subject_breakdown: dict[str, dict[str, int]] = {}
    for it in items:
        subj = it.subject or 'unknown'
        d = subject_breakdown.setdefault(subj, {
            'total': 0, 'flagged': 0, 'answered': 0, 'correct': 0,
        })
        d['total'] += 1
        if it.is_flagged:
            d['flagged'] += 1
        if it.status == 'answered':
            d['answered'] += 1
            if it.is_correct:
                d['correct'] += 1

    # ── 5. Топ slow jobs (для оптимизации) ─────────────────────────────
    slow_jobs = []
    for j in jobs:
        if j.started_at and j.finished_at:
            delta = (j.finished_at - j.started_at).total_seconds()
            slow_jobs.append({
                'job_id': j.id,
                'user_id': j.user_id,
                'date': j.target_date.isoformat() if j.target_date else None,
                'duration_sec': round(delta, 1),
                'state': j.state,
            })
    slow_jobs.sort(key=lambda x: x['duration_sec'], reverse=True)
    slow_jobs = slow_jobs[:5]

    return {
        'period': {
            'start': start_date.isoformat(),
            'end': end_date.isoformat(),
            'days': (end_date - start_date).days + 1,
        },
        'sets': {
            'total': len(sets),
            'by_status': set_status_counts,
            'avg_cost_usd': _safe_avg(set_costs),
            'total_cost_usd': round(sum(set_costs), 4) if set_costs else 0.0,
        },
        'items': {
            'total': items_total,
            'flagged': flagged_count,
            'flagged_pct': flagged_pct,            # ← главная метрика DoD #10
            'iteration_distribution': iteration_dist,
            'user_accuracy_pct': user_accuracy,
            'answered_count': answered_total,
            'avg_time_spent_sec': avg_time_spent_sec,
        },
        'jobs': {
            'total': len(jobs),
            'by_state': job_state_counts,
            'avg_generation_sec': avg_generation_sec,
            'p95_generation_sec': p95_generation_sec,
        },
        'by_subject': subject_breakdown,
        'slowest_jobs': slow_jobs,
    }


# ──────────────────────────────────────────────────────────────────────
# GET /admin/daily_tasks/stats
# ──────────────────────────────────────────────────────────────────────
@admin_daily_stats_bp.route('/stats', methods=['GET'])
@login_required
@admin_required
def stats_json():
    """JSON-ответ со статистикой.

    Query params:
        days (int, default=1) — за сколько последних дней включая сегодня

    Returns 200 OK + JSON со структурой, описанной в разделе 12 ТЗ.
    """
    try:
        days = int(request.args.get('days', '1'))
        days = max(1, min(days, 90))   # clamp 1..90
    except (TypeError, ValueError):
        days = 1

    today = date.today()
    start = today - timedelta(days=days - 1)
    payload = _stats_for_period(start, today)
    payload['generated_at'] = datetime.utcnow().isoformat() + 'Z'
    return jsonify(payload), 200


# ──────────────────────────────────────────────────────────────────────
# GET /admin/daily_tasks/dashboard  — простой HTML
# ──────────────────────────────────────────────────────────────────────
_DASHBOARD_HTML = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>Daily Tasks · Admin Stats</title>
<style>
  body { font-family: -apple-system, Segoe UI, sans-serif; max-width: 1100px; margin: 20px auto; padding: 0 20px; color: #222; }
  h1 { font-size: 22px; margin: 0 0 8px; }
  .sub { color:#666; font-size: 13px; margin-bottom: 24px; }
  .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; margin-bottom: 28px; }
  .card { border: 1px solid #e2e2e2; border-radius: 10px; padding: 14px 16px; background: #fafafa; }
  .card .label { font-size: 12px; color: #777; text-transform: uppercase; letter-spacing: .05em; }
  .card .val { font-size: 26px; font-weight: 600; margin-top: 6px; color: #111; }
  .card .val.warn { color: #c0392b; }
  .card .val.ok { color: #1d8348; }
  table { border-collapse: collapse; width: 100%; margin-bottom: 24px; font-size: 14px; }
  th, td { border: 1px solid #e2e2e2; padding: 8px 10px; text-align: left; }
  th { background: #f6f6f6; font-weight: 600; }
  .nav a { margin-right: 12px; }
  pre { background: #f3f3f3; padding: 10px; border-radius: 6px; font-size: 12px; overflow-x: auto; }
</style>
</head>
<body>
  <h1>📊 «Задачи дня» — статистика</h1>
  <div class="sub">
    Период: {{ d.period.start }} … {{ d.period.end }} ({{ d.period.days }} дн.) ·
    Сгенерировано: {{ d.generated_at }}
  </div>
  <div class="nav">
    <a href="?days=1">сегодня</a>
    <a href="?days=7">7 дней</a>
    <a href="?days=30">30 дней</a>
    <a href="/admin/daily_tasks/stats?days={{ d.period.days }}">JSON</a>
  </div>

  <div class="cards">
    <div class="card">
      <div class="label">Сетов всего</div>
      <div class="val">{{ d.sets.total }}</div>
    </div>
    <div class="card">
      <div class="label">% Flagged задач</div>
      <div class="val {% if d.items.flagged_pct > 20 %}warn{% elif d.items.flagged_pct < 5 %}ok{% endif %}">
        {{ d.items.flagged_pct }}%
      </div>
    </div>
    <div class="card">
      <div class="label">Средняя стоимость, $</div>
      <div class="val">{{ d.sets.avg_cost_usd if d.sets.avg_cost_usd is not none else '—' }}</div>
    </div>
    <div class="card">
      <div class="label">Всего потрачено, $</div>
      <div class="val">{{ d.sets.total_cost_usd }}</div>
    </div>
    <div class="card">
      <div class="label">Среднее время, сек</div>
      <div class="val">{{ d.jobs.avg_generation_sec if d.jobs.avg_generation_sec is not none else '—' }}</div>
    </div>
    <div class="card">
      <div class="label">P95 время, сек</div>
      <div class="val">{{ d.jobs.p95_generation_sec if d.jobs.p95_generation_sec is not none else '—' }}</div>
    </div>
    <div class="card">
      <div class="label">Accuracy учеников</div>
      <div class="val">{{ d.items.user_accuracy_pct if d.items.user_accuracy_pct is not none else '—' }}%</div>
    </div>
    <div class="card">
      <div class="label">Задач решено</div>
      <div class="val">{{ d.items.answered_count }} / {{ d.items.total }}</div>
    </div>
  </div>

  <h2>Сеты по статусам</h2>
  <table>
    <tr><th>status</th><th>count</th></tr>
    {% for k, v in d.sets.by_status.items() %}<tr><td>{{ k }}</td><td>{{ v }}</td></tr>{% endfor %}
  </table>

  <h2>Джобы по состояниям</h2>
  <table>
    <tr><th>state</th><th>count</th></tr>
    {% for k, v in d.jobs.by_state.items() %}<tr><td>{{ k }}</td><td>{{ v }}</td></tr>{% endfor %}
  </table>

  <h2>Распределение итераций Opus (сколько раз переписывали задачу)</h2>
  <table>
    <tr><th>opus_iterations</th><th>задач</th></tr>
    {% for k, v in d.items.iteration_distribution.items() %}
      <tr><td>{{ k }}</td><td>{{ v }}</td></tr>
    {% endfor %}
  </table>

  <h2>По предметам</h2>
  <table>
    <tr><th>subject</th><th>total</th><th>flagged</th><th>answered</th><th>correct</th></tr>
    {% for subj, row in d.by_subject.items() %}
      <tr>
        <td>{{ subj }}</td>
        <td>{{ row.total }}</td>
        <td>{{ row.flagged }}</td>
        <td>{{ row.answered }}</td>
        <td>{{ row.correct }}</td>
      </tr>
    {% endfor %}
  </table>

  {% if d.slowest_jobs %}
    <h2>Топ-5 самых долгих джобов</h2>
    <table>
      <tr><th>job_id</th><th>user_id</th><th>date</th><th>duration, sec</th><th>state</th></tr>
      {% for j in d.slowest_jobs %}
        <tr>
          <td>{{ j.job_id }}</td>
          <td>{{ j.user_id }}</td>
          <td>{{ j.date }}</td>
          <td>{{ j.duration_sec }}</td>
          <td>{{ j.state }}</td>
        </tr>
      {% endfor %}
    </table>
  {% endif %}
</body>
</html>"""


@admin_daily_stats_bp.route('/dashboard', methods=['GET'])
@login_required
@admin_required
def stats_dashboard():
    """Простой HTML-дашборд (inline-шаблон, без внешних зависимостей)."""
    try:
        days = int(request.args.get('days', '1'))
        days = max(1, min(days, 90))
    except (TypeError, ValueError):
        days = 1

    today = date.today()
    start = today - timedelta(days=days - 1)
    data = _stats_for_period(start, today)
    data['generated_at'] = datetime.utcnow().isoformat() + 'Z'
    return render_template_string(_DASHBOARD_HTML, d=data), 200
