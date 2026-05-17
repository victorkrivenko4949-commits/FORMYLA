# -*- coding: utf-8 -*-
"""Создаёт локального тестового друга для отладки чата.

Один раз создаёт пользователя ``testbot@formyla.local`` (nickname ``ТестАня``)
и принятый Friendship с пользователем ``victor.krivenko.4949@gmail.com``.
Идемпотентен: повторный запуск ничего не дублирует.

Запуск:  ``python scripts/_seed_test_friend.py``
"""
from __future__ import annotations

import os
import sys
from datetime import datetime

# Make project root importable when running as `python scripts/_seed_test_friend.py`
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import app  # инициализирует Flask + DB
from models import db, User, Friendship


ME_EMAIL = "victor.krivenko.4949@gmail.com"
BOT_EMAIL = "testbot@formyla.local"
BOT_NICK = "ТестАня"


def main() -> int:
    with app.app.app_context():
        me = User.query.filter_by(email=ME_EMAIL).first()
        if me is None:
            print("[ERR] me not found:", ME_EMAIL)
            return 1

        bot = User.query.filter_by(email=BOT_EMAIL).first()
        if bot is None:
            bot = User(
                email=BOT_EMAIL,
                nickname=BOT_NICK,
                name="Аня (тест-бот)",
                is_guest=False,
                current_level=3,
                experience_points=420,
            )
            db.session.add(bot)
            db.session.commit()
            print("[ok] bot created  id=" + str(bot.id))
        else:
            print("[skip] bot already exists  id=" + str(bot.id))

        # Friendship — single accepted row in either direction is enough.
        existing = Friendship.query.filter(
            db.or_(
                db.and_(Friendship.requester_id == me.id, Friendship.addressee_id == bot.id),
                db.and_(Friendship.requester_id == bot.id, Friendship.addressee_id == me.id),
            )
        ).first()
        if existing is None:
            now = datetime.utcnow()
            f = Friendship(
                requester_id=me.id,
                addressee_id=bot.id,
                status="accepted",
                created_at=now,
                accepted_at=now,
            )
            db.session.add(f)
            db.session.commit()
            print("[ok] friendship created  me=" + str(me.id) + " <-> bot=" + str(bot.id))
        else:
            if existing.status != "accepted":
                existing.status = "accepted"
                existing.accepted_at = datetime.utcnow()
                db.session.commit()
                print("[ok] friendship flipped to accepted")
            else:
                print("[skip] friendship already accepted")

    print("[done] open the chat: /chat/" + str(bot.id))
    return 0


if __name__ == "__main__":
    sys.exit(main())
