# -*- coding: utf-8 -*-
"""
Seed/upsert script for AdaptiveTask — diagnostic tasks (level 4, grades 5–11).

Reads tasks from diagnostic_tasks.json and inserts/updates them into
AdaptiveTask table. Idempotent: dedup by (class_level, task_text).

Usage:
    python -m scripts.seed_diagnostic_tasks

Safe to run multiple times — already-existing tasks are updated in-place.
--------------------------------------------------------------------------------
NOT NULL constraints handled:
  - criteria_1_point / criteria_2_points  ->  placeholder ""
  - subject  ->  "math"
  - task_type  ->  "diagnostic"
  - source / source_id  ->  "diagnostic_seed" / sha256(text)[:40]
--------------------------------------------------------------------------------
Topic validation (grades 7–11 only):
  Asserts that each topic exactly matches a db_topic in
  ADAPTIVE_TOPICS_BY_GRADE (services/adaptive_topics_registry.py).
  Grades 5–6 topics are not registered there (they go via GradeTask path),
  so the assertion is skipped for those grades.
"""
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from models import db, AdaptiveTask
from services.adaptive_topics_registry import ADAPTIVE_TOPICS_BY_GRADE

TASKS_JSON_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "diagnostic_tasks.json",
)


def _build_source_id(task_text):
    """Return a stable 40-char hex digest from task_text for dedup via source_id."""
    return hashlib.sha256(task_text.encode("utf-8")).hexdigest()[:40]


def _validate_topic(grade, topic):
    """Assert that topic is valid for grades 7–11 (skip check for 5–6)."""
    if grade in (5, 6):
        return  # topics for 5–6 are not in the registry
    grade_topics = ADAPTIVE_TOPICS_BY_GRADE.get(grade)
    if grade_topics is None:
        raise ValueError(f"Grade {grade} not found in ADAPTIVE_TOPICS_BY_GRADE")
    valid_db_topics = {entry["db_topic"] for entry in grade_topics}
    if topic not in valid_db_topics:
        raise ValueError(
            f"Topic {topic!r} for grade {grade} is not a valid db_topic. "
            f"Valid topics: {sorted(valid_db_topics)}"
        )


def _derive_subject(topic):
    """Derive a broad subject from topic prefix."""
    prefix = topic.split(".")[0] if "." in topic else topic
    mapping = {
        "Алгебра": "math",
        "Геометрия": "math",
        "Теория чисел": "math",
        "Комбинаторика": "math",
        "Логика": "math",
    }
    return mapping.get(prefix, "math")


def upsert_task(data):
    """
    Insert or update a single AdaptiveTask row.
    Dedup: (class_level, task_text).
    Returns 'inserted' or 'updated'.
    """
    class_level = data["class_level"]
    topic = data["topic"]
    task_text = data["task_text"]
    correct_answer = data.get("correct_answer", "")
    solution = data.get("solution", "")
    difficulty_level = data.get("difficulty_level", 4)

    # Validate topic for grades 7–11
    _validate_topic(class_level, topic)

    # Look for existing row
    existing = AdaptiveTask.query.filter_by(
        class_level=class_level,
        task_text=task_text,
    ).first()

    source_id = _build_source_id(task_text)
    subject = _derive_subject(topic)

    payload = {
        "class_level": class_level,
        "difficulty_level": difficulty_level,
        "topic": topic,
        "task_text": task_text,
        "correct_answer": correct_answer,
        "solution": solution,
        "criteria_1_point": "",   # NOT NULL — no criteria for diagnostic tasks
        "criteria_2_points": "",  # NOT NULL
        "is_flagged": data.get("is_flagged", False),
        "source": "diagnostic_seed",
        "source_id": source_id,
        "subject": subject,
        "task_type": "diagnostic",
    }

    if existing is not None:
        for key, value in payload.items():
            if hasattr(existing, key):
                setattr(existing, key, value)
        return "updated"

    db.session.add(AdaptiveTask(**payload))
    return "inserted"


def main():
    if not os.path.isfile(TASKS_JSON_PATH):
        print(f"[ERROR] Tasks file not found: {TASKS_JSON_PATH}")
        sys.exit(1)

    with open(TASKS_JSON_PATH, "r", encoding="utf-8") as f:
        tasks = json.load(f)

    print(f"Loaded {len(tasks)} tasks from {TASKS_JSON_PATH}")
    print(f"Grades present: {sorted(set(t['class_level'] for t in tasks))}")

    with app.app_context():
        db.create_all()

        inserted = 0
        updated = 0
        errors = []

        for idx, task in enumerate(tasks):
            try:
                result = upsert_task(task)
                if result == "inserted":
                    inserted += 1
                else:
                    updated += 1
            except (ValueError, KeyError) as exc:
                errors.append((idx, str(exc)))
                print(f"  [ERROR] task #{idx} (grade {task.get('class_level')}): {exc}")

        db.session.commit()

    print(f"\nDone.")
    print(f"  Inserted: {inserted}")
    print(f"  Updated:  {updated}")
    print(f"  Errors:   {len(errors)}")
    if errors:
        print(f"  (see above for error details)")
    print(f"  Total:    {len(tasks)}")


if __name__ == "__main__":
    main()
