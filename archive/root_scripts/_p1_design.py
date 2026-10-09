# -*- coding: utf-8 -*-
import re, os

ALLOWED = {'#070C18', '#0E1830', '#121F3C', '#1C2B4F', '#E6EBF7', '#8C9ABC', '#4C7DFF', '#6B95FF', '#3ECF8E', '#E5AC3A', '#E86A62'}
templates = [
    'templates/figures.html',
    'templates/prep/probe.html',
    'templates/daily_tasks/daily_tasks_dashboard.html',
    'templates/olympiad/method.html',
    'templates/olympiad/method_task.html',
]

emoji_re = re.compile(r'[\U0001F300-\U0001FAFF\u2600-\u27BF\u2700-\u27BF]')

for t in templates:
    if not os.path.exists(t):
        print(t, 'NOT FOUND')
        continue
    text = open(t, encoding='utf-8').read()
    colors = set(m.upper() for m in re.findall(r'#[0-9A-Fa-f]{6}', text))
    foreign = colors - ALLOWED
    print(t, 'FOREIGN_HEX', foreign, 'EMOJI', emoji_re.findall(text))
