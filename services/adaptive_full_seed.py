# -*- coding: utf-8 -*-
"""
Production-сидер банка адаптивного теста (9120 задач).

Запускается на старте Flask-приложения в Render (или локально), если
установлена переменная окружения ADAPTIVE_FORCE_IMPORT=1.

Источник:
  data/adaptive/adaptive_full_9120.json  (формат — см. ниже)

Формат записи JSON (как в adaptive_export_2026-06-04_completed (3).json):
  {
    "id": int,
    "subject": "algebra|number_theory|geometry|combinatorics|logic",
    "grade":   5..11,
    "level":   1..8,
    "statement": str,
    "answer":    str,
    "solution":  str
  }

Идемпотентность:
  - Если в БД уже 9000+ задач из этого источника (определяется по
    AdaptiveTask.source == 'calibrated_2026_06_04'), сидер пропускает работу.
  - Иначе делает: TRUNCATE adaptive_tasks → bulk INSERT 9120 строк.
  - Бэкап старых данных в backups/ НЕ делается (это прод; на Render бэкап
    через скачивание Postgres-дампа).

ВНИМАНИЕ: Подсказки по выбору темы из реестра services/adaptive_topics_registry
завязаны на ТОЧНУЮ строку AdaptiveTask.topic. Маппинг (subject, grade) →
canonical topic ниже синхронизирован с registry. Изменения в registry должны
сопровождаться правкой TOPIC_MAP.
"""
from __future__ import annotations

import json
import os
from datetime import datetime

# Маппинг (subject, grade) -> AdaptiveTask.topic.
# СИНХРОНИЗИРОВАНО С services/adaptive_topics_registry.py
TOPIC_MAP = {
    # ── 5 класс ────────────────────────────────────────────────────────
    ("algebra",        5): "Алгебра",
    ("number_theory",  5): "Теория чисел",
    ("geometry",       5): "Геометрия",
    ("combinatorics",  5): "Комбинаторика",
    ("logic",          5): "Логика",
    # ── 6 класс ────────────────────────────────────────────────────────
    ("algebra",        6): "Алгебра",
    ("number_theory",  6): "Теория чисел",
    ("geometry",       6): "Геометрия",
    ("combinatorics",  6): "Комбинаторика",
    ("logic",          6): "Логика",
    # ── 7 класс ────────────────────────────────────────────────────────
    ("algebra",        7): "Алгебра. Выражения, степени, многочлены",
    ("number_theory",  7): "Теория чисел. Делимость и остатки",
    ("geometry",       7): "Геометрия. Геометрия треугольников и углов",
    ("combinatorics",  7): "Комбинаторика. Комбинаторика и графы",
    ("logic",          7): "Логика. Логика и инварианты",
    # ── 8 класс ────────────────────────────────────────────────────────
    ("algebra",        8): "Алгебра. Квадратные уравнения и теорема Виета",
    ("number_theory",  8): "Теория чисел. Теория чисел: остатки и диофантовы",
    ("geometry",       8): "Геометрия. Геометрия: подобие и окружность",
    ("combinatorics",  8): "Комбинаторика. Комбинаторика, логика, инварианты",
    ("logic",          8): "Логика. Логика и инварианты",
    # ── 9 класс ────────────────────────────────────────────────────────
    ("algebra",        9): "Алгебра. Квадратные уравнения, Виет, параметры",
    ("number_theory",  9): "Теория чисел. Теория чисел",
    ("geometry",       9): "Геометрия. Геометрия треугольника и окружности",
    ("combinatorics",  9): "Комбинаторика. Комбинаторика и графы",
    ("logic",          9): "Логика. Логика, инварианты, стратегии",
    # ── 10 класс ───────────────────────────────────────────────────────
    ("algebra",       10): "Алгебра. Системы, параметры и неравенства",
    ("number_theory", 10): "Теория чисел. Теория чисел старшего уровня",
    ("geometry",      10): "Геометрия. Стереометрия и векторы",
    ("combinatorics", 10): "Комбинаторика. Комбинаторика, графы, вероятностный подсчёт",
    ("logic",         10): "Логика. Логика, множества, функции и отображения",
    # ── 11 класс ───────────────────────────────────────────────────────
    ("algebra",       11): "Алгебра. Функции, графики и параметры",
    ("number_theory", 11): "Теория чисел. Теория чисел и диофантовы задачи",
    ("geometry",      11): "Геометрия. Стереометрия, координаты и векторы",
    ("combinatorics", 11): "Комбинаторика. Комбинаторика, графы, логика",
    ("logic",         11): "Логика. Логика, множества, функции и отображения",
}

SOURCE_TAG = "calibrated_2026_06_04"
DEFAULT_PATH = os.path.join("data", "adaptive", "adaptive_full_9120.json")


def run_adaptive_full_seed(app, db):
    """Главная точка входа: импортирует 9120 задач адаптивного теста.

    Возвращает dict со статистикой или с error.
    """
    print("[ADAPTIVE-FULL-SEED] start")

    src_path = os.environ.get("ADAPTIVE_FORCE_IMPORT_PATH", DEFAULT_PATH)
    if not os.path.isfile(src_path):
        print(f"[ADAPTIVE-FULL-SEED] source not found: {src_path}")
        return {"ok": False, "error": f"source not found: {src_path}"}

    try:
        with open(src_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[ADAPTIVE-FULL-SEED] failed to read source: {e}")
        return {"ok": False, "error": f"read failed: {e}"}

    if not isinstance(data, list):
        print("[ADAPTIVE-FULL-SEED] bad source format: expected list")
        return {"ok": False, "error": "bad source format"}

    print(f"[ADAPTIVE-FULL-SEED] source has {len(data)} tasks")

    with app.app_context():
        from models import AdaptiveTask

        # ── Idempotency check ───────────────────────────────────────────
        # Если уже импортировано из этого источника достаточное количество —
        # пропускаем. Это позволяет безопасно держать ADAPTIVE_FORCE_IMPORT=1
        # включённым на продакшне без перетирания на каждом рестарте.
        existing = AdaptiveTask.query.filter(
            AdaptiveTask.source == SOURCE_TAG
        ).count()
        if existing >= 9000:
            print(f"[ADAPTIVE-FULL-SEED] already seeded ({existing} rows), skipping")
            return {"ok": True, "skipped": True, "existing": existing}

        # ── Подготавливаем строки ──────────────────────────────────────
        prepared = []
        skipped = 0
        for entry in data:
            subj = entry.get("subject")
            try:
                grade = int(entry.get("grade", 0))
                level = int(entry.get("level", 0))
            except (TypeError, ValueError):
                skipped += 1
                continue
            if grade not in range(5, 12) or level not in range(1, 9):
                skipped += 1
                continue

            topic = TOPIC_MAP.get((subj, grade))
            if not topic:
                skipped += 1
                continue

            statement = (entry.get("statement") or "").strip()
            answer = (entry.get("answer") or "").strip()
            solution = (entry.get("solution") or "").strip()
            if not statement or not answer or not solution:
                skipped += 1
                continue

            prepared.append({
                "class_level":       grade,
                "difficulty_level":  level,
                "topic":             topic,
                "subtopic":          None,
                "task_text":         statement,
                "solution":          solution,
                "criteria_1_point":  "Частичное решение",
                "criteria_2_points": "Полное верное решение с обоснованием",
                "correct_answer":    answer,
                "subject":           subj,
                "source_id":         f"adaptive_export_2026-06-04#{entry.get('id')}",
                "task_type":         "adaptive",
                "source":            SOURCE_TAG,
                "is_flagged":        False,
                "needs_review":      False,
                "created_at":        datetime.utcnow(),
            })

        print(f"[ADAPTIVE-FULL-SEED] prepared {len(prepared)} (skipped {skipped})")
        if len(prepared) < 9000:
            print("[ADAPTIVE-FULL-SEED] too few prepared rows — aborting")
            return {"ok": False, "error": f"too few prepared ({len(prepared)})"}

        # ── Очистка таблицы + bulk insert ──────────────────────────────
        try:
            deleted = AdaptiveTask.query.delete(synchronize_session=False)
            db.session.commit()
            print(f"[ADAPTIVE-FULL-SEED] deleted {deleted} old rows")
        except Exception as e:
            db.session.rollback()
            print(f"[ADAPTIVE-FULL-SEED] DELETE failed: {e}")
            return {"ok": False, "error": f"delete failed: {e}"}

        try:
            from sqlalchemy import insert
            chunk = 500
            total = 0
            for i in range(0, len(prepared), chunk):
                piece = prepared[i:i + chunk]
                db.session.execute(insert(AdaptiveTask.__table__), piece)
                db.session.commit()
                total += len(piece)
            print(f"[ADAPTIVE-FULL-SEED] inserted {total} rows")
        except Exception as e:
            db.session.rollback()
            print(f"[ADAPTIVE-FULL-SEED] INSERT failed: {e}")
            return {"ok": False, "error": f"insert failed: {e}"}

        # ── Финальная проверка ─────────────────────────────────────────
        final_count = AdaptiveTask.query.count()
        print(f"[ADAPTIVE-FULL-SEED] FINAL: {final_count} rows in adaptive_tasks")
        return {"ok": True, "inserted": total, "final": final_count}
