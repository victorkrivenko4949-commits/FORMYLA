# -*- coding: utf-8 -*-
"""Аудит: какие темы AdaptiveTask реально лежат в БД для каждого класса 5..11."""
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from app import app, db   # noqa: E402
from models import AdaptiveTask  # noqa: E402
from collections import Counter

with app.app_context():
    for g in range(5, 12):
        rows = AdaptiveTask.query.filter_by(class_level=g, is_flagged=False).all()
        c = Counter([(r.topic or '<no topic>') for r in rows])
        print('=' * 70)
        print('GRADE %d   total=%d   distinct_topics=%d'
              % (g, len(rows), len(c)))
        print('-' * 70)
        for t, n in c.most_common(30):
            print('  %5d   %s' % (n, t[:90]))
