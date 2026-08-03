#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Импортёр FORMYLA_L1_L5_TOP5.jsonl -> AdaptiveTask.

Режим по умолчанию — dry-run: только валидация и отчёт, без записи в БД.
Запись только по флагу --apply.

Идемпотентность: по полю source_id = task_uid.
Дополнительная дедупликация по task_text.
"""

import argparse
import json
import os
import sys
import traceback
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

# ── level_name -> каноническое значение ──────────────────────────────────────
LEVEL_NAME_CANON = {
    1: "school_math",
    2: "school_vsosh",
    3: "municipal_vsosh",
    4: "regional_vsosh",
    5: "final_vsosh",
}

SOURCE_VALUE = "formyla_L1_L5_TOP5"
TASK_TYPE_VALUE = "olympiad"

# ── вспомогательные ─────────────────────────────────────────────────────────

def flatten_methods(methods_list):
    """Привести methods[] к нижнему регистру, убрать двойные пробелы, дедуплицировать."""
    if not methods_list:
        return []
    seen = set()
    result = []
    for m in methods_list:
        if not isinstance(m, str):
            continue
        cleaned = " ".join(m.lower().split())
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
    return result


def read_jsonl(filepath):
    """Прочитать JSONL файл, вернуть (list_of_rows, parse_errors)."""
    rows = []
    errors = []
    with open(filepath, "r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                rows.append(obj)
            except json.JSONDecodeError as e:
                errors.append((lineno, str(e)))
    return rows, errors


# ── класс импортёра ─────────────────────────────────────────────────────────

class FormylaImporter:
    def __init__(self, filepath, apply=False, batch_size=50, flagged=False):
        self.filepath = filepath
        self.apply = apply
        self.batch_size = batch_size
        self.flagged = flagged

        # статистика
        self.total_read = 0
        self.parse_errors = []
        self.duplicate_uids = []
        self.level_errors = []
        self.empty_statement = []
        self.empty_answer = []
        self.geo_no_diagram = 0
        self.text_duplicates = 0
        self.validation_errors = []
        self.write_errors = []
        self.created = 0
        self.updated = 0
        self.skipped = 0
        self.flagged_count = 0

        # анализ
        self.section_counter = Counter()
        self.grade_level_counter = Counter()
        self.grade_theme_level_counter = Counter()
        self.all_methods = Counter()
        self.all_tags = Counter()
        self.origin_counter = Counter()
        self.methods_json_null = 0

        # схема
        self.schema_ok = False
        self.field_mapping = []
        self.schema_blockers = []

    def check_schema(self):
        """Проверить пригодность модели AdaptiveTask."""
        from models import AdaptiveTask

        # Проверяем, есть ли source_id (поле для task_uid)
        try:
            col = getattr(AdaptiveTask, "source_id", None)
            if col is None:
                self.schema_blockers.append(
                    "SCHEMA BLOCKER: нет поля source_id в AdaptiveTask, "
                    "идемпотентный импорт невозможен"
                )
                return False
        except Exception:
            self.schema_blockers.append(
                "SCHEMA BLOCKER: не удалось проверить поле source_id"
            )
            return False

        # Строим маппинг
        jsonl_fields = [
            "task_uid", "grade", "level", "level_name", "section",
            "theme_id", "theme", "statement", "answer", "solution",
            "methods[]", "tags[]", "origin", "generator_run_id",
            "diversity_signature{}", "difficulty_justification",
            "originality_justification", "diagram_spec",
            "generator_model", "solver_model", "critic_model",
            "verification{}", "quality_status", "created_at",
            "solver_report", "critic_report",
        ]

        mapping = [
            ("task_uid", "source_id", "[OK] маппится"),
            ("grade", "class_level", "[OK] маппится"),
            ("level", "difficulty_level", "[OK] маппится (1..5)"),
            ("level_name", "—", "[ERROR] нет приёмника, значение отбрасывается"),
            ("section", "subject", "[OK] маппится"),
            ("theme_id", "subtopic", "[OK] маппится"),
            ("theme", "topic", "[OK] маппится"),
            ("statement", "task_text", "[OK] маппится (байт-в-байт)"),
            ("answer", "correct_answer", "[OK] маппится"),
            ("solution", "solution", "[OK] маппится (байт-в-байт)"),
            ("methods[]", "methods_json", "[OK] маппится (нормализован, JSON-массив строк)"),
            ("tags[]", "—", "[ERROR] нет приёмника, значение отбрасывается"),
            ("origin", "origin", "[OK] маппится (as-is: 'generated' / 'olympiad')"),
            (
                "—",
                "criteria_1_point",
                '[!]️ нет источника в JSONL, пишется ""',
            ),
            (
                "—",
                "criteria_2_points",
                '[!]️ нет источника в JSONL, пишется ""',
            ),
            ("—", "source", "[!]️ нет источника в JSONL (хардкод '" + SOURCE_VALUE + "')"),
            (
                "—",
                "task_type",
                "[!]️ нет источника в JSONL (хардкод '" + TASK_TYPE_VALUE + "')",
            ),
        ]

        self.field_mapping = mapping
        self.schema_ok = True
        return True

    def validate_and_normalize(self, row, seen_uids, seen_texts):
        """Проверить одну строку, вернуть (нормализованный dict или None, код ошибки).

        ВАЖНО: все счётчики и сбор аналитики выполняются ДО проверок,
        которые могут досрочно отвергнуть строку.  Это гарантирует, что
        статистика (включая geo_no_diagram) считается по всем прочитанным
        строкам, а не только по «валидным».
        """
        errors = []

        # ── извлечение сырых значений ──────────────────────────────────────
        task_uid = row.get("task_uid")
        if not task_uid:
            errors.append("missing task_uid")
            return None, errors

        if task_uid in seen_uids:
            self.duplicate_uids.append(task_uid)
            errors.append(f"duplicate task_uid: {task_uid}")
            return None, errors

        level = row.get("level")
        try:
            level = int(level)
        except (TypeError, ValueError):
            errors.append(f"invalid level: {level!r}")
            return None, errors
        if level < 1 or level > 5:
            errors.append(f"level out of range 1..5: {level}")
            return None, errors

        grade = row.get("grade")
        try:
            grade = int(grade)
        except (TypeError, ValueError):
            errors.append(f"invalid grade: {grade!r}")
            return None, errors

        statement = row.get("statement")
        answer = row.get("answer")
        solution = row.get("solution") or ""
        section = row.get("section", "")
        theme_id = row.get("theme_id", "")
        theme = row.get("theme", "")
        origin = row.get("origin", "")
        diagram_spec = row.get("diagram_spec")

        # ── аналитика / счётчики (до rejection-проверок) ───────────────────
        self.section_counter[section] += 1
        self.grade_level_counter[(grade, level)] += 1
        self.grade_theme_level_counter[(grade, theme_id, level)] += 1

        if section == "Геометрия" and diagram_spec is None:
            self.geo_no_diagram += 1

        self.origin_counter[origin] += 1

        # --- methods нормализация ---
        methods = flatten_methods(row.get("methods", []))
        for m in methods:
            self.all_methods[m] += 1

        if not methods:
            self.methods_json_null += 1

        # --- tags ---
        tags = row.get("tags", [])
        if isinstance(tags, list):
            for t in tags:
                if isinstance(t, str) and t.strip():
                    self.all_tags[t.strip()] += 1

        # ── валидационные проверки (могут отвергнуть строку) ───────────────
        if not statement or not str(statement).strip():
            self.empty_statement.append(task_uid)
            errors.append("empty statement")
            return None, errors

        if not answer or not str(answer).strip():
            self.empty_answer.append(task_uid)
            errors.append("empty answer")
            return None, errors

        # ── дедупликация по тексту задачи ─────────────────────────────────
        text_key = str(statement).strip()
        if text_key in seen_texts:
            self.text_duplicates += 1
            errors.append(f"duplicate text: {task_uid}")
            return None, errors
        seen_texts.add(text_key)

        # ── нормализация section через level_engine ───────────────────────
        from services.level_engine import _normalize_section as le_norm
        normalized_section = le_norm(section)

        # ── level_name канонизация ────────────────────────────────────────
        level_name_canon = LEVEL_NAME_CANON.get(
            level, row.get("level_name", "unknown")
        )

        # ── собранный объект ──────────────────────────────────────────────
        methods_json = json.dumps(methods, ensure_ascii=False) if methods else None

        normalized = {
            "task_uid": task_uid,
            "class_level": grade,
            "difficulty_level": level,
            "topic": theme,
            "subtopic": theme_id,
            "subject": normalized_section,
            "task_text": statement,
            "solution": solution,
            "correct_answer": answer,
            "criteria_1_point": "",
            "criteria_2_points": "",
            "source": SOURCE_VALUE,
            "task_type": TASK_TYPE_VALUE,
            "level_name_canon": level_name_canon,
            "methods_normalized": methods,
            "methods_json": methods_json,
            "origin": origin,
            "tags_raw": (
                [t for t in tags if isinstance(t, str) and t.strip()] if isinstance(tags, list) else []
            ),
        }

        return normalized, []

    def run(self):
        """Основной цикл."""
        # 1. Проверка схемы
        if not self.check_schema():
            self._print_blocker_report()
            return 2

        # 2. Чтение JSONL
        rows, parse_errors = read_jsonl(self.filepath)
        self.total_read = len(rows)
        self.parse_errors = parse_errors

        if parse_errors:
            for lineno, err in parse_errors[:10]:
                print(f"[PARSE ERROR] line {lineno}: {err}")
            if len(parse_errors) > 10:
                print(f"  ... и ещё {len(parse_errors) - 10} ошибок")

        # 3. Валидация + нормализация
        seen_uids = set()
        seen_texts = set()
        valid_rows = []

        for row in rows:
            normalized, errs = self.validate_and_normalize(row, seen_uids, seen_texts)
            if normalized is None:
                self.validation_errors.append((row.get("task_uid", "??"), errs))
                continue
            seen_uids.add(normalized["task_uid"])
            valid_rows.append(normalized)

        self.skipped = self.total_read - len(valid_rows)

        # В dry-run режиме c --flagged заранее показываем, сколько будет помечено
        if self.flagged and not self.apply:
            self.flagged_count = len(valid_rows)

        # 4. Запись в БД (только при --apply)
        if self.apply and valid_rows:
            self._write_to_db(valid_rows)

        # 5. Отчёт
        self._generate_report()
        return 0

    def _should_flag_existing(self, existing):
        """Вернуть True, если существующую запись можно безопасно флаговать.

        Флагуем только если:
        1. is_flagged УЖЕ True (ручное unflag -> is_flagged=False -> НЕ трогаем)
        2. flagged_reason пустой или равен нашей константе
           (чужой flagged_reason -> НЕ перетираем)
        """
        if not self.flagged:
            return False
        if not existing.is_flagged:
            return False
        existing_reason = getattr(existing, 'flagged_reason', None) or ''
        return existing_reason in ('', 'formyla_import_pending_scale_mapping')

    def _write_to_db(self, valid_rows):
        """Идемпотентная запись пакетами по batch_size.

        При ошибке пакета: rollback, затем повтор построчно — так
        отбраковывается только проблемная строка, а не весь пакет.
        Счётчики created/updated инкрементируются только после commit.
        """
        from models import db, AdaptiveTask

        FLAGGED_REASON = 'formyla_import_pending_scale_mapping'

        total = len(valid_rows)
        for start in range(0, total, self.batch_size):
            batch = valid_rows[start : start + self.batch_size]
            batch_num = start // self.batch_size + 1
            try:
                batch_created = 0
                batch_updated = 0
                for norm in batch:
                    existing = AdaptiveTask.query.filter_by(
                        source_id=norm["task_uid"]
                    ).first()

                    if existing:
                        # update
                        existing.class_level = norm["class_level"]
                        existing.difficulty_level = norm["difficulty_level"]
                        existing.topic = norm["topic"]
                        existing.subtopic = norm["subtopic"]
                        existing.subject = norm["subject"]
                        existing.task_text = norm["task_text"]
                        existing.solution = norm["solution"]
                        existing.correct_answer = norm["correct_answer"]
                        existing.criteria_1_point = norm["criteria_1_point"]
                        existing.criteria_2_points = norm["criteria_2_points"]
                        existing.source = norm["source"]
                        existing.task_type = norm["task_type"]
                        existing.origin = norm["origin"]
                        existing.methods_json = norm["methods_json"]
                        if self._should_flag_existing(existing):
                            existing.is_flagged = True
                            existing.flagged_reason = FLAGGED_REASON
                            self.flagged_count += 1
                        batch_updated += 1
                    else:
                        task = AdaptiveTask(
                            class_level=norm["class_level"],
                            difficulty_level=norm["difficulty_level"],
                            topic=norm["topic"],
                            subtopic=norm["subtopic"],
                            subject=norm["subject"],
                            task_text=norm["task_text"],
                            solution=norm["solution"],
                            correct_answer=norm["correct_answer"],
                            criteria_1_point=norm["criteria_1_point"],
                            criteria_2_points=norm["criteria_2_points"],
                            source=norm["source"],
                            source_id=norm["task_uid"],
                            task_type=norm["task_type"],
                            origin=norm["origin"],
                            methods_json=norm["methods_json"],
                        )
                        if self.flagged:
                            task.is_flagged = True
                            task.flagged_reason = FLAGGED_REASON
                            self.flagged_count += 1
                        db.session.add(task)
                        batch_created += 1

                db.session.commit()
                self.created += batch_created
                self.updated += batch_updated
            except Exception as batch_exc:
                db.session.rollback()
                print(
                    f"[WRITE ERROR] batch {batch_num}: {batch_exc} "
                    f"— rolled back, retrying row-by-row"
                )
                # Построчный повтор
                for norm in batch:
                    try:
                        existing = AdaptiveTask.query.filter_by(
                            source_id=norm["task_uid"]
                        ).first()

                        if existing:
                            existing.class_level = norm["class_level"]
                            existing.difficulty_level = norm["difficulty_level"]
                            existing.topic = norm["topic"]
                            existing.subtopic = norm["subtopic"]
                            existing.subject = norm["subject"]
                            existing.task_text = norm["task_text"]
                            existing.solution = norm["solution"]
                            existing.correct_answer = norm["correct_answer"]
                            existing.criteria_1_point = norm["criteria_1_point"]
                            existing.criteria_2_points = norm["criteria_2_points"]
                            existing.source = norm["source"]
                            existing.task_type = norm["task_type"]
                            existing.origin = norm["origin"]
                            existing.methods_json = norm["methods_json"]
                            if self._should_flag_existing(existing):
                                existing.is_flagged = True
                                existing.flagged_reason = FLAGGED_REASON
                                self.flagged_count += 1
                            db.session.commit()
                            self.updated += 1
                        else:
                            task = AdaptiveTask(
                                class_level=norm["class_level"],
                                difficulty_level=norm["difficulty_level"],
                                topic=norm["topic"],
                                subtopic=norm["subtopic"],
                                subject=norm["subject"],
                                task_text=norm["task_text"],
                                solution=norm["solution"],
                                correct_answer=norm["correct_answer"],
                                criteria_1_point=norm["criteria_1_point"],
                                criteria_2_points=norm["criteria_2_points"],
                                source=norm["source"],
                                source_id=norm["task_uid"],
                                task_type=norm["task_type"],
                                origin=norm["origin"],
                                methods_json=norm["methods_json"],
                            )
                            if self.flagged:
                                task.is_flagged = True
                                task.flagged_reason = FLAGGED_REASON
                                self.flagged_count += 1
                            db.session.add(task)
                            db.session.commit()
                            self.created += 1
                    except Exception as row_exc:
                        db.session.rollback()
                        self.write_errors.append(
                            {
                                "task_uid": norm["task_uid"],
                                "error": str(row_exc),
                                "traceback": traceback.format_exc(),
                            }
                        )
                        print(
                            f"[ROW ERROR] task_uid={norm['task_uid']}: {row_exc}"
                        )

    def _print_blocker_report(self):
        """Вывод при SCHEMA BLOCKER."""
        for blocker in self.schema_blockers:
            print(blocker)
        self._write_markdown_report()

    def _generate_report(self):
        """Вывод в stdout и запись markdown-отчёта."""
        self._print_summary()
        self._write_markdown_report()

    def _print_summary(self):
        """Краткая сводка в stdout."""
        print("=" * 60)
        print("FORMYLA JSONL -> AdaptiveTask  IMPORT REPORT")
        print("=" * 60)
        print(f"Файл: {self.filepath}")
        print(f"Режим: {'--apply (ЗАПИСЬ В БД)' if self.apply else 'DRY-RUN (без записи)'}")
        if self.flagged:
            print(f"Флаг: --flagged (is_flagged=True, flagged_reason='formyla_import_pending_scale_mapping')")
        print(f"Прочитано строк: {self.total_read}")
        print(f"Ошибок парсинга: {len(self.parse_errors)}")
        print(f"Ошибок валидации: {len(self.validation_errors)}")
        print(f"Дубликатов task_uid: {len(self.duplicate_uids)}")
        print(f"Дубликатов по тексту: {self.text_duplicates}")
        print(f"Пустых statement: {len(self.empty_statement)}")
        print(f"Пустых answer: {len(self.empty_answer)}")
        print(f"Геометрий без diagram_spec: {self.geo_no_diagram}")
        print(f"origin: generated {self.origin_counter.get('generated', 0)} / olympiad {self.origin_counter.get('olympiad', 0)}")
        print(f"methods_json NULL: {self.methods_json_null}")
        print(f"Создано: {self.created}")
        print(f"Обновлено: {self.updated}")
        print(f"Пропущено: {self.skipped}")
        print(f"Ошибок записи: {len(self.write_errors)}")
        if self.flagged:
            if self.apply:
                print(f"Помечено скрытыми (is_flagged=True): {self.flagged_count}")
            else:
                print(f"Будет помечено скрытыми (is_flagged=True): {self.flagged_count}")

        # Таблица grade × level
        print("\n── Таблица grade × level ──")
        grades = sorted(set(g for g, _ in self.grade_level_counter.keys()))
        levels = [1, 2, 3, 4, 5]
        header = "grade\\L | " + " | ".join(f"L{l}" for l in levels)
        print(header)
        print("-" * len(header))
        for g in grades:
            row_vals = [str(self.grade_level_counter.get((g, l), 0)) for l in levels]
            print(f"  {g:3d}  | " + " | ".join(f"{v:>3s}" for v in row_vals))

        # Ячейки не ровно 5
        print("\n── Ячейки grade × theme_id × level с числом задач ≠ 5 ──")
        uneven = []
        for (g, tid, l), cnt in sorted(self.grade_theme_level_counter.items()):
            if cnt != 5:
                uneven.append((g, tid, l, cnt))
        if uneven:
            for g, tid, l, cnt in uneven:
                print(f"  grade={g} theme_id={tid} level={l}: {cnt} задач")
        else:
            print("  ВСЕ ячейки содержат ровно 5 задач [OK]")

        print("\nПолный отчёт: scripts/out/import_report.md")

    def _write_markdown_report(self):
        """Записать полный отчёт в scripts/out/import_report.md."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = []
        lines.append(f"# FORMYLA JSONL Import Report")
        lines.append(f"**Date:** {now}")
        lines.append(f"**File:** `{self.filepath}`")
        lines.append(f"**Mode:** {'`--apply` (WRITE)' if self.apply else '`DRY-RUN` (no write)'}")
        lines.append("")

        # A. Schema check
        lines.append("## A. Schema Suitability")
        lines.append("")
        if self.schema_blockers:
            for b in self.schema_blockers:
                lines.append(f"- **{b}**")
        else:
            lines.append("[OK] `source_id` field exists — idempotent import possible.")
        lines.append("")

        lines.append("### Field Mapping")
        lines.append("")
        lines.append("| JSONL field | AdaptiveTask field | Status |")
        lines.append("|---|---|---|")
        for jsonl_f, db_f, status in self.field_mapping:
            lines.append(f"| `{jsonl_f}` | `{db_f}` | {status} |")
        lines.append("")

        # B. Normalization
        lines.append("## B. Normalization")
        lines.append("")
        lines.append(f"- **level_name**: канонизирован по `level` (1..5), игнорируя "
                     f"значение в файле.  Приёмника в AdaptiveTask нет, "
                     f"канонизированное значение отбрасывается.")
        lines.append(
            f"  Канонические значения: {', '.join(f'{k}={v}' for k, v in LEVEL_NAME_CANON.items())}"
        )
        lines.append(
            f"- **methods[]**: приведены к нижнему регистру, двойные пробелы убраны, "
            f"дубликаты склеены.  Результат сохранён в `methods_json` как "
            f"JSON-массив строк.  Если методов нет — `methods_json` = NULL."
        )
        lines.append(
            f"- **tags[]**: поле отбрасывается — в AdaptiveTask нет колонки "
            f"для тегов.  Статистика по тегам собрана в разделе Tags ниже."
        )
        lines.append(
            f"- **origin**: скопировано as-is (`'generated'` / `'olympiad'`) в "
            f"колонку `origin`."
        )
        lines.append(
            f"- **statement / solution**: импортированы байт-в-байт, без замен."
        )
        lines.append(
            f'- **criteria_1_point / criteria_2_points**: источник в JSONL '
            f'отсутствует, поля заполняются пустой строкой "" '
            f'(NOT NULL constraint).'
        )
        if self.flagged:
            lines.append(
                f"- **--flagged**: задачи помечаются `is_flagged=True`, "
                f"`flagged_reason='formyla_import_pending_scale_mapping'`. "
                f"При обновлении существующей записи флаг НЕ перетирается, "
                f"если `flagged_reason` был изменён вручную."
            )
        lines.append("")

        # section counter
        lines.append("### Section Values")
        lines.append("")
        lines.append("| section | count |")
        lines.append("|---|---|")
        for sec, cnt in self.section_counter.most_common():
            lines.append(f"| {sec} | {cnt} |")
        lines.append("")

        # Origin counter
        lines.append("### Origin Values")
        lines.append("")
        lines.append("| origin | count |")
        lines.append("|---|---|")
        for orig, cnt in sorted(self.origin_counter.items()):
            lines.append(f"| {orig} | {cnt} |")
        lines.append("")

        # Methods
        lines.append("### Unique Methods (normalized)")
        lines.append("")
        if self.all_methods:
            lines.append("| method | count |")
            lines.append("|---|---|")
            for m, cnt in self.all_methods.most_common():
                lines.append(f"| {m} | {cnt} |")
        else:
            lines.append("(no methods data)")
        lines.append("")

        # Tags
        lines.append("### Tags (ОТБРАСЫВАЮТСЯ — нет колонки в AdaptiveTask)")
        lines.append("")
        if self.all_tags:
            lines.append("| tag | count |")
            lines.append("|---|---|")
            for t, cnt in self.all_tags.most_common(50):
                lines.append(f"| {t} | {cnt} |")
        else:
            lines.append("(no tags data)")
        lines.append("")

        # C. Validation
        lines.append("## C. Validation")
        lines.append("")
        lines.append(f"- **Total read**: {self.total_read}")
        lines.append(f"- **Parse errors**: {len(self.parse_errors)}")
        lines.append(f"- **Validation errors**: {len(self.validation_errors)}")
        lines.append(f"- **Duplicate task_uid**: {len(self.duplicate_uids)}")
        lines.append(f"- **Duplicate by task_text**: {self.text_duplicates}")
        lines.append(f"- **Empty statement**: {len(self.empty_statement)}")
        lines.append(f"- **Empty answer**: {len(self.empty_answer)}")
        lines.append(
            f"- **Геометрия без diagram_spec**: {self.geo_no_diagram}"
        )
        lines.append(
            f"- **origin**: generated {self.origin_counter.get('generated', 0)}"
            f" / olympiad {self.origin_counter.get('olympiad', 0)}"
        )
        lines.append(
            f"- **methods_json NULL**: {self.methods_json_null}"
        )
        lines.append("")

        # Grade × Level table
        lines.append("### Grade × Level Grid")
        lines.append("")
        grades = sorted(set(g for g, _ in self.grade_level_counter.keys()))
        levels = [1, 2, 3, 4, 5]
        header = "| grade \\ level | " + " | ".join(f"L{l}" for l in levels) + " |"
        sep = "|---|" + "|".join(["---"] * len(levels)) + "|"
        lines.append(header)
        lines.append(sep)
        for g in grades:
            vals = [str(self.grade_level_counter.get((g, l), 0)) for l in levels]
            lines.append(f"| {g} | " + " | ".join(vals) + " |")
        lines.append("")

        # Uneven cells
        lines.append("### Cells with count ≠ 5")
        lines.append("")
        uneven = []
        for (g, tid, l), cnt in sorted(self.grade_theme_level_counter.items()):
            if cnt != 5:
                uneven.append((g, tid, l, cnt))
        if uneven:
            lines.append("| grade | theme_id | level | count |")
            lines.append("|---|---|---|---|")
            for g, tid, l, cnt in uneven:
                lines.append(f"| {g} | {tid} | {l} | {cnt} |")
        else:
            lines.append("[OK] All cells contain exactly 5 tasks.")
        lines.append("")

        # D. Write results
        lines.append("## D. Write Results")
        lines.append("")
        if self.apply:
            lines.append(f"- **Created**: {self.created}")
            lines.append(f"- **Updated**: {self.updated}")
            lines.append(f"- **Skipped**: {self.skipped}")
            lines.append(f"- **Write errors**: {len(self.write_errors)}")
            if self.flagged:
                lines.append(f"- **Помечено скрытыми (is_flagged=True)**: {self.flagged_count}")
            if self.write_errors:
                lines.append("")
                lines.append("| task_uid | error |")
                lines.append("|---|---|")
                for we in self.write_errors[:50]:
                    err_short = we["error"][:120]
                    lines.append(
                        f"| {we['task_uid']} | {err_short} |"
                    )
        else:
            lines.append("(dry-run — no writes performed)")
            if self.flagged:
                lines.append(f"- **Будет помечено скрытыми**: {self.flagged_count}")
        lines.append("")

        # Paths
        out_dir = Path("scripts/out")
        out_dir.mkdir(parents=True, exist_ok=True)
        report_path = out_dir / "import_report.md"
        report_path.write_text("\n".join(lines), encoding="utf-8")
        print(f"\n Markdown отчёт сохранён в: {report_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Импорт FORMYLA JSONL в AdaptiveTask"
    )
    parser.add_argument(
        "--file",
        required=True,
        help="Путь к JSONL-файлу",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Выполнить запись в БД (по умолчанию dry-run)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Размер пакета для commit (default: 50)",
    )
    parser.add_argument(
        "--flagged",
        action="store_true",
        help="Пометить задачи как скрытые (is_flagged=True, "
             "flagged_reason='formyla_import_pending_scale_mapping')",
    )
    args = parser.parse_args()

    # Проверка существования файла
    jsonl_path = Path(args.file)
    if not jsonl_path.exists():
        print(f"ERROR: файл не найден: {args.file}")
        sys.exit(3)

    # Инициализация Flask-приложения (нужно для db)
    # Импорт из корня проекта
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

    try:
        from app import app as flask_app
    except ImportError:
        # fallback: попробовать прямо из models
        from models import db
        from flask import Flask

        flask_app = Flask(__name__)
        flask_app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
            "DATABASE_URL", "sqlite:///database.db"
        )
        flask_app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
        db.init_app(flask_app)

    with flask_app.app_context():
        importer = FormylaImporter(
            filepath=str(jsonl_path),
            apply=args.apply,
            batch_size=args.batch_size,
            flagged=args.flagged,
        )
        exit_code = importer.run()
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
