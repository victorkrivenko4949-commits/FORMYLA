#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import io
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from app import app
from models import db, AdaptiveTask

with app.app_context():
    cols = [c.name for c in AdaptiveTask.__table__.columns]
    print("Columns:", cols)
    
    count = AdaptiveTask.query.count()
    print(f"Total tasks: {count}")
    
    has_subtopic = 'subtopic' in cols
    print(f"Has subtopic field: {has_subtopic}")
    
    topics = db.session.query(
        AdaptiveTask.topic, 
        db.func.count(AdaptiveTask.id)
    ).group_by(AdaptiveTask.topic).all()
    
    print("\nTopics distribution:")
    for t, c in topics:
        print(f"  {t}: {c}")
    
    # Check grade distribution
    grades = db.session.query(
        AdaptiveTask.class_level,
        db.func.count(AdaptiveTask.id)
    ).group_by(AdaptiveTask.class_level).all()
    
    print("\nGrade distribution:")
    for g, c in grades:
        print(f"  Grade {g}: {c}")
