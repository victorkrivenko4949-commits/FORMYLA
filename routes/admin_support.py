# -*- coding: utf-8 -*-
"""Admin support inbox + user-side support thread («Твоя поддержка»).

Маршруты:
    GET  /admin/support                 — список всех обращений + форма ответа (только админу)
    POST /admin/support/<id>/reply      — отправить ответ от админа
    GET  /my/support                    — у пользователя: его обращения + ответы админа
    POST /my/support/<id>/reply         — юзер дописывает ответ в свой тикет (двусторонний чат)
    GET  /api/my/support/unread_count   — кол-во непрочитанных ответов от админа
"""
import logging

from flask import (
    Blueprint, render_template, request, jsonify, abort, redirect,
    url_for, flash, current_app,
)
from flask_login import current_user, login_required
from sqlalchemy import text

from models import db

logger = logging.getLogger(__name__)

admin_support_bp = Blueprint('admin_support', __name__)


# ──────────────────────────────────────────────────────────────────
# AUTO-MIGRATION для таблицы support_replies
# ──────────────────────────────────────────────────────────────────
def ensure_support_replies_table():
    """Создаёт таблицу support_replies если её нет; добавляет sender_kind при апгрейде."""
    try:
        url = (current_app.config.get('SQLALCHEMY_DATABASE_URI') or '').lower()
        is_pg = url.startswith('postgresql')
        if is_pg:
            db.session.execute(text('''
                CREATE TABLE IF NOT EXISTS support_replies (
                    id SERIAL PRIMARY KEY,
                    support_message_id INTEGER NOT NULL,
                    admin_user_id INTEGER,
                    reply_text TEXT NOT NULL,
                    is_read_by_user BOOLEAN DEFAULT FALSE,
                    sender_kind VARCHAR(16) DEFAULT 'admin',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            '''))
            db.session.execute(text(
                'CREATE INDEX IF NOT EXISTS idx_support_replies_smid '
                'ON support_replies(support_message_id)'
            ))
            # ALTER для старой схемы без sender_kind
            try:
                db.session.execute(text(
                    "ALTER TABLE support_replies ADD COLUMN IF NOT EXISTS "
                    "sender_kind VARCHAR(16) DEFAULT 'admin'"
                ))
            except Exception:
                db.session.rollback()
        else:
            db.session.execute(text('''
                CREATE TABLE IF NOT EXISTS support_replies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    support_message_id INTEGER NOT NULL,
                    admin_user_id INTEGER,
                    reply_text TEXT NOT NULL,
                    is_read_by_user INTEGER DEFAULT 0,
                    sender_kind TEXT DEFAULT 'admin',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            '''))
            db.session.execute(text(
                'CREATE INDEX IF NOT EXISTS idx_support_replies_smid '
                'ON support_replies(support_message_id)'
            ))
            # SQLite: проверяем колонку и добавляем если её нет
            try:
                cols = db.session.execute(text(
                    "PRAGMA table_info(support_replies)"
                )).mappings().all()
                col_names = {c['name'] for c in cols}
                if 'sender_kind' not in col_names:
                    db.session.execute(text(
                        "ALTER TABLE support_replies ADD COLUMN sender_kind TEXT DEFAULT 'admin'"
                    ))
            except Exception:
                db.session.rollback()

        # ── CHAT_V2: фото + редактирование + удаление ───────────────
        # Колонки support_replies: attachment_* + edited_at/deleted_at.
        for _col, _type in (
            ('attachment_url', 'VARCHAR(400) NULL' if is_pg else 'TEXT NULL'),
            ('attachment_kind', 'VARCHAR(16) NULL' if is_pg else 'TEXT NULL'),
            ('attachment_name', 'VARCHAR(255) NULL' if is_pg else 'TEXT NULL'),
            ('attachment_size', 'INTEGER NULL'),
            ('edited_at', 'TIMESTAMP NULL'),
            ('deleted_at', 'TIMESTAMP NULL'),
        ):
            try:
                db.session.execute(text(
                    f"ALTER TABLE support_replies ADD COLUMN IF NOT EXISTS {_col} {_type}"
                    if is_pg else f"ALTER TABLE support_replies ADD COLUMN {_col} {_type}"
                ))
            except Exception:
                db.session.rollback()
        # support_messages: edited_at/deleted_at + фото для исходного сообщения тикета.
        for _tbl in ('support_messages',):
            for _col, _type in (
                ('edited_at', 'TIMESTAMP NULL'),
                ('deleted_at', 'TIMESTAMP NULL'),
                ('attachment_url', 'VARCHAR(400) NULL' if is_pg else 'TEXT NULL'),
                ('attachment_kind', 'VARCHAR(16) NULL' if is_pg else 'TEXT NULL'),
                ('attachment_name', 'VARCHAR(255) NULL' if is_pg else 'TEXT NULL'),
            ):
                try:
                    db.session.execute(text(
                        f"ALTER TABLE {_tbl} ADD COLUMN IF NOT EXISTS {_col} {_type}"
                        if is_pg else f"ALTER TABLE {_tbl} ADD COLUMN {_col} {_type}"
                    ))
                except Exception:
                    db.session.rollback()
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.warning('ensure_support_replies_table failed: %r', e)


def _is_admin():
    return getattr(current_user, 'is_admin', False) is True


# ──────────────────────────────────────────────────────────────────
# CHAT_V2 helpers: фото-вложения, редактирование, удаление
# ──────────────────────────────────────────────────────────────────
_SUPPORT_PHOTO_EXTS = {'jpg', 'jpeg', 'png', 'webp', 'gif'}
_SUPPORT_PHOTO_MAX = 10 * 1024 * 1024  # 10 МБ


def _save_support_photo(fs):
    """Сохранить загруженное фото в static/uploads/support/<uid>/.

    Возвращает dict с url/kind/name/size или (None, error_string).
    """
    import os, uuid
    err = None
    if not fs or not (fs.filename or '').strip():
        return None, 'Пустой файл'
    original_name = os.path.basename(fs.filename)[:255]
    ext = (original_name.rsplit('.', 1)[-1] if '.' in original_name else '').lower()
    if ext not in _SUPPORT_PHOTO_EXTS:
        return None, 'Разрешены только изображения (jpg/png/webp/gif)'
    fs.stream.seek(0, os.SEEK_END)
    size = fs.stream.tell()
    fs.stream.seek(0)
    if size <= 0:
        return None, 'Файл пустой'
    if size > _SUPPORT_PHOTO_MAX:
        return None, 'Файл больше 10 МБ'
    folder = os.path.join('static', 'uploads', 'support', str(current_user.id))
    try:
        os.makedirs(folder, exist_ok=True)
    except Exception:
        return None, 'Не удалось создать каталог'
    name = uuid.uuid4().hex + '.' + ext
    path = os.path.join(folder, name)
    try:
        fs.save(path)
    except Exception as _se:
        logger.warning('support photo save failed: %r', _se)
        return None, 'Не удалось сохранить файл'
    return {
        'url': '/static/uploads/support/%d/%s' % (current_user.id, name),
        'kind': 'image',
        'name': original_name,
        'size': size,
    }, None


def _build_messages(ticket_row, replies):
    """Собирает единый хронологический список сообщений тикета."""
    orig_deleted = bool(ticket_row.get('deleted_at'))
    messages = [{
        'sender': 'user',
        'text': '' if orig_deleted else (ticket_row.get('message') or ''),
        'created_at': ticket_row.get('created_at'),
        'edited_at': ticket_row.get('edited_at'),
        'deleted': orig_deleted,
        'attachment_url': ticket_row.get('attachment_url'),
        'attachment_kind': ticket_row.get('attachment_kind'),
        'attachment_name': ticket_row.get('attachment_name'),
        'id': f"orig-{ticket_row.get('id')}",
    }]
    for rp in replies:
        kind = (rp.get('sender_kind') or 'admin').lower()
        if kind not in ('admin', 'user'):
            kind = 'admin'
        rp_deleted = bool(rp.get('deleted_at'))
        messages.append({
            'sender': kind,
            'text': '' if rp_deleted else (rp.get('reply_text') or ''),
            'created_at': rp.get('created_at'),
            'edited_at': rp.get('edited_at'),
            'deleted': rp_deleted,
            'attachment_url': rp.get('attachment_url'),
            'attachment_kind': rp.get('attachment_kind'),
            'attachment_name': rp.get('attachment_name'),
            'id': f"rep-{rp.get('id')}",
        })
    return messages


def _can_touch_message(msg_ref, row):
    """Право на edit/delete: author или admin.

    msg_ref: 'orig-<ticket_id>' или 'rep-<reply_id>'.
    row: строка БД (dict) с колонками для проверки владения.
    """
    if _is_admin():
        # Админ может править/удалять admin-ответы; сообщения юзера — нет.
        if msg_ref.startswith('orig-'):
            return False
        return (row.get('sender_kind') or 'admin').lower() == 'admin'
    # Юзер: своё исходное сообщение тикета (orig) или свой user-ответ.
    uid = current_user.id
    if msg_ref.startswith('orig-'):
        return row.get('user_id') == uid
    return (row.get('sender_kind') or 'admin').lower() == 'user' and row.get('ticket_user_id') == uid


# ──────────────────────────────────────────────────────────────────
# 1) ADMIN INBOX
# ──────────────────────────────────────────────────────────────────
@admin_support_bp.route('/admin/support')
@login_required
def admin_support_inbox():
    if not _is_admin():
        abort(403)
    ensure_support_replies_table()

    rows = db.session.execute(text('''
        SELECT id, user_id, user_nickname, user_email, category, message,
               page_url, created_at, edited_at, deleted_at
        FROM support_messages
        ORDER BY created_at DESC
        LIMIT 500
    ''')).mappings().all()

    msg_ids = [r['id'] for r in rows]
    replies_by_msg = {}
    if msg_ids:
        in_clause = ','.join(str(int(i)) for i in msg_ids)
        rep_rows = db.session.execute(text(f'''
            SELECT id, support_message_id, admin_user_id, reply_text,
                   is_read_by_user, sender_kind, created_at,
                   edited_at, deleted_at,
                   attachment_url, attachment_kind, attachment_name
            FROM support_replies
            WHERE support_message_id IN ({in_clause})
            ORDER BY created_at ASC
        ''')).mappings().all()
        for rp in rep_rows:
            replies_by_msg.setdefault(rp['support_message_id'], []).append(dict(rp))

    tickets = []
    for r in rows:
        d = dict(r)
        d['replies'] = replies_by_msg.get(r['id'], [])
        d['has_replies'] = len(d['replies']) > 0
        d['messages'] = _build_messages(d, d['replies'])
        tickets.append(d)

    return render_template('admin/support_inbox.html', tickets=tickets)


@admin_support_bp.route('/admin/support/<int:msg_id>/reply', methods=['POST'])
@login_required
def admin_support_reply(msg_id):
    if not _is_admin():
        abort(403)
    ensure_support_replies_table()

    reply_text = (request.form.get('reply_text') or '').strip()

    # CHAT_V2: необязательное фото-вложение
    photo = request.files.get('photo')
    photo_meta = None
    if photo is not None:
        photo_meta, photo_err = _save_support_photo(photo)
        if photo_err:
            flash(photo_err, 'error')
            return redirect(url_for('admin_support.admin_support_inbox'))

    if not reply_text and not photo_meta:
        flash('Введи текст ответа или прикрепи фото', 'error')
        return redirect(url_for('admin_support.admin_support_inbox'))
    if len(reply_text) > 5000:
        flash('Ответ слишком длинный (макс 5000)', 'error')
        return redirect(url_for('admin_support.admin_support_inbox'))

    src = db.session.execute(text(
        'SELECT id, user_id, user_email, user_nickname, message '
        'FROM support_messages WHERE id = :i'
    ), {'i': msg_id}).mappings().first()
    if not src:
        flash('Сообщение не найдено', 'error')
        return redirect(url_for('admin_support.admin_support_inbox'))

    if photo_meta:
        db.session.execute(text('''
            INSERT INTO support_replies
                (support_message_id, admin_user_id, reply_text, sender_kind,
                 attachment_url, attachment_kind, attachment_name, attachment_size)
            VALUES (:smid, :aid, :txt, 'admin', :aurl, :akind, :aname, :asize)
        '''), {
            'smid': msg_id, 'aid': current_user.id, 'txt': reply_text,
            'aurl': photo_meta['url'], 'akind': photo_meta['kind'],
            'aname': photo_meta['name'], 'asize': photo_meta['size'],
        })
    else:
        db.session.execute(text('''
            INSERT INTO support_replies (support_message_id, admin_user_id, reply_text, sender_kind)
            VALUES (:smid, :aid, :txt, 'admin')
        '''), {'smid': msg_id, 'aid': current_user.id, 'txt': reply_text})
    db.session.commit()

    if src['user_email']:
        try:
            from utils.mail import send_email as resend_send, is_configured as resend_ready
            if resend_ready():
                subject = 'Ответ от поддержки FORMYLA.net'
                html = (
                    f'<p>Привет!</p>'
                    f'<p>На твоё обращение ответили:</p>'
                    f'<blockquote style="border-left:3px solid #38bdf8;padding-left:12px;color:#334155;">'
                    f'{_escape(reply_text)}'
                    f'</blockquote>'
                    f'<hr><p style="color:#64748b;font-size:12px;">Твой исходный вопрос: '
                    f'<em>{_escape((src["message"] or "")[:200])}</em></p>'
                    f'<p>Ответить можно прямо на сайте: <a href="{request.url_root}my/support">'
                    f'формыла.com/my/support</a></p>'
                )
                resend_send(src['user_email'], subject, html)
        except Exception as e:
            logger.warning('Failed to email user about reply: %r', e)

    flash('Ответ отправлен', 'success')
    return redirect(url_for('admin_support.admin_support_inbox'))


@admin_support_bp.route('/admin/support/user_intake/<int:user_id>')
@login_required
def admin_support_user_intake(user_id):
    """Админ: анкета пользователя (ответы, включая commitment, и якоря).

    Источник: CuratorState.prep_state.intake. Доступно и аккаунту поддержки
    (Lavrik): путь под разрешённым префиксом /admin/support.
    """
    if not _is_admin():
        return jsonify({'error': 'forbidden'}), 403

    import json as _json
    from models import User
    from models_curator import CuratorState

    user = db.session.get(User, user_id)
    if not user:
        return jsonify({'error': 'not_found'}), 404

    cs = CuratorState.query.filter_by(user_id=user_id).first()
    ps = getattr(cs, 'prep_state', None) if cs is not None else None
    if isinstance(ps, str):
        try:
            ps = _json.loads(ps)
        except Exception:
            ps = {}
    if not isinstance(ps, dict):
        ps = {}
    intake = ps.get('intake') or {}
    answers = intake.get('answers') or {}
    anchors = intake.get('anchor_results') or []

    return jsonify({
        'user': {
            'id': user.id,
            'name': user.name,
            'email': user.email,
            'xp': getattr(user, 'experience_points', 0) or 0,
            'problems_solved': getattr(user, 'total_problems_solved', 0) or 0,
            'created_at': user.created_at.isoformat() if getattr(user, 'created_at', None) else None,
        },
        'intake_completed': bool(intake.get('completed')),
        'answers': answers,
        'commitment': answers.get('commitment'),
        'anchors_correct': sum(1 for a in anchors if a.get('correct')),
        'anchors_total': len(anchors),
        'completed_at': intake.get('completed_at'),
    })


@admin_support_bp.route('/admin/support/user_daily3/<int:user_id>')
@login_required
def admin_support_user_daily3(user_id):
    """Админ: попытки и решения задач дня за последние 3 дня (по МСК).

    По каждому дню три источника:
      - bank_* — банковские задачи дня (BankIssue): выдано, отвечено, верно;
      - set_* — запасной контур DailyTaskSet/DailyTaskItem
        (file2/FORMYLA_BANK.jsonl + генерация): выдано, отвечено, верно.
        Именно сюда пишутся ответы пользователей без месячного плана —
        у них bank_issued всегда 0;
      - quest_* — старый DailyQuest: решено (completed_count) и кол-во
        неверных попыток (attempts_map).
    """
    if not _is_admin():
        return jsonify({'error': 'forbidden'}), 403

    import json as _json
    from datetime import datetime as _dt, timedelta as _td
    from models import DailyQuest, BankIssue, UserPresence

    # Продуктовая дата задач дня — московская.
    today_msk = (_dt.utcnow() + _td(hours=3)).date()
    days = [today_msk - _td(days=i) for i in range(3)]

    out_days = []
    for d in days:
        issues = (BankIssue.query
                  .filter(BankIssue.user_id == user_id,
                          BankIssue.issued_date == d)
                  .all())
        out_days.append({
            'date': d.isoformat(),
            'bank_issued': len(issues),
            'bank_attempts': sum(
                1 for i in issues
                if i.answered_at is not None or i.user_answer is not None
            ),
            'bank_correct': sum(1 for i in issues if bool(i.is_correct)),
            **_set_stats(user_id, d),
            **_quest_stats(user_id, d, _json),
        })

    # Возвращения: last_seen из UserPresence обновляется при любой
    # активности пользователя — по нему видно, заходил ли он после
    # регистрации (и когда в последний раз).
    presence = UserPresence.query.filter_by(user_id=user_id).first()
    last_seen = presence.last_seen if presence is not None else None

    # VISIT_COUNT_V1 (2026-09-15): число заходов. Отдельного счётчика
    # визитов в базе нет (User.last_login перезаписывается, не считает),
    # поэтому считаем ДНИ активности как прокси визитов: объединение
    # дат из DailyTaskSet (открытие страницы задач дня) + BankIssue +
    # answered_at. 1 день = 1 визит (нижняя оценка; если заходил 3 раза
    # за день — посчитается 1).
    from models import User
    from daily_tasks.models import DailyTaskSet as _DTS
    user = db.session.get(User, user_id)
    visit_days = set()
    for s in _DTS.query.filter_by(user_id=user_id).all():
        if s.target_date:
            visit_days.add(s.target_date)
    for b in BankIssue.query.filter_by(user_id=user_id).all():
        if b.issued_date:
            visit_days.add(b.issued_date)
        if b.answered_at:
            visit_days.add(b.answered_at.date())
    for s in _DTS.query.filter_by(user_id=user_id).all():
        for it in s.items.all():
            if it.answered_at:
                visit_days.add(it.answered_at.date())
    visits = len(visit_days)
    created = user.created_at.date() if getattr(user, 'created_at', None) else None
    returned = bool(visits and created and any(d > created for d in visit_days))

    # PAGE_TIME_V1 (2026-09-15): время просмотра статей/гайдов
    # (ArticleView), суммарно и по дням по московской дате.
    from models import ArticleView
    from sqlalchemy import func as _func
    from datetime import timedelta as _td3
    page_rows = (db.session.query(ArticleView.page,
                                  _func.sum(ArticleView.seconds),
                                  _func.count(ArticleView.id))
                 .filter(ArticleView.user_id == user_id)
                 .group_by(ArticleView.page).all())
    page_time = {
        str(p): {'seconds': int(s or 0), 'views': int(c or 0)}
        for p, s, c in page_rows
    }
    page_time_by_day = []
    for d in days:
        day_secs = {}
        for av in ArticleView.query.filter(ArticleView.user_id == user_id).all():
            if av.created_at and (av.created_at + _td3(hours=3)).date() == d:
                day_secs[av.page] = day_secs.get(av.page, 0) + int(av.seconds or 0)
        page_time_by_day.append({'date': d.isoformat(), 'seconds_by_page': day_secs})

    return jsonify({
        'user_id': user_id,
        'last_seen': last_seen.isoformat() if last_seen else None,
        'visits': visits,
        'visit_dates': sorted(d.isoformat() for d in visit_days),
        'returned': returned,
        'page_time': page_time,
        'page_time_by_day': page_time_by_day,
        'days': out_days,
    })


def _set_stats(user_id, day):
    """Выдано/отвечено/верно по запасному контуру DailyTaskSet за день."""
    from daily_tasks.models import DailyTaskSet, DailyTaskItem
    sets = (DailyTaskSet.query
            .filter(DailyTaskSet.user_id == user_id,
                    DailyTaskSet.target_date == day)
            .all())
    if not sets:
        return {'set_issued': 0, 'set_attempts': 0, 'set_correct': 0}
    set_ids = [s.id for s in sets]
    items = (DailyTaskItem.query
             .filter(DailyTaskItem.daily_set_id.in_(set_ids))
             .all())
    return {
        'set_issued': len(items),
        'set_attempts': sum(
            1 for i in items
            if i.answered_at is not None or i.user_answer is not None
        ),
        'set_correct': sum(1 for i in items if bool(i.is_correct)),
    }


def _quest_stats(user_id, day, _json):
    """Решено/неверные попытки по старому DailyQuest за день."""
    from models import DailyQuest
    quest = DailyQuest.query.filter_by(user_id=user_id, date=day).first()
    if quest is None:
        return {'quest_solved': 0, 'quest_wrong_attempts': 0}
    try:
        amap = _json.loads(quest.attempts_map or '{}')
        wrong = sum(int(v) for v in amap.values())
    except Exception:
        wrong = 0
    return {
        'quest_solved': int(quest.completed_count or 0),
        'quest_wrong_attempts': wrong,
    }


def _escape(s):
    """Простой HTML escape."""
    return (str(s or '')
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;')
            .replace('\n', '<br>'))


# ──────────────────────────────────────────────────────────────────
# 2) USER-SIDE PAGE: «Твоя поддержка»
# ──────────────────────────────────────────────────────────────────
@admin_support_bp.route('/my/support')
@login_required
def my_support_page():
    """Страница ученика: его обращения + переписка с админом (двусторонний чат)."""
    ensure_support_replies_table()
    uid = current_user.id

    rows = db.session.execute(text('''
        SELECT id, category, message, created_at, edited_at, deleted_at
        FROM support_messages
        WHERE user_id = :uid
        ORDER BY created_at ASC
        LIMIT 200
    '''), {'uid': uid}).mappings().all() 

    msg_ids = [r['id'] for r in rows]
    replies_by_msg = {}
    if msg_ids:
        in_clause = ','.join(str(int(i)) for i in msg_ids)
        rep_rows = db.session.execute(text(f'''
            SELECT id, support_message_id, reply_text, created_at,
                   is_read_by_user, sender_kind, edited_at, deleted_at,
                   attachment_url, attachment_kind, attachment_name
            FROM support_replies
            WHERE support_message_id IN ({in_clause})
            ORDER BY created_at ASC
        ''')).mappings().all()
        for rp in rep_rows:
            replies_by_msg.setdefault(rp['support_message_id'], []).append(dict(rp))

        # Помечаем ВСЕ ответы админа как прочитанные (свои сообщения уже read)
        try:
            is_pg = (current_app.config.get('SQLALCHEMY_DATABASE_URI') or '').lower().startswith('postgresql')
            true_lit = 'TRUE' if is_pg else '1'
            false_lit = 'FALSE' if is_pg else '0'
            db.session.execute(text(f'''
                UPDATE support_replies SET is_read_by_user = {true_lit}
                WHERE support_message_id IN ({in_clause})
                  AND sender_kind = 'admin'
                  AND (is_read_by_user IS NULL OR is_read_by_user = {false_lit})
            '''))
            db.session.commit()
        except Exception:
            db.session.rollback()

    tickets = []
    for r in rows:
        d = dict(r)
        replies = replies_by_msg.get(r['id'], [])
        d['replies'] = replies
        d['messages'] = _build_messages(d, replies)
        # last_status: ждём ответа админа, если последнее сообщение от юзера
        last_sender = d['messages'][-1]['sender'] if d['messages'] else 'user'
        d['status'] = 'waiting' if last_sender == 'user' else 'replied'
        tickets.append(d)

    return render_template('my_support.html', tickets=tickets)


@admin_support_bp.route('/my/support/<int:msg_id>/reply', methods=['POST'])
@login_required
def my_support_reply(msg_id):
    """Юзер дописывает ответ в свой тикет (двусторонний чат)."""
    ensure_support_replies_table()

    reply_text = (request.form.get('reply_text') or '').strip()

    # CHAT_V2: необязательное фото-вложение
    photo = request.files.get('photo')
    photo_meta = None
    if photo is not None:
        photo_meta, photo_err = _save_support_photo(photo)
        if photo_err:
            flash(photo_err, 'error')
            return redirect(url_for('admin_support.my_support_page'))

    if not reply_text and not photo_meta:
        flash('Введи текст сообщения или прикрепи фото', 'error')
        return redirect(url_for('admin_support.my_support_page'))
    if len(reply_text) > 5000:
        flash('Сообщение слишком длинное (макс 5000)', 'error')
        return redirect(url_for('admin_support.my_support_page'))

    # Проверяем что тикет принадлежит текущему юзеру
    src = db.session.execute(text(
        'SELECT id, user_id, user_email, user_nickname, message '
        'FROM support_messages WHERE id = :i'
    ), {'i': msg_id}).mappings().first()
    if not src:
        flash('Тикет не найден', 'error')
        return redirect(url_for('admin_support.my_support_page'))
    if src['user_id'] != current_user.id:
        abort(403)

    # INSERT user reply (is_read_by_user=True — юзер сам читал что написал)
    try:
        is_pg = (current_app.config.get('SQLALCHEMY_DATABASE_URI') or '').lower().startswith('postgresql')
        true_lit = True if is_pg else 1
        _params = {'smid': msg_id, 'txt': reply_text, 'read': true_lit}
        if photo_meta:
            _params.update({
                'aurl': photo_meta['url'], 'akind': photo_meta['kind'],
                'aname': photo_meta['name'], 'asize': photo_meta['size'],
            })
            db.session.execute(text('''
                INSERT INTO support_replies
                    (support_message_id, admin_user_id, reply_text, sender_kind,
                     is_read_by_user, attachment_url, attachment_kind,
                     attachment_name, attachment_size)
                VALUES (:smid, NULL, :txt, 'user', :read,
                        :aurl, :akind, :aname, :asize)
            '''), _params)
        else:
            db.session.execute(text('''
                INSERT INTO support_replies
                    (support_message_id, admin_user_id, reply_text, sender_kind, is_read_by_user)
                VALUES (:smid, NULL, :txt, 'user', :read)
            '''), _params)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.warning('my_support_reply insert failed: %r', e)
        flash('Не удалось отправить сообщение', 'error')
        return redirect(url_for('admin_support.my_support_page'))

    # Опционально: уведомить админа по email
    try:
        admin_email = current_app.config.get('ADMIN_EMAIL') or current_app.config.get('SUPPORT_EMAIL')
        if admin_email:
            from utils.mail import send_email as resend_send, is_configured as resend_ready
            if resend_ready():
                subject = f'Новое сообщение в тикете #{msg_id} от {getattr(current_user, "nickname", "юзера")}'
                html = (
                    f'<p>Юзер <strong>{_escape(getattr(current_user, "nickname", "") or current_user.id)}</strong> '
                    f'дописал в тикете #{msg_id}:</p>'
                    f'<blockquote style="border-left:3px solid #38ef7d;padding-left:12px;color:#334155;">'
                    f'{_escape(reply_text)}'
                    f'</blockquote>'
                    f'<hr><p style="color:#64748b;font-size:12px;">Исходный вопрос: '
                    f'<em>{_escape((src["message"] or "")[:200])}</em></p>'
                    f'<p><a href="{request.url_root}admin/support">Открыть инбокс</a></p>'
                )
                resend_send(admin_email, subject, html)
    except Exception as e:
        logger.warning('Failed to email admin about user reply: %r', e)

    flash('Сообщение отправлено', 'success')
    return redirect(url_for('admin_support.my_support_page'))


@admin_support_bp.route('/api/my/support/messages')
@login_required
def my_support_messages_api():
    """Возвращает ВСЕ сообщения текущего юзера + ответы админа.

    Используется виджетом «Связаться с нами» на /about для:
    1) Восстановления истории при загрузке страницы (persistence).
    2) Polling-а каждые ~15 сек — чтобы видеть ответы админа без перезагрузки.

    Формат ответа:
        {
          "success": true,
          "messages": [
            {"from": "user"|"admin", "text": "...",
             "created_at": "ISO8601", "ticket_id": int, "id": "orig-..."|"rep-..."},
            ...
          ]
        }
    Сортировка — хронологическая (ASC) по created_at.
    """
    ensure_support_replies_table()
    uid = current_user.id

    try:
        ticket_rows = db.session.execute(text('''
            SELECT id, category, message, created_at, edited_at, deleted_at
            FROM support_messages
            WHERE user_id = :uid
            ORDER BY created_at ASC
            LIMIT 500
        '''), {'uid': uid}).mappings().all()

        msg_ids = [r['id'] for r in ticket_rows]
        rep_rows = []
        if msg_ids:
            in_clause = ','.join(str(int(i)) for i in msg_ids)
            rep_rows = db.session.execute(text(f'''
                SELECT id, support_message_id, reply_text, created_at, sender_kind,
                       edited_at, deleted_at,
                       attachment_url, attachment_kind, attachment_name
                FROM support_replies
                WHERE support_message_id IN ({in_clause})
                ORDER BY created_at ASC
            ''')).mappings().all()

        def _iso(ts):
            return ts.isoformat() if hasattr(ts, 'isoformat') else (str(ts) if ts else '')

        all_msgs = []
        for m in ticket_rows:
            deleted = bool(m.get('deleted_at'))
            all_msgs.append({
                'id': f"orig-{m['id']}",
                'from': 'user',
                'text': '' if deleted else (m['message'] or ''),
                'created_at': _iso(m['created_at']),
                'edited_at': _iso(m.get('edited_at')),
                'deleted': deleted,
                'attachment_url': m.get('attachment_url'),
                'attachment_kind': m.get('attachment_kind'),
                'attachment_name': m.get('attachment_name'),
                'ticket_id': m['id'],
            })
        for r in rep_rows:
            kind = (r['sender_kind'] or 'admin').lower()
            if kind not in ('admin', 'user'):
                kind = 'admin'
            deleted = bool(r.get('deleted_at'))
            all_msgs.append({
                'id': f"rep-{r['id']}",
                'from': kind,
                'text': '' if deleted else (r['reply_text'] or ''),
                'created_at': _iso(r['created_at']),
                'edited_at': _iso(r.get('edited_at')),
                'deleted': deleted,
                'attachment_url': r.get('attachment_url'),
                'attachment_kind': r.get('attachment_kind'),
                'attachment_name': r.get('attachment_name'),
                'ticket_id': r['support_message_id'],
            })

        all_msgs.sort(key=lambda x: x['created_at'] or '')

        # Помечаем все ответы админа как прочитанные (раз юзер их сейчас увидит)
        if msg_ids:
            try:
                is_pg = (current_app.config.get('SQLALCHEMY_DATABASE_URI') or '').lower().startswith('postgresql')
                true_lit = 'TRUE' if is_pg else '1'
                false_lit = 'FALSE' if is_pg else '0'
                in_clause = ','.join(str(int(i)) for i in msg_ids)
                db.session.execute(text(f'''
                    UPDATE support_replies SET is_read_by_user = {true_lit}
                    WHERE support_message_id IN ({in_clause})
                      AND sender_kind = 'admin'
                      AND (is_read_by_user IS NULL OR is_read_by_user = {false_lit})
                '''))
                db.session.commit()
            except Exception:
                db.session.rollback()

        return jsonify({'success': True, 'messages': all_msgs})
    except Exception as e:
        logger.warning('my_support_messages_api failed: %r', e)
        return jsonify({'success': False, 'messages': [], 'error': str(e)}), 500


# ──────────────────────────────────────────────────────────────────
# CHAT_V2: редактирование и удаление сообщений (обе стороны)
# ──────────────────────────────────────────────────────────────────
def _fetch_support_msg(msg_ref):
    """Достать сообщение по ссылке вида 'orig-12' / 'rep-34'.

    Возвращает (row_dict, table_name) или (None, None).
    """
    try:
        prefix, _, sid = msg_ref.partition('-')
        row_id = int(sid)
    except (ValueError, AttributeError):
        return None, None
    if prefix == 'orig':
        row = db.session.execute(text('''
            SELECT id, user_id, message, deleted_at
            FROM support_messages WHERE id = :i
        '''), {'i': row_id}).mappings().first()
        if row:
            return dict(row), 'support_messages'
    elif prefix == 'rep':
        row = db.session.execute(text('''
            SELECT sr.id, sr.support_message_id, sr.reply_text, sr.sender_kind,
                   sr.deleted_at, sm.user_id AS ticket_user_id
            FROM support_replies sr
            JOIN support_messages sm ON sm.id = sr.support_message_id
            WHERE sr.id = :i
        '''), {'i': row_id}).mappings().first()
        if row:
            return dict(row), 'support_replies'
    return None, None


@admin_support_bp.route('/api/support/message/<msg_ref>/edit', methods=['POST'])
@login_required
def support_message_edit(msg_ref):
    """Изменить текст своего сообщения. Отмечается как «изменено»."""
    ensure_support_replies_table()
    new_text = (request.form.get('text') or '').strip()
    if not new_text or len(new_text) > 5000:
        return jsonify({'error': 'текст 1-5000 символов'}), 400

    row, table = _fetch_support_msg(msg_ref)
    if not row:
        return jsonify({'error': 'Сообщение не найдено'}), 404
    if row.get('deleted_at'):
        return jsonify({'error': 'Сообщение удалено'}), 400
    if not _can_touch_message(msg_ref, row):
        return jsonify({'error': 'Можно редактировать только свои сообщения'}), 403

    col = 'message' if table == 'support_messages' else 'reply_text'
    db.session.execute(text(f'''
        UPDATE {table}
        SET {col} = :txt, edited_at = CURRENT_TIMESTAMP
        WHERE id = :i
    '''), {'txt': new_text, 'i': row['id']})
    db.session.commit()
    return jsonify({'success': True, 'id': msg_ref, 'text': new_text, 'edited': True})


@admin_support_bp.route('/api/support/message/<msg_ref>/delete', methods=['POST'])
@login_required
def support_message_delete(msg_ref):
    """Удалить своё сообщение (мягкое удаление — показываем «сообщение удалено»)."""
    ensure_support_replies_table()
    row, table = _fetch_support_msg(msg_ref)
    if not row:
        return jsonify({'error': 'Сообщение не найдено'}), 404
    if not _can_touch_message(msg_ref, row):
        return jsonify({'error': 'Можно удалять только свои сообщения'}), 403

    db.session.execute(text(f'''
        UPDATE {table}
        SET deleted_at = CURRENT_TIMESTAMP
        WHERE id = :i
    '''), {'i': row['id']})
    db.session.commit()
    return jsonify({'success': True, 'id': msg_ref, 'deleted': True})


@admin_support_bp.route('/api/my/support/unread_count')
@login_required
def my_support_unread_count():
    """Сколько непрочитанных ответов от админа у текущего юзера."""
    ensure_support_replies_table()
    try:
        is_pg = (current_app.config.get('SQLALCHEMY_DATABASE_URI') or '').lower().startswith('postgresql')
        false_lit = 'FALSE' if is_pg else '0'
        result = db.session.execute(text(f'''
            SELECT COUNT(*) AS cnt FROM support_replies sr
            JOIN support_messages sm ON sm.id = sr.support_message_id
            WHERE sm.user_id = :uid
              AND sr.sender_kind = 'admin'
              AND (sr.is_read_by_user IS NULL OR sr.is_read_by_user = {false_lit})
        '''), {'uid': current_user.id}).scalar()
        return jsonify({'unread': int(result or 0)})
    except Exception as e:
        logger.warning('unread_count failed: %r', e)
        return jsonify({'unread': 0})


# ──────────────────────────────────────────────────────────────────
# 3) ADMIN USERS STATS V2 — богатая статистика пользователей
#    (только для админов: Victor + Lavrik)
# ──────────────────────────────────────────────────────────────────
# USERS_STATS_V2: события сайта (входы / heartbeat) и дневной пик онлайна.
def ensure_site_events_tables():
    """Auto-migration: site_events + site_daily_peak. Безопасно вызывать часто."""
    try:
        uri = (current_app.config.get('SQLALCHEMY_DATABASE_URI') or '').lower()
        is_pg = uri.startswith('postgresql')
        if is_pg:
            db.session.execute(text('''
                CREATE TABLE IF NOT EXISTS site_events (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    kind VARCHAR(16) NOT NULL,
                    seconds INTEGER NOT NULL DEFAULT 0,
                    ts TIMESTAMP NOT NULL DEFAULT NOW()
                )
            '''))
            db.session.execute(text('''
                CREATE INDEX IF NOT EXISTS idx_site_events_ts ON site_events(ts)
            '''))
            db.session.execute(text('''
                CREATE INDEX IF NOT EXISTS idx_site_events_user_ts ON site_events(user_id, ts)
            '''))
            db.session.execute(text('''
                CREATE TABLE IF NOT EXISTS site_daily_peak (
                    day DATE PRIMARY KEY,
                    max_online INTEGER NOT NULL DEFAULT 0
                )
            '''))
        else:
            db.session.execute(text('''
                CREATE TABLE IF NOT EXISTS site_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    kind VARCHAR(16) NOT NULL,
                    seconds INTEGER NOT NULL DEFAULT 0,
                    ts DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            '''))
            db.session.execute(text('''
                CREATE INDEX IF NOT EXISTS idx_site_events_ts ON site_events(ts)
            '''))
            db.session.execute(text('''
                CREATE TABLE IF NOT EXISTS site_daily_peak (
                    day DATE PRIMARY KEY,
                    max_online INTEGER NOT NULL DEFAULT 0
                )
            '''))
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.warning('ensure_site_events_tables: %r', e)


ONLINE_WINDOW_SEC = 300  # 5 минут — «онлайн»


def log_site_event(user_id: int, kind: str, seconds: int = 0) -> None:
    """Публичный помощник: фиксирует событие (login/heartbeat), бьёт presence,
    обновляет дневной пик одновременных пользователей. Вызывать из heartbeat
    и точек входа. Никогда не бросает исключений наружу."""
    try:
        ensure_site_events_tables()
        db.session.execute(text('''
            INSERT INTO site_events (user_id, kind, seconds, ts)
            VALUES (:uid, :kind, :sec, CURRENT_TIMESTAMP)
        '''), {'uid': user_id, 'kind': kind, 'sec': int(seconds)})
        # presence
        db.session.execute(text('''
            UPDATE user_presence SET last_seen = CURRENT_TIMESTAMP WHERE user_id = :uid
        '''), {'uid': user_id})
        db.session.execute(text('''
            INSERT INTO user_presence (user_id, last_seen)
            SELECT :uid, CURRENT_TIMESTAMP
            WHERE NOT EXISTS (SELECT 1 FROM user_presence WHERE user_id = :uid)
        '''), {'uid': user_id})
        # пик онлайна за сегодня
        uri = (current_app.config.get('SQLALCHEMY_DATABASE_URI') or '').lower()
        is_pg = uri.startswith('postgresql')
        if is_pg:
            online_now = db.session.execute(text('''
                SELECT COUNT(*) FROM user_presence
                WHERE last_seen > NOW() - INTERVAL '5 minutes'
            ''')).scalar() or 0
            db.session.execute(text('''
                INSERT INTO site_daily_peak (day, max_online)
                VALUES (CURRENT_DATE, :n)
                ON CONFLICT (day) DO UPDATE
                SET max_online = GREATEST(site_daily_peak.max_online, EXCLUDED.max_online)
            '''), {'n': online_now})
        else:
            online_now = db.session.execute(text('''
                SELECT COUNT(*) FROM user_presence
                WHERE last_seen > datetime('now', '-5 minutes')
            ''')).scalar() or 0
            db.session.execute(text('''
                INSERT INTO site_daily_peak (day, max_online)
                VALUES (date('now'), :n)
                ON CONFLICT(day) DO UPDATE
                SET max_online = MAX(max_online, excluded.max_online)
            '''), {'n': online_now})
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.warning('log_site_event failed: %r', e)


@admin_support_bp.route('/admin/users')
@login_required
def admin_users_stats():
    """USERS_STATS_V2: богатая статистика — онлайн, DAU/WAU/MAU, по дням,
    пики одновременных, топы по активности/XP/задачам, почасовой график."""
    if not _is_admin():
        abort(403)
    ensure_site_events_tables()

    from models import User
    from datetime import datetime, timedelta

    uri = (current_app.config.get('SQLALCHEMY_DATABASE_URI') or '').lower()
    is_pg = uri.startswith('postgresql')
    now = datetime.utcnow()
    today = now.date()

    users = (User.query
             .filter(User.is_guest == False)
             .order_by(User.experience_points.desc())
             .all())

    # presence: онлайн прямо сейчас (last_seen < 5 мин назад)
    presence_rows = db.session.execute(text(
        'SELECT user_id, last_seen FROM user_presence'
    )).fetchall()
    presence_map = {r[0]: r[1] for r in presence_rows}

    rows = []
    for u in users:
        seen = presence_map.get(u.id)
        online = bool(seen and (now - seen).total_seconds() < ONLINE_WINDOW_SEC)
        rows.append({
            'id': u.id,
            'nickname': u.nickname or '—',
            'name': u.name or '—',
            'email': u.email or '—',
            'created_at': u.created_at.strftime('%d.%m.%Y') if u.created_at else '—',
            'last_login': u.last_login.strftime('%d.%m.%Y %H:%M') if u.last_login else '—',
            'login_count': u.login_count or 0,
            'problems': u.total_problems_solved or 0,
            'level': u.current_level or 1,
            'xp': u.experience_points or 0,
            'seconds': u.site_seconds_total or 0,
            'minutes': round((u.site_seconds_total or 0) / 60, 1),
            'hours': round((u.site_seconds_total or 0) / 3600, 2),
            'online': online,
        })

    online_now = sum(1 for r in rows if r['online'])

    # ---------- по дням (14 дней) ----------
    day_expr = "DATE(ts)" if is_pg else "DATE(ts)"
    ev_rows = db.session.execute(text(f'''
        SELECT {day_expr} AS day,
               COUNT(DISTINCT user_id) AS active_users,
               COUNT(DISTINCT CASE WHEN kind='login' THEN user_id END) AS login_users,
               SUM(seconds) AS seconds_total,
               COUNT(*) AS events
        FROM site_events
        WHERE ts >= :since
        GROUP BY {day_expr}
        ORDER BY day
    '''), {'since': today - timedelta(days=13)}).fetchall()
    by_day = []
    for r in ev_rows:
        by_day.append({
            'day': str(r[0]),
            'active': int(r[1] or 0),
            'logins': int(r[2] or 0),
            'hours': round((r[3] or 0) / 3600.0, 2),
            'events': int(r[4] or 0),
        })
    # дополняем нулями дни без событий
    day_map = {d['day']: d for d in by_day}
    by_day = []
    for i in range(13, -1, -1):
        d = today - timedelta(days=i)
        key = d.isoformat()
        by_day.append(day_map.get(key, {'day': key, 'active': 0, 'logins': 0, 'hours': 0.0, 'events': 0}))

    # регистрации по дням (новые пользователи) — users.created_at
    reg_rows = db.session.execute(text('''
        SELECT DATE(created_at) AS day, COUNT(*) AS cnt
        FROM users
        WHERE is_guest = FALSE AND created_at >= :since
        GROUP BY DATE(created_at)
        ORDER BY day
    ''' if is_pg else '''
        SELECT DATE(created_at) AS day, COUNT(*) AS cnt
        FROM users
        WHERE is_guest = 0 AND created_at >= :since
        GROUP BY DATE(created_at)
        ORDER BY day
    '''), {'since': today - timedelta(days=13)}).fetchall()
    reg_map = {str(r[0]): int(r[1]) for r in reg_rows}

    # пик одновременных за сегодня / вчера / всё время
    peak_rows = db.session.execute(text('SELECT day, max_online FROM site_daily_peak')).fetchall()
    peak_map = {str(r[0]): int(r[1]) for r in peak_rows}
    peak_today = peak_map.get(today.isoformat(), online_now)
    peak_yesterday = peak_map.get((today - timedelta(days=1)).isoformat(), 0)
    peak_ever = max(peak_map.values(), default=online_now)

    # DAU / WAU / MAU
    dau = db.session.execute(text('''
        SELECT COUNT(DISTINCT user_id) FROM site_events WHERE ts >= :since
    '''), {'since': today}).scalar() or 0
    wau = db.session.execute(text('''
        SELECT COUNT(DISTINCT user_id) FROM site_events WHERE ts >= :since
    '''), {'since': today - timedelta(days=7)}).scalar() or 0
    mau = db.session.execute(text('''
        SELECT COUNT(DISTINCT user_id) FROM site_events WHERE ts >= :since
    '''), {'since': today - timedelta(days=30)}).scalar() or 0

    # задачи решённые за сегодня / 7 дней (daily_task_items answered_at)
    solved_today = db.session.execute(text('''
        SELECT COUNT(*) FROM daily_task_items
        WHERE answered_at >= :since AND is_correct IS TRUE
    ''' if is_pg else '''
        SELECT COUNT(*) FROM daily_task_items
        WHERE answered_at >= :since AND is_correct = 1
    '''), {'since': today}).scalar() or 0
    solved_week = db.session.execute(text('''
        SELECT COUNT(*) FROM daily_task_items
        WHERE answered_at >= :since AND is_correct IS TRUE
    ''' if is_pg else '''
        SELECT COUNT(*) FROM daily_task_items
        WHERE answered_at >= :since AND is_correct = 1
    '''), {'since': today - timedelta(days=7)}).scalar() or 0

    # почасовое распределение за сегодня (heartbeat + login)
    hour_expr = "EXTRACT(HOUR FROM ts)" if is_pg else "CAST(strftime('%H', ts) AS INTEGER)"
    hour_rows = db.session.execute(text(f'''
        SELECT {hour_expr} AS h, COUNT(DISTINCT user_id) AS u
        FROM site_events WHERE ts >= :since GROUP BY {hour_expr} ORDER BY h
    '''), {'since': today}).fetchall()
    by_hour = [0] * 24
    for h, cnt in hour_rows:
        by_hour[int(h)] = int(cnt)

    # топ по XP / задачам / времени
    top_xp = sorted(rows, key=lambda r: r['xp'], reverse=True)[:5]
    top_problems = sorted(rows, key=lambda r: r['problems'], reverse=True)[:5]
    top_time = sorted(rows, key=lambda r: r['seconds'], reverse=True)[:5]

    # отвалившиеся: последний вход > 7 дней назад или нет входа
    week_ago = now - timedelta(days=7)
    inactive = [r for r in rows if r['last_login'] == '—'
                or datetime.strptime(r['last_login'], '%d.%m.%Y %H:%M') < week_ago]
    inactive = sorted(inactive, key=lambda r: r['xp'], reverse=True)[:10]

    # USERS_STATS_V2: последние фото-решения по каждому пользователю
    photo_items = []  # каждый: {nickname, when, url, kind, correct}
    if is_pg:
        ph_rows = db.session.execute(text('''
            SELECT bi.user_id, bi.answered_at, bi.solution_photos_json,
                   bi.is_correct, u.nickname, 'bank' AS kind
            FROM bank_issues bi JOIN users u ON u.id = bi.user_id
            WHERE bi.solution_photos_json IS NOT NULL AND bi.answered_at IS NOT NULL
            UNION ALL
            SELECT ds.user_id, dti.answered_at, dti.solution_photos_json,
                   dti.is_correct, u.nickname, 'set' AS kind
            FROM daily_task_items dti
            JOIN daily_task_sets ds ON ds.id = dti.daily_set_id
            JOIN users u ON u.id = ds.user_id
            WHERE dti.solution_photos_json IS NOT NULL AND dti.answered_at IS NOT NULL
            UNION ALL
            SELECT sa.user_id, sa.created_at, sa.file_path,
                   NULL, u.nickname, 'attempt' AS kind
            FROM solution_attempts sa JOIN users u ON u.id = sa.user_id
            WHERE sa.attempt_type = 'daily' AND sa.file_path IS NOT NULL
        ''')).fetchall()
    else:
        ph_rows = db.session.execute(text('''
            SELECT bi.user_id, bi.answered_at, bi.solution_photos_json,
                   bi.is_correct, u.nickname, 'bank' AS kind
            FROM bank_issues bi JOIN users u ON u.id = bi.user_id
            WHERE bi.solution_photos_json IS NOT NULL AND bi.answered_at IS NOT NULL
            UNION ALL
            SELECT ds.user_id, dti.answered_at, dti.solution_photos_json,
                   dti.is_correct, u.nickname, 'set' AS kind
            FROM daily_task_items dti
            JOIN daily_task_sets ds ON ds.id = dti.daily_set_id
            JOIN users u ON u.id = ds.user_id
            WHERE dti.solution_photos_json IS NOT NULL AND dti.answered_at IS NOT NULL
            UNION ALL
            SELECT sa.user_id, sa.created_at, sa.file_path,
                   NULL, u.nickname, 'attempt' AS kind
            FROM solution_attempts sa JOIN users u ON u.id = sa.user_id
            WHERE sa.attempt_type = 'daily' AND sa.file_path IS NOT NULL
        ''')).fetchall()
    import json as _json
    for uid, when, photos_json, correct, nickname, kind in ph_rows:
        if kind == 'attempt':
            urls = [photos_json]
        else:
            try:
                urls = _json.loads(photos_json) or []
            except Exception:
                urls = []
        for url in urls:
            photo_items.append({
                'user_id': uid,
                'nickname': nickname or '—',
                'when': when.strftime('%d.%m %H:%M') if when else '—',
                'url': url,
                'correct': correct,
            })
    photo_items.sort(key=lambda x: x['when'], reverse=True)
    photo_items = photo_items[:60]

    total = {
        'users': len(rows),
        'online_now': online_now,
        'logins': sum(r['login_count'] for r in rows),
        'problems': sum(r['problems'] for r in rows),
        'seconds': sum(r['seconds'] for r in rows),
        'dau': dau,
        'wau': wau,
        'mau': mau,
        'peak_today': peak_today,
        'peak_yesterday': peak_yesterday,
        'peak_ever': peak_ever,
        'solved_today': solved_today,
        'solved_week': solved_week,
        'photos_total': len(photo_items),
    }
    return render_template('admin/users_stats.html', rows=rows, total=total,
                           by_day=by_day, reg_map=reg_map, by_hour=by_hour,
                           top_xp=top_xp, top_problems=top_problems,
                           top_time=top_time, inactive=inactive,
                           photo_items=photo_items)
