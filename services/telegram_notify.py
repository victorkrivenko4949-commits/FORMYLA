# -*- coding: utf-8 -*-
"""
Email-уведомления для FORMYLA.
Отправляет обращения из формы поддержки на почту владельцу.
"""
import logging


def send_support_email(mail_instance, *, nickname, email, category,
                       message, page_url, user_agent, ip, ticket_id):
    """Отправить обращение на почту владельцу.
       Возвращает (success: bool, error: str | None)."""
    import os
    from flask_mail import Message

    owner_email = os.environ.get('MAIL_USERNAME')
    if not owner_email:
        return False, 'MAIL_USERNAME не настроен'

    cat_labels = {
        'bug': '🐛 Баг',
        'suggestion': '💡 Предложение',
        'question': '❓ Вопрос',
        'other': '✉️ Сообщение',
    }
    cat_label = cat_labels.get(category, '✉️ Сообщение')

    subject = f'[FORMYLA #{ticket_id}] {cat_label} от {nickname or "Гость"}'

    body_lines = [
        f'{cat_label}',
        f'Тикет: #{ticket_id}',
        '',
        f'Пользователь: {nickname or "Гость"}',
    ]
    if email:
        body_lines.append(f'Email: {email}')
    body_lines.extend([
        '',
        'Сообщение:',
        message,
        '',
        f'Страница: {page_url}' if page_url else '',
        f'IP: {ip}' if ip else '',
        f'User-Agent: {user_agent}' if user_agent else '',
    ])
    body = '\n'.join(l for l in body_lines if l is not None)

    # HTML-версия
    def esc(s):
        if not s:
            return ''
        return (str(s).replace('&', '&amp;')
                      .replace('<', '&lt;')
                      .replace('>', '&gt;'))

    html = f"""
    <div style="font-family: -apple-system, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #7c3aed;">{cat_label} — FORMYLA</h2>
        <p><strong>Тикет:</strong> #{ticket_id}</p>
        <p><strong>Пользователь:</strong> {esc(nickname or 'Гость')}</p>
        {'<p><strong>Email:</strong> ' + esc(email) + '</p>' if email else ''}
        <hr style="border: 1px solid #e2e8f0;">
        <p><strong>Сообщение:</strong></p>
        <div style="background: #f8fafc; padding: 16px; border-radius: 8px; white-space: pre-wrap;">{esc(message)}</div>
        <hr style="border: 1px solid #e2e8f0;">
        <p style="color: #94a3b8; font-size: 12px;">
            {'Страница: ' + esc(page_url) + '<br>' if page_url else ''}
            {'IP: ' + esc(ip) + '<br>' if ip else ''}
        </p>
    </div>
    """

    try:
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
        logging.exception('support email send failed')
        return False, str(e)
