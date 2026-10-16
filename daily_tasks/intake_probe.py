"""Entry diagnostic on the daily-tasks page; answers stay in the database."""
from copy import deepcopy
from datetime import datetime
from uuid import uuid4

from flask import current_app, jsonify, render_template, request
from flask_login import current_user, login_required

SECTIONS = ('algebra', 'number_theory', 'geometry', 'combinatorics', 'logic')
LABELS = dict(zip(SECTIONS, ('Алгебра', 'Теория чисел', 'Геометрия', 'Комбинаторика', 'Логика')))


def probe_complete(intake):
    results = intake.get('anchor_results') or []
    return (len(results) == 5
            and all(isinstance(r, dict) and isinstance(r.get('correct'), bool) for r in results)
            and {r.get('section') for r in results} == set(SECTIONS))


def needs_probe(intake):
    return bool(intake.get('completed') and not intake.get('skipped')
                and not probe_complete(intake))


def _load(user_id, lock=False):
    from models_curator import CuratorState
    from services.intake_service import _prep_state_dict
    query = CuratorState.query.filter_by(user_id=user_id)
    if lock:
        query = query.populate_existing().with_for_update()
    cs = query.first()
    ps = deepcopy(_prep_state_dict(cs)) if cs else {}
    intake = ps.get('intake')
    return cs, ps, intake if isinstance(intake, dict) else {}


def _save(cs, ps, intake):
    from models import db
    from sqlalchemy.orm.attributes import flag_modified
    ps['intake'] = intake
    cs.prep_state = ps
    flag_modified(cs, 'prep_state')
    db.session.commit()


def _public(intake):
    if probe_complete(intake):
        return {'done': True, 'redirect_url': '/daily_tasks/'}
    probe = intake['daily_probe']
    idx = len(probe['results'])
    task = probe['tasks'][idx]
    return {'done': False, 'probe_id': probe['id'], 'index': idx + 1, 'total': 5,
            'task': {'id': task['db_id'], 'statement': task['statement'],
                     'section': LABELS[task['section']], 'figure_url': task.get('figure_url')}}


def _valid_tasks(tasks):
    return (len(tasks) == 5 and {t.get('section') for t in tasks} == set(SECTIONS)
            and len({t.get('db_id') for t in tasks}) == 5
            and all(t.get('db_id') and str(t.get('statement') or '').strip()
                    and str(t.get('answer') or '').strip() for t in tasks))


def _finish(cs, intake, probe):
    from services.intake_questions import compute_prior
    result = compute_prior(intake.get('answers') or {}, probe['results'])
    intake.update(anchor_results=probe['results'], prior_mu=result.prior_mu,
                  prior_sigma=result.prior_sigma, skip_probe=False,
                  probe_completed_at=datetime.utcnow().isoformat())
    intake['anchor_solutions'] = [
        {'section': t['section'], 'section_ru': LABELS[t['section']],
         'statement': t['statement'], 'answer': t['answer'],
         'solution': t.get('solution', ''), 'correct': r['correct']}
        for t, r in zip(probe['tasks'], probe['results'])]
    # Same canonical fields as level_engine.set_prior, in ONE transaction
    # with the answers. Do not erase existing section/theme history or XP.
    cs.level_mu = max(1.0, min(4.0, result.prior_mu))
    cs.level_sigma = max(0.35, result.prior_sigma)
    cs.level_updated_at = intake['probe_completed_at']
    intake.pop('daily_probe', None)


def _advance(cs, intake, data):
    probe = intake.get('daily_probe')
    if not probe or data.get('probe_id') != probe['id']:
        raise ValueError('Тест обновился. Нажми «Продолжить тест».')
    try:
        task_id = int(data.get('task_id'))
    except (TypeError, ValueError):
        raise ValueError('Не указана задача.')
    if any(r['task_id'] == task_id for r in probe['results']):
        return  # Retrying a request must not count the answer twice.
    task = probe['tasks'][len(probe['results'])]
    if task_id != task['db_id']:
        raise ValueError('Ответ относится к другой задаче. Продолжи текущий тест.')
    answer = data.get('answer')
    if not isinstance(answer, str) or not answer.strip() or len(answer) > 1000:
        raise ValueError('Введи короткий ответ или нажми «Не знаю».')
    from services.anchors import check_answer
    skipped = answer.strip() == '__skip__'
    probe['results'].append({'task_id': task_id, 'section': task['section'],
                             'level': task.get('level', 1), 'skipped': skipped,
                             'user_answer': '' if skipped else answer.strip(),
                             'correct': False if skipped else check_answer(answer, task['answer'])})
    if len(probe['results']) == 5:
        _finish(cs, intake, probe)


def attach(bp):
    @bp.after_app_request
    def redirect_completed_intake(response):
        if request.endpoint in ('intake.start_intake', 'intake.answer_intake') and response.is_json:
            data = response.get_json(silent=True)
            if response.status_code == 200 and isinstance(data, dict) and data.get('done') and data.get('result') and not data.get('error'):
                data['redirect_url'] = '/daily_tasks/'
                response.set_data(current_app.json.dumps(data))
                response.headers['Cache-Control'] = 'no-store'
        return response

    @bp.before_app_request
    def show_entry_probe():
        if request.method != 'GET' or request.path.rstrip('/') != '/daily_tasks':
            return None
        if not current_user.is_authenticated or not current_user.has_access():
            return None
        _, _, intake = _load(current_user.id)
        if needs_probe(intake):
            return render_template('daily_tasks/intake_probe.html'), 200, {'Cache-Control': 'no-store'}
        return None

    def run_probe(submit=False):
        from models import db
        if not current_user.has_access():
            return jsonify(error='Доступ к занятиям закончился.'), 402
        try:
            cs, ps, intake = _load(current_user.id, lock=True)
            if not intake.get('completed') or intake.get('skipped'):
                return jsonify(error='Сначала заверши вступительную анкету.', redirect_url='/intake/'), 409
            if probe_complete(intake):
                return jsonify(_public(intake))
            if submit:
                data = request.get_json(silent=True)
                if not isinstance(data, dict):
                    raise ValueError('Некорректный ответ.')
                _advance(cs, intake, data)
            elif not intake.get('daily_probe'):
                grade = int(intake.get('class_level') or 0)
                if grade not in range(5, 12):
                    raise ValueError('Подтверди класс во вступительной анкете.')
                # pick_anchors may lazily seed the database and commit.
                db.session.rollback()
                from services.anchors import pick_anchors
                tasks, _ = pick_anchors(grade)
                if not _valid_tasks(tasks):
                    return jsonify(error='Не удалось загрузить все 5 задач. Попробуй позже. Результаты не потеряны.'), 503
                cs, ps, intake = _load(current_user.id, lock=True)
                if not needs_probe(intake) or int(intake.get('class_level') or 0) != grade:
                    return jsonify(error='Анкета обновилась. Обнови страницу.'), 409
                if not intake.get('daily_probe'):
                    intake['daily_probe'] = {'id': uuid4().hex, 'tasks': tasks, 'results': []}
            payload = _public(intake)
            _save(cs, ps, intake)
            return jsonify(payload)
        except ValueError as exc:
            db.session.rollback()
            return jsonify(error=str(exc)), 400
        except Exception:
            db.session.rollback()
            current_app.logger.exception('daily intake probe failed user=%s', current_user.id)
            return jsonify(error='Не удалось сохранить ответ. Нажми «Продолжить тест» и попробуй ещё раз.'), 503

    @bp.route('/entry-probe/start', methods=['POST'])
    @login_required
    def entry_probe_start():
        return run_probe()

    @bp.route('/entry-probe/answer', methods=['POST'])
    @login_required
    def entry_probe_answer():
        return run_probe(submit=True)
