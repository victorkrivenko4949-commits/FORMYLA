# -*- coding: utf-8 -*-
"""
services/figures_service.py — Чертежи для якорных задач и витрина.

Выбор связи: имя файла по anchor_uid (A_G5_GEO → A_G5_GEO.svg),
потому что канонический anchor_uid уже уникален и не требует ни поля в БД,
ни отдельного файла соответствия; для будущих обычных задач зарезервировано
поле figure_json (описание построения) в таблице задач.

Файлы лежат в static/figures/anchors/.
Статус приёмки — static/figures/anchors/REVIEW_STATUS.json.
"""

import json
import os
import random
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from flask import url_for

# ──────────────────────────────────────────────────────────────────────
# Пути
# ──────────────────────────────────────────────────────────────────────

_ANCHORS_DIR = os.path.join(
    os.path.dirname(__file__), '..', 'static', 'figures', 'anchors'
)
_REVIEW_FILE = os.path.join(_ANCHORS_DIR, 'REVIEW_STATUS.json')

# ──────────────────────────────────────────────────────────────────────
# Статус приёмки
# ──────────────────────────────────────────────────────────────────────


def _load_review_status() -> Dict[str, Dict]:
    """Загрузить REVIEW_STATUS.json."""
    try:
        with open(_REVIEW_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_review_status(data: Dict):
    """Сохранить REVIEW_STATUS.json атомарно."""
    tmp = _REVIEW_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _REVIEW_FILE)


def get_anchor_figures() -> List[Dict[str, Any]]:
    """Получить все якоря, у которых есть SVG-файл + статус из REVIEW_STATUS."""
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        from models import AdaptiveTask
        from app import app as _flask_app
    except Exception:
        # Fallback — читаем anchors.jsonl напрямую
        return _get_anchor_figures_from_file()

    review = _load_review_status()
    results = []

    try:
        with _flask_app.app_context():
            from models import db as _db
            tasks = (
                _db.session.query(AdaptiveTask)
                .filter(AdaptiveTask.source == 'formyla_anchors')
                .filter(AdaptiveTask.subject == 'geometry')
                .all()
            )
            for t in tasks:
                uid = t.source_id or ''
                svg_path = os.path.join(_ANCHORS_DIR, f'{uid}.svg')
                has_figure = os.path.isfile(svg_path)
                entry = review.get(uid, {})
                results.append({
                    'anchor_uid': uid,
                    'task_id': t.id,
                    'statement': (t.task_text or '')[:200],
                    'grade': t.class_level,
                    'subtopic': t.subtopic or '',
                    'has_figure': has_figure,
                    'figure_url': url_for('static', filename=f'figures/anchors/{uid}.svg') if has_figure else None,
                    'status': entry.get('status', 'pending'),
                    'seed': entry.get('seed', 42),
                    'attempts': entry.get('attempts', 0),
                    'reviewed_at': entry.get('reviewed_at'),
                    'accepted_at': entry.get('accepted_at'),
                })
    except Exception as e:
        print(f"[figures_service] DB query failed, falling back: {e}")
        return _get_anchor_figures_from_file()

    return results


def _get_anchor_figures_from_file() -> List[Dict]:
    """Fallback: загрузить из anchors.jsonl напрямую."""
    anchors_file = os.path.join(
        os.path.dirname(__file__), '..', 'data', 'anchors.jsonl'
    )
    review = _load_review_status()
    results = []

    try:
        with open(anchors_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    a = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if a.get('section', '').lower() != 'geometry':
                    continue
                uid = a.get('anchor_uid', '')
                svg_path = os.path.join(_ANCHORS_DIR, f'{uid}.svg')
                has_figure = os.path.isfile(svg_path)
                entry = review.get(uid, {})
                results.append({
                    'anchor_uid': uid,
                    'task_id': 0,
                    'statement': (a.get('statement', ''))[:200],
                    'grade': a.get('grade', 0),
                    'subtopic': a.get('subtopic', ''),
                    'has_figure': has_figure,
                    'figure_url': f'/static/figures/anchors/{uid}.svg' if has_figure else None,
                    'status': entry.get('status', 'pending'),
                    'seed': entry.get('seed', 42),
                    'attempts': entry.get('attempts', 0),
                    'reviewed_at': entry.get('reviewed_at'),
                    'accepted_at': entry.get('accepted_at'),
                })
    except FileNotFoundError:
        pass

    return results


def accept_figure(anchor_uid: str) -> Dict:
    """Пометить чертёж как проверенный."""
    review = _load_review_status()
    now = datetime.now(timezone.utc).isoformat()
    if anchor_uid not in review:
        review[anchor_uid] = {
            'status': 'pending', 'reviewed_at': None,
            'seed': 42, 'attempts': 0, 'accepted_at': None,
        }
    review[anchor_uid]['status'] = 'accepted'
    review[anchor_uid]['reviewed_at'] = now
    review[anchor_uid]['accepted_at'] = now
    _save_review_status(review)
    return review[anchor_uid]


def reject_figure(anchor_uid: str) -> Dict:
    """Пометить чертёж как отклонённый."""
    review = _load_review_status()
    now = datetime.now(timezone.utc).isoformat()
    if anchor_uid not in review:
        review[anchor_uid] = {
            'status': 'pending', 'reviewed_at': None,
            'seed': 42, 'attempts': 0, 'accepted_at': None,
        }
    review[anchor_uid]['status'] = 'rejected'
    review[anchor_uid]['reviewed_at'] = now
    _save_review_status(review)
    return review[anchor_uid]


def rebuild_figure(anchor_uid: str) -> Dict:
    """Перерисовать чертёж с новым семенем.

    Вызывает geometric_engine для построения заново.
    """
    review = _load_review_status()
    entry = review.get(anchor_uid, {
        'status': 'pending', 'reviewed_at': None,
        'seed': 42, 'attempts': 0, 'accepted_at': None,
    })

    new_seed = random.randint(1, 99999)
    entry['seed'] = new_seed
    entry['attempts'] = entry.get('attempts', 0) + 1
    entry['status'] = 'pending'  # сброс статуса при перерисовке

    # Попытаться построить
    construction_file = os.path.join(
        _ANCHORS_DIR, f'{anchor_uid}.json'
    )
    svg_file = os.path.join(_ANCHORS_DIR, f'{anchor_uid}.svg')

    if os.path.isfile(construction_file):
        try:
            import subprocess
            import sys
            result = subprocess.run(
                [sys.executable, '-m', 'geometric_engine.cli',
                 construction_file, '-o', svg_file, '-s', str(new_seed)],
                capture_output=True, text=True, timeout=60,
                cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            )
            if result.returncode != 0:
                print(f"[figures_service] rebuild {anchor_uid} FAILED: {result.stderr}")
                entry['build_error'] = result.stderr[:500]
            else:
                entry.pop('build_error', None)
        except Exception as e:
            print(f"[figures_service] rebuild {anchor_uid} exception: {e}")
            entry['build_error'] = str(e)[:500]
    else:
        entry['build_error'] = f'Construction file not found: {construction_file}'

    review[anchor_uid] = entry
    _save_review_status(review)

    return {
        **entry,
        'figure_url': f'/static/figures/anchors/{anchor_uid}.svg',
    }


def get_counts() -> Dict[str, int]:
    """Счётчики: всего, проверено, отклонено, не смотрели."""
    review = _load_review_status()
    total = 0
    accepted = 0
    rejected = 0
    pending = 0

    for uid, entry in review.items():
        if uid.startswith('_'):
            continue
        total += 1
        st = entry.get('status', 'pending')
        if st == 'accepted':
            accepted += 1
        elif st == 'rejected':
            rejected += 1
        else:
            pending += 1

    return {
        'total': total,
        'accepted': accepted,
        'rejected': rejected,
        'pending': pending,
    }


def get_figure_for_anchor(anchor_uid: str) -> Optional[str]:
    """Вернуть URL фигуры для якоря или None."""
    svg_path = os.path.join(_ANCHORS_DIR, f'{anchor_uid}.svg')
    if os.path.isfile(svg_path):
        return url_for('static', filename=f'figures/anchors/{anchor_uid}.svg')
    return None
