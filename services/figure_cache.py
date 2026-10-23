# -*- coding: utf-8 -*-
"""
services/figure_cache.py — Кеш готовых SVG-чертежей.

Имя файла — SHA256-отпечаток figure_json (описания построений).
Одинаковое описание не рисуется дважды.
При изменении описания отпечаток меняется, старый файл остаётся до чистки.
"""

import hashlib
import json
import os
import sys
import time
from typing import Optional, Tuple

# Путь к папке кеша
_CACHE_DIR = os.path.join(
    os.path.dirname(__file__), '..', 'static', 'figures', 'cache'
)


def _ensure_cache_dir() -> str:
    """Создать папку кеша, если её нет."""
    os.makedirs(_CACHE_DIR, exist_ok=True)
    return _CACHE_DIR


def figure_hash(figure_json: str) -> str:
    """SHA256-отпечаток от канонического JSON-описания построений.

    Возвращает 64-символьную hex-строку.
    """
    if isinstance(figure_json, dict):
        # Каноническая сериализация: отсортированные ключи, без пробелов
        canonical = json.dumps(figure_json, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    else:
        # Парсим строку и пересериализуем канонически
        try:
            parsed = json.loads(figure_json)
            canonical = json.dumps(parsed, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
        except (json.JSONDecodeError, TypeError):
            canonical = str(figure_json)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def svg_path_for_hash(h: str) -> str:
    """Путь к SVG-файлу по хешу."""
    _ensure_cache_dir()
    return os.path.join(_CACHE_DIR, f'{h}.svg')


def svg_exists(h: str) -> bool:
    """Проверить, есть ли готовый SVG в кеше."""
    return os.path.isfile(svg_path_for_hash(h))


def cache_svg(h: str, svg_content: str) -> str:
    """Сохранить SVG в кеш. Возвращает путь к файлу."""
    _ensure_cache_dir()
    fpath = svg_path_for_hash(h)
    with open(fpath, 'w', encoding='utf-8') as f:
        f.write(svg_content)
    return fpath


def get_cached_svg(h: str) -> Optional[str]:
    """Прочитать SVG из кеша. None если нет."""
    fpath = svg_path_for_hash(h)
    if not os.path.isfile(fpath):
        return None
    with open(fpath, 'r', encoding='utf-8') as f:
        return f.read()


def build_figure(figure_json: str, task_id: int = 0) -> Tuple[str, str, float, bool]:
    """Построить чертёж из figure_json, с кешированием по хешу.

    Аргументы:
        figure_json: JSON-строка или dict с описанием построений
        task_id: ID задачи для логирования

    Возвращает:
        (svg_content, hash, elapsed_seconds, was_cached)
    """
    h = figure_hash(figure_json)

    # Проверяем кеш
    cached = get_cached_svg(h)
    if cached is not None:
        return cached, h, 0.0, True

    # Строим
    t0 = time.perf_counter()

    # Добавляем корень проекта в sys.path для импорта geometric_engine
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _root not in sys.path:
        sys.path.insert(0, _root)

    from geometric_engine.engine import GeometricEngine, EngineSettings

    engine = GeometricEngine()

    # Парсим описание
    if isinstance(figure_json, str):
        try:
            description = json.loads(figure_json)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid figure_json JSON: {e}")
    else:
        description = figure_json

    # Валидация
    errors = engine.validate_description(description)
    if errors:
        raise ValueError(f"Figure description validation errors: {'; '.join(errors)}")

    # Построение с retry
    svg, ctx, attempts, violations = engine.build_with_retry(description, seed=task_id % 10000)

    if violations:
        raise RuntimeError(
            f"Engine rejected figure for task {task_id} after {attempts} attempts: "
            + '; '.join(violations)
        )

    elapsed = time.perf_counter() - t0

    # Сохраняем в кеш
    cache_svg(h, svg)

    return svg, h, elapsed, False


def get_figure_url_for_task(task) -> Optional[str]:
    """URL к SVG-чертежу для задачи (DailyTaskItem или AdaptiveTask).

    Если figure_json заполнен и чертёж построен (figure_built),
    возвращает URL вида /static/figures/cache/<hash>.svg.
    Иначе None.
    """
    figure = getattr(task, 'figure_json', None)
    status = getattr(task, 'figure_status', None)
    if not figure or status != 'figure_built':
        return None
    h = figure_hash(figure)
    if svg_exists(h):
        return f'/static/figures/cache/{h}.svg'
    return None


# ──────────────────────────────────────────────────────────────────────
# Список орфанных файлов (для скрипта очистки)
# ──────────────────────────────────────────────────────────────────────

def used_hashes_from_db() -> set:
    """Собрать все хеши figure_json, которые реально используются в БД."""
    from app import app
    from models import db
    from sqlalchemy import text

    with app.app_context():
        rows = db.session.execute(text(
            "SELECT id, figure_json FROM adaptive_tasks WHERE figure_json IS NOT NULL"
        )).fetchall()

        used = set()
        for row in rows:
            try:
                h = figure_hash(row[1])
                used.add(h)
            except Exception:
                pass
        return used


def list_orphan_files() -> list:
    """Список файлов в кеше, которые не используются ни одной задачей."""
    _ensure_cache_dir()
    used = used_hashes_from_db()

    orphans = []
    for fname in os.listdir(_CACHE_DIR):
        if fname.endswith('.svg'):
            h = fname[:-4]  # отрезаем .svg
            if h not in used:
                fpath = os.path.join(_CACHE_DIR, fname)
                orphans.append((fpath, os.path.getsize(fpath)))
    return orphans
