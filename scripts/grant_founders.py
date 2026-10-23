# -*- coding: utf-8 -*-
"""FOUNDERS_V1 — scripts/grant_founders.py: выдача бесплатного доступа Основателям.

Правила:
  * по умолчанию --dry-run: только счётчики и причины исключения, без записи;
  * --apply запрещён, пока не наступил FOUNDER_CUTOFF_AT (03.11.2026 00:00 МСК);
  * пачки по 500 (--batch-size), возобновление после сбоя — просто повторный
    запуск (идемпотентность: UNIQUE(user_id, campaign_id), флаги не дублируются);
  * уже платящие получают is_founder/founder_price_eligible и выдачу,
    оплаченный срок не меняется, лишних выдач не создаётся;
  * в логах НЕТ email и telegram_id — только user_id и счётчики;
  * аудит хранится в БД (founder_grants: granted_at/granted_by/grant_batch),
    а не только в файле контейнера;
  * после выдачи сверяются три числа: COUNT(created_at < cutoff),
    COUNT(is_founder), COUNT(выдач этой кампании).

Запуск (Render Shell / локально):
    python scripts/grant_founders.py                 # dry-run
    python scripts/grant_founders.py --apply         # только после 03.11 00:00 МСК
    python scripts/grant_founders.py --rollback      # адресный откат кампании
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger('grant_founders')

BATCH_SIZE_DEFAULT = 500


def _exclude_ids() -> set:
    raw = os.environ.get('FOUNDER_EXCLUDE_USER_IDS', '')
    out = set()
    for part in raw.split(','):
        part = part.strip()
        if part.isdigit():
            out.add(int(part))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description='Выдача бесплатного доступа Основателям')
    parser.add_argument('--apply', action='store_true', help='записать изменения (иначе dry-run)')
    parser.add_argument('--rollback', action='store_true', help='адресный откат выдач этой кампании')
    parser.add_argument('--campaign-id', default='founders_2026_v1')
    parser.add_argument('--batch-size', type=int, default=BATCH_SIZE_DEFAULT)
    parser.add_argument('--limit', type=int, default=0, help='только для ручной проверки (первые N)')
    args = parser.parse_args()

    from app import app  # noqa: E402 — приложение создаёт контекст БД
    from models import db, User
    from models_founders import FounderGrant
    from services.access import founder_cutoff, founder_grant_start, founder_grant_until

    cutoff = founder_cutoff()
    grant_start = founder_grant_start()
    grant_until = founder_grant_until()

    with app.app_context():
        if args.rollback:
            return _rollback(db, User, FounderGrant, args.campaign_id)
        return _run(db, User, FounderGrant, args, cutoff, grant_start, grant_until)


def _eligible_filter(User, cutoff, exclude_ids):
    return (
        User.query
        .filter(User.created_at != None,  # noqa: E711
                User.created_at < cutoff.replace(tzinfo=None))
        .filter(User.is_guest.is_(False))
    )


def _run(db, User, FounderGrant, args, cutoff, grant_start, grant_until, now=None) -> int:
    now_utc = (now or datetime.utcnow())
    exclude_ids = _exclude_ids()

    if args.apply and now_utc < cutoff.replace(tzinfo=None):
        print('[ОТКАЗАНО] --apply до FOUNDER_CUTOFF_AT запрещён '
              f'(cutoff={cutoff.isoformat()}, сейчас={now_utc.isoformat()}). '
              'Повторите после 03.11.2026 00:00 МСК.')
        return 2

    q = _eligible_filter(User, cutoff, exclude_ids)
    total_candidates = q.count()
    print(f'Кандидаты (created_at < {cutoff.isoformat()}, не гости): {total_candidates}')

    # причины исключения (счётчики, без персональных данных)
    blocked = User.query.filter(User.is_blocked == True).count() if hasattr(User, 'is_blocked') else None  # noqa: E712
    guests = User.query.filter(User.is_guest == True).count()  # noqa: E712
    later = User.query.filter(User.created_at != None, User.created_at >= cutoff.replace(tzinfo=None)).count()  # noqa: E711
    print(f'Исключены: гостей={guests}, созданных после границы={later}'
          + (f', заблокированных={blocked}' if blocked is not None else ''))
    if exclude_ids:
        print(f'Ручных исключений (FOUNDER_EXCLUDE_USER_IDS): {len(exclude_ids)}')

    users = q.order_by(User.id).all()
    if args.limit > 0:
        users = users[:args.limit]

    granted = flags_set = skipped_existing = 0
    batch_no = 0
    for i in range(0, len(users), args.batch_size):
        batch = users[i:i + args.batch_size]
        batch_no += 1
        for u in batch:
            if u.id in exclude_ids:
                continue
            already = (FounderGrant.query
                       .filter_by(user_id=u.id, campaign_id=args.campaign_id).first())
            if args.apply:
                if not u.is_founder or not u.founder_price_eligible:
                    u.is_founder = True
                    u.founder_price_eligible = True
                    if u.founder_granted_at is None:
                        u.founder_granted_at = now_utc
                    flags_set += 1
                if already is None:
                    db.session.add(FounderGrant(
                        user_id=u.id, campaign_id=args.campaign_id, amount=0,
                        payment_id=None, is_free_grant=True,
                        starts_at=grant_start.replace(tzinfo=None),
                        expires_at=grant_until.replace(tzinfo=None),
                        granted_at=now_utc, granted_by='script:grant_founders',
                        grant_batch=batch_no))
                    granted += 1
                else:
                    skipped_existing += 1
        if args.apply:
            db.session.commit()
            print(f'Пачка {batch_no}: коммит ({len(batch)} чел.)')

    mode = 'APPLY' if args.apply else 'DRY-RUN (ничего не записано)'
    print(f'[{mode}] кандидатов={len(users)} (лимит={args.limit or "нет"}), '
          f'новых выдач={granted}, флагов выставлено={flags_set}, '
          f'уже было={skipped_existing}')

    if args.apply:
        _verify(db, User, FounderGrant, args, cutoff)
    else:
        print('Это был dry-run: записи нет. Для выдачи: python scripts/grant_founders.py --apply')
    return 0


def _verify(db, User, FounderGrant, args, cutoff) -> None:
    """Сверка трёх чисел + выборка 5 аккаунтов (без email в выводе)."""
    n_created = _eligible_filter(User, cutoff, _exclude_ids()).count()
    n_flags = User.query.filter(User.is_founder == True).count()  # noqa: E712
    n_grants = FounderGrant.query.filter_by(campaign_id=args.campaign_id).count()
    print('Сверка: создано до границы=%d, is_founder=%d, выдач кампании=%d' % (
        n_created, n_flags, n_grants))
    if n_created != n_flags or n_created != n_grants:
        print('[ВНИМАНИЕ] Числа не сходятся — проверьте исключения (FOUNDER_EXCLUDE_USER_IDS) '
              'и повторите запуск: он идемпотентен и довыдаст недостающее.')
    sample = (User.query.filter(User.is_founder == True)  # noqa: E712
              .order_by(User.id).limit(5).all())
    print('Проверка 5 аккаунтов (id, is_founder, founder_price_eligible, '
          'founder_granted_at, есть выдача):')
    for u in sample:
        has_grant = (FounderGrant.query
                     .filter_by(user_id=u.id, campaign_id=args.campaign_id).first()) is not None
        print(f'  user_id={u.id} founder={bool(u.is_founder)} '
              f'price={bool(u.founder_price_eligible)} '
              f'granted_at={u.founder_granted_at} grant={has_grant}')


def _rollback(db, User, FounderGrant, campaign_id) -> int:
    """Адресный откат: удаляет ТОЛЬКО выдачи этой кампании и её флаги.

    Платежи, orders и оплаченные права (subscriptions) не трогаются.
    """
    grants = FounderGrant.query.filter_by(campaign_id=campaign_id).all()
    user_ids = [g.user_id for g in grants]
    print(f'Откат кампании {campaign_id}: выдач={len(grants)}')
    if not grants:
        print('Нечего откатывать.')
        return 0
    for g in grants:
        db.session.delete(g)
    # флаги снимаем только у тех, у кого выдача была в этой кампании
    for uid in user_ids:
        u = db.session.get(User, uid)
        if u is None:
            continue
        u.is_founder = False
        u.founder_price_eligible = False
        u.founder_granted_at = None
    db.session.commit()
    print(f'Удалено выдач: {len(grants)}; флаги сняты у {len(user_ids)} пользователей. '
          'Платежи и оплаченные права не тронуты.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
