#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Quick merge of _new_fill_tasks.json into adaptive_full_9120_fixed.json."""
import json
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DB_PATH = "adaptive_data/adaptive_full_9120_fixed.json"
NEW_TASKS_PATH = "adaptive_data/_new_fill_tasks.json"

def merge_into_db(db: list, new_tasks: list) -> list:
    existing_texts = set()
    for t in db:
        stmt = t.get('statement', '').strip()
        if stmt:
            existing_texts.add(stmt[:100].lower().replace(' ', ''))

    added = 0
    skipped = 0
    for t in new_tasks:
        stmt = t.get('statement', '').strip()
        if not stmt:
            continue
        fingerprint = stmt[:100].lower().replace(' ', '')
        if fingerprint in existing_texts:
            skipped += 1
            continue
        existing_texts.add(fingerprint)
        max_id = max((int(x.get('id', 0)) for x in db if str(x.get('id', '')).isdigit()), default=0)
        t['id'] = max_id + 1 + added
        db.append(t)
        added += 1

    logger.info(f"Merged: +{added} new tasks, skipped {skipped} duplicates")
    return db

def main():
    logger.info("Loading DB...")
    with open(DB_PATH, 'r', encoding='utf-8') as f:
        db = json.load(f)
    logger.info(f"DB has {len(db)} tasks before merge")

    logger.info("Loading new tasks...")
    with open(NEW_TASKS_PATH, 'r', encoding='utf-8') as f:
        new_tasks = json.load(f)
    logger.info(f"New tasks: {len(new_tasks)}")

    db = merge_into_db(db, new_tasks)

    with open(DB_PATH, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=2)
    logger.info(f"Saved DB with {len(db)} tasks")

if __name__ == '__main__':
    main()
