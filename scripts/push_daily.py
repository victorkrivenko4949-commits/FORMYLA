# -*- coding: utf-8 -*-
"""scripts/push_daily.py — разослать push «Задачи дня ждут» всем подписчикам.

Запуск из корня репо (локально или как Render Cron Job):
    python scripts/push_daily.py
    python scripts/push_daily.py --dry-run
    python scripts/push_daily.py --title "Заголовок" --body "Текст" --url /daily_tasks

Render Cron Job: command = `python scripts/push_daily.py`, schedule = `0 5 * * *`
(05:00 UTC = 08:00 МСК). Нужны те же env, что у веб-сервиса
(DATABASE_URL, VAPID_PRIVATE_KEY, VAPID_CLAIM_EMAIL).
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def main():
    parser = argparse.ArgumentParser(description='FORMYLA push broadcast')
    parser.add_argument('--title')
    parser.add_argument('--body')
    parser.add_argument('--url')
    parser.add_argument('--kind', default='daily')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    from app import app
    from services import push_broadcast as pb

    with app.app_context():
        stats = pb.broadcast(
            args.title or pb.DAILY_TITLE,
            args.body or pb.DAILY_BODY,
            url=args.url or pb.DAILY_URL,
            kind=args.kind,
            dry_run=args.dry_run,
        )
    print('push broadcast:', stats)
    return 0 if stats['failed'] == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
