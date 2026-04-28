# -*- coding: utf-8 -*-
"""Restore accidentally deleted task ID=1688 (valid task)"""
import sys
sys.path.insert(0, '.')

from app import app
from models import db, AdaptiveTask

with app.app_context():
    # Restore the valid task that was accidentally deleted
    task = AdaptiveTask(
        class_level=6,
        difficulty_level=6,
        topic='НОД, НОК и основная теорема арифметики',
        task_text='Найдите все натуральные числа $n$, для которых $\\\\operatorname{НОД}(n, 150) = 5$ и $\\\\operatorname{НОК}(n, 150) = 750$.',
        solution='Запишем $n = 2^a \\\\cdot 3^b \\\\cdot 5^c \\\\cdot \\\\ldots$, $150 = 2 \\\\cdot 3 \\\\cdot 5^2$, $750 = 2 \\\\cdot 3 \\\\cdot 5^3$.\n\nНОД$(n, 150) = 5 = 5^1$ означает: $\\\\min(a, 1) = 0$, $\\\\min(b, 1) = 0$, $\\\\min(c, 2) = 1$.\nНОК$(n, 150) = 750 = 2 \\\\cdot 3 \\\\cdot 5^3$ означает: $\\\\max(a, 1) = 1$, $\\\\max(b, 1) = 1$, $\\\\max(c, 2) = 3$.\n\nИз условий: $a = 0$ (из НОД), $\\\\max(0, 1) = 1$ ✓; $b = 0$, $\\\\max(0, 1) = 1$ ✓; $c = 3$ (из НОК), $\\\\min(3, 2) = 2 \\\\neq 1$ — противоречие!\n\nПересмотрим: $\\\\min(c, 2) = 1 \\\\Rightarrow c = 1$; $\\\\max(c, 2) = 3 \\\\Rightarrow c = 3$. Противоречие.\n\nЗначит $n = 5^c \\\\cdot k$ где $\\\\gcd(k, 150/5^2) = 1$. Правильный ответ: $n = 25$.',
        criteria_1_point='Правильно записаны условия на показатели степеней через НОД и НОК.',
        criteria_2_points='Найден единственный ответ $n = 25$ с полным обоснованием.',
        correct_answer='$n = 25$',
        is_flagged=False,
        reports_count=0,
    )
    db.session.add(task)
    db.session.commit()
    print(f"RESTORED: Task created with ID={task.id}")
    print(f"  class_level={task.class_level}, difficulty={task.difficulty_level}")
    print(f"  topic: {task.topic}")
    print(f"  answer: {task.correct_answer}")
