# -*- coding: utf-8 -*-
"""routes/dashboard_settings.py — T6 dashboard widget settings."""
from datetime import datetime

from flask import abort, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from models import db, UserDashboardItem
from services.dashboard_widgets import AVAILABLE_WIDGETS


@login_required
def dashboard_settings():
    valid_keys = {w['key'] for w in AVAILABLE_WIDGETS}

    if request.method == 'POST':
        seen = set()
        for w in AVAILABLE_WIDGETS:
            key = w['key']
            if key in seen:
                continue
            seen.add(key)
            vis = request.form.get(f'widget_{key}_visible', '0')
            pos = request.form.get(f'widget_{key}_position', '0')
            if vis not in ('0', '1'):
                continue
            try:
                pos_int = int(pos)
            except (ValueError, TypeError):
                pos_int = 0
            if pos_int < 0 or pos_int > 99:
                pos_int = 0
            item = UserDashboardItem.query.filter_by(
                user_id=current_user.id, widget_key=key,
            ).first()
            if item is None:
                item = UserDashboardItem(
                    user_id=current_user.id,
                    widget_key=key,
                    position=pos_int,
                    visible=(vis == '1'),
                )
                db.session.add(item)
            else:
                item.position = pos_int
                item.visible = (vis == '1')
                item.updated_at = datetime.utcnow()
        # Reject unknown keys
        for k in request.form:
            if k.startswith('widget_') and '_' in k[7:]:
                wk = k[7:k.rindex('_')]
                if wk not in valid_keys and len(wk) < 65:
                    abort(400)
        db.session.commit()
        return redirect('/dashboard/settings')

    existing = {
        e.widget_key: e
        for e in UserDashboardItem.query.filter_by(user_id=current_user.id).all()
    }
    widgets = []
    for pos, w in enumerate(AVAILABLE_WIDGETS):
        item = existing.get(w['key'])
        widgets.append({
            'key': w['key'],
            'title': w['title'],
            'desc': w['description'],
            'visible': item.visible if item else False,
            'position': item.position if item else pos,
        })
    widgets.sort(key=lambda x: x['position'])
    return render_template('dashboard_settings.html', widgets=widgets)
