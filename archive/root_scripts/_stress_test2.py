# -*- coding: utf-8 -*-
"""Стресс-тест v2: 10 параллельных генераций через прямой вызов пайплайна."""

import sys, os, time, asyncio, json

os.chdir(r'c:\Users\Redmi\Desktop\Новая папка (2)')
sys.path.insert(0, '.')

from app import app, db
from models import User
from daily_tasks.profile import build_profile
from daily_tasks.pipeline.orchestrator import run_daily_generation_pipeline
from datetime import datetime

TOPICS = [
    "Квадратные уравнения", "Дробно-рациональные уравнения",
    "Системы уравнений", "Неравенства", "Функции и графики",
    "Арифметическая прогрессия", "Геометрическая прогрессия",
    "Текстовые задачи", "Модули и параметры", "Комбинаторика",
]

async def run_one(profile, label):
    """Запуск одного пайплайна."""
    t0 = time.monotonic()
    result = await run_daily_generation_pipeline(profile)
    dt = time.monotonic() - t0
    return {
        'label': label,
        'status': result.status,
        'tasks': len(result.tasks),
        'valid': sum(1 for f in result.is_flagged if not f) if result.is_flagged else len(result.tasks),
        'time': dt,
        'error': result.error or '',
        'cost': round(sum(s.cost_usd for s in result.steps), 4) if result.steps else 0,
    }

async def main():
    with app.app_context():
        user = db.session.get(User, 1)
        profile = build_profile(user.id)
        grade = profile.get('class_level', 9)
        topics_full = profile.get('topics_full', [])
        
        print(f"User: id={user.id} grade={grade}")
        print(f"Topics in catalog: {len(topics_full)}")
        print(f"\n{'='*60}")
        print("ЗАПУСК 10 ПАРАЛЛЕЛЬНЫХ ПАЙПЛАЙНОВ")
        print(f"{'='*60}\n")
        
        # Создаём 10 профилей с разными темами (берём из topics_full)
        profiles = []
        for i, topic_name in enumerate(TOPICS):
            p = dict(profile)
            # Ищем соответствующую тему в каталоге
            matched = None
            for t in topics_full:
                if isinstance(t, dict) and topic_name.lower() in (t.get('topic') or '').lower():
                    matched = dict(t)
                    break
            if matched:
                p['weak_topics'] = [matched]
                p['strong_topics'] = []
                p['calibration_topics'] = []
            profiles.append((topic_name, p))
        
        # Запускаем все 10 параллельно
        t0_total = time.monotonic()
        coros = [run_one(p, label) for label, p in profiles]
        results = await asyncio.gather(*coros)
        total_t = time.monotonic() - t0_total
        
        print(f"\n{'='*60}")
        print(f"РЕЗУЛЬТАТЫ (общее время: {total_t:.1f} сек)")
        print(f"{'='*60}\n")
        
        total_tasks = 0
        total_valid = 0
        total_cost = 0
        for r in results:
            icon = '✅' if r['status'] == 'ready' else '❌'
            print(f"  {icon} {r['label'][:25]:25s} "
                  f"status={r['status']:8s} tasks={r['tasks']} valid={r['valid']} "
                  f"time={r['time']:.0f}s cost=${r['cost']:.4f} "
                  f"err={r['error'][:50]}")
            if r['status'] == 'ready':
                total_tasks += r['tasks']
                total_valid += r['valid']
                total_cost += r['cost']
        
        print(f"\n  ИТОГО: {sum(1 for r in results if r['status']=='ready')}/{len(results)} успешно")
        print(f"  Задач: {total_tasks} (валидных: {total_valid})")
        print(f"  Стоимость: ${total_cost:.4f}")
        print(f"  Среднее время: {sum(r['time'] for r in results)/len(results):.0f} сек на генерацию")
        
        if total_cost > 0:
            print(f"\n  Стоимость на пользователя: ${total_cost/len(results):.4f}")
            print(f"  Стоимость на 300 польз./день (без кэша): ${total_cost*30:.2f}")
            print(f"  Стоимость на 300 польз./день (с кэшем 85%): ${total_cost*30*0.15:.2f}")

asyncio.run(main())
print("\n[DONE]")
