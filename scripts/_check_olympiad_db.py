# -*- coding: utf-8 -*-
"""Quick sanity check: look at what landed in olympiad_tasks."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from models import db
from models_olympiad import OlympiadTask, Probnik, TheoryBlock

with app.app_context():
    total = OlympiadTask.query.count()
    real = OlympiadTask.query.filter(~OlympiadTask.condition_md.like('TODO%')).count()
    placeholder = OlympiadTask.query.filter(OlympiadTask.condition_md.like('TODO%')).count()
    print(f'olympiad_tasks total: {total}')
    print(f'  with real condition_md: {real}')
    print(f'  with TODO placeholder : {placeholder}')

    t = OlympiadTask.query.filter_by(number='1.1').first()
    print(f'\nfirst task #1.1 from topic-1:')
    print(f'  method_primary = {t.method_primary}')
    print(f'  answer         = {t.answer!r}')
    print(f'  condition_md   = {t.condition_md[:120]!r}…')
    print(f'  solution_md    = {t.solution_md[:120]!r}…')

    print(f'\nprobniks: {Probnik.query.count()}')
    print(f'theory blocks: {TheoryBlock.query.count()}')
