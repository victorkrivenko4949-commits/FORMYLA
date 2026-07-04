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

# Полный каталог 102 методов (последняя версия — с метаданными И с полными
# текстами definition_md/main_theorems_md/etc). Используется в первую очередь.
# Fallback: каталог 89 методов → исторический theory_65_methods.json.
THEORY_JSON_CATALOG_102 = os.path.join(DATA_DIR, 'methods_catalog_105.json')
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


# Дополнительные источники полного содержимого методов: эти JSON-файлы
# содержат definition_md / main_theorems_md / worked_example_md / ... ,
# тогда как methods_catalog_89.json — только метаданные (название, классы,
# частоты). Сидер сливает оба источника, чтобы у каждого из 89 методов
# было как тело конспекта, так и атрибуты.
THEORY_BODY_SOURCES = (
    os.path.join(DATA_DIR, 'theory_65_methods.json'),
    os.path.join(DATA_DIR, 'theory_24_methods.json'),
)

_BODY_FIELDS = (
    'definition_md',
    'main_theorems_md',
    'typical_techniques_md',
    'triggers_md',
    'worked_example_md',
    'pitfalls_md',
)


def _fill_theory_bodies(db, TheoryBlock) -> None:
    """Дозаливаем пустые `*_md` поля методов из theory_65 / theory_24 JSON.

    Не трогает поля, у которых УЖЕ есть содержимое (idempotent, safe для
    ручных правок). Считает {created/updated} только когда реально что-то
    меняется.
    """
    all_rows = []
    for path in THEORY_BODY_SOURCES:
        rows = _load_json(path)
        if rows:
            print(f"[THEORY-SEED] body source: {path} ({len(rows)} rows)")
            all_rows.extend(rows)
    if not all_rows:
        print("[THEORY-SEED] No body sources found — skipping body fill")
        return

    by_code: dict = {}
    for item in all_rows:
        code = item.get('method_code')
        if code:
            # Если код встретился в нескольких файлах — выигрывает первый
            # непустой definition_md / main_theorems_md.
            existing = by_code.get(code)
            if not existing:
                by_code[code] = item
            else:
                # Дозаливаем пустые поля из последующих источников.
                for fld in _BODY_FIELDS + ('related_methods',):
                    if not existing.get(fld) and item.get(fld):
                        existing[fld] = item[fld]

    updated = 0
    for code, src in by_code.items():
        try:
            tb = TheoryBlock.query.filter_by(method_code=code).first()
            if tb is None:
                continue  # Сидер каталога должен был создать строку.
            changed = False
            for fld in _BODY_FIELDS:
                cur = getattr(tb, fld, None)
                cur_stripped = str(cur).strip() if cur else ''
                src_val = src.get(fld)
                # Overwrite if:
                #   - field is empty/null, OR
                #   - field has stubby content (< 300 chars, likely placeholder)
                #   - AND source has richer content
                if src_val and (
                    not cur_stripped
                    or len(cur_stripped) < 300
                ):
                    setattr(tb, fld, src_val)
                    changed = True
            if (not tb.related_methods) and src.get('related_methods'):
                tb.related_methods = src['related_methods']
                changed = True
            if changed:
                updated += 1
        except Exception as e:
            print(f"[THEORY-SEED] body fill row failed ({code}): {e}")

    try:
        db.session.commit()
        print(f"[THEORY-SEED] Theory bodies filled: {updated} methods updated")
    except Exception as e:
        db.session.rollback()
        print(f"[THEORY-SEED] body commit failed: {e}")


def seed_theory_only(app, db) -> None:
    """Idempotent: засевает ТОЛЬКО таблицу olympiad_theory.

    Шаг 1 (`_seed_theory`): метаданные из `methods_catalog_89.json`
        (название, секция, классы, частоты, sort_order).
    Шаг 2 (`_fill_theory_bodies`): полные тексты `*_md` из
        `theory_65_methods.json` + `theory_24_methods.json` (89 методов
        в сумме — оба файла дополняют друг друга).
    Шаг 3 (`_seed_probnik_theory`): привязка тематических Probnik'ов
        к TheoryBlock'ам через method_code из задач (olympiad_probnik_theory).

    Запускается на каждом старте БЕЗ env-гейта. Не трогает
    Probnik/OlympiadTask (для них autoseed остаётся под флагом
    OLYMPIAD_AUTOSEED=1). Идемпотентна: повторные запуски ничего
    не меняют, кроме случаев, когда были пустые поля.
    """
    try:
        from models_olympiad import (
            TheoryBlock,
            Probnik,
            ProbnikTheory,
        )
    except Exception as e:
        print(f"[THEORY-SEED] models_olympiad not available: {e}")
        return
    try:
        with app.app_context():
            _seed_theory(db, TheoryBlock)
            _fill_theory_bodies(db, TheoryBlock)
            # Rich MD-конспекты для 13 методов (E14, F1, F8, B1, F3, F2,
            # D12, D1, C5a, F4a, E5, A2, E10) — там по ~7 семейств и
            # ~10 разобранных примеров на метод (раньше отображалось
            # «мало», потому что seed брал лишь короткие версии из
            # theory_65/theory_24 JSON).
            try:
                from services.olympiad_md_import import import_rich_md_into_theory
                import_rich_md_into_theory(db, TheoryBlock)
            except Exception as _e_md:
                print(f"[THEORY-MD] hook skipped: {_e_md}")
            # Привязываем theory-блоки к probnik'ам через method_code из задач.
            _seed_probnik_theory(db, TheoryBlock, Probnik, ProbnikTheory)
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
            ProbnikTheory,
        )
    except Exception as e:
        print(f"[OLYMPIAD-SEED] Models not available: {e}")
        return

    try:
        with app.app_context():
            _seed_theory(db, TheoryBlock)
            code_to_probnik = _seed_probniks(db, Probnik)
            _seed_tasks(db, OlympiadTask, Probnik, code_to_probnik)
            # Привязываем theory-блоки к probnik'ам через method_code из задач.
            _seed_probnik_theory(db, TheoryBlock, Probnik, ProbnikTheory)
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

    # Берём максимально полный каталог: сначала 102 (последняя версия,
    # с полными текстами), затем 89-методов, затем fallback на legacy.
    rows = _load_json(THEORY_JSON_CATALOG_102)
    src_path = THEORY_JSON_CATALOG_102
    if not rows:
        rows = _load_json(THEORY_JSON_CATALOG_89)
        src_path = THEORY_JSON_CATALOG_89
    if not rows:
        rows = _load_json(THEORY_JSON_LEGACY_65)
        src_path = THEORY_JSON_LEGACY_65
    if not rows:
        print(f"[OLYMPIAD-SEED] No theory data found ({THEORY_JSON_CATALOG_89} / {THEORY_JSON_LEGACY_65}) — skipping theory seed")
        return

    # Всегда проходим по всем строкам из JSON-фикстуры, чтобы:
    #   1) Создать недостающие строки (когда JSON пополнился новыми методами).
    #   2) Обновить плейсхолдер-имена настоящими.
    #   3) Дозаполнить пустые метаполя.
    # Итерация идемпотентна: существующие строки находятся по method_code
    # и не пересоздаются; только пустые поля заполняются.
    _placeholder = '(название ждёт текста)'
    try:
        stub_count = TheoryBlock.query.filter(
            TheoryBlock.method_name.like(f'%{_placeholder}%')
        ).count()
    except Exception:
        stub_count = 0

    if stub_count:
        print(f"[OLYMPIAD-SEED] TheoryBlock: found {stub_count} placeholder names — running upsert to fix")
    print(f"[OLYMPIAD-SEED] Theory source: {src_path} ({len(rows)} rows; in DB: {existing} — ensuring all present)")

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


# ─── Probnik ↔ Theory links ──────────────────────────────────────────────────

def _seed_probnik_theory(db, TheoryBlock, Probnik, ProbnikTheory) -> None:
    """Привязывает TheoryBlock'и к Probnik'ам через method_code из задач.

    В tasks JSON каждый элемент имеет probnik_code и method_primary/method_secondary.
    Функция собирает уникальные method_code для каждого probnik'а, находит
    соответствующие TheoryBlock.id по method_code и создаёт ProbnikTheory-записи.

    Идемпотентна: если (probnik_id, theory_block_id) уже существует — пропускает.
    """
    items = _load_json(TASKS_JSON)
    if not items:
        print(f"[PROBNIK-THEORY] No data in {TASKS_JSON} — skipping probnik-theory seed")
        return

    # Шаг 1: собрать уникальные method_code для каждого probnik_code.
    probnik_methods: dict[str, set[str]] = {}
    for item in items:
        pcode = item.get('probnik_code')
        if not pcode:
            continue
        if pcode not in probnik_methods:
            probnik_methods[pcode] = set()
        mp = item.get('method_primary')
        if mp:
            probnik_methods[pcode].add(mp)
        ms = item.get('method_secondary')
        if ms:
            probnik_methods[pcode].add(ms)

    if not probnik_methods:
        print("[PROBNIK-THEORY] No probnik-method mappings found in tasks — nothing to seed")
        return

    # Шаг 2: построить карту method_code → TheoryBlock.id (одним запросом).
    all_codes = sorted({c for codes in probnik_methods.values() for c in codes})
    theory_rows = TheoryBlock.query.filter(
        TheoryBlock.method_code.in_(all_codes)
    ).all()
    code_to_theory_id: dict[str, int] = {
        t.method_code: t.id for t in theory_rows
    }

    # Шаг 3: построить карту probnik_code → Probnik.id.
    all_probnik_codes = list(probnik_methods.keys())
    probnik_rows = Probnik.query.filter(
        Probnik.code.in_(all_probnik_codes)
    ).all()
    code_to_probnik_id: dict[str, int] = {
        p.code: p.id for p in probnik_rows
    }

    # Шаг 4: создать ProbnikTheory-записи (idempotent — пропускаем существующие).
    created = 0
    skipped = 0
    for probnik_code, method_codes in probnik_methods.items():
        probnik_id = code_to_probnik_id.get(probnik_code)
        if probnik_id is None:
            print(f"[PROBNIK-THEORY] Probnik {probnik_code!r} not found in DB — skipping")
            skipped += len(method_codes)
            continue

        # Выясняем, какие theory_block_id уже привязаны к этому probnik'у.
        existing_ids = {
            pt.theory_block_id
            for pt in ProbnikTheory.query.filter_by(probnik_id=probnik_id).all()
        }

        sorted_codes = sorted(method_codes)
        for display_order, mcode in enumerate(sorted_codes, start=1):
            theory_id = code_to_theory_id.get(mcode)
            if theory_id is None:
                print(f"[PROBNIK-THEORY] TheoryBlock {mcode!r} not found in DB — skipping for probnik {probnik_code!r}")
                skipped += 1
                continue
            if theory_id in existing_ids:
                skipped += 1
                continue
            try:
                link = ProbnikTheory(
                    probnik_id=probnik_id,
                    theory_block_id=theory_id,
                    display_order=display_order,
                )
                db.session.add(link)
                created += 1
            except Exception as e:
                print(f"[PROBNIK-THEORY] Failed to create link (probnik={probnik_code}, method={mcode}): {e}")
                skipped += 1

    try:
        db.session.commit()
        print(f"[PROBNIK-THEORY] Created {created} probnik-theory links (skipped {skipped})")
    except Exception as e:
        db.session.rollback()
        print(f"[PROBNIK-THEORY] Commit failed: {e}")


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
