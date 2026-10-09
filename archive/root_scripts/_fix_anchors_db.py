"""Delete all synthetic formyla_anchors and load real ones from data/anchors.jsonl."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app import app
from models import AdaptiveTask, db
from services.anchors import load_anchors

with app.app_context():
    # 1. Count and show before
    before = AdaptiveTask.query.filter(AdaptiveTask.source == 'formyla_anchors').count()
    print(f"Before: {before} tasks with source='formyla_anchors'")
    
    # Show synthetic samples
    synthetic = AdaptiveTask.query.filter(
        AdaptiveTask.source == 'formyla_anchors'
    ).limit(3).all()
    for t in synthetic:
        print(f"  id={t.id} topic={t.topic} statement={(t.task_text or '')[:60]}...")
    
    # 2. Delete all existing formyla_anchors
    deleted = AdaptiveTask.query.filter(AdaptiveTask.source == 'formyla_anchors').delete()
    db.session.commit()
    print(f"Deleted: {deleted} tasks")
    
    # Verify
    after_delete = AdaptiveTask.query.filter(AdaptiveTask.source == 'formyla_anchors').count()
    print(f"After delete: {after_delete} tasks")
    
    # 3. Load real anchors from data/anchors.jsonl
    result = load_anchors(dry_run=False)
    print(f"\nLoad result: {result}")
    
    # 4. Verify
    final = AdaptiveTask.query.filter(AdaptiveTask.source == 'formyla_anchors').count()
    print(f"\nFinal: {final} tasks with source='formyla_anchors'")
    
    # Show per-grade breakdown
    for grade in range(5, 12):
        count = AdaptiveTask.query.filter(
            AdaptiveTask.source == 'formyla_anchors',
            AdaptiveTask.class_level == grade
        ).count()
        print(f"  Grade {grade}: {count}")
    
    # Show first 3 real statements
    real = AdaptiveTask.query.filter(
        AdaptiveTask.source == 'formyla_anchors'
    ).order_by(AdaptiveTask.class_level, AdaptiveTask.id).limit(5).all()
    print(f"\nFirst 5 real tasks:")
    for t in real:
        print(f"  id={t.id} class={t.class_level} topic={t.topic} source_id={t.source_id}")
        print(f"    statement={(t.task_text or '')[:100]}")
        print(f"    answer={t.correct_answer}")
