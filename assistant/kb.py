# -*- coding: utf-8 -*-
"""FORMYLA assistant knowledge base (renamed from knowledge.py to dodge a
mysterious file-watcher that kept truncating ``knowledge.py`` to 0 bytes).

The table schema (TZ §8) is portable between SQLite (local dev) and
PostgreSQL (Render production). First call to :func:`init_db` creates
the tables on-the-fly and seeds the KB with the records from TZ §9.
"""
from __future__ import annotations

import logging
import re
from typing import List, Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)


SEED_RECORDS: List[dict] = [
    {
        "title": "Как начать пользоваться FORMYLA",
        "category": "getting_started",
        "question": "Как начать?",
        "answer": (
            "Чтобы начать пользоваться FORMYLA: 1) зарегистрируйся или войди в "
            "аккаунт; 2) выбери свой класс; 3) пройди стартовую диагностику. "
            "После этого платформа покажет, какие темы и методы стоит "
            "прокачать в первую очередь."
        ),
        "keywords": "старт, начать, регистрация, вход, первый раз, как пользоваться, новичок, онбординг",
        "page_url": "/",
    },
    {
        "title": "Как пройти адаптивный тест",
        "category": "adaptive_test",
        "question": "Как пройти адаптивный тест?",
        "answer": (
            "Чтобы пройти адаптивный тест: 1) открой раздел «Адаптивный тест» "
            "или «Диагностика»; 2) выбери свой класс; 3) начни решать задачи. "
            "Система учитывает твои ответы и подбирает уровень сложности, "
            "чтобы определить сильные и слабые темы."
        ),
        "keywords": "адаптивный тест, диагностика, тест, уровень, слабые темы, пройти тест, начать тест",
        "page_url": "/adaptive-test",
    },
    {
        "title": "Как следить за прогрессом",
        "category": "progress",
        "question": "Где смотреть прогресс?",
        "answer": (
            "Прогресс можно смотреть в личном кабинете. Там отображаются "
            "решённые задачи, темы, уровень подготовки, слабые места и "
            "рекомендации, что решать дальше."
        ),
        "keywords": "прогресс, статистика, личный кабинет, результаты, слабые места, успехи, мой профиль",
        "page_url": "/profile",
    },
    {
        "title": "Где найти задачи",
        "category": "problems",
        "question": "Где найти задачи?",
        "answer": (
            "Задачи находятся в разделе с пробниками и темами. Можно выбрать "
            "класс, тему, метод или этап подготовки и решать задачи по "
            "уровню сложности."
        ),
        "keywords": "задачи, пробники, темы, класс, сложность, решать, что решать",
        "page_url": "/problems",
    },
    {
        "title": "Что такое методы",
        "category": "methods",
        "question": "Что такое методы?",
        "answer": (
            "Методы — это приёмы решения олимпиадных задач. В FORMYLA задачи "
            "связаны с методами, чтобы ученик понимал не только ответ, но и "
            "идею решения."
        ),
        "keywords": "методы, приёмы, идеи, решение, олимпиадные задачи, способы решения",
        "page_url": "/methods",
    },
    {
        "title": "Как работают пробники",
        "category": "probniki",
        "question": "Как работают пробники?",
        "answer": (
            "Пробники — это наборы задач в формате тренировки. Они помогают "
            "проверить уровень по теме, классу или этапу олимпиады и понять, "
            "какие методы нужно повторить."
        ),
        "keywords": "пробник, пробники, вариант, этап, тренировка, всош, набор задач",
        "page_url": "/probniki",
    },
    {
        "title": "Подготовка к ВсОШ",
        "category": "olympiads",
        "question": "Как готовиться к ВсОШ?",
        "answer": (
            "Для подготовки к ВсОШ в FORMYLA: 1) пройди диагностику; "
            "2) решай тематические и этапные пробники; 3) изучай методы "
            "решения; 4) отслеживай прогресс в личном кабинете."
        ),
        "keywords": "всош, олимпиада, подготовка, муниципальный этап, региональный этап, школьный этап, заключительный",
        "page_url": "/vsosh",
    },
    {
        "title": "Тарифы",
        "category": "tariffs",
        "question": "Какие тарифы?",
        "answer": (
            "Информация о тарифах находится в разделе «Тарифы». Там можно "
            "посмотреть, какие возможности доступны на каждом уровне доступа."
        ),
        "keywords": "тариф, тарифы, цена, оплата, подписка, доступ, premium, про, стоимость",
        "page_url": "/pricing",
    },
    {
        "title": "Ошибка на сайте",
        "category": "errors",
        "question": "Что делать, если на сайте ошибка?",
        "answer": (
            "Если на сайте возникла ошибка: 1) обнови страницу; 2) войди в "
            "аккаунт заново; 3) если проблема повторяется — напиши в "
            "поддержку и опиши, что именно произошло."
        ),
        "keywords": "ошибка, не работает, баг, проблема, зависло, поддержка, лагает, не грузится, белый экран",
        "page_url": "/support",
    },
]


_DDL_KB_PG = (
    "CREATE TABLE IF NOT EXISTS assistant_knowledge ("
    " id          SERIAL PRIMARY KEY,"
    " title       TEXT NOT NULL,"
    " category    TEXT NOT NULL,"
    " question    TEXT,"
    " answer      TEXT NOT NULL,"
    " keywords    TEXT,"
    " page_url    TEXT,"
    " is_active   BOOLEAN DEFAULT TRUE,"
    " created_at  TIMESTAMP DEFAULT NOW(),"
    " updated_at  TIMESTAMP DEFAULT NOW()"
    ");"
)
_DDL_KB_SQLITE = (
    "CREATE TABLE IF NOT EXISTS assistant_knowledge ("
    " id          INTEGER PRIMARY KEY AUTOINCREMENT,"
    " title       TEXT NOT NULL,"
    " category    TEXT NOT NULL,"
    " question    TEXT,"
    " answer      TEXT NOT NULL,"
    " keywords    TEXT,"
    " page_url    TEXT,"
    " is_active   INTEGER DEFAULT 1,"
    " created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
    " updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
    ");"
)
_DDL_LOGS_PG = (
    "CREATE TABLE IF NOT EXISTS assistant_logs ("
    " id                 SERIAL PRIMARY KEY,"
    " user_message       TEXT NOT NULL,"
    " assistant_answer   TEXT,"
    " category           TEXT,"
    " used_context_ids   TEXT,"
    " is_refused         BOOLEAN DEFAULT FALSE,"
    " error              TEXT,"
    " created_at         TIMESTAMP DEFAULT NOW()"
    ");"
)
_DDL_LOGS_SQLITE = (
    "CREATE TABLE IF NOT EXISTS assistant_logs ("
    " id                 INTEGER PRIMARY KEY AUTOINCREMENT,"
    " user_message       TEXT NOT NULL,"
    " assistant_answer   TEXT,"
    " category           TEXT,"
    " used_context_ids   TEXT,"
    " is_refused         INTEGER DEFAULT 0,"
    " error              TEXT,"
    " created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
    ");"
)


def init_db() -> None:
    """Create tables and seed the KB on first run. Idempotent."""
    from models import db
    engine = db.engine
    dialect = engine.dialect.name
    with engine.begin() as conn:
        if dialect == "postgresql":
            conn.execute(text(_DDL_KB_PG))
            conn.execute(text(_DDL_LOGS_PG))
        else:
            conn.execute(text(_DDL_KB_SQLITE))
            conn.execute(text(_DDL_LOGS_SQLITE))
        count = conn.execute(text("SELECT COUNT(*) FROM assistant_knowledge")).scalar() or 0
        if count == 0:
            logger.info("assistant.kb: seeding %d records", len(SEED_RECORDS))
            for rec in SEED_RECORDS:
                conn.execute(
                    text(
                        "INSERT INTO assistant_knowledge "
                        "(title, category, question, answer, keywords, page_url, is_active) "
                        "VALUES (:title, :category, :question, :answer, :keywords, :page_url, :is_active)"
                    ),
                    {
                        "title": rec["title"],
                        "category": rec["category"],
                        "question": rec.get("question"),
                        "answer": rec["answer"],
                        "keywords": rec.get("keywords"),
                        "page_url": rec.get("page_url"),
                        "is_active": True,
                    },
                )


def all_active() -> List[dict]:
    """Return every active KB row as plain dicts."""
    from models import db
    rows = db.session.execute(
        text(
            "SELECT id, title, category, question, answer, keywords, page_url "
            "FROM assistant_knowledge WHERE is_active = :flag"
        ),
        {"flag": True},
    ).mappings().all()
    return [dict(r) for r in rows]


_WORD_RE = re.compile(r"[\w\-]+", flags=re.UNICODE)

_STOPWORDS = {
    "и", "в", "во", "не", "на", "я", "что", "он", "с", "со", "как", "а", "то",
    "все", "она", "так", "его", "но", "да", "ты", "к", "у", "же", "вы", "за",
    "по", "только", "ее", "мне", "было", "вот", "от", "меня", "еще", "нет",
    "о", "из", "ему", "когда", "ну", "ли", "если", "уже", "или", "ни",
    "был", "была", "были", "до", "вас", "для", "мы", "тебя", "их",
    "чем", "сам", "чтоб", "без", "себе", "под", "будет", "тогда", "кто",
    "этот", "того", "потому", "этого", "какой", "ним", "этом", "один",
    "мой", "тем", "чтобы", "нее", "сейчас", "куда", "зачем", "всех",
    "никогда", "можно", "при", "два", "об", "другой", "хоть",
    "после", "над", "больше", "тот", "через", "эти", "нас", "про", "всего",
    "них", "какая", "много", "разве", "три", "эту", "моя", "это", "эта",
}


def _tokens(text_: str) -> List[str]:
    return [
        t.lower()
        for t in _WORD_RE.findall(text_ or "")
        if t.lower() not in _STOPWORDS and len(t) >= 2
    ]


def _score_row(row: dict, query_tokens: List[str], raw_query_lc: str) -> float:
    if not query_tokens:
        return 0.0
    fields = (
        (row.get("title") or "",    3.0),
        (row.get("question") or "", 2.5),
        (row.get("keywords") or "", 2.0),
        (row.get("category") or "", 1.5),
        (row.get("answer") or "",   0.8),
    )
    score = 0.0
    for haystack, weight in fields:
        haystack_lc = haystack.lower()
        if not haystack_lc:
            continue
        for t in query_tokens:
            if t in haystack_lc:
                score += weight
        if raw_query_lc and len(raw_query_lc) >= 4 and raw_query_lc in haystack_lc:
            score += weight * 1.5
    return score


def search(query: str, *, limit: int = 5) -> List[dict]:
    """Return up to ``limit`` most relevant KB rows for ``query``."""
    rows = all_active()
    if not rows:
        return []
    raw_lc = (query or "").strip().lower()
    tokens = _tokens(raw_lc)
    if not tokens:
        return []
    scored = []
    for r in rows:
        s = _score_row(r, tokens, raw_lc)
        if s > 0:
            scored.append((s, r))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [r for _s, r in scored[:limit]]


def log_event(
    *,
    user_message: str,
    assistant_answer: Optional[str] = None,
    category: Optional[str] = None,
    used_context_ids: Optional[List[int]] = None,
    is_refused: bool = False,
    error: Optional[str] = None,
) -> None:
    """Best-effort append-only logging. Swallows all DB errors."""
    from models import db
    try:
        db.session.execute(
            text(
                "INSERT INTO assistant_logs "
                "(user_message, assistant_answer, category, used_context_ids, is_refused, error) "
                "VALUES (:user_message, :assistant_answer, :category, :used_context_ids, :is_refused, :error)"
            ),
            {
                "user_message": (user_message or "")[:2000],
                "assistant_answer": (assistant_answer or "")[:4000],
                "category": (category or "")[:120] or None,
                "used_context_ids": (
                    ",".join(str(i) for i in used_context_ids) if used_context_ids else None
                ),
                "is_refused": bool(is_refused),
                "error": (error or "")[:500] or None,
            },
        )
        db.session.commit()
    except Exception as e:
        logger.debug("assistant.kb.log_event: %s", e)
        try:
            db.session.rollback()
        except Exception:
            pass


__all__ = [
    "SEED_RECORDS",
    "init_db",
    "all_active",
    "search",
    "log_event",
]
