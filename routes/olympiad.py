# -*- coding: utf-8 -*-
"""
Blueprint: Раздел «Олимпиады» (`/olympiads/*`) — новая версия.

Эндпоинты (по ТЗ):

  GET  /olympiads/courses                         — каталог олимпиад (НОВЫЙ; временно
                                                    под /courses, потому что устаревший
                                                    /olympiads уже занят в app.py).
  GET  /olympiads/vsosh-9-2027                    — главная страница курса (overview)
  GET  /olympiads/probnik/<code>                  — страница пробника
  GET  /olympiads/task/<task_id>                  — страница одной задачи
  POST /olympiads/task/<task_id>/attempt          — отметить попытку (status/self_score/note)
  POST /olympiads/stage/<code>/start              — стартовать этапный пробник (таймер)
  POST /olympiads/stage/<code>/submit             — сдать этапный пробник
  GET  /olympiads/methods                         — каталог теоретических методов
  GET  /olympiads/methods/<method_code>           — детальная страница метода
  GET  /olympiads/my-progress                     — личная сводка прогресса

ВНИМАНИЕ:
  • Раздел НОВЫЙ, рядом со старыми routes `/olympiads`, `/olympiads/open`,
    `/olympiads/solution/<id>` в `app.py`.  Чтобы не дублировать корневой URL,
    каталог НОВОГО раздела временно живёт на `/olympiads/courses`.  Когда
    данные въедут на прод (после Stage 6: импорт настоящих JSON), мы переключим
    `base.html` со старого `url_for('olympiads')` на новый `url_for('olympiad.catalog')`,
    а старый ендпоинт переименуем в `olympiads_legacy`.

  • Авторизация:
        — GET-страницы каталога/курса/пробника/методов/задач: ПУБЛИЧНЫЕ
          (любой посетитель видит контент).
        — POST attempt / stage start / submit / my-progress: требуют
          login_required (см. ТЗ § 8 «Auth rules»).

  • Markdown-рендеринг полей `*_md` производится в шаблонах через Jinja-фильтр
    `md_render` (регистрируется отдельно в `app.py` в Stage 3.4).
"""

from datetime import datetime
from typing import Optional

from flask import Blueprint, abort, jsonify, render_template, request
from flask_login import current_user, login_required
from sqlalchemy import asc, func

from models import (
    db,
    Probnik,
    OlympiadTask,
    TheoryBlock,
    ProbnikTheory,
    TaskAttempt,
    StageAttempt,
    ATTEMPT_STATUSES,
    STAGE_RESULTS,
)


olympiad_bp = Blueprint('olympiad', __name__, url_prefix='/olympiads')


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _get_probnik_or_404(code: str) -> Probnik:
    probnik = Probnik.query.filter_by(code=code, is_published=True).first()
    if probnik is None:
        abort(404, description=f'Probnik {code!r} not found')
    return probnik


def _get_task_or_404(task_id: int) -> OlympiadTask:
    task = db.session.get(OlympiadTask, task_id)
    if task is None:
        abort(404, description=f'Task #{task_id} not found')
    return task


def _get_theory_or_404(method_code: str) -> TheoryBlock:
    block = TheoryBlock.query.filter_by(method_code=method_code).first()
    if block is None:
        abort(404, description=f'Method {method_code!r} not found')
    return block


def _wants_json() -> bool:
    """True если клиент явно просит JSON (AJAX-запросы из Alpine.js)."""
    return (
        request.is_json
        or request.headers.get('Accept', '').startswith('application/json')
        or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    )


def _compute_stage_result(total_score: int,
                          threshold_prize: Optional[int],
                          threshold_winner: Optional[int]) -> Optional[str]:
    """Вернуть 'winner' / 'prize' / 'participant' (или None, если пороги не заданы)."""
    if threshold_winner is not None and total_score >= threshold_winner:
        return 'winner'
    if threshold_prize is not None and total_score >= threshold_prize:
        return 'prize'
    return 'participant'


def _user_attempt_map(user_id: int, task_ids: list) -> dict:
    """Вернуть {task_id: TaskAttempt} для пользователя."""
    if not task_ids:
        return {}
    rows = TaskAttempt.query.filter(
        TaskAttempt.user_id == user_id,
        TaskAttempt.task_id.in_(task_ids),
    ).all()
    return {a.task_id: a for a in rows}


# ─── 1. Каталог олимпиад ──────────────────────────────────────────────────────

@olympiad_bp.route('/courses', endpoint='catalog')
def catalog():
    """Каталог: все опубликованные курсы (пока только ВсОШ-9-2027)."""
    courses = (
        db.session.query(
            Probnik.competition,
            Probnik.grade,
            Probnik.season_year,
            func.count(Probnik.id).label('probniks_total'),
        )
        .filter(Probnik.is_published.is_(True))
        .group_by(Probnik.competition, Probnik.grade, Probnik.season_year)
        .order_by(Probnik.competition, Probnik.grade, Probnik.season_year)
        .all()
    )
    return render_template('olympiad/catalog.html', courses=courses)


# ─── 2. Страница курса ────────────────────────────────────────────────────────

@olympiad_bp.route('/vsosh-9-2027', endpoint='course')
def course():
    """Курс «ВсОШ-9, сезон 2026/2027»: разделены тематические + этапные пробники."""
    competition, grade, season_year = 'ВсОШ', 9, 2027

    probniks = (
        Probnik.query
        .filter_by(
            competition=competition,
            grade=grade,
            season_year=season_year,
            is_published=True,
        )
        .order_by(asc(Probnik.type), asc(Probnik.sort_order), asc(Probnik.number))
        .all()
    )
    topic_probniks = [p for p in probniks if p.type == 'topic']
    stage_probniks = [p for p in probniks if p.type == 'stage']

    # Карта прогресса (если залогинен)
    progress_by_probnik = {}
    if current_user.is_authenticated:
        all_task_ids = [t.id for p in probniks for t in p.tasks]
        amap = _user_attempt_map(current_user.id, all_task_ids)
        for p in probniks:
            solved = sum(
                1 for t in p.tasks
                if amap.get(t.id) and amap[t.id].status == 'solved'
            )
            progress_by_probnik[p.id] = {
                'solved': solved,
                'total': len(p.tasks),
            }

    return render_template(
        'olympiad/course.html',
        competition=competition,
        grade=grade,
        season_year=season_year,
        topic_probniks=topic_probniks,
        stage_probniks=stage_probniks,
        progress_by_probnik=progress_by_probnik,
    )


# ─── 3. Страница пробника ─────────────────────────────────────────────────────

@olympiad_bp.route('/probnik/<string:code>', endpoint='probnik')
def probnik_page(code):
    """Список задач пробника + связанная теория (для топиков)."""
    probnik = _get_probnik_or_404(code)

    # Связанные теоретические блоки (порядок по display_order)
    theory_links = (
        ProbnikTheory.query
        .filter_by(probnik_id=probnik.id)
        .order_by(asc(ProbnikTheory.display_order))
        .all()
    )

    # Прогресс по задачам пробника
    attempt_map = {}
    if current_user.is_authenticated:
        attempt_map = _user_attempt_map(
            current_user.id,
            [t.id for t in probnik.tasks],
        )

    return render_template(
        'olympiad/probnik.html',
        probnik=probnik,
        tasks=probnik.tasks,
        theory_links=theory_links,
        attempt_map=attempt_map,
    )


# ─── 4. Страница одной задачи ─────────────────────────────────────────────────

@olympiad_bp.route('/task/<int:task_id>', endpoint='task')
def task_page(task_id):
    """Условие + раскрываемая идея + решение + ответ."""
    task = _get_task_or_404(task_id)

    attempt = None
    if current_user.is_authenticated:
        attempt = TaskAttempt.query.filter_by(
            user_id=current_user.id,
            task_id=task.id,
        ).first()

    return render_template(
        'olympiad/task.html',
        task=task,
        probnik=task.probnik,
        attempt=attempt,
    )


# ─── 5. Отметить попытку ──────────────────────────────────────────────────────

@olympiad_bp.route('/task/<int:task_id>/attempt',
                   methods=['POST'], endpoint='task_attempt')
@login_required
def task_attempt(task_id):
    """Создать/обновить TaskAttempt.

    Принимает JSON или form-data с полями:
        status: 'viewed' | 'attempted' | 'solved' | 'revealed'
        self_score: int 0..7 (опционально)
        note: str (опционально)
        time_spent_seconds: int (опционально, прибавляется к существующему)
    """
    task = _get_task_or_404(task_id)
    payload = request.get_json(silent=True) or request.form

    status = payload.get('status')
    if status not in ATTEMPT_STATUSES:
        return jsonify({'ok': False, 'error': 'invalid_status'}), 400

    self_score = payload.get('self_score')
    if self_score is not None:
        try:
            self_score = int(self_score)
        except (TypeError, ValueError):
            return jsonify({'ok': False, 'error': 'invalid_self_score'}), 400
        if not 0 <= self_score <= 7:
            return jsonify({'ok': False, 'error': 'self_score_out_of_range'}), 400

    note = (payload.get('note') or '').strip() or None

    time_delta = payload.get('time_spent_seconds') or 0
    try:
        time_delta = max(0, int(time_delta))
    except (TypeError, ValueError):
        time_delta = 0

    attempt = TaskAttempt.query.filter_by(
        user_id=current_user.id,
        task_id=task.id,
    ).first()

    now = datetime.utcnow()
    if attempt is None:
        attempt = TaskAttempt(
            user_id=current_user.id,
            task_id=task.id,
            status=status,
            self_score=self_score,
            note=note,
            time_spent_seconds=time_delta,
            started_at=now,
        )
        db.session.add(attempt)
    else:
        attempt.status = status
        if self_score is not None:
            attempt.self_score = self_score
        if note is not None:
            attempt.note = note
        attempt.time_spent_seconds = (attempt.time_spent_seconds or 0) + time_delta

    if status in ('solved', 'revealed'):
        attempt.finished_at = now

    db.session.commit()

    return jsonify({
        'ok': True,
        'attempt': {
            'task_id': attempt.task_id,
            'status': attempt.status,
            'self_score': attempt.self_score,
            'time_spent_seconds': attempt.time_spent_seconds,
        },
    })


# ─── 6. Старт этапного пробника ───────────────────────────────────────────────

@olympiad_bp.route('/stage/<string:code>/start',
                   methods=['POST'], endpoint='stage_start')
@login_required
def stage_start(code):
    """Создать новую StageAttempt и вернуть отрендеренную страницу (или JSON)."""
    probnik = _get_probnik_or_404(code)
    if probnik.type != 'stage':
        return jsonify({'ok': False, 'error': 'not_a_stage_probnik'}), 400
    if not probnik.duration_minutes or not probnik.max_score:
        return jsonify({'ok': False, 'error': 'stage_not_configured'}), 400

    attempt = StageAttempt(
        user_id=current_user.id,
        probnik_id=probnik.id,
        started_at=datetime.utcnow(),
        total_score=0,
        task_scores={},
    )
    db.session.add(attempt)
    db.session.commit()

    if _wants_json():
        return jsonify({
            'ok': True,
            'attempt_id': attempt.id,
            'started_at': attempt.started_at.isoformat() + 'Z',
            'duration_minutes': probnik.duration_minutes,
        })

    return render_template(
        'olympiad/stage_active.html',
        probnik=probnik,
        tasks=probnik.tasks,
        attempt=attempt,
    )


# ─── 7. Сдача этапного пробника ───────────────────────────────────────────────

@olympiad_bp.route('/stage/<string:code>/submit',
                   methods=['POST'], endpoint='stage_submit')
@login_required
def stage_submit(code):
    """Завершить StageAttempt: записать оценки 0..7 за каждую задачу, посчитать итог.

    Принимает JSON или form-data:
        attempt_id: int (последняя активная попытка, если не указан)
        scores: dict, ключ — `OlympiadTask.number`, значение — int 0..7
    """
    probnik = _get_probnik_or_404(code)
    if probnik.type != 'stage':
        return jsonify({'ok': False, 'error': 'not_a_stage_probnik'}), 400

    payload = request.get_json(silent=True) or request.form.to_dict(flat=False) or {}

    # form-data вариант: scores[1.1]=7 → собираем словарь
    scores = payload.get('scores')
    if scores is None and isinstance(payload, dict):
        scores = {}
        for k, v in payload.items():
            if k.startswith('scores[') and k.endswith(']'):
                num = k[len('scores['):-1]
                scores[num] = v[0] if isinstance(v, list) else v

    if not isinstance(scores, dict):
        return jsonify({'ok': False, 'error': 'invalid_scores'}), 400

    # Найти попытку
    attempt_id = payload.get('attempt_id')
    if isinstance(attempt_id, list):
        attempt_id = attempt_id[0]
    if attempt_id:
        try:
            attempt = db.session.get(StageAttempt, int(attempt_id))
        except (TypeError, ValueError):
            attempt = None
    else:
        attempt = (
            StageAttempt.query
            .filter_by(user_id=current_user.id, probnik_id=probnik.id, finished_at=None)
            .order_by(StageAttempt.started_at.desc())
            .first()
        )

    if attempt is None or attempt.user_id != current_user.id:
        abort(404, description='stage_attempt_not_found')
    if attempt.finished_at is not None:
        return jsonify({'ok': False, 'error': 'already_submitted'}), 409

    # Нормализуем и валидируем оценки.
    normalized = {}
    total = 0
    valid_numbers = {t.number for t in probnik.tasks}
    for num, raw in scores.items():
        if num not in valid_numbers:
            continue
        try:
            score = int(raw)
        except (TypeError, ValueError):
            continue
        score = max(0, min(7, score))
        normalized[num] = score
        total += score

    attempt.task_scores = normalized
    attempt.total_score = total
    attempt.finished_at = datetime.utcnow()
    attempt.result = _compute_stage_result(
        total,
        probnik.threshold_prize,
        probnik.threshold_winner,
    )

    db.session.commit()

    if _wants_json():
        return jsonify({
            'ok': True,
            'attempt_id': attempt.id,
            'total_score': attempt.total_score,
            'result': attempt.result,
        })

    return render_template(
        'olympiad/stage_report.html',
        probnik=probnik,
        attempt=attempt,
    )


# ─── 8. Каталог методов (теория) ──────────────────────────────────────────────

@olympiad_bp.route('/methods', endpoint='methods')
def methods_catalog():
    """Каталог теоретических блоков, сгруппированный по разделам A..H."""
    blocks = (
        TheoryBlock.query
        .order_by(asc(TheoryBlock.section), asc(TheoryBlock.method_code))
        .all()
    )
    sections = {}
    for b in blocks:
        sections.setdefault(b.section or '?', []).append(b)
    return render_template('olympiad/method.html',
                           sections=sections, block=None, related=[])


# ─── 9. Детальная страница метода ─────────────────────────────────────────────

@olympiad_bp.route('/methods/<string:method_code>', endpoint='method_detail')
def method_detail(method_code):
    """Один теоретический метод + ссылки на связанные."""
    block = _get_theory_or_404(method_code)

    related = []
    codes = block.related_methods or []
    if codes:
        related = TheoryBlock.query.filter(TheoryBlock.method_code.in_(codes)).all()

    return render_template('olympiad/method.html',
                           sections=None, block=block, related=related)


# ─── 10. Моя сводка прогресса ─────────────────────────────────────────────────

@olympiad_bp.route('/my-progress', endpoint='my_progress')
@login_required
def my_progress():
    """Прогресс пользователя по олимпиадам: задачи + этапные попытки."""
    attempts = (
        TaskAttempt.query
        .filter_by(user_id=current_user.id)
        .order_by(TaskAttempt.finished_at.desc().nullslast(),
                  TaskAttempt.started_at.desc())
        .all()
    )

    # Сгруппировать по пробникам
    by_probnik = {}
    for a in attempts:
        if a.task is None:
            continue
        p = a.task.probnik
        if p is None:
            continue
        d = by_probnik.setdefault(p.id, {
            'probnik': p,
            'viewed': 0, 'attempted': 0, 'solved': 0, 'revealed': 0,
        })
        d[a.status] = d.get(a.status, 0) + 1

    stage_attempts = (
        StageAttempt.query
        .filter_by(user_id=current_user.id)
        .order_by(StageAttempt.started_at.desc())
        .all()
    )

    totals = {
        'tasks_viewed': sum(1 for a in attempts if a.status == 'viewed'),
        'tasks_attempted': sum(1 for a in attempts if a.status == 'attempted'),
        'tasks_solved': sum(1 for a in attempts if a.status == 'solved'),
        'tasks_revealed': sum(1 for a in attempts if a.status == 'revealed'),
        'stages_finished': sum(1 for s in stage_attempts if s.finished_at),
    }

    return render_template(
        'olympiad/my_progress.html',
        by_probnik=list(by_probnik.values()),
        stage_attempts=stage_attempts,
        totals=totals,
    )
