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
from datetime import date, datetime

from flask import Blueprint, jsonify, request, abort, render_template, current_app
from flask_login import current_user, login_required

from models import db, AdaptiveTask, AdaptiveTestResult, OlympiadPrep, PrepPlan, PrepDay, TaskSolution
from services.prep_planner import generate_prep_plan, RADAR_TOPICS, TOPIC_NAMES_RU

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
    """Build radar dict from user's UserTopicProgress or defaults."""
    from models import UserTopicProgress
    radar = {}
    for topic in RADAR_TOPICS:
        progress = UserTopicProgress.query.filter_by(
            user_id=current_user.id, topic=topic
        ).first()
        if progress:
            # Map IRT level (1-7) to skill (0-100)
            radar[topic] = min(100, max(0, int(progress.current_level / 7 * 100)))
        else:
            radar[topic] = 50  # default
    return radar


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
            radar[topic] = min(100, max(0, int((r.final_level or 3) / 7 * 100)))

    # Fill missing topics with default
    for t in RADAR_TOPICS:
        if t not in radar:
            radar[t] = 50

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
  "hint": "подсказка, если решение неверное (1 предложение)"
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


# --- Куратор подготовки: радар + чат с ИИ-куратором ---
@prep_bp.route('/coach')
@login_required
def coach():
  """Страница Куратора: радар + чат с ИИ-агентом."""
    radar = _get_user_radar()
        return render_template('prep/coach.html', radar=radar, topic_names=TOPIC_NAMES_RU)


@prep_bp.route('/coach/chat', methods=['POST'])
@login_required
def coach_chat():
    """Обработка сообщения чата с ИИ-куратором."""
    data = request.get_json(silent=True) or {}
      message = (data.get('message') or '').strip()
      if not message:
        return jsonify(reply='Напиши вопрос, и я подскажу, что подтянуть.'), 400
      radar = _get_user_radar()
      weak = sorted(radar.items(), key=lambda kv: kv[1])[:3]
      weak_names = ', '.join(TOPIC_NAMES_RU.get(t, t) for t, _ in weak)

      reply = (
        f'По твоему радару слабее всего: {weak_names}. '
        f'Советую на этой неделе сделать акцент на них: по 10 задач в день, '
        f'база по 1 на каждую из 7 подтем + 3 в самые слабые. '
        f'Твой вопрос: "{message}".'
      )
      return jsonify(reply=reply, weak_topics=[t for t, _ in weak])
