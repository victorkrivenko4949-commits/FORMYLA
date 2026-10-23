# -*- coding: utf-8 -*-
"""AB_V1 — CLI `flask ab-report`: отчёт по эксперименту лимитов.

Только читает данные. Даты — по МСК. Анализ — по исходному назначению
(ab_cohort), покупка после назначения не переносит человека в другую группу.
Каждая метрика выводится с абсолютным знаменателем. Абсолютный DAU —
только справочно. SQL-эквивалент для ручного запуска: reports/ab_daily.sql.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import click
from flask import Flask
from sqlalchemy import text

from models import db

logger = logging.getLogger(__name__)
MSK = ZoneInfo('Europe/Moscow')
UTC = timezone.utc


def _to_dt(value):
    """Нормализация даты из БД: SQLite возвращает строки, PG — datetime."""
    if value is None or isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError:
        return None


def _naive(value) -> datetime | None:
    dt = _to_dt(value)
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    return dt.replace(tzinfo=None)


def _msk_date(value) -> str:
    if value is None:
        return ''
    if isinstance(value, str):
        value = value.replace('Z', '+00:00')
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return str(value)[:10]
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(MSK).date().isoformat()


def _rows(sql: str, params: dict) -> list:
    return db.session.execute(text(sql), params).fetchall()


def _streak_stats_from_events(exp_id: str, cohorts: dict,
                              min_assigned, as_of: datetime):
    """Доля прерванных серий — из событий воронки, не из реконструкции.

    События (план добавления в README_LAUNCH_V1):
      * 'streak_day'  — день засчитан в серию (props: {'streak': <длина>});
      * 'streak_broken' — серия сброшена (check_streak_on_open / неверно
        закрытый день).
    Пользователи «с серией» = есть 'streak_day' со значением streak >= 2.
    Прервана = есть 'streak_broken' в окне после назначения.

    Если событий нет вовсе → None («нет источника данных»).
    Возвращает {'limits': (broken, series_users), 'control': (...)} или None.
    """
    import json as _json
    # все события серий для юзеров эксперимента (без временного фильтра в SQL:
    # окно [назначение; as_of) применяется по каждому юзеру в Python — иначе
    # «все события вне окна» неотличимо от «событий нет вообще»)
    all_uids = [r[0] for rs in cohorts.values() for r in rs]
    if not all_uids:
        return None
    ph = ','.join(str(int(u)) for u in all_uids)
    try:
        rows = _rows(
            f"SELECT user_id, event, props, created_at FROM funnel_events "
            f"WHERE event IN ('streak_day', 'streak_broken') "
            f"AND user_id IN ({ph})", params=[])
    except Exception:  # noqa: BLE001
        return None
    if not rows:
        return None    # событий серий нет вообще → нет источника данных
    hi = _naive(as_of)
    # user_id → (cohort, assigned_at)
    by_uid = {r[0]: (c, _naive(r[1])) for c, rs in cohorts.items() for r in rs}
    broken = {'limits': set(), 'control': set()}
    series = {'limits': set(), 'control': set()}
    for uid, event, props, created in rows:
        info = by_uid.get(uid)
        if info is None:
            continue
        cohort, assigned_at = info
        c = _naive(created)
        # событие в окне [назначение; as_of)
        if c is None or c >= hi:
            continue
        if assigned_at is not None and c < assigned_at:
            continue
        p = props
        if isinstance(props, str):
            try:
                p = _json.loads(props)
            except Exception:  # noqa: BLE001
                p = None
        if event == 'streak_broken':
            broken[cohort].add(uid)
        elif event == 'streak_day' and isinstance(p, dict) \
                and int(p.get('streak') or 0) >= 2:
            series[cohort].add(uid)
    return {c: (len(broken[c]), len(series[c] | broken[c]))
            for c in ('limits', 'control')}


def build_report(exp_id: str, as_of: datetime) -> dict:
    """Собирает отчёт. Все метрики — с абсолютными знаменателями."""
    cohorts = {'limits': [], 'control': []}
    assigned = _rows(
        "SELECT user_id, cohort, assigned_at, first_limit_shown_at FROM ab_cohort "
        "WHERE experiment_id = :e ORDER BY assigned_at", {'e': exp_id})
    for user_id, cohort, assigned_at, first_shown in assigned:
        cohorts.setdefault(cohort, []).append((user_id, assigned_at, first_shown))

    now_msk = as_of.astimezone(MSK)
    today_msk = now_msk.date()

    # Активность — реальные ответы на задачи дня (daily_task_items.user_answer),
    # НЕ usage_daily: там счётчик выдач/резервов лимитера, а не решения.
    # День активности = МСК-дата answered_at (не target_date: долг можно
    # закрыть позже). Ответы после момента отчёта не учитываются.
    # Выборка ограничена окном эксперимента [min(assigned); as_of).
    usage = {}
    min_assigned = min((r[1] for rows in cohorts.values() for r in rows),
                       default=None)
    if min_assigned is not None:
        for uid, answered_at, cnt in _rows(
                "SELECT s.user_id, i.answered_at, COUNT(i.id) FROM daily_task_items i "
                "JOIN daily_task_sets s ON i.daily_set_id = s.id "
                "WHERE i.user_answer IS NOT NULL AND i.answered_at IS NOT NULL "
                "AND i.answered_at >= :lo AND i.answered_at < :hi "
                "GROUP BY 1, 2", {'lo': _naive(min_assigned), 'hi': _naive(as_of)}):
            usage.setdefault(uid, {})[_msk_date(answered_at)] = int(cnt or 0)
    # первый показ лимита в ЭТОМ эксперименте (для правила запуска)
    fs_row = _rows(
        "SELECT MIN(first_limit_shown_at) FROM ab_cohort "
        "WHERE experiment_id = :e AND first_limit_shown_at IS NOT NULL", {'e': exp_id})
    first_shown_at = fs_row[0][0] if fs_row and fs_row[0] else None

    # оплаченные заказы (боевые) — по исходной группе; paid_at в окне
    # [назначение; момент отчёта)
    paid = {}
    for uid, paid_at in _rows(
            "SELECT beneficiary_user_id, paid_at FROM orders "
            "WHERE status = 'paid' AND COALESCE(CAST(is_test AS INTEGER), 0) = 0 "
            "AND paid_at IS NOT NULL AND paid_at < :hi", {'hi': _naive(as_of)}):
        paid.setdefault(uid, []).append(paid_at)

    # ── прерванные серии: по СОБЫТИЯМ, не реконструкции ──
    # Правило серий (streak_service): серия растёт на полностью верных днях
    # (complete_day, для лимитированных Free — правило 2/3), рвётся при
    # пропуске > 1 дня (check_streak_on_open) либо сбрасывается при неверно
    # закрытом дне. История серий в БД не пишется (streak_records хранит
    # только текущее состояние; day-off логируется только в last_solved_date),
    # поэтому реконструкция из daily_task_items невозможна без искажений.
    # Честная метрика — события: 'streak_day' (день засчитан, props.streak =
    # длина серии) и 'streak_broken' (серия сброшена). Пока события не
    # добавлены (план в README_LAUNCH_V1) → «нет источника данных».
    streak_stats = _streak_stats_from_events(exp_id, cohorts, min_assigned, as_of)

    result = {'experiment_id': exp_id, 'as_of_msk': now_msk.isoformat(timespec='seconds'),
              'daily': [], 'groups': {}, 'first_limit_shown_at': first_shown_at}
    # ── дневная численность назначений (по МСК) ──
    per_day = {}
    for cohort, rows in cohorts.items():
        for uid, assigned_at, _ in rows:
            d = _msk_date(assigned_at)
            per_day.setdefault(d, {'limits': 0, 'control': 0})[cohort] += 1
    result['daily'] = [{'date': d, **v} for d, v in sorted(per_day.items())]

    # ── метрики по группам (по исходному назначению) ──
    for cohort, rows in cohorts.items():
        n = len(rows)
        active_n = 0
        tasks_total = 0
        paid_n = 0
        broken_n = None      # нет источника данных, пока события не пишутся
        streak_had = None
        if streak_stats is not None:
            broken_n = streak_stats[cohort][0]
            streak_had = streak_stats[cohort][1]
        d7_n = 0
        d7_eligible = 0
        for uid, assigned_at, _ in rows:
            a_msk = _msk_date(assigned_at)
            try:
                a_date = datetime.fromisoformat(a_msk).date()
            except ValueError:
                continue
            window_end = min(a_date + timedelta(days=7), today_msk)
            days = [d for d in usage.get(uid, {})
                    if a_date <= datetime.fromisoformat(d).date() <= window_end]
            if days:
                active_n += 1
                tasks_total += sum(usage[uid][d] for d in days)
            # оплата после назначения (по исходной группе): paid_at >= assigned_at
            a_n = _naive(assigned_at)
            if any(p is not None and (pa := _naive(p)) is not None
                   and a_n is not None and pa >= a_n for p in paid.get(uid, [])):
                paid_n += 1
            # D7: активен на 7-й день; полное окно = 7-е сутки ЗАВЕРШИЛИСЬ
            if a_date + timedelta(days=7) < today_msk:
                d7_eligible += 1
                day7 = (a_date + timedelta(days=7)).isoformat()
                if usage.get(uid, {}).get(day7, 0) > 0:
                    d7_n += 1
        result['groups'][cohort] = {
            'assigned': n,
            'active_7d': active_n,
            'tasks_total_7d': tasks_total,
            'tasks_per_assigned': round(tasks_total / n, 2) if n else 0.0,
            'paid_after_assignment': paid_n,
            'paid_conversion': round(paid_n / n, 4) if n else 0.0,
            'streak_users': streak_had,
            'broken_streaks': broken_n,
            'broken_share': (round(broken_n / streak_had, 4)
                             if streak_had else None),
            'd7_eligible': d7_eligible,
            'd7_retained': d7_n if d7_eligible else None,   # неполный D7 не выводится
        }
    return result


def _print_report(rep: dict) -> None:
    click.echo(f"Эксперимент: {rep['experiment_id']}   (на {rep['as_of_msk']} МСК)")
    click.echo('')
    click.echo('Назначения по дням (МСК):')
    for row in rep['daily']:
        click.echo(f"  {row['date']}: limits={row['limits']}  control={row['control']}")
    click.echo('')
    for cohort in ('limits', 'control'):
        g = rep['groups'].get(cohort)
        if not g:
            continue
        click.echo(f'Группа {cohort}: назначлено {g["assigned"]}')
        click.echo(f'  Активные (7д): {g["active_7d"]}/{g["assigned"]}')
        click.echo(f'  Задач на назначенного: {g["tasks_per_assigned"]} '
                  f'(всего {g["tasks_total_7d"]})')
        click.echo(f'  Конверсия в оплату: {g["paid_after_assignment"]}/{g["assigned"]} '
                   f'= {g["paid_conversion"]:.1%}')
        if g['broken_share'] is None:
            click.echo('  Прерванные серии: нет источника данных '
                       '(события streak_day/streak_broken не пишутся — план в README)')
        else:
            click.echo(f'  Прерванные серии: {g["broken_streaks"]}/{g["streak_users"]} '
                       f'= {g["broken_share"]:.1%}')
        if g['d7_retained'] is not None:
            click.echo(f'  D7: {g["d7_retained"]}/{g["d7_eligible"]}')
        else:
            click.echo('  D7: нет полного окна наблюдения (не выводится)')
    click.echo('')
    click.echo('DAU выводится только справочно и не используется для сравнения групп.')


def install_ab(app: Flask) -> None:
    if app.extensions.get('ab_installed'):
        return
    app.extensions['ab_installed'] = True

    @app.cli.command('ab-report')
    @click.option('--experiment-id', default=None, help='по умолчанию PAYWALL_EXPERIMENT_ID')
    @click.option('--as-of', default=None, help='YYYY-MM-DD по МСК, по умолчанию сейчас')
    def ab_report(experiment_id, as_of):
        """Отчёт по эксперименту лимитов (только чтение, даты по МСК)."""
        import services.ab as ab
        exp = experiment_id or ab.experiment_id()
        if as_of:
            now = datetime.fromisoformat(as_of).replace(tzinfo=MSK).astimezone(UTC)
        else:
            now = datetime.now(UTC)
        with app.app_context():
            rep = build_report(exp, now)
        _print_report(rep)
