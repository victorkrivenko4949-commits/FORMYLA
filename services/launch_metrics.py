# -*- coding: utf-8 -*-
"""LAUNCH_V1 — метрики дашборда запуска (промпт 29).

Только чтение БД (read-only SQL). Даты — по МСК. Каждый блок собирается
независимо: ошибка одного блока не ломает страницу. Если события/таблицы нет —
значение None, в UI выводится «нет источника данных», а не 0.
Ничего не включает и не выключает: страница показывает числа и текст правила.
Секреты (email, токены ссылок, payload платежей) не выводятся.

Карта источников и недостающие события — в README_LAUNCH (поставляется с патчем).
"""
from __future__ import annotations

import json
import logging
import math
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import text

logger = logging.getLogger(__name__)

MSK = ZoneInfo('Europe/Moscow')
UTC = timezone.utc

NO_DATA = None          # в шаблоне: «нет источника данных»


def _rows(sql: str, params: dict | None = None) -> list:
    from models import db
    return db.session.execute(text(sql), params or {}).fetchall()


def _rollback() -> None:
    """Сброс aborted-транзакции (PostgreSQL) после ошибки запроса."""
    try:
        from models import db
        db.session.rollback()
    except Exception:  # noqa: BLE001
        pass


def msk_now(as_of: datetime | None = None) -> datetime:
    now = as_of or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    return now.astimezone(MSK)


def _msk_date(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        v = value.replace('Z', '+00:00')
        try:
            value = datetime.fromisoformat(v)
        except ValueError:
            return str(value)[:10]
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(MSK).date().isoformat()


def _naive_utc(dt: datetime) -> datetime:
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC)
    return dt.replace(tzinfo=None)


def _to_dt(value):
    """Нормализация даты из БД: SQLite возвращает строки, PG — datetime."""
    if value is None or isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError:
        return None


def _naive_any(value) -> datetime | None:
    dt = _to_dt(value)
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC)
    return dt.replace(tzinfo=None)


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """Доверительный интервал Уилсона для доли k/n."""
    if not n:
        return None
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, center - half), min(1.0, center + half)


def _fmt_ci(ci: tuple[float, float] | None) -> str:
    if not ci:
        return ''
    return f'95% ДИ: {ci[0]:.1%}–{ci[1]:.1%}'


def _table_exists(name: str) -> bool:
    try:
        from models import db
        insp = db.inspect(db.engine)
        return name in insp.get_table_names()
    except Exception:  # noqa: BLE001
        return False


# ────────────────────────── блок 1: готовность ──────────────────────────
def readiness(now_msk: datetime) -> dict:
    """Если источник события отсутствует — None («нет источника данных»).
    Число появляется только после успешного запроса к действующему источнику."""
    out: dict = {
        'paywall_mode': os.environ.get('PAYWALL_MODE') or NO_DATA,
        'experiment_id': os.environ.get('PAYWALL_EXPERIMENT_ID') or NO_DATA,
        'paywall_start_at': os.environ.get('PAYWALL_START_AT') or NO_DATA,
        # HTTP-ошибки webhook не сохраняются в БД — отдельного источника нет
        'webhook_http_errors': NO_DATA,
        'webhook_http_errors_note': 'HTTP-логи webhook не сохраняются в БД',
        'orders_failed_7d': NO_DATA,
        'pending_stuck_24h': NO_DATA,
        'paid_no_access_7d': NO_DATA,
        'limits_fail_open_7d': NO_DATA,
    }
    as_of_utc = _naive_utc(now_msk)
    try:
        since7 = _naive_utc(now_msk - timedelta(days=7))
        out['orders_failed_7d'] = _rows(
            "SELECT COUNT(*) FROM orders WHERE status = 'failed' "
            "AND created_at >= :s AND created_at < :e", {'s': since7, 'e': as_of_utc})[0][0]
        stuck = _naive_utc(now_msk - timedelta(hours=24))
        out['pending_stuck_24h'] = _rows(
            "SELECT COUNT(*) FROM orders WHERE status IN ('created', 'pending') "
            "AND created_at < :s", {'s': stuck})[0][0]
    except Exception as exc:  # noqa: BLE001
        logger.warning('launch.readiness: %r', exc)
        _rollback()
    # оплачено, но доступ не выдан: реальная связь заказа с выдачей —
    # subscriptions.payment_id = order.yookassa_payment_id (kind=access)
    # или purchases.order_id (разовые). Проверяем боевые paid-заказы за 7 дней.
    try:
        since7 = _naive_utc(now_msk - timedelta(days=7))
        # kind определяем по каталогу продуктов
        from services.billing.catalog import get_product
        paid_rows = _rows(
            "SELECT id, plan_code, yookassa_payment_id, access_ends_at FROM orders "
            "WHERE status = 'paid' AND COALESCE(CAST(is_test AS INTEGER), 0) = 0 "
            "AND paid_at >= :s AND paid_at < :e", {'s': since7, 'e': as_of_utc})
        n = 0
        for oid, plan_code, pay_id, access_ends in paid_rows:
            product = get_product(plan_code)
            if product is None:
                continue  # неизвестный план — не можем проверить выдачу
            if product.kind == 'access':
                # выдано, если есть строка subscriptions с этим payment_id
                granted = _rows(
                    'SELECT 1 FROM subscriptions WHERE payment_id = :p LIMIT 1',
                    {'p': pay_id})
                if not granted:
                    n += 1
            else:
                granted = _rows(
                    'SELECT 1 FROM purchases WHERE order_id = :o LIMIT 1',
                    {'o': oid})
                if not granted:
                    n += 1
        out['paid_no_access_7d'] = n
    except Exception as exc:  # noqa: BLE001
        logger.warning('launch.readiness.paid_no_access: %r', exc)
        _rollback()
    # fail-open лимитера: события limits_fail_open в funnel_events
    if _table_exists('funnel_events'):
        try:
            since7 = _naive_utc(now_msk - timedelta(days=7))
            out['limits_fail_open_7d'] = _rows(
                "SELECT COUNT(*) FROM funnel_events WHERE event = 'limits_fail_open' "
                "AND created_at >= :s AND created_at < :e",
                {'s': since7, 'e': as_of_utc})[0][0]
        except Exception as exc:  # noqa: BLE001
            logger.warning('launch.readiness.fail_open: %r', exc)
            _rollback()
    return out


# ────────────────────── блок 2: эксперимент (A/B) ──────────────────────
def experiment(now_msk: datetime) -> dict | None:
    exp_id = os.environ.get('PAYWALL_EXPERIMENT_ID')
    if not exp_id:
        return NO_DATA
    if not _table_exists('ab_cohort'):
        return NO_DATA
    try:
        from routes.ab import build_report
        rep = build_report(exp_id, now_msk.astimezone(UTC))
    except Exception as exc:  # noqa: BLE001
        logger.warning('launch.experiment: %r', exc)
        _rollback()
        return NO_DATA
    # доверительные интервалы для долей
    for cohort, g in rep.get('groups', {}).items():
        a, n = g.get('active_7d', 0), g.get('assigned', 0)
        b, sn = g.get('broken_streaks', 0), g.get('streak_users', 0)
        g['active_ci'] = _fmt_ci(wilson_ci(a, n)) or None
        g['broken_ci'] = _fmt_ci(wilson_ci(b, sn)) or None
    # воронка по группам: показ → визит /subscribe → заказ → оплата.
    # События и заказы — только ПОСЛЕ назначения и ДО момента отчёта.
    as_of_utc = _naive_utc(now_msk)
    try:
        assigned = _rows(
            'SELECT user_id, cohort, assigned_at FROM ab_cohort '
            'WHERE experiment_id = :e', {'e': exp_id})
        by_uid = {r[0]: (r[1], r[2]) for r in assigned}
        for cohort, g in rep['groups'].items():
            uids = [u for u, (c, _) in by_uid.items() if c == cohort]
            g.update(_funnel_for_users(uids, by_uid, as_of_utc))
    except Exception as exc:  # noqa: BLE001
        logger.warning('launch.experiment.funnel: %r', exc)
        _rollback()
    # DAU справочно: пользователи, ответившие хотя бы на одну задачу дня сегодня
    rep['dau_today'] = NO_DATA
    try:
        today = now_msk.date().isoformat()
        rep['dau_today'] = _rows(
            'SELECT COUNT(DISTINCT s.user_id) FROM daily_task_items i '
            'JOIN daily_task_sets s ON i.daily_set_id = s.id '
            'WHERE i.user_answer IS NOT NULL AND i.answered_at IS NOT NULL '
            'AND s.target_date = :d', {'d': today})[0][0]
    except Exception as exc:  # noqa: BLE001
        logger.warning('launch.experiment.dau: %r', exc)
        _rollback()
    return rep


def _funnel_for_users(uids: list[int], assigned: dict, as_of_utc: datetime) -> dict:
    """Воронка: limit_shown → визит /subscribe → заказ → оплата.
    Только события/заказы в окне [assigned_at, as_of)."""
    out: dict = {'shown': NO_DATA, 'subscribe_view': NO_DATA,
                 'order_created': NO_DATA, 'paid': NO_DATA}
    if not uids:
        return {k: 0 for k in out}
    try:
        if _table_exists('funnel_events'):
            out['shown'] = _count_events(uids, ('limit_shown',), assigned, as_of_utc)
            out['subscribe_view'] = _count_events(
                uids, ('subscribe_view', 'paywall_view'), assigned, as_of_utc)
        out['order_created'] = _count_orders(uids, assigned, as_of_utc, paid_only=False)
        out['paid'] = _count_orders(uids, assigned, as_of_utc, paid_only=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning('launch._funnel_for_users: %r', exc)
        _rollback()
    return out


def _uid_list(uids: list[int]) -> str:
    return ','.join(str(int(u)) for u in uids)


def _count_events(uids: list[int], events: tuple, assigned: dict,
                  as_of_utc: datetime) -> int:
    """Число ПОЛЬЗОВАТЕЛЕЙ, у которых есть событие в окне
    [назначение; момент отчёта). Один пакетный запрос, фильтр по
    назначению — в Python (даты из БД нормализуются)."""
    ph = _uid_list(uids)
    ev = ','.join(f"'{e}'" for e in events)
    rows = _rows(
        f'SELECT user_id, created_at FROM funnel_events '
        f'WHERE event IN ({ev}) AND user_id IN ({ph}) AND created_at < :e',
        {'e': as_of_utc})
    users = set()
    for uid, created in rows:
        c = _naive_any(created)
        if c is None or c >= as_of_utc:
            continue
        a = assigned.get(uid)
        a_n = _naive_any(a[1]) if a else None
        if a_n is not None and c < a_n:
            continue
        users.add(uid)
    return len(users)


def _count_orders(uids: list[int], assigned: dict, as_of_utc: datetime,
                  paid_only: bool) -> int:
    """Число ПОЛЬЗОВАТЕЛЕЙ группы, у которых есть заказ в окне
    [назначение; момент отчёта). Воронка — по людям, не по заказам.
    Для оплаченных шагов дополнительно проверяется paid_at в том же окне.
    Тестовые заказы исключаются из обоих шагов: учитывается только
    явный is_test=0; NULL (неизвестно) исключается (fail-closed для денег)."""
    ph = _uid_list(uids)
    extra = ("AND status = 'paid' AND CAST(is_test AS INTEGER) = 0"
             if paid_only
             else "AND CAST(is_test AS INTEGER) = 0")
    col = 'paid_at' if paid_only else 'created_at'
    rows = _rows(
        f'SELECT beneficiary_user_id, {col} FROM orders '
        f'WHERE beneficiary_user_id IN ({ph}) AND {col} IS NOT NULL {extra} '
        f'AND {col} < :e', {'e': as_of_utc})
    users = set()
    for uid, created in rows:
        c = _naive_any(created)
        if c is None or c >= as_of_utc:
            continue
        a = assigned.get(uid)
        a_n = _naive_any(a[1]) if a else None
        if a_n is not None and c < a_n:
            continue
        users.add(uid)
    return len(users)


# ─────────────────── блок 3: воронка родителя ───────────────────────
def parent_funnel(now_msk: datetime) -> dict:
    """Клик «Отправить родителю» → ссылка создана → ссылка открыта → оплата.

    Отдельных событий parent_share_click / parent_link_created /
    parent_link_opened в кодовой базе нет (карта источников в README_LAUNCH).
    Пока источника нет — «нет источника данных», подмена другими метриками
    не допускается. Данные ребёнка в UI не выводятся.
    """
    return {
        'link_click': NO_DATA,
        'link_created': NO_DATA,
        'link_opened': NO_DATA,
        'paid': NO_DATA,
        'source': 'события «Отправить родителю» не реализованы — минимальный '
                  'план добавления в README_LAUNCH (3 события в funnel_events)',
    }


# ──────────────────────── блок 4: деньги ────────────────────────
def money(now_msk: datetime) -> dict:
    out: dict = {
        'by_plan': NO_DATA, 'refunds': NO_DATA, 'ai_cost_usd': NO_DATA,
        'founder_grants': NO_DATA, 'trial_granted': NO_DATA, 'trial_expired': NO_DATA,
        'monthly_equivalent': NO_DATA, 'yearly_received': NO_DATA,
        'monthly_received': NO_DATA,
        'monthly_equivalent_formula':
        'месячный эквивалент = месячные платежи за 30 дн + годовые платежи '
        'за 30 дн / 12 — это НЕ выручка и НЕ recurring revenue (автосписаний нет)',
    }
    as_of_utc = _naive_utc(now_msk)
    since30 = _naive_utc(now_msk - timedelta(days=30))
    try:
        # подтверждённые боевые: явный is_test = 0 (не NULL) и окно [30д; сейчас)
        rows = _rows(
            "SELECT plan_code, COUNT(*), SUM(amount) FROM orders "
            "WHERE status = 'paid' AND is_test IS NOT NULL "
            "AND CAST(is_test AS INTEGER) = 0 "
            "AND paid_at >= :s AND paid_at < :e GROUP BY plan_code",
            {'s': since30, 'e': as_of_utc})
        out['by_plan'] = [(r[0], r[1], (r[2] or 0) / 100) for r in rows]
        # месячность/годовость — по каталогу продуктов, не по подстрокам
        from services.billing.catalog import get_product
        monthly = 0.0
        yearly = 0.0
        for code, _cnt, rub in (out['by_plan'] or []):
            product = get_product(code)
            if product is None:
                continue
            if product.plan == 'premium_yearly' or product.duration == '1y':
                yearly += rub
            elif product.plan == 'premium_monthly' or product.duration == '30d':
                monthly += rub
        out['monthly_received'] = round(monthly, 2)
        out['yearly_received'] = round(yearly, 2)
        out['monthly_equivalent'] = round(monthly + yearly / 12, 2)
    except Exception as exc:  # noqa: BLE001
        logger.warning('launch.money: %r', exc)
        _rollback()
    # AI-затраты отдельно, в USD, за 30 дней (дата МСК из usage_daily.date)
    if _table_exists('usage_daily'):
        try:
            since_d = (now_msk - timedelta(days=30)).date().isoformat()
            until_d = now_msk.date().isoformat()
            out['ai_cost_usd'] = _rows(
                'SELECT COALESCE(SUM(cost_usd), 0) FROM usage_daily '
                'WHERE date >= :s AND date <= :e', {'s': since_d, 'e': until_d})[0][0]
        except Exception as exc:  # noqa: BLE001
            logger.warning('launch.money.ai: %r', exc)
            _rollback()
    # основатели и триалы — аудитория, не продажи
    if _table_exists('founder_grants'):
        try:
            out['founder_grants'] = _rows(
                'SELECT COUNT(*) FROM founder_grants')[0][0]
        except Exception as exc:  # noqa: BLE001
            logger.warning('launch.money.founders: %r', exc)
            _rollback()
    try:
        out['trial_granted'] = _rows(
            'SELECT COUNT(*) FROM users WHERE trial_until IS NOT NULL')[0][0]
        now_utc = as_of_utc
        out['trial_expired'] = _rows(
            'SELECT COUNT(*) FROM users WHERE trial_until IS NOT NULL '
            'AND trial_until < :n', {'n': now_utc})[0][0]
    except Exception as exc:  # noqa: BLE001
        logger.warning('launch.money.trials: %r', exc)
        _rollback()
    # возвраты: отдельной таблицы возвратов нет
    out['refunds'] = NO_DATA
    return out


# ──────────────────────── блок 5: источники ────────────────────────
def sources(now_msk: datetime) -> dict:
    out: dict = {'by_acq_source': NO_DATA, 'by_utm_source': NO_DATA,
                 'by_utm_campaign': NO_DATA}
    since = _naive_utc(now_msk - timedelta(days=30))
    as_of_utc = _naive_utc(now_msk)
    # регистрации по acq_source (поле users есть)
    try:
        rows = _rows(
            'SELECT COALESCE(acq_source, \'(нет)\'), COUNT(*) FROM users '
            'WHERE created_at >= :s AND created_at < :e GROUP BY 1 ORDER BY 2 DESC',
            {'s': since, 'e': as_of_utc})
        out['by_acq_source'] = [(r[0], r[1]) for r in rows]
    except Exception as exc:  # noqa: BLE001
        logger.warning('launch.sources.acq: %r', exc)
        _rollback()
    # регистрации по utm_source/utm_campaign: полей users.* нет —
    # связываем signup-событие с первым визитом того же anon_id
    if _table_exists('funnel_events'):
        try:
            signups = _rows(
                "SELECT user_id, anon_id FROM funnel_events WHERE event = 'signup' "
                "AND created_at >= :s AND created_at < :e AND user_id IS NOT NULL",
                {'s': since, 'e': as_of_utc})
            anon_ids = [r[1] for r in signups if r[1]]
            first_visit: dict[str, str] = {}
            if anon_ids:
                # bind-параметры, не интерполяция строк в SQL
                ph = ','.join(f':a{i}' for i in range(len(anon_ids)))
                params = {f'a{i}': a for i, a in enumerate(anon_ids)}
                visits = _rows(
                    f"SELECT anon_id, props, created_at FROM funnel_events "
                    f"WHERE event = 'visit' AND anon_id IN ({ph})", params)
                for aid, props, created in visits:
                    if aid not in first_visit or (created or '') < first_visit[aid][0]:
                        first_visit[aid] = ((created or ''), props)
            utm_s: dict = {}
            utm_c: dict = {}
            for uid, aid in signups:
                if not aid or aid not in first_visit:
                    continue
                props = first_visit[aid][1]
                p = props
                if isinstance(props, str):
                    try:
                        p = json.loads(props)
                    except Exception:  # noqa: BLE001
                        p = None
                utm = (p or {}).get('utm') or {}
                if not isinstance(utm, dict):
                    continue
                us = utm.get('utm_source')
                if us:
                    utm_s[str(us)] = utm_s.get(str(us), 0) + 1
                uc = utm.get('utm_campaign')
                if uc:
                    utm_c[str(uc)] = utm_c.get(str(uc), 0) + 1
            out['by_utm_source'] = sorted(utm_s.items(), key=lambda x: -x[1])
            out['by_utm_campaign'] = sorted(utm_c.items(), key=lambda x: -x[1])
        except Exception as exc:  # noqa: BLE001
            logger.warning('launch.sources.utm: %r', exc)
            _rollback()
    return out


# ────────────────── правило для 11.11 (текст) ──────────────────
def launch_rule(exp: dict | None, now_msk: datetime) -> dict:
    """Текст решения. Ничего не включает — только рекомендация.
    «7 полных дней после первого показа» = полные 24-часовые периоды."""
    min_eligible = int(os.environ.get('LAUNCH_MIN_ELIGIBLE', '150') or 150)
    ins = {'min_eligible': min_eligible, 'days_since_first_shown': NO_DATA,
           'active_share_limits': NO_DATA, 'active_share_control': NO_DATA,
           'broken_diff_pp': NO_DATA}
    if not exp or not exp.get('groups'):
        return {'decision': 'Недостаточно данных', 'inputs': ins,
                'note': 'эксперимент не найден или не назначено ни одной группы'}
    g_l = exp['groups'].get('limits') or {}
    g_c = exp['groups'].get('control') or {}
    # полных суток с первого показа лимита В ЭТОМ эксперименте
    fs = exp.get('first_limit_shown_at')
    if fs is not None:
        fs_dt = fs if isinstance(fs, datetime) else datetime.fromisoformat(str(fs))
        if fs_dt.tzinfo is None:
            fs_dt = fs_dt.replace(tzinfo=UTC)
        elapsed = now_msk.astimezone(UTC) - fs_dt
        ins['days_since_first_shown'] = elapsed.days  # полных 24-часовых периодов
    a_l, n_l = g_l.get('active_7d', 0), g_l.get('assigned', 0)
    a_c, n_c = g_c.get('active_7d', 0), g_c.get('assigned', 0)
    sh_l = (a_l / n_l) if n_l else None
    sh_c = (a_c / n_c) if n_c else None
    ins['active_share_limits'] = sh_l
    ins['active_share_control'] = sh_c
    b_l, s_l = g_l.get('broken_streaks'), g_l.get('streak_users')
    b_c, s_c = g_c.get('broken_streaks'), g_c.get('streak_users')
    br_l = (b_l / s_l) if (s_l is not None and s_l) else None
    br_c = (b_c / s_c) if (s_c is not None and s_c) else None
    broken_diff = None       # НЕокруглённое значение для сравнения
    if br_l is not None and br_c is not None:
        broken_diff = (br_l - br_c) * 100       # в п.п.
    if broken_diff is not None:
        ins['broken_diff_pp'] = round(broken_diff, 1)   # округление — только отображение

    small = (n_l < min_eligible or n_c < min_eligible)
    few_days = (ins['days_since_first_shown'] is None
                or ins['days_since_first_shown'] < 7)
    if small or few_days:
        return {'decision': 'Недостаточно данных', 'inputs': ins,
                'note': 'меньше LAUNCH_MIN_ELIGIBLE в группе или меньше 7 '
                        'полных суток с первого показа лимита'}
    if broken_diff is None:
        # доля прерванных серий недоступна (события не пишутся) —
        # рекомендация rollout на подмене данных недопустима
        return {'decision': 'Недостаточно данных', 'inputs': ins,
                'note': 'доля прерванных серий: нет источника данных '
                        '(события streak_day/streak_broken не пишутся — '
                        'план в README_LAUNCH_V1)'}
    if sh_l is not None and sh_c and (sh_l / sh_c) >= 0.8 and broken_diff <= 5:
        decision = 'Рассмотреть PAYWALL_MODE=rollout'
    else:
        decision = 'FREE_TASKS_PER_DAY=4, продолжить эксперимент 7 дней'
    return {'decision': decision, 'inputs': ins,
            'note': 'отсутствие значимой разницы — не доказательство '
                    'безопасности; решение принимает человек'}


def collect(as_of: datetime | None = None) -> dict:
    now_msk = msk_now(as_of)
    exp = experiment(now_msk)
    return {
        'as_of_msk': now_msk.isoformat(timespec='seconds'),
        'readiness': readiness(now_msk),
        'experiment': exp,
        'parent_funnel': parent_funnel(now_msk),
        'money': money(now_msk),
        'sources': sources(now_msk),
        'rule': launch_rule(exp, now_msk),
    }


# ─────────────────────────── CSV ───────────────────────────
def csv_escape(value) -> str:
    """Защита от formula-injection: ячейка, начинающаяся с =,+,-,@ или
    табуляции/перевода строки, получает префикс-апостроф."""
    s = '' if value is None else str(value)
    if s[:1] in ('=', '+', '-', '@', '\t', '\n', '\r'):
        return "'" + s
    return s


def to_csv_rows(data: dict) -> list[list[str]]:
    """Те же данные, что в HTML, плоским списком строк (section, metric, value).
    None → «нет источника данных» (как в HTML)."""
    rows: list[list[str]] = [['section', 'metric', 'value']]
    ND = 'нет источника данных'

    def add(section, metric, value):
        v = ND if value is None else value
        rows.append([csv_escape(section), csv_escape(metric), csv_escape(v)])

    r = data.get('readiness') or {}
    add('готовность', 'PAYWALL_MODE', r.get('paywall_mode'))
    add('готовность', 'experiment_id', r.get('experiment_id'))
    add('готовность', 'paywall_start_at', r.get('paywall_start_at'))
    add('готовность', 'ошибки webhook (HTTP)', r.get('webhook_http_errors'))
    add('готовность', 'заказы failed/mismatch (7д)', r.get('orders_failed_7d'))
    add('готовность', 'зависшие заказы (24ч)', r.get('pending_stuck_24h'))
    add('готовность', 'оплачено без доступа (7д)', r.get('paid_no_access_7d'))
    add('готовность', 'fail-open лимитера (7д)', r.get('limits_fail_open_7d'))

    exp = data.get('experiment')
    if exp and exp.get('groups'):
        for cohort, g in exp['groups'].items():
            c = f'эксперимент/{cohort}'
            add(c, 'назначено', g.get('assigned'))
            add(c, 'активные 7д', f"{g.get('active_7d')}/{g.get('assigned')}")
            if g.get('active_ci') is not None:
                add(c, 'активные 7д, ДИ', g.get('active_ci'))
            add(c, 'задач с ответом на назначенного', g.get('tasks_per_assigned'))
            if g.get('streak_users') is not None:
                add(c, 'прерванные серии',
                    (f"нет наблюдений ({g.get('broken_streaks')}/"
                     f"{g.get('streak_users')})")
                    if not g.get('streak_users')
                    else f"{g.get('broken_streaks')}/{g.get('streak_users')}")
                if g.get('broken_ci') is not None:
                    add(c, 'прерванные серии, ДИ', g.get('broken_ci'))
            else:
                add(c, 'прерванные серии', ND)
            add(c, 'D7', (f"{g.get('d7_retained')}/{g.get('d7_eligible')}"
                           if g.get('d7_retained') is not None else 'нет полного окна'))
            add(c, 'показ лимита', g.get('shown'))
            add(c, 'визит /subscribe', g.get('subscribe_view'))
            add(c, 'заказы', g.get('order_created'))
            add(c, 'оплаты', g.get('paid'))
        add('эксперимент', 'DAU сегодня (справочно)', exp.get('dau_today'))

    pf = data.get('parent_funnel') or {}
    add('воронка родителя', 'клик «Отправить родителю»', pf.get('link_click'))
    add('воронка родителя', 'ссылка создана', pf.get('link_created'))
    add('воронка родителя', 'ссылка открыта', pf.get('link_opened'))
    add('воронка родителя', 'оплата', pf.get('paid'))

    m = data.get('money') or {}
    if m.get('by_plan'):
        for code, cnt, rub in m['by_plan']:
            add('деньги', f'{code}: шт', cnt)
            add('деньги', f'{code}: руб', rub)
    else:
        add('деньги', 'платежи по планам (30д)', None)
    add('деньги', 'месячные получено (30д), руб', m.get('monthly_received'))
    add('деньги', 'годовые получено (30д), руб', m.get('yearly_received'))
    add('деньги', 'месячный эквивалент (30д)', m.get('monthly_equivalent'))
    add('деньги', 'возвраты', m.get('refunds'))
    add('деньги', 'AI-затраты (30д), USD', m.get('ai_cost_usd'))
    add('деньги', 'гранты основателя (аудитория)', m.get('founder_grants'))
    add('деньги', 'trial выдано', m.get('trial_granted'))
    add('деньги', 'trial истекло', m.get('trial_expired'))

    s = data.get('sources') or {}
    if s.get('by_acq_source'):
        for k, v in s['by_acq_source']:
            add('источники', f'acq_source: {k}', v)
    else:
        add('источники', 'acq_source', None)
    if s.get('by_utm_source'):
        for k, v in s['by_utm_source']:
            add('источники', f'utm_source: {k}', v)
    else:
        add('источники', 'utm_source', None)
    if s.get('by_utm_campaign'):
        for k, v in s['by_utm_campaign']:
            add('источники', f'utm_campaign: {k}', v)
    else:
        add('источники', 'utm_campaign', None)

    rule = data.get('rule') or {}
    add('правило 11.11', 'решение', rule.get('decision'))
    for k, v in (rule.get('inputs') or {}).items():
        add('правило 11.11', k, v)
    return rows
