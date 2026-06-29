# -*- coding: utf-8 -*-
"""FORMYLA AI-Curator data models (Step 0).
New tables: curator_state, subtopics, subtopic_progress.
Import these models from models.py / app.py so SQLAlchemy registers them.
"""
from datetime import datetime
from models import db

class CuratorState(db.Model):
"""Persistent profile of a student for the AI curator (1:1 with User)."""
__tablename__ = 'curator_state'
user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, unique=True, index=True)
target_olympiads = db.Column(db.JSON, default=list)
grade = db.Column(db.Integer, nullable=True)
goal_text = db.Column(db.Text, nullable=True)
prep_plan = db.Column(db.JSON, default=dict)
onboarding_done = db.Column(db.Boolean, default=False, nullable=False)
last_diagnostic_id = db.Column(db.Integer, db.ForeignKey('adaptive_test_results.id', ondelete='SET NULL'), nullable=True)
summary = db.Column(db.Text, nullable=True)
created_at = db.Column(db.DateTime, default=datetime.utcnow)
updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
user = db.relationship('User', backref=db.backref('curator_state', uselist=False, cascade='all, delete-orphan')

class Subtopic(db.Model):
__tablename__ = 'subtopics'
id = db.Column(db.Integer, primary_key=True)
slug = db.Column(db.String(100), unique=True, nullable=False, index=True)
title = db.Column(db.String(200), nullable=False)
parent_topic = db.Column(db.String(50), nullable=True, index=True)
olympiad_weights = db.Column(db.JSON, default=dict)
is_active = db.Column(db.Boolean, default=True, nullable=False)
created_at = db.Column(db.DateTime, default=datetime.utcnow

class SubtopicProgress(db.Model):
__tablename__ = 'subtopic_progress'
id = db.Column(db.Integer, primary_key=True)
user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
subtopic_id = db.Column(db.Integer, db.ForeignKey('subtopics.id', ondelete='CASCADE'), nullable=False, index=True)
mastery = db.Column(db.Float, default=0.0)
attempts = db.Column(db.Integer, default=0)
correct = db.Column(db.Integer, default=0)
last_seen_at = db.Column(db.DateTime, nullable=True)
updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
subtopic = db.relationship('Subtopic')
__table_args__ = (db.UniqueConstraint('user_id', 'subtopic_id', name='uq_subtopic_progress'),)
