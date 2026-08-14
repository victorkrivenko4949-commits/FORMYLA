# -*- coding: utf-8 -*-
"""Стресс-тест v3: 10 параллельных генераций с сохранением в БД + файл."""

import sys, os, time, asyncio, json, sqlite3

os.chdir(r'c:\Users\Redmi\Desktop\Новая папка (2)')
sys.path.insert(0, '.')

# Чистка
db = sqlite3.connect('instance/formyla.db')
db.execute("UPDATE daily_task_sets SET status='failed' WHERE status='generating'")
db.execute("UPDATE daily_generation_jobs SET state='failed',error_message='stale',finished_at=datetime('now') WHERE state='running'")
db.commit()
db.close()

from app import app, db as flask_db
from models import User
from daily_tasks.profile import build_profile
from daily_tasks.pipeline.orchestrator import run_daily_generation_pipeline, PipelineResult
from daily_tasks.services import enqueue_daily_generation

TOPICS = [
    "Квадратные уравнения", "Дробно-рациональные уравнения",
    "Системы уравнений", "Неравенства", "Функции и графики",
    "Арифметическая прогрессия", "Геометрическая прогрессия",
    "Текстовые задачи", "Модули и параметры", "Комбинаторика",
]

async def run_one_pipeline(profile, label):
    t0 = time.monotonic()
    try:
        result = await run_daily_generation_pipeline(profile)
        return {'label': label, 'result': result, 'time': time.monotonic()-t0, 'error': None}
    except Exception as e:
        return {'label': label, 'result': None, 'time': time.monotonic()-t0, 'error': str(e)}

async def main():
    with app.app_context():
        user = flask_db.session.get(User, 1)
        base_profile = build_profile(user.id)
        topics_full = base_profile.get('topics_full', [])
        
        print(f"User id=1 grade={base_profile.get('class_level')}")
        print(f"Topics in catalog: {len(topics_full)}")
        
        # 10 профилей с разными темами
        profiles = []
        for topic_name in TOPICS:
            p = dict(base_profile)
            matched = None
            for t in topics_full:
                if isinstance(t, dict) and topic_name.lower() in (t.get('topic') or '').lower():
                    matched = dict(t)
                    break
            if matched:
                p['weak_topics'] = [matched]
                p['strong_topics'] = []
            profiles.append((topic_name, p))
        
        print(f"\n{'='*60}")
        print("ЗАПУСК 10 ПАРАЛЛЕЛЬНЫХ ПАЙПЛАЙНОВ (100 потоков API)")
        print(f"{'='*60}\n")
        
        t0_total = time.monotonic()
        coros = [run_one_pipeline(p, label) for label, p in profiles]
        results = await asyncio.gather(*coros)
        total_t = time.monotonic() - t0_total
        
        # Вывод результатов
        print(f"\n{'='*60}")
        print(f"РЕЗУЛЬТАТЫ ({total_t:.0f} сек = {total_t/60:.1f} мин)")
        print(f"{'='*60}\n")
        
        all_tasks = []
        success = 0
        
        for i, r in enumerate(results):
            label = r['label']
            result = r['result']
            dt = r['time']
            err = r['error']
            
            if result and result.status == 'ready':
                success += 1
                n_valid = sum(1 for f in result.is_flagged if not f) if result.is_flagged else len(result.tasks)
                cost = round(sum(s.cost_usd for s in result.steps), 4) if result.steps else 0
                print(f"  [{i+1:2d}] ✅ {label[:25]:25s} valid={n_valid}/{len(result.tasks)} time={dt:.0f}s cost=${cost:.4f}")
                
                for j, task in enumerate(result.tasks):
                    spec = result.specs[j] if j < len(result.specs) else {}
                    flagged = result.is_flagged[j] if result.is_flagged and j < len(result.is_flagged) else False
                    all_tasks.append({
                        'pipeline': i+1, 'topic': label, 'position': j+1,
                        'task_text': task.get('task_text', ''),
                        'correct_answer': task.get('correct_answer', ''),
                        'difficulty_level': spec.get('difficulty_level', '?'),
                        'subtopic': spec.get('subtopic', '?'),
                        'flagged': flagged,
                    })
            else:
                err_msg = err or (result.error if result else 'no result')
                print(f"  [{i+1:2d}] ❌ {label[:25]:25s} FAILED time={dt:.0f}s err={err_msg[:60]}")
        
        print(f"\n  Итого: {success}/{len(results)} успешно")
        print(f"  Всего задач: {len(all_tasks)}")
        print(f"  Время: {total_t:.0f} сек ({total_t/60:.1f} мин)")
        
        # Сохраняем в JSON
        with open('_stress_results.json', 'w', encoding='utf-8') as f:
            json.dump(all_tasks, f, ensure_ascii=False, indent=2)
        
        # Сохраняем в БД
        from daily_tasks.models import DailyTaskSet, DailyTaskItem
        from datetime import date, datetime
        today = date.today()
        
        for i, r in enumerate(results):
            if not r['result'] or r['result'].status != 'ready':
                continue
            
            result = r['result']
            daily_set = DailyTaskSet(
                user_id=1, target_date=today, status='ready',
                triggered_by='stress_test',
                generated_at=datetime.utcnow(),
                class_level=base_profile.get('class_level'),
                reason_summary=f'Stress test: {r["label"]}',
            )
            flask_db.session.add(daily_set)
            flask_db.session.flush()
            
            for j, task in enumerate(result.tasks):
                spec = result.specs[j] if j < len(result.specs) else {}
                flagged = result.is_flagged[j] if result.is_flagged and j < len(result.is_flagged) else False
                item = DailyTaskItem(
                    daily_set_id=daily_set.id,
                    position=j+1,
                    subject=spec.get('subject'),
                    topic=spec.get('topic'),
                    subtopic=spec.get('subtopic'),
                    difficulty_level=spec.get('difficulty_level'),
                    task_text=task.get('task_text', ''),
                    correct_answer=task.get('correct_answer', ''),
                    is_flagged=flagged,
                    status='approved' if not flagged else 'flagged',
                )
                flask_db.session.add(item)
        
        flask_db.session.commit()
        print(f"\n  Сохранено в БД: {success} сетов, {len(all_tasks)} задач")

asyncio.run(main())
print("\n[DONE]")
