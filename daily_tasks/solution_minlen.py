# -*- coding: utf-8 -*-
"""
daily_tasks/solution_minlen.py — минимальная длина текстового решения в «Задачах дня».

Правило: для задач уровня >= DT_SOLUTION_MIN_LEVEL (по умолчанию 2, т.е. уровни
2, 3, 4) ученик обязан описать ход решения текстом не короче
DT_SOLUTION_MIN_LEN символов (по умолчанию 15) — либо прикрепить фото решения.
Уровень 1 не затрагивается.

Как solution_guard / admin_api: вешается на daily_tasks_bp через attach(bp),
без правки routes.py и шаблона daily_tasks_dashboard.html.

  * before_request — серверная проверка POST /daily_tasks/<id>/submit и
    /daily_tasks/<id>/submit_ai. При нарушении -> 400 JSON
    {"status": "error", "error": "...", "code": "solution_too_short"}.
    Уровень берётся как в submit_ai: сначала банк (BankIssue -> DailyTaskBank.level),
    затем DailyTaskItem.difficulty_level. Если задача не найдена — не вмешиваемся
    (роут сам вернёт 404).
  * after_request — в HTML дашборда (есть dt-init-data) добавляет
    <script defer src="/static/js/dt_solution_minlen.js"> — клиентская проверка
    и счётчик символов до отправки на сервер.

Отключить без деплоя: DT_SOLUTION_MINLEN_DISABLED=1.
Порог/уровень: DT_SOLUTION_MIN_LEN, DT_SOLUTION_MIN_LEVEL.
Любая внутренняя ошибка логируется и НЕ блокирует отправку ответа.
"""
import logging
import os
import re
import time

from flask import jsonify, request

log = logging.getLogger(__name__)

_SCRIPT_SRC = '/static/js/dt_solution_minlen.js'
_MARKER = 'dt-init-data'
_VERSION = str(int(time.time()))
_SUBMIT_RE = re.compile(r'^/daily_tasks/(\d+)/submit(?:_ai)?/?$')


def _env_int(name, default):
    try:
        return int(os.environ.get(name, '').strip() or default)
    except (TypeError, ValueError):
        return default


def min_len() -> int:
    return max(1, _env_int('DT_SOLUTION_MIN_LEN', 15))


def min_level() -> int:
    return max(1, _env_int('DT_SOLUTION_MIN_LEVEL', 2))


def _disabled() -> bool:
    return os.environ.get('DT_SOLUTION_MINLEN_DISABLED', '0').strip().lower() in ('1', 'true', 'yes')


def _task_level(item_id: int, user_id: int):
    """Уровень задачи или None, если задачу определить не удалось."""
    try:
        from models import db, BankIssue, DailyTaskBank
        issue = BankIssue.query.filter_by(user_id=user_id, task_id=item_id).first()
        if issue is not None:
            task = db.session.get(DailyTaskBank, item_id)
            if task is None:
                return None
            return int(task.level or 1)
    except Exception as exc:  # pragma: no cover
        log.warning('solution_minlen: bank lookup failed item=%s: %s', item_id, exc)
    try:
        from .models import DailyTaskItem
        item = DailyTaskItem.query.get(item_id)
        if item is not None:
            return int(item.difficulty_level or 1)
    except Exception as exc:  # pragma: no cover
        log.warning('solution_minlen: item lookup failed item=%s: %s', item_id, exc)
    return None


def _solution_len(data) -> int:
    raw = ''
    for key in ('user_solution', 'solution_text', 'solution'):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            raw = val
            break
    return len(re.sub(r'\s+', ' ', raw).strip())


def _has_photo(data) -> bool:
    single = data.get('solution_image_b64') or ''
    if isinstance(single, str) and single.strip():
        return True
    multi = data.get('solution_images_b64') or []
    if isinstance(multi, list) and any(isinstance(x, str) and x.strip() for x in multi):
        return True
    try:
        if request.files and any(f and f.filename for f in request.files.values()):
            return True
    except Exception:
        pass
    return False


def check_solution_minlen():
    """before_request: вернуть Response (400) или None (пропустить)."""
    try:
        if _disabled() or request.method != 'POST':
            return None
        m = _SUBMIT_RE.match(request.path or '')
        if not m:
            return None
        from flask_login import current_user
        if not getattr(current_user, 'is_authenticated', False):
            return None
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            data = request.form.to_dict() if request.form else {}
        if _has_photo(data):
            return None
        need = min_len()
        have = _solution_len(data)
        if have >= need:
            return None
        level = _task_level(int(m.group(1)), current_user.id)
        if level is None or level < min_level():
            return None
        msg = (
            'Для задачи уровня %d нужно описать ход решения — минимум %d символов '
            '(сейчас %d). Или прикрепи фото решения из тетради.'
            % (level, need, have)
        )
        log.info(
            'solution_minlen: blocked user=%s item=%s level=%s len=%s',
            current_user.id, m.group(1), level, have,
        )
        return jsonify({
            'status': 'error',
            'error': msg,
            'message': msg,
            'code': 'solution_too_short',
            'min_len': need,
            'solution_len': have,
            'level': level,
        }), 400
    except Exception as exc:  # pragma: no cover
        log.warning('solution_minlen check failed: %s', exc)
        return None


def _inject(response):
    try:
        if _disabled() or response.status_code != 200:
            return response
        if getattr(response, 'direct_passthrough', False):
            return response
        ctype = response.headers.get('Content-Type', '') or ''
        if 'text/html' not in ctype:
            return response
        body = response.get_data(as_text=True)
        if not body or _MARKER not in body or _SCRIPT_SRC in body:
            return response
        tag = (
            '<script>window.DT_SOLUTION_MIN_LEN=%d;window.DT_SOLUTION_MIN_LEVEL=%d;</script>\n'
            '<script src="%s?v=%s" defer></script>\n'
            % (min_len(), min_level(), _SCRIPT_SRC, _VERSION)
        )
        idx = body.rfind('</body>')
        body = body + tag if idx == -1 else body[:idx] + tag + body[idx:]
        response.set_data(body)
    except Exception as exc:  # pragma: no cover
        log.warning('solution_minlen inject failed: %s', exc)
    return response


def attach(bp):
    """Повесить before_request/after_request на daily_tasks_bp (до регистрации в app)."""
    bp.before_request(check_solution_minlen)
    bp.after_request(_inject)
    log.info('DT_SOLUTION_MINLEN: attached to %s (min_len=%d, min_level=%d)',
             getattr(bp, 'name', bp), min_len(), min_level())
