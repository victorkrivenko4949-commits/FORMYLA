# -*- coding: utf-8 -*-
"""
Blueprint: Персональная подготовка к олимпиадам (/prep)

Endpoints:
  GET    /prep/                              — дашборд активных планов
  GET    /prep/new                           — данные для мастера создания
  POST   /prep/new                           — создать план
  GET    /prep/<plan_id>                     — детали плана
  GET    /prep/<plan_id>/today               — задачи на сегодня
  POST   /prep/<plan_id>/today/complete/<id> — отметить задачу решённой
  POST   /prep/<plan_id>/pause               — пауза
  POST   /prep/<plan_id>/resume              — возобновить
  DELETE /prep/<plan_id>                     — удалить план
"""

import json
import hashlib
import random
from datetime import date, datetime, timedelta

from flask import Blueprint, jsonify, request, abort, render_template, current_app, session
from flask_login import current_user, login_required

from models import db, AdaptiveTask, AdaptiveTestResult, OlympiadPrep, PrepPlan, PrepDay, TaskSolution, DailyQuest, ChatMessage
from services.prep_planner import generate_prep_plan, RADAR_TOPICS, TOPIC_NAMES_RU
from services.adaptive_topics_registry import ADAPTIVE_TOPICS_BY_GRADE, get_db_topic, get_topic_entry
from daily_tasks.profile import build_profile, ProfileBuildError, score_to_target_level
from daily_tasks.monthly_plan import subtopic_title
from services.olympiads_knowledge import build_olympiads_context, recommend_olympiads_for, get_olympiad_knowledge

# Allowed MIME types for photo upload
ALLOWED_PHOTO_MIMES = {'image/jpeg', 'image/png', 'image/webp', 'image/heic'}
MAX_PHOTO_SIZE = 5 * 1024 * 1024  # 5 MB

prep_bp = Blueprint('prep', __name__, url_prefix='/prep')


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _get_plan_or_404(plan_id):
    """Get plan and verify ownership."""
    plan = db.session.get(PrepPlan, plan_id)
    if not plan:
        abort(404, description='План не найден')
    if plan.user_id != current_user.id:
        abort(403, description='Нет доступа к этому плану')
    return plan


def _get_user_radar():
    """Build radar dict from build_profile() topics_full (7 subtopics).

    Returns dict {topic_key: pct} for the user's class subtopics,
    or falls back to empty dict if profile cannot be built.
    """
    try:
        profile = build_profile(current_user.id)
        topics_full = profile.get('topics_full', []) or []
        radar = {}
        for t in topics_full:
            key = t.get('topic_key') or t.get('topic', '')
            pct = t.get('pct', 0)
            if key:
                radar[key] = min(100, max(0, int(pct)))
        return radar
    except ProfileBuildError:
        return {}
    except Exception:
        current_app.logger.exception('_get_user_radar failed')
        return {}


def _get_user_grade():
    """Return current user's preferred grade or None."""
    return getattr(current_user, 'preferred_grade', None)


def _curator_profile():
    """Build profile dict for curator, or None on failure."""
    try:
        return build_profile(current_user.id)
    except ProfileBuildError:
        return None
    except Exception:
        current_app.logger.exception('_curator_profile failed')
        return None


def _get_radar_from_adaptive_test():
    """Get radar from the latest adaptive test result (last 30 days)."""
    from datetime import timedelta
    cutoff = datetime.utcnow() - timedelta(days=30)

    # Get latest results per topic
    results = (
        AdaptiveTestResult.query
        .filter_by(user_id=current_user.id)
        .filter(AdaptiveTestResult.started_at >= cutoff)
        .order_by(AdaptiveTestResult.started_at.desc())
        .all()
    )

    if not results:
        return None

    radar = {}
    seen_topics = set()
    for r in results:
        topic = r.topic
        if topic and topic not in seen_topics:
            seen_topics.add(topic)
            # Map final_level (1-7) to skill (0-100)
            radar[topic] = min(100, max(0, int(((r.final_level or 1) - 1) / 6 * 100)))

    # Fill missing topics with default
    for t in RADAR_TOPICS:
        if t not in radar:
            radar[t] = 0

    return radar


# ─── Error handlers ──────────────────────────────────────────────────────────

@prep_bp.errorhandler(400)
def bad_request(e):
    return jsonify(error=str(e.description)), 400


@prep_bp.errorhandler(403)
def forbidden(e):
    return jsonify(error=str(e.description)), 403


@prep_bp.errorhandler(404)
def not_found(e):
    return jsonify(error=str(e.description)), 404


@prep_bp.errorhandler(409)
def conflict(e):
    return jsonify(error=str(e.description)), 409


# ─── Routes ──────────────────────────────────────────────────────────────────

def _wants_json():
    """Check if client prefers JSON (API) over HTML."""
    return (
        request.accept_mimetypes.best == 'application/json'
        or request.content_type == 'application/json'
        or request.args.get('format') == 'json'
    )


@prep_bp.route('/')
@login_required
def dashboard():
    """Дашборд: список активных/паузированных планов."""
    active_plans = (
        PrepPlan.query
        .filter_by(user_id=current_user.id)
        .filter(PrepPlan.status.in_(['active', 'paused']))
        .order_by(PrepPlan.created_at.desc())
        .all()
    )
    completed_plans = (
        PrepPlan.query
        .filter_by(user_id=current_user.id, status='completed')
        .order_by(PrepPlan.created_at.desc())
        .limit(8)
        .all()
    )

    if _wants_json():
        return jsonify(plans=[p.to_dict() for p in active_plans])

    return render_template('prep/dashboard.html',
                           active_plans=active_plans,
                           completed_plans=completed_plans)


@prep_bp.route('/new', methods=['GET'])
@login_required
def new_plan_form():
    """Мастер создания плана."""
    olympiads = OlympiadPrep.query.filter_by(is_active=True).order_by(OlympiadPrep.sort_order).all()

    # Get user's current radar for step 3
    user_radar = _get_user_radar()
    has_radar = any(v != 50 for v in user_radar.values())

    if _wants_json():
        return jsonify(olympiads=[
            {
                'slug': o.slug,
                'name': o.name,
                'short_name': o.short_name,
                'grades': o.grades_list,
                'stages': o.stages_list,
                'color_hex': o.color_hex,
            }
            for o in olympiads
        ])

    return render_template('prep/new_wizard.html',
                           olympiads=olympiads,
                           user_radar=user_radar,
                           has_radar=has_radar,
                           topic_names=TOPIC_NAMES_RU)


@prep_bp.route('/new', methods=['POST'])
@login_required
def create_plan():
    """Создать персональный план подготовки."""
    data = request.get_json(silent=True) or {}

    olympiad_slug = data.get('olympiad_slug', '').strip()
    target_stage = data.get('target_stage', '').strip()
    target_date_str = data.get('target_date', '').strip()
    use_baseline = data.get('use_baseline', 'radar')

    # Validate required fields
    if not olympiad_slug:
        abort(400, description='Укажите олимпиаду (olympiad_slug)')
    if not target_date_str:
        abort(400, description='Укажите дату олимпиады (target_date)')

    # Parse target_date
    try:
        target_dt = date.fromisoformat(target_date_str)
    except (ValueError, TypeError):
        abort(400, description='Некорректный формат даты (YYYY-MM-DD)')

    if target_dt <= date.today():
        abort(400, description='Дата олимпиады должна быть в будущем')

    # Find olympiad
    olympiad = OlympiadPrep.query.filter_by(slug=olympiad_slug, is_active=True).first()
    if not olympiad:
        abort(404, description=f'Олимпиада «{olympiad_slug}» не найдена')

    # Check for duplicate active plan
    existing = PrepPlan.query.filter_by(
        user_id=current_user.id,
        olympiad_id=olympiad.id,
        status='active',
    ).first()
    if existing and existing.target_stage == target_stage:
        abort(409, description='Уже есть активный план для этой олимпиады и этапа')

    # Get baseline radar
    if use_baseline == 'adaptive_test':
        radar = _get_radar_from_adaptive_test()
        if not radar:
            abort(400, description='Сначала пройдите адаптивный тест (результатов за последние 30 дней нет)')
    else:
        radar = _get_user_radar()

    # Determine daily task count
    days_to_olympiad = (target_dt - date.today()).days
    daily_count = 7 if days_to_olympiad < 30 else 5

    # Generate plan
    plan = generate_prep_plan(
        user=current_user,
        olympiad=olympiad,
        target_stage_name=target_stage,
        target_date=target_dt,
        baseline_radar=radar,
        daily_task_count=daily_count,
    )

    return jsonify(
        plan_id=plan.id,
        days_total=plan.days_total,
        daily_task_count=plan.daily_task_count,
        redirect_url=f'/prep/{plan.id}',
    ), 201


@prep_bp.route('/<int:plan_id>')
@login_required
def plan_detail(plan_id):
    """Детали плана: календарь дней + радар."""
    plan = _get_plan_or_404(plan_id)

    days = (
        PrepDay.query
        .filter_by(plan_id=plan_id)
        .order_by(PrepDay.date)
        .all()
    )

    days_data = [{
        'id': d.id,
        'date': d.date.isoformat(),
        'day_num': d.date.day,
        'status': d.status,
        'topics': d.target_topics_list,
        'problem_count': d.total_problems,
        'completed_count': d.completed_count,
        'day_score': d.day_score,
        'is_variant': (d.date - plan.start_date).days % 7 == 6 and (d.date - plan.start_date).days > 0,
    } for d in days]

    # Stats
    total_solved = sum(d.completed_count for d in days)
    completed_days = sum(1 for d in days if d.status == 'completed')
    variant_days_total = sum(1 for dd in days_data if dd['is_variant'])
    variant_days_done = sum(1 for dd in days_data if dd['is_variant'] and dd['status'] == 'completed')
    avg_score = round(sum(d.day_score for d in days if d.status == 'completed') / max(completed_days, 1), 1)

    if _wants_json():
        return jsonify(plan=plan.to_dict(), days=days_data)

    return render_template('prep/plan_detail.html',
                           plan=plan,
                           days=days,
                           days_json=json.dumps(days_data, ensure_ascii=False),
                           total_solved=total_solved,
                           completed_days=completed_days,
                           variant_days_total=variant_days_total,
                           variant_days_done=variant_days_done,
                           avg_score=avg_score,
                           topic_names=TOPIC_NAMES_RU)


@prep_bp.route('/<int:plan_id>/day/<int:day_id>')
@login_required
def day_detail(plan_id, day_id):
    """JSON: задачи конкретного дня (для modal в календаре)."""
    plan = _get_plan_or_404(plan_id)
    day = db.session.get(PrepDay, day_id)
    if not day or day.plan_id != plan.id:
        abort(404, description='День не найден')

    problems = _fetch_problems_for_day(day)
    return jsonify(
        day=day.to_dict(),
        problems=problems,
    )


def _fetch_problems_for_day(day):
    """Fetch problem dicts for a PrepDay."""
    problem_ids = day.problem_ids_list
    problems = []
    if problem_ids:
        tasks = AdaptiveTask.query.filter(AdaptiveTask.id.in_(problem_ids)).all()
        tasks_map = {t.id: t for t in tasks}
        for pid in problem_ids:
            t = tasks_map.get(pid)
            if t:
                problems.append({
                    'id': t.id,
                    'topic': t.topic,
                    'difficulty': t.difficulty_level,
                    'task_text': t.task_text,
                    'correct_answer': t.correct_answer,
                    'solution': t.solution,
                })
    return problems


@prep_bp.route('/<int:plan_id>/today')
@login_required
def today_problems(plan_id):
    """Задачи на сегодня."""
    plan = _get_plan_or_404(plan_id)

    today_date = date.today()
    day = PrepDay.query.filter_by(plan_id=plan_id, date=today_date).first()

    if not day:
        abort(404, description='Нет задач на сегодня')

    problems = _fetch_problems_for_day(day)

    if _wants_json():
        return jsonify(
            day_id=day.id,
            date=day.date.isoformat(),
            topics=day.target_topics_list,
            problems=problems,
            completed_ids=day.completed_problem_ids_list,
            day_score=day.day_score,
            total=day.total_problems,
            completed_count=day.completed_count,
        )

    return render_template('prep/today.html',
                           plan=plan,
                           day=day,
                           problems=problems,
                           problems_json=json.dumps(problems, ensure_ascii=False),
                           completed_ids=day.completed_problem_ids_list,
                           topic_names=TOPIC_NAMES_RU)


@prep_bp.route('/<int:plan_id>/today/complete/<int:problem_id>', methods=['POST'])
@login_required
def complete_problem(plan_id, problem_id):
    """Отметить задачу решённой + проверить решение через DeepSeek."""
    plan = _get_plan_or_404(plan_id)

    today = date.today()
    day = PrepDay.query.filter_by(plan_id=plan_id, date=today).first()
    if not day:
        abort(404, description='Нет дня на сегодня')

    # Verify problem belongs to this day
    if problem_id not in day.problem_ids_list:
        abort(400, description='Задача не принадлежит этому дню')

    data = request.get_json(silent=True) or {}
    user_answer = data.get('user_answer', '').strip()
    user_solution = data.get('user_solution', '').strip()
    skip = data.get('skip', False)

    task = db.session.get(AdaptiveTask, problem_id)

    # ── Evaluate solution via DeepSeek ──
    is_correct = False
    feedback = {}

    if skip:
        # User skipped — mark as wrong
        is_correct = False
        feedback = {'verdict': 'skipped', 'message': 'Задача пропущена.'}
    elif 'is_correct' in data and not user_solution:
        # Legacy / simple mode: client already determined correctness
        is_correct = bool(data['is_correct'])
        feedback = {'verdict': 'correct' if is_correct else 'wrong',
                    'message': '', 'correct_answer': (task.correct_answer or '') if task else ''}
    elif user_answer or user_solution:
        is_correct, feedback = _evaluate_solution(
            task, user_answer, user_solution
        )
    else:
        is_correct = False
        feedback = {'verdict': 'empty', 'message': 'Введи ответ или решение.'}

    # Add to completed (if not already)
    completed = day.completed_problem_ids_list
    if problem_id not in completed:
        completed.append(problem_id)
        day.completed_problem_ids = json.dumps(completed)

        if is_correct:
            day.day_score = (day.day_score or 0) + 1

    # Check if day is complete
    if day.completed_count >= day.total_problems:
        day.status = 'completed'

    # Update radar: find task topic and adjust skill
    if task:
        radar = plan.current_radar_dict
        from services.adaptive_topic_mapping import get_keywords_for_grade_topic
        task_topic_lower = (task.topic or '').lower()
        grade = getattr(current_user, 'preferred_grade', 9) or 9

        matched_topic = None
        for canonical in RADAR_TOPICS:
            keywords = get_keywords_for_grade_topic(grade, canonical)
            for kw in keywords:
                if kw.lower() in task_topic_lower:
                    matched_topic = canonical
                    break
            if matched_topic:
                break

        if matched_topic:
            current_skill = radar.get(matched_topic, 50)
            if is_correct:
                radar[matched_topic] = min(100, current_skill + 2)
            else:
                radar[matched_topic] = max(0, current_skill - 1)
            plan.current_radar = json.dumps(radar, ensure_ascii=False)

    db.session.commit()

    return jsonify(
        status='ok',
        is_correct=is_correct,
        feedback=feedback,
        day_score=day.day_score,
        day_complete=day.status == 'completed',
        completed_count=day.completed_count,
        total=day.total_problems,
        radar_updated=plan.current_radar_dict,
    )


def _evaluate_solution(task, user_answer, user_solution):
    """
    Evaluate user's solution against the DB reference.
    Returns (is_correct: bool, feedback: dict).
    """
    if not task:
        return False, {'verdict': 'error', 'message': 'Задача не найдена.'}

    correct_answer = (task.correct_answer or '').strip()
    reference_solution = (task.solution or '').strip()
    task_text = (task.task_text or '').strip()

    # ── Step 1: Quick answer check (if short answer provided) ──
    if user_answer and correct_answer:
        if _answers_match(user_answer, correct_answer):
            return True, {
                'verdict': 'correct',
                'message': 'Верно! Ответ совпадает.',
                'correct_answer': correct_answer,
            }

    # ── Step 2: If user provided a full solution, evaluate via DeepSeek ──
    solution_text = user_solution or user_answer
    if not solution_text:
        return False, {'verdict': 'empty', 'message': 'Введи ответ или решение.'}

    # If only short answer and it didn't match — try DeepSeek for equivalence
    try:
        from ai.deepseek_client import DeepSeekClient
        client = DeepSeekClient()

        prompt = f"""Ты — строгий проверяющий олимпиадных работ по математике.

УСЛОВИЕ ЗАДАЧИ:
{task_text[:1500]}

ПРАВИЛЬНЫЙ ОТВЕТ: {correct_answer}

ЭТАЛОННОЕ РЕШЕНИЕ:
{reference_solution[:2000]}

РЕШЕНИЕ УЧЕНИКА:
{solution_text[:2000]}

Оцени решение ученика. Ответь СТРОГО в формате JSON:
{{
  "is_correct": true/false,
  "score": 0-2,
  "errors": ["список ошибок, если есть"],
  "feedback": "краткий комментарий (1-3 предложения): что верно, что нет, как исправить",
  "hint": "подсказка, если решение неверное (1 предложение)",
  "solution": "ПОЛНОЕ пошаговое решение задачи (на русском, с LaTeX-формулами в $...$). Если эталонное решение дано — перепиши его своими словами. Если эталонного решения нет — составь полное решение сам. Обязательно покажи все шаги."
}}

Правила оценки:
- 2 балла: полностью верное решение (ответ правильный, логика верная)
- 1 балл: частично верное (правильный ход мысли, но ошибка в вычислениях или неполное обоснование)
- 0 баллов: неверное решение или ответ"""

        import re as _re
        raw = client.generate(prompt, max_tokens=500, temperature=0.1)
        # Parse JSON from response
        raw = _re.sub(r'```json\s*', '', raw)
        raw = _re.sub(r'```\s*', '', raw).strip()
        result = json.loads(raw)

        is_correct = bool(result.get('is_correct', False))
        score = int(result.get('score', 0))
        if score >= 2:
            is_correct = True

        return is_correct, {
            'verdict': 'correct' if is_correct else ('partial' if score == 1 else 'wrong'),
            'score': score,
            'message': result.get('feedback', ''),
            'errors': result.get('errors', []),
            'hint': result.get('hint', ''),
            'correct_answer': correct_answer,
            'solution': result.get('solution', ''),
            'ai_checked': True,
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        # Fallback: simple answer comparison
        if user_answer and correct_answer:
            matched = _answers_match(user_answer, correct_answer)
            return matched, {
                'verdict': 'correct' if matched else 'wrong',
                'message': 'Проверено по ответу (AI недоступен).',
                'correct_answer': correct_answer,
            }
        return False, {
            'verdict': 'error',
            'message': 'Не удалось проверить решение. Попробуй позже.',
        }


def _answers_match(user_ans, correct_ans):
    """Compare answers with normalization."""
    import re as _re

    def normalize(s):
        s = s.strip().lower()
        s = _re.sub(r'[\\${}]', '', s)  # strip LaTeX
        s = s.replace(',', '.').replace(' ', '')
        s = _re.sub(r'\.0+$', '', s)  # trailing zeros
        return s

    u = normalize(user_ans)
    c = normalize(correct_ans)
    if u == c:
        return True

    # Try numeric comparison
    try:
        return abs(float(u) - float(c)) < 1e-6
    except (ValueError, TypeError):
        pass

    return False


@prep_bp.route('/<int:plan_id>/pause', methods=['POST'])
@login_required
def pause_plan(plan_id):
    """Поставить план на паузу."""
    plan = _get_plan_or_404(plan_id)
    if plan.status != 'active':
        abort(400, description='Можно поставить на паузу только активный план')
    plan.status = 'paused'
    db.session.commit()
    return jsonify(status='paused', plan_id=plan.id)


@prep_bp.route('/<int:plan_id>/resume', methods=['POST'])
@login_required
def resume_plan(plan_id):
    """Возобновить план."""
    plan = _get_plan_or_404(plan_id)
    if plan.status != 'paused':
        abort(400, description='Можно возобновить только план на паузе')
    if plan.target_date and plan.target_date < date.today():
        abort(400, description='Дата олимпиады уже прошла — план нельзя возобновить')
    plan.status = 'active'
    db.session.commit()
    return jsonify(status='active', plan_id=plan.id)


@prep_bp.route('/<int:plan_id>', methods=['DELETE'])
@login_required
def delete_plan(plan_id):
    """Удалить план (каскадно удаляет все PrepDay)."""
    plan = _get_plan_or_404(plan_id)
    db.session.delete(plan)
    db.session.commit()
    return '', 204


@prep_bp.route('/<int:plan_id>/today/upload_photo/<int:problem_id>', methods=['POST'])
@login_required
def upload_solution_photo(plan_id, problem_id):
    """Upload handwritten solution photo with security checks."""
    plan = _get_plan_or_404(plan_id)
    today = date.today()
    day = PrepDay.query.filter_by(plan_id=plan_id, date=today).first()
    if not day:
        abort(404, description='No day for today')
    if problem_id not in day.problem_ids_list:
        abort(400, description='Problem not in today')

    if 'photo' not in request.files:
        return jsonify(error='No photo file'), 400
    photo_file = request.files['photo']
    if not photo_file.filename:
        return jsonify(error='Empty filename'), 400

    photo_bytes = photo_file.read()
    if len(photo_bytes) > MAX_PHOTO_SIZE:
        return jsonify(error='File too large. Max 5MB'), 413
    if len(photo_bytes) == 0:
        return jsonify(error='Empty file'), 400

    content_type = photo_file.content_type or 'application/octet-stream'
    if content_type not in ALLOWED_PHOTO_MIMES:
        return jsonify(error='Unsupported format. Use JPEG/PNG/WebP/HEIC'), 415

    if content_type == 'image/heic':
        photo_bytes, content_type = _convert_heic_to_jpeg(photo_bytes)

    from services.storage import compute_photo_hash, dedupe_check, upload_photo
    photo_hash = compute_photo_hash(photo_bytes)
    if dedupe_check(photo_hash):
        return jsonify(error='Duplicate photo', photo_hash=photo_hash), 409

    url, _ = upload_photo(photo_bytes, current_user.id, content_type)

    consent = getattr(current_user, 'ml_training_consent', False)
    sol = TaskSolution(
        user_id=current_user.id,
        task_id=problem_id,
        original_photo_url=url,
        photo_hash=photo_hash,
        consent_for_training=consent,
        plan_id=plan_id,
        day_id=day.id,
    )
    db.session.add(sol)

    from services.ml_quality import update_quality_score
    update_quality_score(sol, photo_bytes)

    db.session.commit()
    return jsonify(
        status='ok',
        solution_id=sol.id,
        photo_url=url,
        photo_hash=photo_hash,
        quality_score=sol.quality_score,
    )


def _convert_heic_to_jpeg(photo_bytes):
    """Convert HEIC image bytes to JPEG."""
    try:
        import pillow_heif
        from PIL import Image
        import io
        heif = pillow_heif.read_heif(photo_bytes)
        img = Image.frombytes(heif.mode, heif.size, heif.data, 'raw')
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=90)
        return buf.getvalue(), 'image/jpeg'
    except ImportError:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(photo_bytes))
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=90)
        return buf.getvalue(), 'image/jpeg'


# ─── Куратор подготовки: подтемы, приветствие, чат с ИИ ────────────────────

def _build_subtopic_ctx(profile):
    """Build (radar_dict, topic_names_dict, weak_keys, subtopics_to_test)
    from a profile dict containing 'topics_full'.

    Returns dict with keys: radar, topic_names, weak_keys, subtopics_to_test, test_done.
    Returns empty-data dict if profile is None or has no topics_full.
    """
    if not profile:
        return {'radar': {}, 'topic_names': {}, 'weak_keys': [],
                'subtopics_to_test': [], 'test_done': False}

    topics_full = profile.get('topics_full', []) or []
    radar = {}
    topic_names = {}
    subtopics_to_test = []
    for t in topics_full:
        key = t.get('topic_key') or t.get('topic', '')
        pct_raw = t.get('pct')
        pct = pct_raw if pct_raw is not None else 0
        measured = t.get('measured', False)
        name = t.get('topic_name') or t.get('topic', key)
        if key:
            radar[key] = min(100, max(0, int(pct)))
            topic_names[key] = name
            if not measured:
                subtopics_to_test.append({'key': key, 'name': name})

    # Weak = lowest pct among measured topics
    measured_radar = {k: v for k, v in radar.items()
                      if any(t.get('measured') and (t.get('topic_key') or t.get('topic')) == k
                             for t in topics_full)}
    weak_keys = [k for k, _ in sorted(measured_radar.items(), key=lambda kv: kv[1])[:3]]
    test_done = profile.get('measured_topics_count', 0) > 0

    return {
        'radar': radar,
        'topic_names': topic_names,
        'weak_keys': weak_keys,
        'subtopics_to_test': subtopics_to_test,
        'test_done': test_done,
    }


# ─── Content hooks (C6) ────────────────────────────────────────────────────

def get_onboarding_tasks(grade, limit=12):
    """Подобрать задачи для онбординга (первый тест, без профиля).

    Берёт задачи класса на уровне CALIBRATION_START_LEVEL (2) с запасом.
    Если задач уровня 2 недостаточно — падает на уровень 1.
    Возвращает список словарей с ключами: id, task_text, topic, difficulty_level.
    task_text нормализуется через normalize_math_text для KaTeX-совместимости.
    """
    from daily_tasks.profile import CALIBRATION_START_LEVEL
    try:
        grade_int = int(grade)
    except (TypeError, ValueError):
        return []
    try:
        tasks = (
            AdaptiveTask.query
            .filter_by(class_level=grade_int, difficulty_level=CALIBRATION_START_LEVEL)
            .filter(AdaptiveTask.is_flagged.is_(False))
            .order_by(db.func.random())
            .limit(limit)
            .all()
        )
        if len(tasks) < limit // 2 and CALIBRATION_START_LEVEL > 1:
            # Fallback: level 1
            tasks = (
                AdaptiveTask.query
                .filter_by(class_level=grade_int, difficulty_level=CALIBRATION_START_LEVEL - 1)
                .filter(AdaptiveTask.is_flagged.is_(False))
                .order_by(db.func.random())
                .limit(limit)
                .all()
            )
        if not tasks:
            # Ultimate fallback: any difficulty level
            current_app.logger.warning(
                'get_onboarding_tasks: no tasks found for grade=%s at levels %s-%s, trying any level',
                grade_int, CALIBRATION_START_LEVEL - 1, CALIBRATION_START_LEVEL
            )
            tasks = (
                AdaptiveTask.query
                .filter_by(class_level=grade_int)
                .filter(AdaptiveTask.is_flagged.is_(False))
                .order_by(db.func.random())
                .limit(limit)
                .all()
            )
        if not tasks:
            current_app.logger.error(
                'get_onboarding_tasks: completely empty for grade=%s (no AdaptiveTask records at all)',
                grade_int
            )
        from services.math_text_normalizer import normalize_math_text
        return [
            {'id': t.id, 'task_text': normalize_math_text(t.task_text) if t.task_text else t.task_text,
             'topic': t.topic, 'difficulty_level': t.difficulty_level}
            for t in tasks
        ]
    except Exception:
        current_app.logger.exception('get_onboarding_tasks failed')
        return []


def get_subtopic_test(grade, subtopic_key, count=5):
    """Подобрать задачи для теста по подтеме дня.

    Использует registry для маппинга (grade, subtopic_key) → db_topic.
    Берёт задачи на уровне [CALIBRATION_START_LEVEL, CALIBRATION_START_LEVEL+1].
    Если db_topic не найден — пытается найти LIKE-совпадение по topic.
    """
    from daily_tasks.profile import CALIBRATION_START_LEVEL
    try:
        grade_int = int(grade)
    except (TypeError, ValueError):
        return []
    try:
        db_topic = get_db_topic(grade_int, subtopic_key)
        if not db_topic:
            # Fallback: ищем по ключевому слову в topic
            topic_entry = get_topic_entry(grade_int, subtopic_key)
            keyword = topic_entry['name'] if topic_entry else subtopic_key
            tasks = (
                AdaptiveTask.query
                .filter_by(class_level=grade_int)
                .filter(AdaptiveTask.topic.ilike(f'%{keyword}%'))
                .filter(AdaptiveTask.difficulty_level.between(
                    CALIBRATION_START_LEVEL, CALIBRATION_START_LEVEL + 1))
                .filter(AdaptiveTask.is_flagged.is_(False))
                .order_by(db.func.random())
                .limit(count)
                .all()
            )
        else:
            tasks = (
                AdaptiveTask.query
                .filter_by(class_level=grade_int, topic=db_topic)
                .filter(AdaptiveTask.difficulty_level.between(
                    CALIBRATION_START_LEVEL, CALIBRATION_START_LEVEL + 1))
                .filter(AdaptiveTask.is_flagged.is_(False))
                .order_by(db.func.random())
                .limit(count)
                .all()
            )
        # Fallback: если не найдено — просто tasks уровня CALIBRATION_START_LEVEL
        if not tasks:
            tasks = (
                AdaptiveTask.query
                .filter_by(class_level=grade_int, difficulty_level=CALIBRATION_START_LEVEL)
                .filter(AdaptiveTask.is_flagged.is_(False))
                .order_by(db.func.random())
                .limit(count)
                .all()
            )
        return [
            {'id': t.id, 'task_text': t.task_text,
             'topic': t.topic, 'difficulty_level': t.difficulty_level}
            for t in tasks
        ]
    except Exception:
        current_app.logger.exception('get_subtopic_test failed')
        return []


# ─── Страница куратора ─────────────────────────────────────────────────────

@prep_bp.route('/coach')
@login_required
def coach():
    """Страница Куратора: радар по 7 выбранным куратором подтемам + чат с ИИ-агентом."""
    profile = _curator_profile()
    ctx = _build_subtopic_ctx(profile)

    # ── Вычислить overall_level из профиля для отображения в шапке ──
    overall_level = None
    level_label = ''
    if profile:
        measured = [t for t in (profile.get('topics_full') or []) if t.get('measured')]
        if measured:
            # Средний target_level по измеренным темам (шкала 1..8)
            avg_target = sum(t.get('target_level') or 0 for t in measured) / len(measured)
            overall_level = round(avg_target)
            # Маппинг в сжатую шкалу 1..5 для отображения
            if avg_target <= 2:
                display_level = 1
            elif avg_target <= 4:
                display_level = 2
            elif avg_target <= 6:
                display_level = 3
            elif avg_target <= 7:
                display_level = 4
            else:
                display_level = 5
            level_labels = {1: '🔵 Начальный', 2: '🟢 Базовый', 3: '🟡 Средний',
                            4: '🟠 Продвинутый', 5: '🔴 Высокий'}
            level_label = f'{level_labels.get(display_level, "🟡 Средний")} (уровень {display_level}/5)'
        # Также пробуем взять из анкеты (наивысший приоритет)
        if overall_level is None:
            try:
                from services.questionnaire_storage import get_questionnaire_level
                q_level = get_questionnaire_level(current_user.id)
                if q_level is not None:
                    overall_level = q_level
                    level_labels = {1: '🔵 Начальный', 2: '🟢 Базовый', 3: '🟡 Средний',
                                    4: '🟠 Продвинутый', 5: '🔴 Высокий'}
                    level_label = f'{level_labels.get(min(q_level, 5), "🟡 Средний")} (уровень {min(q_level, 5)}/5)'
            except Exception:
                pass
        # Затем пробуем взять из CuratorState.prep_state.level (monthly cycle)
        if overall_level is None:
            try:
                from models_curator import CuratorState as _CS2
                _cs2 = _CS2.query.filter_by(user_id=current_user.id).first()
                if _cs2 and _cs2.prep_state and _cs2.prep_state.get('level'):
                    prep_lvl = _cs2.prep_state['level']
                    overall_level = prep_lvl
                    level_labels = {1: '🔵 Начальный', 2: '🟢 Базовый', 3: '🟡 Средний',
                                    4: '🟠 Продвинутый', 5: '🔴 Высокий'}
                    level_label = f'{level_labels.get(min(prep_lvl, 5), "🟡 Средний")} (уровень {min(prep_lvl, 5)}/5)'
            except Exception:
                pass

    # ── Build mastery_list from TopicMastery + ADAPTIVE_TOPICS_BY_GRADE ──
    from models import TopicMastery
    from services.adaptive_topics_registry import ADAPTIVE_TOPICS_BY_GRADE
    from models_curator import CuratorState as _CS
    from daily_tasks.monthly_plan import current_month_index as _curr_month_idx

    _user_grade = (
        getattr(current_user, 'preferred_grade', None)
        or getattr(current_user, 'class_level', None)
        or getattr(current_user, 'grade', None)
    )
    try:
        _user_grade_int = int(_user_grade) if _user_grade is not None else None
    except (TypeError, ValueError):
        _user_grade_int = None

    _legacy_topic_meta = [
        ('algebra',        'Алгебра'),
        ('geometry',       'Геометрия'),
        ('combinatorics',  'Комбинаторика'),
        ('number_theory',  'Теория чисел'),
        ('kl_movement',    'Задачи на движение'),
        ('knights_liars',  'Рыцари и лжецы'),
    ]

    # ── Try to get 7 curator-selected subtopics from CuratorState.prep_plan ──
    _selected_db_topics = None
    _cs = _CS.query.filter_by(user_id=current_user.id).first()
    if _cs and _cs.prep_plan:
        _months = _cs.prep_plan.get('months', [])
        if _months:
            # Динамически выбираем месяц по календарю (не hardcoded months[0])
            _month_idx_1based = _curr_month_idx(_cs.prep_plan)
            _month_idx_0based = max(0, _month_idx_1based - 1)
            if _month_idx_0based < len(_months):
                _selected_db_topics = _months[_month_idx_0based].get('subtopics', [])
            else:
                _selected_db_topics = _months[0].get('subtopics', [])

    topics_def = []
    if _selected_db_topics:
        # ── Only the 7 curator-selected subtopics (радар показывает именно их) ──
        for _db_topic in _selected_db_topics:
            _db_topic_str = str(_db_topic)
            _entry = None
            if _user_grade_int in ADAPTIVE_TOPICS_BY_GRADE:
                _entry = next(
                    (t for t in ADAPTIVE_TOPICS_BY_GRADE[_user_grade_int]
                     if t.get('db_topic') == _db_topic_str),
                    None
                )
            if _entry:
                topics_def.append({
                    'key': _entry['key'],
                    'name_ru': _entry['name'],
                    'match_keys': [_entry['key'], _db_topic_str] + (_entry.get('aliases', []) or []),
                })
            else:
                topics_def.append({
                    'key': _db_topic_str,
                    'name_ru': _db_topic_str,
                    'match_keys': [_db_topic_str],
                })
    elif _user_grade_int in ADAPTIVE_TOPICS_BY_GRADE:
        # ── Fallback: all grade topics ──
        for t in ADAPTIVE_TOPICS_BY_GRADE[_user_grade_int]:
            match_keys = [t['key']]
            if t.get('db_topic'):
                match_keys.append(t['db_topic'])
            match_keys.extend(t.get('aliases', []) or [])
            topics_def.append({
                'key': t['key'],
                'name_ru': t['name'],
                'match_keys': match_keys,
            })
    else:
        # ── Legacy topics for grades 5-6 ──
        for key, name_ru in _legacy_topic_meta:
            topics_def.append({
                'key': key,
                'name_ru': name_ru,
                'match_keys': [key],
            })

    mastery_rows = TopicMastery.query.filter_by(user_id=current_user.id).all()
    mastery_by_topic = {row.topic: row for row in mastery_rows}

    mastery_list = []
    for td in topics_def:
        row = None
        for mk in td['match_keys']:
            row = mastery_by_topic.get(mk)
            if row is not None:
                break
        mastery_val = round(row.mastery, 3) if row is not None else 0.0
        mastery_list.append({
            'name': td['name_ru'],
            'value': mastery_val,
        })

    import json as _json_coach
    # Нормализуем mastery_val (0.0-1.0 → 0-5) для radar chart
    for _m in mastery_list:
        _m['value'] = round(_m['value'] * 5, 1)
    mastery_list_json = _json_coach.dumps(mastery_list, ensure_ascii=False)

    _grade_val = _user_grade_int if _user_grade_int else ''
    return render_template('prep/coach.html',
                           radar=ctx['radar'],
                           topic_names=ctx['topic_names'],
                           test_done=ctx['test_done'],
                           subtopics_to_test=ctx['subtopics_to_test'],
                           mastery_list=mastery_list,
                           mastery_list_json=mastery_list_json,
                           user_grade=_grade_val,
                           overall_level=overall_level,
                           level_label=level_label)


# ─── Приветствие / определение сценария (C4 + C7) ─────────────────────────

@prep_bp.route('/coach/greeting')
@login_required
def coach_greeting():
    """JSON-приветствие: 6+4 сценариев по состоянию пользователя.

    Основные сценарии (C7):
      1. need_grade            — класс не выбран
      2. onboarding_test       — класс есть, но профиль пуст (0 измеренных тем)
      3. daily_test            — нет квеста сегодня, профиль есть (предложить тест по подтеме)
      4. daily_tasks_ready     — квест сегодня есть, но не завершён
      5. day_summary           — квест сегодня завершён
      6. recommend_olympiad    — флаг, добавляется к day_summary/daily_test при слабых темах

    Сценарии monthly prep cycle (C8–C11), проверяются перед daily_test:
      7. prep_morning_test     — тестовый день (1-7), тест не пройден
      8. prep_test_taken       — тестовый день, тест уже пройден
      9. prep_tasks_ready      — тренировочный день (8-30), задачи готовы
     10. prep_task_day         — тренировочный день, задачи ещё не готовы
    """
    grade = _get_user_grade()

    # ── Query-param actions ───────────────────────────────────────────
    action = request.args.get('action')
    if action == 'onboarding_tasks':
        limit = request.args.get('limit', 21, type=int)
        tasks = get_onboarding_tasks(grade, limit=limit)
        return jsonify(tasks=tasks)

    if action == 'prep_test_tasks':
        """Вернуть 5 задач для утреннего теста в monthly prep cycle."""
        from curator.monthly_cycle import get_morning_test
        test_data = get_morning_test(current_user.id)
        if test_data.get('is_test_day'):
            return jsonify(
                tasks=test_data.get('tasks', []),
                subtopic=test_data.get('subtopic'),
                subtopic_title=test_data.get('subtopic_title'),
            )
        return jsonify(tasks=[], subtopic=None)

    if action == 'subtopic_test':
        """Вернуть 5 задач для теста по конкретной подтеме (daily_test)."""
        subtopic_key = request.args.get('subtopic_key', '')
        tasks = get_subtopic_test(grade, subtopic_key, count=5)
        return jsonify(tasks=tasks)

    if not grade:
        return jsonify(
            greeting='👋 Привет! Я твой ИИ-куратор FORMYLA. Для начала выбери свой класс, '
                     'чтобы я мог построить радар твоих подтем.',
            scenario='need_grade',
            recommended_olympiad=None,
            subtopics_to_test=[],
            cta_url='/profile',
            cta_text='🎯 Выбрать класс',
        )

    # ── coach_greeting SAFETY NET: wrap main logic in try/except ─────
    try:
        profile = _curator_profile()
        ctx = _build_subtopic_ctx(profile)
        test_done = ctx['test_done']
        measured_count = profile.get('measured_topics_count', 0) if profile else 0

        # ── Сценарий 2a: онбординг уже запущен ──────────────────────────────
        existing_test = session.get('coach_test')
        if existing_test and existing_test.get('active'):
            task_ids = existing_test.get('task_ids', [])
            idx = existing_test.get('current_index', 0)
            total = len(task_ids)
            greeting = (
                f'🧪 <strong>Диагностика уже запущена!</strong> '
                f'Ты на задаче {idx + 1} из {total}. '
                f'Просто напиши ответ в чат, чтобы продолжить.'
            )
            return jsonify(
                greeting=greeting,
                scenario='test_in_progress',
                recommended_olympiad=None,
                subtopics_to_test=[],
                cta_url=None,
                cta_text=None,
            )

        # ── Проверка анкеты (приоритетнее диагностики) ─────────────────────
        questionnaire_done = False
        questionnaire_level = None
        try:
            from services.questionnaire_storage import get_questionnaire_level
            q_level = get_questionnaire_level(current_user.id)
            if q_level is not None:
                questionnaire_done = True
                questionnaire_level = q_level
        except Exception:
            pass

        # ── Сценарий 2: онбординг ────────────────────────────────────────────
        if measured_count == 0:
            if questionnaire_done:
                # Анкета пройдена — уровень известен, предлагаем тест по темам
                level_labels = {1: '🔵 Начальный', 2: '🟢 Базовый', 3: '🟡 Средний',
                                4: '🟠 Продвинутый', 5: '🔴 Высокий'}
                label = level_labels.get(questionnaire_level, '🟡 Средний')
                return jsonify(
                    greeting=f'📋 Анкета пройдена! Твой уровень: <strong>{label} (уровень {questionnaire_level}/5)</strong>.\n\n'
                             f'Теперь пройди адаптивный тест по темам — он настроен под твой уровень.',
                    scenario='open_url',
                    recommended_olympiad=None,
                    subtopics_to_test=[],
                    cta_url='/olympiad-test',
                    cta_text='🎯 Пройти тест по темам',
                )
            else:
                # Анкета не пройдена — предлагаем пройти (не 21 задачу!)
                return jsonify(
                    greeting='Чтобы я мог оценить твой уровень и подобрать задачи, пройди короткий тест по темам! Это займёт 5-10 минут.',
                    scenario='open_url',
                    recommended_olympiad=None,
                    subtopics_to_test=[],
                    cta_url='/olympiad-test',
                    cta_text='🎯 Пройти тест по темам',
                )

        # ── Проверка DailyQuest на сегодня ──────────────────────────────────
        today = date.today()
        daily_quest = DailyQuest.query.filter_by(
            user_id=current_user.id, date=today
        ).first()

        # ── Сценарий 4: задачи дня в процессе ──────────────────────────────
        if daily_quest and daily_quest.completed_at is None:
            remaining = daily_quest.total_count - daily_quest.completed_count
            greeting = (
                f'👋 С возвращением! У тебя осталось **{remaining} из {daily_quest.total_count}** задач '
                f'на сегодня. Продолжай в том же духе! 💪'
            )
            return jsonify(
                greeting=greeting,
                scenario='daily_tasks_ready',
                recommended_olympiad=None,
                subtopics_to_test=[],
                cta_url=None,
                cta_text='📝 Продолжить задачи дня',
            )

        # ── Сценарий 5: день завершён ──────────────────────────────────────
        if daily_quest and daily_quest.completed_at is not None:
            # Определяем слабые подтемы для рекомендации
            weak_keys = ctx['weak_keys']
            weak_names = ', '.join(ctx['topic_names'].get(k, k) for k in weak_keys[:3]) if weak_keys else ''
            day_result = f'{daily_quest.completed_count}/{daily_quest.total_count}'
            greeting = (
                f'🎉 Отлично! Ты завершил день — {day_result}. '
                f'Завтра будет новая подтема. Отдохни и набирайся сил!'
            )
            if weak_names:
                greeting += f'\n\nОбрати внимание на: **{weak_names}** — стоит подтянуть.'

            # Рекомендуем олимпиаду если есть слабые темы
            recommended = None
            try:
                recommended_slugs = recommend_olympiads_for(
                    grade, [t.get('topic_key') or t.get('topic', '') for t in (profile.get('weak_topics') or [])]
                )
                if recommended_slugs:
                    olymp = OlympiadPrep.query.filter_by(
                        slug=recommended_slugs[0], is_active=True
                    ).first()
                    if olymp:
                        recommended = {'slug': olymp.slug, 'name': olymp.name, 'short_name': olymp.short_name}
            except Exception:
                pass

            return jsonify(
                greeting=greeting,
                scenario='day_summary',
                recommended_olympiad=recommended,
                subtopics_to_test=ctx['subtopics_to_test'],
                cta_url='/prep/new' if recommended else None,
                cta_text='📋 Создать план подготовки' if recommended else None,
                day_result=day_result,
            )

        # ── Сценарий 3a: monthly prep cycle — тестовый день ──────────────────
        # Проверяем, есть ли у пользователя активный monthly prep plan
        try:
            _prep_info = None
            _has_prep = False
            # lazy import to avoid circular dependencies
            from curator.monthly_cycle import get_today_info as _get_prep_info
            _prep_info = _get_prep_info(current_user.id)
            if _prep_info and _prep_info.get("subtopic"):
                _has_prep = True
        except Exception:
            _prep_info = None
            _has_prep = False

        if _has_prep:
            _cycle_day = _prep_info.get("cycle_day", 0)
            _is_test_day = _prep_info.get("is_test_day", False)
            _tested = _prep_info.get("tested", False)
            _has_tasks = _prep_info.get("has_tasks", False)
            _subtopic_title = _prep_info.get("subtopic_title", _prep_info.get("subtopic", ""))
            _level = _prep_info.get("level", 2)
            _remaining_tests = max(0, 7 - len(_prep_info.get("tested_subtopics", [])))
            _cycle_progress = f"День {_cycle_day}/28"

            # Сценарий 3a.0: Месяц завершён — показать следующие подтемы
            _month_completed = _prep_info.get("month_completed", False)
            if _month_completed:
                _next_subs = _prep_info.get("next_month_subtopics", [])
                try:
                    _next_names = ', '.join(
                        subtopic_title(s) for s in _next_subs[:7]
                    ) if _next_subs else 'следующие подтемы'
                except Exception:
                    _next_names = 'следующие подтемы'
                greeting = (
                    f'🎉 <strong>Прошёл месяц!</strong> Поздравляю с завершением '
                    f'очередного этапа подготовки!\n\n'
                    f'Вот твои следующие подтемы, над которыми будем работать:\n'
                    f'<strong>{_next_names}</strong>\n\n'
                    f'Готов начать новый месяц? 🚀'
                )
                return jsonify(
                    greeting=greeting,
                    scenario='prep_month_complete',
                    recommended_olympiad=None,
                    prep_info={
                        'cycle_day': _cycle_day,
                        'month_completed': True,
                        'next_month_subtopics': _next_subs,
                        'subtopic': _prep_info.get('subtopic'),
                    },
                    cta_url='/coach',
                    cta_text='🚀 Начать новый месяц',
                )

            if _is_test_day and not _tested:
                # Сценарий 3a.1: Утренний тест — "7 дней чтобы пройти 7 тестов"
                greeting = (
                    f'🌅 Доброе утро! У тебя **7 дней, чтобы пройти 7 тестов** — '
                    f'по одному на каждую подтему.\n\n'
                    f'Сегодня **тестовый день** ({_cycle_progress}).\n\n'
                    f'Тема дня: **«{_subtopic_title}»**.\n'
                    f'Пройди тест из 5 задач — это займёт 5–10 минут. '
                    f'По результатам я подберу задачи дня под твой уровень.\n\n'
                    f'Осталось пройти тестов: **{_remaining_tests}**. 💪'
                )
                return jsonify(
                    greeting=greeting,
                    scenario='prep_morning_test',
                    recommended_olympiad=None,
                    prep_info={
                        'cycle_day': _cycle_day,
                        'subtopic': _prep_info.get('subtopic'),
                        'subtopic_title': _subtopic_title,
                        'is_test_day': True,
                        'tested': False,
                        'remaining_tests': _remaining_tests,
                        'level': _level,
                    },
                    cta_url='/coach',
                    cta_text='🧪 Начать тест',
                )

            elif _is_test_day and _tested:
                # Сценарий 3a.2: Тест пройден, ждём задачи
                greeting = (
                    f'✅ Отлично! Ты уже прошёл тест по теме **«{_subtopic_title}»** сегодня.\n\n'
    f'Задачи дня уже готовятся под твой уровень (сложность {_level}/5). '
                    f'Они придут вечером — проверь уведомления!\n\n'
                    f'{_cycle_progress}. Осталось тестов: **{_remaining_tests}** из 7. 💪'
                )
                return jsonify(
                    greeting=greeting,
                    scenario='prep_test_taken',
                    recommended_olympiad=None,
                    prep_info={
                        'cycle_day': _cycle_day,
                        'subtopic': _prep_info.get('subtopic'),
                        'subtopic_title': _subtopic_title,
                        'is_test_day': True,
                        'tested': True,
                        'remaining_tests': _remaining_tests,
                        'level': _level,
                    },
                    cta_url='/daily-set',
                    cta_text='📚 Перейти к задачам дня' if _has_tasks else None,
                )

            elif not _is_test_day:
                if _has_tasks:
                    # Сценарий 3a.3: Task-only день, задачи уже готовы
                    greeting = (
                        f'📚 Сегодня **тренировочный день** ({_cycle_progress}).\n\n'
                        f'Тема: **«{_subtopic_title}»**.\n'
                        f'Задачи дня уже готовы — продолжай тренироваться! 💪\n\n'
                        f'Уровень сложности: {_level}/5.'
                    )
                    return jsonify(
                        greeting=greeting,
                        scenario='prep_tasks_ready',
                        recommended_olympiad=None,
                        prep_info={
                            'cycle_day': _cycle_day,
                            'subtopic': _prep_info.get('subtopic'),
                            'subtopic_title': _subtopic_title,
                            'is_test_day': False,
                            'has_tasks': True,
                            'level': _level,
                        },
                        cta_url='/daily-set',
                        cta_text='📚 Перейти к задачам дня',
                    )
                else:
                    # Сценарий 3a.4: Task-only день, задачи ещё не готовы
                    greeting = (
                        f'🌅 Доброе утро! Сегодня **тренировочный день** ({_cycle_progress}).\n\n'
                        f'Тема недели: **«{_subtopic_title}»**.\n'
                        f'Задачи придут вечером — настроим их под твой уровень ({_level}/5).\n\n'
                        f'А пока можешь повторить теорию или решить несколько задач для разминки! 📖'
                    )
                    return jsonify(
                        greeting=greeting,
                        scenario='prep_task_day',
                        recommended_olympiad=None,
                        prep_info={
                            'cycle_day': _cycle_day,
                            'subtopic': _prep_info.get('subtopic'),
                            'subtopic_title': _subtopic_title,
                            'is_test_day': False,
                            'has_tasks': False,
                            'level': _level,
                        },
                        cta_url=None,
                        cta_text='📖 Повторить теорию',
                    )

        # ── Сценарий 3b: daily_test — предложить тест по приоритетной подтеме ─
        # Нет квеста сегодня, но профиль есть
        priority_subtopic = None
        if ctx.get('subtopics_to_test'):
            priority_subtopic = ctx['subtopics_to_test'][0]
        elif ctx['weak_keys']:
            priority_subtopic = {'key': ctx['weak_keys'][0], 'name': ctx['topic_names'].get(ctx['weak_keys'][0], ctx['weak_keys'][0])}

        subtopic_name = priority_subtopic['name'] if priority_subtopic else 'математике'
        greeting = (
            f'👋 Привет! Ты в {grade}-м классе. Готов позаниматься? '
            f'Предлагаю начать с темы **«{subtopic_name}»** — '
            f'реши несколько задач, и я подберу задачи дня под твой уровень.'
        )

        return jsonify(
            greeting=greeting,
            scenario='daily_test',
            recommended_olympiad=None,
            subtopics_to_test=ctx['subtopics_to_test'],
            priority_subtopic=priority_subtopic,
            cta_url=None,
            cta_text='🧪 Пройти тест по теме',
        )
    except Exception as _greeting_err:
        current_app.logger.exception('coach_greeting safety net caught error')
        return jsonify(
            greeting='👋 Привет! Я твой ИИ-куратор FORMYLA. Задай мне вопрос!',
            scenario='fallback',
            recommended_olympiad=None,
            subtopics_to_test=[],
            cta_url=None,
            cta_text=None,
        )

# ─── Онбординг: inline-тест в чате ────────────────────────────────────────


@prep_bp.route('/coach/test/start', methods=['POST'])
@login_required
def coach_test_start():
    """Начать онбординг-диагностику прямо в чате.

    Сохраняет список задач в сессии, возвращает первую задачу
    как сообщение бота. Последующие ответы обрабатываются через
    coach_chat (тест-режим).
    """
    # ── Guard: test already in progress ──────────────────────────────────
    existing = session.get('coach_test')
    if existing and existing.get('active'):
        task_ids = existing.get('task_ids', [])
        current_index = existing.get('current_index', 0)
        if current_index < len(task_ids):
            # Return current task instead of restarting
            current_task_id = task_ids[current_index]
            task = AdaptiveTask.query.get(current_task_id)
            if task:
                from services.math_text_normalizer import normalize_math_text
                task_text = normalize_math_text(task.task_text) if task.task_text else task.task_text
                total = len(task_ids)
                num = current_index + 1
                reply = (
                    f"🧪 <strong>Диагностика уже запущена!</strong>\n\n"
                    f"<hr>\n"
                    f"<strong>Задача {num} из {total}:</strong><br>"
                    f"{task_text}\n\n"
                    f"<hr>\n"
                    f"✏️ <em>Запиши свой ответ.</em>"
                )
                return jsonify(reply=reply)
        # All tasks answered but not submitted yet
        return jsonify(
            reply='📊 Ты уже ответил на все вопросы! Напиши свой ответ на последний, чтобы завершить тест.'
        ), 400

    profile = _curator_profile()
    measured_count = profile.get('measured_topics_count', 0) if profile else 0
    if measured_count > 0:
        return jsonify(reply='Диагностика уже пройдена!'), 400

    grade = _get_user_grade()
    if not grade:
        return jsonify(reply='Сначала выберите класс в профиле.'), 400

    tasks = get_onboarding_tasks(grade, limit=21)
    if not tasks:
        return jsonify(reply='😅 Диагностические задачи временно недоступны. Попробуй позже.'), 503

    task_ids = [t['id'] for t in tasks]

    # Store minimal test state in session (only IDs, not full task text)
    session['coach_test'] = {
        'active': True,
        'task_ids': task_ids,
        'current_index': 0,
        'answers': {},
        'awaiting_difficulty_for': None,
        'difficulty_ratings': {},
    }

    # Build reply with first task
    first_task = tasks[0]
    total = len(tasks)
    reply = (
        f"🧪 <strong>Диагностика начата!</strong> Всего {total} задач.\n\n"
        f"<hr>\n"
        f"<strong>Задача 1 из {total}:</strong><br>"
        f"{first_task['task_text']}\n\n"
        f"<hr>\n"
        f"✏️ <em>Запиши свой ответ.</em>"
    )

    # Save bot message to history
    try:
        db.session.add(ChatMessage(
            user_id=current_user.id,
            agent_type='coach',
            role='assistant',
            content=reply,
        ))
        db.session.commit()
    except Exception:
        db.session.rollback()

    return jsonify(reply=reply)


# ─── Онбординг: сохранить результаты (C4) ─────────────────────────────────


@prep_bp.route('/coach/onboarding/submit', methods=['POST'])
@login_required
def coach_onboarding_submit():
    """Сохранить результаты онбординг-теста (первые задачи пользователя).

    Ожидает JSON: {'results': {task_id: score, ...}, 'solutions': {task_id: solution_text, ...}}
    где score = 0 (неверно) или 1 (верно) или 2 (частично).

    Если переданы solutions — использует AI-проверку через _evaluate_solution
    для каждого ответа, вместо простого счёта.

    Создаёт AdaptiveTestResult для каждой темы, пересчитывает профиль.
    Возвращает профиль + слабые темы + рекомендуемую олимпиаду.
    """
    data = request.get_json(silent=True) or {}
    results = data.get('results')
    solutions = data.get('solutions') or {}
    if not results or not isinstance(results, dict):
        return jsonify(error='Передайте results: {task_id: score, ...}'), 400

    grade = _get_user_grade()
    if not grade:
        return jsonify(error='Сначала выберите класс'), 400

    try:
        # Группируем результаты по topic
        topic_results = {}
        task_ids = [int(k) for k in results.keys()]
        tasks_map = {t.id: t for t in AdaptiveTask.query.filter(AdaptiveTask.id.in_(task_ids)).all()}

        # Если есть решения — используем AI-проверку
        use_ai_check = bool(solutions)

        for task_id_str, score in results.items():
            try:
                task_id = int(task_id_str)
                task = tasks_map.get(task_id)
                if not task:
                    continue
                topic = task.topic or 'unknown'
                if topic not in topic_results:
                    topic_results[topic] = {'correct': 0, 'total': 0, 'final_level': 0}
                topic_results[topic]['total'] += 1

                if use_ai_check and task_id_str in solutions:
                    # AI-проверка решения
                    user_solution = solutions.get(task_id_str, '')
                    is_correct, feedback = _evaluate_solution(task, '', user_solution)
                    score_val = 2 if is_correct else (1 if feedback.get('score') == 1 else 0)
                else:
                    try:
                        score_val = int(score)
                    except (ValueError, TypeError):
                        score_val = 0

                if score_val >= 1:
                    topic_results[topic]['correct'] += 1
                topic_results[topic]['final_level'] = max(1, min(5, int(
                    topic_results[topic]['correct'] / max(1, topic_results[topic]['total']) * 5
                )))
            except (ValueError, TypeError):
                continue

        # Сохраняем результаты
        now = datetime.utcnow()
        for topic, tr in topic_results.items():
            result = AdaptiveTestResult(
                user_id=current_user.id,
                topic=topic,
                class_level=grade,
                final_level=tr['final_level'],
                tasks_correct=tr['correct'],
                tasks_total=tr['total'],
                started_at=now,
                completed_at=now,
            )
            db.session.add(result)
        db.session.commit()

        # Перестраиваем профиль
        profile = build_profile(current_user.id)
        ctx = _build_subtopic_ctx(profile)
        weak_keys = ctx['weak_keys']
        weak_names = [ctx['topic_names'].get(k, k) for k in weak_keys]

        # Определяем общий уровень (средний по всем темам)
        all_levels = [tr['final_level'] for tr in topic_results.values()]
        overall_level = round(sum(all_levels) / max(len(all_levels), 1))

        # Рекомендуем олимпиаду
        recommended = None
        try:
            recommended_slugs = recommend_olympiads_for(
                grade, [t.get('topic_key') or t.get('topic', '') for t in (profile.get('weak_topics') or [])]
            )
            if recommended_slugs:
                olymp = OlympiadPrep.query.filter_by(
                    slug=recommended_slugs[0], is_active=True
                ).first()
                if olymp:
                    recommended = {'slug': olymp.slug, 'name': olymp.name, 'short_name': olymp.short_name}
        except Exception:
            pass

        return jsonify(
            status='ok',
            measured_count=profile.get('measured_topics_count', 0),
            weak_topics=weak_names,
            recommended_olympiad=recommended,
            overall_level=overall_level,
            topic_results={t: tr['final_level'] for t, tr in topic_results.items()},
        )
    except Exception:
        db.session.rollback()
        current_app.logger.exception('coach_onboarding_submit failed')
        return jsonify(error='Ошибка при сохранении результатов'), 500


# ─── Daily test: сохранить результат теста по подтеме (C4) ────────────────

@prep_bp.route('/coach/daily/submit', methods=['POST'])
@login_required
def coach_daily_submit():
    """Сохранить результат теста по подтеме дня.

    Ожидает JSON: {'subtopic_key': str, 'results': {task_id: score, ...}}

    Вычисляет уровень ученика по подтеме, создаёт DailyQuest с задачами
    на уровне [level-1, level+1] (окно ±1, clamped 1..5).
    Возвращает: tasks (первые 5 из квеста), level, subtopic_key.
    """
    data = request.get_json(silent=True) or {}
    subtopic_key = (data.get('subtopic_key') or '').strip()
    results = data.get('results')
    if not subtopic_key or not results or not isinstance(results, dict):
        return jsonify(error='Передайте subtopic_key и results: {task_id: score, ...}'), 400

    grade = _get_user_grade()
    if not grade:
        return jsonify(error='Сначала выберите класс'), 400

    try:
        # Оценка правильных ответов
        correct = 0
        total = 0
        for task_id_str, score in results.items():
            try:
                total += 1
                if int(score) >= 1:
                    correct += 1
            except (ValueError, TypeError):
                continue

        # Определение уровня: используем score_to_target_level
        from daily_tasks.profile import CALIBRATION_START_LEVEL
        level = score_to_target_level(correct, total, final_level=CALIBRATION_START_LEVEL)
        level = max(1, min(5, level or CALIBRATION_START_LEVEL))

        # Окно ±1 для задач дня
        min_level = max(1, level - 1)
        max_level = min(5, level + 1)

        # Получаем db_topic для подтемы
        db_topic = get_db_topic(grade, subtopic_key)
        if db_topic:
            # Подбираем задачи из БД на уровне [level-1, level+1]
            quest_tasks = (
                AdaptiveTask.query
                .filter_by(class_level=grade, topic=db_topic)
                .filter(AdaptiveTask.difficulty_level.between(min_level, max_level))
                .filter(AdaptiveTask.is_flagged.is_(False))
                .order_by(db.func.random())
                .limit(10)
                .all()
            )
        else:
            quest_tasks = []

        # Fallback: если задач по теме нет — любые задачи класса на уровне level
        if len(quest_tasks) < 5:
            quest_tasks = (
                AdaptiveTask.query
                .filter_by(class_level=grade)
                .filter(AdaptiveTask.difficulty_level.between(min_level, max_level))
                .filter(AdaptiveTask.is_flagged.is_(False))
                .order_by(db.func.random())
                .limit(10)
                .all()
            )

        # Создаём DailyQuest
        import json as json_mod
        task_ids = [t.id for t in quest_tasks]
        today = date.today()
        # Удаляем старый незавершённый квест, если есть
        old_quest = DailyQuest.query.filter_by(
            user_id=current_user.id, date=today
        ).first()
        if old_quest:
            db.session.delete(old_quest)
            db.session.flush()

        quest = DailyQuest(
            user_id=current_user.id,
            date=today,
            task_ids=json_mod.dumps(task_ids),
            completed_count=0,
            total_count=len(task_ids),
            ai_comment=f'Подтема: {subtopic_key}, уровень: {level} (окно {min_level}–{max_level})',
        )
        db.session.add(quest)
        db.session.commit()

        # Возвращаем первые 5 задач
        preview_tasks = [
            {'id': t.id, 'task_text': t.task_text, 'difficulty_level': t.difficulty_level}
            for t in quest_tasks[:5]
        ]

        return jsonify(
            status='ok',
            level=level,
            min_level=min_level,
            max_level=max_level,
            subtopic_key=subtopic_key,
            tasks=preview_tasks,
            total_count=len(task_ids),
        )
    except Exception:
        db.session.rollback()
        current_app.logger.exception('coach_daily_submit failed')
        return jsonify(error='Ошибка при обработке теста'), 500


# ─── Отправить результат теста monthly prep cycle ────────────────────────────

@prep_bp.route('/coach/prep/submit_test', methods=['POST'])
@login_required
def coach_prep_submit_test():
    """Принять результаты адаптивного теста в monthly prep cycle.

    Ожидает JSON: {'results': {task_id: 0|1, ...}}  (0=неверно, 1=верно)

    Делегирует curator.monthly_cycle.submit_test_and_generate_tasks(),
    который:
      - определяет подтему дня (pick_day_subtopic)
      - вычисляет уровень (score_to_target_level)
      - отмечает подтему как протестированную
      - ставит в очередь генерацию задач дня (enqueue_daily_generation)
    """
    data = request.get_json(silent=True) or {}
    results_raw = data.get('results')
    if not results_raw or not isinstance(results_raw, dict):
        return jsonify(error='Передайте results: {task_id: 0|1, ...}'), 400

    # Преобразуем в формат, ожидаемый submit_test_and_generate_tasks
    # results: список dict с ключами task_id, is_correct
    results_list = []
    for task_id_str, score in results_raw.items():
        try:
            task_id = int(task_id_str)
            is_correct = bool(int(score))
            results_list.append({'task_id': task_id, 'is_correct': is_correct})
        except (ValueError, TypeError):
            continue

    if not results_list:
        return jsonify(error='Нет валидных результатов'), 400

    try:
        from curator.monthly_cycle import submit_test_and_generate_tasks
        result = submit_test_and_generate_tasks(current_user.id, results_list)
    except Exception:
        current_app.logger.exception('coach_prep_submit_test failed')
        return jsonify(error='Ошибка при обработке теста'), 500

    if result.get('success'):
        return jsonify(
            status='ok',
            level=result.get('level'),
            correct=result.get('correct'),
            total=result.get('total'),
            subtopic=result.get('subtopic'),
            subtopic_title=result.get('subtopic_title'),
            generation_queued=result.get('generation_queued', False),
            message=result.get('message', 'Тест завершён. Задачи дня готовятся.'),
        )
    else:
        return jsonify(error=result.get('message', 'Неизвестная ошибка')), 400


# ─── Завершить день (C4) ──────────────────────────────────────────────────

@prep_bp.route('/coach/day/complete', methods=['POST'])
@login_required
def coach_day_complete():
    """Завершить день: принять X/10 правильных ответов, адаптировать уровень.

    Ожидает JSON: {'correct': int, 'total': int}

    Адаптация уровня (шкала 1..5):
      - correct ≥ 8 → +1 (вверх)
      - 4 ≤ correct ≤ 7 → 0 (без изменений)
      - correct ≤ 3 → -1 (вниз)

    Обновляет completed_at в DailyQuest.
    Возвращает новый уровень и сообщение.
    """
    data = request.get_json(silent=True) or {}
    try:
        correct = int(data.get('correct', 0))
        total = int(data.get('total', 10))
    except (ValueError, TypeError):
        return jsonify(error='Передайте correct и total (целые числа)'), 400

    if total <= 0:
        return jsonify(error='total должен быть > 0'), 400
    if correct < 0 or correct > total:
        return jsonify(error=f'correct должен быть от 0 до {total}'), 400

    today = date.today()
    try:
        # Находим сегодняшний квест
        quest = DailyQuest.query.filter_by(
            user_id=current_user.id, date=today
        ).first()

        if quest:
            quest.completed_count = correct
            quest.total_count = total
            quest.completed_at = datetime.utcnow()
            db.session.commit()

        # Адаптация уровня
        prev_level = 2  # дефолт
        if quest and quest.ai_comment:
            try:
                # Парсим уровень из ai_comment
                for part in quest.ai_comment.split(','):
                    part = part.strip()
                    if 'уровень:' in part:
                        lvl_str = part.split(':')[1].strip().split()[0]
                        prev_level = int(lvl_str)
            except (ValueError, IndexError):
                pass

        if correct >= 8:
            delta = 1
        elif correct <= 3:
            delta = -1
        else:
            delta = 0

        new_level = max(1, min(5, prev_level + delta))
        pct = int(round(correct / total * 100))

        # Сообщение
        if delta > 0:
            msg = f'🎉 Отлично! {correct}/{total} правильных. Уровень повышен: {prev_level} → {new_level}.'
        elif delta < 0:
            msg = f'💪 Ничего страшного! {correct}/{total} правильных. Попробуй уровень {new_level}.'
        else:
            msg = f'✅ Хорошо! {correct}/{total} правильных. Уровень {new_level} подходит.'

        return jsonify(
            status='ok',
            correct=correct,
            total=total,
            pct=pct,
            prev_level=prev_level,
            new_level=new_level,
            delta=delta,
            message=msg,
        )
    except Exception:
        db.session.rollback()
        current_app.logger.exception('coach_day_complete failed')
        return jsonify(error='Ошибка при завершении дня'), 500


# ─── Coach chat history ────────────────────────────────────────────────────
@prep_bp.route('/coach/history')
@login_required
def coach_history():
    """Вернуть историю чата с куратором (последние 50 сообщений)."""
    messages = (
        ChatMessage.query
        .filter_by(user_id=current_user.id, agent_type='coach')
        .order_by(ChatMessage.timestamp.asc())
        .limit(50)
        .all()
    )
    return jsonify(messages=[m.to_dict() for m in messages])


@prep_bp.route('/coach/history/delete', methods=['POST'])
@login_required
def coach_history_delete():
    """Удалить всю историю чата с куратором для текущего пользователя."""
    try:
        ChatMessage.query.filter_by(
            user_id=current_user.id,
            agent_type='coach'
        ).delete()
        db.session.commit()
        # Также сбрасываем активную диагностику в сессии
        session.pop('coach_test', None)
        return jsonify(status='ok')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Failed to delete coach chat history: {e}")
        return jsonify(status='error', error=str(e)), 500


@prep_bp.route('/coach/set_grade', methods=['POST'])
@login_required
def coach_set_grade():
    """Сохранить выбранный класс (preferred_grade) для текущего пользователя."""
    data = request.get_json(silent=True) or {}
    grade = data.get('grade')
    if not grade:
        return jsonify(error='Укажите grade (5-11)'), 400
    try:
        grade_int = int(grade)
        if grade_int < 5 or grade_int > 11:
            return jsonify(error='Класс должен быть от 5 до 11'), 400
        current_user.preferred_grade = grade_int
        db.session.commit()

        # Инициализируем анкету в БД (не в cookie-сессии)
        from services.diagnostic_questionnaire import QUESTIONNAIRE_FLOW as _QFLOW
        from services.questionnaire_storage import init_questionnaire
        init_questionnaire(len(_QFLOW))

        return jsonify(status='ok', grade=grade_int)
    except (ValueError, TypeError):
        return jsonify(error='Некорректный класс'), 400
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Failed to set grade: {e}")
        return jsonify(error='Ошибка сохранения'), 500


# ─── Диагностическая анкета ────────────────────────────────────────────────

@prep_bp.route('/coach/questionnaire/start', methods=['POST'])
@login_required
def coach_questionnaire_start():
    """Запустить анкету из 3 вопросов для определения уровня."""
    from services.diagnostic_questionnaire import get_question, QUESTIONNAIRE_FLOW
    from services.questionnaire_storage import init_questionnaire, save_questionnaire_state

    # Инициализируем анкету
    total = len(QUESTIONNAIRE_FLOW)
    init_questionnaire(total)

    # Показываем первый вопрос
    first_q = get_question(0)
    if not first_q:
        return jsonify(reply='❌ Не удалось загрузить анкету.')

    reply = (
        f"📋 <strong>Анкета — вопрос 1 из {total}:</strong><br>"
        f"{first_q['question']}\n\n"
        f"<hr>\n"
        f"✏️ <em>Напиши свой ответ.</em>"
    )
    return jsonify(reply=reply)


@prep_bp.route('/coach/questionnaire/answer', methods=['POST'])
@login_required
def coach_questionnaire_answer():
    """Обработка ответа на вопрос анкеты (устаревший endpoint — теперь через coach_chat)."""
    return jsonify(reply='Используй чат куратора для ответов на анкету.')


# ─── Helpers: chat persistence and onboarding submission ─────────────────

def _save_chat_message(user_id, role, content):
    """Save a chat message to the ChatMessage table for the coach agent."""
    try:
        db.session.add(ChatMessage(
            user_id=user_id,
            agent_type='coach',
            role=role,
            content=content,
        ))
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Failed to save coach chat message: {e}")


def _submit_onboarding_results(solutions_dict, difficulty_ratings=None):
    """Submit onboarding test results from inline chat test mode.

    Builds {results: {task_id: 1, ...}, solutions: {...}} from the solutions
    dict, evaluates each solution via AI, creates AdaptiveTestResult rows,
    rebuilds the profile, and returns a formatted chat bot message with results.

    If difficulty_ratings dict {task_id: 1-8} is provided, includes it in the
    summary.
    """
    if difficulty_ratings is None:
        difficulty_ratings = {}
    # Build results dict — all 1s; AI will evaluate via solutions
    results = {tid: 1 for tid in solutions_dict}

    grade = _get_user_grade()
    if not grade:
        reply = '⚠️ Сначала выберите класс в профиле.'
        _save_chat_message(current_user.id, 'assistant', reply)
        return jsonify(reply=reply)

    try:
        # Group results by topic
        topic_results = {}
        task_ids = [int(k) for k in results.keys()]
        tasks_map = {t.id: t for t in AdaptiveTask.query.filter(AdaptiveTask.id.in_(task_ids)).all()}

        for task_id_str in results:
            try:
                task_id = int(task_id_str)
                task = tasks_map.get(task_id)
                if not task:
                    continue
                topic = task.topic or 'unknown'
                if topic not in topic_results:
                    topic_results[topic] = {'correct': 0, 'total': 0, 'final_level': 0}
                topic_results[topic]['total'] += 1

                # Use AI to evaluate solution
                user_solution = solutions_dict.get(task_id_str, '')
                try:
                    is_correct, feedback = _evaluate_solution(task, '', user_solution)
                    score_val = 2 if is_correct else (1 if feedback.get('score') == 1 else 0)
                except Exception:
                    score_val = 1  # fallback: count as attempted

                if score_val >= 1:
                    topic_results[topic]['correct'] += 1
                topic_results[topic]['final_level'] = max(1, min(5, int(
                    topic_results[topic]['correct'] / max(1, topic_results[topic]['total']) * 5
                )))
            except (ValueError, TypeError):
                continue

        # Save results
        now = datetime.utcnow()
        for topic, tr in topic_results.items():
            db.session.add(AdaptiveTestResult(
                user_id=current_user.id,
                topic=topic,
                class_level=grade,
                final_level=tr['final_level'],
                tasks_correct=tr['correct'],
                tasks_total=tr['total'],
                started_at=now,
                completed_at=now,
            ))
        db.session.commit()

        # Rebuild profile
        profile = build_profile(current_user.id)
        ctx = _build_subtopic_ctx(profile)
        weak_names = [ctx['topic_names'].get(k, k) for k in ctx['weak_keys']]

        all_levels = [tr['final_level'] for tr in topic_results.values()]
        overall_level = round(sum(all_levels) / max(len(all_levels), 1))

        # Recommend olympiad
        recommended = None
        try:
            recommended_slugs = recommend_olympiads_for(
                grade, [t.get('topic_key') or t.get('topic', '')
                        for t in (profile.get('weak_topics') or [])]
            )
            if recommended_slugs:
                olymp = OlympiadPrep.query.filter_by(
                    slug=recommended_slugs[0], is_active=True
                ).first()
                if olymp:
                    recommended = {'slug': olymp.slug, 'name': olymp.name, 'short_name': olymp.short_name}
        except Exception:
            pass

        # Format response as chat bot message
        level_labels = {1: '🔵 Начальный', 2: '🟢 Базовый', 3: '🟡 Средний',
                        4: '🟠 Продвинутый', 5: '🔴 Высокий'}
        level_label = level_labels.get(overall_level, '🟡 Средний')

        reply = (
            f"🎉 <strong>Диагностика завершена!</strong>\n\n"
            f"📊 <strong>Твой общий уровень:</strong> {level_label} (уровень {overall_level}/5)\n"
            f"📐 Измерено <strong>{profile.get('measured_topics_count', 0)}</strong> тем.\n"
        )
        if weak_names:
            reply += f"⚠️ <strong>Слабые темы:</strong> {', '.join(weak_names)}.\n"
        reply += "\n🔥 Рекомендация: задачи дня будут подобраны под твой уровень."

        if recommended:
            reply += f"\n\n📋 <strong>Рекомендуемая олимпиада:</strong> {recommended['name']}"

        reply += "\n\n📝 <em>Оцени сложность каждой задачи от 1 до 5 в следующем сообщении.</em>"

        _save_chat_message(current_user.id, 'assistant', reply)
        return jsonify(reply=reply)

    except Exception:
        db.session.rollback()
        current_app.logger.exception('_submit_onboarding_results failed')
        reply = '❌ Произошла ошибка при проверке результатов. Попробуй начать тест заново.'
        _save_chat_message(current_user.id, 'assistant', reply)
        return jsonify(reply=reply)


# ─── Чат с ИИ-куратором (C5 + Part B integration) ────────────────────────


@prep_bp.route('/coach/chat', methods=['POST'])
@login_required
def coach_chat():
    """Обработка сообщения чата с ИИ-куратором (DeepSeek + fallback).

    В system_prompt добавляет блок ДОСТУПНЫЕ ОЛИМПИАДЫ И ТРЕБОВАНИЯ
    из build_olympiads_context() (Part B).

    Если в сессии активен онбординг-тест (coach_test), сообщение
    обрабатывается как ответ на текущую задачу диагностики.
    """
    data = request.get_json(silent=True) or {}
    message = (data.get('message') or '').strip()
    if not message:
        return jsonify(reply='Напиши вопрос, и я подскажу, что подтянуть.'), 400

    # ─── Questionnaire in progress (DB-backed) ─────────────────────────
    from services.questionnaire_storage import get_questionnaire_state, save_questionnaire_state
    q_state = get_questionnaire_state()
    current_app.logger.info(f"[questionnaire] coach_chat check: active={q_state.get('active') if q_state else None}, idx={q_state.get('current_index') if q_state else 'N/A'}")
    if q_state and q_state.get('active'):
        from services.diagnostic_questionnaire import get_question, compute_provisional_level, build_summary, get_test_start_level

        idx = q_state['current_index']
        total = q_state['total']
        q = get_question(idx)
        if q:
            q_state['answers'][q['field']] = message
            q_state['current_index'] = idx + 1
            save_questionnaire_state(q_state)

        next_idx = q_state['current_index']
        if next_idx < total:
            next_q = get_question(next_idx)
            if next_q:
                reply = (
                    f"<strong>Вопрос {next_idx + 1} из {total}:</strong><br>"
                    f"{next_q['question']}\n\n"
                    f"<hr>\n"
                    f"✏️ <em>Напиши свой ответ.</em>"
                )
            else:
                reply = '📋 Анкета завершена!'
        else:
            q_state['active'] = False
            save_questionnaire_state(q_state)
            level = compute_provisional_level(q_state['answers'])
            summary = build_summary(q_state['answers'], level)

            # Сохраняем уровень анкеты в БД (CuratorState)
            try:
                from services.questionnaire_storage import save_questionnaire_result_to_db
                save_questionnaire_result_to_db(current_user.id, level, q_state['answers'])
                current_app.logger.info(f"[questionnaire] saved to DB: user={current_user.id} level={level}")
            except Exception as _e:
                current_app.logger.error(f"[questionnaire] failed to save to DB: {_e}")

            # Save the user answer
            _save_chat_message(current_user.id, 'user', message)
            _save_chat_message(current_user.id, 'assistant', summary)

            current_app.logger.info(f"[questionnaire] completed: level={level}")
            # НЕ запускаем автоматически 21-задачный тест — анкета заменила его
            return jsonify(reply=summary, done=True, level=level, questionnaire_done=True)

        _save_chat_message(current_user.id, 'user', message)
        _save_chat_message(current_user.id, 'assistant', reply)
        return jsonify(reply=reply, done=False)

    # ─── Onboarding test in progress ─────────────────────────────────────
    test_state = session.get('coach_test')
    if test_state and test_state.get('active'):
        total = len(test_state['task_ids'])
        current_index = test_state['current_index']

        # ── Case 1: Awaiting difficulty rating for previous answer ─────
        awaiting_task_id = test_state.get('awaiting_difficulty_for')
        if awaiting_task_id is not None:
            difficulty_str = message.strip()
            try:
                difficulty = int(difficulty_str)
                if 1 <= difficulty <= 5:
                    # Save difficulty rating
                    test_state.setdefault('difficulty_ratings', {})[str(awaiting_task_id)] = difficulty
                    test_state['awaiting_difficulty_for'] = None
                    session['coach_test'] = test_state

                    # All tasks answered + difficulty rated → submit
                    if current_index >= total:
                        session.pop('coach_test', None)
                        return _submit_onboarding_results(
                            test_state['answers'],
                            difficulty_ratings=test_state.get('difficulty_ratings', {})
                        )

                    # Show next task
                    next_task_id = test_state['task_ids'][current_index]
                    task = AdaptiveTask.query.get(next_task_id)
                    if task:
                        from services.math_text_normalizer import normalize_math_text
                        task_text = normalize_math_text(task.task_text) if task.task_text else task.task_text
                        num = current_index + 1
                        reply = (
                            f"✅ Спасибо! Переходим к следующей задаче.\n\n"
                            f"<hr>\n"
                            f"<strong>Задача {num} из {total}:</strong><br>"
                            f"{task_text}\n\n"
                            f"<hr>\n"
                            f"✏️ <em>Запиши свой ответ.</em>"
                        )
                    else:
                        reply = "⚠️ Ошибка загрузки задачи. Попробуй начать тест заново."

                    _save_chat_message(current_user.id, 'assistant', reply)
                    return jsonify(reply=reply)
            except (ValueError, TypeError):
                pass
            # Invalid difficulty — ask again
            reply = "📝 Пожалуйста, оцените сложность задачи по шкале от 1 до 5 — именно для вас, с учётом ваших текущих знаний (просто напишите число)."
            _save_chat_message(current_user.id, 'assistant', reply)
            return jsonify(reply=reply)

        # ── Case 2: Student answered a task ────────────────────────────
        if current_index < total:
            task_id = test_state['task_ids'][current_index]
            # Save user answer
            test_state['answers'][str(task_id)] = message
            test_state['current_index'] = current_index + 1
            session['coach_test'] = test_state

            # Save user message to history
            _save_chat_message(current_user.id, 'user', message)

            # Get the task for evaluation
            task = AdaptiveTask.query.get(task_id)
            if not task:
                reply = "⚠️ Ошибка загрузки задачи. Попробуй начать тест заново."
                _save_chat_message(current_user.id, 'assistant', reply)
                return jsonify(reply=reply)

            # Evaluate answer via AI
            try:
                is_correct, feedback = _evaluate_solution(task, '', message)
                verdict = feedback.get('verdict', 'unknown')
                ai_msg = feedback.get('message', '')
                correct_answer = feedback.get('correct_answer', '') or (task.correct_answer or '')
                reference_solution = task.solution or ''
                # Use AI-generated solution as fallback when DB has none
                ai_solution = feedback.get('solution', '') or ''
                display_solution = reference_solution or ai_solution

                # Build evaluation reply
                if verdict == 'correct':
                    eval_part = f"✅ <strong>Верно!</strong> {ai_msg}"
                elif verdict == 'partial':
                    eval_part = f"⚠️ <strong>Частично верно.</strong> {ai_msg}"
                else:
                    eval_part = f"❌ <strong>Неверно.</strong> {ai_msg}"

                reply = f"{eval_part}\n\n"

                # Show correct answer
                if correct_answer:
                    reply += f"📌 <strong>Правильный ответ:</strong> ${correct_answer}$\n\n"

                # Show full solution (DB reference or AI-generated)
                if display_solution:
                    reply += f"📝 <strong>Полное решение:</strong>\n{display_solution}\n\n"

                # Ask for difficulty rating
                reply += (
                    f"<hr>\n"
                    f"📝 <em>Оцени сложность этой задачи от 1 до 5.</em>"
                )

                # Set awaiting difficulty flag
                test_state['awaiting_difficulty_for'] = task_id
                session['coach_test'] = test_state

            except Exception as e:
                current_app.logger.error(f"coach_chat evaluation error: {e}")
                # Fallback: skip AI evaluation, still ask difficulty
                reference_solution = task.solution or ''
                correct_answer = task.correct_answer or ''

                reply = "✅ Ответ принят!\n\n"
                if correct_answer:
                    reply += f"📌 <strong>Правильный ответ:</strong> ${correct_answer}$\n\n"
                if reference_solution:
                    reply += f"📝 <strong>Полное решение:</strong>\n{reference_solution}\n\n"
                reply += (
                    f"<hr>\n"
                    f"📝 <em>Оцени сложность этой задачи от 1 до 5.</em>"
                )
                test_state['awaiting_difficulty_for'] = task_id
                session['coach_test'] = test_state

            _save_chat_message(current_user.id, 'assistant', reply)
            return jsonify(reply=reply)

    profile = _curator_profile()
    ctx = _build_subtopic_ctx(profile)
    radar = ctx['radar']
    topic_names = ctx['topic_names']
    weak_keys = ctx['weak_keys']
    test_done = ctx['test_done']
    grade = _get_user_grade()

    # Build subtopic radar lines using only 7 adaptive subtopics
    sorted_topics = sorted(radar.items(), key=lambda kv: kv[1], reverse=True)
    radar_lines = [f"  - {topic_names.get(t, t)}: {s}/100" for t, s in sorted_topics]

    # Plans
    plans = PrepPlan.query.filter_by(user_id=current_user.id).order_by(PrepPlan.created_at.desc()).all()
    plan_lines = []
    for p in plans:
        done = PrepDay.query.filter_by(plan_id=p.id, completed=True).count()
        total = PrepDay.query.filter_by(plan_id=p.id).count()
        plan_lines.append(f"  - {p.title} (цель: {p.target_olympiad or '—'}, статус: {p.status}, прогресс: {done}/{total} дней)")

    # Weak names
    weak_names_str = ', '.join(topic_names.get(k, k) for k in weak_keys) if weak_keys else 'нет данных'

    # Build olympiads context (Part B)
    olympiad_block = ''
    if grade and test_done:
        try:
            weak_subtopic_keys = [t.get('topic_key') or t.get('topic', '') for t in (profile.get('weak_topics') or [])]
            olympiad_block = (
                '\n\nДОСТУПНЫЕ ОЛИМПИАДЫ И ТРЕБОВАНИЯ:\n'
                + build_olympiads_context(grade, weak_subtopic_keys)
            )
        except Exception:
            pass

    # Build rich system prompt
    system_prompt = (
        "Ты — персональный ИИ-куратор FORMYLA для подготовки к математическим олимпиадам. "
        "Твоя задача — помогать ученику 5–11 классов улучшать свои знания по подтемам математики. "
        "Отвечай кратко, на русском, давай конкретные шаги на ближайшие дни. "
        "Используй эмодзи для наглядности. Не выдумывай данные — опирайся только на те, что переданы. "
        "Если ученик спрашивает про незнакомую тему — честно скажи, что данных нет."
        + olympiad_block
    )

    radar_block = "\n".join(radar_lines) or "  (нет данных)"
    plan_block = "\n".join(plan_lines) or "  (планов нет)"
    test_status = "диагностика пройдена" if test_done else "диагностика не пройдена"
    grade_info = f"Класс: {grade}" if grade else "Класс: не выбран"

    prompt = (
        f"ДАННЫЕ ОБ УЧЕНИКЕ:\n"
        f"{grade_info}\n"
        f"Статус: {test_status}\n"
        f"Радар подтем (навык 0-100):\n{radar_block}\n\n"
        f"Слабые подтемы: {weak_names_str}\n\n"
        f"Планы подготовки:\n{plan_block}\n\n"
        f"ВОПРОС УЧЕНИКА: {message}"
    )

    try:
        from ai.deepseek_client import DeepSeekClient
        client = DeepSeekClient()
        reply = client.generate_with_reasoning(
            prompt, system_prompt=system_prompt, max_tokens=2000
        )
    except Exception as e:
        current_app.logger.error(f"DeepSeek coach_chat error: {e}")
        fallback = weak_names_str if weak_names_str else 'подтянуть пробелы в математике'
        reply = f"Сейчас не могу связаться с ИИ-куратором. Стоит подтянуть: {fallback}."

    # Save user message and bot reply to chat history
    _save_chat_message(current_user.id, 'user', message)
    _save_chat_message(current_user.id, 'assistant', reply)

    return jsonify(reply=reply)
