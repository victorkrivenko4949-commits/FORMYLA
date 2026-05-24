# -*- coding: utf-8 -*-
"""
Аналитика + Отзывы.

Модели вынесены в отдельный файл, чтобы не раздувать models.py.
Импортируются в models.py поздним импортом (см. конец models.py).
"""

from datetime import datetime

from models import db


class Event(db.Model):
    """Событие пользователя/анонима.

    Используется для воронки, UTM-источников, A/B, активации, retention.
    """
    __tablename__ = 'events'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
    )
    session_id = db.Column(db.String(64), index=True)  # для анонимов
    event = db.Column(db.String(64), nullable=False, index=True)

    # UTM-метки
    utm_source = db.Column(db.String(64))
    utm_medium = db.Column(db.String(64))
    utm_campaign = db.Column(db.String(64))
    utm_content = db.Column(db.String(64))

    # Контекст
    path = db.Column(db.String(256))
    referer = db.Column(db.String(512))
    user_agent = db.Column(db.String(512))
    ip = db.Column(db.String(64))

    # Доп. данные (произвольный JSON)
    meta = db.Column(db.JSON)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        db.Index('ix_events_event_created', 'event', 'created_at'),
        db.Index('ix_events_user_created', 'user_id', 'created_at'),
        db.Index('ix_events_utm_campaign_content', 'utm_campaign', 'utm_content'),
        db.Index('ix_events_session_created', 'session_id', 'created_at'),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f'<Event {self.event} user={self.user_id} session={self.session_id}>'


class Review(db.Model):
    """Отзыв об обучении на FORMYLA.

    Карусель показывается на /, /about, /welcome, /subscribe.
    Управляется через /admin/reviews.
    """
    __tablename__ = 'reviews'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False, default='Аноним')
    role = db.Column(db.String(64))   # ученик / родитель / преподаватель
    grade = db.Column(db.String(16))  # «9 класс»
    text = db.Column(db.Text, nullable=False, default='')
    rating = db.Column(db.Integer, default=5)
    avatar_url = db.Column(db.String(256))
    is_published = db.Column(db.Boolean, default=False, nullable=False, index=True)
    sort_order = db.Column(db.Integer, default=0, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:  # pragma: no cover
        return f'<Review #{self.id} {self.name!r} pub={self.is_published}>'

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'role': self.role,
            'grade': self.grade,
            'text': self.text,
            'rating': self.rating or 5,
            'avatar_url': self.avatar_url,
            'is_published': bool(self.is_published),
            'sort_order': self.sort_order or 0,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
