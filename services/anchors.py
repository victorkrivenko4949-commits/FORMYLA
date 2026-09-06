# -*- coding: utf-8 -*-
"""
services/anchors.py — Якорные задачи анкеты (formyla_anchors).

Загружает data/anchors.jsonl (35 задач, по 5 на класс 5-11, ровно по одной
на раздел), сохраняет в AdaptiveTask с source='formyla_anchors',
предоставляет подбор якорей и нормализованную проверку ответов.

Поля JSONL: anchor_uid, grade, section, subtopic, level, statement, answer.
"""

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from models import db, AdaptiveTask

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# Константы
# ──────────────────────────────────────────────────────────────────────

SOURCE_NAME = 'formyla_anchors'
ANCHORS_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'anchors.jsonl')
THEME_MAP_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'theme_to_section.json')

# Канонические разделы в порядке приоритета (п.4)
CANONICAL_SECTIONS_ORDER = ('algebra', 'number_theory', 'geometry', 'combinatorics', 'logic')

# ──────────────────────────────────────────────────────────────────────
# Загрузка справочника theme -> section
# ──────────────────────────────────────────────────────────────────────

def _load_theme_map() -> Dict[str, str]:
    """Загрузить data/theme_to_section.json -> {theme_id: section_slug}."""
    try:
        with open(THEME_MAP_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning("theme_to_section.json не загружен: %s", e)
        return {}


# Глобальный кэш справочника (загружается один раз)
_THEME_MAP: Optional[Dict[str, str]] = None


def get_theme_map() -> Dict[str, str]:
    """Получить справочник theme_id -> section (с кэшированием)."""
    global _THEME_MAP
    if _THEME_MAP is None:
        _THEME_MAP = _load_theme_map()
    return _THEME_MAP


# ──────────────────────────────────────────────────────────────────────
# Загрузка anchors.jsonl в AdaptiveTask
# ──────────────────────────────────────────────────────────────────────

def _validate_anchors(lines):
    """Проверка целостности: ровно 35 строк, 7x5, ответы непустые, нет заглушек."""
    if len(lines) != 35:
        raise RuntimeError(f"anchors.jsonl: ожидалось 35 строк, получено {len(lines)}")
    from collections import Counter
    by_grade = Counter(l.get('grade', 0) for l in lines)
    for g in range(5, 12):
        if by_grade.get(g, 0) != 5:
            raise RuntimeError(f"anchors.jsonl: класс {g}: ожидалось 5, получено {by_grade.get(g,0)}")
    expected = {'algebra','geometry','combinatorics','logic','number_theory'}
    for l in lines:
        a = str(l.get('answer','')).strip()
        if not a:
            raise RuntimeError(f"anchors.jsonl:{l.get('_line_no','?')}: пустой answer")
        s = str(l.get('statement','')).strip()
        if s.lower().startswith('задача'):
            raise RuntimeError(f"anchors.jsonl:{l.get('_line_no','?')}: statement начинается с 'Задача'")
        if str(l.get('section','')).strip().lower() not in expected:
            raise RuntimeError(f"anchors.jsonl:{l.get('_line_no','?')}: неизвестный раздел")
    logger.info("anchors.jsonl integrity check PASSED: 35 anchors, 7x5")

def load_anchors(dry_run: bool = False) -> Dict[str, Any]:
    """Загрузить data/anchors.jsonl в AdaptiveTask с source='formyla_anchors'.

    Идемпотентно: если задача с таким anchor_uid уже есть в БД — пропускает.
    Возвращает статистику: сколько загружено, сколько пропущено, список
    строк с неоднозначным theme_id.

    Параметры
    ---------
    dry_run : bool
        Если True — только парсит и валидирует, не пишет в БД.
    """
    theme_map = get_theme_map()
    result: Dict[str, Any] = {
        'loaded': 0,
        'skipped': 0,
        'errors': [],
        'unmapped_themes': [],  # строки без однозначного theme_id
        'total_in_file': 0,
        'per_grade': {},
    }

    if not os.path.exists(ANCHORS_FILE):
        logger.warning("anchors.jsonl не найден: %s", ANCHORS_FILE)
        result['errors'].append(f"Файл не найден: {ANCHORS_FILE}")
        return result

    # Читаем все строки
    lines: List[Dict[str, Any]] = []
    with open(ANCHORS_FILE, 'r', encoding='utf-8') as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                data['_line_no'] = line_no
                lines.append(data)
            except json.JSONDecodeError as e:
                result['errors'].append(f"Строка {line_no}: JSON error: {e}")

    result['total_in_file'] = len(lines)

    # Проверка целостности
    _validate_anchors(lines)

    # Получаем существующие anchor_uid для идемпотентности
    existing_uids: set = set()
    try:
        existing = (
            AdaptiveTask.query
            .filter(AdaptiveTask.source == SOURCE_NAME)
            .with_entities(AdaptiveTask.source_id)
            .all()
        )
        existing_uids = {row[0] for row in existing if row[0]}
    except Exception as e:
        logger.warning("Не удалось получить existing_uids: %s", e)

    for data in lines:
        anchor_uid = str(data.get('anchor_uid', '')).strip()
        grade = int(data.get('grade', 0))
        section = str(data.get('section', '')).strip().lower()
        subtopic = str(data.get('subtopic', '')).strip()
        level = int(data.get('level', 1))
        statement = str(data.get('statement', '')).strip()
        answer = str(data.get('answer', '')).strip()
        line_no = data.get('_line_no', '?')

        # Валидация
        if not anchor_uid:
            result['errors'].append(f"Строка {line_no}: пустой anchor_uid")
            continue
        if grade < 5 or grade > 11:
            result['errors'].append(f"Строка {line_no}: некорректный grade={grade}")
            continue
        if not statement:
            result['errors'].append(f"Строка {line_no}: пустой statement")
            continue

        # Пропускаем уже существующие
        if anchor_uid in existing_uids:
            result['skipped'] += 1
            continue

        # Ищем theme_id по разделу и классу
        theme_id = _resolve_theme_id(grade, section, theme_map)
        if theme_id is None:
            result['unmapped_themes'].append(
                f"Строка {line_no}: anchor_uid={anchor_uid} grade={grade} "
                f"section={section} — нет однозначного theme_id"
            )

        if dry_run:
            result['loaded'] += 1
            result['per_grade'][str(grade)] = result['per_grade'].get(str(grade), 0) + 1
            continue

        # Сохраняем в БД
        try:
            task = AdaptiveTask(
                class_level=grade,
                difficulty_level=level,
                topic=section,
                subtopic=subtopic,
                task_text=statement,
                solution='',  # якоря без эталонного решения
                criteria_1_point='',
                criteria_2_points='',
                correct_answer=answer,
                source=SOURCE_NAME,
                source_id=anchor_uid,
                subject=section,
                theme_id=theme_id,
                task_type='anchor',
                origin='curated',
            )
            db.session.add(task)
            result['loaded'] += 1
            result['per_grade'][str(grade)] = result['per_grade'].get(str(grade), 0) + 1
        except Exception as e:
            result['errors'].append(f"Строка {line_no}: ошибка записи: {e}")
            logger.exception("Ошибка записи anchor_uid=%s", anchor_uid)

    if not dry_run:
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            result['errors'].append(f"Ошибка commit: {e}")
            logger.exception("Ошибка commit при загрузке anchors")

    return result


def _resolve_theme_id(grade: int, section: str, theme_map: Dict[str, str]) -> Optional[str]:
    """Найти theme_id для (grade, section) в справочнике.

    Возвращает theme_id (например 'G9_T05') если ровно один ключ
    G{grade}_T* соответствует данному section. Если несколько или
    ни одного — возвращает None.
    """
    prefix = f"G{grade}_"
    matches = []
    for key, sec in theme_map.items():
        if key.startswith(prefix) and sec == section:
            matches.append(key)
    if len(matches) == 1:
        return matches[0]
    return None


# ──────────────────────────────────────────────────────────────────────
# Подбор якорей для анкеты
# ──────────────────────────────────────────────────────────────────────

def pick_anchors(grade: int) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Подобрать якорные задачи для анкеты ученика заданного класса.

    Правила:
      - ТОЛЬКО класс ученика
      - ТОЛЬКО source='formyla_anchors'
      - Не больше одной задачи на раздел
      - Если задач меньше 5 — добираем разделы в порядке:
        algebra, number_theory, geometry, combinatorics, logic

    Returns
    -------
    (anchors, meta)
        anchors: список словарей с ключами anchor_uid, grade, section,
                 subtopic, level, statement, answer, theme_id, db_id
        meta: {total_available, sections_found, file_line_info}
    """
    available = (
        AdaptiveTask.query
        .filter(
            AdaptiveTask.class_level == grade,
            AdaptiveTask.source == SOURCE_NAME,
        )
        .all()
    )

    # Auto-load if nothing in DB yet (lazy init)
    if len(available) == 0:
        load_result = load_anchors(dry_run=False)
        logger.info(
            "pick_anchors: auto-loaded anchors: loaded=%s skipped=%s errors=%s",
            load_result.get('loaded', 0),
            load_result.get('skipped', 0),
            len(load_result.get('errors', [])),
        )
        # Re-query after load
        available = (
            AdaptiveTask.query
            .filter(
                AdaptiveTask.class_level == grade,
                AdaptiveTask.source == SOURCE_NAME,
            )
            .all()
        )

    meta: Dict[str, Any] = {
        'total_available': len(available),
        'sections_found': {},
        'file_line_info': [],
    }

    # Группируем по разделу
    by_section: Dict[str, List[AdaptiveTask]] = {}
    for task in available:
        sec = (task.subject or task.topic or '').strip().lower()
        if sec not in CANONICAL_SECTIONS_ORDER:
            # Пытаемся нормализовать
            sec = _normalize_section(sec)
        if sec not in CANONICAL_SECTIONS_ORDER:
            continue
        by_section.setdefault(sec, []).append(task)

    meta['sections_found'] = {sec: len(tasks) for sec, tasks in by_section.items()}

    # Берём по одной задаче из каждого раздела
    anchors: List[Dict[str, Any]] = []
    used_sections: set = set()

    for section in CANONICAL_SECTIONS_ORDER:
        tasks = by_section.get(section, [])
        if not tasks:
            continue
        # Берём первую (по anchor_uid для детерминизма)
        tasks.sort(key=lambda t: t.source_id or '')
        task = tasks[0]
        anchors.append(_task_to_anchor_dict(task))
        used_sections.add(section)
        meta['file_line_info'].append(
            f"anchor_uid={task.source_id} section={section} "
            f"grade={task.class_level} id={task.id}"
        )

    meta['anchor_count'] = len(anchors)
    return anchors, meta


def _task_to_anchor_dict(task: AdaptiveTask) -> Dict[str, Any]:
    """Конвертировать AdaptiveTask -> словарь якоря.

    Связь задачи с чертежом — по anchor_uid: A_G5_GEO -> A_G5_GEO.svg
    в static/figures/anchors/. Не требует поля в БД, не требует файла
    соответствия. Для будущих обычных задач зарезервировано поле
    figure_json (описание построения) в таблице задач.
    """
    import os as _os
    uid = task.source_id or ''
    anchors_dir = _os.path.join(
        _os.path.dirname(__file__), '..', 'static', 'figures', 'anchors'
    )
    svg_path = _os.path.join(anchors_dir, f'{uid}.svg')
    figure_url = None
    if _os.path.isfile(svg_path):
        figure_url = f'/static/figures/anchors/{uid}.svg'

    return {
        'anchor_uid': uid,
        'grade': task.class_level,
        'section': task.subject or task.topic or '',
        'subtopic': task.subtopic or '',
        'level': task.difficulty_level,
        'statement': task.task_text or '',
        'answer': task.correct_answer or '',
        'solution': task.solution or '',
        'theme_id': task.theme_id or '',
        'db_id': task.id,
        'figure_url': figure_url,
    }


def _normalize_section(raw: str) -> str:
    """Нормализовать название раздела в канонический slug."""
    s = raw.strip().lower()
    # Прямые совпадения
    if s in CANONICAL_SECTIONS_ORDER:
        return s
    # Русские названия
    ru_map = {
        'алгебра': 'algebra',
        'алгебра и анализ': 'algebra',
        'арифметика': 'algebra',
        'геометрия': 'geometry',
        'комбинаторика': 'combinatorics',
        'логика': 'logic',
        'логика и методы': 'logic',
        'логика и игры': 'logic',
        'теория чисел': 'number_theory',
        'текстовые задачи': 'algebra',
    }
    return ru_map.get(s, s)


# ──────────────────────────────────────────────────────────────────────
# Проверка ответа
# ──────────────────────────────────────────────────────────────────────

def normalize_answer(raw: str) -> str:
    """Нормализовать ответ для сравнения.

    Правила:
      - Убрать пробелы
      - Запятую -> точку
      - Регистр не учитывать (lowercase)
      - Убрать точки в конце (чтобы «нет.» == «нет»)
    """
    s = raw.strip()
    s = s.replace(',', '.')
    s = s.replace(' ', '')
    s = s.lower()
    s = s.rstrip('.')
    return s


def check_answer(user_answer: str, correct_answer: str) -> bool:
    """Проверить ответ ученика против эталонного.

    Использует нормализацию: пробелы убраны, запятая->точка,
    регистр не учитывается. «нет» допустимо.
    """
    user_norm = normalize_answer(user_answer)
    correct_norm = normalize_answer(correct_answer)
    return user_norm == correct_norm


# ──────────────────────────────────────────────────────────────────────
# Инспекция: сколько якорей сейчас в БД
# ──────────────────────────────────────────────────────────────────────

def inspect_anchors() -> Dict[str, Any]:
    """Вернуть сводку: сколько якорей, по каким классам/разделам."""
    tasks = (
        AdaptiveTask.query
        .filter(AdaptiveTask.source == SOURCE_NAME)
        .all()
    )

    by_grade: Dict[int, List[Dict[str, Any]]] = {}
    for t in tasks:
        g = t.class_level or 0
        by_grade.setdefault(g, []).append({
            'id': t.id,
            'anchor_uid': t.source_id,
            'section': t.subject or t.topic,
            'subtopic': t.subtopic,
            'level': t.difficulty_level,
            'theme_id': t.theme_id,
            'answer_preview': (t.correct_answer or '')[:50],
        })

    summary = {
        'total': len(tasks),
        'by_grade': {
            str(g): {'count': len(items), 'items': items}
            for g, items in sorted(by_grade.items())
        },
    }

    # Считаем разделы для каждого класса
    for g_str, data in summary['by_grade'].items():
        sections = set(item['section'] for item in data['items'] if item['section'])
        data['sections'] = sorted(sections)
        data['section_count'] = len(sections)

    return summary


# ──────────────────────────────────────────────────────────────────────
# Получить ID всех якорных задач (для фильтрации в других подсистемах)
# ──────────────────────────────────────────────────────────────────────

def get_anchor_ids() -> List[int]:
    """Вернуть список id всех задач с source='formyla_anchors'.

    Используется для быстрой фильтрации в daily_task_rotation и theme_probe.
    """
    try:
        rows = (
            AdaptiveTask.query
            .filter(AdaptiveTask.source == SOURCE_NAME)
            .with_entities(AdaptiveTask.id)
            .all()
        )
        return [r[0] for r in rows]
    except Exception:
        return []


def get_anchor_ids_set() -> set:
    """Вернуть множество id всех задач с source='formyla_anchors'."""
    return set(get_anchor_ids())
