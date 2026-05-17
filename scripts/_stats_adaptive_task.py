# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import app
from models import AdaptiveTask, db
from sqlalchemy import func

with app.app_context():
    total = AdaptiveTask.query.count()
    print('TOTAL AdaptiveTask rows:', total)
    rows = db.session.query(
        AdaptiveTask.class_level,
        AdaptiveTask.is_flagged,
        func.count(),
    ).group_by(AdaptiveTask.class_level, AdaptiveTask.is_flagged).all()
    for cl, fl, n in rows:
        print('  level=%r flagged=%r count=%d' % (cl, fl, n))

    # Топ topic по 7-11
    print('\nTop topics for grade 7-11 (not flagged):')
    rows2 = db.session.query(
        AdaptiveTask.class_level, AdaptiveTask.topic, func.count()
    ).filter(
        AdaptiveTask.is_flagged == False,
        AdaptiveTask.class_level.in_([7,8,9,10,11]),
    ).group_by(AdaptiveTask.class_level, AdaptiveTask.topic).order_by(func.count().desc()).limit(20).all()
    for cl, t, n in rows2:
        print('  g=%s topic=%r n=%d' % (cl, t, n))
