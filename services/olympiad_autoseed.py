# -*- coding: utf-8 -*-
"""
Auto-seed олимпиадного раздела из JSON-фикстур при пустых таблицах.

Запускается на старте app.py:
  - Если `olympiad_theory` пуста — грузит data/olympiads/theory_65_methods.json.
  - Если `olympiad_probniks` пуст — грузит data/olympiads/vsosh_9_2027_probniks.json.
  - Если `olympiad_tasks` пуст — грузит data/olympiads/vsosh_9_2027_tasks.json.

Это решает проблему «на проде раздел методов/задач пустой», потому что
импортёр scripts/import_olympiad.py не запускался на Render.

Все ошибки ловятся и логируются, никогда не валят запуск приложения.
"""

from __future__ import annotations

import json
import os
from typing import Any, Iterable


DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'olympiads')

# Полный каталог 89 методов (с метаданными — секции, классы, частоты).
# Если файл доступен — используется в первую очередь; иначе берётся
# исторический theory_65_methods.json (полное описание у 65 методов).
THEORY_JSON_CATALOG_89 = os.path.join(DATA_DIR, 'methods_catalog_89.json')
THEORY_JSON_LEGACY_65 = os.path.join(DATA_DIR, 'theory_65_methods.json')
THEORY_JSON = THEORY_JSON_LEGACY_65  # обратная совместимость для тестов

PROBNIKS_JSON = os.path.join(DATA_DIR, 'vsosh_9_2027_probniks.json')
TASKS_JSON = os.path.join(DATA_DIR, 'vsosh_9_2027_tasks.json')


def _load_json(path: str) -> list:
    if not os.path.exists(path):
        return []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f) or []
    except Exception as e:
        print(f"[OLYMPIAD-SEED] Failed to read {path}: {e}")
        return []


def _safe_section(method_code: str) -> str | None:
    """Первая буква метода (A..H) определяет секцию каталога."""
    if not method_code:
        return None
    ch = method_code[0].upper()
    if ch in 'ABCDEFGH':
        return ch
    return None


def fix_theory_placeholders(app, db) -> None:
    """Targeted fix: replace placeholder method names «X (название ждёт текста)»
    with real names from data/olympiads/methods_catalog_89.json.

    Runs independently of OLYMPIAD_AUTOSEED (idempotent, safe to call on
    every boot). Only touches rows whose `method_name` literally contains
    the placeholder marker, so manually edited names are never overwritten.
    """
    placeholder = '(название ждёт текста)'
    try:
        from models_olympiad import TheoryBlock
    except Exception as e:
        print(f"[THEORY-FIX] models_olympiad not available: {e}")
        return

    try:
        with app.app_context():
            try:
                stub_q = TheoryBlock.query.filter(
                    TheoryBlock.method_name.like(f'%{placeholder}%')
                )
                stub_count = stub_q.count()
            except Exception as e:
                print(f"[THEORY-FIX] Cannot query stubs: {e}")
                return

            if stub_count == 0:
                print("[THEORY-FIX] No placeholder method names — nothing to do")
                return

            rows = _load_json(THEORY_JSON_CATALOG_89)
            if not rows:
                print(f"[THEORY-FIX] Source JSON missing: {THEORY_JSON_CATALOG_89}")
                return

            by_code = {
                str(r.get('method_code')): r for r in rows
                if r.get('method_code') and r.get('method_name')
            }

            fixed = 0
            for tb in stub_q.all():
                src = by_code.get(tb.method_code)
                if not src:
                    continue
                new_name = src.get('method_name')
                if not new_name or placeholder in new_name:
                    continue
                tb.method_name = new_name
                # Заодно дозальём метаданные, если они пустые — это безопасно.
                if not tb.section:
                    tb.section = src.get('section') or _safe_section(tb.method_code)
                if (not tb.grades) and src.get('grades'):
                    tb.grades = src['grades']
                if (not tb.recommended_competitions) and src.get('recommended_competitions'):
                    tb.recommended_competitions = src['recommended_competitions']
                if tb.difficulty_level is None and src.get('difficulty_level') is not None:
                    tb.difficulty_level = src['difficulty_level']
                if tb.frequency_vsosh_9 is None and src.get('frequency_vsosh_9') is not None:
                    tb.frequency_vsosh_9 = src['frequency_vsosh_9']
                fixed += 1

            try:
                db.session.commit()
                print(f"[THEORY-FIX] Renamed {fixed}/{stub_count} placeholder methods")
            except Exception as e:
                db.session.rollback()
                print(f"[THEORY-FIX] Commit failed: {e}")
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        print(f"[THEORY-FIX] Top-level error: {e}")


def seed_theory_only(app, db) -> None:
    """Idempotent: засевает ТОЛЬКО таблицу olympiad_theory из
    methods_catalog_89.json (или legacy 65). Используется на каждом старте
    БЕЗ env-гейта, чтобы прод-каталог методов не оставался пустым после
    деплоя. Не трогает Probnik/OlympiadTask (для них autoseed остаётся
    под флагом OLYMPIAD_AUTOSEED=1).
    """
    try:
        from models_olympiad import TheoryBlock
    except Exception as e:
        print(f"[THEORY-SEED] models_olympiad not available: {e}")
        return
    try:
        with app.app_context():
            _seed_theory(db, TheoryBlock)
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        print(f"[THEORY-SEED] Top-level error: {e}")


def autoseed_olympiad(app, db) -> None:
    """Главная точка входа. Вызывается из app.py внутри app_context().

    Args:
        app: Flask application (для логирования).
        db:  SQLAlchemy() из models.
    """
    try:
        from models_olympiad import (
            Probnik,
            OlympiadTask,
            TheoryBlock,
        )
    except Exception as e:
        print(f"[OLYMPIAD-SEED] Models not available: {e}")
        return

    try:
        with app.app_context():
            _seed_theory(db, TheoryBlock)
            code_to_probnik = _seed_probniks(db, Probnik)
            _seed_tasks(db, OlympiadTask, Probnik, code_to_probnik)
    except Exception as e:
        # Никогда не должны падать здесь — это not-critical-path.
        try:
            db.session.rollback()
        except Exception:
            pass
        print(f"[OLYMPIAD-SEED] Top-level error: {e}")


# ─── Theory ─────────────────────────────────────────────────────────────────

def _seed_theory(db, TheoryBlock) -> None:
    try:
        existing = TheoryBlock.query.count()
    except Exception as e:
        print(f"[OLYMPIAD-SEED] Cannot query TheoryBlock: {e}")
        return

    # Берём максимально полный каталог: сначала 89-методов, потом fallback на legacy.
    rows = _load_json(THEORY_JSON_CATALOG_89)
    src_path = THEORY_JSON_CATALOG_89
    if not rows:
        rows = _load_json(THEORY_JSON_LEGACY_65)
        src_path = THEORY_JSON_LEGACY_65
    if not rows:
        print(f"[OLYMPIAD-SEED] No theory data found ({THEORY_JSON_CATALOG_89} / {THEORY_JSON_LEGACY_65}) — skipping theory seed")
        return

    # Если в БД уже есть строки и их не меньше, чем в фикстуре,
    # и при этом НИ ОДНА из них не выглядит как skeleton-заглушка
    # «E14 (название ждёт текста)» — пропускаем (ничего ломать не будем).
    # Если же заглушки есть — всё равно идём в upsert-цикл, чтобы их
    # перезаписать настоящими именами из JSON.
    _placeholder = '(название ждёт текста)'
    try:
        stub_count = TheoryBlock.query.filter(
            TheoryBlock.method_name.like(f'%{_placeholder}%')
        ).count()
    except Exception:
        stub_count = 0

    if existing >= len(rows) and stub_count == 0:
        print(f"[OLYMPIAD-SEED] TheoryBlock: {existing} rows (>= {len(rows)} in fixture, no stubs) — skipping seed")
        return

    if stub_count:
        print(f"[OLYMPIAD-SEED] TheoryBlock: found {stub_count} placeholder names — running upsert to fix")
    print(f"[OLYMPIAD-SEED] Theory source: {src_path} ({len(rows)} rows; in DB: {existing} → topping up)")

    created = 0
    updated = 0
    for item in rows:
        try:
            code = item.get('method_code')
            if not code:
                continue
            tb = TheoryBlock.query.filter_by(method_code=code).first()
            if tb is None:
                tb = TheoryBlock(
                    method_code=code,
                    method_name=item.get('method_name') or code,
                    section=item.get('section') or _safe_section(code),
                    definition_md=item.get('definition_md'),
                    main_theorems_md=item.get('main_theorems_md'),
                    typical_techniques_md=item.get('typical_techniques_md'),
                    triggers_md=item.get('triggers_md'),
                    worked_example_md=item.get('worked_example_md'),
                    pitfalls_md=item.get('pitfalls_md'),
                    related_methods=item.get('related_methods') or [],
                    grades=item.get('grades'),
                    recommended_competitions=item.get('recommended_competitions'),
                    difficulty_level=item.get('difficulty_level'),
                    frequency_vsosh_9=item.get('frequency_vsosh_9'),
                    sort_order=item.get('sort_order', 0) or 0,
                )
                db.session.add(tb)
                created += 1
            else:
                # upsert: только заполняем пустые поля, чтобы не затирать
                # редактируемое. Исключение: явные skeleton-плейсхолдеры
                # вида «E14 (название ждёт текста)» считаются пустыми и
                # принудительно перезаписываются настоящим именем из JSON.
                changed = False
                _placeholder = '(название ждёт текста)'
                _name_is_stub = (
                    (not tb.method_name)
                    or (_placeholder in (tb.method_name or ''))
                )
                if _name_is_stub and item.get('method_name'):
                    tb.method_name = item['method_name']; changed = True
                if not tb.section:
                    tb.section = item.get('section') or _safe_section(code); changed = True
                for fld in ('definition_md', 'main_theorems_md', 'typical_techniques_md',
                            'triggers_md', 'worked_example_md', 'pitfalls_md'):
                    if not getattr(tb, fld, None) and item.get(fld):
                        setattr(tb, fld, item[fld]); changed = True
                if (not tb.grades) and item.get('grades'):
                    tb.grades = item['grades']; changed = True
                if (not tb.recommended_competitions) and item.get('recommended_competitions'):
                    tb.recommended_competitions = item['recommended_competitions']; changed = True
                if tb.difficulty_level is None and item.get('difficulty_level') is not None:
                    tb.difficulty_level = item['difficulty_level']; changed = True
                if tb.frequency_vsosh_9 is None and item.get('frequency_vsosh_9') is not None:
                    tb.frequency_vsosh_9 = item['frequency_vsosh_9']; changed = True
                if changed:
                    updated += 1
        except Exception as e:
            print(f"[OLYMPIAD-SEED] Theory row failed ({item.get('method_code', '?')}): {e}")

    try:
        db.session.commit()
        print(f"[OLYMPIAD-SEED] TheoryBlock: created {created} rows, updated {updated} rows")
    except Exception as e:
        db.session.rollback()
        print(f"[OLYMPIAD-SEED] Theory commit failed: {e}")


# ─── Probniks ────────────────────────────────────────────────────────────────

def _seed_probniks(db, Probnik) -> dict:
    """Возвращает {code: probnik_id} для последующей привязки задач."""
    try:
        existing = Probnik.query.count()
    except Exception as e:
        print(f"[OLYMPIAD-SEED] Cannot query Probnik: {e}")
        return {}

    if existing > 0:
        rows = Probnik.query.all()
        print(f"[OLYMPIAD-SEED] Probnik: {existing} rows — skipping seed")
        return {p.code: p.id for p in rows}

    items = _load_json(PROBNIKS_JSON)
    if not items:
        print(f"[OLYMPIAD-SEED] No data in {PROBNIKS_JSON} — skipping probniks seed")
        return {}

    created = 0
    code_to_id: dict = {}
    for item in items:
        try:
            code = item.get('code')
            if not code:
                continue
            p = Probnik(
                code=code,
                type=item.get('type', 'topic'),
                number=item.get('number', 0) or 0,
                title=item.get('title') or code,
                description=item.get('description'),
                competition=item.get('competition', 'ВсОШ'),
                grade=item.get('grade', 9) or 9,
                season_year=item.get('season_year', 2027) or 2027,
                duration_minutes=item.get('duration_minutes'),
                max_score=item.get('max_score'),
                threshold_prize=item.get('threshold_prize'),
                threshold_winner=item.get('threshold_winner'),
                sort_order=item.get('sort_order', 0) or 0,
                is_published=bool(item.get('is_published', True)),
            )
            db.session.add(p)
            db.session.flush()
            code_to_id[code] = p.id
            created += 1
        except Exception as e:
            print(f"[OLYMPIAD-SEED] Probnik row failed ({item.get('code', '?')}): {e}")

    try:
        db.session.commit()
        print(f"[OLYMPIAD-SEED] Probnik: created {created} rows")
    except Exception as e:
        db.session.rollback()
        print(f"[OLYMPIAD-SEED] Probnik commit failed: {e}")
        return {}

    return code_to_id


# ─── Tasks ───────────────────────────────────────────────────────────────────

def _seed_tasks(db, OlympiadTask, Probnik, code_to_id: dict) -> None:
    try:
        existing = OlympiadTask.query.count()
    except Exception as e:
        print(f"[OLYMPIAD-SEED] Cannot query OlympiadTask: {e}")
        return

    if existing > 0:
        print(f"[OLYMPIAD-SEED] OlympiadTask: {existing} rows — skipping seed")
        return

    items = _load_json(TASKS_JSON)
    if not items:
        print(f"[OLYMPIAD-SEED] No data in {TASKS_JSON} — skipping tasks seed")
        return

    # Если probnik'и существовали, но мы не получили карту code→id — построим её.
    if not code_to_id:
        try:
            for p in Probnik.query.all():
                code_to_id[p.code] = p.id
        except Exception as e:
            print(f"[OLYMPIAD-SEED] Cannot rebuild probnik map: {e}")
            return

    created = 0
    skipped = 0
    for item in items:
        try:
            probnik_code = item.get('probnik_code')
            probnik_id = code_to_id.get(probnik_code)
            if not probnik_id:
                skipped += 1
                continue
            t = OlympiadTask(
                probnik_id=probnik_id,
                number=str(item.get('number', '')),
                sort_order=item.get('sort_order', 0) or 0,
                difficulty=item.get('difficulty'),
                method_primary=item.get('method_primary') or 'A1',
                method_secondary=item.get('method_secondary'),
                condition_md=item.get('condition_md') or '',
                idea_md=item.get('idea_md') or '',
                solution_md=item.get('solution_md') or '',
                answer=item.get('answer'),
                source_prototype=item.get('source_prototype'),
                estimated_minutes=item.get('estimated_minutes'),
                max_score=item.get('max_score', 7) or 7,
            )
            db.session.add(t)
            created += 1
        except Exception as e:
            print(f"[OLYMPIAD-SEED] Task row failed ({item.get('number', '?')}): {e}")

    try:
        db.session.commit()
        print(f"[OLYMPIAD-SEED] OlympiadTask: created {created} rows, skipped {skipped}")
    except Exception as e:
        db.session.rollback()
        print(f"[OLYMPIAD-SEED] Task commit failed: {e}")
