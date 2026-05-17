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


# ─── 5b. Проверка ответа (1-в-1 как Daily Quest) ─────────────────────────────

@olympiad_bp.route('/task/<int:task_id>/submit',
                   methods=['POST'], endpoint='task_submit')
@login_required
def task_submit(task_id):
    """Проверка ответа ученика на олимпиадную задачу.

    Полный аналог `daily_quest_submit` из app.py:
      ШАГ 1. Локальная сверка `compare_math_answers`.
      ШАГ 2. ИИ-верификация (DeepSeek) — с правом переопределить ошибочный эталон.
      ШАГ 3. Финальный вердикт (AI > локальная сверка).
      ШАГ 4. При is_correct=True — апдейтим TaskAttempt(status='solved') и XP.
      ШАГ 5. Fallback-фидбек, если AI не дал ничего.

    Принимает JSON ``{answer, solution}``, возвращает
    ``{success, is_correct, correct_answer, xp_earned, ai_feedback,
       reference_overridden}``.
    """
    from flask import current_app
    from flask_login import current_user as _cu
    from utils.math_answer_utils import compare_math_answers

    task = _get_task_or_404(task_id)
    payload = request.get_json(silent=True) or {}

    user_answer = (payload.get('answer') or '').strip()
    user_solution = (payload.get('solution') or '').strip()

    if not user_answer and not user_solution:
        return jsonify({
            'success': False,
            'error': 'Answer or solution is required',
        }), 400

    # === ШАГ 1. Быстрая локальная сверка ответа с заложенным эталоном ===
    correct_answer = task.answer or ''
    correct_solution = task.solution_md or ''
    local_match = (
        compare_math_answers(user_answer, correct_answer)
        if user_answer and correct_answer
        else False
    )

    # === ШАГ 2. ИИ-верификация: даём тьютору право переопределить вердикт ===
    ai_feedback = ""
    ai_verdict = None  # 'correct' | 'wrong' | None
    ai_overrode_reference = False
    actual_correct_answer = correct_answer  # что считать правильным после AI-проверки

    try:
        from ai.deepseek_client import DeepSeekClient  # noqa: WPS433
        deepseek_available = True
    except Exception:  # pragma: no cover — ИИ опционален
        deepseek_available = False

    if deepseek_available and user_answer:
        try:
            import json as _json
            import re as _re
            client = DeepSeekClient()
            solution_part = (
                f"\n\nРешение ученика:\n{user_solution}" if user_solution else ""
            )
            ref_solution_part = (
                f"\nЭталонное решение из базы:\n{correct_solution}"
                if correct_solution else ""
            )

            prompt = f"""Ты — ИИ-тьютор по олимпиадной математике. Реши задачу САМ, затем проверь ответ ученика.

ВАЖНО: эталонный ответ из базы задач МОЖЕТ БЫТЬ ОШИБОЧНЫМ. Не доверяй ему слепо — реши задачу сам и сравни.

Задача:
{task.condition_md}

Эталонный ответ из базы: {correct_answer}
{ref_solution_part}

Ответ ученика: {user_answer}
{solution_part}

Сделай следующее:
1. Реши задачу самостоятельно. Найди ИСТИННО правильный ответ.
2. Сравни истинный ответ с ответом ученика (учитывай эквивалентные формы: 1/2 = 0.5, 70° = 70 и т. п.).
3. Сравни истинный ответ с эталоном из базы. Если они отличаются — пометь, что эталон ошибочен.
4. Дай подробный разбор решения ученика на русском.

ПРАВИЛА ФОРМАТИРОВАНИЯ (СТРОГО):
- Используй обычный Markdown: **жирный текст** через две звёздочки, # заголовки, * списки.
- НЕ используй \\cdot или \\textbf для выделения текста — только Markdown **звёздочки**.
- Все формулы оборачивай в \\( ... \\) для inline или \\[ ... \\] для display.
- Внутри формул используй стандартный LaTeX: \\frac{{a}}{{b}}, \\cdot, \\sqrt{{...}}.
- НИКОГДА не пиши \\cdot \\cdot вокруг русских слов — это ломает рендеринг.

В САМОМ КОНЦЕ ответа добавь СТРОГО такой блок (без изменений формата):

```json
{{"true_answer": "<твой правильный ответ>", "student_correct": <true|false>, "reference_was_wrong": <true|false>}}
```

Где:
- true_answer — твой правильный ответ к задаче
- student_correct — true если ответ ученика правильный (эквивалентен истинному)
- reference_was_wrong — true если эталон из базы не совпадает с истинным ответом
"""

            ai_raw = client.generate(prompt, max_tokens=2000) or ""

            # Парсим JSON-блок из конца ответа
            json_match = _re.search(
                r'\{[^{}]*"student_correct"[^{}]*\}', ai_raw
            )
            if json_match:
                try:
                    verdict_data = _json.loads(json_match.group(0))
                    student_correct = bool(
                        verdict_data.get('student_correct', False)
                    )
                    reference_was_wrong = bool(
                        verdict_data.get('reference_was_wrong', False)
                    )
                    true_answer = str(
                        verdict_data.get('true_answer', '')
                    ).strip()

                    ai_verdict = 'correct' if student_correct else 'wrong'
                    if reference_was_wrong and true_answer:
                        ai_overrode_reference = True
                        actual_correct_answer = true_answer
                except Exception as _je:
                    current_app.logger.warning(
                        f"olympiad task_submit: failed to parse AI verdict JSON: {_je}"
                    )

            # В фидбеке прячем технический JSON-блок от пользователя
            ai_feedback = _re.sub(
                r'```json\s*\{[^{}]*"student_correct"[^{}]*\}\s*```',
                '', ai_raw,
            )
            ai_feedback = _re.sub(
                r'\{[^{}]*"student_correct"[^{}]*\}',
                '', ai_feedback,
            ).strip()

            # Чиним типичный косяк LLM: \cdot \cdot вокруг русских слов вместо ** **.
            ai_feedback = _re.sub(
                r'\\cdot\s*\\cdot\s*([^\n\\]+?)\s*\\cdot\s*\\cdot',
                r'**\1**',
                ai_feedback,
            )
            # Также \textbf{...} → **...**
            ai_feedback = _re.sub(
                r'\\textbf\{([^{}]+)\}', r'**\1**', ai_feedback
            )

            if ai_overrode_reference and ai_verdict == 'correct':
                ai_feedback = (
                    "ℹ️ *Эталонный ответ в базе задач был ошибочным. "
                    "Я перепроверил — твой ответ верный, истинный ответ: "
                    f"**{actual_correct_answer}**.*\n\n"
                    + ai_feedback
                )
        except Exception as e:
            current_app.logger.error(f"olympiad task_submit AI verdict error: {e}")
            ai_feedback = ""

    # === ШАГ 3. Финальный вердикт ===
    # Приоритет: AI-вердикт > локальная сверка.
    if ai_verdict == 'correct':
        is_correct = True
    elif ai_verdict == 'wrong' and ai_overrode_reference:
        is_correct = False
    else:
        is_correct = local_match

    # === ШАГ 4. XP + отметка TaskAttempt(status='solved') ===
    xp_earned = 20 if is_correct else 0

    if is_correct:
        # Обновляем TaskAttempt: status='solved', finished_at=now
        attempt = TaskAttempt.query.filter_by(
            user_id=_cu.id, task_id=task.id,
        ).first()
        now = datetime.utcnow()
        if attempt is None:
            attempt = TaskAttempt(
                user_id=_cu.id,
                task_id=task.id,
                status='solved',
                started_at=now,
                finished_at=now,
            )
            db.session.add(attempt)
        else:
            attempt.status = 'solved'
            attempt.finished_at = now

        # Начисляем XP, если у модели User есть это поле
        try:
            _cu.experience_points = (_cu.experience_points or 0) + xp_earned
        except Exception:
            # На случай, если у пользователя нет такого поля — не падаем.
            pass

        db.session.commit()

    # === ШАГ 5. Fallback-фидбек, если AI не дал ничего ===
    if not ai_feedback:
        if is_correct:
            ai_feedback = "✅ Правильно! +20 XP"
        else:
            ai_feedback = (
                f"❌ Неправильно. Правильный ответ: {actual_correct_answer}"
            )
            if correct_solution and not ai_overrode_reference:
                ai_feedback += f"\n\n**Решение:**\n{correct_solution}"

    return jsonify({
        'success': True,
        'is_correct': is_correct,
        'correct_answer': actual_correct_answer if not is_correct else None,
        'xp_earned': xp_earned,
        'ai_feedback': ai_feedback,
        'reference_overridden': ai_overrode_reference,
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

ALLOWED_METHOD_COMPETITIONS = (
    'ВсОШ', 'Ломоносов', 'Курчатов', 'Физтех', 'Высшая проба', 'Турнир городов',
)
ALLOWED_METHOD_SECTIONS = ('A', 'B', 'C', 'D', 'E', 'F', 'G', 'H')
ALLOWED_METHOD_SORTS = ('frequency', 'level', 'code')

# Категория (русская группа) ← буквенный префикс кода метода.
# Согласовано с ТЗ: одна категория может склеивать несколько букв.
LETTER_TO_CATEGORY = {
    'A': 'algebra',  'C': 'algebra',  'G': 'algebra',
    'B': 'logic',
    'D': 'number_theory',
    'E': 'combinatorics',
    'F': 'geometry',
    'H': 'other',
}
CATEGORY_LABELS = (
    ('algebra',       'Алгебра'),
    ('geometry',      'Геометрия'),
    ('combinatorics', 'Комбинаторика'),
    ('number_theory', 'Теория чисел'),
    ('logic',         'Логика'),
    ('other',         'Прочее'),
)
ALLOWED_METHOD_CATEGORIES = tuple(slug for slug, _ in CATEGORY_LABELS)


def _category_for_code(code: str):
    """Вернуть slug категории по первой букве кода метода (или None)."""
    if not code:
        return None
    return LETTER_TO_CATEGORY.get(code[0].upper())


@olympiad_bp.route('/methods', endpoint='methods')
def methods_catalog():
    """Каталог теоретических блоков с фильтрами grade/competition/difficulty/category.

    Query params:
        grade        int  5..11
        competition  str  одна из ALLOWED_METHOD_COMPETITIONS
        difficulty   int  1..5
        category     str  algebra | geometry | combinatorics | number_theory
                          | logic | other  (группирует буквы кода метода)
        section      str  A..H  (legacy; если задан, используется как low-level фильтр)
        sort         str  frequency (default) | level | code
    """
    grade = request.args.get('grade', type=int)
    competition = request.args.get('competition', type=str)
    difficulty = request.args.get('difficulty', type=int)
    category = request.args.get('category', type=str)
    section = request.args.get('section', type=str)
    sort_key = request.args.get('sort', default='frequency', type=str)

    # Валидация.
    if grade is not None and not (5 <= grade <= 11):
        grade = None
    if competition and competition not in ALLOWED_METHOD_COMPETITIONS:
        competition = None
    if difficulty is not None and not (1 <= difficulty <= 5):
        difficulty = None
    if category and category not in ALLOWED_METHOD_CATEGORIES:
        category = None
    if section:
        section = section.upper()
        if section not in ALLOWED_METHOD_SECTIONS:
            section = None
    if sort_key not in ALLOWED_METHOD_SORTS:
        sort_key = 'frequency'

    def _build_query(use_freq_fields: bool):
        q = TheoryBlock.query
        if section:
            q = q.filter(TheoryBlock.section == section)
        if difficulty is not None:
            q = q.filter(TheoryBlock.difficulty_level == difficulty)

        if sort_key == 'frequency' and use_freq_fields:
            # Сначала по total_count (точные данные xlsx), затем frequency_vsosh_9 как fallback.
            q = q.order_by(
                TheoryBlock.total_count.desc().nullslast(),
                TheoryBlock.frequency_vsosh_9.desc().nullslast(),
                asc(TheoryBlock.sort_order),
                asc(TheoryBlock.method_code),
            )
        elif sort_key == 'level':
            q = q.order_by(
                asc(TheoryBlock.difficulty_level),
                asc(TheoryBlock.sort_order),
                asc(TheoryBlock.method_code),
            )
        else:  # 'code' или 'frequency' без новых колонок
            q = q.order_by(
                asc(TheoryBlock.section),
                asc(TheoryBlock.sort_order),
                asc(TheoryBlock.method_code),
            )
        return q

    # На проде Postgres колонки total_count/share_percent/grades/... могут
    # отсутствовать, если auto-migration не отработала. Тогда любой SELECT
    # через ORM (он выбирает ВСЕ поля модели) бросает UndefinedColumn → 500.
    # Делаем многоуровневый fallback.
    import logging as _logging
    _log = _logging.getLogger(__name__)
    try:
        blocks = _build_query(use_freq_fields=True).all()
    except Exception as _e_freq:
        db.session.rollback()
        _log.warning(f"[methods_catalog] freq-fields query failed: {_e_freq}")
        try:
            blocks = _build_query(use_freq_fields=False).all()
        except Exception as _e_orm:
            db.session.rollback()
            _log.error(
                f"[methods_catalog] ORM query failed (missing columns?): {_e_orm}"
            )
            # Последний рубеж: пытаемся отдать пустую страницу,
            # чтобы пользователь увидел оболочку, а не 500.
            blocks = []

    # JSON-фильтры в Python: SQLite не любит индексы по JSON.
    if grade is not None:
        blocks = [b for b in blocks if b.grades and grade in b.grades]
    if competition:
        blocks = [
            b for b in blocks
            if b.recommended_competitions
            and competition in b.recommended_competitions
        ]
    # Категория — группа букв кода метода. Фильтруем в Python (89 записей, OK).
    if category:
        blocks = [b for b in blocks if _category_for_code(b.method_code) == category]

    sections = {}
    for b in blocks:
        sections.setdefault(b.section or '?', []).append(b)

    # Группировка по человекочитаемой категории — для шаблона.
    categories_grouped = {slug: [] for slug, _ in CATEGORY_LABELS}
    for b in blocks:
        slug = _category_for_code(b.method_code) or 'other'
        categories_grouped.setdefault(slug, []).append(b)

    try:
        total_methods = TheoryBlock.query.count()
    except Exception:
        db.session.rollback()
        total_methods = len(blocks)

    # TOP-10 по абсолютной частотности на ВсОШ-9 (для бейджа «🔥 ТОП-10»).
    # На проде колонка total_count может отсутствовать → fallback к пустому множеству.
    try:
        top_10_query = (
            TheoryBlock.query
            .filter(TheoryBlock.total_count.isnot(None))
            .order_by(TheoryBlock.total_count.desc())
            .limit(10)
            .all()
        )
        top_10_codes = {tb.method_code for tb in top_10_query}
    except Exception as _e_top:
        db.session.rollback()
        import logging as _logging
        _logging.getLogger(__name__).warning(
            f"[methods_catalog] top10 query failed: {_e_top}"
        )
        top_10_codes = set()

    # Максимум total_count — для нормализации прогресс-баров.
    try:
        max_count = max((getattr(b, 'total_count', None) or 0) for b in blocks) if blocks else 0
    except Exception:
        max_count = 0

    return render_template(
        'olympiad/method.html',
        sections=sections,
        categories_grouped=categories_grouped,
        category_labels=CATEGORY_LABELS,
        blocks=blocks,
        block=None,
        related=[],
        total_methods=total_methods,
        top_10_codes=top_10_codes,
        max_count=max_count,
        filters={
            'grade': grade,
            'competition': competition,
            'difficulty': difficulty,
            'category': category,
            'section': section,
            'sort': sort_key,
        },
        allowed_competitions=ALLOWED_METHOD_COMPETITIONS,
        allowed_sections=ALLOWED_METHOD_SECTIONS,
        allowed_categories=CATEGORY_LABELS,
    )


# ─── 9. Детальная страница метода ─────────────────────────────────────────────

@olympiad_bp.route('/methods/<string:method_code>', endpoint='method_detail')
def method_detail(method_code):
    """Один теоретический метод + связанные методы + список реальных задач
    ВсОШ-9, в которых этот метод применяется (по xlsx-импорту).
    """
    block = _get_theory_or_404(method_code)

    related = []
    codes = block.related_methods or []
    if codes:
        related = TheoryBlock.query.filter(
            TheoryBlock.method_code.in_(codes)
        ).all()

    # Связанные задачи: ищем method_code в JSON-массиве OlympiadTask.method_codes.
    # Для SQLite используем LIKE-фоллбек по сериализованной строке JSON, а в
    # Python ещё раз фильтруем точно, чтобы не ловить ложные подстроки.
    from sqlalchemy import or_, cast, String

    candidates = (
        OlympiadTask.query
        .join(Probnik)
        .filter(
            Probnik.code.like('vsosh-9-archive-%'),
            or_(
                OlympiadTask.method_primary == method_code,
                OlympiadTask.method_secondary == method_code,
                cast(OlympiadTask.method_codes, String).like(f'%"{method_code}"%'),
            ),
        )
        .order_by(Probnik.season_year.desc(), OlympiadTask.sort_order.asc())
        .all()
    )

    # Финальная точная фильтрация: проверяем JSON-массив в Python.
    linked_tasks = []
    for t in candidates:
        codes = t.method_codes or []
        if (
            method_code in codes
            or t.method_primary == method_code
            or t.method_secondary == method_code
        ):
            linked_tasks.append(t)

    return render_template('olympiad/method.html',
                           sections=None, block=block, related=related,
                           linked_tasks=linked_tasks)


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
