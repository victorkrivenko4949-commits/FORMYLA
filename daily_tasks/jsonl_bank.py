# -*- coding: utf-8 -*-
"""
jsonl_bank.py — Банк готовых задач из _all_tasks.jsonl

Ключ: (grade, topic, level) — точный подбор по куратору.
"""
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_BANK_PATH = Path(__file__).resolve().parents[1] / "_all_tasks.jsonl"
_index: Dict[Tuple[int, str, int], List[Dict]] = {}
_loaded = False


def load():
    global _loaded, _index
    if _loaded:
        return
    if not _BANK_PATH.exists():
        logger.warning("jsonl_bank: %s not found — using stubs", _BANK_PATH)
        _load_stubs()
        _loaded = True
        return
    with open(_BANK_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = (d.get('grade', 0), d.get('topic', ''), d.get('level', 0))
            _index.setdefault(key, []).append(d)
            _loaded = True
            total = sum(len(v) for v in _index.values())
            logger.info("jsonl_bank: loaded %d tasks for %d keys", total, len(_index))
        
        
        def _load_stubs():
            """Generate placeholder tasks for testing the pipeline."""
            from daily_tasks.pipeline.slot_planner import THEMES_BY_GRADE as _T
            for grade in [5, 6, 7, 8, 9, 10, 11]:
                for topic in _T.get(grade, _T[5]):
                    for level in [1, 2, 3, 4]:
                        key = (grade, topic, level)
                        tasks = []
                        count = {1: 5, 2: 10, 3: 10, 4: 10}[level]
                        for pos in range(1, count + 1):
                            tasks.append({
                                'grade': grade, 'topic': topic, 'level': level,
                                'position': pos,
                                'task_text': f'[ЗАГЛУШКА] G{grade} | Неделя {level} | {topic} | Задача {pos}/{count}',
                                'correct_answer': f'Ответ-{pos}',
                                'generated_at': '2026-08-09T00:00:00',
                            })
                        _index[key] = tasks
            logger.info("jsonl_bank: loaded %d stub tasks for %d keys",
                        sum(len(v) for v in _index.values()), len(_index))


def get_tasks(grade: int, topic: str, level: int,
              count: int = 10) -> List[Dict]:
    load()
    key = (grade, topic, level)
    tasks = sorted(_index.get(key, []), key=lambda t: t.get('position', 0))
    # If not enough, try any level for same grade+topic
    if len(tasks) < count:
        for lv in [4, 3, 2, 1]:
            if lv == level:
                continue
            extra = _index.get((grade, topic, lv), [])
            tasks.extend(extra)
            if len(tasks) >= count:
                break
    # De-duplicate by position
    seen = set()
    unique = []
    for t in sorted(tasks, key=lambda t: t.get('position', 0)):
        p = t.get('position', 0)
        if p not in seen:
            seen.add(p)
            unique.append(t)
    return unique[:count]


def available_topics(grade: int) -> List[str]:
    load()
    topics = set()
    for (g, t, _), v in _index.items():
        if g == grade and v:
            topics.add(t)
    return sorted(topics)


def task_count(grade: int, topic: str, level: int) -> int:
    load()
    return len(_index.get((grade, topic, level), []))
