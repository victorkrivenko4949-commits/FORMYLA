# -*- coding: utf-8 -*-
r"""Идемпотентный boot-hook: чинит битые \sqrt[n]{} / \sqrt{} корни прямо в БД.

JSON-сидеры чинятся отдельно (scripts/normalize_roots_in_data.py), но прод
читает данные из PostgreSQL, куда задачи уже залиты. Этот хук на каждом старте
прогоняет текстовые колонки через services.latex_root_normalizer.normalize_roots
и UPDATE-ит ТОЛЬКО те строки, где результат отличается от текущего значения.

Безопасно запускать каждый редеплой:
  * нормализатор идемпотентен — повторный прогон ничего не меняет;
  * только UPDATE существующих строк (никаких INSERT/DELETE, без дублей);
  * правится лишь однозначно-битый LaTeX (см. docstring нормализатора).

Покрываемые таблицы и колонки:
  * olympiad_tasks : condition_md, idea_md, solution_md, answer
  * method_tasks   : text, answer, solution_idea
  * adaptive_tasks : task_text, solution, correct_answer
"""
from __future__ import annotations

from services.latex_root_normalizer import normalize_roots

# (ORM-класс, [колонки]) — заполняется лениво внутри функции, чтобы не тянуть
# тяжёлые импорты при загрузке модуля.
_TARGETS = [
    ("OlympiadTask", "olympiad_tasks",
     ("condition_md", "idea_md", "solution_md", "answer")),
    ("MethodTask", "method_tasks",
     ("text", "answer", "solution_idea")),
    ("AdaptiveTask", "adaptive_tasks",
     ("task_text", "solution", "correct_answer")),
]


def _resolve_models():
    """Возвращает {имя: ORM-класс} для целевых таблиц (или None, если нет)."""
    models = {}
    try:
        from models_olympiad import OlympiadTask, MethodTask
        models["OlympiadTask"] = OlympiadTask
        models["MethodTask"] = MethodTask
    except Exception:
        pass
    try:
        from models import AdaptiveTask
        models["AdaptiveTask"] = AdaptiveTask
    except Exception:
        pass
    return models


def run_latex_root_db_fix(app, db):
    """Чинит корни в БД. Идемпотентно. Возвращает dict со счётчиками по таблицам."""
    summary = {}
    models = _resolve_models()

    with app.app_context():
        for model_name, table, cols in _TARGETS:
            model = models.get(model_name)
            if model is None:
                summary[table] = {"updated": 0, "skipped": "model not available"}
                continue
            try:
                updated = 0
                rows = model.query.all()
                for row in rows:
                    changed = False
                    for col in cols:
                        cur = getattr(row, col, None)
                        if isinstance(cur, str) and cur:
                            new = normalize_roots(cur)
                            if new != cur:
                                setattr(row, col, new)
                                changed = True
                    if changed:
                        updated += 1
                if updated:
                    db.session.commit()
                else:
                    db.session.rollback()
                summary[table] = {"updated": updated, "scanned": len(rows)}
                print(f"[LATEX-ROOT-DB-FIX] {table}: updated {updated} / {len(rows)} rows")
            except Exception as e:  # одна таблица не должна валить остальные
                db.session.rollback()
                summary[table] = {"updated": 0, "error": str(e)}
                print(f"[LATEX-ROOT-DB-FIX] {table}: FAILED {e}")

    total = sum(v.get("updated", 0) for v in summary.values())
    print(f"[LATEX-ROOT-DB-FIX] total rows updated: {total}")
    return summary


__all__ = ["run_latex_root_db_fix"]
