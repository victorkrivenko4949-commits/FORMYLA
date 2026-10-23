# -*- coding: utf-8 -*-
"""
services/admin_base_stats.py — раздел «База» админ-статистики (ADMIN_BASE_V1, 06.10.2026).

Задача: показать ВСЁ, что реально лежит в базе данных сайта —
все задачи, все решения, все ответы пользователей, все сгенерированные
чертежи, переписку с AI-тьютором и любые другие записи, — без привязки к
конкретным моделям. Модуль не импортирует модели: он интроспектирует схему
через SQLAlchemy Inspector, поэтому новые таблицы автоматически попадают
в раздел, а изменение колонок ничего не ломает.

Принципы:
  * никогда не бросает исключения наружу — каждая таблица считается в
    try/except, ошибка попадает в поле `error`;
  * только SELECT, идентификаторы проверяются регуляркой и квотируются;
  * любая таблица с колонкой user_id / author_id / student_id / owner_id
    считается «пользовательской активностью» и доступна в карточке юзера.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import inspect as sa_inspect, text

from models import db

logger = logging.getLogger(__name__)

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

USER_FK_CANDIDATES = ("user_id", "author_id", "student_id", "owner_id", "sender_id")
TIME_COL_CANDIDATES = (
    "created_at", "submitted_at", "answered_at", "finished_at", "completed_at",
    "updated_at", "timestamp", "ts", "created", "date", "day", "started_at",
)
NAME_COL_CANDIDATES = (
    "username", "display_name", "name", "first_name", "full_name",
    "telegram_username", "tg_username", "login", "email", "phone",
)
# Колонки, которые интересно показать в ленте (в порядке приоритета).
INTEREST_COLS = (
    "status", "is_correct", "correct", "verdict", "result", "score", "xp",
    "level", "grade", "topic", "subtopic", "theme", "section", "task_id",
    "problem_id", "item_id", "set_id", "job_id", "kind", "type", "mode",
    "role", "answer", "user_answer", "given_answer", "final_answer",
    "correct_answer", "solution", "solution_text", "content", "message",
    "text", "title", "question", "ai_feedback", "feedback", "comment",
    "svg_path", "png_path", "image_url", "image_path", "svg", "url", "path",
    "solution_photos_json", "photos_json", "base_plan_json", "aux_plan_json",
)
IMAGE_HINT_COLS = (
    "solution_photos_json", "photos_json", "image_url", "image_path",
    "png_path", "svg_path", "png_url", "svg_url", "thumbnail", "preview",
)

# Человеческие названия и категории известных таблиц. Всё, чего нет в
# словаре, попадает в категорию «Прочее» с техническим именем таблицы.
TABLE_META: dict[str, tuple[str, str]] = {
    # category, label
    "daily_task_items":        ("Задачи и ответы", "Задачи дня — ответы пользователей"),
    "daily_task_sets":         ("Задачи и ответы", "Задачи дня — наборы"),
    "daily_generation_jobs":   ("Генерация", "Задачи дня — задания генерации"),
    "task_solutions":          ("Решения", "Решения задач (TaskSolution)"),
    "task_solution":           ("Решения", "Решения задач (TaskSolution)"),
    "solution_attempts":       ("Решения", "Попытки решений (SolutionAttempt)"),
    "solution_attempt":        ("Решения", "Попытки решений (SolutionAttempt)"),
    "adaptive_test_results":   ("Задачи и ответы", "Адаптивный тест — результаты"),
    "adaptive_test_result":    ("Задачи и ответы", "Адаптивный тест — результаты"),
    "adaptive_tasks":          ("Банк задач", "Адаптивные задачи"),
    "grade_tasks":             ("Банк задач", "Задачи тренажёра 5–6 класс"),
    "olympiad_tasks":          ("Банк задач", "Олимпиадные задачи"),
    "figure_build_jobs":       ("Чертежи", "Сгенерированные чертежи (FigureBuildJob)"),
    "figure_build_job":        ("Чертежи", "Сгенерированные чертежи (FigureBuildJob)"),
    "figure_credit_transactions": ("Чертежи", "Кредиты на чертежи"),
    "figures":                 ("Чертежи", "Чертежи (витрина)"),
    "chat_messages":           ("AI-тьютор", "Переписка с AI-тьютором"),
    "support_messages":        ("Поддержка", "Сообщения в поддержку"),
    "support_replies":         ("Поддержка", "Ответы поддержки"),
    "site_feedback":           ("Опросы", "Опрос «Как тебе сайт?»"),
    "site_events":             ("Активность", "События сайта (входы / heartbeat)"),
    "user_presence":           ("Активность", "Онлайн-присутствие"),
    "streak_records":          ("Активность", "Стрики"),
    "daily_quests":            ("Активность", "Ежедневные квесты"),
    "prep_plans":              ("Подготовка", "Планы подготовки"),
    "prep_days":               ("Подготовка", "Дни подготовки"),
    "learning_plans":          ("Подготовка", "Планы обучения (куратор)"),
    "student_diagnostics":     ("Подготовка", "Диагностика ученика"),
    "insights":                ("Банк неточностей", "Неточности (insights)"),
    "insight_notifications":   ("Банк неточностей", "Уведомления о неточностях"),
    "notifications":           ("Прочее", "Уведомления"),
    "friendships":             ("Соцсеть", "Друзья"),
    "direct_messages":         ("Соцсеть", "Личные сообщения"),
    "message_reactions":       ("Соцсеть", "Реакции"),
    "users":                   ("Пользователи", "Пользователи"),
    "user":                    ("Пользователи", "Пользователи"),
}

CATEGORY_ORDER = [
    "Задачи и ответы", "Решения", "Чертежи", "AI-тьютор", "Банк задач",
    "Генерация", "Подготовка", "Активность", "Поддержка", "Опросы",
    "Банк неточностей", "Соцсеть", "Пользователи", "Прочее",
]

_SKIP_TABLES = {"alembic_version", "sqlite_sequence"}


# ──────────────────────────────────────────────────────────────────────
# низкоуровневые помощники
# ──────────────────────────────────────────────────────────────────────
def _q(ident: str) -> str:
    if not _IDENT_RE.match(ident):
        raise ValueError(f"bad identifier: {ident!r}")
    return '"' + ident + '"'


def _scalar(sql: str, **params) -> Any:
    try:
        return db.session.execute(text(sql), params).scalar()
    except Exception as e:  # noqa: BLE001
        db.session.rollback()
        raise e


def _rows(sql: str, **params) -> list[dict]:
    try:
        res = db.session.execute(text(sql), params)
        cols = list(res.keys())
        return [dict(zip(cols, r)) for r in res.fetchall()]
    except Exception as e:  # noqa: BLE001
        db.session.rollback()
        raise e


def _schema() -> dict[str, list[dict]]:
    """{table: [ {name, type}, ... ]} для всех таблиц текущей БД."""
    insp = sa_inspect(db.engine)
    out: dict[str, list[dict]] = {}
    for t in insp.get_table_names():
        if t in _SKIP_TABLES or not _IDENT_RE.match(t):
            continue
        try:
            out[t] = [{"name": c["name"], "type": str(c.get("type", ""))}
                      for c in insp.get_columns(t)]
        except Exception as e:  # noqa: BLE001
            logger.warning("[admin_base] get_columns(%s) failed: %r", t, e)
    return out


def _pick(cols: list[str], candidates: tuple[str, ...]) -> str | None:
    s = set(cols)
    for c in candidates:
        if c in s:
            return c
    return None


def _meta(table: str) -> tuple[str, str]:
    if table in TABLE_META:
        return TABLE_META[table]
    low = table.lower()
    if "figure" in low or "drawing" in low or "svg" in low:
        return ("Чертежи", table)
    if "solution" in low or "attempt" in low:
        return ("Решения", table)
    if "task" in low or "answer" in low or "quiz" in low or "test" in low:
        return ("Задачи и ответы", table)
    if "chat" in low or "tutor" in low or "coach" in low:
        return ("AI-тьютор", table)
    return ("Прочее", table)


def _to_jsonable(v: Any) -> Any:
    if v is None or isinstance(v, (int, float, bool)):
        return v
    if isinstance(v, datetime):
        return v.isoformat(sep=" ", timespec="seconds")
    if isinstance(v, (bytes, bytearray)):
        return f"<{len(v)} bytes>"
    s = str(v)
    return s


def _short(v: Any, n: int = 400) -> Any:
    v = _to_jsonable(v)
    if isinstance(v, str) and len(v) > n:
        return v[:n] + "…"
    return v


def _extract_images(row: dict) -> list[str]:
    """Собрать URL картинок/чертежей из строки (фото решений, svg/png)."""
    urls: list[str] = []
    for c, v in row.items():
        if v is None:
            continue
        cl = c.lower()
        if cl in IMAGE_HINT_COLS or cl.endswith("_url") or cl.endswith("_path"):
            sv = str(v).strip()
            if sv.startswith("[") or sv.startswith("{"):
                try:
                    data = json.loads(sv)
                    if isinstance(data, dict):
                        data = list(data.values())
                    for item in data or []:
                        if isinstance(item, str):
                            urls.append(item)
                        elif isinstance(item, dict):
                            for k in ("url", "src", "path", "png", "svg"):
                                if item.get(k):
                                    urls.append(str(item[k]))
                                    break
                except Exception:  # noqa: BLE001
                    pass
            elif any(sv.lower().endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif")) \
                    or sv.startswith("/static/") or sv.startswith("http"):
                urls.append(sv)
    # нормализуем относительные пути
    norm = []
    for u in urls:
        if not u:
            continue
        if not (u.startswith("/") or u.startswith("http") or u.startswith("data:")):
            u = "/" + u.lstrip("./")
        norm.append(u)
    return norm[:12]


# ──────────────────────────────────────────────────────────────────────
# публичное API
# ──────────────────────────────────────────────────────────────────────
def users_table_info(schema: dict | None = None) -> dict | None:
    schema = schema or _schema()
    for name in ("users", "user", "app_users", "accounts"):
        if name in schema:
            cols = [c["name"] for c in schema[name]]
            return {
                "table": name,
                "cols": cols,
                "name_cols": [c for c in NAME_COL_CANDIDATES if c in cols],
                "time_col": _pick(cols, ("created_at", "registered_at", "created", "date_joined")),
                "last_seen_col": _pick(cols, ("last_seen", "last_seen_at", "last_login", "last_active_at", "last_activity")),
                "has_is_admin": "is_admin" in cols,
                "has_is_guest": "is_guest" in cols,
            }
    return None


def collect_summary() -> dict:
    """Сводка по всей базе: все таблицы, счётчики, свежесть, категория."""
    schema = _schema()
    now = datetime.utcnow()
    d1 = now - timedelta(days=1)
    d7 = now - timedelta(days=7)
    d30 = now - timedelta(days=30)

    tables: list[dict] = []
    totals = {"rows": 0, "tables": 0, "user_tables": 0, "content_tables": 0}
    cat_totals: dict[str, int] = {}

    for t, cols_meta in sorted(schema.items()):
        cols = [c["name"] for c in cols_meta]
        fk = _pick(cols, USER_FK_CANDIDATES)
        tcol = _pick(cols, TIME_COL_CANDIDATES)
        cat, label = _meta(t)
        info: dict[str, Any] = {
            "table": t, "label": label, "category": cat,
            "user_fk": fk, "time_col": tcol, "columns": cols,
            "rows": None, "users": None, "last_24h": None, "last_7d": None,
            "last_30d": None, "last_at": None, "error": None,
        }
        try:
            info["rows"] = int(_scalar(f"SELECT COUNT(*) FROM {_q(t)}") or 0)
            if fk:
                info["users"] = int(_scalar(
                    f"SELECT COUNT(DISTINCT {_q(fk)}) FROM {_q(t)} WHERE {_q(fk)} IS NOT NULL") or 0)
            if tcol:
                try:
                    info["last_24h"] = int(_scalar(
                        f"SELECT COUNT(*) FROM {_q(t)} WHERE {_q(tcol)} >= :s", s=d1) or 0)
                    info["last_7d"] = int(_scalar(
                        f"SELECT COUNT(*) FROM {_q(t)} WHERE {_q(tcol)} >= :s", s=d7) or 0)
                    info["last_30d"] = int(_scalar(
                        f"SELECT COUNT(*) FROM {_q(t)} WHERE {_q(tcol)} >= :s", s=d30) or 0)
                    info["last_at"] = _to_jsonable(_scalar(
                        f"SELECT MAX({_q(tcol)}) FROM {_q(t)}"))
                except Exception as e:  # noqa: BLE001
                    info["error"] = f"time: {e.__class__.__name__}"
        except Exception as e:  # noqa: BLE001
            info["error"] = f"{e.__class__.__name__}: {str(e)[:120]}"
            logger.warning("[admin_base] summary(%s) failed: %r", t, e)

        tables.append(info)
        totals["tables"] += 1
        totals["rows"] += info["rows"] or 0
        if fk:
            totals["user_tables"] += 1
        else:
            totals["content_tables"] += 1
        cat_totals[cat] = cat_totals.get(cat, 0) + (info["rows"] or 0)

    by_category: list[dict] = []
    for cat in CATEGORY_ORDER:
        items = [x for x in tables if x["category"] == cat]
        if items:
            by_category.append({"category": cat, "rows": cat_totals.get(cat, 0),
                                "tables": sorted(items, key=lambda x: -(x["rows"] or 0))})

    # ключевые цифры для шапки
    def _sum(cat: str) -> int:
        return cat_totals.get(cat, 0)

    headline = {
        "answers": _sum("Задачи и ответы"),
        "solutions": _sum("Решения"),
        "figures": _sum("Чертежи"),
        "tutor": _sum("AI-тьютор"),
        "bank": _sum("Банк задач"),
        "all_rows": totals["rows"],
        "tables": totals["tables"],
    }
    return {
        "generated_at": now.isoformat(sep=" ", timespec="seconds"),
        "dialect": db.engine.dialect.name,
        "totals": totals,
        "headline": headline,
        "by_category": by_category,
        "tables": tables,
    }


def list_users(q: str = "", limit: int = 300) -> list[dict]:
    """Все пользователи + суммарная активность по всем user-таблицам.
    Поиск q — по id и всем name-колонкам (регистронезависимо)."""
    schema = _schema()
    ut = users_table_info(schema)
    if not ut:
        return []
    t = ut["table"]
    sel_cols = ["id"] + ut["name_cols"]
    if ut["time_col"]:
        sel_cols.append(ut["time_col"])
    if ut["last_seen_col"]:
        sel_cols.append(ut["last_seen_col"])
    if ut["has_is_admin"]:
        sel_cols.append("is_admin")
    if ut["has_is_guest"]:
        sel_cols.append("is_guest")
    sel_cols = list(dict.fromkeys(c for c in sel_cols if c in ut["cols"]))

    where = ""
    params: dict[str, Any] = {}
    q = (q or "").strip()
    if q:
        parts = []
        if q.isdigit():
            parts.append('"id" = :qid')
            params["qid"] = int(q)
        for i, c in enumerate(ut["name_cols"]):
            parts.append(f"LOWER(CAST({_q(c)} AS TEXT)) LIKE :q{i}")
            params[f"q{i}"] = f"%{q.lower()}%"
        if parts:
            where = " WHERE " + " OR ".join(parts)

    sql = f"SELECT {', '.join(_q(c) for c in sel_cols)} FROM {_q(t)}{where} ORDER BY \"id\" DESC LIMIT :lim"
    params["lim"] = int(limit)
    try:
        users = _rows(sql, **params)
    except Exception as e:  # noqa: BLE001
        logger.warning("[admin_base] list_users failed: %r", e)
        return []

    # активность: по каждой user-таблице GROUP BY fk → словарь uid → count
    activity: dict[int, dict[str, int]] = {}
    for tbl, cols_meta in schema.items():
        if tbl == t:
            continue
        cols = [c["name"] for c in cols_meta]
        fk = _pick(cols, USER_FK_CANDIDATES)
        if not fk:
            continue
        try:
            for r in _rows(f"SELECT {_q(fk)} AS uid, COUNT(*) AS n FROM {_q(tbl)} "
                           f"WHERE {_q(fk)} IS NOT NULL GROUP BY {_q(fk)}"):
                try:
                    uid = int(r["uid"])
                except Exception:  # noqa: BLE001
                    continue
                activity.setdefault(uid, {})[tbl] = int(r["n"] or 0)
        except Exception as e:  # noqa: BLE001
            logger.debug("[admin_base] activity(%s) failed: %r", tbl, e)

    out: list[dict] = []
    for u in users:
        uid = int(u["id"])
        act = activity.get(uid, {})
        cats: dict[str, int] = {}
        for tbl, n in act.items():
            c = _meta(tbl)[0]
            cats[c] = cats.get(c, 0) + n
        name = next((str(u[c]) for c in ut["name_cols"] if u.get(c)), f"user #{uid}")
        out.append({
            "id": uid,
            "name": name,
            "fields": {k: _to_jsonable(v) for k, v in u.items()},
            "total": sum(act.values()),
            "answers": cats.get("Задачи и ответы", 0),
            "solutions": cats.get("Решения", 0),
            "figures": cats.get("Чертежи", 0),
            "tutor": cats.get("AI-тьютор", 0),
            "by_table": act,
            "is_admin": bool(u.get("is_admin")) if "is_admin" in u else False,
            "is_guest": bool(u.get("is_guest")) if "is_guest" in u else False,
        })
    out.sort(key=lambda x: -x["total"])
    return out


def user_detail(user_id: int, per_table: int = 100) -> dict | None:
    """Полная карточка пользователя: профиль + ВСЕ записи из ВСЕХ таблиц,
    где есть ссылка на него (ответы, решения, чертежи, чат, события…)."""
    schema = _schema()
    ut = users_table_info(schema)
    profile: dict | None = None
    if ut:
        try:
            rows = _rows(f"SELECT * FROM {_q(ut['table'])} WHERE \"id\" = :uid", uid=int(user_id))
            if rows:
                profile = {k: _short(v, 200) for k, v in rows[0].items()
                           if k.lower() not in ("password", "password_hash", "auth_code", "token", "api_key")}
        except Exception as e:  # noqa: BLE001
            logger.warning("[admin_base] profile failed: %r", e)
    if profile is None and ut:
        return None

    name = f"user #{user_id}"
    if profile and ut:
        name = next((str(profile[c]) for c in ut["name_cols"] if profile.get(c)), name)

    sections: list[dict] = []
    grand_total = 0
    timeline: list[dict] = []
    gallery: list[dict] = []

    for tbl, cols_meta in sorted(schema.items()):
        if ut and tbl == ut["table"]:
            continue
        cols = [c["name"] for c in cols_meta]
        fk = _pick(cols, USER_FK_CANDIDATES)
        if not fk:
            continue
        tcol = _pick(cols, TIME_COL_CANDIDATES)
        cat, label = _meta(tbl)
        sec: dict[str, Any] = {"table": tbl, "label": label, "category": cat,
                               "count": 0, "rows": [], "columns": [], "error": None}
        try:
            sec["count"] = int(_scalar(
                f"SELECT COUNT(*) FROM {_q(tbl)} WHERE {_q(fk)} = :uid", uid=int(user_id)) or 0)
            if sec["count"]:
                order = _q(tcol) if tcol else ('"id"' if "id" in cols else _q(cols[0]))
                raw = _rows(f"SELECT * FROM {_q(tbl)} WHERE {_q(fk)} = :uid "
                            f"ORDER BY {order} DESC LIMIT :lim",
                            uid=int(user_id), lim=int(per_table))
                # колонки для показа: интересные + время + id
                show = [c for c in cols if c in INTEREST_COLS]
                if tcol and tcol not in show:
                    show.insert(0, tcol)
                if "id" in cols and "id" not in show:
                    show.insert(0, "id")
                if not show:
                    show = cols[:8]
                sec["columns"] = show
                for r in raw:
                    imgs = _extract_images(r)
                    item = {"cells": {c: _short(r.get(c)) for c in show},
                            "images": imgs,
                            "raw": {k: _short(v, 1500) for k, v in r.items()}}
                    sec["rows"].append(item)
                    when = _to_jsonable(r.get(tcol)) if tcol else None
                    timeline.append({"when": when or "", "table": tbl, "label": label,
                                     "category": cat, "id": r.get("id"),
                                     "summary": _row_summary(r)})
                    for u in imgs:
                        gallery.append({"url": u, "table": tbl, "label": label, "when": when})
        except Exception as e:  # noqa: BLE001
            sec["error"] = f"{e.__class__.__name__}: {str(e)[:120]}"
            logger.warning("[admin_base] user_detail(%s) failed: %r", tbl, e)
        if sec["count"] or sec["error"]:
            sections.append(sec)
            grand_total += sec["count"]

    sections.sort(key=lambda s: (CATEGORY_ORDER.index(s["category"])
                                 if s["category"] in CATEGORY_ORDER else 99, -s["count"]))
    timeline.sort(key=lambda x: str(x["when"]), reverse=True)

    cats: dict[str, int] = {}
    for s in sections:
        cats[s["category"]] = cats.get(s["category"], 0) + s["count"]

    return {
        "user_id": int(user_id),
        "name": name,
        "profile": profile or {},
        "total": grand_total,
        "by_category": [{"category": c, "count": cats.get(c, 0)} for c in CATEGORY_ORDER if c in cats],
        "sections": sections,
        "timeline": timeline[:500],
        "gallery": gallery[:200],
    }


def _row_summary(r: dict) -> str:
    bits = []
    for c in ("status", "is_correct", "verdict", "score", "topic", "subtopic",
              "answer", "user_answer", "title", "message", "content", "text", "ai_feedback"):
        if c in r and r[c] is not None and str(r[c]).strip():
            bits.append(f"{c}={_short(r[c], 80)}")
        if len(bits) >= 4:
            break
    return "; ".join(bits)


def recent_feed(limit_per_table: int = 20, total_limit: int = 300) -> list[dict]:
    """Единая лента последних событий по всем user-таблицам (для раздела «База»)."""
    schema = _schema()
    ut = users_table_info(schema)
    feed: list[dict] = []
    for tbl, cols_meta in schema.items():
        if ut and tbl == ut["table"]:
            continue
        cols = [c["name"] for c in cols_meta]
        fk = _pick(cols, USER_FK_CANDIDATES)
        tcol = _pick(cols, TIME_COL_CANDIDATES)
        if not fk or not tcol:
            continue
        cat, label = _meta(tbl)
        try:
            for r in _rows(f"SELECT * FROM {_q(tbl)} ORDER BY {_q(tcol)} DESC LIMIT :lim",
                           lim=int(limit_per_table)):
                feed.append({
                    "when": _to_jsonable(r.get(tcol)) or "",
                    "user_id": r.get(fk),
                    "table": tbl, "label": label, "category": cat,
                    "id": r.get("id"),
                    "summary": _row_summary(r),
                    "images": _extract_images(r),
                })
        except Exception as e:  # noqa: BLE001
            logger.debug("[admin_base] feed(%s) failed: %r", tbl, e)
    feed.sort(key=lambda x: str(x["when"]), reverse=True)
    return feed[:total_limit]
