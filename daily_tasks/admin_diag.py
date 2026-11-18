# -*- coding: utf-8 -*-
"""daily_tasks/admin_diag.py — диагностический бейдж «источник / уровень / тема» для админа.

Шаг 9 плана восстановления задач дня. Ничего не меняет в выдаче и в БД:
  * GET /daily_tasks/admin/api/diag[?user_id=<id>] — JSON с тем, что система знает
    об ученике и его сегодняшней выдаче (только админ; чужой user_id — тоже только админ);
  * after_request на страницу /daily_tasks/ — для админа дописывает в HTML маленький
    плавающий блок, который подгружает этот JSON. Обычные ученики ничего не видят.

Диагностика read-only: build_daily_set / pick_daily_set НЕ вызываются (они пишут
bank_issues / daily_task_sets). Читаются уже существующие записи за сегодня.
Любая ошибка внутри — проглатывается, страница отдаётся как есть.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from flask import jsonify, request
from flask_login import current_user

logger = logging.getLogger(__name__)

_BADGE_HTML = """
<div id="dt-admin-diag" style="position:fixed;right:12px;bottom:12px;z-index:9999;max-width:360px;
font:12px/1.4 system-ui,sans-serif;background:#0b1220;color:#dfe7ff;border:1px solid #3b82f6;
border-radius:10px;padding:10px 12px;box-shadow:0 4px 18px rgba(0,0,0,.45);opacity:.95">
<div style="font-weight:600;margin-bottom:4px">Диагностика (админ)</div>
<div id="dt-admin-diag-body">загрузка…</div></div>
<script>(function(){try{fetch('/daily_tasks/admin/api/diag',{credentials:'same-origin'})
.then(function(r){return r.json()}).then(function(d){var b=document.getElementById('dt-admin-diag-body');
if(!b)return;if(d.error){b.textContent='нет данных: '+d.error;return}
function row(k,v){return '<div><span style=\\"color:#8fa3c7\\">'+k+':</span> '+(v===null||v===undefined?'—':v)+'</div>'}
var s=d.today||{};var l=d.level||{};var t=d.theme||{};var c=d.cells||{};
b.innerHTML=row('источник сегодня',s.source)+row('задач / уровни',(s.count||0)+' / '+(s.levels||'—'))
+row('тема дня',(t.title||'—')+(t.id?' ('+t.id+')':''))+row('класс',d.grade)
+row('уровень',l.level+' (mu '+l.mu+', '+l.origin+')')+row('ячейка L1/L2/L3/L4',c.counts||'—')
+row('дырка на уровне',c.hole?'ДА':'нет')+row('основной банк',d.main_bank)
+(d.note?'<div style=\\"margin-top:4px;color:#f59e0b\\">'+d.note+'</div>':'');}).catch(function(e){})}catch(e){}})();</script>
"""


def _is_admin() -> bool:
    try:
        return bool(getattr(current_user, 'is_authenticated', False)
                    and getattr(current_user, 'is_admin', False) is True)
    except Exception:
        return False


def _msk_today():
    return (datetime.utcnow() + timedelta(hours=3)).date()


def collect(user_id: int) -> dict:
    """Собрать диагностику. Только чтение."""
    out = {'user_id': user_id, 'date': _msk_today().isoformat(), 'note': ''}
    notes = []

    # Класс
    grade = None
    try:
        from models_curator import CuratorState
        cs = CuratorState.query.filter_by(user_id=user_id).first()
        grade = getattr(cs, 'grade', None) if cs is not None else None
        if grade is None:
            from models import User
            u = User.query.get(user_id)
            grade = getattr(u, 'preferred_grade', None) or getattr(u, 'class_level', None) if u else None
    except Exception as e:
        notes.append(f'класс: {e}')
    out['grade'] = grade

    # Тема дня по циклу
    theme_id, theme_title = None, None
    try:
        from curator.monthly_cycle import get_cycle_info
        info = get_cycle_info(user_id)
        if info.get('active'):
            theme_id = info.get('current_theme')
            out['cycle'] = {'day_index': info.get('day_index'), 'themes': info.get('themes')}
        if theme_id:
            from services.theme_registry import theme_title as _tt
            theme_title = _tt(theme_id)
    except Exception as e:
        notes.append(f'цикл: {e}')
    out['theme'] = {'id': theme_id, 'title': theme_title}

    # Уровень: по теме -> глобальный (как в JSONL-выдаче)
    level = {'mu': None, 'level': None, 'origin': None}
    try:
        from services.level_engine import get_state, get_level_by_theme
        st = get_state(user_id)
        mu, origin = float(st.get('mu', 3.0)), 'глобальный'
        lbt = get_level_by_theme(user_id) or {}
        ent = lbt.get(theme_id) if theme_id else None
        if isinstance(ent, dict) and ent.get('mu') is not None:
            mu, origin = float(ent['mu']), 'по теме'
        level = {'mu': round(mu, 2), 'level': max(1, min(4, int(round(mu)))), 'origin': origin,
                 'global_mu': round(float(st.get('mu', 3.0)), 2), 'sigma': round(float(st.get('sigma', 0)), 2)}
    except Exception as e:
        notes.append(f'уровень: {e}')
    out['level'] = level

    # Ячейка JSONL-банка по теме и классу
    cells = {'counts': None, 'hole': None}
    try:
        from daily_tasks.formyla_bank import task_count, has_rows
        if has_rows() and grade and theme_title:
            counts = [task_count(int(grade), theme_title, lv) for lv in (1, 2, 3, 4)]
            cells = {'counts': '/'.join(map(str, counts)),
                     'hole': bool(level.get('level') and counts[level['level'] - 1] == 0)}
    except Exception as e:
        notes.append(f'банк: {e}')
    out['cells'] = cells

    # Основной банк: назначения и строки (без автоактивации!)
    try:
        from services.curator_plan_service import get_active_subtopics
        from models import db, DailyTaskBank
        from sqlalchemy import func
        assignments, status = get_active_subtopics(user_id)
        rows = db.session.query(func.count(DailyTaskBank.id)).scalar() or 0
        out['main_bank'] = (f"строк {rows}, назначений {len(assignments)} "
                            f"(месяц {status.get('month')}, plan_missing={status.get('plan_missing')})")
    except Exception as e:
        out['main_bank'] = None
        notes.append(f'основной банк: {e}')

    # Что реально выдано сегодня
    today = _msk_today()
    src, count, levels = None, 0, None
    try:
        from models import BankIssue
        issues = BankIssue.query.filter_by(user_id=user_id, issued_date=today).all()
        if issues:
            src, count = 'daily_task_bank', len(issues)
            levels = ','.join(str(i.level) for i in issues)
    except Exception as e:
        notes.append(f'bank_issues: {e}')
    if not src:
        try:
            from daily_tasks.models import DailyTaskSet, DailyTaskItem
            ds = DailyTaskSet.query.filter_by(user_id=user_id, target_date=today).first()
            if ds is not None:
                items = DailyTaskItem.query.filter_by(daily_set_id=ds.id).order_by(DailyTaskItem.position).all()
                src = f"{ds.triggered_by or 'daily_set'} (status={ds.status})"
                count = len(items)
                levels = ','.join(str(i.difficulty_level) for i in items)
                out['reason_summary'] = ds.reason_summary
        except Exception as e:
            notes.append(f'daily_set: {e}')
    out['today'] = {'source': src or 'ещё не выдано', 'count': count, 'levels': levels}
    out['note'] = '; '.join(notes)
    return out


def attach(bp):
    @bp.route('/admin/api/diag')
    def admin_api_diag():
        if not _is_admin():
            return jsonify({'error': 'forbidden'}), 403
        raw = request.args.get('user_id')
        try:
            uid = int(raw) if raw else int(current_user.id)
        except (TypeError, ValueError):
            return jsonify({'error': 'bad_user_id'}), 400
        try:
            return jsonify(collect(uid))
        except Exception as e:  # pragma: no cover
            logger.warning('admin_diag: collect failed user=%s: %s', uid, e)
            return jsonify({'error': str(e)}), 500

    @bp.after_request
    def _inject_badge(resp):
        try:
            if request.endpoint != 'daily_tasks.get_daily_tasks' or request.method != 'GET':
                return resp
            if not _is_admin():
                return resp
            ctype = (resp.content_type or '')
            if 'text/html' not in ctype or resp.status_code != 200 or resp.direct_passthrough:
                return resp
            body = resp.get_data(as_text=True)
            idx = body.rfind('</body>')
            if idx < 0:
                return resp
            resp.set_data(body[:idx] + _BADGE_HTML + body[idx:])
        except Exception as e:  # pragma: no cover
            logger.debug('admin_diag: badge skipped: %s', e)
        return resp

    logger.info('daily_tasks admin_diag attached')
