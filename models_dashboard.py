# -*- coding: utf-8 -*-
"""T6 — UserDashboardItem model.  Imported by models.py in the re-export block."""
from models import db
from datetime import datetime


class UserDashboardItem(db.Model):
    """User dashboard widget configuration — one row per (user, widget_key)."""
    __tablename__ = 'user_dashboard_items'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    widget_key = db.Column(db.String(64), nullable=False)
    position = db.Column(db.Integer, nullable=False, default=0)
    visible = db.Column(db.Boolean, nullable=False, default=False, server_default='0')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'widget_key', name='_udwi_user_key_unique'),
    )

    user = db.relationship('User', backref=db.backref('dashboard_items', lazy='dynamic'))

    def __repr__(self):
        return f'<UserDashboardItem uid={self.user_id} key={self.widget_key!r}>'
