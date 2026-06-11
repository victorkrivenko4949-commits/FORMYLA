# -*- coding: utf-8 -*-
"""Email-уведомления для FORMYLA: support-форма и отзывы."""
import logging
import os


def _esc(s):
    if not s:
        return ''
    return (str(s).replace('&', '&amp;')
                  .replace('<', '&lt;')
                  .replace('>', '&gt;'))


def send_support_email(mail_instance, *, nickname, email, category,
                       message, page_url, user_agent, ip, ticket_id,
                       attachments=None):
    """Отправить обращение поддержки.
    attachments: список tuples (filename, content_type, bytes).
    Возвращает (ok, error)."""
    from flask_mail import Message
    attachments = attachments or []

    owner_email = (os.environ.get('SUPPORT_NOTIFY_EMAIL')
                   or os.environ.get('MAIL_USERNAME'))
    if owner_email == 'resend' or not owner_email or '@' not in str(owner_email):
        owner_email = os.environ.get('MAIL_DEFAULT_SENDER') or None
    if not owner_email or '@' not in str(owner_email):
        return False, ('Получатель не настроен. Задайте SUPPORT_NOTIFY_EMAIL в env.')

    cat_labels = {
        'bug': 'Bug',
        'suggestion': 'Suggestion',
        'question': 'Question',
        'other': 'Message',
    }
    cat_label = cat_labels.get(category, 'Message')

    subject = '[FORMYLA #' + str(ticket_id) + '] ' + cat_label
    subject += ' from ' + (nickname or 'Guest')

    lines = [cat_label, 'Ticket: #' + str(ticket_id), '',
             'User: ' + (nickname or 'Guest')]
    if email:
        lines.append('Email: ' + email)
    lines.extend(['', 'Message:', message, ''])
    if page_url:
        lines.append('Page: ' + page_url)
    if ip:
        lines.append('IP: ' + ip)
    if user_agent:
        lines.append('UA: ' + user_agent)
    body = '\n'.join(lines)

    parts = [
        '<div style="font-family:-apple-system,sans-serif;max-width:600px;'
        'margin:0 auto;">',
        '<h2 style="color:#7c3aed;">' + cat_label + ' &mdash; FORMYLA</h2>',
        '<p><b>Ticket:</b> #' + str(ticket_id) + '</p>',
        '<p><b>User:</b> ' + _esc(nickname or 'Guest') + '</p>',
    ]
    if email:
        parts.append('<p><b>Email:</b> ' + _esc(email) + '</p>')
    parts.append('<hr style="border:1px solid #e2e8f0;">')
    parts.append('<p><b>Message:</b></p>')
    parts.append(
        '<div style="background:#f8fafc;padding:16px;border-radius:8px;'
        'white-space:pre-wrap;">' + _esc(message) + '</div>'
    )
    parts.append('<hr style="border:1px solid #e2e8f0;">')
    meta = []
    if page_url:
        meta.append('Page: ' + _esc(page_url))
    if ip:
        meta.append('IP: ' + _esc(ip))
    if meta:
        parts.append('<p style="color:#94a3b8;font-size:12px;">'
                     + '<br>'.join(meta) + '</p>')
    # Список приложений (для отображения в email)
    if attachments:
        parts.append('<hr style="border:1px solid #e2e8f0;">')
        parts.append('<p><b>Вложения:</b></p><ul style="padding-left:18px;">')
        for fname, _ctype, _data in attachments:
            try:
                _size_kb = len(_data) / 1024.0
                parts.append(
                    '<li>' + _esc(fname)
                    + ' <span style="color:#94a3b8;font-size:12px;">('
                    + ('%.1f КБ' % _size_kb if _size_kb < 1024 else '%.1f МБ' % (_size_kb / 1024))
                    + ')</span></li>'
                )
            except Exception:
                parts.append('<li>' + _esc(fname) + '</li>')
        parts.append('</ul>')
        body += '\n\nВложения:\n' + '\n'.join(' - ' + a[0] for a in attachments)

    parts.append('</div>')
    html = ''.join(parts)

    # ── 1) Пробуем Resend HTTP API — без зависимости от SMTP. ──
    try:
        from utils.mail import send_email as _resend_send, is_configured as _resend_ready
        if _resend_ready():
            # Resend API: attachments как list of {filename, content (base64)}
            resend_attachments = None
            if attachments:
                import base64 as _b64
                resend_attachments = [
                    {
                        'filename': fname,
                        'content': _b64.b64encode(data).decode('ascii'),
                    }
                    for fname, _ctype, data in attachments
                ]
            try:
                _resend_send(
                    to=owner_email,
                    subject=subject,
                    html=html,
                    text=body,
                    reply_to=email if email else None,
                    attachments=resend_attachments,
                )
            except TypeError:
                # send_email может не поддерживать attachments — пробуем без них
                _resend_send(
                    to=owner_email,
                    subject=subject,
                    html=html,
                    text=body,
                    reply_to=email if email else None,
                )
            return True, None
    except Exception as e:
        logging.warning('support email via Resend failed, will try SMTP: %s', e)

    # ── 2) Fallback: Flask-Mail SMTP ───────────────────────────────────────
    try:
        if mail_instance is None:
            return False, 'mail_instance is None and Resend not configured'
        msg = Message(
            subject=subject,
            recipients=[owner_email],
            body=body,
            html=html,
            reply_to=email if email else None,
        )
        for fname, ctype, data in attachments:
            try:
                msg.attach(fname, ctype or 'application/octet-stream', data)
            except Exception as _att_err:
                logging.warning('attach failed (%s): %s', fname, _att_err)
        mail_instance.send(msg)
        return True, None
    except Exception as e:
        logging.exception('support email send failed (both Resend and SMTP)')
        return False, str(e)


def send_review_email(mail_instance, *, nickname, email, rating, message,
                      page_url, user_agent, ip, ticket_id):
    """Отправить отзыв пользователя владельцу.
       Получатель: env REVIEW_NOTIFY_EMAIL → SUPPORT_NOTIFY_EMAIL → MAIL_USERNAME.
       Возвращает (ok, error).

       Стратегия отправки:
       1) Resend HTTP API (utils.mail.send_email) — основной путь.
       2) Flask-Mail SMTP — fallback если Resend не настроен.
    """
    owner_email = (
        os.environ.get('REVIEW_NOTIFY_EMAIL')
        or os.environ.get('SUPPORT_NOTIFY_EMAIL')
        or os.environ.get('MAIL_USERNAME')
    )
    # MAIL_USERNAME может быть равен "resend" — это SMTP-юзер, а не адрес.
    if owner_email == 'resend' or not owner_email or '@' not in str(owner_email):
        owner_email = os.environ.get('MAIL_DEFAULT_SENDER') or None
    if not owner_email or '@' not in str(owner_email):
        return False, ('Получатель отзыва не настроен. Задайте '
                       'REVIEW_NOTIFY_EMAIL или SUPPORT_NOTIFY_EMAIL в env.')

    try:
        r = int(rating) if rating is not None else 0
    except (TypeError, ValueError):
        r = 0
    if r < 0:
        r = 0
    if r > 5:
        r = 5
    stars = ('★' * r) + ('☆' * (5 - r)) if r > 0 else '(без оценки)'

    subject = '[FORMYLA отзыв #' + str(ticket_id) + '] '
    subject += stars + ' от ' + (nickname or 'Гость')

    lines = [
        'Новый отзыв на FORMYLA',
        'Тикет: #' + str(ticket_id),
        'Оценка: ' + stars + (' (' + str(r) + '/5)' if r > 0 else ''),
        '',
        'Пользователь: ' + (nickname or 'Гость'),
    ]
    if email:
        lines.append('Email: ' + email)
    lines.extend(['', 'Текст отзыва:', message, ''])
    if page_url:
        lines.append('Страница: ' + page_url)
    if ip:
        lines.append('IP: ' + ip)
    if user_agent:
        lines.append('User-Agent: ' + user_agent)
    body = '\n'.join(lines)

    parts = [
        '<div style="font-family:-apple-system,sans-serif;max-width:600px;'
        'margin:0 auto;">',
        '<h2 style="color:#10b981;">Новый отзыв &mdash; FORMYLA</h2>',
        '<p><b>Тикет:</b> #' + str(ticket_id) + '</p>',
        '<p style="font-size:22px;letter-spacing:2px;color:#f59e0b;">'
        + stars + '</p>',
        '<p><b>Пользователь:</b> ' + _esc(nickname or 'Гость') + '</p>',
    ]
    if email:
        parts.append('<p><b>Email:</b> ' + _esc(email) + '</p>')
    parts.append('<hr style="border:1px solid #e2e8f0;">')
    parts.append('<p><b>Отзыв:</b></p>')
    parts.append(
        '<div style="background:#f0fdf4;padding:16px;border-radius:8px;'
        'border-left:4px solid #10b981;white-space:pre-wrap;">'
        + _esc(message) + '</div>'
    )
    parts.append('<hr style="border:1px solid #e2e8f0;">')
    meta = []
    if page_url:
        meta.append('Страница: ' + _esc(page_url))
    if ip:
        meta.append('IP: ' + _esc(ip))
    if meta:
        parts.append('<p style="color:#94a3b8;font-size:12px;">'
                     + '<br>'.join(meta) + '</p>')
    parts.append('</div>')
    html = ''.join(parts)

    # ── 1) Пробуем Resend HTTP API (utils.mail) — без зависимости от SMTP. ──
    try:
        from utils.mail import send_email as _resend_send, is_configured as _resend_ready
        if _resend_ready():
            _resend_send(
                to=owner_email,
                subject=subject,
                html=html,
                text=body,
                reply_to=email if email else None,
            )
            return True, None
    except Exception as e:
        logging.warning('review email via Resend failed, will try SMTP: %s', e)

    # ── 2) Fallback: Flask-Mail SMTP ───────────────────────────────────────
    try:
        from flask_mail import Message
        if mail_instance is None:
            return False, 'mail_instance is None and Resend not configured'
        msg = Message(
            subject=subject,
            recipients=[owner_email],
            body=body,
            html=html,
            reply_to=email if email else None,
        )
        mail_instance.send(msg)
        return True, None
    except Exception as e:
        logging.exception('review email send failed (both Resend and SMTP)')
        return False, str(e)
